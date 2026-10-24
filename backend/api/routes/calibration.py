"""
Calibration API — StreetDRS spec module G.

Multi-camera Hawk-Eye ke liye har camera calibrate hona chahiye:
  G1: Intrinsics — focal length, principal point, distortion
  G2: Extrinsics — camera ki position/orientation (R, t)
  G3: Point correspondences — 2D image points + known 3D world points
      (stumps, crease marks — pitch ke fixed points)
  G4: DLT solve — correspondences se projection matrix nikalo

Calibration ke bina triangulation galat hoga — ye poore 3D system
ki neev hai.
"""

import math

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from extensions import db
from models.camera import Camera, CalibrationProfile

calibration_bp = Blueprint('calibration', __name__)

MIN_CORRESPONDENCES = 6  # DLT ke liye kam se kam 6 points


def _get_profile(camera_id):
    """Camera ka profile lao, nahi hai to banao."""
    cam = Camera.query.get(camera_id)
    if not cam:
        return None, None
    prof = cam.calibration_profile
    if not prof:
        prof = CalibrationProfile(camera_id=cam.id, data={})
        db.session.add(prof)
        db.session.flush()
    return cam, prof


def _update_data(prof, **fields):
    """profile.data me fields merge karo (naya dict assign — SQLAlchemy tracking ke liye)."""
    data = dict(prof.data or {})
    data.update(fields)
    prof.data = data
    prof.is_calibrated = bool(
        data.get('projection_matrix') or
        (data.get('intrinsics') and data.get('extrinsics')))
    db.session.commit()


# ---------------------------------------------------------
# G1: Intrinsics
# ---------------------------------------------------------
@calibration_bp.route('/calibration/camera/<int:cam_id>/intrinsics', methods=['POST'])
@jwt_required()
def save_intrinsics(cam_id):
    """Camera ka lens calibration save karo."""
    cam, prof = _get_profile(cam_id)
    if not cam:
        return jsonify({'message': 'Camera nahi mili'}), 404

    data = request.get_json() or {}
    # focal_x/focal_y ya single focal_length dono chalenge
    fx = data.get('focal_x', data.get('focal_length'))
    fy = data.get('focal_y', data.get('focal_length'))
    cx = data.get('cx', data.get('principal_x'))
    cy = data.get('cy', data.get('principal_y'))
    if fx is None or fy is None or cx is None or cy is None:
        return jsonify({'message': 'focal_x, focal_y, cx, cy zaroori hain'}), 400
    try:
        fx, fy, cx, cy = float(fx), float(fy), float(cx), float(cy)
    except (TypeError, ValueError):
        return jsonify({'message': 'Intrinsics numbers hone chahiye'}), 400
    if fx <= 0 or fy <= 0:
        return jsonify({'message': 'Focal length positive honi chahiye'}), 400

    distortion = data.get('distortion', [0, 0, 0, 0, 0])
    if len(distortion) != 5:
        return jsonify({'message': 'distortion me 5 coeffs chahiye [k1,k2,p1,p2,k3]'}), 400

    _update_data(prof, intrinsics={
        'focal_x': fx, 'focal_y': fy,
        'cx': cx, 'cy': cy,
        'distortion': [float(d) for d in distortion],
        'image_width': data.get('image_width'),
        'image_height': data.get('image_height'),
    })
    return jsonify({'message': 'Intrinsics save ho gaye',
                    'camera_id': cam_id,
                    'calibrated': prof.is_calibrated}), 200


# ---------------------------------------------------------
# G2: Extrinsics
# ---------------------------------------------------------
@calibration_bp.route('/calibration/camera/<int:cam_id>/extrinsics', methods=['POST'])
@jwt_required()
def save_extrinsics(cam_id):
    """Camera ki pose (rotation R + translation t) save karo."""
    cam, prof = _get_profile(cam_id)
    if not cam:
        return jsonify({'message': 'Camera nahi mili'}), 404

    data = request.get_json() or {}
    R = data.get('R', data.get('rotation'))
    t = data.get('t', data.get('translation'))
    if R is None or t is None:
        return jsonify({'message': 'R (3x3) aur t ([x,y,z]) zaroori hain'}), 400
    if len(R) != 3 or any(len(row) != 3 for row in R):
        return jsonify({'message': 'R 3x3 matrix honi chahiye'}), 400
    if len(t) != 3:
        return jsonify({'message': 't me 3 values chahiye [x,y,z]'}), 400
    try:
        R = [[float(v) for v in row] for row in R]
        t = [float(v) for v in t]
    except (TypeError, ValueError):
        return jsonify({'message': 'R aur t me numbers hone chahiye'}), 400

    _update_data(prof, extrinsics={'R': R, 't': t})
    return jsonify({'message': 'Extrinsics save ho gaye',
                    'camera_id': cam_id,
                    'calibrated': prof.is_calibrated}), 200


