"""
Notifications & Audit — StreetDRS spec modules W + X.

W: Review alerts, camera alerts, system warnings
X: Audit logs — kaunne kya change kiya, kab
"""

from extensions import db
from datetime import datetime


class Notification(db.Model):
    """W: System alerts."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # W1-W5: review/camera/sync/storage/processing
    category = db.Column(db.String(30), nullable=False)
    severity = db.Column(db.String(10), default='info')  # info/warning/critical
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)

    # Link (optional)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'))
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id'))

    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'category': self.category,
            'severity': self.severity, 'title': self.title,
            'message': self.message, 'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    """X9: Har important action ka record."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50), nullable=False)  # review.confirmed, score.corrected
    entity_type = db.Column(db.String(30))  # review, delivery, match
    entity_id = db.Column(db.Integer)
    details = db.Column(db.JSON)  # purana vs naya value
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id, 'action': self.action,
            'entity_type': self.entity_type, 'entity_id': self.entity_id,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


def log_audit(user_id, action, entity_type=None, entity_id=None,
              details=None, ip=None):
    """X: Audit entry banao."""
    entry = AuditLog(
        user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        details=details or {}, ip_address=ip,
    )
    db.session.add(entry)
    return entry


def notify(user_id, category, title, message, severity='info',
           match_id=None, review_id=None):
    """W: Notification bhejo."""
    n = Notification(
        user_id=user_id, category=category, title=title,
        message=message, severity=severity,
        match_id=match_id, review_id=review_id,
    )
    db.session.add(n)
    return n
