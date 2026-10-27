"""
Production-grade real-time cricket tracker.
World-class engineering: fast, robust, observable.

Features:
  - Configurable inference size (320 = real-time, 416 = balanced, 640 = accurate)
  - Frame skipping: skipped frames are NOT re-appended as fresh points.
    When the next real detection arrives, the skipped gap is filled with
    real linear interpolation between the two bracketing detections
    (CV-H1). A skipped frame itself returns ball=None, interpolated=True.
  - Threaded inference (non-blocking)
  - Performance metrics: 'est_fps' is INFERENCE-ONLY (mean infer time);
    'end_to_end_fps' is the wall-clock frames/elapsed figure (CV-H2).
    No end-to-end FPS number is claimed here: any published number must
    state hardware, resolution, model and preset alongside it.
  - No silent model downgrade (CV-C4): the default model is the real
    v4 ball-specialist file. If no model file is present the tracker
    FAILS LOUDLY (FileNotFoundError) instead of silently running COCO.
    A COCO fallback is only used when a caller explicitly opts in with
    allow_coco_fallback=True, and then 'using_fallback' is True in every
    result's metrics so the API/DB can record it.
  - Ball trajectory smoothing (Kalman jaisa simple filter)

Usage:
    tracker = RealtimeTracker(model_path='ai_model/cricket_ball_v4.pt',
                              imgsz=320, frame_skip=1)
    result = tracker.track(frame)  # har frame par call karo
    # result: {'ball': (x,y)|None, 'trajectory': [...], 'fps': ..., ...}
"""

import os
import time
import threading
import queue
from collections import deque

import torch
from ultralytics import YOLO


# Default model: the real v4 ball-specialist file in the repo (CV-C4).
# The 3-class v3 file ai_model/cricket_yolo_v8.pt does NOT exist; it must
# never again be the default, and no silent COCO downgrade may replace it.
DEFAULT_MODEL_PATH = 'ai_model/cricket_ball_v4.pt'


def _resolve_model_path(model_path):
    """Resolve a model path independent of the caller's working directory.

    Tries, in order: the path as given, relative to this file's backend
    directory (backend/ai_model/...), and relative to the cwd. Returns the
    first existing path, else the path as given (so the caller can report
    it in the loud failure).
    """
    candidates = [model_path]
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(backend_dir, model_path))
    candidates.append(os.path.join(os.getcwd(), model_path))
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return model_path


# Performance presets — imgsz / frame_skip / conf only. No FPS is claimed
# for any preset here (CV-H2): the old "30+ FPS" comments were inference
# only and were never measured end-to-end on the production preset.
PRESETS = {
    'realtime':  {'imgsz': 320, 'frame_skip': 1, 'conf': 0.25},
    'balanced':  {'imgsz': 416, 'frame_skip': 1, 'conf': 0.25},
    'accurate':  {'imgsz': 640, 'frame_skip': 2, 'conf': 0.20},
}


