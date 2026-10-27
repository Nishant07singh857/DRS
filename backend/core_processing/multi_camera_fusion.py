"""
Multi-Camera Fusion — 4-6 angles se ball detect karke ek decision.

Pipeline:
  1. Har camera ki video se ball trajectory nikalo (v2 model)
  2. Audio clap se sab cameras sync karo
  3. Har frame par 3D triangulate karo
  4. 3D trajectory se LBW decision (ICC logic)

Yehi asli Hawk-Eye ka principle hai — multiple angles milkar ek sach!
"""

import os
import cv2


def _ball_class_ids(model, ball_class_id=None):
    """Explicit ball-class mapping for a given model (CV-C2).

    Returns the set of class ids whose name is the ball. If the caller
    passes ball_class_id explicitly, that mapping wins. Otherwise it is
    derived from model.names: 'ball' (v4 ball-only, 3-class v3) or
    'sports ball' (COCO). If the model has no ball class at all, a
    ValueError is raised loudly — a pad/bat box must never silently
    become the ball trajectory.
    """
    if ball_class_id is not None:
        return {int(ball_class_id)}
    names = getattr(model, 'names', None)
    if names is None:
        raise ValueError(
            "detect_ball_trajectory: model has no .names; pass "
            "ball_class_id explicitly")
    items = names.items() if isinstance(names, dict) else enumerate(names)
    ids = {int(cid) for cid, name in items
           if name in ('ball', 'sports ball')}
    if not ids:
        raise ValueError(
            f"detect_ball_trajectory: model has no ball class in "
            f"names={names!r}; refusing to treat another class as ball")
    return ids


def detect_ball_trajectory(video_path, model, conf=0.15, imgsz=640,
                           max_frames=None, frame_skip=1, ball_class_id=None):
    """
    Ek camera ki video se ball ki 2D trajectory nikalo.
    Returns: [(frame_idx, x, y, conf), ...] — TIME-TRUE for sampled
    frames: a sampled frame with no ball detection is marked
    (fi, None, None, 0.0) instead of being silently dropped (CV-C2),
    so consumers that enumerate the list cannot mistake detection
    order for frame order. Callers that need positions only must
    filter out the None entries (fuse_trajectories and the 2D fallback
    below both do).
    """
    ball_ids = _ball_class_ids(model, ball_class_id)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    trajectory = []
    fi = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if fi % frame_skip == 0:
            r = model.predict(frame, verbose=False, conf=conf,
                              imgsz=imgsz)[0]
            # Sabse confident BALL lo — class filter ke saath (CV-C2).
            # r.boxes None ho sakta hai (koi detection nahi): guard karo.
            best = None
            best_conf = 0
            if r.boxes is not None:
                for box in r.boxes:
                    if int(box.cls[0]) not in ball_ids:
                        continue  # pad/bat/person kabhi ball nahi
                    c = float(box.conf[0])
                    if c > best_conf:
                        best_conf = c
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        best = ((x1 + x2) / 2, (y1 + y2) / 2)
            if best:
                trajectory.append((fi, best[0], best[1], best_conf))
            else:
                trajectory.append((fi, None, None, 0.0))
        fi += 1
        if max_frames and fi >= max_frames:
            break
    cap.release()
    return trajectory


