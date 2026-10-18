"""
Training API — StreetDRS spec module R.

Endpoints:
  POST /api/training/sessions          — session banao
  GET  /api/training/sessions          — list
  GET  /api/training/sessions/<id>     — detail + analytics
  POST /api/training/sessions/<id>/balls — ball metric add karo
  POST /api/training/sessions/<id>/complete — session khatam + report
  GET  /api/training/sessions/<id>/report — AI coach style report
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.training import TrainingSession, DeliveryMetric
from datetime import datetime

training_bp = Blueprint('training', __name__)


@training_bp.route('/training/sessions', methods=['POST'])
@jwt_required()
def create_session():
    data = request.get_json() or {}
    session = TrainingSession(
        user_id=int(get_jwt_identity()),
        player_id=data.get('player_id'),
        venue_id=data.get('venue_id'),
        session_type=data.get('session_type', 'bowling'),
        title=data.get('title', 'Training Session'),
        notes=data.get('notes', ''),
        target_deliveries=data.get('target_deliveries', 30),
        target_area=data.get('target_area'),
    )
    db.session.add(session)
    db.session.commit()
    return jsonify(session.to_dict()), 201


@training_bp.route('/training/sessions', methods=['GET'])
@jwt_required()
def list_sessions():
    user_id = int(get_jwt_identity())
    sessions = TrainingSession.query.filter_by(user_id=user_id)\
        .order_by(TrainingSession.created_at.desc()).limit(30).all()
    return jsonify([s.to_dict() for s in sessions]), 200


@training_bp.route('/training/sessions/<int:sid>/balls', methods=['POST'])
@jwt_required()
def add_ball_metric(sid):
    session = TrainingSession.query.get_or_404(sid)
    if session.status != 'active':
        return jsonify({'message': 'Session completed hai'}), 400

    data = request.get_json() or {}
    last = DeliveryMetric.query.filter_by(session_id=sid)\
        .order_by(DeliveryMetric.ball_number.desc()).first()
    ball_num = (last.ball_number + 1) if last else 1

    # Target hit check
    is_target = None
    if session.target_area and data.get('pitch_x') is not None:
        ta = session.target_area
        is_target = (ta.get('x_min', 0) <= data['pitch_x'] <= ta.get('x_max', 10) and
                     ta.get('y_min', -1) <= data.get('pitch_y', 0) <= ta.get('y_max', 1))

    metric = DeliveryMetric(
        session_id=sid, ball_number=ball_num,
        speed_kmh=data.get('speed_kmh'),
        pitch_x=data.get('pitch_x'), pitch_y=data.get('pitch_y'),
        length_zone=data.get('length_zone'), line_zone=data.get('line_zone'),
        swing=data.get('swing'), spin=data.get('spin'),
        is_target_hit=is_target,
        shot_angle=data.get('shot_angle'), shot_type=data.get('shot_type'),
        runs=data.get('runs', 0), timing=data.get('timing'),
    )
    db.session.add(metric)
    db.session.commit()
    return jsonify(metric.to_dict()), 201


@training_bp.route('/training/sessions/<int:sid>/report', methods=['GET'])
@jwt_required()
def session_report(sid):
    """R6: Training report + R2/R3 analytics."""
    session = TrainingSession.query.get_or_404(sid)
    metrics = DeliveryMetric.query.filter_by(session_id=sid)\
        .order_by(DeliveryMetric.ball_number).all()

    # Bowler analytics (R2)
    speeds = [m.speed_kmh for m in metrics if m.speed_kmh]
    lengths = {}
    targets_hit = 0
    for m in metrics:
        if m.length_zone:
            lengths[m.length_zone] = lengths.get(m.length_zone, 0) + 1
        if m.is_target_hit:
            targets_hit += 1

    # Batsman analytics (R3)
    shots = {}
    total_runs = 0
    for m in metrics:
        if m.shot_type:
            shots[m.shot_type] = shots.get(m.shot_type, 0) + 1
        total_runs += (m.runs or 0)

    n = len(metrics)
    report = {
        'session': session.to_dict(),
        'total_balls': n,
        'bowling': {
            'avg_speed': round(sum(speeds)/len(speeds), 1) if speeds else None,
            'max_speed': round(max(speeds), 1) if speeds else None,
            'min_speed': round(min(speeds), 1) if speeds else None,
            'length_distribution': lengths,
            'target_accuracy_pct': round(targets_hit/n*100, 1) if n else 0,
        },
        'batting': {
            'total_runs': total_runs,
            'shot_distribution': shots,
        },
        # AI Coach teaser (T)
        'insights': _generate_insights(metrics, speeds, lengths, targets_hit, n),
    }
    return jsonify(report), 200


def _generate_insights(metrics, speeds, lengths, targets_hit, n):
    """T: Rule-based AI coach insights."""
    insights = []
    if n == 0:
        return ["Abhi koi ball record nahi hui."]

    if speeds and len(speeds) >= 5:
        avg = sum(speeds) / len(speeds)
        if avg < 120:
            insights.append(f"Average speed {avg:.0f} km/h hai — pace badhane par kaam karo.")
        elif avg > 140:
            insights.append(f"Excellent pace! {avg:.0f} km/h average.")

    if lengths:
        good_pct = lengths.get('Good length', 0) / n * 100
        if good_pct < 40:
            insights.append(f"Good length sirf {good_pct:.0f}% — consistency par focus karo (target 60%+).")
        else:
            insights.append(f"Good length {good_pct:.0f}% — bahut badhiya control!")

    if n >= 5:
        acc = targets_hit / n * 100
        if acc < 50:
            insights.append(f"Target accuracy {acc:.0f}% — line/length drill karo.")

    # Speed consistency
    if speeds and len(speeds) >= 5:
        spread = max(speeds) - min(speeds)
        if spread > 15:
            insights.append(f"Speed me {spread:.0f} km/h ka gap — rhythm consistent rakho.")

    return insights if insights else ["Solid session! Aise hi continue karo."]


@training_bp.route('/training/sessions/<int:sid>/complete', methods=['POST'])
@jwt_required()
def complete_session(sid):
    session = TrainingSession.query.get_or_404(sid)
    session.status = 'completed'
    session.completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify(session.to_dict()), 200
