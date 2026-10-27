"""
API + pipeline tests — `pytest backend/tests/test_api.py` se chalao.

Coverage: auth flow, upload validation, video processing task (eager Celery).
DB: in-memory SQLite. Broker ki zaroorat nahi (eager mode).
"""

import io
import os
import sys

# Env vars app import se PEHLE set hon — warna Config fail-fast karega.
# DATABASE_URL=sqlite se test me Postgres driver ki zaroorat nahi.
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef01234567")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-0123456789abcdef01234567")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MAX_UPLOAD_MB", "5")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app import create_app, celery
from extensions import db, limiter


@pytest.fixture()
def app():
    application = create_app()
    limiter.reset()
    application.config["TESTING"] = True
    # Broker ke bina task turant in-process chale;
    # result backend memory me taaki Redis ki zaroorat na pade
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


def _auth_header(client):
    client.post(
        "/api/auth/register",
        json={"username": "tester", "email": "t@test.com", "password": "StrongPass123"},
    )
    res = client.post(
        "/api/auth/login", json={"username": "tester", "password": "StrongPass123"}
    )
    token = res.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_login_profile(client):
    assert client.post(
        "/api/auth/register",
        json={"username": "u1", "email": "u1@x.com", "password": "StrongPass123"},
    ).status_code == 201

    res = client.post(
        "/api/auth/login", json={"username": "u1", "password": "StrongPass123"}
    )
    assert res.status_code == 200
    assert "access_token" in res.get_json()

    res = client.get(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {res.get_json()['access_token']}"},
    )
    assert res.status_code == 200
    assert res.get_json()["username"] == "u1"


def test_register_duplicate_username(client):
    client.post(
        "/api/auth/register",
        json={"username": "u2", "email": "u2@x.com", "password": "StrongPass123"},
    )
    res = client.post(
        "/api/auth/register",
        json={"username": "u2", "email": "other@x.com", "password": "StrongPass123"},
    )
    assert res.status_code == 400


def test_login_wrong_password(client):
    client.post(
        "/api/auth/register",
        json={"username": "u3", "email": "u3@x.com", "password": "StrongPass123"},
    )
    res = client.post(
        "/api/auth/login", json={"username": "u3", "password": "WrongPass123"}
    )
    assert res.status_code == 401


def test_profile_needs_auth(client):
    assert client.get("/api/auth/profile").status_code == 401


def test_upload_no_file(client):
    headers = _auth_header(client)
    assert client.post("/api/analysis/upload", headers=headers).status_code == 400


def test_upload_bad_extension_rejected(client):
    headers = _auth_header(client)
    data = {"video": (io.BytesIO(b"not a video"), "evil.exe")}
    res = client.post(
        "/api/analysis/upload", headers=headers, data=data,
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert "Invalid file type" in res.get_json()["message"]


def test_upload_too_large_rejected(client):
    headers = _auth_header(client)
    big = io.BytesIO(b"x" * (6 * 1024 * 1024))  # 6MB > 5MB test limit
    data = {"video": (big, "big.mp4")}
    res = client.post(
        "/api/analysis/upload", headers=headers, data=data,
        content_type="multipart/form-data",
    )
    assert res.status_code == 413


def _make_test_video(path, frames=30):
    """Synthetic MP4: kala background, safed ghumta circle (nakli ball)."""
    import cv2
    import numpy as np

    writer = cv2.VideoWriter(
        path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240)
    )
    for i in range(frames):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cx = 20 + i * 9
        cv2.circle(frame, (cx, 120), 12, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def test_video_task_runs_end_to_end(client, tmp_path, monkeypatch):
    """Poori pipeline: upload -> eager Celery task -> DB me review.

    YOLO inference ko stub karte hain (deterministic, torch-free) —
    test task ka DB + decision logic karta hai, ultralytics ka nahi.
    """
    import tasks as tasks_module
    from models.review import Review

    class FakeTracker:
        def track(self, frame):
            # Stumps ki taraf jaati ball (320px wide frame me) — BE-C1:
            # LBW pitching ab BOUNCE point se judge hoti hai, isliye
            # synthetic trajectory me asli bounce hona chahiye (flat
            # line par koi bounce nahi hota, to wo INCONCLUSIVE hoti).
            # Bounce i=8 par (x=104, y=180, ground), phir ball pad tak
            # jaati hai (impact x=160, in line; stumps zone 128-192).
            ys = [60, 75, 90, 105, 120, 135, 150, 165,
                  180, 170, 162, 156, 152, 150, 149, 148]
            traj = [(40 + i * 8, ys[i]) for i in range(16)]
            return {"ball": (160, 148), "trajectory": traj,
                    "pad": None, "bat": None}

    monkeypatch.setattr(tasks_module, "tracker", FakeTracker())
    headers = _auth_header(client)
    video_path = str(tmp_path / "test.mp4")
    _make_test_video(video_path)

    with open(video_path, "rb") as f:
        data = {"video": (f, "test.mp4")}
        res = client.post(
            "/api/analysis/upload", headers=headers, data=data,
            content_type="multipart/form-data",
        )
    assert res.status_code == 202
    task_id = res.get_json()["task_id"]

    # Eager mode me task turant chal chuka hai
    result = celery.AsyncResult(task_id)
    assert result.state == "SUCCESS"
    payload = result.result
    assert payload["status"] == "SUCCESS"
    assert payload["total_frames_processed"] == 30
    # Deterministic decision + DB write verify karo
    assert payload["result"]["final_decision"] == "OUT"
    # Visualization coordinates maujood hain
    viz = payload["result"]
    assert viz["pitch_point"] and viz["impact_point"]
    assert len(viz["trajectory"]) > 0
    assert len(viz["predicted_path"]) > 0
    assert viz["frame_width"] == 320
    assert Review.query.count() == 1
    assert Review.query.first().decision == "OUT"
    # SEC-C4: upload ne task_id -> user_id binding likhi hai.
    from models.security import TaskOwnership
    owner = TaskOwnership.query.filter_by(task_id=task_id).first()
    assert owner is not None
    assert owner.user_id == Review.query.first().user_id


def test_reviews_pagination_shape(client):
    headers = _auth_header(client)
    res = client.get("/api/reviews?page=1&per_page=10", headers=headers)
    assert res.status_code == 200
    body = res.get_json()
    assert set(body.keys()) == {"items", "page", "per_page", "total", "pages"}
