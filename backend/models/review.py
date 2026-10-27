import os

from extensions import db
from datetime import datetime

class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    video_path = db.Column(db.String(255), nullable=False)
    decision = db.Column(db.String(50), nullable=False)
    confidence = db.Column(db.Float)
    analysis_data = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # --- Umpire Control Center (N) ---
    # Review type: LBW/EDGE/RUNOUT/STUMPING/WIDE/NOBALL/BOUNDARY
    review_type = db.Column(db.String(20), default='LBW')
    # Queue state: pending/processing/completed/failed/inconclusive/confirmed
    status = db.Column(db.String(20), default='pending')

    # Match context (optional links)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'))
    delivery_id = db.Column(db.Integer, db.ForeignKey('deliveries.id'))

    # Decision workflow (N8/N9)
    original_call = db.Column(db.String(20))  # on-field umpire: OUT/NOT OUT
    ai_recommendation = db.Column(db.String(20))  # AI: OUT/NOT OUT/INCONCLUSIVE
    ai_confidence = db.Column(db.Float)
    final_decision = db.Column(db.String(20))  # third umpire ka final

    # Human confirmation (N9/N11)
    confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    confirmed_at = db.Column(db.DateTime)
    confirmation_note = db.Column(db.String(500))  # kyun override kiya?
    is_locked = db.Column(db.Boolean, default=False)  # N11: lock ke baad no change

    # Evidence (N8)
    evidence = db.Column(db.JSON)  # pitching, impact, trajectory, audio

    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def to_dict(self):
        # BE-H9: YEHI ek serializer hai — list/detail (reviews.py
        # _serialize) aur request/complete/confirm/retry/queue sab isi
        # ko use karte hain, isliye koi field kisi endpoint par gayab
        # nahi hoti (pehle list/detail me delivery_id nahi tha, aur
        # baaki me video_url nahi tha).
        video_name = (os.path.basename(self.video_path)
                      if self.video_path else self.video_path)
        return {
            'id': self.id,
            'user_id': self.user_id,
            # SEC-M1: never disclose the absolute server path — only
            # the file identifier (basename) leaves the server.
            'video_path': video_name,
            'video_url': video_name,
            'decision': self.decision,
            'confidence': self.confidence,
            'analysis_data': self.analysis_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            # Umpire workflow
            'review_type': self.review_type,
            'status': self.status,
            'match_id': self.match_id,
            'delivery_id': self.delivery_id,
            'original_call': self.original_call,
            'ai_recommendation': self.ai_recommendation,
            'ai_confidence': self.ai_confidence,
            'final_decision': self.final_decision,
            'confirmed_by': self.confirmed_by,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'confirmation_note': self.confirmation_note,
            'is_locked': self.is_locked,
            'evidence': self.evidence,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f'<Review {self.id} - {self.review_type} - {self.status}>'
