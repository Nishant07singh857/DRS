"""
Multi-camera 3D triangulation — asli Hawk-Eye ka core principle.

4-6 smartphones alag angles se ball dekhte hain.
Har camera 2D position deta hai (x, y pixels).
Ye module unhe jodkar 3D position nikalta hai (X, Y, Z meters).

Math: Direct Linear Transform (DLT) + Least Squares + RANSAC
- DLT: har camera se 2 equations, N cameras = 2N equations, 4 unknowns (X,Y,Z,1)
- Least Squares: sab cameras ka best-fit 3D point (SVD se)
- RANSAC: galat detections ko reject karo (outlier cameras hatao)

Camera setup (Hawk-Eye jaisa):
  Cam 0,1: Bowler ke peeche (sightscreen) — pitch ki seedh
  Cam 2,3: Square — dono taraf (point/cover)
  Cam 4,5: Upar/peechhe — extra angles (optional)

Calibration: har camera ke liye chahiye:
  - K: intrinsic matrix (focal length, center) — phone se andaza ya calibrate
  - R, t: rotation + translation (camera kahan hai, kidhar dekh raha)
  Simplest: pitch ke known points (stumps, crease) par click karke calibrate karo.
"""

import math


def _mat_vec_mul(M, v):
    """3x3 matrix * 3-vector."""
    return [
        M[0][0]*v[0] + M[0][1]*v[1] + M[0][2]*v[2],
        M[1][0]*v[0] + M[1][1]*v[1] + M[1][2]*v[2],
        M[2][0]*v[0] + M[2][1]*v[1] + M[2][2]*v[2],
    ]


