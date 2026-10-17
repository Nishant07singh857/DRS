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
