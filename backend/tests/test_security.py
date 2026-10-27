"""
Phase-1 security regression tests (QA report SEC-C1..C5, SEC-H1/H4/H5/H6).

Coverage: rate-limit 429, cross-user 404 on every endpoint touched
by the Phase-1 ownership fix, task-status auth + ownership,
logout revocation, password policy, registration enumeration,
placeholder-secret rejection, JWT expiry config.

DB: in-memory SQLite. Limiter buckets are reset per test because
the in-memory limiter is a process-global singleton.
"""

import io
import os
import sys
from datetime import timedelta

os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef01234567")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-0123456789abcdef01234567")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MAX_UPLOAD_MB", "5")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app import create_app, celery
from extensions import db, limiter

PW = "StrongPass123"


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
    return {"Authorization": f"Bearer {res.get_json()['access_token']}"}


def _review(client, headers):
    res = client.post(
        "/api/reviews/request",
        json={"review_type": "LBW", "original_call": "OUT",
              "video_path": "/app/uploads/should-be-ignored.mp4"},
        headers=headers)
    assert res.status_code == 201
    return res.get_json()["id"]


def _team(client, headers, name="Team A"):
    res = client.post("/api/teams", json={"name": name}, headers=headers)
    assert res.status_code == 201
    return res.get_json()["id"]


def _match(client, headers):
    ta = _team(client, headers, "Team A")
    tb = _team(client, headers, "Team B")
    res = client.post("/api/matches", json={
        "title": "M1", "team_a_id": ta, "team_b_id": tb}, headers=headers)
    assert res.status_code == 201
    return res.get_json()["id"]


def _camera(client, headers):
    res = client.post("/api/cameras", json={"name": "Cam 1"}, headers=headers)
    assert res.status_code == 201
    return res.get_json()["id"]


def _session(client, headers):
    res = client.post("/api/training/sessions", json={},
                      headers=headers)
    assert res.status_code == 201
    return res.get_json()["id"]


# --- SEC-C1 / SEC-H1: rate limiting actually enforces ---

def test_login_rate_limit_returns_429(client):
    # NOTE: _user() ki successful login bhi isi username bucket me
    # ginti hoti hai (1), isliye 4 galat attempts (total 5) ke baad
    # agla attempt 6th hota hai aur 429 deta hai.
    _user(client, "rluser")
    for _ in range(4):
        assert client.post(
            "/api/auth/login",
            json={"username": "rluser", "password": "WrongPass123"},
        ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"username": "rluser", "password": "WrongPass123"},
    ).status_code == 429


# --- SEC-C2: umpire actions are owner-only ---

def test_cross_user_review_complete_confirm_retry_404(client):
    a, b = _user(client, "alice"), _user(client, "bob")
    rid = _review(client, a)
    # Bob can do none of these on Alice's review.
    assert client.post(f"/api/reviews/{rid}/complete",
                       json={"ai_recommendation": "OUT", "ai_confidence": 90},
                       headers=b).status_code == 404
    assert client.post(f"/api/reviews/{rid}/retry", json={}, headers=b).status_code == 404
    # Alice completes, then Bob still cannot confirm.
    assert client.post(f"/api/reviews/{rid}/complete",
                       json={"ai_recommendation": "OUT", "ai_confidence": 90},
                       headers=a).status_code == 200
    assert client.post(f"/api/reviews/{rid}/confirm",
                       json={"action": "accept"}, headers=b).status_code == 404
    assert client.post(f"/api/reviews/{rid}/confirm",
                       json={"action": "accept"}, headers=a).status_code == 200


def test_cross_user_review_read_404(client):
    a, b = _user(client, "alice"), _user(client, "bob")
    rid = _review(client, a)
    assert client.get(f"/api/reviews/{rid}", headers=b).status_code == 404
    assert client.get("/api/reviews/queue", headers=b).get_json() == []


# --- SEC-C3: systemic IDOR closed on every touched endpoint ---

def test_cross_user_matches_teams_404(client):
    a, b = _user(client, "alice"), _user(client, "bob")
    tid = _team(client, a)
    assert client.post(f"/api/teams/{tid}/players",
                       json={"name": "P1"}, headers=b).status_code == 404
    mid = _match(client, a)
    assert client.get(f"/api/matches/{mid}", headers=b).status_code == 404
    assert client.post(f"/api/matches/{mid}/toss",
                       json={"toss_winner_id": 1, "toss_choice": "bat"},
                       headers=b).status_code == 404
    assert client.get("/api/matches", headers=b).get_json() == []
    assert len(client.get("/api/matches", headers=a).get_json()) == 1


def test_cross_user_training_404(client):
    a, b = _user(client, "alice"), _user(client, "bob")
    sid = _session(client, a)
    assert client.post(f"/api/training/sessions/{sid}/balls",
                       json={}, headers=b).status_code == 404
    assert client.get(f"/api/training/sessions/{sid}/report",
                      headers=b).status_code == 404
    assert client.post(f"/api/training/sessions/{sid}/complete",
                       json={}, headers=b).status_code == 404
    assert client.post(f"/api/training/sessions/{sid}/balls",
                       json={}, headers=a).status_code == 201