# ---------------------------------------------------------
# G3: Point correspondences
# ---------------------------------------------------------
@calibration_bp.route('/calibration/point-correspondences', methods=['POST'])
@jwt_required()
def save_correspondences():
    """
    2D-3D point pairs save karo.
    Body: {camera_id, image_points: [[u,v]...], world_points: [[X,Y,Z]...]}
    World points pitch ke known points hote hain — stump tops,
    crease ends (pitch 20.12m, stumps 71.1cm — fixed geometry!).
    """
    data = request.get_json() or {}
    cam_id = data.get('camera_id')
    img_pts = data.get('image_points')
    world_pts = data.get('world_points')
    if not cam_id or img_pts is None or world_pts is None:
        return jsonify({'message': 'camera_id, image_points, world_points zaroori hain'}), 400

    cam, prof = _get_profile(cam_id)
    if not cam:
        return jsonify({'message': 'Camera nahi mili'}), 404

    if len(img_pts) != len(world_pts):
        return jsonify({'message': 'image_points aur world_points ki ginti barabar ho'}), 400
    if len(img_pts) < MIN_CORRESPONDENCES:
        return jsonify({'message': f'DLT ke liye kam se kam {MIN_CORRESPONDENCES} points chahiye'}), 400
    if any(len(p) != 2 for p in img_pts) or any(len(p) != 3 for p in world_pts):
        return jsonify({'message': 'image_points [u,v] aur world_points [X,Y,Z] format me hon'}), 400

    _update_data(prof, correspondences={
        'image_points': [[float(a), float(b)] for a, b in img_pts],
        'world_points': [[float(a), float(b), float(c)] for a, b, c in world_pts],
        'n_points': len(img_pts),
    })
    return jsonify({'message': f'{len(img_pts)} correspondences save ho gayin',
                    'camera_id': cam_id}), 200


# ---------------------------------------------------------
# G4: DLT solve
# ---------------------------------------------------------
def _dlt_calibrate(image_points, world_points):
    """
    Direct Linear Transform — 2D-3D pairs se 3x4 projection matrix P.

    Har pair se 2 equations: A @ p = 0 (12 unknowns).
    SVD ka sabse chhota singular vector = solution.
    Phir RQ decomposition se K, R, t nikalo.
    Returns: (P, K, R, t, reprojection_error_px)
    """
    import numpy as np

    n = len(image_points)
    if n < 6:
        raise ValueError('DLT ke liye kam se kam 6 points chahiye')

    W = np.array(world_points, dtype=float)
    # Coplanar points se poora P nahi nikalta — 3D me phaile points chahiye
    _, s_vals, _ = np.linalg.svd(W - W.mean(axis=0))
    if s_vals[2] < 1e-6 * s_vals[0]:
        raise ValueError('Points lagbhag ek hi plane me hain — 3D me phaile points do')

    A = []
    for (u, v), (X, Y, Z) in zip(image_points, world_points):
        A.append([-X, -Y, -Z, -1, 0, 0, 0, 0, u*X, u*Y, u*Z, u])
        A.append([0, 0, 0, 0, -X, -Y, -Z, -1, v*X, v*Y, v*Z, v])
    A = np.array(A, dtype=float)

    _, _, Vt = np.linalg.svd(A)
    P = Vt[-1].reshape(3, 4)

    # Sign fix: projection ka scale positive rakho
    if P[2, 3] < 0:
        P = -P

    # RQ decomposition: M = K @ R (K upper-triangular, R orthogonal).
    # Derivation: J M^T J = Q @ R_up (QR)  =>
    #   K = J R_up^T J,  R = J Q^T J   (J = anti-identity)
    M = P[:, :3]
    N = (M.T)[::-1, ::-1]
    Q, R_up = np.linalg.qr(N)
    K = (R_up.T)[::-1, ::-1]
    R = (Q.T)[::-1, ::-1]
    # K ke diagonal ko positive karo (sign ambiguity hatana)
    d = np.sign(np.diag(K))
    d[d == 0] = 1  # sirf diagonal fix karo — poora matrix nahi!
    D = np.diag(d)
    K = K @ D
    R = D @ R  # M = K@R barkarar: (KD)(DR) = K(DD)R = KR
    # K normalize: K[2,2] = 1
    if abs(K[2, 2]) > 1e-9:
        K = K / K[2, 2]
    t = np.linalg.inv(K) @ P[:, 3]

    # Reprojection error (pixels)
    errs = []
    for (u, v), (X, Y, Z) in zip(image_points, world_points):
        proj = P @ np.array([X, Y, Z, 1.0])
        up, vp = proj[0] / proj[2], proj[1] / proj[2]
        errs.append(math.hypot(up - u, vp - v))
    reproj = float(np.mean(errs))

    return (P.tolist(), K.tolist(), R.tolist(), t.tolist(), reproj)


