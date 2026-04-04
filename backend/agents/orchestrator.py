"""
Orchestrator Agent — the brain of the system.

Classifies every user message and routes to the correct sub-agent(s).
Manages the tailor → evaluate → re-tailor loop.
Handles chat history for context.
"""
import json
from pathlib import Path
from backend.config import MAX_EVAL_LOOPS, EVAL_PASS_THRESHOLD, get_openai_client, get_model_name
from backend.agents import extractor, tailor, evaluator, formatter

# ── Intent classification ──────────────────────────

INTENTS = [
    "UPLOAD_CV",              # user wants to upload a new CV
    "PASTE_CV_TEXT",          # user pastes raw CV text
    "EDIT_KNOWLEDGE_BASE",   # add/edit/remove experience, project, cert, skill, link
    "TAILOR_CV",             # paste JD → generate tailored CV
    "FORMAT_CHANGE",         # change font, margins, section order, etc.
    "SELECTION_CHANGE",      # include/exclude specific items from active CV
    "VIEW_DATA",             # show knowledge base, current CV, etc.
    "DOWNLOAD",              # download docx/pdf
    "GENERAL_CHAT",          # greeting, question, help
    "IMAGE_REFERENCE",       # user uploaded an image for reference/OCR
]


def classify_intent(message: str, has_file: bool = False, file_type: str = "") -> str:
    """Classify user message into an intent category."""

    # Quick heuristic checks for common cases
    if has_file:
        if file_type in ("pdf", "docx", "doc"):
            return "UPLOAD_CV"
        if file_type in ("png", "jpg", "jpeg", "webp", "gif", "bmp"):
            return "IMAGE_REFERENCE"

    msg_lower = message.lower()

    # Keyword-based fast path (avoids LLM call for obvious intents)
    if any(k in msg_lower for k in ["download", "export", "get my cv", "give me the file"]):
        return "DOWNLOAD"
    if any(k in msg_lower for k in ["job description", "jd:", "jd :", "tailor", "here's a jd", "here is the jd", "position:", "role:"]):
        return "TAILOR_CV"
    if any(k in msg_lower for k in ["font", "margin", "section order", "remove section", "hide section", "page size", "make it"]):
        return "FORMAT_CHANGE"
    if any(k in msg_lower for k in [
        # ── add ──
        "add project", "add experience", "add cert", "add skill", "add education",
        "add extracurricular", "add activity", "add link", "add bullet", "add point",
        "new experience", "new project", "new job", "new role", "new position",
        "i worked at", "i joined", "i started working", "i have a new",
        # ── remove / delete ──
        "remove", "delete", "get rid of", "drop",
        # ── edit / update / change ──
        "edit my", "update my", "change my", "correct my", "fix my",
        "edit the", "update the", "change the", "rename", "replace",
        "set my", "set the",
        # ── reorder / move ──
        "move", "reorder", "put", "bring", "on top", "at top",
        "swap", "rearrange", "shift", "make it first", "make it last",
        # ── content: summary / title ──
        "summary", "headline", "title", "objective",
        "make my summary", "rewrite my summary", "improve my summary",
        "shorten my summary", "expand my summary",
        # ── content: bullets / descriptions ──
        "bullet", "point", "rewrite", "improve", "strengthen", "make it more",
        "make it sound", "make it better", "polish", "rephrase",
        "add a line", "remove a line", "change the wording",
        # ── dates / periods ──
        "date", "period", "start date", "end date", "from", "to present",
        "currently working", "still working", "ended", "left",
        # ── contact / personal ──
        "linkedin", "github", "phone", "email", "address", "location",
        "contact", "website", "portfolio", "url", "link",
        # ── skills ──
        "skill", "technology", "tech stack", "language", "framework", "tool",
        "category", "add to skills", "remove from skills",
        # ── hide / show / toggle ──
        "hide", "show", "activate", "deactivate", "include", "exclude",
        "toggle", "mark as active", "mark as inactive",
        # ── education / certs ──
        "extracurricular", "certification", "certificate", "degree", "module",
        "course", "grade", "cgpa", "gpa", "gpa",
        # ── misc ──
        "make eaton", "make ceadar", "make cognizant", "make ltimindtree",
    ]):
        return "EDIT_KNOWLEDGE_BASE"
    if any(k in msg_lower for k in ["show my", "view my", "what do i have", "my profile", "my data", "list my"]):
        return "VIEW_DATA"
    if any(k in msg_lower for k in ["select", "deselect"]):
        return "SELECTION_CHANGE"

    # For ambiguous cases, use LLM
    response = get_openai_client().chat.completions.create(
        model=get_model_name(),
        messages=[
            {"role": "system", "content": f"Classify the user message into exactly one of these intents: {', '.join(INTENTS)}. Reply with ONLY the intent name, nothing else."},
            {"role": "user", "content": message},
        ],
        temperature=0,
        max_tokens=30,
    )
    intent = response.choices[0].message.content.strip().upper()
    return intent if intent in INTENTS else "GENERAL_CHAT"


