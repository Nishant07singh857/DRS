from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from werkzeug.exceptions import RequestEntityTooLarge, HTTPException
from extensions import db, limiter
from models.security import TaskOwnership
from api.routes.common import current_user_id
from config import Config
import os
import uuid
from tasks import process_video_task

analysis_bp = Blueprint('analysis', __name__)

# Absolute upload folder (Config se) — CWD par nirbhar nahi
UPLOAD_FOLDER = Config.UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@analysis_bp.route('/upload', methods=['POST'])
@jwt_required()
@limiter.limit("10 per hour")  # upload abuse roko
def upload_video():
    try:
        uid = current_user_id()

        if 'video' not in request.files:
            return jsonify({'message': 'No video file provided'}), 400

        video_file = request.files['video']
        if not video_file.filename:
            return jsonify({'message': 'No video file selected'}), 400

        # Sirf allowed video formats — bina iske koi bhi file (.exe, .php) upload ho jati
        file_ext = os.path.splitext(video_file.filename)[1].lower()
        if file_ext not in Config.ALLOWED_VIDEO_EXTENSIONS:
            return jsonify({
                'message': f"Invalid file type '{file_ext}'. "
                           f"Allowed: {sorted(Config.ALLOWED_VIDEO_EXTENSIONS)}"
            }), 400

        # File size check (pehle se hi MAX_CONTENT_LENGTH hai, lekin clear message do)
        video_file.seek(0, 2)  # end par jao
        file_size = video_file.tell()
        video_file.seek(0)  # wapas shuru par
        from flask import current_app
        max_size = current_app.config.get('MAX_CONTENT_LENGTH', 500 * 1024 * 1024)
        max_mb = max_size // (1024 * 1024)
        if file_size > max_size:
            return jsonify({
                'message': f'File too large ({file_size // (1024*1024)}MB). '
                           f'Max: {max_mb}MB. '
                           f'Tip: video ko compress karo ya chhota clip upload karo.'
            }), 413
        if file_size < 1024:  # 1KB se chhota = corrupt
            return jsonify({'message': 'File too small, possibly corrupt.'}), 400

        # Unique filename (UUID) — path traversal ka khatra nahi
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        video_path = os.path.join(UPLOAD_FOLDER, unique_filename)

        video_file.save(video_path)

        # Video validity check — ffprobe se duration nikalo.
        # SEC-H2: pehle ffprobe failure swallow ho jati thi (pass),
        # aur Docker image me ffprobe tha hi nahi — 10-min limit
        # kabhi chalta hi nahi tha. Ab failure / missing duration =
        # reject (file delete karke), pass-through nahi.
        try:
            import subprocess, json
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'json', video_path],
                capture_output=True, text=True, timeout=10
            )
            info = json.loads(probe.stdout)
            duration = float(info.get('format', {}).get('duration', 0))
            if not duration:
                raise ValueError('duration missing')
            if duration > 600:  # 10 min se zyada
                os.remove(video_path)
                return jsonify({
                    'message': f'Video too long ({duration:.0f}s). Max 10 minutes. '
                               f'Chhota clip upload karo.'
                }), 400
        except Exception:
            if os.path.exists(video_path):
                os.remove(video_path)
            return jsonify({
                'message': 'Video validate nahi ho saka — corrupt ya '
                           'unsupported file ho sakti hai.'
            }), 400

        # Background me processing shuru karo
        task = process_video_task.delay(video_path, uid)

        # SEC-C4: task_id -> user_id binding likho, taaki status
        # endpoint sirf uploader ko result de. DB me hai, isliye
        # kisi bhi backend worker se poll karne par bhi kaam karega.
        try:
            db.session.add(TaskOwnership(task_id=task.id, user_id=uid))
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "TaskOwnership write failed for task %s", task.id)

        # Server ka filesystem path client ko mat do — sirf task_id kaafi hai
        return jsonify({
            'message': 'Video accepted for processing',
            'task_id': task.id,
            'filename': unique_filename,
        }), 202

    except RequestEntityTooLarge:
        # Bahar phenko taaki app-level 413 handler saaf JSON de
        raise
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Upload failed")
        return jsonify({'message': 'Upload failed'}), 500
