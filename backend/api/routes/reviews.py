import os

from flask import jsonify, Blueprint, request, current_app, send_file
from werkzeug.exceptions import HTTPException
from config import Config
from models.review import Review
from models.system import log_audit
from extensions import db
from flask_jwt_extended import jwt_required
from api.routes.common import current_user_id

reviews_bp = Blueprint('reviews', __name__)


def _serialize(review):
    # BE-H9: EK serializer — Review.to_dict() hi hai. Pehle _serialize
    # list/detail par alag tha: usme delivery_id nahi tha, to_dict me
    # video_url nahi tha, aur _serialize NULL review_type/status ko
    # 'LBW'/'completed' se mask kar deta tha. Ab dono ek hi dict dete
    # hain, aur NULL wahi dikhta hai (mask nahi hota). video_path /
    # video_url dono me sirf basename hota hai (SEC-M1: absolute server
    # path kabhi client ko nahi).
    return review.to_dict()


@reviews_bp.route('/reviews', methods=['GET'])
@jwt_required()
def get_user_reviews():
    try:
        uid = current_user_id()
        # Pagination — bina iske hazaaron reviews ek saath load hote
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = max(1, min(per_page, 100))

        pagination = (
            Review.query.filter_by(user_id=uid)
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

    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Reviews fetch failed")
        return jsonify({'message': 'Error fetching reviews'}), 500


@reviews_bp.route('/reviews/<int:review_id>', methods=['GET'])
@jwt_required()
def get_review(review_id):
    try:
        uid = current_user_id()
        review = Review.query.filter_by(id=review_id, user_id=uid).first()

        if not review:
            return jsonify({'message': 'Review not found'}), 404

        return jsonify(_serialize(review)), 200

    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Review fetch failed")
        return jsonify({'message': 'Error fetching review'}), 500


# ===== Uploaded video serving (FE-C1) =====
# ReviewCenter ka <video> pehle review.video_url (ek server filesystem
# path, ab sirf basename) ko seedha src banata tha — koi route uploads
# serve hi nahi karta tha, isliye nginx try_files HTML wapas deta tha
# aur video silently fail hota tha. Ye route us gap ko band karta hai.
# SECURITY (Phase 1/3 rules preserved):
# - JWT zaroori hai; <video> tag khud Bearer header nahi bhejta,
#   isliye frontend is route ko axios (blob) se fetch karta hai.
# - filename sirf basename ho sakta hai — koi '/' / '..' / traversal
#   nahi; sirf allowed video extensions serve hote hain.
# - Ownership: sirf tab serve hota hai jab caller ke paas ek review ho
#   jiski stored video_path isi filename par khatam hoti ho. Koi
#   owning review nahi (ya doosre user ka review) to 404 — taaki
#   arbitrary files enumerate/serve na hon, aur existence leak na ho.
# - Absolute server path kabhi response me nahi aata (SEC-M1).
@reviews_bp.route('/uploads/<filename>', methods=['GET'])
@jwt_required()
def get_upload(filename):
    try:
        uid = current_user_id()
        # Basename-only: traversal / server path yahan se aage nahi.
        if not filename or filename != os.path.basename(filename) \
                or filename in ('.', '..') \
                or os.path.splitext(filename)[1].lower() \
                not in Config.ALLOWED_VIDEO_EXTENSIONS:
            return jsonify({'message': 'Video not found'}), 404

        # Owning review caller ka hi hona chahiye. Stored video_path
        # absolute hai (e.g. /app/uploads/<uuid>.mp4), isliye suffix
        # match karo; exact-basename rows bhi cover karo.
        review = (Review.query.filter_by(user_id=uid, video_path=filename)
                  .first()
                  or Review.query.filter_by(user_id=uid)
                  .filter(Review.video_path.like(f'%/{filename}'))
                  .first())
        if review is None:
            return jsonify({'message': 'Video not found'}), 404

        upload_folder = os.path.abspath(Config.UPLOAD_FOLDER)
        path = os.path.abspath(os.path.join(upload_folder, filename))
        if not path.startswith(upload_folder + os.sep) \
                or not os.path.isfile(path):
            return jsonify({'message': 'Video not found'}), 404
        return send_file(path, as_attachment=False)
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Upload serve failed")
        return jsonify({'message': 'Error fetching video'}), 500


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
        uid = current_user_id()
        data = request.get_json() or {}

        review_type = data.get('review_type', 'LBW')
        validate_review_request(review_type, data.get('original_call'))

        # SEC-M1: client se video_path kabhi accept mat karo — stored
        # path injection tha (koi bhi arbitrary path store ho jata).
        review = Review(
            user_id=uid,
            video_path='',
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
        db.session.rollback()
        return jsonify({'message': str(e)}), 400
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Review request failed")
        return jsonify({'message': 'Error creating review'}), 500


@reviews_bp.route('/reviews/queue', methods=['GET'])
@jwt_required()
def review_queue():
    """
    N3: Review queue — pending/processing sabse pehle.
    ?status=pending ya ?match_id=1 se filter karo
    """
    try:
        # SEC-C3 read leak band: queue sirf apne reviews dikhata hai
        # (pehle sab users ke reviews aate the).
        uid = current_user_id()
        status = request.args.get('status')
        match_id = request.args.get('match_id', type=int)

        q = Review.query.filter_by(user_id=uid)
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

    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Review queue failed")
        return jsonify({'message': 'Error fetching queue'}), 500


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
        # SEC-C2: sirf owner hi complete kar sakta hai — get_review
        # wali pattern (non-owner par 404, existence leak nahi).
        uid = current_user_id()
        review = Review.query.filter_by(id=review_id, user_id=uid).first_or_404()
        data = request.get_json() or {}

        rec = data.get('ai_recommendation')
        conf = data.get('ai_confidence', 0)
        if rec not in ('OUT', 'NOT OUT', 'INCONCLUSIVE'):
            return jsonify({'message': 'Invalid recommendation'}), 400
        if isinstance(conf, bool) or not isinstance(conf, (int, float)):
            return jsonify({'message': 'ai_confidence numeric hona chahiye'}), 400

        ReviewWorkflow.transition(review, 'processing')
        review.ai_recommendation = rec
        review.ai_confidence = conf
        review.evidence = data.get('evidence', {})
        review.decision = rec
        review.confidence = conf

        # BE-H6: inconclusive sirf tab jab recommendation hi INCONCLUSIVE
        # hai. Pehle conf < 50 par bhi inconclusive ban jaata tha, jabki
        # recommendation 'OUT' hoti thi — phir confirm→accept OUT deta
        # tha, aur status (inconclusive) vs final decision (OUT) ek
        # doosre se contradict karte the. Kam confidence ab ai_confidence
        # me dikhta hai, status ko jhootha nahi banata.
        if rec == 'INCONCLUSIVE':
            ReviewWorkflow.transition(review, 'inconclusive')
        else:
            ReviewWorkflow.transition(review, 'completed')

        log_audit(uid, 'review.completed', 'review', review.id,
                  {'ai_recommendation': rec}, ip=request.remote_addr)
        db.session.commit()
        return jsonify(review.to_dict()), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 400
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Review complete failed")
        return jsonify({'message': 'Error completing review'}), 500


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
        # SEC-C2: sirf owner hi confirm kar sakta hai (non-owner: 404).
        uid = current_user_id()
        review = Review.query.filter_by(id=review_id, user_id=uid).first_or_404()
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
            # BE-H6: INCONCLUSIVE accept nahi ho sakta — wo valid final
            # decision hi nahi hai (pehle final_decision='INCONCLUSIVE'
            # lock ho jaata tha). Umpire ko reject/override karna hoga.
            if review.ai_recommendation in (None, 'INCONCLUSIVE'):
                return jsonify({'message': 'INCONCLUSIVE recommendation accept nahi ho sakti — reject ya override karo'}), 400
            final = review.ai_recommendation
        elif action == 'reject':
            # BE-H6: reject = original call wapas — lekin original_call
            # NULL ho to NOT OUT invent nahi karte (pehle wahi hota tha).
            if review.original_call is None:
                return jsonify({'message': 'Reject ke liye stored original_call zaroori hai'}), 400
            final = review.original_call
        else:  # override
            final = data.get('final_decision')
            if final not in ('OUT', 'NOT OUT'):
                return jsonify({'message': 'Override ke liye final_decision do'}), 400

        review.final_decision = final
        review.decision = final
        review.confirmed_by = uid
        review.confirmed_at = db.func.current_timestamp()
        review.confirmation_note = data.get('note', '')
        review.is_locked = True  # N11: lock!
        ReviewWorkflow.transition(review, 'confirmed')

        log_audit(uid, 'review.confirmed', 'review', review.id,
                  {'action': action, 'final_decision': final},
                  ip=request.remote_addr)
        db.session.commit()
        return jsonify(review.to_dict()), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 400
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Review confirm failed")
        return jsonify({'message': 'Error confirming review'}), 500


@reviews_bp.route('/reviews/<int:review_id>/retry', methods=['POST'])
@jwt_required()
def retry_review(review_id):
    """N3: Failed review ko wapas queue me dalo."""
    from core_processing.review_workflow import ReviewWorkflow
    try:
        # SEC-C2: sirf owner hi retry kar sakta hai (non-owner: 404).
        uid = current_user_id()
        review = Review.query.filter_by(id=review_id, user_id=uid).first_or_404()
        ReviewWorkflow.transition(review, 'pending')
        # BE-H6: retry par POORI AI state clear karo — pehle decision /
        # confidence stale reh jaate the aur pending review par purani
        # decision dikhti thi.
        review.ai_recommendation = None
        review.ai_confidence = None
        review.evidence = None
        review.decision = 'PENDING'
        review.confidence = None
        review.final_decision = None
        review.confirmed_by = None
        review.confirmation_note = None
        review.is_locked = False
        log_audit(uid, 'review.retried', 'review', review.id,
                  ip=request.remote_addr)
        db.session.commit()
        return jsonify(review.to_dict()), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 400
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Review retry failed")
        return jsonify({'message': 'Error retrying review'}), 500


# ===== Pitch Map / Over Summary (BE-H8) =====
# Pehle ye sirf library the — claimed POST /api/reviews/pitch-map aur
# /over-summary endpoints exist hi nahi karte the (404 milta tha).
# Ab ye stateless transforms hain: caller body me data deta hai, koi
# DB row read/write nahi hoti, isliye koi cross-tenant surface nahi
# hai (match_id se DB build karne wala variant deliberately nahi joda
# gaya — wo jode to owner filter zaroori hoga). PDF endpoint nahi hai:
# over-summary HTML report milta hai, jise library ka export_pdf()
# (weasyprint/pdfkit, optional deps) PDF me badal sakta hai.

def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


@reviews_bp.route('/reviews/pitch-map', methods=['POST'])
@jwt_required()
def pitch_map_endpoint():
    """POST /api/reviews/pitch-map
    Body: {"bowler_name": "Bumrah", "deliveries": [
        {"pitch_x": 2.5, "pitch_y": 0.1, "outcome": "dot",
         "speed_kmh": 135, "swing": null, "spin": null}, ...]}
    pitch_x: stumps se distance (meters, bowler ki taraf positive).
    pitch_y: lateral (meters, + = off side for RHB).
    outcome: dot | run | boundary | wicket | wide | noball.
    Response: {"bowler": str, "svg": str, "stats": {...}} (200),
    ya bad entry par 400."""
    from core_processing.pitch_map import PitchMap, OUTCOME_COLORS
    try:
        data = request.get_json() or {}
        deliveries = data.get('deliveries')
        if not isinstance(deliveries, list):
            return jsonify({'message': 'deliveries list zaroori hai'}), 400
        pm = PitchMap(bowler_name=data.get('bowler_name', 'Bowler'))
        for i, d in enumerate(deliveries):
            if not isinstance(d, dict) or not _is_number(d.get('pitch_x')) \
                    or not _is_number(d.get('pitch_y')):
                return jsonify({'message': f'deliveries[{i}] me numeric pitch_x/pitch_y zaroori hai'}), 400
            # BE-M6: pitch map 0-10 m ka hai — bahar ki value SVG se
            # bahar plot hoti thi (negative pitch_x Yorker ban jaata tha).
            if not (0 <= d['pitch_x'] <= 10):
                return jsonify({'message': f'deliveries[{i}] pitch_x 0-10 m ke andar hona chahiye'}), 400
            outcome = d.get('outcome', 'dot')
            if outcome not in OUTCOME_COLORS:
                return jsonify({'message': f'deliveries[{i}] outcome invalid: {outcome!r}'}), 400
            speed = d.get('speed_kmh')
            if speed is not None and not _is_number(speed):
                return jsonify({'message': f'deliveries[{i}] speed_kmh numeric hona chahiye'}), 400
            pm.add_delivery(pitch_x=d['pitch_x'], pitch_y=d['pitch_y'],
                            outcome=outcome, speed_kmh=speed,
                            swing=d.get('swing'), spin=d.get('spin'))
        return jsonify({'bowler': pm.bowler_name, 'svg': pm.to_svg(),
                        'stats': pm.get_stats()}), 200
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Pitch map failed")
        return jsonify({'message': 'Error building pitch map'}), 500


@reviews_bp.route('/reviews/over-summary', methods=['POST'])
@jwt_required()
def over_summary_endpoint():
    """POST /api/reviews/over-summary
    Body: {"over_number": 1, "bowler": "Bumrah", "batsman": "Kohli",
           "balls": [{"pitch_3d": [x, y, z] | null,
                      "decision": "OUT" | "NOT OUT" | ...,
                      "confidence": float,
                      "delivery_analysis": {"speed_kmh": float,
                                            "delivery_type": str},
                      "outcome": "dot" | "run" | "boundary" | "wicket" | "wide",
                      "runs": int, "line": str}, ...]}
    Response: {"summary": {...OverSummary.get_summary()...},
               "html": "<html>...ball-by-ball + pitch map SVG...</html>"} (200),
    ya bad entry par 400. HTML table me ab har row me header jitne
    (6) cells hote hain (BE-H8 row fix)."""
    from core_processing.over_summary import OverSummary
    try:
        data = request.get_json() or {}
        balls = data.get('balls')
        if not isinstance(balls, list):
            return jsonify({'message': 'balls list zaroori hai'}), 400
        over = OverSummary(over_number=data.get('over_number', 1),
                           bowler=data.get('bowler', 'Bowler'),
                           batsman=data.get('batsman', 'Batsman'))
        for i, b in enumerate(balls):
            if not isinstance(b, dict):
                return jsonify({'message': f'balls[{i}] dict hona chahiye'}), 400
            over.add_ball(b)
        return jsonify({'summary': over.get_summary(),
                        'html': over.to_html_report()}), 200
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Over summary failed")
        return jsonify({'message': 'Error building over summary'}), 500
