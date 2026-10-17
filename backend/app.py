import json
import os

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from config import Config
from celery import Celery

# Extensions ka single source of truth — models, tasks aur routes sab
# extensions.db use karte hain. (Pehle app.py me alag db instance tha,
# jo asli bug tha.)
from extensions import db, migrate, jwt

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


# ----------------------------------------------------
# App Factory
# ----------------------------------------------------
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Upload size limit — bina iske koi bhi kitni badi file bhejkar disk bhar sakta hai
    max_mb = int(os.getenv("MAX_UPLOAD_MB", "500"))
    app.config["MAX_CONTENT_LENGTH"] = max_mb * 1024 * 1024

    # Extensions link karo
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

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

    # Blueprints register karo
    with app.app_context():
        from api.routes.auth import auth_bp
        from api.routes.analysis import analysis_bp
        from api.routes.reviews import reviews_bp

        app.register_blueprint(auth_bp, url_prefix="/api/auth")
        app.register_blueprint(analysis_bp, url_prefix="/api/analysis")
        app.register_blueprint(reviews_bp, url_prefix="/api")

    return app


# ----------------------------------------------------
# App instance (gunicorn app:app aur celery -A app.celery ke liye)
# ----------------------------------------------------
app = create_app()


@app.route("/api/tasks/<task_id>/status")
def get_task_status(task_id):
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
    max_mb = int(os.getenv("MAX_UPLOAD_MB", "500"))
    return jsonify({"message": f"File too large (limit {max_mb} MB)"}), 413
