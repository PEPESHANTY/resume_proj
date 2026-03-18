"""
FastAPI main application — ties auth, agents, renderer together.
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.auth.models import User, init_db, get_db
from backend.auth.routes import router as auth_router, get_current_user
from backend.agents import orchestrator, extractor, formatter
from backend.renderer.build_cv_dynamic import render_cv

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
# Profile helpers
# ─────────────────────────────────────────────

def _load_profile(user: User) -> dict | None:
    p = user.master_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None

def _save_profile(user: User, profile: dict):
    user.master_path().write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")

def _load_config(user: User) -> dict:
    p = user.render_config_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

def _save_config(user: User, config: dict):
    user.render_config_path().write_text(json.dumps(config, indent=2), encoding="utf-8")

def _load_tailored(user: User, company: str) -> dict | None:
    p = user.storage_dir() / f"tailored_{company.upper()}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None

def _save_tailored(user: User, company: str, data: dict):
    p = user.storage_dir() / f"tailored_{company.upper()}.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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

                print(f"[EDIT] action={action}, section={section}, target_id={target_id}, updates={updates}")

                if action.startswith("add_") and section and section != "personal":
                    items = profile.get(section, [])
                    if isinstance(updates, dict):
                        # Extracurricular can be strings or dicts
                        if section == "extracurricular":
                            text = updates.get("text", str(updates))
                            new_id = f"extra_{len(items)+1}"
                            items.append({"id": new_id, "text": text, "active": True})
                        else:
                            if not updates.get("id"):
                                updates["id"] = f"{section}_{len(items)+1}"
                            updates.setdefault("active", True)
                            items.append(updates)
                    elif isinstance(updates, str) and section == "extracurricular":
                        new_id = f"extra_{len(items)+1}"
                        items.append({"id": new_id, "text": updates, "active": True})
                    profile[section] = items

                elif action.startswith("edit_") and section and target_id:
                    if section == "personal":
                        profile["personal"].update(updates)
                    else:
                        items = profile.get(section, [])
                        for item in items:
                            if item.get("id") == target_id:
                                item.update(updates)
                                break

                elif action.startswith("remove_") and section and target_id:
                    items = profile.get(section, [])
                    profile[section] = [it for it in items if it.get("id") != target_id]

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

                reply = edit_result.get("response_message", "Updated your profile.")
                action_taken = action
                data_updated = True
                _save_profile(user, profile)

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
    tailored = _load_tailored(user, req.company)
    profile = _load_profile(user)
    data = tailored or profile
    if not data:
        raise HTTPException(status_code=400, detail="No data to render.")

    # Merge sections from profile that the tailor may not include
    if profile and data is not profile:
        for key in ("extracurricular", "education", "certifications"):
            if not data.get(key) and profile.get(key):
                data[key] = profile[key]

    config = _load_config(user)
    output_dir = str(user.output_dir())

    result = render_cv(data, mode=req.mode, company=req.company,
                       config=config, output_dir=output_dir,
                       export_pdf=req.export_pdf)

    return {
        "docx_path": result["docx"],
        "pdf_path": result.get("pdf"),
    }


# ─────────────────────────────────────────────
# File download endpoints
# ─────────────────────────────────────────────

@app.get("/download/{filename}")
async def download_file(
    filename: str,
    user: User = Depends(get_current_user),
):
    """Download a generated file."""
    file_path = user.output_dir() / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if filename.endswith(".pdf"):
        media_type = "application/pdf"

    return FileResponse(str(file_path), media_type=media_type, filename=filename)


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
