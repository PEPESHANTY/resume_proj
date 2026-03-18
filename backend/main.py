"""
FastAPI main application — ties auth, agents, renderer together.
"""
import json
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from backend.auth.models import User, init_db, get_db
from backend.auth.routes import router as auth_router, get_current_user
from backend.agents import orchestrator, extractor, formatter
from backend.renderer.build_cv_dynamic import render_cv
from backend.utils import (
    r2_enabled, r2_read_json, r2_write_json,
    r2_read_bytes, r2_write_bytes, r2_exists, upload_to_r2,
)

app = FastAPI(title="CV Builder API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.on_event("startup")
def startup():
    init_db()


# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    chat_history: list[dict] = []
    company: str = "GENERIC"

class ChatResponse(BaseModel):
    reply: str
    intent: str
    action_taken: str | None = None
    data_updated: bool = False
    needs_re_render: bool = False
    questions: list[str] = []
    evaluation: dict | None = None

class TailorRequest(BaseModel):
    job_description: str
    mode: str = "2page"
    company: str = "GENERIC"
    user_selections: dict | None = None

class RenderRequest(BaseModel):
    mode: str = "2page"
    company: str = "GENERIC"
    export_pdf: bool = False

class ProfileUpdateRequest(BaseModel):
    section: str    # "personal", "experience", "projects", etc.
    action: str     # "add", "edit", "remove", "toggle"
    item_id: str | None = None
    data: dict = {}


# ─────────────────────────────────────────────
# Profile helpers — R2 backed (no local storage)
# ─────────────────────────────────────────────

def _r2_key(user: User, filename: str) -> str:
    """Build R2 object key for a user file."""
    return f"users/{user.username}/{filename}"


def _load_profile(user: User) -> dict | None:
    return r2_read_json(_r2_key(user, "master_profile.json"))


def _save_profile(user: User, profile: dict):
    ok = r2_write_json(_r2_key(user, "master_profile.json"), profile)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save profile to R2")


def _load_config(user: User) -> dict:
    data = r2_read_json(_r2_key(user, "render_config.json"))
    return data or {}


def _save_config(user: User, config: dict):
    ok = r2_write_json(_r2_key(user, "render_config.json"), config)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save config to R2")


def _load_tailored(user: User, company: str) -> dict | None:
    return r2_read_json(_r2_key(user, f"tailored_{company.upper()}.json"))


def _save_tailored(user: User, company: str, data: dict):
    ok = r2_write_json(_r2_key(user, f"tailored_{company.upper()}.json"), data)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save tailored data to R2")


# ─────────────────────────────────────────────
# Upload endpoint (CV extraction)
# ─────────────────────────────────────────────

@app.post("/upload-cv")
async def upload_cv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Upload a CV file (PDF/DOCX/Image) and extract structured data."""
    file_bytes = await file.read()
    filename = file.filename or "upload.pdf"

    existing_profile = _load_profile(user)

    result = extractor.run_extraction(file_bytes, filename, existing_profile)

    if result.get("profile"):
        _save_profile(user, result["profile"])

    return {
        "success": result.get("profile") is not None,
        "missing_fields": result.get("missing_fields", []),
        "questions": result.get("questions", []),
        "profile_saved": result.get("profile") is not None,
    }


# ─────────────────────────────────────────────
# Chat endpoint (orchestrator)
# ─────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
):
    """Main chat endpoint — classifies intent and routes to the right agent."""
    message = req.message
    intent = orchestrator.classify_intent(message)
    profile = _load_profile(user)
    config = _load_config(user)

    reply = ""
    action_taken = None
    data_updated = False
    needs_re_render = False
    questions = []
    evaluation = None

    if intent == "GENERAL_CHAT":
        reply = orchestrator.handle_general_chat(message, req.chat_history, profile)

    elif intent == "EDIT_KNOWLEDGE_BASE":
        if not profile:
            reply = "You don't have a profile yet. Please upload your CV first or start by telling me about yourself."
        else:
            edit_result = orchestrator.handle_edit_request(message, profile, req.chat_history)
            if edit_result.get("needs_more_info"):
                reply = edit_result.get("question", "Could you provide more details?")
                questions = [reply]
            else:
                # Apply the edit to the profile
                action = edit_result.get("action", "")
                updates = edit_result.get("updates", {})
                target_id = edit_result.get("target_id")

                # Determine which section to modify
                section_map = {
                    "add_experience": "experience", "edit_experience": "experience", "remove_experience": "experience",
                    "add_project": "projects", "edit_project": "projects", "remove_project": "projects",
                    "add_certification": "certifications", "edit_certification": "certifications", "remove_certification": "certifications",
                    "add_extracurricular": "extracurricular", "edit_extracurricular": "extracurricular", "remove_extracurricular": "extracurricular",
                    "add_education": "education", "edit_education": "education", "remove_education": "education",
                    "add_skill": "skills_pool", "remove_skill": "skills_pool",
                    "edit_personal": "personal", "edit_links": "personal",
                }
                section = section_map.get(action, "")

                print(f"[EDIT] action={action}, section={section}, target_id={target_id}, updates={json.dumps(updates, default=str)[:500]}")

                if action.startswith("add_") and section and section != "personal":
                    items = profile.get(section, [])
                    if isinstance(updates, dict):
                        # Extracurricular can be strings or dicts
                        if section == "extracurricular":
                            text = updates.get("text", str(updates))
                            new_id = f"extra_{len(items)+1}"
                            items.append({"id": new_id, "text": text, "active": True})
                            print(f"[ADD] Added extracurricular: {text[:60]}")
                        else:
                            if not updates.get("id"):
                                updates["id"] = f"{section}_{len(items)+1}"
                            updates.setdefault("active", True)
                            items.append(updates)
                    elif isinstance(updates, str) and section == "extracurricular":
                        new_id = f"extra_{len(items)+1}"
                        items.append({"id": new_id, "text": updates, "active": True})
                        print(f"[ADD] Added extracurricular (str): {updates[:60]}")
                    elif isinstance(updates, list) and section == "extracurricular":
                        # LLM returned a list of items — add each one
                        for u in updates:
                            text = u.get("text", str(u)) if isinstance(u, dict) else str(u)
                            new_id = f"extra_{len(items)+1}"
                            items.append({"id": new_id, "text": text, "active": True})
                            print(f"[ADD] Added extracurricular from list: {text[:60]}")
                    profile[section] = items

                elif action.startswith("edit_") and section:
                    if section == "personal":
                        profile["personal"].update(updates)
                    else:
                        items = profile.get(section, [])
                        # Ensure all items have IDs
                        for idx, item in enumerate(items):
                            if not item.get("id"):
                                item["id"] = f"{section}_{idx+1}"

                        matched = False
                        # First try exact ID match
                        if target_id:
                            for item in items:
                                if item.get("id") == target_id:
                                    item.update(updates)
                                    matched = True
                                    break

                        # Fallback: fuzzy text match for extracurricular/cert items
                        if not matched and section in ("extracurricular", "certifications"):
                            search_text = (updates.get("text", "") or updates.get("original_text", "") or
                                          str(target_id) or "").lower()
                            # Try matching by keyword from the target_id or update text
                            for item in items:
                                item_text = (item.get("text", "") or item.get("name", "")).lower()
                                # Match if target_id appears in text, or if updates reference matches
                                if target_id and target_id.lower() in item_text:
                                    item.update(updates)
                                    matched = True
                                    break
                                # Match by keyword overlap
                                if search_text:
                                    search_words = set(search_text.split())
                                    item_words = set(item_text.split())
                                    if len(search_words & item_words) >= 2:
                                        item.update(updates)
                                        matched = True
                                        break

                        # Last resort for extracurricular: match by index hint in target_id
                        if not matched and section == "extracurricular" and target_id:
                            # Try extracting index from target_id like "extra_3" or "3"
                            import re as _re
                            idx_match = _re.search(r'(\d+)', str(target_id))
                            if idx_match:
                                idx = int(idx_match.group(1)) - 1
                                if 0 <= idx < len(items):
                                    items[idx].update(updates)
                                    matched = True

                        if not matched:
                            print(f"[WARN] Could not find item to edit: section={section}, target_id={target_id}")

                elif action.startswith("remove_") and section and target_id:
                    items = profile.get(section, [])
                    original_len = len(items)
                    # Try exact ID match first
                    remaining = [it for it in items if it.get("id") != target_id]
                    if len(remaining) == original_len and section == "extracurricular":
                        # Exact ID didn't match — try fuzzy text match
                        import re as _re
                        remaining = []
                        removed = False
                        for it in items:
                            item_text = (it.get("text", "") or "").lower()
                            if not removed and target_id.lower() in item_text:
                                removed = True
                                print(f"[REMOVE] Fuzzy matched and removed: {item_text[:60]}")
                                continue
                            remaining.append(it)
                        if not removed:
                            # Try index extraction from target_id
                            idx_match = _re.search(r'(\d+)', str(target_id))
                            if idx_match:
                                idx = int(idx_match.group(1)) - 1
                                if 0 <= idx < len(items):
                                    remaining = items[:idx] + items[idx+1:]
                                    print(f"[REMOVE] Removed by index {idx}")
                    else:
                        print(f"[REMOVE] Exact ID match removed item with id={target_id}")
                    profile[section] = remaining

                elif action == "add_skill" and updates:
                    pool = profile.get("skills_pool", [])
                    cat = updates.get("category", "Other")
                    skill_items = updates.get("items", [])
                    found = False
                    for s in pool:
                        if s.get("category", "").lower() == cat.lower():
                            existing = s.get("items", [])
                            if isinstance(existing, str):
                                existing = [x.strip() for x in existing.split(",")]
                            for si in skill_items:
                                if si not in existing:
                                    existing.append(si)
                            s["items"] = existing
                            found = True
                            break
                    if not found:
                        pool.append({"category": cat, "items": skill_items})
                    profile["skills_pool"] = pool

                elif action == "remove_skill" and updates:
                    pool = profile.get("skills_pool", [])
                    skill_to_remove = updates.get("skill", "")
                    for s in pool:
                        items = s.get("items", [])
                        if isinstance(items, str):
                            items = [x.strip() for x in items.split(",")]
                        items = [x for x in items if x.lower() != skill_to_remove.lower()]
                        s["items"] = items
                    profile["skills_pool"] = pool

                elif action == "update_skill" and updates:
                    pool = profile.get("skills_pool", [])
                    cat = updates.get("category", "Other")
                    skill_items = updates.get("items", [])
                    for s in pool:
                        if s.get("category", "").lower() == cat.lower():
                            s["items"] = skill_items
                            break
                    profile["skills_pool"] = pool

                elif action == "update_experience" and updates:
                    exp_id = updates.get("id")
                    new_data = updates.get("data", {})
                    for exp in profile.get("experience", []):
                        if exp.get("id") == exp_id:
                            exp.update(new_data)
                            break
                    profile["experience"] = profile.get("experience", [])

                elif action == "update_course_module" and updates:
                    edu_id = updates.get("id")
                    new_modules = updates.get("modules", [])
                    for edu in profile.get("education", []):
                        if edu.get("id") == edu_id:
                            edu["modules"] = new_modules
                            break
                    profile["education"] = profile.get("education", [])

                elif action == "edit_summary" and updates:
                    new_summary = updates.get("summary", "")
                    if new_summary:
                        profile["summary"] = new_summary

                elif action == "edit_title" and updates:
                    new_title = updates.get("title", "")
                    if new_title:
                        personal = profile.get("personal", {})
                        personal["title"] = new_title
                        profile["personal"] = personal

                reply = edit_result.get("response_message", "Updated your profile.")
                action_taken = action
                data_updated = True
                _save_profile(user, profile)

                # ── Also propagate edits to tailored data (if exists) ──
                active_company = req.company or "GENERIC"
                tailored = _load_tailored(user, active_company)
                if tailored:
                    # Mirror the same field updates into tailored data
                    if action == "edit_summary" and updates.get("summary"):
                        tailored["summary"] = updates["summary"]
                    elif action == "edit_title" and updates.get("title"):
                        tp = tailored.get("personal", {})
                        tp["title"] = updates["title"]
                        tailored["personal"] = tp
                    elif action == "edit_personal":
                        tp = tailored.get("personal", {})
                        tp.update(updates)
                        tailored["personal"] = tp
                    elif action in ("add_extracurricular", "edit_extracurricular", "remove_extracurricular"):
                        tailored["extracurricular"] = profile.get("extracurricular", [])
                    elif action in ("add_education", "edit_education", "remove_education"):
                        tailored["education"] = profile.get("education", [])
                    elif action in ("add_certification", "edit_certification", "remove_certification"):
                        tailored["certifications"] = profile.get("certifications", [])
                    elif action in ("add_skill", "remove_skill", "update_skill"):
                        tailored["skills_pool"] = profile.get("skills_pool", [])
                    _save_tailored(user, active_company, tailored)

    elif intent == "FORMAT_CHANGE":
        fmt_result = formatter.parse_format_request(message, config)
        updated_config = formatter.apply_config_updates(config, fmt_result.get("updates", {}))
        _save_config(user, updated_config)
        reply = fmt_result.get("explanation", "Formatting updated.")
        action_taken = "format_change"
        needs_re_render = fmt_result.get("requires_re_render", True)

    elif intent == "VIEW_DATA":
        if profile:
            exp_count = len(profile.get("experience", []))
            proj_count = len(profile.get("projects", []))
            cert_count = len(profile.get("certifications", []))
            skill_cats = len(profile.get("skills_pool", profile.get("skills", {}).get("full", [])))
            reply = (f"Your knowledge base has:\n"
                     f"• {exp_count} experience entries\n"
                     f"• {proj_count} projects\n"
                     f"• {cert_count} certifications\n"
                     f"• {skill_cats} skill categories\n\n"
                     f"Use the main panel to view and edit details.")
        else:
            reply = "No profile found. Upload your CV to get started."

    elif intent == "DOWNLOAD":
        reply = "Use the Download buttons in the preview panel to get your CV."
        action_taken = "download_prompt"

    else:
        reply = orchestrator.handle_general_chat(message, req.chat_history, profile)

    return ChatResponse(
        reply=reply,
        intent=intent,
        action_taken=action_taken,
        data_updated=data_updated,
        needs_re_render=needs_re_render,
        questions=questions,
        evaluation=evaluation,
    )


# ─────────────────────────────────────────────
# Tailor endpoint
# ─────────────────────────────────────────────

@app.post("/tailor")
async def tailor_cv(
    req: TailorRequest,
    user: User = Depends(get_current_user),
):
    """Run the full tailor → evaluate → iterate pipeline."""
    profile = _load_profile(user)
    if not profile:
        raise HTTPException(status_code=400, detail="No profile found. Upload CV first.")

    result = orchestrator.run_tailor_pipeline(
        profile, req.job_description, req.mode, req.user_selections
    )

    # Save tailored data
    _save_tailored(user, req.company, result["tailored_data"])

    return {
        "success": True,
        "verdict": result["final_verdict"],
        "iterations": result["iterations"],
        "evaluation": result["evaluation"],
        "needs_manual_review": result.get("needs_manual_review", False),
        "pass_threshold": result.get("pass_threshold", 95),
        "selection_rationale": result.get("selection_rationale", ""),
        "keyword_coverage": result.get("keyword_coverage", {}),
    }


# ─────────────────────────────────────────────
# Manual re-tailor endpoint (for manual iteration after auto-loop)
# ─────────────────────────────────────────────

class ManualRetailorRequest(BaseModel):
    company: str = "GENERIC"
    job_description: str
    feedback: str = ""
    mode: str = "2page"

@app.post("/re-tailor")
async def re_tailor_cv(
    req: ManualRetailorRequest,
    user: User = Depends(get_current_user),
):
    """Re-tailor current CV with manual feedback, then evaluate again."""
    from backend.agents import tailor as tailor_agent, evaluator as eval_agent

    profile = _load_profile(user)
    current = _load_tailored(user, req.company)
    if not profile or not current:
        raise HTTPException(status_code=400, detail="No profile or tailored data found.")

    re_result = tailor_agent.re_tailor_with_feedback(
        profile, req.job_description, current, req.feedback, req.mode
    )
    tailored_data = re_result.get("tailored_data", current)

    evaluation = eval_agent.evaluate(tailored_data, req.job_description, profile)
    _save_tailored(user, req.company, tailored_data)

    return {
        "success": True,
        "verdict": evaluation.get("verdict", "FAIL"),
        "evaluation": evaluation,
        "keyword_coverage": re_result.get("keyword_coverage", {}),
    }


# ─────────────────────────────────────────────
# Inject missing keywords into skills/experience
# ─────────────────────────────────────────────

class InjectKeywordsRequest(BaseModel):
    company: str = "GENERIC"
    keywords: list[str]
    job_description: str = ""

@app.post("/inject-keywords")
async def inject_keywords(
    req: InjectKeywordsRequest,
    user: User = Depends(get_current_user),
):
    """Smartly inject selected missing keywords into tailored CV's skills or experience."""
    from backend.config import get_openai_client, get_model_name

    profile = _load_profile(user)
    tailored = _load_tailored(user, req.company)
    if not tailored:
        raise HTTPException(status_code=400, detail="No tailored data found.")

    client = get_openai_client()
    prompt = f"""You have a tailored CV (JSON) and a list of missing keywords the user wants added.
Your job: insert each keyword into the most logical place — either:
1. Add it to the relevant skills category row
2. Weave it naturally into an existing experience/project bullet (without fabricating)

RULES:
- Only add keywords that are truthfully present in the master profile
- If a keyword maps to a skill, add to the matching skills category
- If a keyword maps to experience, subtly weave it into a relevant bullet
- Do NOT fabricate new bullets or experiences
- Return the full updated tailored_data JSON

## MASTER PROFILE (source of truth)
{json.dumps(profile, indent=2)}

## CURRENT TAILORED CV
{json.dumps(tailored, indent=2)}

## KEYWORDS TO INJECT
{json.dumps(req.keywords)}

## JOB DESCRIPTION (for context)
{req.job_description[:2000] if req.job_description else 'N/A'}

Return JSON with key "tailored_data" containing the updated CV data.
"""
    response = client.chat.completions.create(
        model=get_model_name(),
        messages=[
            {"role": "system", "content": "You are a CV keyword optimization agent. Never fabricate data."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
        max_tokens=8000,
    )
    result = json.loads(response.choices[0].message.content)
    updated = result.get("tailored_data", tailored)
    _save_tailored(user, req.company, updated)

    return {"success": True, "keywords_injected": req.keywords}


# ─────────────────────────────────────────────
# Render endpoint
# ─────────────────────────────────────────────

@app.post("/render")
async def render(
    req: RenderRequest,
    user: User = Depends(get_current_user),
):
    """Render tailored CV to .docx (and optionally .pdf)."""
    print("Render request received with:", req)
    tailored = _load_tailored(user, req.company)
    print("Loaded tailored data:", tailored)
    profile = _load_profile(user)
    print("Loaded profile data:", profile)
    data = tailored or profile
    if not data:
        print("No data to render.")
        raise HTTPException(status_code=400, detail="No data to render.")

    # Merge sections from profile that the tailor may not include
    # ALWAYS prefer profile data for these sections (user edits go to profile first)
    if profile and data is not profile:
        for key in ("extracurricular", "education", "certifications", "summary"):
            if profile.get(key):
                data[key] = profile[key]
                print(f"Merged {key} from profile (always-sync).")
        # Also sync personal fields (name, title, email, etc.)
        if profile.get("personal"):
            if not data.get("personal"):
                data["personal"] = {}
            for pkey in ("name", "title", "email", "phone", "location", "linkedin", "github"):
                if profile["personal"].get(pkey):
                    data["personal"][pkey] = profile["personal"][pkey]

    config = _load_config(user)
    print("Loaded render config:", config)

    # Render to a temp directory, then upload to R2
    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory() as tmp_dir:
        try:
            result = render_cv(data, mode=req.mode, company=req.company,
                               config=config, output_dir=tmp_dir,
                               export_pdf=req.export_pdf)
            print("Render result:", result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Render failed: {str(e)}")

        # Upload rendered files to R2
        import os as _os
        docx_filename = _os.path.basename(result["docx"]) if result.get("docx") else None
        pdf_filename = _os.path.basename(result["pdf"]) if result.get("pdf") else None

        if docx_filename and result.get("docx") and _os.path.exists(result["docx"]):
            with open(result["docx"], "rb") as f:
                r2_write_bytes(
                    _r2_key(user, f"output/{docx_filename}"),
                    f.read(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            print(f"Uploaded {docx_filename} to R2")

        if pdf_filename and result.get("pdf") and _os.path.exists(result["pdf"]):
            with open(result["pdf"], "rb") as f:
                r2_write_bytes(
                    _r2_key(user, f"output/{pdf_filename}"),
                    f.read(),
                    "application/pdf"
                )
            print(f"Uploaded {pdf_filename} to R2")

    return {
        "docx_path": result.get("docx"),
        "pdf_path": result.get("pdf"),
        "docx_filename": docx_filename,
        "pdf_filename": pdf_filename,
    }


# ─────────────────────────────────────────────
# File download endpoints — served from R2
# ─────────────────────────────────────────────

@app.get("/download/{filename}")
async def download_file(
    filename: str,
    user: User = Depends(get_current_user),
):
    """Download a generated file from R2."""
    r2_key = _r2_key(user, f"output/{filename}")
    file_bytes = r2_read_bytes(r2_key)
    if file_bytes is None:
        raise HTTPException(status_code=404, detail="File not found in R2")

    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if filename.endswith(".pdf"):
        media_type = "application/pdf"

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────
# Profile CRUD endpoints (for the main UI panel)
# ─────────────────────────────────────────────

@app.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    """Get user's knowledge base profile."""
    profile = _load_profile(user)
    config = _load_config(user)
    return {
        "profile": profile,
        "render_config": config,
        "has_profile": profile is not None,
    }


@app.put("/profile")
async def update_profile(
    profile: dict,
    user: User = Depends(get_current_user),
):
    """Update entire profile (from UI form saves)."""
    _save_profile(user, profile)
    return {"success": True}


@app.put("/profile/section/{section}")
async def update_section(
    section: str,
    data: dict,
    user: User = Depends(get_current_user),
):
    """Update a specific profile section."""
    profile = _load_profile(user) or {}
    profile[section] = data.get("items", data)
    _save_profile(user, profile)
    return {"success": True}


@app.put("/render-config")
async def update_render_config(
    config: dict,
    user: User = Depends(get_current_user),
):
    """Update render config."""
    current = _load_config(user)
    merged = formatter.apply_config_updates(current, config)
    _save_config(user, merged)
    return {"success": True, "config": merged}


# ─────────────────────────────────────────────
# Image reading endpoint (OCR / reference)
# ─────────────────────────────────────────────

@app.post("/read-image")
async def read_image(
    file: UploadFile = File(...),
    context: str = Form(default="Extract all text from this image."),
    user: User = Depends(get_current_user),
):
    """Read text from an image using GPT-4o Vision."""
    file_bytes = await file.read()
    text = extractor.extract_text_from_image(file_bytes, file.content_type or "image/png")
    return {"text": text}
