"""
Replay API — bookmarks, highlights, library (O).
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.replay import Bookmark, Highlight, BOOKMARK_TYPES, auto_highlights
from models.match import Delivery

replay_bp = Blueprint('replay', __name__)


@replay_bp.route('/replay/bookmarks', methods=['POST'])
@jwt_required()
def create_bookmark():
    """O5: Event bookmark banao."""
    data = request.get_json() or {}
    btype = data.get('bookmark_type', 'custom')
    if btype not in BOOKMARK_TYPES:
        return jsonify({'message': f'Type {sorted(BOOKMARK_TYPES)} me se ho'}), 400
    if data.get('timestamp_s') is None:
        return jsonify({'message': 'timestamp_s zaroori hai'}), 400

    bm = Bookmark(
        match_id=data.get('match_id'),
        delivery_id=data.get('delivery_id'),
        user_id=int(get_jwt_identity()),
        bookmark_type=btype,
        timestamp_s=data['timestamp_s'],
        frame_number=data.get('frame_number'),
        camera_id=data.get('camera_id'),
        note=data.get('note', ''),
    )
    db.session.add(bm)
    db.session.commit()
    return jsonify(bm.to_dict()), 201


@replay_bp.route('/replay/bookmarks', methods=['GET'])
@jwt_required()
def list_bookmarks():
    """O11: Search by match/type."""
    match_id = request.args.get('match_id', type=int)
    btype = request.args.get('type')
    q = Bookmark.query
    if match_id:
        q = q.filter_by(match_id=match_id)
    if btype:
        q = q.filter_by(bookmark_type=btype)
    bms = q.order_by(Bookmark.timestamp_s).limit(100).all()
    return jsonify([b.to_dict() for b in bms]), 200


@replay_bp.route('/replay/highlights/generate/<int:match_id>', methods=['POST'])
@jwt_required()
def generate_highlights(match_id):
    """O8: Match se auto highlights banao."""
    deliveries = Delivery.query.filter_by(match_id=match_id)\
        .order_by(Delivery.ball_number).all()
    if not deliveries:
        return jsonify({'message': 'Koi ball nahi mili'}), 404

    highlights = auto_highlights(match_id, [d.to_dict() for d in deliveries])
    for h in highlights:
        db.session.add(h)
    db.session.commit()
    return jsonify({
        'count': len(highlights),
        'highlights': [h.to_dict() for h in highlights],
    }), 201


@replay_bp.route('/replay/highlights', methods=['GET'])
@jwt_required()
def list_highlights():
    match_id = request.args.get('match_id', type=int)
    q = Highlight.query
    if match_id:
        q = q.filter_by(match_id=match_id)
    hls = q.order_by(Highlight.start_s).all()
    return jsonify([h.to_dict() for h in hls]), 200
