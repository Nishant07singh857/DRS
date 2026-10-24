"""
Calibration API tests — `pytest backend/tests/test_calibration.py` se chalao.

Coverage: intrinsics/extrinsics save, status, DLT solve (synthetic
camera se — known P se points project karke), error cases, auth.
"""

import os
import sys

# Env vars app import se PEHLE — warna Config fail-fast karega.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/test_calib.db")
os.environ.setdefault("MAX_UPLOAD_MB", "5")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
import pytest

from app import create_app
from extensions import db


@pytest.fixture()
def app():
    # Purani test DB hatao taaki har run fresh ho
    if os.path.exists("/tmp/test_calib.db"):
        os.remove("/tmp/test_calib.db")
    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _auth_header(client):
    client.post("/api/auth/register",
                json={"username": "calib", "email": "c@c.com",
                      "password": "pass123"})
    res = client.post("/api/auth/login",
                      json={"username": "calib", "password": "pass123"})
    token = res.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_camera(client, h, name="Cam 1"):
    res = client.post("/api/cameras", json={"name": name}, headers=h)
    assert res.status_code == 201
    return res.get_json()["id"]


def _synthetic_correspondences(n=12, seed=7):
    """Known camera se 2D-3D pairs banao (DLT ko test karne ke liye)."""
    rnd = random.Random(seed)
    fx, fy, cx, cy = 800.0, 800.0, 320.0, 240.0
    img_pts, world_pts = [], []
    for _ in range(n):
        X = rnd.uniform(-2, 2)
        Y = rnd.uniform(-1, 1)
        Z = rnd.uniform(8, 12)  # camera ke saamne
        u = fx * X / Z + cx + rnd.uniform(-0.5, 0.5)
        v = fy * Y / Z + cy + rnd.uniform(-0.5, 0.5)
        img_pts.append([u, v])
        world_pts.append([X, Y, Z])
    return img_pts, world_pts


def test_intrinsics_extrinsics_status(client):
    h = _auth_header(client)
    cam_id = _make_camera(client, h)

    # Shuru me uncalibrated
    res = client.get(f"/api/calibration/camera/{cam_id}", headers=h)
    assert res.status_code == 200
    assert res.get_json()["calibrated"] is False

    # Intrinsics
    res = client.post(f"/api/calibration/camera/{cam_id}/intrinsics",
                      json={"focal_x": 800, "focal_y": 800,
                            "cx": 320, "cy": 240,
                            "distortion": [0.1, -0.05, 0, 0, 0]},
                      headers=h)
    assert res.status_code == 200
    assert res.get_json()["calibrated"] is False  # sirf intrinsics — abhi nahi

    # Extrinsics
    res = client.post(f"/api/calibration/camera/{cam_id}/extrinsics",
                      json={"R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                            "t": [0, 0, 5]},
                      headers=h)
    assert res.status_code == 200
    assert res.get_json()["calibrated"] is True

    # Status
    res = client.get(f"/api/calibration/camera/{cam_id}", headers=h)
    d = res.get_json()
    assert d["calibrated"] is True
    assert d["has_intrinsics"] is True
    assert d["has_extrinsics"] is True
    assert d["intrinsics"]["focal_x"] == 800
    assert d["extrinsics"]["t"] == [0, 0, 5]


def test_dlt_solve(client):
    """Known camera se banaye points par DLT — P recover hona chahiye."""
    h = _auth_header(client)
    cam_id = _make_camera(client, h, name="Cam DLT")

    img_pts, world_pts = _synthetic_correspondences(12)
    res = client.post("/api/calibration/point-correspondences",
                      json={"camera_id": cam_id,
                            "image_points": img_pts,
                            "world_points": world_pts},
                      headers=h)
    assert res.status_code == 200

    res = client.post("/api/calibration/solve",
                      json={"camera_id": cam_id}, headers=h)
    assert res.status_code == 200
    d = res.get_json()
    # Noise +-0.5px tha — reprojection error chhota hona chahiye
    assert d["reprojection_error_px"] < 2.0
    assert d["quality"] in ("excellent", "good")
    assert len(d["projection_matrix"]) == 3
    assert len(d["projection_matrix"][0]) == 4

    # Status me sab kuch dikhe
    res = client.get(f"/api/calibration/camera/{cam_id}", headers=h)
    d = res.get_json()
    assert d["calibrated"] is True
    assert d["n_correspondences"] == 12
    assert d["reprojection_error"] < 2.0
    # DLT se nikle intrinsics ~800/320/240 hone chahiye
    assert abs(d["intrinsics"]["focal_x"] - 800) < 30
    assert abs(d["intrinsics"]["cx"] - 320) < 30


def test_dlt_math_sanity():
    """RQ decomposition sahi hai: K@R == M aur R orthogonal."""
    import numpy as np
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from api.routes.calibration import _dlt_calibrate

    img_pts, world_pts = _synthetic_correspondences(10, seed=21)
    P, K, R, t, reproj = _dlt_calibrate(img_pts, world_pts)
    P, K, R = np.array(P), np.array(K), np.array(R)

    # K upper-triangular, R orthogonal.
    # (K normalize hota hai K[2,2]=1 par, isliye K@R scale tak P[:,:3] ke barabar)
    assert np.allclose(K, np.triu(K), atol=1e-6)
    assert np.allclose(R @ R.T, np.eye(3), atol=1e-6)
    KRn = (K @ R) / np.linalg.norm(K @ R)
    Mn = P[:, :3] / np.linalg.norm(P[:, :3])
    assert np.allclose(KRn, Mn, atol=1e-3) or np.allclose(KRn, -Mn, atol=1e-3)
    assert reproj < 2.0


def test_error_cases(client):
    h = _auth_header(client)

    # Galat camera
    res = client.get("/api/calibration/camera/9999", headers=h)
    assert res.status_code == 404
    assert "message" in res.get_json()

    res = client.post("/api/calibration/camera/9999/intrinsics",
                      json={"focal_x": 1, "focal_y": 1, "cx": 1, "cy": 1},
                      headers=h)
    assert res.status_code == 404

    # Kam points
    cam_id = _make_camera(client, h, name="Cam Err")
    res = client.post("/api/calibration/point-correspondences",
                      json={"camera_id": cam_id,
                            "image_points": [[1, 2]] * 3,
                            "world_points": [[1, 2, 3]] * 3},
                      headers=h)
    assert res.status_code == 400
    assert "message" in res.get_json()

    # Bina correspondences ke solve
    res = client.post("/api/calibration/solve",
                      json={"camera_id": cam_id}, headers=h)
    assert res.status_code == 400

    # Bina token ke — 401
    res = client.get(f"/api/calibration/camera/{cam_id}")
    assert res.status_code == 401