def fuse_trajectories(trajectories_2d, frame_offsets=None,
                      offset_seconds=None, fps_list=None):
    """
    Multiple cameras ki 2D trajectories ko time-sync karke jodo.

    trajectories_2d: [traj_cam0, traj_cam1, ...]
      har traj = [(frame_idx, x, y, conf), ...] (None positions = miss)
    frame_offsets: [offset0, offset1, ...] — integer frame shifts
    offset_seconds: alternative — clap-sync offsets in SECONDS, as
      produced by audio_sync.sync_videos. Converted with fps_list
      (per-camera fps): offset_frames = round(seconds * fps). This is
      the CV-H10 fix: 30 fps vs 60 fps phones drift apart over a
      delivery under a frames-only offset, and a seconds offset was
      previously never converted at all.
    fps_list: [fps_cam0, fps_cam1, ...], required with offset_seconds.

    CV-H10 validation: an offset list whose length does not match the
    number of cameras raises ValueError (the old code raised IndexError
    for a short list and silently ignored a long one). Negative synced
    frames are dropped, not accepted. None (missed) positions are
    skipped — they carry no detection to fuse.

    Returns: {synced_frame: [(cam_idx, x, y, conf), ...]}
    """
    n_cams = len(trajectories_2d)
    if offset_seconds is not None:
        if fps_list is None:
            raise ValueError(
                "fuse_trajectories: fps_list is required when "
                "offset_seconds is given (seconds x fps = frames)")
        if len(offset_seconds) != n_cams or len(fps_list) != n_cams:
            raise ValueError(
                f"fuse_trajectories: {n_cams} cameras but "
                f"{len(offset_seconds)} offset_seconds / {len(fps_list)} fps")
        frame_offsets = [int(round(float(s) * float(f)))
                         for s, f in zip(offset_seconds, fps_list)]
    if frame_offsets is None:
        frame_offsets = [0] * n_cams
    if len(frame_offsets) != n_cams:
        raise ValueError(
            f"fuse_trajectories: {n_cams} cameras but "
            f"{len(frame_offsets)} frame_offsets")
    frame_offsets = [int(round(float(o))) for o in frame_offsets]

    fused = {}
    for cam_idx, traj in enumerate(trajectories_2d):
        offset = frame_offsets[cam_idx]
        for fi, x, y, conf in traj:
            if x is None or y is None:
                continue  # missed frame — no detection to fuse
            synced = fi + offset
            if synced < 0:
                continue  # negative synced frames are dropped, not accepted
            if synced not in fused:
                fused[synced] = []
            fused[synced].append((cam_idx, x, y, conf))
    return fused


def triangulate_frame(detections, camera_matrices):
    """
    Ek frame ki multiple 2D detections se 3D point nikalo.

    detections: [(cam_idx, x, y, conf), ...]
    camera_matrices: {cam_idx: (K, R, t)}

    Returns: (X, Y, Z) ya None (agar <2 cameras ne dekha)
    """
    try:
        from core_processing.triangulation import Camera, triangulate_robust
    except ImportError:
        from triangulation import Camera, triangulate_robust

    if len(detections) < 2:
        return None

    # CV-C1: triangulate/triangulate_robust require Camera objects
    # (cam.P, cam.reprojection_error). The old code passed raw 3x4
    # matrices, which crashed with AttributeError on every call and
    # meant the 2D fallback below was never reached either. Wrap each
    # (K, R, t) in a Camera; confidences weight the RANSAC choice (CV-H10).
    points_2d = []
    cameras = []
    weights = []
    for cam_idx, x, y, conf in detections:
        if cam_idx not in camera_matrices:
            continue
        K, R, t = camera_matrices[cam_idx]
        points_2d.append((x, y))
        cameras.append(Camera(K, R, t, name=f"cam{cam_idx}"))
        weights.append(float(conf) if conf is not None else 0.0)

    if len(points_2d) < 2:
        return None

    return triangulate_robust(points_2d, cameras, weights=weights)


def _projection_matrix(K, R, t):
    """P = K @ [R | t] — 3x4 projection matrix."""
    # [R | t]: 3x4
    Rt = [R[0] + [t[0]], R[1] + [t[1]], R[2] + [t[2]]]
    # K @ Rt
    P = []
    for i in range(3):
        row = []
        for j in range(4):
            s = sum(K[i][k] * Rt[k][j] for k in range(3))
            row.append(s)
        P.append(row)
    return P


