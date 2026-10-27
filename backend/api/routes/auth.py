import re

from flask import request, jsonify, Blueprint, current_app
from models.user import User
from models.security import RevokedToken
from extensions import db, limiter
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity, get_jwt,
)
from flask_limiter.util import get_remote_address
from api.routes.common import current_user_id

auth_bp = Blueprint('auth', __name__)

# SEC-H6: server-side password policy (pehle sirf frontend me >=6
# tha, API se bypass ho jata tha). Email format bhi server par check.
MIN_PASSWORD_LEN = 10
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _login_key():
    """SEC-H1: login bucket = IP + username. Sirf IP par key karne
    se ek user ke brute-force attempts sab users ka bucket kha
    jate; sirf username par key karne se attacker IP limit se bach
    jata. Dono milkar dono attack rokate hain."""
    data = request.get_json(silent=True) or {}
    username = data.get('username') or ''
    return f"login:{get_remote_address()}:{username}"


@auth_bp.route('/register', methods=['POST'])
@limiter.limit("10 per hour")  # spam registration roko
def register():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'message': 'Missing required fields'}), 400
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip()
        password = data.get('password') or ''
        if not username or not email or not password:
            return jsonify({'message': 'Missing required fields'}), 400
        if not _EMAIL_RE.match(email):
            return jsonify({'message': 'Invalid email format'}), 400
        if len(password) < MIN_PASSWORD_LEN:
            return jsonify({
                'message': f'Password kam se kam {MIN_PASSWORD_LEN} characters ka ho'
            }), 400

        # SEC-H6: enumeration oracle band — username/email alag-alag
        # batane ki jagah ek hi generic error. Status 400 hi rehta hai.
        if (User.query.filter_by(username=username).first()
                or User.query.filter_by(email=email).first()):
            return jsonify({'message': 'Registration failed'}), 400

        new_user = User(username=username, email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return jsonify({'message': 'User created successfully'}), 201

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Register failed")
        return jsonify({'message': 'Registration failed'}), 500


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute", key_func=_login_key)  # brute-force protection
def login():
    try:
        data = request.get_json(silent=True)
        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'message': 'Username and password required'}), 400

        user = User.query.filter_by(username=data['username']).first()

        # Login pehle se hi generic tha — user-exists vs wrong-password
        # ka farq kabhi mat batao.
        if user is None or not user.check_password(data['password']):
            return jsonify({'message': 'Invalid credentials'}), 401

        access_token = create_access_token(identity=str(user.id))
        return jsonify({
            'access_token': access_token,
            'user_id': user.id,
            'username': user.username
        }), 200

    except Exception:
        current_app.logger.exception("Login failed")
        return jsonify({'message': 'Login failed'}), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """SEC-H4: is token ka jti blocklist me daalo — logout ke baad
    token server-side bhi invalid ho jata hai (pehle sirf frontend
    localStorage se delete hota tha)."""
    jti = get_jwt()["jti"]
    db.session.add(RevokedToken(jti=jti, user_id=current_user_id()))
    db.session.commit()
    return jsonify({'message': 'Logged out'}), 200


@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def profile():
    try:
        user = User.query.get(current_user_id())

        if not user:
            return jsonify({'message': 'User not found'}), 404

        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': user.email
        }), 200

    except Exception:
        current_app.logger.exception("Profile fetch failed")
        return jsonify({'message': 'Error fetching profile'}), 500
