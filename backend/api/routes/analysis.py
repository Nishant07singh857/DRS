from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
import os
import uuid
from datetime import datetime
from tasks import process_video_task

analysis_bp = Blueprint('analysis', __name__)

# Ensure upload directory exists
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@analysis_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_video():
    try:
        current_user_id = get_jwt_identity()
        
        if 'video' not in request.files:
            return jsonify({'message': 'No video file provided'}), 400
        
        video_file = request.files['video']
        if video_file.filename == '':
            return jsonify({'message': 'No video file selected'}), 400
        
        # Generate unique filename
        file_ext = os.path.splitext(video_file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        video_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save the video file
        video_file.save(video_path)
        
        # Start video processing task
        task = process_video_task.delay(video_path, current_user_id)
        
        return jsonify({
            'message': 'Video accepted for processing', 
            'task_id': task.id,
            'video_path': video_path
        }), 202
        
    except Exception as e:
        return jsonify({'message': f'Upload error: {str(e)}'}), 500