def handle_general_chat(message: str, chat_history: list[dict], profile: dict | None = None) -> str:
    """Handle general conversation / help questions with profile context."""
    system = """You are a friendly CV assistant. You help users build ATS-optimized resumes.
You can help them:
- Upload their CV (PDF, DOCX, or image)
- Edit their knowledge base (add/remove experience, projects, certifications, skills, links)
- Paste a job description to generate a tailored CV
- Change formatting (font, margins, section order)
- Preview and download their CV

Keep responses concise and helpful. Guide them to the right action."""

    if profile:
        # Include a summary of the user's profile so the assistant has context
        personal = profile.get("personal", {})
        exp_count = len(profile.get("experience", []))
        proj_count = len(profile.get("projects", []))
        cert_count = len(profile.get("certifications", []))
        edu_count = len(profile.get("education", []))
        extra = profile.get("extracurricular", [])
        extra_count = len(extra) if isinstance(extra, list) else 0

        profile_summary = f"""\n\nUSER PROFILE CONTEXT (their knowledge base):
- Name: {personal.get('name', 'Unknown')}
- Title: {personal.get('title', 'N/A')}
- {exp_count} experience entries, {proj_count} projects, {cert_count} certifications, {edu_count} education entries, {extra_count} extracurricular items

Experience: {', '.join(e.get('company', '') + ' (' + e.get('role', '') + ')' for e in profile.get('experience', []))}
Projects: {', '.join(p.get('title', '') for p in profile.get('projects', []))}
Extracurricular: {', '.join(e if isinstance(e, str) else e.get('text', '') for e in extra) if extra else 'None listed'}

Full profile JSON is available to the system. Use this context to answer user questions about their CV data."""
        system += profile_summary

    messages = [{"role": "system", "content": system}]
    messages.extend(chat_history[-10:])  # last 10 messages for context
    messages.append({"role": "user", "content": message})

    response = get_openai_client().chat.completions.create(
        model=get_model_name(),
        messages=messages,
        temperature=0.7,
        max_tokens=500,
    )
    return response.choices[0].message.content


