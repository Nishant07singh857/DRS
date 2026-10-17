from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.exceptions import RequestEntityTooLarge
from extensions import db, limiter
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
        current_user_id = int(get_jwt_identity())

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

        # Video validity check — ffprobe se duration nikalo
        try:
            import subprocess, json
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'json', video_path],
                capture_output=True, text=True, timeout=10
            )
            info = json.loads(probe.stdout)
            duration = float(info.get('format', {}).get('duration', 0))
            if duration > 600:  # 10 min se zyada
                os.remove(video_path)
                return jsonify({
                    'message': f'Video too long ({duration:.0f}s). Max 10 minutes. '
                               f'Chhota clip upload karo.'
                }), 400
        except Exception:
            pass  # ffprobe fail ho to aage badho, worker handle karega

        # Background me processing shuru karo
        task = process_video_task.delay(video_path, current_user_id)

        # Server ka filesystem path client ko mat do — sirf task_id kaafi hai
        return jsonify({
            'message': 'Video accepted for processing',
            'task_id': task.id,
            'filename': unique_filename,
        }), 202

    except RequestEntityTooLarge:
        # Bahar phenko taaki app-level 413 handler saaf JSON de
        raise
    except Exception as e:
        return jsonify({'message': f'Upload error: {str(e)}'}), 500
