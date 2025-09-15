from flask import jsonify, Blueprint
from models.review import Review
from models.user import User
from extensions import db
from flask_jwt_extended import jwt_required, get_jwt_identity

reviews_bp = Blueprint('reviews', __name__)

@reviews_bp.route('/reviews', methods=['GET'])
@jwt_required()
def get_user_reviews():
    try:
        current_user_id = get_jwt_identity()
        reviews = Review.query.filter_by(user_id=current_user_id).order_by(Review.created_at.desc()).all()
        
        return jsonify([{
            'id': review.id,
            'decision': review.decision,
            'confidence': review.confidence,
            'analysis_data': review.analysis_data,
            'video_url': review.video_path,
            'created_at': review.created_at.isoformat() if review.created_at else None
        } for review in reviews]), 200
        
    except Exception as e:
        return jsonify({'message': f'Error fetching reviews: {str(e)}'}), 500

@reviews_bp.route('/reviews/<int:review_id>', methods=['GET'])
@jwt_required()
def get_review(review_id):
    try:
        current_user_id = get_jwt_identity()
        review = Review.query.filter_by(id=review_id, user_id=current_user_id).first()
        
        if not review:
            return jsonify({'message': 'Review not found'}), 404
        
        return jsonify({
            'id': review.id,
            'decision': review.decision,
            'confidence': review.confidence,
            'analysis_data': review.analysis_data,
            'video_url': review.video_path,
            'created_at': review.created_at.isoformat() if review.created_at else None
        }), 200
        
    except Exception as e:
        return jsonify({'message': f'Error fetching review: {str(e)}'}), 500