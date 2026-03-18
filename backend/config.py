"""
Application configuration — reads from .env
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent.parent          # c:\RESUME_PROJECT
BACKEND_DIR  = Path(__file__).resolve().parent                 # c:\RESUME_PROJECT\backend
STORAGE_DIR  = BACKEND_DIR / "storage"
SCHEMA_DIR   = BASE_DIR / "schema"
PROMPTS_DIR  = BACKEND_DIR / "prompts"
OUTPUT_DIR   = BASE_DIR / "CREATED"
RENDERER_DIR = BACKEND_DIR / "renderer"

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Azure OpenAI ───────────────────────────────────
AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY    = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

# Fallback to direct OpenAI if Azure vars not set
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
USE_AZURE        = bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY)

# Model names (used when NOT on Azure — Azure uses deployment name instead)
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_VISION    = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")

# ── Auth ───────────────────────────────────────────
SECRET_KEY       = os.getenv("SECRET_KEY", "change-me-in-production-abcdef123456")
ALGORITHM        = "HS256"
ACCESS_TOKEN_TTL = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "1440"))   # 24h default

# ── Database ───────────────────────────────────────
DATABASE_URL     = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'app.db'}")

# ── Agent temperatures ─────────────────────────────
EXTRACTOR_TEMP   = float(os.getenv("EXTRACTOR_TEMP", "0.2"))
TAILOR_TEMP      = float(os.getenv("TAILOR_TEMP", "0.5"))
EVALUATOR_TEMP   = float(os.getenv("EVALUATOR_TEMP", "0.3"))
FORMATTER_TEMP   = float(os.getenv("FORMATTER_TEMP", "0.3"))

# ── Limits ─────────────────────────────────────────
MAX_EVAL_LOOPS      = int(os.getenv("MAX_EVAL_LOOPS", "3"))
EVAL_PASS_THRESHOLD = int(os.getenv("EVAL_PASS_THRESHOLD", "95"))


# ── OpenAI Client Factory ─────────────────────────
def get_openai_client():
    """Return an OpenAI or AzureOpenAI client depending on env vars."""
    from openai import OpenAI, AzureOpenAI

    if USE_AZURE:
        return AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    else:
        return OpenAI(api_key=OPENAI_API_KEY)


def get_model_name():
    """Return the model/deployment name to use in API calls."""
    if USE_AZURE:
        return AZURE_OPENAI_DEPLOYMENT
    return OPENAI_MODEL

# ── Cloudflare R2 (S3-compatible storage) ─────────────────────────
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_REGION = os.getenv("R2_REGION", "")
