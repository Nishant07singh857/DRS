from flask import jsonify, Blueprint, request
from models.review import Review
from extensions import db
from flask_jwt_extended import jwt_required, get_jwt_identity

reviews_bp = Blueprint('reviews', __name__)


def _serialize(review):
    return {
        'id': review.id,
        'decision': review.decision,
        'confidence': review.confidence,
        'analysis_data': review.analysis_data,
        'video_url': review.video_path,
        'created_at': review.created_at.isoformat() if review.created_at else None,
    }


@reviews_bp.route('/reviews', methods=['GET'])
@jwt_required()
def get_user_reviews():
    try:
        current_user_id = int(get_jwt_identity())
        # Pagination — bina iske hazaaron reviews ek saath load hote
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = max(1, min(per_page, 100))

        pagination = (
            Review.query.filter_by(user_id=current_user_id)
            .order_by(Review.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        return jsonify({
            'items': [_serialize(r) for r in pagination.items],
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages,
        }), 200

    except Exception as e:
        return jsonify({'message': f'Error fetching reviews: {str(e)}'}), 500


@reviews_bp.route('/reviews/<int:review_id>', methods=['GET'])
@jwt_required()
def get_review(review_id):
    try:
        current_user_id = int(get_jwt_identity())
        review = Review.query.filter_by(id=review_id, user_id=current_user_id).first()

        if not review:
            return jsonify({'message': 'Review not found'}), 404

        return jsonify(_serialize(review)), 200

    except Exception as e:
        return jsonify({'message': f'Error fetching review: {str(e)}'}), 500


@reviews_bp.route('/reviews/pitch-map', methods=['POST'])
@jwt_required()
def pitch_map_endpoint():
    """
    Bowler ka pitch map banao.
    Body: {"bowler": "Bumrah", "deliveries": [
        {"pitch_x": 4.5, "pitch_y": 0.1, "outcome": "dot", "speed_kmh": 142},
        ...
    ]}
    Returns: {"svg": "<svg>...</svg>", "stats": {...}}
    """
    from core_processing.pitch_map import PitchMap
    data = request.get_json() or {}
    pm = PitchMap(bowler_name=data.get('bowler', 'Bowler'))
    for d in data.get('deliveries', []):
        pm.add_delivery(
            pitch_x=d.get('pitch_x', 5),
            pitch_y=d.get('pitch_y', 0),
            outcome=d.get('outcome', 'dot'),
            speed_kmh=d.get('speed_kmh'),
        )
    return jsonify({'svg': pm.to_svg(), 'stats': pm.get_stats()})


@reviews_bp.route('/reviews/over-summary', methods=['POST'])
@jwt_required()
def over_summary_endpoint():
    """
    Over ka summary + HTML report banao.
    Body: {"over": 1, "bowler": "...", "batsman": "...", "balls": [...]}
    Returns: {"summary": {...}, "html": "<html>...</html>"}
    """
    from core_processing.over_summary import OverSummary
    data = request.get_json() or {}
    over = OverSummary(
        over_number=data.get('over', 1),
        bowler=data.get('bowler', 'Bowler'),
        batsman=data.get('batsman', 'Batsman'),
    )
    for b in data.get('balls', []):
        over.add_ball(b)
    return jsonify({
        'summary': over.get_summary(),
        'html': over.to_html_report(),
        'pitch_map_svg': over.pitch_map.to_svg(),
    })
