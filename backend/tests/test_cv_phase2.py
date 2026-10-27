"""
Phase 2 (CV/tracking) regression tests — QA report 2026-10-27, section 9.

Covers the Critical fixes (CV-C1..C5) plus the High fixes that are
cheaply unit-testable (CV-H4, H6, H8, H10). Pure-Python / fake-model
tests only: no real video inference, no model upload/download.
"""

import inspect
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core_processing import ball_physics
from core_processing.ball_physics import (
    analyze_delivery,
    estimate_speed,
    measure_lateral,
)
from core_processing import multi_camera_fusion as fusion
from core_processing.multi_camera_fusion import (
    detect_ball_trajectory,
    fuse_trajectories,
    multi_camera_lbw,
    triangulate_frame,
)
from core_processing import triangulation
from core_processing.triangulation import (
    analyze_lbw_3d,
    camera_looking_at,
    suggested_4_camera_setup,
)
from core_processing.failproof_tracker import FailproofTracker
from core_processing.realtime_tracker import (
    DEFAULT_MODEL_PATH,
    RealtimeTracker,
)


# ---------------------------------------------------------------- CV-C1
def test_fusion_triangulates_with_three_plus_cameras_no_type_error():
    """CV-C1: triangulate_frame must accept (K, R, t) and return a 3D
    point close to the true point — previously it crashed with
    AttributeError because raw 3x4 matrices were passed where Camera
    objects were required."""
    setup = suggested_4_camera_setup()
    cams = setup[:3]
    camera_matrices = {
        i: (c['camera'].K, c['camera'].R, c['camera'].t)
        for i, c in enumerate(cams)
    }
    true_pt = (5.0, 0.2, 0.8)
    detections = []
    for i, c in enumerate(cams):
        u, v = c['camera'].project(true_pt)
        detections.append((i, u, v, 0.9))
    pt = triangulate_frame(detections, camera_matrices)
    assert pt is not None
    err = math.sqrt(sum((a - b) ** 2 for a, b in zip(pt, true_pt)))
    assert err < 0.5, f"triangulated {pt} vs true {true_pt} (err {err})"


def test_camera_looking_at_overhead_does_not_crash():
    """CV-M1: overhead camera (forward parallel to up) must not raise
    ZeroDivisionError."""
    R, t = camera_looking_at((0, 0, 10), (0, 0, 0))
    assert len(R) == 3 and len(t) == 3


# ---------------------------------------------------------------- CV-C2
class _Cls(int):
    """Scalar class id that also supports [0] indexing, like a
    1-element tensor (failproof uses int(b.cls), fusion uses b.cls[0])."""
    def __getitem__(self, idx):
        if idx == 0:
            return int(self)
        raise IndexError(idx)


class _Conf(float):
    """Scalar confidence that also supports [0] indexing."""
    def __getitem__(self, idx):
        if idx == 0:
            return float(self)
        raise IndexError(idx)


class _FakeBox:
    def __init__(self, cls_id, conf, xyxy):
        self.cls = _Cls(cls_id)
        self.conf = _Conf(conf)
        self.xyxy = np.array([xyxy], dtype=float)


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeModel:
    """names: 0=ball, 1=pad, 2=bat. Returns a confident PAD box and a
    weaker BALL box on every frame, unless boxes=None is requested."""

    names = {0: 'ball', 1: 'pad', 2: 'bat'}

    def __init__(self, boxes='normal'):
        self._boxes = boxes

    def predict(self, frame, verbose=False, conf=0.15, imgsz=640):
        if self._boxes is None:
            return [_FakeResult(None)]
        pad = _FakeBox(1, 0.99, [10, 10, 20, 20])    # centre (15, 15)
        ball = _FakeBox(0, 0.60, [30, 30, 40, 40])   # centre (35, 35)
        return [_FakeResult([pad, ball])]


def _write_black_video(path, n_frames=4):
    import cv2
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), 30, (64, 64))
    for _ in range(n_frames):
        w.write(np.zeros((64, 64, 3), dtype=np.uint8))
    w.release()


