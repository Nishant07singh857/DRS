"""Shared helpers for Phase-1 security fixes.

current_user_id(): the single place that converts the JWT subject
back to an int. A token whose subject is not numeric (minted by an
older build, or a future identity scheme) previously raised
ValueError inside view try/excepts and surfaced as a generic 500
(SEC-L2). It now aborts with 401, which app.py renders as JSON.
"""

from flask import abort
from flask_jwt_extended import get_jwt_identity


def current_user_id():
    try:
        return int(get_jwt_identity())
    except (TypeError, ValueError):
        abort(401)
