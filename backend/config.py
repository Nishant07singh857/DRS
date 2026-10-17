import os
from dotenv import load_dotenv

load_dotenv()


def _required(name):
    """Zaroori env var missing ho to startup par hi saaf error do."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} missing hai. "
            f".env.example se .env banao aur values bharo."
        )
    return value


class Config:
    SECRET_KEY = _required("SECRET_KEY")
    JWT_SECRET_KEY = _required("JWT_SECRET_KEY")

    # Database Configuration
    # DATABASE_URL set ho to wahi use karo (tests / Heroku-style deploy ke liye),
    # warna POSTGRES_* vars se URI banao.
    _database_url = os.getenv("DATABASE_URL")
    if _database_url:
        SQLALCHEMY_DATABASE_URI = _database_url
    else:
        DB_USER = os.getenv("POSTGRES_USER", "postgres")
        DB_PASSWORD = _required("POSTGRES_PASSWORD")
        DB_HOST = os.getenv("DATABASE_HOST", "localhost")
        DB_PORT = os.getenv("DATABASE_PORT", "5432")
        DB_NAME = os.getenv("POSTGRES_DB", "drsdb")
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}

    # Celery Configuration
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # Uploads — absolute path taaki CWD par nirbhar na rahe
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

    # Sirf ye video formats allow hain
    ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
