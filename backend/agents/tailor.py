"""
Tailor Agent — takes master_profile.json + JD → tailored_data.json

Selects the best subset of experience, projects, certs from the knowledge base.
Rewrites bullets/summary to match JD keywords. Never fabricates.
"""
import json
from backend.config import TAILOR_TEMP, PROMPTS_DIR, SCHEMA_DIR, get_openai_client, get_model_name


def _load_prompt(name: str) -> str:
    from pathlib import Path
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _load_render_schema() -> str:
    """Load the original render-ready schema (what build_cv_dynamic.py expects)."""
    path = SCHEMA_DIR / ".." / "schema.json"
    path = path.resolve()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def tailor(master_profile: dict, job_description: str, mode: str = "2page",
           user_selections: dict | None = None) -> dict:
    """
    Generate a tailored CV JSON from master profile + JD.

    Args:
        master_profile: Full knowledge base (master_profile_schema format).
        job_description: Raw JD text.
        mode: "1page" or "2page".
        user_selections: Optional overrides — user-specified exp/project IDs to include.

    Returns:
        {
          "tailored_data": { ... },        # render-ready JSON (schema.json format)
          "selection_rationale": "...",     # why these items were chosen
          "keyword_coverage": { ... },     # JD keywords matched vs missed
        }
    """
    system_prompt = _load_prompt("tailor_system.txt")
    render_schema = _load_render_schema()

    user_content = f"""## MASTER PROFILE (knowledge base — everything the user has)
{json.dumps(master_profile, indent=2)}

## JOB DESCRIPTION
{job_description}

## TARGET MODE
{mode}

## OUTPUT SCHEMA (the render-ready format — fill this)
{render_schema}
"""

    if user_selections:
        user_content += f"""
## USER OVERRIDES (user explicitly wants these items included)
{json.dumps(user_selections, indent=2)}
"""

    user_content += """
## INSTRUCTIONS
1. Pick the best headline from title_variants (or rewrite from title) to match JD.
2. Pick or rewrite the best summary from summary_variants.
3. Select 2-4 experience entries most relevant to JD. Rewrite bullets to match JD language. NEVER fabricate.
4. Select 2-3 projects most relevant to JD. Rewrite bullets to match JD keywords.
5. Select certifications relevant to JD.
6. Reorder skills to put JD-matching skills first in each category.
7. For 1page mode: use bullets_short, tech_short, bullet_short fields. Omit summary. Fewer items.
8. For 2page mode: use full bullets. Include summary. More items.
9. Provide keyword_coverage showing which JD keywords were matched and which were missed.

Return JSON with keys: tailored_data, selection_rationale, keyword_coverage
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    response = get_openai_client().chat.completions.create(
        model=get_model_name(),
        messages=messages,
        temperature=TAILOR_TEMP,
        response_format={"type": "json_object"},
        max_tokens=8000,
    )

    result = json.loads(response.choices[0].message.content)
    result.setdefault("tailored_data", {})
    result.setdefault("selection_rationale", "")
    result.setdefault("keyword_coverage", {})

    return result


def re_tailor_with_feedback(master_profile: dict, job_description: str,
                             current_tailored: dict, evaluator_feedback: str,
                             mode: str = "2page") -> dict:
    """
    Re-run tailoring with evaluator feedback to fix issues.
    """
    system_prompt = _load_prompt("tailor_system.txt")

    user_content = f"""## MASTER PROFILE
{json.dumps(master_profile, indent=2)}

## JOB DESCRIPTION
{job_description}

## CURRENT TAILORED CV (needs improvement)
{json.dumps(current_tailored, indent=2)}

## EVALUATOR FEEDBACK (fix these issues)
{evaluator_feedback}

## TARGET MODE
{mode}

Revise the tailored CV based on the feedback above. Return same JSON structure:
tailored_data, selection_rationale, keyword_coverage
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    response = get_openai_client().chat.completions.create(
        model=get_model_name(),
        messages=messages,
        temperature=TAILOR_TEMP,
        response_format={"type": "json_object"},
        max_tokens=8000,
    )

    result = json.loads(response.choices[0].message.content)
    result.setdefault("tailored_data", {})
    return result
