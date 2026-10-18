"""
Training Mode — StreetDRS spec module R.

Doosra product mode: bowling/batting practice analytics.
- TrainingSession: ek practice session
- DeliveryMetric: har ball ka data (speed, line, length, shot)
"""

from extensions import db
from datetime import datetime


class TrainingSession(db.Model):
    """Ek training session."""
    __tablename__ = 'training_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'))
    venue_id = db.Column(db.Integer, db.ForeignKey('venues.id'))

    session_type = db.Column(db.String(20), default='bowling')  # bowling/batting
    title = db.Column(db.String(200))
    notes = db.Column(db.Text)

    # Config
    target_deliveries = db.Column(db.Integer, default=30)
    target_area = db.Column(db.JSON)  # {x_min, x_max, y_min, y_max} for accuracy

    status = db.Column(db.String(20), default='active')  # active/completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    deliveries = db.relationship('DeliveryMetric', backref='session', lazy=True,
                                 cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'session_type': self.session_type,
            'title': self.title, 'target_deliveries': self.target_deliveries,
            'status': self.status,
            'deliveries_count': len(self.deliveries),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class DeliveryMetric(db.Model):
    """Training me har ball ka metric."""
    __tablename__ = 'delivery_metrics'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('training_sessions.id'),
                           nullable=False)
    ball_number = db.Column(db.Integer, nullable=False)

    # Bowler metrics
    speed_kmh = db.Column(db.Float)
    pitch_x = db.Column(db.Float)  # stumps se distance (m)
    pitch_y = db.Column(db.Float)  # lateral (m)
    length_zone = db.Column(db.String(20))  # Yorker/Full/Good/Short
    line_zone = db.Column(db.String(30))  # Off stump/Middle/Leg etc.
    swing = db.Column(db.String(20))
    spin = db.Column(db.String(20))
    is_target_hit = db.Column(db.Boolean)  # target area me gira?

    # Batsman metrics
    shot_angle = db.Column(db.Float)  # wagon wheel ke liye
    shot_type = db.Column(db.String(30))  # Cover drive/Pull/etc.
    runs = db.Column(db.Integer, default=0)
    timing = db.Column(db.String(20))  # perfect/good/early/late/miss

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'ball_number': self.ball_number,
            'speed_kmh': self.speed_kmh,
            'pitch_x': self.pitch_x, 'pitch_y': self.pitch_y,
            'length_zone': self.length_zone, 'line_zone': self.line_zone,
            'is_target_hit': self.is_target_hit,
            'shot_angle': self.shot_angle, 'shot_type': self.shot_type,
            'runs': self.runs, 'timing': self.timing,
        }
