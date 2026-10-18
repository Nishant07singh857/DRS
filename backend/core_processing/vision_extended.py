"""
Extended AI Vision — StreetDRS spec module H (poora karo).

H3. Player detection — YOLO COCO 'person' class
H4. Stump detection — vertical line groups (3 stumps)
H5. Crease detection — horizontal white lines (Hough)

Ye heuristic + YOLO hybrid hai — trained stump model nahi,
lekin real footage par kaam karta hai.

Usage:
    from core_processing.vision_extended import ExtendedVision
    ev = ExtendedVision()
    result = ev.analyze_frame(frame)
    # → {'players': [...], 'stumps': {...}, 'creases': [...]}
"""

import cv2
import numpy as np


class ExtendedVision:
    def __init__(self, yolo_model=None):
        """
        yolo_model: ultralytics YOLO (COCO) — person detection ke liye.
        Agar None to player detection skip hoga.
        """
        self.yolo = yolo_model

    # --- H3: Player detection ---

    def detect_players(self, frame, conf=0.4):
        """
        YOLO COCO 'person' class se players dhoondo.
        Returns: [{'bbox': (x1,y1,x2,y2), 'confidence': ...}, ...]
        """
        if self.yolo is None:
            return []

        results = self.yolo.predict(frame, verbose=False, conf=conf)[0]
        players = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            # COCO class 0 = person
            if cls_id == 0:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                players.append({
                    'bbox': (round(x1), round(y1), round(x2), round(y2)),
                    'confidence': round(float(box.conf[0]), 2),
                    'center': (round((x1+x2)/2), round((y1+y2)/2)),
                })
        # Confidence se sort
        players.sort(key=lambda p: p['confidence'], reverse=True)
        return players

    # --- H4: Stump detection ---

    def detect_stumps(self, frame):
        """
        3 stumps = 3 vertical lines jo paas-paas hain.
        Hough lines + grouping se dhoondo.

        Returns: {'found': bool, 'x_center': ..., 'bboxes': [...], 'confidence': ...}
        Ya {'found': False}
        """
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Neeche ka hissa (stumps ground par hote hain)
        roi = gray[int(h*0.5):, :]

        # Edges
        edges = cv2.Canny(roi, 50, 150)

        # Vertical lines dhoondo
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=60,
                                 minLineLength=h*0.08, maxLineGap=10)
        if lines is None:
            return {'found': False}

        # Vertical lines filter karo (angle ~90°)
        vertical = []
        for l in lines:
            x1, y1, x2, y2 = l  # OpenCV 4.x: shape (N,4)
            # Vertical check: height > 2x width
            if abs(y2 - y1) > 2 * abs(x2 - x1) + 5:
                vertical.append((x1 + x2) / 2)  # x-center

        if len(vertical) < 2:
            return {'found': False}

        # Group karo: sorted order me, gap > 15px = naya stump
        # (Stump edges ~7px apart, adjacent stumps ~30px+ apart)
        vertical.sort()
        groups = [[vertical[0]]]
        for x in vertical[1:]:
            if x - groups[-1][-1] < 15:
                groups[-1].append(x)
            else:
                groups.append([x])

        # 3 groups = 3 stumps!
        if len(groups) >= 3:
            # Sabse strong 3 groups lo
            groups.sort(key=len, reverse=True)
            top3 = sorted([sum(g)/len(g) for g in groups[:3]])
            # Check: spacing roughly equal (stumps evenly spaced)
            d1 = top3[1] - top3[0]
            d2 = top3[2] - top3[1]
            spacing_ok = abs(d1 - d2) < max(d1, d2) * 0.5

            return {
                'found': True,
                'x_center': round(sum(top3) / 3),
                'stump_x': [round(x) for x in top3],
                'y_base': h,  # ground level
                'confidence': 85 if spacing_ok else 60,
                'spacing_ok': spacing_ok,
            }

        return {'found': False}

    # --- H5: Crease detection ---

    def detect_creases(self, frame):
        """
        Popping crease = horizontal white line.
        Hough lines se dhoondo.

        Returns: [{'y': ..., 'x1': ..., 'x2': ..., 'confidence': ...}, ...]
        """
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # White lines ke liye threshold
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

        edges = cv2.Canny(binary, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80,
                                 minLineLength=w*0.15, maxLineGap=20)
        if lines is None:
            return []

        creases = []
        for l in lines:
            x1, y1, x2, y2 = l  # OpenCV 4.x: shape (N,4)
            # Horizontal check: width > 3x height
            if abs(x2 - x1) > 3 * abs(y2 - y1) + 5:
                # Neeche ka hissa (crease ground par)
                y_avg = (y1 + y2) / 2
                if y_avg > h * 0.4:
                    creases.append({
                        'y': round(y_avg),
                        'x1': round(min(x1, x2)),
                        'x2': round(max(x1, x2)),
                        'confidence': 70,
                    })

        # Duplicate lines hatao (paas-paali)
        filtered = []
        for c in sorted(creases, key=lambda x: x['y']):
            if not any(abs(c['y'] - f['y']) < 15 for f in filtered):
                filtered.append(c)

        return filtered

    # --- Full frame analysis ---

    def analyze_frame(self, frame):
        """
        Ek frame me sab kuch detect karo.
        Returns: {'players': [...], 'stumps': {...}, 'creases': [...]}
        """
        return {
            'players': self.detect_players(frame),
            'stumps': self.detect_stumps(frame),
            'creases': self.detect_creases(frame),
        }