def handle_edit_request(message: str, master_profile: dict, chat_history: list[dict]) -> dict:
    """
    Handle knowledge base edit requests via chat.
    Returns the updated profile + a response message.
    """
    system = """You are a **senior CV copywriter and ATS optimization expert**. The user wants to modify their knowledge base profile.
Your edits must be polished, professional, and ATS-friendly.

## ⚠️ GOLDEN RULE — USER INSTRUCTION ALWAYS WINS:
The writing quality rules below are DEFAULTS. If the user explicitly asks for a different length, tone, or style
(e.g. "make it shorter", "one liner", "make it longer", "expand it", "keep it brief"),
OBEY THE USER'S REQUEST and override the defaults. The user's instruction is the highest priority.

## WRITING QUALITY RULES (defaults — override if user says otherwise):

### Professional Summary ("edit_summary"):
- DEFAULT: Write 2-3 sentences (40-60 words).
- Open with role identity + years/level: e.g. "Generative AI Engineer with hands-on experience in…"
- Include 3-5 hard skills / technologies mentioned in the existing profile.
- End with an impact phrase: "…delivering scalable, production-ready solutions" / "…driving data-driven decision-making."
- Match the tone and depth of the existing summary — if it's detailed, keep it detailed.
- When user says "just add X" to the summary, integrate X naturally into the EXISTING summary text. Do NOT rewrite or shorten it.
- If user explicitly asks for shorter/longer, adjust length accordingly while keeping it professional.

### Title / Headline ("edit_title"):
- Format: "Primary Role | Secondary Strength | Key Tech/Domain"
- Example: "Generative AI Engineer | AI-Powered Backend Specialist"

### Experience Bullets:
- Start with a strong action verb (Designed, Built, Optimized, Deployed, Automated…).
- Follow XYZ formula: "Accomplished [X] by doing [Y], resulting in [Z]."
- Include specific technologies, tools, and quantified impact where possible.
- Professional, concise, 1-2 lines each.

### Project Bullets:
- Lead with what was built and the tech stack used.
- Highlight the outcome or capability delivered.

### Extracurricular:
- DEFAULT: Write clear, descriptive entries: e.g. "Volunteered in community gardening and plantation drives with Simon Community"
- NOT just a single word like "Gardening" — provide some context.
- BUT if the user says "one liner", "short", or "brief", write a concise single line (8-15 words max).
- If the user says "longer" or "expand", write 2-3 detailed sentences.

### Skills:
- Group by category. Use industry-standard names (e.g., "LangChain" not "langchain").

## MINIMAL EDIT PRINCIPLE:
- When the user says "just add X" or "add one word of X", make the SMALLEST edit needed — integrate the word/phrase into the existing text. Do NOT rewrite the entire section.
- Preserve the existing content, length, and structure. Only modify what the user explicitly asked for.

## COMPLETE ACTION REFERENCE:

### ── EXPERIENCE ──
| User says | action | updates shape |
|---|---|---|
| "add experience at X as Y from Z" | add_experience | {company, role, location, date_range, bullets:[], active:true} |
| "edit CeADAR dates / role / location / bullets" | edit_experience | {target_id, date_range / role / location / bullets} |
| "add a bullet to Eaton experience" | edit_experience | {target_id, bullets: [...existing + new]} |
| "remove bullet 2 from CeADAR" | edit_experience | {target_id, bullets: [...existing minus removed]} |
| "rewrite CeADAR bullets to be more ATS-friendly" | edit_experience | {target_id, bullets: [...rewritten]} |
| "hide / deactivate Cognizant experience" | edit_experience | {target_id, active: false} |
| "show / activate Cognizant experience" | edit_experience | {target_id, active: true} |
| "remove / delete experience" | remove_experience | target_id only |
| "move Eaton to top / reorder experience" | reorder_experience | {order: ["id1","id2",...]} — full ordered id list |
| "mark Eaton as current / present" | edit_experience | {target_id, date_range: "Month YYYY – Present"} |

### ── PROJECTS ──
| User says | action | updates shape |
|---|---|---|
| "add project X built with Y" | add_project | {title, description, tech_stack:[], bullets:[], active:true} |
| "edit RiceAI description / tech stack / bullets" | edit_project | {target_id, description / tech_stack / bullets} |
| "add a bullet to ScholarGenie" | edit_project | {target_id, bullets: [...existing + new]} |
| "remove bullet 1 from Face Verification" | edit_project | {target_id, bullets: [...remaining]} |
| "rewrite RiceAI bullets" | edit_project | {target_id, bullets: [...rewritten]} |
| "hide / deactivate a project" | edit_project | {target_id, active: false} |
| "show / activate a project" | edit_project | {target_id, active: true} |
| "remove project" | remove_project | target_id only |
| "move RiceAI to top / reorder projects" | reorder_projects | {order: ["id1","id2",...]} |

### ── SUMMARY & TITLE ──
| User says | action | updates shape |
|---|---|---|
| "update / rewrite / improve my summary" | edit_summary | {summary: "full text"} |
| "make summary shorter / longer / ATS-focused" | edit_summary | {summary: "adjusted text"} |
| "add Azure to my summary" | edit_summary | {summary: "existing + Azure woven in"} |
| "change title / headline" | edit_title | {title: "Role | Role | Tech"} |

### ── SKILLS ──
| User says | action | updates shape |
|---|---|---|
| "add LangGraph to ML & AI skills" | add_skill | {category: "ML & AI", items: ["LangGraph"]} |
| "remove Kafka from Data Engineering" | remove_skill | {skill: "Kafka"} |
| "rename 'Tools' category to 'Frameworks & Tools'" | update_skill | {old_category: "Tools", category: "Frameworks & Tools", items: [...existing]} |
| "replace entire Languages category with [...]" | update_skill | {category: "Languages", items: [...]} |
| "move Python to first in Languages" | update_skill | {category: "Languages", items: ["Python", ...rest]} |

### ── CERTIFICATIONS ──
| User says | action | updates shape |
|---|---|---|
| "add Azure AI-900 cert, Dec 2025" | add_certification | {name, issuer, date, badge_url, active:true} |
| "edit AWS cert date" | edit_certification | {target_id, date: "..."} |
| "add badge URL to Oracle cert" | edit_certification | {target_id, badge_url: "..."} |
| "hide / deactivate a cert" | edit_certification | {target_id, active: false} |
| "remove cert" | remove_certification | target_id only |

### ── EDUCATION ──
| User says | action | updates shape |
|---|---|---|
| "add Deep Learning module to UCD" | edit_education | {target_id, modules: [...existing + "Deep Learning"]} |
| "remove Blockchain from SPPU modules" | edit_education | {target_id, modules: [...remaining]} |
| "edit UCD grade / degree name" | edit_education | {target_id, grade / degree} |
| "add new education entry" | add_education | {institution, degree, location, date_range, grade, modules:[]} |
| "remove education entry" | remove_education | target_id |

### ── EXTRACURRICULAR ──
| User says | action | updates shape |
|---|---|---|
| "add chess / swimming / volunteering" | add_extracurricular | {text: "descriptive sentence"} |
| "edit Simon Community entry" | edit_extracurricular | {target_id, text: "updated text"} |
| "make badminton entry shorter / longer" | edit_extracurricular | {target_id, text: "adjusted text"} |
| "hide / deactivate an activity" | edit_extracurricular | {target_id, active: false} |
| "remove extracurricular" | remove_extracurricular | target_id |

### ── PERSONAL / CONTACT ──
| User says | action | updates shape |
|---|---|---|
| "update LinkedIn URL" | edit_personal | {linkedin: "url"} |
| "update GitHub URL" | edit_personal | {github: "url"} |
| "change phone number" | edit_personal | {phone: "..."} |
| "change email" | edit_personal | {email: "..."} |
| "update location / city" | edit_personal | {location: "..."} |
| "add portfolio / website URL" | edit_personal | {website: "..."} |
| "change my name" | edit_personal | {name: "..."} |

---

## OUTPUT FORMAT:
Return a JSON object with:
1. "action": one of the actions listed above
2. "target_id": the exact ID string of the item to edit/remove (null for add/summary/title/personal)
   - ALWAYS look up the correct ID from the profile JSON provided. Never guess.
3. "updates": the data dict as described in the table above
4. "needs_more_info": true if critical info is missing (e.g. adding experience but no company name given)
5. "question": if needs_more_info=true, a single specific question to ask the user
6. "response_message": short friendly confirmation of what changed

RULES:
- For reorder actions: include ALL existing IDs in the "order" array, just rearranged.
- For bullet edits: always return the FULL updated bullets array (not just the changed bullet).
- For hide/show: set active=true or active=false in updates.
- Never fabricate data the user hasn't mentioned.
- For ambiguous references like "my last job" or "the first project" — resolve from the profile JSON."""

    messages = [{"role": "system", "content": system}]
    # Include recent chat history for context (user may refer to previous edits)
    for msg in chat_history[-6:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": f"Current profile:\n{json.dumps(master_profile, indent=2)}\n\nUser request: {message}"})

    response = get_openai_client().chat.completions.create(
        model=get_model_name(),
        messages=messages,
        temperature=0.3,
        response_format={"type": "json_object"},
        max_tokens=3000,
    )

    return json.loads(response.choices[0].message.content)


def run_tailor_pipeline(master_profile: dict, job_description: str,
                        mode: str = "2page", user_selections: dict | None = None) -> dict:
    """
    Full pipeline: Tailor → Evaluate → (loop if fail) → Return.
    Auto-iterates until score >= EVAL_PASS_THRESHOLD or MAX_EVAL_LOOPS.
    If still below threshold, returns with needs_manual_review=True.

    Returns:
        {
          "tailored_data": { ... },
          "evaluation": { ... },
          "iterations": int,
          "final_verdict": "PASS" | "FAIL",
          "needs_manual_review": bool,
        }
    """
    # Step 1: Initial tailoring
    tailor_result = tailor.tailor(master_profile, job_description, mode, user_selections)
    tailored_data = tailor_result["tailored_data"]

    iterations = 0
    evaluation = None

    for i in range(MAX_EVAL_LOOPS):
        iterations = i + 1

        # Step 2: Evaluate
        evaluation = evaluator.evaluate(tailored_data, job_description, master_profile)

        if evaluation.get("overall_score", 0) >= EVAL_PASS_THRESHOLD:
            break

        # Step 3: Re-tailor with feedback
        if i < MAX_EVAL_LOOPS - 1:  # don't re-tailor on the last iteration
            feedback = evaluation.get("feedback", "") + "\nIssues:\n" + "\n".join(evaluation.get("issues", []))
            re_result = tailor.re_tailor_with_feedback(
                master_profile, job_description, tailored_data, feedback, mode
            )
            tailored_data = re_result.get("tailored_data", tailored_data)

    score = evaluation.get("overall_score", 0) if evaluation else 0
    passed = score >= EVAL_PASS_THRESHOLD

    return {
        "tailored_data": tailored_data,
        "evaluation": evaluation,
        "iterations": iterations,
        "final_verdict": "PASS" if passed else "FAIL",
        "needs_manual_review": not passed,
        "selection_rationale": tailor_result.get("selection_rationale", ""),
        "keyword_coverage": tailor_result.get("keyword_coverage", {}),
        "pass_threshold": EVAL_PASS_THRESHOLD,
    }
