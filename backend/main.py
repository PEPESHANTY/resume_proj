"""
FastAPI main application — ties auth, agents, renderer together.
"""
import json
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from backend.auth.models import User, init_db, get_db
from backend.auth.routes import router as auth_router, get_current_user
from backend.agents import orchestrator, extractor, formatter
from backend.renderer.build_cv_dynamic import render_cv
from backend.utils import (
    r2_enabled, r2_read_json, r2_write_json,
    r2_read_bytes, r2_write_bytes, r2_exists, r2_list_keys, upload_to_r2,
)
from backend.config import _request_api_key, WHITELISTED_EMAILS

app = FastAPI(title="CV Builder API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


# ─────────────────────────────────────────────
# LLM access gate
# ─────────────────────────────────────────────

def _require_llm_key(user: User, provided_key: str | None) -> str | None:
    """Return the key to inject, or raise 402 if no key available.

    Whitelisted emails use the server env key (returns None = use default).
    All other users must supply x-openai-api-key header.
    """
    if user.email in WHITELISTED_EMAILS:
        return None  # use server env key
    if not provided_key:
        raise HTTPException(
            status_code=402,
            detail=(
                "An OpenAI API key is required to use AI features. "
                "Please enter your key in Settings → API Key."
            ),
        )
    return provided_key


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


_MONTH_ORDER = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

def _parse_start_date(date_range: str | None) -> tuple[int, int]:
    """Parse 'Month YYYY – …' or 'Month YYYY – Present' into (year, month) for sorting."""
    if not date_range:
        return (0, 0)
    # Take the first part before the dash/em-dash
    import re
    part = re.split(r'[-\u2013\u2014]', str(date_range))[0].strip()
    tokens = part.split()
    year, month = 0, 0
    for tok in tokens:
        if tok.isdigit() and len(tok) == 4:
            year = int(tok)
        else:
            month = _MONTH_ORDER.get(tok.lower(), 0)
    return (year, month)


def _sort_experience(items: list) -> list:
    """Return experience list sorted newest-first by start date."""
    return sorted(items, key=lambda e: _parse_start_date(e.get("date_range")), reverse=True)


def _list_tailored_companies(user: User) -> list[str]:
    """Return list of company codes that have tailored JSON files in R2."""
    prefix = f"users/{user.username}/tailored_"
    keys = r2_list_keys(prefix)
    companies = []
    for key in keys:
        filename = key.split("/")[-1]  # e.g. "tailored_AA.json"
        if filename.startswith("tailored_") and filename.endswith(".json"):
            company = filename[len("tailored_"):-len(".json")]
            companies.append(company)
    return companies


def _propagate_to_all_tailored(user: User, profile: dict, action: str, updates: dict):
    """Propagate a profile edit to ALL existing tailored JSONs for the user."""
    companies = _list_tailored_companies(user)
    print(f"[PROPAGATE] action={action}, updating {len(companies)} tailored file(s): {companies}")
    for company in companies:
        tailored = _load_tailored(user, company)
        if not tailored:
            continue
        if action == "edit_summary" and updates.get("summary"):
            tailored["summary"] = updates["summary"]
        elif action == "edit_title" and updates.get("title"):
            tp = tailored.get("personal", {})
            tp["title"] = updates["title"]
            tailored["personal"] = tp
        elif action in ("edit_personal", "edit_links"):
            tp = tailored.get("personal", {})
            tp.update(updates)
            tailored["personal"] = tp
        elif action in ("add_experience", "edit_experience", "remove_experience", "update_experience", "reorder_experience"):
            tailored["experience"] = profile.get("experience", [])
        elif action in ("add_project", "edit_project", "remove_project", "reorder_projects"):
            tailored["projects"] = profile.get("projects", [])
        elif action in ("add_extracurricular", "edit_extracurricular", "remove_extracurricular"):
            tailored["extracurricular"] = profile.get("extracurricular", [])
        elif action in ("add_education", "edit_education", "remove_education", "update_course_module"):
            tailored["education"] = profile.get("education", [])
        elif action in ("add_certification", "edit_certification", "remove_certification"):
            tailored["certifications"] = profile.get("certifications", [])
        elif action in ("add_skill", "remove_skill", "update_skill"):
            tailored["skills_pool"] = profile.get("skills_pool", [])
        r2_write_json(_r2_key(user, f"tailored_{company}.json"), tailored)
        print(f"[PROPAGATE] Updated tailored_{company}.json")


# ─────────────────────────────────────────────
# Upload endpoint (CV extraction)
# ─────────────────────────────────────────────

@app.post("/upload-cv")
async def upload_cv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    x_openai_api_key: str | None = Header(default=None),
):
    """Upload a CV file (PDF/DOCX/Image) and extract structured data."""
    key = _require_llm_key(user, x_openai_api_key)
    file_bytes = await file.read()
    filename = file.filename or "upload.pdf"

    existing_profile = _load_profile(user)

    token = _request_api_key.set(key) if key else None
    try:
        result = extractor.run_extraction(file_bytes, filename, existing_profile)
    finally:
        if token is not None:
            _request_api_key.reset(token)

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
    x_openai_api_key: str | None = Header(default=None),
):
    """Main chat endpoint — classifies intent and routes to the right agent."""
    # Gate LLM access — sets context var so all agents use the right key
    key = _require_llm_key(user, x_openai_api_key)
    _cv_token = _request_api_key.set(key) if key else None
    try:
        return await _chat_inner(req, user)
    finally:
        if _cv_token is not None:
            _request_api_key.reset(_cv_token)


