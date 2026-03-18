"""
Auth routes — register, login, get current user.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import json

from backend.auth.models import User, get_db, init_db
from backend.auth.utils import hash_password, verify_password, create_access_token, decode_access_token
from backend.config import STORAGE_DIR
from backend.utils import r2_write_json, r2_exists

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ── Default render config ──────────────────────────
DEFAULT_RENDER_CONFIG = {
    "font_name": "Calibri",
    "font_size": 10,
    "link_color": "0070C0",
    "name_size": 18,
    "tag_size": 10.5,
    "contact_size": 9,
    "page_margins": {"top": 0.5, "bottom": 0.25, "left": 0.4, "right": 0.4},
    "section_order": ["summary", "skills", "education", "certifications", "experience", "projects", "extracurricular"],
    "include_summary": True,
    "include_extracurricular": True,
    "skills_label_width": 2.1,
    "bullet_indent": 0.2,
    "max_certs_1page": 4,
    "max_projects_1page": 3,
    "page_size": "letter"
}


# ── Schemas ────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str

class UserOut(BaseModel):
    id: str
    username: str
    email: str
    full_name: str | None
    has_master_profile: bool


# ── Dependency: current user ───────────────────────

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


# ── Endpoints ──────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter((User.email == req.email) | (User.username == req.username)).first():
        raise HTTPException(status_code=400, detail="Email or username already registered")

    user = User(
        email=req.email,
        username=req.username,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create default render config in R2
    r2_write_json(f"users/{user.username}/render_config.json", DEFAULT_RENDER_CONFIG)

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token, user_id=user.id, username=user.username)


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == form.username) | (User.email == form.username)
    ).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token, user_id=user.id, username=user.username)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        has_master_profile=r2_exists(f"users/{user.username}/master_profile.json"),
    )