def _svd_solve(A):
    """
    AX=0 ka least-squares solution (smallest singular vector).
    A: MxN matrix (list of lists). N=4 ke liye optimized.
    Returns: N-vector (normalized).
    """
    # A^T * A banao (NxN)
    n = len(A[0])
    m = len(A)
    AtA = [[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            s = 0.0
            for k in range(m):
                s += A[k][i] * A[k][j]
            AtA[i][j] = s
    # Power iteration se SMALLEST eigenvector nahi milta aasani se.
    # Trick: inverse power iteration, ya...
    # Simple: 4x4 ke liye, hum shift karke largest nikalte hain.
    # Actually: smallest eigenvector of AtA = largest of (I*mu - AtA) for large mu
    # Yahan simple Jacobi eigenvalue algorithm use karte hain.
    return _smallest_eigenvector(AtA)


def _smallest_eigenvector(M):
    """4x4 symmetric matrix ka smallest eigenvector (Jacobi rotations)."""
    n = len(M)
    # Copy
    A = [row[:] for row in M]
    V = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

    for _ in range(50):  # Jacobi sweeps
        # Sabse bada off-diagonal dhoondo
        p, q, maxv = 0, 1, 0.0
        for i in range(n):
            for j in range(i+1, n):
                if abs(A[i][j]) > maxv:
                    maxv, p, q = abs(A[i][j]), i, j
        if maxv < 1e-12:
            break
        # Rotation
        app, aqq, apq = A[p][p], A[q][q], A[p][q]
        theta = 0.5 * math.atan2(2*apq, aqq - app)
        c, s = math.cos(theta), math.sin(theta)
        # A update
        for i in range(n):
            if i != p and i != q:
                aip, aiq = A[i][p], A[i][q]
                A[i][p] = A[p][i] = c*aip - s*aiq
                A[i][q] = A[q][i] = s*aip + c*aiq
        A[p][p] = c*c*app - 2*s*c*apq + s*s*aqq
        A[q][q] = s*s*app + 2*s*c*apq + c*c*aqq
        A[p][q] = A[q][p] = 0.0
        # V update
        for i in range(n):
            vip, viq = V[i][p], V[i][q]
            V[i][p] = c*vip - s*viq
            V[i][q] = s*vip + c*viq

    # Sabse chhoti eigenvalue ka eigenvector
    best_i, best_v = 0, A[0][0]
    for i in range(1, n):
        if A[i][i] < best_v:
            best_v, best_i = A[i][i], i
    vec = [V[i][best_i] for i in range(n)]
    # Normalize
    norm = math.sqrt(sum(x*x for x in vec))
    if norm < 1e-12:
        return [0, 0, 0, 1]
    return [x / norm for x in vec]


class Camera:
    """
    Ek smartphone camera ka model.
    K: 3x3 intrinsic [[fx,0,cx],[0,fy,cy],[0,0,1]]
    R: 3x3 rotation matrix (world -> camera)
    t: 3-vector translation (world -> camera): x_cam = R @ x_world + t
    """
    def __init__(self, K, R, t, name="cam"):
        self.K = K
        self.R = R
        self.t = t
        self.name = name
        # Projection matrix P = K @ [R | t]  (3x4)
        self.P = [
            [
                K[0][0]*R[0][0] + K[0][1]*R[1][0] + K[0][2]*R[2][0],
                K[0][0]*R[0][1] + K[0][1]*R[1][1] + K[0][2]*R[2][1],
                K[0][0]*R[0][2] + K[0][1]*R[1][2] + K[0][2]*R[2][2],
                K[0][0]*t[0] + K[0][1]*t[1] + K[0][2]*t[2],
            ],
            [
                K[1][0]*R[0][0] + K[1][1]*R[1][0] + K[1][2]*R[2][0],
                K[1][0]*R[0][1] + K[1][1]*R[1][1] + K[1][2]*R[2][1],
                K[1][0]*R[0][2] + K[1][1]*R[1][2] + K[1][2]*R[2][2],
                K[1][0]*t[0] + K[1][1]*t[1] + K[1][2]*t[2],
            ],
            [
                R[2][0], R[2][1], R[2][2], t[2],
            ],
        ]

    def project(self, X):
        """3D point (x,y,z) -> 2D pixel (u,v)."""
        x, y, z = X
        p = [
            self.P[0][0]*x + self.P[0][1]*y + self.P[0][2]*z + self.P[0][3],
            self.P[1][0]*x + self.P[1][1]*y + self.P[1][2]*z + self.P[1][3],
            self.P[2][0]*x + self.P[2][1]*y + self.P[2][2]*z + self.P[2][3],
        ]
        if abs(p[2]) < 1e-9:
            return None
        return (p[0]/p[2], p[1]/p[2])

    def reprojection_error(self, X, uv):
        """3D point ko wapas project karke error nikalo (pixels me)."""
        proj = self.project(X)
        if proj is None:
            return float('inf')
        return math.sqrt((proj[0]-uv[0])**2 + (proj[1]-uv[1])**2)


def triangulate(points_2d, cameras):
    """
    Kai cameras ke 2D detections se 3D point nikalo (DLT + least squares).

    points_2d: [(u, v) ya None, ...] — har camera ke liye (None = ball nahi dikhi)
    cameras: [Camera, ...] — same order me

    Returns: (x, y, z) meters me, ya None (agar <2 cameras me dikhi)
    """
    # CV-M4: length mismatch is an error, never a silent zip truncation.
    if len(points_2d) != len(cameras):
        raise ValueError(
            f"triangulate: {len(points_2d)} points but {len(cameras)} cameras")
    # Kam se kam 2 cameras me ball dikhni chahiye
    valid = [(uv, cam) for uv, cam in zip(points_2d, cameras) if uv is not None]
    if len(valid) < 2:
        return None

    # DLT: har camera se 2 equations
    A = []
    for (u, v), cam in valid:
        P = cam.P
        # u * P[2] - P[0] = 0
        A.append([u*P[2][0]-P[0][0], u*P[2][1]-P[0][1],
                  u*P[2][2]-P[0][2], u*P[2][3]-P[0][3]])
        # v * P[2] - P[1] = 0
        A.append([v*P[2][0]-P[1][0], v*P[2][1]-P[1][1],
                  v*P[2][2]-P[1][2], v*P[2][3]-P[1][3]])

    Xh = _svd_solve(A)  # homogeneous [X, Y, Z, W]
    if abs(Xh[3]) < 1e-9:
        return None
    return (Xh[0]/Xh[3], Xh[1]/Xh[3], Xh[2]/Xh[3])


def triangulate_robust(points_2d, cameras, ransac_thresh_px=15.0,
                       weights=None):
    """
    RANSAC ke saath triangulation — galat detections reject karo.
    4-6 cameras me se agar 1-2 galat detect karein to bhi sahi 3D milega.

    CV-H10: weights (per-camera detection confidences, same order as
    points_2d) weight the pair selection: the best pair maximises the
    summed confidence of its inliers, not just the inlier count, and
    ties break on lower mean reprojection error. Without weights every
    camera counts equally, as before.
    """
    if len(points_2d) != len(cameras):
        raise ValueError(
            f"triangulate_robust: {len(points_2d)} points but {len(cameras)} cameras")
    if weights is not None and len(weights) != len(points_2d):
        raise ValueError("triangulate_robust: weights length must match points")
    valid_idx = [i for i, uv in enumerate(points_2d) if uv is not None]
    if len(valid_idx) < 2:
        return None
    if len(valid_idx) == 2:
        return triangulate(points_2d, cameras)

    def _w(k):
        return float(weights[k]) if weights is not None else 1.0

    best_X, best_inliers = None, []
    best_score, best_err = -1.0, float('inf')
    # Har pair se try karo, sabse zyada inliers wala chuno
    import itertools
    for i, j in itertools.combinations(valid_idx, 2):
        sub_pts = [None]*len(cameras)
        sub_pts[i], sub_pts[j] = points_2d[i], points_2d[j]
        X = triangulate(sub_pts, cameras)
        if X is None:
            continue
        # Inliers gino
        inliers = []
        errs = []
        for k in valid_idx:
            err = cameras[k].reprojection_error(X, points_2d[k])
            if err < ransac_thresh_px:
                inliers.append(k)
                errs.append(err)
        score = sum(_w(k) for k in inliers)
        mean_err = sum(errs) / len(errs) if errs else float('inf')
        if score > best_score or (score == best_score and mean_err < best_err):
            best_inliers, best_X = inliers, X
            best_score, best_err = score, mean_err

    if best_X is None or len(best_inliers) < 2:
        return triangulate(points_2d, cameras)

    # Inliers se final refine
    sub_pts = [points_2d[i] if i in best_inliers else None
               for i in range(len(cameras))]
    return triangulate(sub_pts, cameras)


def default_phone_camera(width=1920, height=1080, fov_deg=70):
    """
    Smartphone ka andaza intrinsic matrix (calibration ke bina).
    fov_deg: horizontal field of view (aam taur par 65-75).
    """
    import math
    fx = (width / 2) / math.tan(math.radians(fov_deg / 2))
    fy = fx  # square pixels
    cx, cy = width / 2, height / 2
    return [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]


def camera_looking_at(cam_pos, target, up=(0, 0, 1)):
    """
    Camera position se target ki taraf dekhne wala R, t banao.
    cam_pos: (x, y, z) meters me
    target: (x, y, z) — jidhar dekhna hai (aam taur par pitch ka center)
    Returns: (R, t)
    """
    import math
    # Forward vector
    fx = target[0] - cam_pos[0]
    fy = target[1] - cam_pos[1]
    fz = target[2] - cam_pos[2]
    fl = math.sqrt(fx*fx + fy*fy + fz*fz)
    if fl < 1e-9:
        raise ValueError("camera_looking_at: cam_pos == target (no direction)")
    fx, fy, fz = fx/fl, fy/fl, fz/fl
    # Right = forward x up. CV-M1: an overhead camera (forward parallel
    # to up) gives right = 0 and a division by zero — fall back to a
    # different up vector instead of crashing.
    rx = fy*up[2] - fz*up[1]
    ry = fz*up[0] - fx*up[2]
    rz = fx*up[1] - fy*up[0]
    rl = math.sqrt(rx*rx + ry*ry + rz*rz)
    if rl < 1e-9:
        alt_up = (0, 1, 0) if abs(fy) < 0.9 else (1, 0, 0)
        rx = fy*alt_up[2] - fz*alt_up[1]
        ry = fz*alt_up[0] - fx*alt_up[2]
        rz = fx*alt_up[1] - fy*alt_up[0]
        rl = math.sqrt(rx*rx + ry*ry + rz*rz)
        if rl < 1e-9:
            raise ValueError("camera_looking_at: degenerate camera orientation")
    rx, ry, rz = rx/rl, ry/rl, rz/rl
    # True up = right x forward
    ux = ry*fz - rz*fy
    uy = rz*fx - rx*fz
    uz = rx*fy - ry*fx
    # R: world -> camera (rows = right, up, -forward)
    R = [
        [rx, ry, rz],
        [ux, uy, uz],
        [-fx, -fy, -fz],
    ]
    # t = -R @ cam_pos
    t = [
        -(R[0][0]*cam_pos[0] + R[0][1]*cam_pos[1] + R[0][2]*cam_pos[2]),
        -(R[1][0]*cam_pos[0] + R[1][1]*cam_pos[1] + R[1][2]*cam_pos[2]),
        -(R[2][0]*cam_pos[0] + R[2][1]*cam_pos[1] + R[2][2]*cam_pos[2]),
    ]
    return R, t


def suggested_4_camera_setup(pitch_center=(0, 0, 0), pitch_length=20.12):
    """
    4 smartphones ke liye suggested positions (meters me).
    Coordinate: x = pitch ke along (bowler -x, batsman +x),
                y = pitch ke across, z = upar.
    """
    L = pitch_length
    cams = []
    positions = [
        # (name, position, description)
        ("bowler_end", (-L/2 - 15, 0, 3), "Bowler ke peeche (sightscreen)"),
        ("square_leg", (0, -18, 2.5), "Square leg side"),
        ("point", (0, 18, 2.5), "Point side"),
        ("batsman_end_high", (L/2 + 12, 0, 6), "Batsman ke peeche, upar"),
    ]
    for name, pos, desc in positions:
        K = default_phone_camera()
        R, t = camera_looking_at(pos, pitch_center)
        cams.append({
            'camera': Camera(K, R, t, name=name),
            'description': desc,
            'position': pos,
        })
    return cams


# --- 3D LBW Analysis (Hawk-Eye jaisa) ---

# Stumps ka 3D model (meters me, origin = pitch center)
# x: pitch along (-10.06 bowler end, +10.06 batsman end)
# y: pitch across (0 = middle stump)
# z: upar (0 = ground)
STUMP_X = 10.06  # batsman end
STUMP_HALF_WIDTH = 0.114  # 3 stumps ~22.8cm wide
STUMP_HEIGHT = 0.711
BALL_RADIUS = 0.036  # cricket ball ~7.2cm diameter


def _fit_poly(ts, vals, degree):
    """Least-squares polynomial fit (small degree, normal equations)."""
    # Build normal equations; degree <= 2 and n small, so this is stable
    # enough for a pre-impact fit window.
    m = degree + 1
    ata = [[0.0] * m for _ in range(m)]
    atb = [0.0] * m
    for t, v in zip(ts, vals):
        powers = [t ** k for k in range(m)]
        for i in range(m):
            atb[i] += powers[i] * v
            for j in range(m):
                ata[i][j] += powers[i] * powers[j]
    # Gaussian elimination
    aug = [ata[i] + [atb[i]] for i in range(m)]
    for col in range(m):
        piv = max(range(col, m), key=lambda r: abs(aug[r][col]))
        if abs(aug[piv][col]) < 1e-12:
            return None
        aug[col], aug[piv] = aug[piv], aug[col]
        for r in range(m):
            if r != col:
                f = aug[r][col] / aug[col][col]
                for c in range(col, m + 1):
                    aug[r][c] -= f * aug[col][c]
    return [aug[i][m] / aug[i][i] for i in range(m)]


def _polyval(coeffs, t):
    return sum(c * t ** k for k, c in enumerate(coeffs))


def analyze_lbw_3d(trajectory_3d, handedness='RHB'):
    """
    3D trajectory se LBW decision — asli Hawk-Eye logic (CV-H6 fixed).

    trajectory_3d: [(x, y, z), ...] meters me, time-ordered.
    Bowler -x se, batsman +x par.
    handedness: 'RHB' (leg side y<0) or 'LHB' (leg side y>0) — the old
    code hardcoded y<0 for a right-hander with no parameter.

    CV-H6 fixes vs. the old version:
    - Pitch is NOT the global z-minimum: it is the FIRST local z-minimum
      with a genuine bounce signature (descending then ascending z).
      A trajectory that keeps rolling / is tracked past the pad no
      longer gets its "pitch" from the lowest stray point, and a
      no-bounce (full toss) trajectory reports pitch_3d=None.
    - Impact is NOT pts[-1]: it is the largest velocity-direction
      discontinuity after the bounce (pad deflection), falling back to
      the last point only with impact_detected=False.
    - Hitting is NOT a 2-point linear extrapolation that returns False
      once the ball is past the stumps: a gravity-aware fit (x,y linear
      in frame index, z quadratic) over the PRE-IMPACT segment is
      evaluated at the stump plane x=STUMP_X, so a ball that already
      passed through the stump segment still counts as hitting.
    - Confidence is NOT min(95, 60+2*n) from point count: it comes from
      the pre-impact fit residuals (RMS, metres) — see 'fit_rms_m'.
    - 'pitch_in_line' (|y| within stump width) and 'pitch_ok' (not
      outside leg, handedness-aware) are distinct fields (CV-L4); the
      decision uses pitch_ok, not pitch_in_line.

    Returns: {
        'pitch_3d': (x, y, z) | None, 'pitch_in_line': bool,
        'pitch_ok': bool, 'bounced': bool,
        'impact_3d': (x, y, z), 'impact_in_line': bool,
        'impact_detected': bool, 'hitting_stumps': bool,
        'fit_rms_m': float | None, 'confidence': float,
        'decision': 'OUT' | 'NOT OUT' | "UMPIRE'S CALL",
        'handedness': str, 'leg_side': str,
    }
    """
    if not trajectory_3d or len(trajectory_3d) < 5:
        return None
    if handedness not in ('RHB', 'LHB'):
        raise ValueError(f"handedness must be 'RHB' or 'LHB', got {handedness!r}")

    pts = [(float(p[0]), float(p[1]), float(p[2])) for p in trajectory_3d]
    n = len(pts)
    # Leg side sign: RHB -> leg is y<0, LHB -> leg is y>0.
    leg_sign = -1 if handedness == 'RHB' else 1

    # 1. PITCH: first local z-minimum with a bounce signature.
    # vz estimated over 2 frames either side; descending (vz<0) then
    # ascending (vz>0) is a genuine bounce, not a stray low point.
    pitch_idx = None
    for i in range(2, n - 2):
        z = pts[i][2]
        if z <= pts[i - 1][2] and z <= pts[i + 1][2]:
            vz_pre = (pts[i][2] - pts[i - 2][2]) / 2.0
            vz_post = (pts[i + 2][2] - pts[i][2]) / 2.0
            if vz_pre < 0 and vz_post > 0:
                pitch_idx = i
                break
    bounced = pitch_idx is not None
    pitch_3d = pts[pitch_idx] if bounced else None
    pitch_in_line = (abs(pitch_3d[1]) < (STUMP_HALF_WIDTH + BALL_RADIUS)
                     if bounced else False)
    if not bounced:
        pitch_ok = True  # full toss — pitch rule skipped
    else:
        # Outside leg: legward distance (leg_sign * y, where leg_sign
        # is -1 for RHB so legward = -y, +1 for LHB so legward = +y)
        # beyond the stump width + ball radius.
        pitch_ok = not (leg_sign * pitch_3d[1] > (STUMP_HALF_WIDTH + BALL_RADIUS))

    # 2. IMPACT: largest direction discontinuity after the bounce.
    # Segment direction change (degrees) between consecutive segments.
    impact_idx = n - 1
    impact_detected = False
    start = (pitch_idx + 1) if bounced else 1
    best_angle, best_i = 15.0, None  # >15 deg counts as a deflection
    for i in range(start, n - 1):
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts[i - 1], pts[i], pts[i + 1]
        ax, ay, az = x1 - x0, y1 - y0, z1 - z0
        bx, by, bz = x2 - x1, y2 - y1, z2 - z1
        na = math.sqrt(ax * ax + ay * ay + az * az)
        nb = math.sqrt(bx * bx + by * by + bz * bz)
        if na < 1e-9 or nb < 1e-9:
            continue
        cosang = max(-1.0, min(1.0, (ax * bx + ay * by + az * bz) / (na * nb)))
        ang = math.degrees(math.acos(cosang))
        if ang > best_angle:
            best_angle, best_i = ang, i
    if best_i is not None:
        impact_idx, impact_detected = best_i, True
    impact_3d = pts[impact_idx]
    impact_in_line = abs(impact_3d[1]) < (STUMP_HALF_WIDTH + BALL_RADIUS)

    # 3. HITTING: gravity-aware fit over the PRE-IMPACT segment
    # (up to 8 points ending at impact, at least 3). x,y linear in
    # frame index, z quadratic (gravity). Evaluate at x = STUMP_X:
    # this is a stump-SEGMENT crossing check, valid even if the ball
    # is already past the stump plane at impact.
    hitting = False
    fit_rms = None
    pre = pts[max(0, impact_idx - 7):impact_idx + 1]
    if len(pre) >= 3:
        ts = list(range(len(pre)))
        cx = _fit_poly(ts, [p[0] for p in pre], 1)
        cy = _fit_poly(ts, [p[1] for p in pre], 1)
        cz = _fit_poly(ts, [p[2] for p in pre], 2)
        if cx is not None and cy is not None and cz is not None:
            # Fit residuals (RMS over the pre-impact window)
            sq = 0.0
            for t, p in zip(ts, pre):
                dx = _polyval(cx, t) - p[0]
                dy = _polyval(cy, t) - p[1]
                dz = _polyval(cz, t) - p[2]
                sq += dx * dx + dy * dy + dz * dz
            fit_rms = math.sqrt(sq / len(pre))
            # Solve x(t) = STUMP_X (linear in t)
            if abs(cx[1]) > 1e-9:
                t_stump = (STUMP_X - cx[0]) / cx[1]
                # The crossing must lie within (or just beyond) the
                # fitted window's forward projection, not arbitrarily
                # far back in time: allow up to 30 frames past impact.
                if -1.0 <= t_stump <= (len(pre) - 1) + 30:
                    hy = _polyval(cy, t_stump)
                    hz = _polyval(cz, t_stump)
                    if (abs(hy) < STUMP_HALF_WIDTH + BALL_RADIUS and
                            0 < hz < STUMP_HEIGHT + BALL_RADIUS):
                        hitting = True

    # 4. CONFIDENCE from fit residuals (not point count).
    # rms <= 0.02 m -> 95; 0.05 -> 85; 0.10 -> 70; 0.20 -> 55; worse -> 50.
    if fit_rms is None:
        fit_conf = 50.0
    elif fit_rms <= 0.02:
        fit_conf = 95.0
    elif fit_rms <= 0.05:
        fit_conf = 95.0 - (fit_rms - 0.02) / 0.03 * 10.0
    elif fit_rms <= 0.10:
        fit_conf = 85.0 - (fit_rms - 0.05) / 0.05 * 15.0
    elif fit_rms <= 0.20:
        fit_conf = 70.0 - (fit_rms - 0.10) / 0.10 * 15.0
    else:
        fit_conf = 50.0

    # 5. DECISION (ICC LBW rules, simplified)
    if not pitch_ok:
        decision, confidence = "NOT OUT", 95.0
    elif not impact_in_line:
        decision, confidence = "NOT OUT", 85.0
    elif not hitting:
        decision, confidence = "NOT OUT", 80.0
    else:
        confidence = round(fit_conf, 1)
        decision = "OUT" if confidence > 75 else "UMPIRE'S CALL"

    return {
        'pitch_3d': tuple(round(c, 3) for c in pitch_3d) if pitch_3d else None,
        'pitch_in_line': pitch_in_line,
        'pitch_ok': pitch_ok,
        'bounced': bounced,
        'impact_3d': tuple(round(c, 3) for c in impact_3d),
        'impact_in_line': impact_in_line,
        'impact_detected': impact_detected,
        'hitting_stumps': hitting,
        'fit_rms_m': round(fit_rms, 4) if fit_rms is not None else None,
        'confidence': round(confidence, 1),
        'decision': decision,
        'handedness': handedness,
        'leg_side': 'y<0' if handedness == 'RHB' else 'y>0',
    }
