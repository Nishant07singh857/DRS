import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# Values that must never be accepted as real secrets (SEC-H5).
# .env.example used to ship these pre-filled; a deployer who copied
# it without editing started production with publicly known keys.
_PLACEHOLDER_SECRETS = {
    "change-me-to-a-long-random-string",
    "change-me-to-another-long-random-string",
    "change-me",
    "changeme",
    "secret",
    "password",
}


def _required(name, min_length=0):
    """Zaroori env var missing ho to startup par hi saaf error do."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} missing hai. "
            f".env.example se .env banao aur values bharo."
        )
    if value in _PLACEHOLDER_SECRETS:
        raise RuntimeError(
            f"Environment variable {name} abhi bhi placeholder value par hai. "
            f"Asli random value bharo (secrets.token_hex(32))."
        )
    if min_length and len(value) < min_length:
        raise RuntimeError(
            f"Environment variable {name} bahut chhota hai "
            f"(kam se kam {min_length} characters chahiye)."
        )
    return value


class Config:
    # Flask/JWT secrets: no hardcoded fallback (good, kept), and now
    # placeholders / short values are also rejected (SEC-H5).
    SECRET_KEY = _required("SECRET_KEY", min_length=32)
    JWT_SECRET_KEY = _required("JWT_SECRET_KEY", min_length=32)

    # JWT contract, now explicit instead of silently depending on the
    # Flask-JWT-Extended library default (SEC-H4). Access tokens live
    # 1 hour; revocation is via the blocklist (/auth/logout).
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_ALGORITHM = "HS256"

    # Rate-limiter storage (SEC-H1): memory:// for dev/tests, Redis
    # (with auth, per SEC-C5) in docker-compose. Never share the
    # Celery broker DB (0) — limiters use DB 1 there.
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    # Database Configuration
    # DATABASE_URL set ho to wahi use karo (tests / Heroku-style deploy ke liye),
    # warna POSTGRES_* vars se URI banao.
    _database_url = os.getenv("DATABASE_URL")
    if _database_url:
        SQLALCHEMY_DATABASE_URI = _database_url
    else:
        DB_USER = os.getenv("POSTGRES_USER", "postgres")
        # No silent default password: missing POSTGRES_PASSWORD fails
        # startup (SEC-H5). docker-compose must not reintroduce a
        # :-password fallback either.
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
