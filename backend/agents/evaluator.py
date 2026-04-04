"""
Evaluator Agent — scores a tailored CV against the JD.

Returns PASS/FAIL + specific feedback for improvement.
"""
import json
from backend.config import EVALUATOR_TEMP, PROMPTS_DIR, EVAL_PASS_THRESHOLD, get_openai_client, get_model_name


def _load_prompt(name: str) -> str:
    from pathlib import Path
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def evaluate(tailored_data: dict, job_description: str, master_profile: dict) -> dict:
    """
    Evaluate a tailored CV for quality, ATS friendliness, and truthfulness.

    Returns:
        {
          "verdict": "PASS" | "FAIL",
          "overall_score": 0-100,
          "scores": {
            "ats_keyword_match": 0-100,
            "truthfulness": 0-100,
            "relevance_ordering": 0-100,
            "completeness": 0-100,
            "bullet_quality": 0-100,
          },
          "feedback": "Specific actionable feedback...",
          "issues": ["issue 1", "issue 2", ...],
          "strengths": ["strength 1", ...],
        }
    """
    system_prompt = _load_prompt("evaluator_system.txt")

    user_content = f"""## TAILORED CV DATA
{json.dumps(tailored_data, indent=2)}

## JOB DESCRIPTION
{job_description}

## MASTER PROFILE (source of truth — every claim must be traceable here)
{json.dumps(master_profile, indent=2)}

## EVALUATION CRITERIA
Score each dimension 0-100:

1. **ATS Keyword Match**: What % of important JD keywords appear in the CV? Check job title, required skills, tools, frameworks, methodologies.
2. **Truthfulness**: Is every bullet traceable to the master profile? Flag any fabricated or exaggerated claims.
3. **Relevance Ordering**: Are the most JD-relevant bullets listed first in each section?
4. **Completeness**: Are all required schema fields filled? Are there enough bullets per experience?
5. **Bullet Quality**: Are bullets action-verb-led, quantified where possible, under 2 lines, and ATS-parseable?

Overall score = weighted average (ATS 30%, Truthfulness 25%, Relevance 20%, Completeness 15%, Quality 10%).
PASS threshold = {EVAL_PASS_THRESHOLD}.

Return JSON with: verdict, overall_score, scores, feedback, issues, strengths
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    response = get_openai_client().chat.completions.create(
        model=get_model_name(),
        messages=messages,
        temperature=EVALUATOR_TEMP,
        response_format={"type": "json_object"},
        max_tokens=3000,
    )

    result = json.loads(response.choices[0].message.content)
    result.setdefault("verdict", "FAIL")
    result.setdefault("overall_score", 0)
    result.setdefault("scores", {})
    result.setdefault("feedback", "")
    result.setdefault("issues", [])
    result.setdefault("strengths", [])

    # Override verdict based on actual threshold
    if result["overall_score"] >= EVAL_PASS_THRESHOLD:
        result["verdict"] = "PASS"
    else:
        result["verdict"] = "FAIL"

    return result
