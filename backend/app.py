import json
import os

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from celery import Celery

# Extensions ka single source of truth — models, tasks aur routes sab
# extensions.db use karte hain. (Pehle app.py me alag db instance tha,
# jo asli bug tha.)
from extensions import db, migrate, jwt, limiter

# Celery instance banayein.
# NOTE: broker/backend constructor me mat do — wo _preconf me jaate hain
# aur baad me conf.update() se override NAHI hote. Sab config neeche
# create_app() me hoti hai taaki override hamesha kaam kare.
celery = Celery(__name__)


def _json_safe(value):
    """Celery result ko JSON-serializable banao (exception objects ko string me badlo)."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _max_upload_mb():
    """Non-numeric MAX_UPLOAD_MB par ValueError ki jagah saaf config error do."""
    raw = os.getenv("MAX_UPLOAD_MB", "500")
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(
            f"MAX_UPLOAD_MB numeric hona chahiye, mila: {raw!r}"
        )


# ----------------------------------------------------
# App Factory
# ----------------------------------------------------
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Upload size limit — bina iske koi bhi kitni badi file bhejkar disk bhar sakta hai
    max_mb = _max_upload_mb()
    app.config["MAX_CONTENT_LENGTH"] = max_mb * 1024 * 1024

    # SEC-H1: nginx ke peeche Flask ko asli client IP chahiye, warna
    # rate limiter har user ko nginx container ka IP samajhta hai.
    # ProxyFix SIRF tab lagao jab deployment me ek trusted proxy ho
    # (docker-compose backend/worker me TRUST_PROXY=1 set hai). Bina
    # proxy ke direct deploy par X-Forwarded-For spoof ho sakta hai,
    # isliye wahan ise off rakho.
    if os.getenv("TRUST_PROXY", "").lower() in ("1", "true", "yes"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Extensions link karo
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    # SEC-C1: isi call ke bina limiter decorators inert the.
    # Storage Config.RATELIMIT_STORAGE_URI se aata hai (memory://
    # dev/tests, Redis prod) — Flask-Limiter init_app app config se
    # padhta hai.
    limiter.init_app(app)

    # SEC-H4: token blocklist — /auth/logout par revoke hua token
    # dobara accept nahi hoga.
    from models.security import RevokedToken

    @jwt.token_in_blocklist_loader
    def _check_blocklist(jwt_header, jwt_payload):
        return (
            RevokedToken.query.filter_by(jti=jwt_payload["jti"]).first()
            is not None
        )

    # CORS sirf allowed origins ke liye (pehle sab ke liye khula tha)
    origins = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ]
    CORS(app, origins=origins)

    # Celery config — poora Flask config dump karne se purani (CELERY_*)
    # aur nayi setting keys mix ho jati hain, jo Celery reject karta hai.
    # Sirf zaroori keys naye format me set karo.
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
    )

    # Celery tasks ko Flask app context do
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    # Task-status / health routes yahan (factory ke andar) register
    # hote hain, taaki ye sirf module-level app par hi nahi, har
    # create_app() instance par milen (tests isi se chalte hain).
    @app.route("/api/tasks/<task_id>/status")
    def get_task_status(task_id):
        # SEC-C4: pehle ye endpoint bina JWT ke kisi bhi task_id ka
        # result de deta tha. Ab JWT zaroori hai, aur task sirf usi
        # user ko dikhta hai jisne upload kiya tha (models.security.
        # TaskOwnership, upload par likha jata hai). Non-owner /
        # unknown task_id par 404 — taaki task existence bhi
        # enumerate na ho.
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        from models.security import TaskOwnership

        try:
            verify_jwt_in_request()
            current_user_id = int(get_jwt_identity())
        except Exception:
            return jsonify({"message": "Missing or invalid token"}), 401

        owner = TaskOwnership.query.filter_by(task_id=task_id).first()
        if owner is None or owner.user_id != current_user_id:
            return jsonify({"message": "Task not found"}), 404

        task = celery.AsyncResult(task_id)
        state = task.state
        if state == "FAILURE":
            # Exception object ko seedha jsonify karne par crash hota tha
            result = str(task.result)
        elif state == "PROGRESS":
            result = _json_safe(task.info)
        else:
            result = _json_safe(task.result)
        return jsonify({"state": state, "result": result})

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_file(e):
        max_mb = _max_upload_mb()
        return jsonify({"message": f"File too large (limit {max_mb} MB)"}), 413

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """SEC-H6: abort()/get_or_404() par HTML ki jagah JSON, aur
        koi internal detail leak nahi — sirf HTTP status ka message."""
        return jsonify({"message": e.description or "Request failed"}), e.code

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        """SEC-H6: unhandled exception par generic 500 — stack trace
        ya DB error text kabhi client ko nahi jata. Detail server
        log me."""
        app.logger.exception("Unhandled error: %s", e)
        return jsonify({"message": "Internal error"}), 500

    # Blueprints register karo
    with app.app_context():
        from api.routes.auth import auth_bp
        from api.routes.analysis import analysis_bp
        from api.routes.reviews import reviews_bp
        from api.routes.matches import matches_bp
        from api.routes.training import training_bp
        from api.routes.system import system_bp
        from api.routes.replay import replay_bp
        from api.routes.calibration import calibration_bp

        app.register_blueprint(auth_bp, url_prefix="/api/auth")
        app.register_blueprint(analysis_bp, url_prefix="/api/analysis")
        app.register_blueprint(reviews_bp, url_prefix="/api")
        app.register_blueprint(matches_bp, url_prefix="/api")
        app.register_blueprint(training_bp, url_prefix="/api")
        app.register_blueprint(system_bp, url_prefix="/api")
        app.register_blueprint(replay_bp, url_prefix="/api")
        app.register_blueprint(calibration_bp, url_prefix="/api")

    return app


# ----------------------------------------------------
# App instance (gunicorn app:app aur celery -A app.celery ke liye)
# ----------------------------------------------------
app = create_app()
