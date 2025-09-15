from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from config import Config
from celery import Celery

# ----------------------------------------------------
# 1. ऐप और एक्सटेंशन को इनिशियलाइज़ करें
# ----------------------------------------------------
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()

# Celery इंस्टेंस बनाएँ
celery = Celery(__name__, broker=Config.CELERY_BROKER_URL, backend=Config.CELERY_RESULT_BACKEND)

# ----------------------------------------------------
# 2. App Factory फंक्शन
# ----------------------------------------------------
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # एक्सटेंशन को ऐप के साथ लिंक करें
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(app)

    # Celery कॉन्फ़िगरेशन को ऐप के साथ अपडेट करें
    celery.conf.update(app.config)

    # एक विशेष क्लास जो Celery को Flask कॉन्टेक्स्ट देती है
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask
    
    # ब्लूप्रिंट को ऐप कॉन्टेक्स्ट के अंदर इम्पोर्ट और रजिस्टर करें
    with app.app_context():
        # --- यही वह बदलाव है ---
        # हमने 'backend.' हटा दिया है क्योंकि हम पहले से ही उस फोल्डर के अंदर हैं।
        from api.routes.auth import auth_bp
        from api.routes.analysis import analysis_bp
        from api.routes.reviews import reviews_bp
        
        app.register_blueprint(auth_bp, url_prefix='/api/auth')
        app.register_blueprint(analysis_bp, url_prefix='/api/analysis')
        app.register_blueprint(reviews_bp, url_prefix='/api')
        # ------------------------

    return app

# ----------------------------------------------------
# 3. ऐप बनाएँ
# ----------------------------------------------------
app = create_app()

# ----------------------------------------------------
# 4. टास्क स्टेटस के लिए रूट
# ----------------------------------------------------
@app.route('/api/tasks/<task_id>/status')
def get_task_status(task_id):
    task = celery.AsyncResult(task_id)
    response = {
        'state': task.state,
        'result': task.result,
    }
    return jsonify(response)