def test_fusion_ball_class_filter_rejects_pad(tmp_path):
    """CV-C2: the highest-confidence box of ANY class must not become
    the ball — a 0.99 pad box must lose to a 0.60 ball box."""
    video = str(tmp_path / "cam.mp4")
    _write_black_video(video)
    traj = detect_ball_trajectory(video, _FakeModel())
    assert len(traj) == 4
    for fi, x, y, conf in traj:
        assert (x, y) == (35.0, 35.0), f"pad box leaked into trajectory: {(x, y)}"
        assert conf == pytest.approx(0.60)


def test_fusion_boxes_none_guard_and_time_true_markers(tmp_path):
    """CV-C2: boxes=None must not crash, and missed frames must be
    marked (fi, None, None, 0.0) instead of silently dropped."""
    video = str(tmp_path / "cam.mp4")
    _write_black_video(video, n_frames=3)
    traj = detect_ball_trajectory(video, _FakeModel(boxes=None))
    assert traj == [(0, None, None, 0.0), (1, None, None, 0.0), (2, None, None, 0.0)]
    # Fusing a missed trajectory yields no fused frames (no crash).
    assert fuse_trajectories([traj]) == {}


def test_fusion_no_ball_class_raises(tmp_path):
    """CV-C2: a model with no ball class must fail loudly, not pick
    another class as the ball."""
    video = str(tmp_path / "cam.mp4")
    _write_black_video(video, n_frames=1)

    class _NoBallModel(_FakeModel):
        names = {0: 'person', 1: 'pad'}

    with pytest.raises(ValueError, match="no ball class"):
        detect_ball_trajectory(video, _NoBallModel())


def test_multi_camera_lbw_empty_input_inconclusive():
    """CV-L3: empty video list must not raise ValueError from max()."""
    res = multi_camera_lbw([], _FakeModel())
    assert res['decision'] == 'INCONCLUSIVE'


# ---------------------------------------------------------------- CV-C3
def _curved_traj(sign):
    """Diagonal trajectory with a sinusoidal deviation of +/-30 px in x
    (the QA report's reproduction shape)."""
    n = 21
    return [(i * 5 + sign * 30 * math.sin(math.pi * i / (n - 1)), i * 5)
            for i in range(n)]


def test_swing_direction_both_signs():
    """CV-C3: a consistent curve must not always be 'in'. The +30 px
    curve is 'in' and the mirrored -30 px curve is 'out'."""
    dev_pos, dir_pos = measure_lateral(_curved_traj(+1), 0, 20, 1280)
    dev_neg, dir_neg = measure_lateral(_curved_traj(-1), 0, 20, 1280)
    assert dev_pos > 10 and dir_pos == 'in'
    assert dev_neg > 10 and dir_neg == 'out'


# ---------------------------------------------------------------- CV-H8
def test_calibration_validation():
    """CV-H8: fps=0 / pixels_per_meter=0 must not ZeroDivisionError, and
    a negative scale must not return a negative speed."""
    traj = [(0, 0), (100, 0)]
    with pytest.raises(ValueError):
        estimate_speed(traj, fps=0)
    with pytest.raises(ValueError):
        estimate_speed(traj, fps=30, pixels_per_meter=0)
    with pytest.raises(ValueError):
        estimate_speed(traj, fps=30, pixels_per_meter=-50)
    with pytest.raises(ValueError):
        analyze_delivery([(0, 0)] * 6, frame_width=0)


def test_speed_calibrated_from_stump_height():
    """CV-H7: stump height in px derives pixels_per_meter."""
    traj = [(0, 0), (100, 0)]
    # 100 px at 100 px/m = 1 m in 0.1 s (fps=10, 2 points) = 36 km/h.
    assert estimate_speed(traj, fps=10, stump_height_px=71.1) == pytest.approx(36.0)


# ---------------------------------------------------------------- CV-C5 / CV-H1
def _make_tracker(**kwargs):
    kwargs.setdefault('preset', 'realtime')
    return RealtimeTracker(**kwargs)


