"""
Fail-proof ball tracking system — model kabhi fail na ho.

Strategy (world-class robustness):
1. ENSEMBLE: v1 (aggressive) + v3/v4 (precise) — dono se detect karo
2. MOTION FALLBACK: YOLO fail ho to frame differencing se moving ball dhoondo
3. TEMPORAL TRACKING: pichhle frames se ball ki position predict karo
   (agar ek frame me miss ho to trajectory se andaza lagao)

Ye system single model se kahin zyada robust hai.
"""

import cv2
import numpy as np
import math
from collections import deque


class MotionDetector:
    """Frame differencing se moving objects dhoondo (YOLO fallback).

    CV-H5: the reference frame is updated EVERY frame (see
    FailproofTracker.track, which calls update_reference() even when
    YOLO hits). The old code updated prev_gray only inside detect(),
    which track() called only on YOLO misses — so after 30 YOLO-hit
    frames the next motion diff was against a 30-frame-old frame and
    bowler/batsman/umpire movement flooded the detector.
    Area limits are defined at a 1280x720 reference frame and scaled
    linearly by frame pixel count, instead of fixed pixels at any
    resolution.
    """

    # Reference resolution the area limits were tuned at.
    REF_PIXELS = 1280 * 720

    def __init__(self, min_area=50, max_area=5000):
        self.min_area = min_area
        self.max_area = max_area
        self.prev_gray = None

    def update_reference(self, frame):
        """Advance the background reference to this frame, unconditionally."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.prev_gray = cv2.GaussianBlur(gray, (5, 5), 0)

    def detect(self, frame):
        """
        Returns: [(x, y, area), ...] — moving blobs ke centers.
        Ball chhoti aur tez hoti hai, isliye area filter zaroori hai.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if self.prev_gray is None:
            self.prev_gray = gray
            return []

        # Frame difference
        diff = cv2.absdiff(self.prev_gray, gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        thresh = cv2.dilate(thresh, None, iterations=2)

        # Contours
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Scale area limits by frame size (CV-H5).
        h, w = frame.shape[:2]
        scale = (h * w) / self.REF_PIXELS if self.REF_PIXELS else 1.0
        min_area = self.min_area * scale
        max_area = self.max_area * scale

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if min_area < area < max_area:
                M = cv2.moments(cnt)
                if M['m00'] > 0:
                    cx = M['m10'] / M['m00']
                    cy = M['m01'] / M['m00']
                    detections.append((cx, cy, area))

        self.prev_gray = gray
        # Sabse chhota (ball jaisa) pehle
        detections.sort(key=lambda d: d[2])
        return detections


class TemporalTracker:
    """Ball ki position ko frames ke across track karo."""

    def __init__(self, max_history=10, max_jump_px=100):
        self.history = deque(maxlen=max_history)
        self.max_jump = max_jump_px
        # CV-H4: True when the last update() rejected a detection as a
        # >max_jump jump. Callers must then label the returned point
        # 'predicted', never 'yolo'.
        self.last_rejected = False

    def update(self, pos):
        """Nayi detection do, smoothed position lo."""
        self.last_rejected = False
        if pos is None:
            return self.predict()

        if self.history:
            last = self.history[-1]
            dist = math.sqrt((pos[0]-last[0])**2 + (pos[1]-last[1])**2)
            if dist > self.max_jump:
                # Bahut bada jump — galat detection, ignore karo
                self.last_rejected = True
                return self.predict()

        self.history.append(pos)
        return self.smooth()

    def predict(self):
        """Agli position ka andaza (linear extrapolation)."""
        if len(self.history) < 2:
            return self.history[-1] if self.history else None
        # Last 2 se velocity
        (x1, y1), (x2, y2) = self.history[-2], self.history[-1]
        vx, vy = x2-x1, y2-y1
        return (x2 + vx, y2 + vy)

    def smooth(self):
        """Recent history ka weighted average (naya zyada important)."""
        if not self.history:
            return None
        n = len(self.history)
        weights = [i+1 for i in range(n)]
        total = sum(weights)
        x = sum(p[0]*w for p, w in zip(self.history, weights)) / total
        y = sum(p[1]*w for p, w in zip(self.history, weights)) / total
        return (x, y)

    def reset(self):
        self.history.clear()


class FailproofTracker:
    """
    Kabhi fail na hone wala tracker.

    Pipeline har frame par:
    1. YOLO ensemble se detect karo (v1 + v3/v4)
    2. Agar YOLO ne ball nahi diya → motion detector try karo
    3. Temporal tracker se smooth/predict karo
    4. Confidence score do (kitna bharosa hai)
    """

    def __init__(self, yolo_models=None, imgsz=320, max_predicted_frames=8):
        """
        yolo_models: [(YOLO_model, weight, name), ...]
        Agar None to sirf motion + temporal (YOLO ke bina bhi kaam karega!)
        max_predicted_frames (CV-H4): after this many consecutive
        prediction-only frames the track is dropped (ball=None,
        source='lost') instead of predicting forever.
        """
        self.yolo_models = yolo_models or []
        self.imgsz = imgsz
        self.max_predicted_frames = max_predicted_frames
        self.consecutive_predicted = 0
        self.motion = MotionDetector()
        self.temporal = TemporalTracker()
        self.frame_count = 0

        # Stats
        self.yolo_hits = 0
        self.motion_hits = 0
        self.predicted = 0

    def track(self, frame):
        self.frame_count += 1
        h, w = frame.shape[:2]

        ball_pos = None
        ball_conf = 0.0
        source = 'none'

        # Step 1: YOLO ensemble
        best_ball = None
        best_conf = 0
        for model, weight, name in self.yolo_models:
            try:
                r = model.predict(frame, verbose=False,
                                  imgsz=self.imgsz, conf=0.15)[0]
                for b in r.boxes:
                    if model.names[int(b.cls)] == 'ball':
                        # CV-H4: weights rank models only; the reported
                        # confidence is clamped to <= 1.0 (the old
                        # v4 weight 1.5 produced ball_conf up to 1.35).
                        conf = min(1.0, float(b.conf) * weight)
                        if conf > best_conf:
                            x1, y1, x2, y2 = b.xyxy[0].tolist()
                            best_ball = ((x1+x2)/2, (y1+y2)/2)
                            best_conf = conf
            except Exception:
                continue  # ek model fail ho to doosra try karo

        if best_ball is not None:
            ball_pos, ball_conf = best_ball, best_conf
            source = 'yolo'
            self.yolo_hits += 1
        else:
            # Step 2: Motion fallback — ONLY near the predicted track
            # (CV-H5). With no prediction/history there is no track to
            # be near, so motion is NOT accepted: the old "smallest
            # motion blob is the ball" fallback locked onto fielders
            # and the umpire's arm.
            motions = self.motion.detect(frame)
            if motions:
                pred = self.temporal.predict()
                if pred is not None:
                    best = min(motions,
                               key=lambda m: (m[0]-pred[0])**2 + (m[1]-pred[1])**2)
                    dist = math.sqrt((best[0]-pred[0])**2 + (best[1]-pred[1])**2)
                    if dist < 150:  # reasonable range me
                        ball_pos, ball_conf = (best[0], best[1]), 0.3
                        source = 'motion'
                        self.motion_hits += 1
        # CV-H5: reference advances EVERY frame, even on YOLO hits
        # (detect() already advanced it on motion frames).
        if source != 'motion':
            self.motion.update_reference(frame)

        # Step 3: Temporal smoothing/prediction
        if ball_pos is not None:
            smoothed = self.temporal.update(ball_pos)
            if self.temporal.last_rejected:
                # CV-H4: the returned point is a PREDICTION, not the
                # YOLO detection — label it so, and do not keep the
                # YOLO confidence on it.
                source = 'predicted'
                ball_conf = 0.1
                self.predicted += 1
                self.consecutive_predicted += 1
            else:
                self.consecutive_predicted = 0
        else:
            smoothed = self.temporal.predict()
            if smoothed is not None:
                source = 'predicted'
                ball_conf = 0.1
                self.predicted += 1
                self.consecutive_predicted += 1
            else:
                self.consecutive_predicted = 0

        # CV-H4: cap consecutive predictions, then drop the track.
        if (source == 'predicted'
                and self.consecutive_predicted > self.max_predicted_frames):
            return {
                'ball': None,
                'ball_conf': 0.0,
                'source': 'lost',
                'frame_id': self.frame_count,
                'stats': {
                    'yolo_hits': self.yolo_hits,
                    'motion_hits': self.motion_hits,
                    'predicted': self.predicted,
                }
            }

        return {
            'ball': smoothed,
            'ball_conf': ball_conf,
            'source': source,  # 'yolo' | 'motion' | 'predicted' | 'lost' | 'none'
            'frame_id': self.frame_count,
            'stats': {
                'yolo_hits': self.yolo_hits,
                'motion_hits': self.motion_hits,
                'predicted': self.predicted,
            }
        }

    def reset(self):
        self.motion.prev_gray = None
        self.temporal.reset()
        self.frame_count = 0
        self.consecutive_predicted = 0


def create_optimal_tracker(ai_model_dir='ai_model'):
    """
    v4 ball specialist (if present) + motion fallback + temporal smoothing.

    CORRECTED docstring (CV-C4): the old docstring promised a "v4+v3
    ensemble", but this function can only ever load v4 as its YOLO
    model — the v3 file ai_model/cricket_yolo_v8.pt does not exist, so
    the v3 branch below is opportunistic (it loads only if that file
    ever appears) and is never part of the default tracker. What this
    actually builds: v4 (weight 1.5, used for ranking only, confidence
    clamped to <= 1.0) + MotionDetector + TemporalTracker, with a
    prediction cap (see FailproofTracker).
    """
    import os
    try:
        from ultralytics import YOLO
    except ImportError:
        return FailproofTracker()  # YOLO ke bina bhi kaam karega

    models = []
    v4_path = os.path.join(ai_model_dir, 'cricket_ball_v4.pt')
    if os.path.exists(v4_path):
        try:
            v4 = YOLO(v4_path)
            models.append((v4, 1.5, 'ball-v4'))
        except Exception:
            pass

    # v3 (3-class) bhi ho to pad/bat ke liye rakho
    v3_path = os.path.join(ai_model_dir, 'cricket_yolo_v8.pt')
    if os.path.exists(v3_path):
        try:
            v3 = YOLO(v3_path)
            models.append((v3, 1.0, 'v3'))
        except Exception:
            pass

    return FailproofTracker(yolo_models=models, imgsz=640)
