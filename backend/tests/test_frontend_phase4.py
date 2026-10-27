"""
Phase-4 frontend backend-surface tests (QA report FE-C1).

GET /api/uploads/<filename>: JWT required, filename sanitised to a
basename with an allowed video extension, and served only when the
caller owns a review whose stored video_path ends in that filename.
Non-owner / unknown / traversal requests all get 404 (no existence
leak), and a successful response carries video bytes, never HTML.
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef01234567")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-0123456789abcdef01234567")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MAX_UPLOAD_MB", "5")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app import create_app, celery
from config import Config
from extensions import db, limiter
from models.review import Review
from models.user import User

PW = "StrongPass123"
# Minimal bytes that are not HTML — the point is content-type/bytes,
# not a playable container, so the test does not need a real codec.
VIDEO_BYTES = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64


@pytest.fixture()
def app():
    application = create_app()
    application.config["TESTING"] = True
    limiter.reset()
    celery.conf.update(
        task_always_eager=True,
        task_store_eager_result=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _user(client, username):
    assert client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@x.com",
              "password": PW},
    ).status_code == 201
    res = client.post(
        "/api/auth/login", json={"username": username, "password": PW})
    assert res.status_code == 200
    token = res.get_json()["access_token"]
    user = User.query.filter_by(username=username).first()
    return {"Authorization": f"Bearer {token}"}, user.id


def _owning_review(app, user_id, filename):
    # Stored video_path is absolute on disk (Phase-1/3 rule: the API
    # only ever exposes the basename); the file itself lives in the
    # real upload folder so send_file has something to return.
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    path = os.path.join(Config.UPLOAD_FOLDER, filename)
    with open(path, "wb") as f:
        f.write(VIDEO_BYTES)
    with app.app_context():
        review = Review(user_id=user_id, video_path=path,
                        decision="OUT", status="completed",
                        ai_recommendation="OUT")
        db.session.add(review)
        db.session.commit()
        return review.id, path


def test_uploads_requires_jwt(client, app):
    headers, uid = _user(client, "owner4")
    _owning_review(app, uid, "owner4-video.mp4")
    assert client.get("/api/uploads/owner4-video.mp4").status_code == 401


def test_uploads_owner_gets_video_bytes_not_html(client, app):
    headers, uid = _user(client, "owner4b")
    _owning_review(app, uid, "owner4b-video.mp4")
    res = client.get("/api/uploads/owner4b-video.mp4", headers=headers)
    assert res.status_code == 200
    assert res.data == VIDEO_BYTES
    assert b"<html" not in res.data.lower()
    assert res.content_type.startswith("video/")


def test_uploads_non_owner_gets_404(client, app):
    headers, uid = _user(client, "owner4c")
    _owning_review(app, uid, "owner4c-video.mp4")
    other_headers, _ = _user(client, "other4c")
    assert client.get("/api/uploads/owner4c-video.mp4",
                      headers=other_headers).status_code == 404


def test_uploads_unknown_file_gets_404(client):
    headers, _ = _user(client, "owner4d")
    assert client.get("/api/uploads/no-such-video.mp4",
                      headers=headers).status_code == 404


def test_uploads_traversal_and_wrong_extension_rejected(client):
    headers, _ = _user(client, "owner4e")
    for bad in ("..%2f..%2fetc%2fpasswd", "video.exe", "video.txt"):
        res = client.get(f"/api/uploads/{bad}", headers=headers)
        assert res.status_code == 404
