# CV Builder — Reusable Personalised CV System
**Stack:** Python · python-docx · GPT-4o API · JSON Schema
**Goal:** Given any old CV + a job description → produce a polished, ATS-friendly, tailored `.docx` + `.pdf` without fabricating anything.

---

## Core Idea

```
OLD CV (PDF/DOCX/text)
        │
        ▼
  [Extractor Agent]  ──── GPT-4o ────►  master_data.json   (one per person, saved forever)
                                               │
                          JOB DESCRIPTION ────►│
                                               ▼
                                   [Tailor Agent]  ──── GPT-4o ────►  tailored_data.json
                                                                              │
                                                                              ▼
                                                                   [Renderer]  build_cv_dynamic.py
                                                                              │
                                                                    ┌─────────┴─────────┐
                                                                    ▼                   ▼
                                                            output.docx           output.pdf
```

Three clean stages. Each stage is independent — you can re-run the tailor step with a new JD without re-extracting. You can re-render with a different template without touching the data.

---

## Project Structure

```
cv-builder/
│
├── data/
│   └── shantanu_master.json        # one per person — source of truth
│
├── output/
│   └── SHANTANU_CV_<COMPANY>.docx  # generated files
│   └── SHANTANU_CV_<COMPANY>.pdf
│
├── agents/
│   ├── extractor.py                # Stage 1: old CV → master_data.json
│   └── tailor.py                   # Stage 2: master + JD → tailored_data.json
│
├── renderer/
│   └── build_cv_dynamic.py         # Stage 3: tailored JSON → docx + pdf
│   └── schema.json                 # JSON schema for validation
│
├── prompts/
│   ├── extract_system.txt          # system prompt for extractor agent
│   └── tailor_system.txt           # system prompt for tailor agent
│
├── run.py                          # CLI entry point — ties all three stages
└── requirements.txt
```

---

## Stage 1 — Extractor Agent

**Input:** Old CV as raw text (extracted from PDF/DOCX) + `schema.json`
**Output:** `master_data.json` — complete structured profile
**Model:** `gpt-4o`

### What it does:
- Reads the raw CV text
- Fills every field in the JSON schema faithfully — no invention, no paraphrasing beyond cleanup
- Marks fields it could not find as `null` so you know what's missing
- You review and correct `master_data.json` once — then it's your permanent profile

### Key prompt principle:
> "Extract only what is explicitly stated. Do not infer, embellish, or assume. If a field is absent, set it to null."

### PDF/DOCX text extraction:
- PDF → `pdfplumber` or `pymupdf`
- DOCX → `python-docx` `.text` property
- Fallback: user pastes raw text

---

## Stage 2 — Tailor Agent

**Input:** `master_data.json` + raw job description text
**Output:** `tailored_data.json` — same schema, content optimised for the JD
**Model:** `gpt-4o`

### What it does:
1. **Headline selection** — picks the best title variant from master data for this role
2. **Summary rewrite** — rewrites summary using JD keywords, stays truthful to master data
3. **Bullet reordering + rewording** — for each experience/project, reorders bullets by relevance to JD, tightens phrasing to mirror JD language (without fabricating)
4. **Skills reordering** — moves JD-matching skills to front of each category
5. **Project selection** — picks the 2–3 most relevant projects (drops others)
6. **Certification inclusion** — includes certs most relevant to the role
7. **ATS keyword injection** — naturally inserts JD keywords into existing bullets where truthful

### Key prompt principles:
> "You are a professional CV writer. Your job is to reframe and reorder — never fabricate. Every bullet must be traceable to a real fact in master_data.json. Mirror the language of the job description where the candidate's real experience genuinely matches it."

> "ATS systems scan for exact keyword matches. Prefer the JD's exact phrasing over synonyms where both are accurate (e.g., if JD says 'machine learning pipelines' and master data says 'ML workflows', use 'machine learning pipelines')."

### ATS rules baked into the prompt:
- No tables in the final content (renderer uses borderless tables for layout — fine; content itself is plain)
- No headers/footers for key info (name/contact always in body)
- Spell out acronyms at least once
- Quantify achievements where numbers exist in master data
- No graphics, icons, or images (renderer handles this)
- Keep bullet sentences under ~2 lines (ATS truncates)

