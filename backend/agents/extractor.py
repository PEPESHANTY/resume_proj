"""
Extractor Agent — converts uploaded CV (PDF/DOCX/image) into master_profile.json

Supports:
  - PDF  → pdfplumber text extraction
  - DOCX → python-docx text extraction
  - Image → GPT-4o Vision for OCR
  - Raw text → direct extraction

Returns structured JSON + list of missing/ambiguous fields to ask the user about.
"""
import json
import io
import base64
from pathlib import Path

from backend.config import EXTRACTOR_TEMP, PROMPTS_DIR, SCHEMA_DIR, get_openai_client, get_model_name, USE_AZURE, AZURE_OPENAI_DEPLOYMENT

client = get_openai_client()


# ── Text extraction from files ─────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    import pdfplumber
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n\n".join(text_parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text_from_image(file_bytes: bytes, mime_type: str = "image/png") -> str:
    """Use GPT-4o Vision to OCR an image of a CV."""
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    response = client.chat.completions.create(
        model=get_model_name(),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract ALL text from this CV/resume image exactly as written. Preserve structure, headings, bullets, dates. Return plain text."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
                ]
            }
        ],
        max_tokens=4000,
        temperature=0.1,
    )
    return response.choices[0].message.content


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Route to the right extractor based on file extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_bytes)
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}
        return extract_text_from_image(file_bytes, mime_map.get(ext, "image/png"))
    else:
        # Assume raw text
        return file_bytes.decode("utf-8", errors="replace")


# ── LLM extraction ────────────────────────────────

def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _load_schema() -> str:
    path = SCHEMA_DIR / "master_profile_schema.json"
    return path.read_text(encoding="utf-8")


def extract_to_json(cv_text: str, existing_profile: dict | None = None) -> dict:
    """
    Call GPT-4o to convert raw CV text into structured JSON matching master_profile_schema.

    Args:
        cv_text: Raw text extracted from the uploaded file.
        existing_profile: If user already has a profile, pass it so the LLM can merge/update.

    Returns:
        {
          "profile": { ... },        # the structured JSON (master_profile format)
          "missing_fields": [ ... ],  # list of field names that couldn't be found
          "questions": [ ... ]        # specific questions to ask the user
        }
    """
    system_prompt = _load_prompt("extract_system.txt")
    schema_text = _load_schema()

    user_content = f"""## RAW CV TEXT
{cv_text}

## JSON SCHEMA TO FILL
{schema_text}
"""

    if existing_profile:
        user_content += f"""
## EXISTING PROFILE (merge new data into this, do not lose existing entries)
{json.dumps(existing_profile, indent=2)}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    response = client.chat.completions.create(
        model=get_model_name(),
        messages=messages,
        temperature=EXTRACTOR_TEMP,
        response_format={"type": "json_object"},
        max_tokens=8000,
    )

    result = json.loads(response.choices[0].message.content)
    return result


def run_extraction(file_bytes: bytes, filename: str, existing_profile: dict | None = None) -> dict:
    """
    Full extraction pipeline: file → text → structured JSON.

    Returns:
        {
          "profile": { ... },
          "missing_fields": ["github_url", "phone", ...],
          "questions": ["What is your GitHub profile URL?", ...]
        }
    """
    cv_text = extract_text(file_bytes, filename)

    if not cv_text or len(cv_text.strip()) < 50:
        return {
            "profile": None,
            "missing_fields": ["entire_cv"],
            "questions": ["Could not extract text from the uploaded file. Please try a different format (PDF preferred) or paste your CV text directly."],
            "raw_text": cv_text,
        }

    result = extract_to_json(cv_text, existing_profile)

    # Ensure required keys exist
    result.setdefault("profile", {})
    result.setdefault("missing_fields", [])
    result.setdefault("questions", [])

    return result
