"""
Formatter Agent — translates natural-language formatting requests
into render_config.json updates.

Examples:
  "Make font size 11" → {"font_size": 11}
  "Put experience before education" → update section_order
  "Remove extracurricular section" → {"include_extracurricular": false}
"""
import json
from backend.config import FORMATTER_TEMP, PROMPTS_DIR, get_openai_client, get_model_name


def _load_prompt(name: str) -> str:
    from pathlib import Path
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def parse_format_request(user_message: str, current_config: dict) -> dict:
    """
    Convert a natural language formatting request into render_config changes.

    Args:
        user_message: User's formatting request in plain English.
        current_config: Current render_config.json contents.

    Returns:
        {
          "updates": { ... },           # key-value pairs to merge into render_config
          "explanation": "...",         # what was changed and why
          "requires_re_render": true    # whether CV needs to be re-rendered
        }
    """
    system_prompt = _load_prompt("formatter_system.txt")

    user_content = f"""## USER REQUEST
{user_message}

## CURRENT RENDER CONFIG
{json.dumps(current_config, indent=2)}

## AVAILABLE CONFIG FIELDS
- font_name (string): Font family name e.g. "Calibri", "Arial", "Times New Roman"
- font_size (number): Body text font size e.g. 10, 11, 12
- link_color (string): Hex color for hyperlinks e.g. "0070C0"
- name_size (number): Name font size in header e.g. 18
- tag_size (number): Title/tagline font size e.g. 10.5
- contact_size (number): Contact line font size e.g. 9
- page_margins (object): {{top, bottom, left, right}} in inches
- section_order (array): Order of sections e.g. ["summary", "skills", "education", "certifications", "experience", "projects", "extracurricular"]
- include_summary (boolean): Whether to show professional summary
- include_extracurricular (boolean): Whether to show extracurricular section
- skills_label_width (number): Width of skill category label column in inches
- bullet_indent (number): Bullet point left indent in inches
- max_certs_1page (integer): Max certifications on 1-page CV
- max_projects_1page (integer): Max projects on 1-page CV
- page_size (string): "letter" or "a4"

Return JSON with: updates, explanation, requires_re_render
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    response = get_openai_client().chat.completions.create(
        model=get_model_name(),
        messages=messages,
        temperature=FORMATTER_TEMP,
        response_format={"type": "json_object"},
        max_tokens=1500,
    )

    result = json.loads(response.choices[0].message.content)
    result.setdefault("updates", {})
    result.setdefault("explanation", "")
    result.setdefault("requires_re_render", True)

    return result


def apply_config_updates(current_config: dict, updates: dict) -> dict:
    """
    Merge updates into current config (deep merge for nested objects like page_margins).
    """
    merged = current_config.copy()
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