@calibration_bp.route('/calibration/solve', methods=['POST'])
@jwt_required()
def solve_calibration():
    """
    Correspondences se DLT chalakar camera matrices nikalo.
    Body: {camera_id}
    """
    data = request.get_json() or {}
    cam_id = data.get('camera_id')
    if not cam_id:
        return jsonify({'message': 'camera_id zaroori hai'}), 400

    cam, prof = _get_profile(cam_id)
    if not cam:
        return jsonify({'message': 'Camera nahi mili'}), 404

    corr = (prof.data or {}).get('correspondences')
    if not corr:
        return jsonify({'message': 'Pehle point-correspondences save karo'}), 400
    img_pts = corr['image_points']
    world_pts = corr['world_points']
    if len(img_pts) < MIN_CORRESPONDENCES:
        return jsonify({'message': f'Kam se kam {MIN_CORRESPONDENCES} points chahiye'}), 400

    try:
        P, K, R, t, reproj = _dlt_calibrate(img_pts, world_pts)
    except Exception as e:
        return jsonify({'message': f'DLT solve fail: {e}'}), 500

    fx, fy, cx, cy = K[0][0], K[1][1], K[0][2], K[1][2]
    data_new = dict(prof.data or {})
    data_new['projection_matrix'] = P
    data_new['intrinsics'] = {
        'focal_x': fx, 'focal_y': fy, 'cx': cx, 'cy': cy,
        'distortion': (data_new.get('intrinsics') or {}).get('distortion', [0, 0, 0, 0, 0]),
        'source': 'dlt-solve',
    }
    data_new['extrinsics'] = {'R': R, 't': t, 'source': 'dlt-solve'}
    prof.data = data_new
    prof.reprojection_error = reproj
    prof.is_calibrated = True
    db.session.commit()

    quality = 'excellent' if reproj < 2 else 'good' if reproj < 5 else 'poor'
    return jsonify({
        'message': 'Calibration solve ho gayi',
        'camera_id': cam_id,
        'calibrated': True,
        'reprojection_error_px': round(reproj, 2),
        'quality': quality,
        'projection_matrix': P,
    }), 200


# ---------------------------------------------------------
# G5: Status
# ---------------------------------------------------------
@calibration_bp.route('/calibration/camera/<int:cam_id>', methods=['GET'])
@jwt_required()
def calibration_status(cam_id):
    """Camera ka calibration status dekho."""
    cam = Camera.query.get(cam_id)
    if not cam:
        return jsonify({'message': 'Camera nahi mili'}), 404

    prof = cam.calibration_profile
    if not prof:
        return jsonify({
            'camera_id': cam_id,
            'camera_name': cam.name,
            'calibrated': False,
            'reprojection_error': None,
            'has_intrinsics': False,
            'has_extrinsics': False,
            'n_correspondences': 0,
        }), 200

    d = prof.to_dict()
    d['camera_name'] = cam.name
    return jsonify(d), 200