async def _chat_inner(req: ChatRequest, user: User):
    message = req.message
    intent = orchestrator.classify_intent(message)
    profile = _load_profile(user)
    config = _load_config(user)

    # If the last bot message was a clarifying question about an edit,
    # treat this reply as a continuation of EDIT_KNOWLEDGE_BASE regardless of classification.
    if intent == "GENERAL_CHAT" and req.chat_history:
        last_bot_msgs = [m for m in req.chat_history if m.get("role") == "assistant"]
        if last_bot_msgs:
            last_bot_text = last_bot_msgs[-1].get("content", "")
            edit_question_hints = [
                "location", "date", "company", "role", "title", "description",
                "tell me more", "could you provide", "can you share", "what is the",
                "which", "when did", "please provide", "could you clarify",
            ]
            if "?" in last_bot_text and any(h in last_bot_text.lower() for h in edit_question_hints):
                intent = "EDIT_KNOWLEDGE_BASE"

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
                    "reorder_experience": "experience",
                    "add_project": "projects", "edit_project": "projects", "remove_project": "projects",
                    "reorder_projects": "projects",
                    "add_certification": "certifications", "edit_certification": "certifications", "remove_certification": "certifications",
                    "add_extracurricular": "extracurricular", "edit_extracurricular": "extracurricular", "remove_extracurricular": "extracurricular",
                    "add_education": "education", "edit_education": "education", "remove_education": "education",
                    "add_skill": "skills_pool", "remove_skill": "skills_pool", "update_skill": "skills_pool",
                    "edit_personal": "personal", "edit_links": "personal",
                }
                section = section_map.get(action, "")

                print(f"[EDIT] action={action}, section={section}, target_id={target_id}, updates={json.dumps(updates, default=str)[:500]}")

                if action in ("reorder_experience", "reorder_projects") and section:
                    desired_order = updates.get("order", [])
                    if desired_order:
                        items = profile.get(section, [])
                        id_to_item = {it.get("id"): it for it in items}
                        reordered = [id_to_item[eid] for eid in desired_order if eid in id_to_item]
                        remaining = [it for it in items if it.get("id") not in set(desired_order)]
                        profile[section] = reordered + remaining
                        # Mark as manually ordered — render will respect this instead of date-sorting
                        order_key = "experience_manual_order" if section == "experience" else "projects_manual_order"
                        profile[order_key] = [e.get("id") for e in profile[section]]
                        print(f"[REORDER] {section}: {profile[order_key]}")

                elif action.startswith("add_") and section and section != "personal":
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
                    old_cat = updates.get("old_category", "")  # for rename
                    skill_items = updates.get("items", [])
                    match_cat = old_cat if old_cat else cat
                    found = False
                    for s in pool:
                        if s.get("category", "").lower() == match_cat.lower():
                            s["category"] = cat  # rename if old_category was provided
                            if skill_items:
                                s["items"] = skill_items
                            found = True
                            break
                    if not found:
                        pool.append({"category": cat, "items": skill_items})
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

                # ── Propagate edits to ALL existing tailored JSONs ──
                _propagate_to_all_tailored(user, profile, action, updates)

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
    x_openai_api_key: str | None = Header(default=None),
):
    """Run the full tailor → evaluate → iterate pipeline."""
    key = _require_llm_key(user, x_openai_api_key)
    profile = _load_profile(user)
    if not profile:
        raise HTTPException(status_code=400, detail="No profile found. Upload CV first.")

    token = _request_api_key.set(key) if key else None
    try:
        result = orchestrator.run_tailor_pipeline(
            profile, req.job_description, req.mode, req.user_selections
        )
    finally:
        if token is not None:
            _request_api_key.reset(token)

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
    x_openai_api_key: str | None = Header(default=None),
):
    """Re-tailor current CV with manual feedback, then evaluate again."""
    from backend.agents import tailor as tailor_agent, evaluator as eval_agent

    key = _require_llm_key(user, x_openai_api_key)
    profile = _load_profile(user)
    current = _load_tailored(user, req.company)
    if not profile or not current:
        raise HTTPException(status_code=400, detail="No profile or tailored data found.")

    token = _request_api_key.set(key) if key else None
    try:
        re_result = tailor_agent.re_tailor_with_feedback(
            profile, req.job_description, current, req.feedback, req.mode
        )
        tailored_data = re_result.get("tailored_data", current)
        evaluation = eval_agent.evaluate(tailored_data, req.job_description, profile)
    finally:
        if token is not None:
            _request_api_key.reset(token)
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
    x_openai_api_key: str | None = Header(default=None),
):
    """Smartly inject selected missing keywords into tailored CV's skills or experience."""
    from backend.config import get_openai_client, get_model_name

    key = _require_llm_key(user, x_openai_api_key)
    profile = _load_profile(user)
    tailored = _load_tailored(user, req.company)
    if not tailored:
        raise HTTPException(status_code=400, detail="No tailored data found.")

    prompt = (
        "You have a tailored CV (JSON) and a list of missing keywords the user wants added.\n"
        "Your job: insert each keyword into the most logical place — either:\n"
        "1. Add it to the relevant skills category row\n"
        "2. Weave it naturally into an existing experience/project bullet (without fabricating)\n\n"
        "RULES:\n"
        "- Only add keywords that are truthfully present in the master profile\n"
        "- If a keyword maps to a skill, add to the matching skills category\n"
        "- If a keyword maps to experience, subtly weave it into a relevant bullet\n"
        "- Do NOT fabricate new bullets or experiences\n"
        "- Return the full updated tailored_data JSON\n\n"
        f"## MASTER PROFILE (source of truth)\n{json.dumps(profile, indent=2)}\n\n"
        f"## CURRENT TAILORED CV\n{json.dumps(tailored, indent=2)}\n\n"
        f"## KEYWORDS TO INJECT\n{json.dumps(req.keywords)}\n\n"
        f"## JOB DESCRIPTION (for context)\n{req.job_description[:2000] if req.job_description else 'N/A'}\n\n"
        "Return JSON with key \"tailored_data\" containing the updated CV data."
    )
    token = _request_api_key.set(key) if key else None
    try:
        response = get_openai_client().chat.completions.create(
            model=get_model_name(),
            messages=[
                {"role": "system", "content": "You are a CV keyword optimization agent. Never fabricate data."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            max_tokens=8000,
        )
    finally:
        if token is not None:
            _request_api_key.reset(token)
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

        # Sync experience/projects from profile — profile is always source of truth for
        # which entries exist, in what order, and with correct IDs.
        # If tailored has entries with no IDs (stale data), fall back to profile fully.
        for section in ("experience", "projects"):
            profile_items = profile.get(section, [])
            if not profile_items:
                continue
            tailored_items = data.get(section, [])
            tailored_ids = {e.get("id") for e in tailored_items if e.get("id")}

            # If tailored has no IDs at all → stale, replace entirely with profile
            if not tailored_ids:
                data[section] = profile_items
                print(f"Replaced stale {section} from profile (no IDs in tailored).")
            else:
                # Append any profile entries that are genuinely missing from tailored
                new_items = [e for e in profile_items if e.get("id") not in tailored_ids]
                if new_items:
                    data[section] = tailored_items + new_items
                    print(f"Merged {len(new_items)} new {section} entries from profile.")
                # Remove tailored entries that no longer exist in profile
                profile_ids = {e.get("id") for e in profile_items if e.get("id")}
                data[section] = [e for e in data[section] if not e.get("id") or e.get("id") in profile_ids]

    # Apply ordering: respect manual order if set, otherwise sort by date (newest first)
    for section, order_key in (("experience", "experience_manual_order"), ("projects", "projects_manual_order")):
        if not data.get(section):
            continue
        manual_order = profile.get(order_key) if profile else None
        if manual_order:
            # Respect manual order stored in profile
            id_to_item = {e.get("id"): e for e in data[section]}
            ordered = [id_to_item[eid] for eid in manual_order if eid in id_to_item]
            remaining = [e for e in data[section] if e.get("id") not in set(manual_order)]
            data[section] = ordered + remaining
        else:
            # Default: sort newest first by date
            if section == "experience":
                data[section] = _sort_experience(data[section])

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


@app.get("/preview/{filename}")
async def preview_file(
    filename: str,
    user: User = Depends(get_current_user),
):
    """Return an HTML preview of a .docx file using mammoth."""
    if not filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Preview only supported for .docx files")

    r2_key = _r2_key(user, f"output/{filename}")
    file_bytes = r2_read_bytes(r2_key)
    if file_bytes is None:
        raise HTTPException(status_code=404, detail="File not found in R2")

    try:
        import mammoth
        import io
        result = mammoth.convert_to_html(io.BytesIO(file_bytes))
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body {{ font-family: Calibri, Arial, sans-serif; font-size: 10pt;
          margin: 0.5in 0.4in; line-height: 1.3; }}
  p {{ margin: 2px 0; }}
  ul {{ margin: 2px 0; padding-left: 1.2em; }}
  li {{ margin: 1px 0; }}
  strong {{ font-weight: bold; }}
</style></head><body>{result.value}</body></html>"""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {e}")

    return Response(content=html, media_type="text/html")


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
# Saved CVs listing endpoint
# ─────────────────────────────────────────────

@app.get("/saved-cvs")
async def list_saved_cvs(user: User = Depends(get_current_user)):
    """List all previously rendered CVs for the user, grouped by company."""
    import re as _re
    prefix = _r2_key(user, "output/")
    all_keys = r2_list_keys(prefix)

    cv_map = {}
    for key in all_keys:
        filename = key.split("/")[-1]
        m = _re.search(r'_CV_(.+?)_(1PAGE|2PAGE)\.(docx|pdf)$', filename, _re.IGNORECASE)
        if not m:
            continue
        company = m.group(1)
        mode = m.group(2).lower()
        ext = m.group(3).lower()
        slot = f"{company}_{mode}"
        if slot not in cv_map:
            cv_map[slot] = {"company": company, "mode": mode,
                            "docx_filename": None, "pdf_filename": None}
        if ext == "docx":
            cv_map[slot]["docx_filename"] = filename
        else:
            cv_map[slot]["pdf_filename"] = filename

    items = sorted(cv_map.values(), key=lambda x: x["company"])
    return {"saved_cvs": items}


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
