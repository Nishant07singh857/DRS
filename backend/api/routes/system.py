"""
System API — cameras, notifications, audit (E, W, X).
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.camera import Camera, CAMERA_ROLES
from models.system import Notification, AuditLog, notify, log_audit
from datetime import datetime

system_bp = Blueprint('system', __name__)


# --- Cameras (E) ---

@system_bp.route('/cameras', methods=['POST'])
@jwt_required()
def register_camera():
    """E1: Camera register karo."""
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'message': 'Camera name zaroori hai'}), 400
    if data.get('role') and data['role'] not in CAMERA_ROLES:
        return jsonify({'message': f'Role {list(CAMERA_ROLES)} me se ho'}), 400

    cam = Camera(
        name=data['name'],
        role=data.get('role', 'main'),
        device_id=data.get('device_id'),
        venue_id=data.get('venue_id'),
        match_id=data.get('match_id'),
        resolution=data.get('resolution', '1080p'),
        fps=data.get('fps', 60),
        status='online',
    )
    db.session.add(cam)
    db.session.commit()

    log_audit(int(get_jwt_identity()), 'camera.registered',
              'camera', cam.id, {'name': cam.name})
    db.session.commit()
    return jsonify(cam.to_dict()), 201


@system_bp.route('/cameras', methods=['GET'])
@jwt_required()
def list_cameras():
    match_id = request.args.get('match_id', type=int)
    q = Camera.query
    if match_id:
        q = q.filter_by(match_id=match_id)
    cams = q.all()
    return jsonify([c.to_dict() for c in cams]), 200


@system_bp.route('/cameras/<int:cam_id>/heartbeat', methods=['POST'])
@jwt_required()
def camera_heartbeat(cam_id):
    """E5: Camera health update."""
    cam = Camera.query.get_or_404(cam_id)
    data = request.get_json() or {}
    cam.heartbeat(
        battery=data.get('battery_pct'),
        storage=data.get('storage_gb_free'),
        dropped=data.get('dropped_frames', 0),
    )

    # W3: Low battery / storage alert
    if cam.battery_pct and cam.battery_pct < 20:
        notify(None, 'camera',
               f'{cam.name}: Battery low!',
               f'Battery {cam.battery_pct}% — charge karo ya replace karo.',
               severity='warning')

    db.session.commit()
    return jsonify(cam.to_dict()), 200


@system_bp.route('/cameras/<int:cam_id>/status', methods=['POST'])
@jwt_required()
def camera_status(cam_id):
    """Recording start/stop, offline mark karo."""
    cam = Camera.query.get_or_404(cam_id)
    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status not in ('online', 'offline', 'recording', 'error'):
        return jsonify({'message': 'Invalid status'}), 400
    cam.status = new_status
    db.session.commit()
    return jsonify(cam.to_dict()), 200


# --- Notifications (W) ---

@system_bp.route('/notifications', methods=['GET'])
@jwt_required()
def list_notifications():
    user_id = int(get_jwt_identity())
    unread_only = request.args.get('unread') == '1'
    q = Notification.query.filter(
        (Notification.user_id == user_id) | (Notification.user_id.is_(None))
    )
    if unread_only:
        q = q.filter_by(is_read=False)
    notifs = q.order_by(Notification.created_at.desc()).limit(30).all()
    return jsonify([n.to_dict() for n in notifs]), 200


@system_bp.route('/notifications/<int:nid>/read', methods=['POST'])
@jwt_required()
def mark_read(nid):
    n = Notification.query.get_or_404(nid)
    n.is_read = True
    db.session.commit()
    return jsonify(n.to_dict()), 200


# --- Audit (X) ---

@system_bp.route('/audit', methods=['GET'])
@jwt_required()
def list_audit():
    """X9: Audit trail dekho."""
    entity = request.args.get('entity_type')
    eid = request.args.get('entity_id', type=int)
    q = AuditLog.query
    if entity:
        q = q.filter_by(entity_type=entity)
    if eid:
        q = q.filter_by(entity_id=eid)
    logs = q.order_by(AuditLog.created_at.desc()).limit(50).all()
    return jsonify([l.to_dict() for l in logs]), 200
