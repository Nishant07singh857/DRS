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


# ===== Umpire Control Center (N) =====

@reviews_bp.route('/reviews/request', methods=['POST'])
@jwt_required()
def request_review():
    """
    N1: Umpire review request karta hai.
    Body: {"review_type": "LBW", "video_path": "...", "original_call": "OUT",
           "match_id": 1, "delivery_id": 5}
    → status='pending', queue me jayega
    """
    from core_processing.review_workflow import validate_review_request
    try:
        current_user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        review_type = data.get('review_type', 'LBW')
        validate_review_request(review_type, data.get('original_call'))

        review = Review(
            user_id=current_user_id,
            video_path=data.get('video_path', ''),
            decision='PENDING',
            review_type=review_type,
            status='pending',
            match_id=data.get('match_id'),
            delivery_id=data.get('delivery_id'),
            original_call=data.get('original_call'),
        )
        db.session.add(review)
        db.session.commit()
        return jsonify(review.to_dict()), 201

    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500


@reviews_bp.route('/reviews/queue', methods=['GET'])
@jwt_required()
def review_queue():
    """
    N3: Review queue — pending/processing sabse pehle.
    ?status=pending ya ?match_id=1 se filter karo
    """
    try:
        status = request.args.get('status')
        match_id = request.args.get('match_id', type=int)

        q = Review.query
        if status:
            q = q.filter_by(status=status)
        if match_id:
            q = q.filter_by(match_id=match_id)

        # Pending sabse pehle, phir naye sabse pehle
        reviews = q.order_by(
            db.case(
                (Review.status == 'pending', 0),
                (Review.status == 'processing', 1),
                else_=2
            ),
            Review.created_at.desc()
        ).limit(50).all()

        return jsonify([r.to_dict() for r in reviews]), 200

    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500


@reviews_bp.route('/reviews/<int:review_id>/complete', methods=['POST'])
@jwt_required()
def complete_review(review_id):
    """
    System AI processing complete karta hai.
    Body: {"ai_recommendation": "OUT", "ai_confidence": 87.5,
           "evidence": {...}}
    → status='completed' (ya 'inconclusive' agar confidence kam)
    """
    from core_processing.review_workflow import ReviewWorkflow
    try:
        review = Review.query.get_or_404(review_id)
        data = request.get_json() or {}

        rec = data.get('ai_recommendation')
        conf = data.get('ai_confidence', 0)
        if rec not in ('OUT', 'NOT OUT', 'INCONCLUSIVE'):
            return jsonify({'message': 'Invalid recommendation'}), 400

        ReviewWorkflow.transition(review, 'processing')
        review.ai_recommendation = rec
        review.ai_confidence = conf
        review.evidence = data.get('evidence', {})
        review.decision = rec
        review.confidence = conf

        # Kam confidence → inconclusive
        if rec == 'INCONCLUSIVE' or conf < 50:
            ReviewWorkflow.transition(review, 'inconclusive')
        else:
            ReviewWorkflow.transition(review, 'completed')

        db.session.commit()
        return jsonify(review.to_dict()), 200

    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500


@reviews_bp.route('/reviews/<int:review_id>/confirm', methods=['POST'])
@jwt_required()
def confirm_review(review_id):
    """
    N9: Third umpire confirm karta hai.
    Body: {"action": "accept" | "reject" | "override",
           "final_decision": "OUT" (override ke liye),
           "note": "kyun override kiya"}
    → status='confirmed', is_locked=True (N11)
    """
    from core_processing.review_workflow import ReviewWorkflow
    try:
        current_user_id = int(get_jwt_identity())
        review = Review.query.get_or_404(review_id)
        data = request.get_json() or {}

        if review.is_locked:
            return jsonify({'message': 'Review locked hai — change nahi ho sakta'}), 400

        action = data.get('action')
        if action not in ('accept', 'reject', 'override'):
            return jsonify({'message': 'Action accept/reject/override hona chahiye'}), 400

        if review.status not in ('completed', 'inconclusive'):
            return jsonify({
                'message': f'Pehle AI processing complete hone do (current: {review.status})'
            }), 400

        # Final decision nikalo
        if action == 'accept':
            final = review.ai_recommendation
        elif action == 'reject':
            # Reject = original call wapas
            final = review.original_call or 'NOT OUT'
        else:  # override
            final = data.get('final_decision')
            if final not in ('OUT', 'NOT OUT'):
                return jsonify({'message': 'Override ke liye final_decision do'}), 400

        review.final_decision = final
        review.decision = final
        review.confirmed_by = current_user_id
        review.confirmed_at = db.func.current_timestamp()
        review.confirmation_note = data.get('note', '')
        review.is_locked = True  # N11: lock!
        ReviewWorkflow.transition(review, 'confirmed')

        db.session.commit()
        return jsonify(review.to_dict()), 200

    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500


@reviews_bp.route('/reviews/<int:review_id>/retry', methods=['POST'])
@jwt_required()
def retry_review(review_id):
    """N3: Failed review ko wapas queue me dalo."""
    from core_processing.review_workflow import ReviewWorkflow
    try:
        review = Review.query.get_or_404(review_id)
        ReviewWorkflow.transition(review, 'pending')
        review.ai_recommendation = None
        review.evidence = None
        db.session.commit()
        return jsonify(review.to_dict()), 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500
