"""Phase-1 security models (SEC-C4, SEC-H4).

RevokedToken: JWT blocklist for /auth/logout. A token whose jti is
in this table is rejected by the blocklist loader in app.py, so a
stolen token can be revoked instead of living until expiry.

TaskOwnership: task_id -> user_id binding written at upload time.
The task-status endpoint (app.py) requires this row to match the
caller; unknown task_ids return 404 (fail closed). This is durable
across processes because it lives in the shared database, unlike an
in-memory dict (which would break as soon as status polling hit a
different backend worker than the upload did).
"""

from extensions import db
from datetime import datetime


class RevokedToken(db.Model):
    __tablename__ = 'revoked_tokens'

    jti = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TaskOwnership(db.Model):
    __tablename__ = 'task_ownership'

    task_id = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