class RealtimeTracker:
    def __init__(self, model_path=DEFAULT_MODEL_PATH,
                 preset='realtime', imgsz=None, frame_skip=None, conf=None,
                 threaded=False, trajectory_len=30,
                 allow_coco_fallback=False):
        """
        preset: 'realtime' | 'balanced' | 'accurate'
        Har parameter ko preset ke upar override kar sakte ho.
        threaded=True: inference alag thread me (non-blocking track()).
        """
        cfg = PRESETS.get(preset, PRESETS['realtime']).copy()
        if imgsz is not None:
            cfg['imgsz'] = imgsz
        if frame_skip is not None:
            cfg['frame_skip'] = frame_skip
        if conf is not None:
            cfg['conf'] = conf
        self.cfg = cfg

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model = None
        self.class_map = {}
        self.using_fallback = False
        self.allow_coco_fallback = allow_coco_fallback
        self._load_model(model_path)

        # State
        self.ball_trajectory = deque(maxlen=trajectory_len)
        self.trajectory_len = trajectory_len
        self.last_detections = {}
        self.frame_count = 0
        # Skipped-frame interpolation state (CV-H1): points skipped since
        # the last real ball detection, filled in only once the next real
        # detection brackets them. Never re-appended as fresh points.
        self._pending_skip_count = 0
        self._last_ball_pos = None
        # Threaded shared result (CV-H9): _last_dets/_last_fid are a pair,
        # guarded by one lock so a reader never sees a mixed pair.
        self._result_lock = threading.Lock()
        self._last_dets = {}
        self._last_fid = 0

        # Metrics
        self._infer_times = deque(maxlen=100)
        self._track_times = deque(maxlen=100)
        self._start_time = time.time()

        # Threading
        self.threaded = threaded
        self._infer_queue = queue.Queue(maxsize=2)
        self._result_queue = queue.Queue(maxsize=2)
        self._thread = None
        if threaded:
            self._start_thread()

    def _load_model(self, model_path):
        """Model load karo. CV-C4: no silent COCO downgrade.

        The model file must exist. If it does not, raise FileNotFoundError
        loudly — a decision pipeline must never silently run on a generic
        sports-ball model. A COCO fallback happens ONLY when the caller
        explicitly passed allow_coco_fallback=True, and then
        self.using_fallback is True so results record it.
        """
        resolved = _resolve_model_path(model_path)
        if not os.path.exists(resolved):
            raise FileNotFoundError(
                f"[RealtimeTracker] Model file not found: {model_path} "
                f"(resolved to {resolved}). Refusing to fall back to a "
                f"generic COCO model: place the real cricket model at "
                f"ai_model/cricket_ball_v4.pt (v4 ball specialist) and retry."
            )
        try:
            self.model = YOLO(resolved)
            self.model.to(self.device)
        except Exception as e:
            if not self.allow_coco_fallback:
                raise RuntimeError(
                    f"[RealtimeTracker] Failed to load model {resolved}: {e}. "
                    f"Refusing silent COCO fallback (allow_coco_fallback=False)."
                ) from e
            print(f"[RealtimeTracker] Custom model fail ({e}), COCO fallback...")
            try:
                self.model = YOLO('yolov8n.pt')
                self.model.to(self.device)
                # COCO: 32 = sports ball
                self.class_map = {32: 'ball'}
                self.using_fallback = True
                print("[RealtimeTracker] COCO fallback ready (sirf ball).")
            except Exception as e2:
                print(f"[RealtimeTracker] Fallback bhi fail: {e2}")
                self.model = None
            return
        # Filtered class map ONLY (CV-H9): the old code built a filtered
        # map and then immediately overwrote it with the unfiltered map,
        # leaking person/wicket/etc. classes into detections. Keep only
        # ball/pad/bat ('sports ball' counts as ball for COCO-style names).
        names = self.model.names
        self.class_map = {}
        for cid, name in names.items():
            if name == 'sports ball':
                self.class_map[cid] = 'ball'
            elif name in ('ball', 'pad', 'bat'):
                self.class_map[cid] = name
        print(f"[RealtimeTracker] Custom model loaded: {resolved} "
              f"({self.device}, imgsz={self.cfg['imgsz']}, "
              f"classes={self.class_map})")

    def reset(self):
        """Per-video/per-task state reset (CV-C5).

        Call before processing a new video. Without this, the previous
        video's ball_trajectory contaminated the next video's decisions.
        """
        self.ball_trajectory.clear()
        self.last_detections = {}
        self.frame_count = 0
        self._pending_skip_count = 0
        self._last_ball_pos = None
        with self._result_lock:
            self._last_dets = {}
            self._last_fid = 0
        self._infer_times.clear()
        self._track_times.clear()
        self._start_time = time.time()

    def _start_thread(self):
        def _worker():
            while True:
                item = self._infer_queue.get()
                if item is None:
                    break
                frame, fid = item
                t0 = time.time()
                dets = self._infer(frame)
                dt = time.time() - t0
                self._infer_times.append(dt)
                # Purana result hatao, naya rakho
                while not self._result_queue.empty():
                    try:
                        self._result_queue.get_nowait()
                    except queue.Empty:
                        break
                self._result_queue.put((fid, dets))
        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def _infer(self, frame):
        """YOLO inference — sirf detection, koi tracking nahi."""
        if self.model is None:
            return {}
        results = self.model.predict(
            frame, verbose=False,
            imgsz=self.cfg['imgsz'],
            conf=self.cfg['conf'],
        )[0]
        dets = {}
        if results.boxes is not None:
            for box in results.boxes:
                cid = int(box.cls[0])
                label = self.class_map.get(cid)
                if label is None:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                conf = float(box.conf[0])
                # Har class ka best detection rakho
                if label not in dets or conf > dets[label][2]:
                    dets[label] = (cx, cy, conf)
        # (x, y, conf) -> (x, y) + conf alag
        return {k: {'pos': (v[0], v[1]), 'conf': v[2]} for k, v in dets.items()}

    def track(self, frame):
        """
        Har frame par call karo. Frame skip + interpolation automatic.
        Returns: {
            'ball': (x, y) | None,
            'ball_conf': float,
            'detections': {'pad': {...}, 'bat': {...}},
            'trajectory': [(x, y), ...],
            'frame_id': int,
            'interpolated': bool,  # kya ye frame skip ki wajah se andaza hai
            'metrics': {...},
        }
        """
        t0 = time.time()
        self.frame_count += 1
        fid = self.frame_count
        skip = self.cfg['frame_skip']
        # CV-H1: clean every-Nth pattern. The old `fid == 1` special case
        # made the first interval irregular (frames 1, 2, 4, 6, ... for
        # skip=2); it is dropped, not preserved.
        should_infer = (fid % skip == 0)

        dets = {}
        interpolated = False

        if self.threaded:
            if should_infer:
                try:
                    self._infer_queue.put_nowait((frame.copy(), fid))
                except queue.Full:
                    pass  # purana frame abhi process ho raha — skip
            # Latest available result lo (non-blocking), pair under lock.
            while True:
                try:
                    rfid, rdets = self._result_queue.get_nowait()
                    with self._result_lock:
                        self._last_dets, self._last_fid = rdets, rfid
                except queue.Empty:
                    break
            with self._result_lock:
                dets, last_fid = self._last_dets, self._last_fid
            if not should_infer or last_fid != fid:
                # Skipped frame or stale threaded result: NEVER re-append
                # the old detection as a fresh point (old CV-H1 bug).
                # The gap is interpolated later, once a bracketing
                # detection exists (see below).
                self._pending_skip_count += 1
                interpolated = True
                dt = time.time() - t0
                self._track_times.append(dt)
                return {
                    'ball': None,
                    'ball_conf': 0.0,
                    'detections': {},
                    'trajectory': list(self.ball_trajectory),
                    'frame_id': fid,
                    'interpolated': interpolated,
                    'metrics': self.get_metrics(),
                }
        else:
            if should_infer:
                t1 = time.time()
                dets = self._infer(frame)
                self._infer_times.append(time.time() - t1)
                self.last_detections = dets
            else:
                # Skipped frame: record the gap, return no fresh point.
                self._pending_skip_count += 1
                interpolated = True
                dt = time.time() - t0
                self._track_times.append(dt)
                return {
                    'ball': None,
                    'ball_conf': 0.0,
                    'detections': {},
                    'trajectory': list(self.ball_trajectory),
                    'frame_id': fid,
                    'interpolated': interpolated,
                    'metrics': self.get_metrics(),
                }

        # Ball trajectory update, with REAL linear interpolation (CV-H1):
        # if frames were skipped since the last real ball point, fill the
        # gap with evenly spaced points between the bracketing detections
        # before appending the new point.
        ball = dets.get('ball')
        if ball is not None:
            new_pos = ball['pos']
            if self._pending_skip_count and self._last_ball_pos is not None:
                n = self._pending_skip_count
                x0, y0 = self._last_ball_pos
                x1, y1 = new_pos
                for k in range(1, n + 1):
                    f = k / (n + 1)
                    self.ball_trajectory.append(
                        (x0 + f * (x1 - x0), y0 + f * (y1 - y0)))
            self.ball_trajectory.append(new_pos)
            self._last_ball_pos = new_pos
            self._pending_skip_count = 0
        else:
            # Inference ran but found no ball: the gap stays open; a later
            # detection still brackets it, a lost ball simply leaves it out.
            pass

        dt = time.time() - t0
        self._track_times.append(dt)

        return {
            'ball': ball['pos'] if ball else None,
            'ball_conf': ball['conf'] if ball else 0.0,
            'detections': {k: v for k, v in dets.items() if k != 'ball'},
            'trajectory': list(self.ball_trajectory),
            'frame_id': fid,
            'interpolated': interpolated,
            'metrics': self.get_metrics(),
        }

    def get_metrics(self):
        """Performance metrics — monitoring ke liye.

        CV-H2: 'est_fps' is INFERENCE-ONLY (1 / mean infer time) and must
        never be quoted as the tracker's speed. 'end_to_end_fps' is the
        wall-clock figure (frames processed / seconds since start/reset,
        including capture, preprocessing and track overhead); it still
        carries no benchmark conditions unless the caller records
        hardware, resolution, model and preset alongside it.
        """
        infer = list(self._infer_times)
        track = list(self._track_times)
        elapsed = time.time() - self._start_time
        return {
            'avg_infer_ms': round(sum(infer) / len(infer) * 1000, 1) if infer else 0,
            'avg_track_ms': round(sum(track) / len(track) * 1000, 1) if track else 0,
            'est_fps': round(1 / (sum(infer) / len(infer)), 1) if infer else 0,
            'end_to_end_fps': round(self.frame_count / elapsed, 1) if elapsed > 0 else 0,
            'frames_processed': self.frame_count,
            'device': self.device,
            'using_fallback': self.using_fallback,
            'uptime_s': round(elapsed, 1),
        }

    def close(self):
        """Threaded mode me safai (CV-H9: never block forever).

        The old blocking put(None) into a maxsize=2 queue could hang
        indefinitely when the queue was full, despite join(timeout=2).
        """
        if self.threaded and self._thread:
            try:
                self._infer_queue.put_nowait(None)
            except queue.Full:
                try:
                    self._infer_queue.get_nowait()
                    self._infer_queue.put_nowait(None)
                except queue.Empty:
                    pass
                except queue.Full:
                    pass
            self._thread.join(timeout=2)