def test_cross_user_camera_calibration_404(client):
    a, b = _user(client, "alice"), _user(client, "bob")
    cam = _camera(client, a)
    assert client.post(f"/api/cameras/{cam}/heartbeat",
                       json={}, headers=b).status_code == 404
    assert client.post(f"/api/cameras/{cam}/status",
                       json={"status": "offline"}, headers=b).status_code == 404
    assert client.post(f"/api/calibration/camera/{cam}/intrinsics",
                       json={"focal_x": 800, "focal_y": 800,
                             "cx": 320, "cy": 240}, headers=b).status_code == 404
    assert client.post(f"/api/calibration/camera/{cam}/intrinsics",
                       json={"focal_x": 800, "focal_y": 800,
                             "cx": 320, "cy": 240}, headers=a).status_code == 200


def test_cross_user_replay_audit_isolation(client):
    a, b = _user(client, "alice"), _user(client, "bob")
    res = client.post("/api/replay/bookmarks",
                      json={"bookmark_type": "wicket", "timestamp_s": 12.5},
                      headers=a)
    assert res.status_code == 201
    assert client.get("/api/replay/bookmarks", headers=b).get_json() == []
    assert len(client.get("/api/replay/bookmarks", headers=a).get_json()) == 1
    # Alice's camera.registered audit row is not visible to Bob.
    _camera(client, a)
    assert client.get("/api/audit", headers=b).get_json() == []
    assert len(client.get("/api/audit", headers=a).get_json()) >= 1


def test_review_request_ignores_client_video_path(client):
    """SEC-M1: client-supplied video_path must not be stored."""
    a = _user(client, "alice")
    rid = _review(client, a)
    res = client.get(f"/api/reviews/{rid}", headers=a)
    assert "/app/" not in (res.get_json()["video_url"] or "")


# --- SEC-C4: task status requires JWT + ownership ---

def test_task_status_auth_and_ownership(client):
    """SEC-C4: status endpoint needs JWT + ownership.

    NOTE: no video task is run here on purpose. The eager Celery
    task's Flask context follows the first app that ran a task in
    this pytest process (a pre-existing harness quirk — production
    has a single app instance), so a second video task under a
    fresh fixture app is order-dependent. The upload -> ownership
    write itself is asserted in test_api's video test; here the
    endpoint logic is tested with a directly inserted binding row.
    """
    from models.security import TaskOwnership

    a, b = _user(client, "alice"), _user(client, "bob")
    db.session.add(TaskOwnership(task_id="task-123", user_id=1))
    db.session.commit()

    assert client.get("/api/tasks/task-123/status").status_code == 401
    assert client.get("/api/tasks/task-123/status",
                      headers=b).status_code == 404
    assert client.get("/api/tasks/does-not-exist/status",
                      headers=a).status_code == 404
    res = client.get("/api/tasks/task-123/status", headers=a)
    assert res.status_code == 200
    # Unknown to Celery, but owned: PENDING, no result leak.
    assert res.get_json()["state"] == "PENDING"


# --- SEC-H4/H5/H6: tokens, secrets, passwords, enumeration ---

def test_logout_revokes_token(client):
    a = _user(client, "alice")
    assert client.post("/api/auth/logout", headers=a).status_code == 200
    assert client.get("/api/auth/profile", headers=a).status_code == 401


def test_jwt_expiry_is_explicit(app):
    assert app.config["JWT_ACCESS_TOKEN_EXPIRES"] == timedelta(hours=1)


def test_register_password_policy_and_generic_duplicate(client):
    assert client.post("/api/auth/register", json={
        "username": "w1", "email": "w1@x.com", "password": "short",
    }).status_code == 400
    assert client.post("/api/auth/register", json={
        "username": "w2", "email": "w2@x.com", "password": "",
    }).status_code == 400
    assert client.post("/api/auth/register", json={
        "username": "w3", "email": "not-an-email", "password": PW,
    }).status_code == 400
    assert client.post("/api/auth/register", json={
        "username": "dup", "email": "dup@x.com", "password": PW,
    }).status_code == 201
    res = client.post("/api/auth/register", json={
        "username": "dup", "email": "other@x.com", "password": PW,
    })
    assert res.status_code == 400
    # Generic: must not say which field already exists.
    assert "already exists" not in res.get_json()["message"]


def test_placeholder_and_short_secrets_rejected(monkeypatch):
    from config import _required

    monkeypatch.setenv("SECRET_KEY", "change-me-to-a-long-random-string")
    with pytest.raises(RuntimeError):
        _required("SECRET_KEY", min_length=32)
    monkeypatch.setenv("SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError):
        _required("SECRET_KEY", min_length=32)
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    assert _required("SECRET_KEY", min_length=32) == "a" * 40
