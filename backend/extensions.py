from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def _rate_limit_key():
    """Rate-limit key: authenticated user id, else client IP.

    Keying by IP alone breaks behind a proxy (everyone shares the
    nginx container IP) and lets one user exhaust everyone else's
    bucket; keying by user id alone would let unauthenticated
    traffic share one bucket. This combines both. A bad/missing
    token falls back to the IP — never raises inside the limiter.
    """
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity is not None:
            return f"user:{identity}"
    except Exception:
        pass
    return f"ip:{get_remote_address()}"


# Rate limiter — brute-force protection ke liye
# Default: 200 requests/day, 50/hour per key (see _rate_limit_key).
# Storage is NOT hardcoded here: create_app() in app.py reads
# RATELIMIT_STORAGE_URI from Config (env RATELIMIT_STORAGE_URI,
# default memory:// for dev/tests, Redis in docker-compose for prod).
# init_app() must be called in create_app() — without it the
# decorators below are inert (that was SEC-C1).
limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["200 per day", "50 per hour"],
)

# Don't initialize celery here - it will be created in app.py
