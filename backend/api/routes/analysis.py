from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.exceptions import RequestEntityTooLarge
from extensions import db
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

        # Unique filename (UUID) — path traversal ka khatra nahi
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        video_path = os.path.join(UPLOAD_FOLDER, unique_filename)

        video_file.save(video_path)

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
