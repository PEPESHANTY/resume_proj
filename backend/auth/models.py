"""
User model — SQLite via SQLAlchemy.
Each user gets a row here + a folder under storage/users/{user_id}/
"""
from sqlalchemy import Column, String, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
import uuid

from backend.config import DATABASE_URL
from backend.utils import upload_to_r2

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email      = Column(String, unique=True, nullable=False, index=True)
    username   = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name  = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)

    def storage_dir(self):
        """Return per-user storage path."""
        from backend.config import STORAGE_DIR
        d = STORAGE_DIR / "users" / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def master_path(self):
        return self.storage_dir() / "master_profile.json"

    def render_config_path(self):
        return self.storage_dir() / "render_config.json"

    def output_dir(self):
        d = self.storage_dir() / "output"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_to_storage(self, file_path, object_name):
        """Upload file directly to R2 without local storage."""
        # Upload to R2
        success = upload_to_r2(str(file_path), f"users/{self.id}/{object_name}")
        if success:
            print(f"File {file_path} successfully uploaded to R2 as users/{self.id}/{object_name}.")
        else:
            raise Exception(f"Failed to upload {file_path} to R2.")


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