def multi_camera_lbw(video_paths, model, camera_matrices=None,
                     frame_offsets=None, conf=0.15, handedness='RHB',
                     offset_seconds=None, fps_list=None):
    """
    FULL PIPELINE: 4-6 videos → fused 3D trajectory → LBW decision.

    video_paths: [video_cam0, video_cam1, ...] (4-6 videos)
    model: ball detection YOLO model
    camera_matrices: {cam_idx: (K, R, t)} — calibration se
    frame_offsets: clap sync offsets in frames (see fuse_trajectories
      for the seconds-based alternative offset_seconds + fps_list)
    handedness: 'RHB' | 'LHB', passed to the 3D LBW decision (CV-H6).

    CV-L3: an empty video_paths list returns INCONCLUSIVE instead of
    raising ValueError from max() on an empty range.
    CV-H3: the 3D path NO LONGER feeds metre-scale (x, z) coordinates
    into analyze_lbw_icc with pixel defaults (stumps 400-600, leg 700,
    4-unit steps) — that decision was meaningless. It now routes
    through triangulation.analyze_lbw_3d, which works in metres with
    stump geometry in metres. The 2D fallback still uses
    analyze_lbw_icc with the best camera's real frame width.

    Returns: {
      'decision': 'OUT'/'NOT OUT'/...,
      'trajectory_3d': [(X,Y,Z), ...],
      'per_camera': [...],
      'fused_frames': int,
      ...
    }
    """
    # CV-L3: empty input guard, before any max() call.
    if not video_paths:
        return {
            'decision': 'INCONCLUSIVE',
            'reason': 'Koi video nahi di gayi',
            'per_camera_detections': [],
        }
    n_cams = len(video_paths)
    print(f"Multi-camera fusion: {n_cams} cameras")

    # Step 1: Har camera se 2D trajectory
    trajs_2d = []
    for i, vp in enumerate(video_paths):
        print(f"  Camera {i+1}: detecting...")
        traj = detect_ball_trajectory(vp, model, conf=conf)
        trajs_2d.append(traj)
        n_det = sum(1 for _, x, _, _ in traj if x is not None)
        print(f"  Camera {i+1}: {n_det} detections")

    # Step 2: Time sync + fuse
    fused = fuse_trajectories(trajs_2d, frame_offsets,
                              offset_seconds=offset_seconds,
                              fps_list=fps_list)
    multi_view_frames = sum(1 for v in fused.values() if len(v) >= 2)
    print(f"  Fused frames: {len(fused)}, multi-view: {multi_view_frames}")

    # Step 3: 3D triangulate (agar calibration hai)
    trajectory_3d = []
    if camera_matrices:
        for fi in sorted(fused.keys()):
            pt3d = triangulate_frame(fused[fi], camera_matrices)
            if pt3d:
                trajectory_3d.append(pt3d)
        print(f"  3D points: {len(trajectory_3d)}")

    # Step 4: Best camera ki trajectory se 2D fallback
    # (agar 3D nahi bana to sabse zyada detections wali camera;
    # None markers count nahi hote, positions filter hote hain)
    def _n_det(traj):
        return sum(1 for _, x, _, _ in traj if x is not None)
    best_cam = max(range(n_cams), key=lambda i: _n_det(trajs_2d[i]))
    fallback_2d = [(x, y) for _, x, y, _ in trajs_2d[best_cam]
                   if x is not None and y is not None]

    # Step 5: LBW decision
    try:
        from core_processing.drs_logic import analyze_lbw_icc
        from core_processing.triangulation import analyze_lbw_3d
    except ImportError:
        from drs_logic import analyze_lbw_icc
        from triangulation import analyze_lbw_3d

    result = None
    method = 'none'

    if len(trajectory_3d) >= 5:
        # 3D trajectory se decision — METRES me, 3D LBW logic se (CV-H3).
        decision_3d = analyze_lbw_3d(trajectory_3d, handedness=handedness)
        if decision_3d is not None:
            result = dict(decision_3d)
            result['trajectory_3d'] = trajectory_3d
            method = f'3D triangulation ({n_cams} cameras)'
    if result is None and len(fallback_2d) >= 3:
        # Best camera se 2D decision
        cap = cv2.VideoCapture(video_paths[best_cam])
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        cap.release()
        tracking = {'ball': fallback_2d[-1], 'trajectory': fallback_2d}
        result = analyze_lbw_icc(tracking, frame_width=fw)
        method = f'2D (best camera {best_cam+1}/{n_cams})'

    if result is None:
        return {
            'decision': 'INCONCLUSIVE',
            'reason': 'Kisi camera me ball track nahi hui',
            'per_camera_detections': [_n_det(t) for t in trajs_2d],
        }

    result['method'] = method
    result['n_cameras'] = n_cams
    result['per_camera_detections'] = [_n_det(t) for t in trajs_2d]
    result['fused_frames'] = len(fused)
    result['multi_view_frames'] = multi_view_frames
    result['trajectory_3d_points'] = len(trajectory_3d)
    return result
