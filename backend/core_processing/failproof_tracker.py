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
    """Frame differencing se moving objects dhoondo (YOLO fallback)."""

    def __init__(self, min_area=50, max_area=5000):
        self.min_area = min_area
        self.max_area = max_area
        self.prev_gray = None

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

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.min_area < area < self.max_area:
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

    def update(self, pos):
        """Nayi detection do, smoothed position lo."""
        if pos is None:
            return self.predict()

        if self.history:
            last = self.history[-1]
            dist = math.sqrt((pos[0]-last[0])**2 + (pos[1]-last[1])**2)
            if dist > self.max_jump:
                # Bahut bada jump — galat detection, ignore karo
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

    def __init__(self, yolo_models=None, imgsz=320):
        """
        yolo_models: [(YOLO_model, weight, name), ...]
        Agar None to sirf motion + temporal (YOLO ke bina bhi kaam karega!)
        """
        self.yolo_models = yolo_models or []
        self.imgsz = imgsz
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
                        conf = float(b.conf) * weight
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
            # Step 2: Motion fallback
            motions = self.motion.detect(frame)
            if motions:
                # Temporal prediction ke sabse kareeb wala motion chunno
                pred = self.temporal.predict()
                if pred is not None:
                    # Sabse kareeb motion
                    best = min(motions,
                               key=lambda m: (m[0]-pred[0])**2 + (m[1]-pred[1])**2)
                    dist = math.sqrt((best[0]-pred[0])**2 + (best[1]-pred[1])**2)
                    if dist < 150:  # reasonable range me
                        ball_pos, ball_conf = (best[0], best[1]), 0.3
                        source = 'motion'
                        self.motion_hits += 1
                else:
                    # Koi history nahi, sabse chhota motion lo
                    ball_pos, ball_conf = (motions[0][0], motions[0][1]), 0.2
                    source = 'motion'
                    self.motion_hits += 1

        # Step 3: Temporal smoothing/prediction
        if ball_pos is not None:
            smoothed = self.temporal.update(ball_pos)
        else:
            smoothed = self.temporal.predict()
            if smoothed is not None:
                source = 'predicted'
                ball_conf = 0.1
                self.predicted += 1

        return {
            'ball': smoothed,
            'ball_conf': ball_conf,
            'source': source,  # 'yolo' | 'motion' | 'predicted' | 'none'
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