---

## Stage 3 — Renderer (`build_cv_dynamic.py`)

**Input:** `tailored_data.json` (or `master_data.json` for generic version)
**Output:** `.docx` + `.pdf`

This is a direct evolution of the existing `build_cv.py`. All formatting logic stays identical. The only change: instead of hardcoded constants, it reads from the JSON file.

### Supports:
- `"mode": "2page"` or `"mode": "1page"` flag in JSON (or CLI arg)
- Hyperlinks from JSON (`linkedin.url`, `certifications[].badge_url`, `projects[].paper_url`)
- Right-aligned bold dates on all sections (existing behaviour)
- Optional sections: `summary`, `extracurricular` (omitted if null or empty)

---

## JSON Schema (`schema.json`)

```json
{
  "personal": {
    "name": "string",
    "title": "string",
    "location": "string",
    "email": "string",
    "phone": "string",
    "linkedin": { "url": "string", "display": "string" },
    "github":   { "url": "string", "display": "string" }
  },
  "summary": "string | null",
  "skills": [
    { "category": "string", "items": "string" }
  ],
  "experience": [
    {
      "company":    "string",
      "location":   "string",
      "role":       "string",
      "date_range": "string",
      "bullets":    ["string"]
    }
  ],
  "projects": [
    {
      "title":     "string",
      "date":      "string",
      "tech":      "string",
      "bullets":   ["string"],
      "paper_url": "string | null"
    }
  ],
  "education": [
    {
      "degree":      "string",
      "institution": "string",
      "date":        "string",
      "honors":      "string | null",
      "grade":       "string | null",
      "modules":     "string | null"
    }
  ],
  "certifications": [
    {
      "name":      "string",
      "link_text": "string",
      "url":       "string | null",
      "date":      "string"
    }
  ],
  "extracurricular": ["string"]
}
```

---

## CLI Entry Point (`run.py`)

```
# Extract from old CV (run once per person)
python run.py extract --input "old_cv.pdf" --out "data/shantanu_master.json"

# Tailor for a job (run per application)
python run.py tailor --master "data/shantanu_master.json" --jd "jd_google.txt" --out "data/shantanu_google.json"

# Render to docx + pdf
python run.py render --data "data/shantanu_google.json" --mode 2page --company GOOGLE

# Full pipeline in one shot
python run.py all --input "old_cv.pdf" --jd "jd_google.txt" --company GOOGLE --mode 2page
```

---

## Build Order

| Phase | File | What to build |
|---|---|---|
| 1 | `schema.json` | Define the JSON contract first — everything depends on this |
| 2 | `renderer/build_cv_dynamic.py` | Port existing `build_cv.py` to read from JSON — test with Shantanu's data |
| 3 | `agents/extractor.py` | GPT-4o extraction agent + system prompt |
| 4 | `agents/tailor.py` | GPT-4o tailor agent + system prompt |
| 5 | `run.py` | CLI wiring |
| 6 | Test end-to-end | Old CV → JSON → tailored → docx → pdf |

Start with Phase 2 so you have a working renderer to validate the schema against before the agents are written.

---

## What stays from `build_cv.py`

All formatting functions copy across unchanged:
- `set_page_margins`, `sp`, `r`, `heading`, `bul`, `right_tab`, `tab_run`
- `add_hyperlink`, `build_skills`, `build_certifications`
- `build_education`, `build_exp_entry`, `build_project`
- `export_pdfs`

Only the data constants at the top get replaced by `json.load(open(data_file))`.

---

## Notes

- **Never overwrite `master_data.json`** — the tailor step always writes a new `tailored_data.json`
- **Human review checkpoint** recommended after extraction (Stage 1) before tailoring
- **GPT-4o temperature** = 0.3 for extractor (faithful), 0.6 for tailor (creative reframing)
- **Token budget**: a full CV JSON is ~1500 tokens; a JD is ~500–1000 tokens — well within gpt-4o context
- The renderer is completely offline — API calls only happen in Stages 1 and 2