def test_tracker_reset_clears_trajectory():
    """CV-C5: reset() must clear ball_trajectory so the next video
    does not inherit the previous video's points."""
    tracker = _make_tracker()
    tracker.ball_trajectory.append((1, 2))
    tracker.ball_trajectory.append((3, 4))
    tracker.frame_count = 99
    tracker.reset()
    assert list(tracker.ball_trajectory) == []
    assert tracker.frame_count == 0
    tracker.close()


def test_tracker_skipped_frames_interpolated_not_duplicated():
    """CV-H1: with frame_skip=2, skipped frames must NOT re-append the
    last detection, and the gap must be filled with real linear
    interpolation once the next detection brackets it."""
    tracker = _make_tracker(frame_skip=2)
    positions = iter([(0.0, 0.0), (20.0, 0.0)])
    tracker._infer = lambda frame: {'ball': {'pos': next(positions), 'conf': 0.9}}
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    r1 = tracker.track(frame)   # fid 1: skipped
    assert r1['ball'] is None and r1['interpolated'] is True
    assert list(tracker.ball_trajectory) == []
    r2 = tracker.track(frame)   # fid 2: first real detection
    assert r2['ball'] == (0.0, 0.0)
    r3 = tracker.track(frame)   # fid 3: skipped
    assert r3['ball'] is None
    r4 = tracker.track(frame)   # fid 4: brackets the gap
    assert list(tracker.ball_trajectory) == [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    tracker.close()


def test_default_model_is_v4_and_missing_model_fails_loudly():
    """CV-C4: the default must be the real v4 file, and a missing model
    must raise instead of silently falling back to COCO."""
    assert DEFAULT_MODEL_PATH == 'ai_model/cricket_ball_v4.pt'
    assert inspect.signature(RealtimeTracker.__init__).parameters[
        'model_path'].default == 'ai_model/cricket_ball_v4.pt'
    with pytest.raises(FileNotFoundError, match="Model file not found"):
        RealtimeTracker(model_path='ai_model/does_not_exist_xyz.pt')


# ---------------------------------------------------------------- CV-H4
def _blank_frame():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_failproof_prediction_cap_drops_track():
    """CV-H4: after max_predicted_frames consecutive predictions the
    track must be dropped (ball=None, source='lost'), not predicted
    forever."""
    tracker = FailproofTracker(yolo_models=[], max_predicted_frames=8)
    tracker.temporal.history.append((0.0, 0.0))
    tracker.temporal.history.append((10.0, 0.0))
    sources = [tracker.track(_blank_frame())['source'] for _ in range(10)]
    assert sources[:8] == ['predicted'] * 8
    last = tracker.track(_blank_frame())
    assert last['source'] == 'lost' and last['ball'] is None


def test_failproof_weighted_confidence_clamped():
    """CV-H4: a v4 weight of 1.5 on a 0.9 detection must not report
    ball_conf 1.35; weights rank only, confidence clamps to <= 1.0."""
    class _Yolo:
        names = {0: 'ball'}

        def predict(self, frame, verbose=False, imgsz=320, conf=0.15):
            box = _FakeBox(0, 0.9, [0, 0, 10, 10])
            return [_FakeResult([box])]

    tracker = FailproofTracker(yolo_models=[(_Yolo(), 1.5, 'ball-v4')])
    res = tracker.track(_blank_frame())
    assert res['source'] == 'yolo'
    assert res['ball_conf'] <= 1.0
    assert res['ball_conf'] == pytest.approx(1.0)


def test_failproof_rejected_jump_labelled_predicted():
    """CV-H4: a YOLO detection rejected as a >100 px jump must be
    reported as source='predicted' with prediction confidence, not
    as a high-confidence 'yolo' detection."""
    positions = iter([(5.0, 5.0), (500.0, 500.0)])

    class _Yolo:
        names = {0: 'ball'}

        def predict(self, frame, verbose=False, imgsz=320, conf=0.15):
            x, y = next(positions)
            box = _FakeBox(0, 0.95, [x, y, x + 10, y + 10])
            return [_FakeResult([box])]

    tracker = FailproofTracker(yolo_models=[(_Yolo(), 1.0, 'v')])
    first = tracker.track(_blank_frame())
    assert first['source'] == 'yolo'
    second = tracker.track(_blank_frame())
    assert second['source'] == 'predicted'
    assert second['ball_conf'] == pytest.approx(0.1)


# ---------------------------------------------------------------- CV-H6
def _lbw_3d_traj(pitch_y=0.0):
    """Smooth 3D delivery: bounce at t=7 (z local min), pad impact at
    t=13 (sharp direction change), heading at the stumps."""
    pts = []
    for t in range(14):
        x = -9.0 + 1.2 * t
        z = 0.1 + 0.005 * (t - 7) ** 2
        pts.append((x, pitch_y, z))
    pts.append((7.8, pitch_y, -0.5))  # deflected post-impact point
    return pts


def test_analyze_lbw_3d_hitting_and_residual_confidence():
    """CV-H6: a ball pitched in line, impacting in line and fitted
    through the stump segment must be OUT with a residual-based
    confidence (not min(95, 60+2*n) from point count)."""
    res = analyze_lbw_3d(_lbw_3d_traj())
    assert res is not None
    assert res['bounced'] is True
    assert res['pitch_3d'] is not None
    assert res['impact_in_line'] is True
    assert res['hitting_stumps'] is True
    assert res['decision'] == 'OUT'
    assert res['fit_rms_m'] is not None and res['fit_rms_m'] < 0.05


def test_analyze_lbw_3d_handedness_leg_side():
    """CV-H6: leg side must be parameterised, not hardcoded y<0."""
    traj = _lbw_3d_traj(pitch_y=-0.5)
    rhb = analyze_lbw_3d(traj, handedness='RHB')
    lhb = analyze_lbw_3d(traj, handedness='LHB')
    assert rhb['pitch_ok'] is False   # y=-0.5 is leg side for RHB
    assert lhb['pitch_ok'] is True    # y=-0.5 is off side for LHB
    with pytest.raises(ValueError):
        analyze_lbw_3d(traj, handedness='XXX')


# ---------------------------------------------------------------- CV-H10
def test_fuse_offset_validation_and_seconds_conversion():
    """CV-H10: offset length mismatch raises; seconds offsets convert
    via per-camera fps; negative synced frames are dropped."""
    trajs = [[(0, 1, 2, 0.9), (1, 3, 4, 0.9)],
             [(0, 5, 6, 0.8), (1, 7, 8, 0.8)]]
    with pytest.raises(ValueError, match="frame_offsets"):
        fuse_trajectories(trajs, frame_offsets=[0])
    fused = fuse_trajectories(trajs, offset_seconds=[0.0, 1.0],
                              fps_list=[30, 60])
    assert 60 in fused and fused[60][0][0] == 1
    with pytest.raises(ValueError, match="fps_list"):
        fuse_trajectories(trajs, offset_seconds=[0.0, 1.0])
    dropped = fuse_trajectories([[(0, 1, 2, 0.9)], [(0, 5, 6, 0.8)]],
                                frame_offsets=[0, -1])
    assert dropped == {0: [(0, 1, 2, 0.9)]}


# ---------------------------------------------------------------- CV-C5 (fps) / CV-C4 (surface)
def test_lbw_rules_effective_fps_and_fallback_flag():
    """CV-C5: analyze_lbw_rules must pass fps through to
    ball_physics (speed halves when fps halves); CV-C4: the tracker's
    using_fallback flag must surface in the result."""
    from core_processing.drs_logic import analyze_lbw_rules
    traj = [(100 + 50 * i, 300) for i in range(11)]
    tracking = {'ball': (600, 300), 'trajectory': traj,
                'metrics': {'using_fallback': True}}
    fast = analyze_lbw_rules(tracking, 1000, fps=30)
    slow = analyze_lbw_rules(tracking, 1000, fps=15)
    assert fast is not None and slow is not None
    assert fast['using_fallback'] is True
    sf = fast['delivery_analysis']['speed_kmh']
    ss = slow['delivery_analysis']['speed_kmh']
    assert sf is not None and ss is not None
    assert sf == pytest.approx(2 * ss, rel=0.05)
