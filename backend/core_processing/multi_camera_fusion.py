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


def detect_ball_trajectory(video_path, model, conf=0.15, imgsz=640,
                           max_frames=None, frame_skip=1):
    """
    Ek camera ki video se ball ki 2D trajectory nikalo.
    Returns: [(frame_idx, x, y, conf), ...]
    """
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
            # Sabse confident ball lo
            best = None
            best_conf = 0
            for box in r.boxes:
                c = float(box.conf[0])
                if c > best_conf:
                    best_conf = c
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    best = ((x1 + x2) / 2, (y1 + y2) / 2)
            if best:
                trajectory.append((fi, best[0], best[1], best_conf))
        fi += 1
        if max_frames and fi >= max_frames:
            break
    cap.release()
    return trajectory


def fuse_trajectories(trajectories_2d, frame_offsets=None):
    """
    Multiple cameras ki 2D trajectories ko time-sync karke jodo.

    trajectories_2d: [traj_cam0, traj_cam1, ...]
      har traj = [(frame_idx, x, y, conf), ...]
    frame_offsets: [offset0, offset1, ...] — clap sync se (default: 0)

    Returns: {synced_frame: [(cam_idx, x, y, conf), ...]}
    """
    if frame_offsets is None:
        frame_offsets = [0] * len(trajectories_2d)

    fused = {}
    for cam_idx, traj in enumerate(trajectories_2d):
        offset = frame_offsets[cam_idx]
        for fi, x, y, conf in traj:
            synced = fi + offset
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
        from core_processing.triangulation import triangulate_robust
    except ImportError:
        from triangulation import triangulate_robust

    if len(detections) < 2:
        return None

    points_2d = []
    proj_matrices = []
    for cam_idx, x, y, conf in detections:
        if cam_idx not in camera_matrices:
            continue
        K, R, t = camera_matrices[cam_idx]
        # Projection matrix P = K @ [R | t]
        P = _projection_matrix(K, R, t)
        points_2d.append((x, y))
        proj_matrices.append(P)

    if len(points_2d) < 2:
        return None

    return triangulate_robust(points_2d, proj_matrices)


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
                     frame_offsets=None, conf=0.15):
    """
    FULL PIPELINE: 4-6 videos → fused 3D trajectory → LBW decision.

    video_paths: [video_cam0, video_cam1, ...] (4-6 videos)
    model: ball detection YOLO model
    camera_matrices: {cam_idx: (K, R, t)} — calibration se
    frame_offsets: clap sync offsets

    Returns: {
      'decision': 'OUT'/'NOT OUT'/...,
      'trajectory_3d': [(X,Y,Z), ...],
      'per_camera': [...],
      'fused_frames': int,
      ...
    }
    """
    n_cams = len(video_paths)
    print(f"Multi-camera fusion: {n_cams} cameras")

    # Step 1: Har camera se 2D trajectory
    trajs_2d = []
    for i, vp in enumerate(video_paths):
        print(f"  Camera {i+1}: detecting...")
        traj = detect_ball_trajectory(vp, model, conf=conf)
        trajs_2d.append(traj)
        print(f"  Camera {i+1}: {len(traj)} detections")

    # Step 2: Time sync + fuse
    fused = fuse_trajectories(trajs_2d, frame_offsets)
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
    # (agar 3D nahi bana to sabse zyada detections wali camera)
    best_cam = max(range(n_cams), key=lambda i: len(trajs_2d[i]))
    fallback_2d = [(x, y) for _, x, y, _ in trajs_2d[best_cam]]

    # Step 5: LBW decision
    try:
        from core_processing.drs_logic import analyze_lbw_icc
    except ImportError:
        from drs_logic import analyze_lbw_icc

    result = None
    method = 'none'

    if len(trajectory_3d) >= 3:
        # 3D trajectory se decision (X-Z plane use karo)
        traj_xz = [(p[0], p[2]) for p in trajectory_3d]
        tracking = {'ball': traj_xz[-1], 'trajectory': traj_xz}
        result = analyze_lbw_icc(tracking, frame_width=1000)
        method = f'3D triangulation ({n_cams} cameras)'
    elif len(fallback_2d) >= 3:
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
            'per_camera_detections': [len(t) for t in trajs_2d],
        }

    result['method'] = method
    result['n_cameras'] = n_cams
    result['per_camera_detections'] = [len(t) for t in trajs_2d]
    result['fused_frames'] = len(fused)
    result['multi_view_frames'] = multi_view_frames
    result['trajectory_3d_points'] = len(trajectory_3d)
    return result
