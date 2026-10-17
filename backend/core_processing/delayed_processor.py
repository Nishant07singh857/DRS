"""
Delayed Live Processor — "10 second baad auto process"

Workflow (jaise TV broadcast me hota hai):
1. Video record hoti rehti hai (continuous)
2. Har ball ke 10 second baad, us ball ka clip auto-process hota hai
3. LBW decision + analysis ready!

Kyun 10 second delay?
- Ball ko pitch se pad tak pahunchne me ~2 sec lagta hai
- Trajectory complete hone me ~3 sec
- Processing me ~5 sec (YOLO + physics + LBW)
- Total: ~10 sec = TV broadcast delay jaisa!

Usage:
    from core_processing.delayed_processor import DelayedProcessor

    dp = DelayedProcessor(delay_sec=10)

    # Option A: Poori video file do
    result = dp.process_ball("match_video.mp4", ball_start_sec=45.0)
    # → 45s se 55s tak ka clip process hoga (10 sec baad jaisa)

    # Option B: Live stream (continuous)
    dp.start_live("http://phone-ip:8080/video")
    # Har 10 sec me pichhle ball ka result aayega
"""

import cv2
import time
import os
import tempfile
from collections import deque


class DelayedProcessor:
    def __init__(self, delay_sec=10, clip_duration=8):
        """
        delay_sec: ball ke kitne sec baad process karna hai
        clip_duration: kitne sec ka clip lena hai (ball ke aas-paas)
        """
        self.delay_sec = delay_sec
        self.clip_duration = clip_duration
        # Tracker lazy load (torch heavy hai)
        self._tracker = None
        self._v3_model = None

    def _get_tracker(self):
        if self._tracker is None:
            from core_processing.realtime_tracker import RealtimeTracker
            self._tracker = RealtimeTracker(preset='realtime')
        return self._tracker

    def _get_model(self):
        if self._v3_model is None:
            from ultralytics import YOLO
            # v3 model dhoondo
            import glob
            candidates = [
                '/tmp/DRS/backend/ai_model/cricket_yolo_v8.pt',
                os.path.expanduser('~/workspace/drs-test/training/cricket_v3/weights/best.pt'),
            ]
            for p in candidates:
                if os.path.exists(p):
                    self._v3_model = YOLO(p)
                    break
        return self._v3_model

    def extract_clip(self, video_path, start_sec, duration_sec, output_path=None):
        """
        Video se clip nikalo.
        Returns: clip ka path
        """
        if output_path is None:
            output_path = tempfile.mktemp(suffix='.mp4')

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        start_frame = int(start_sec * fps)
        end_frame = int((start_sec + duration_sec) * fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

        for _ in range(start_frame, end_frame):
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)

        cap.release()
        out.release()
        return output_path

    def process_ball(self, video_path, ball_start_sec):
        """
        Ek ball ko process karo (10 sec delay ke baad jaisa).

        video_path: poori match video
        ball_start_sec: ball kab start hui (seconds me)

        Returns: {
            'decision': 'OUT' | 'NOT OUT' | ...,
            'confidence': float,
            'speed_kmh': float,
            'delivery_type': str,
            'trajectory': [...],
            'processing_time_s': float,
        }
        """
        t0 = time.time()
        print(f"Ball at {ball_start_sec:.1f}s — processing (10s delayed)...")

        # 1. Clip nikalo (ball ke 2 sec pehle se 6 sec baad tak)
        clip_start = max(0, ball_start_sec - 2)
        clip_path = self.extract_clip(video_path, clip_start, self.clip_duration)
        print(f"  Clip: {clip_start:.1f}s - {clip_start + self.clip_duration:.1f}s")

        # 2. Ball track karo
        tracker = self._get_tracker()
        # Reset tracker (nayi ball = nayi trajectory)
        if hasattr(tracker, 'ball_trajectory'):
            tracker.ball_trajectory.clear()

        cap = cv2.VideoCapture(clip_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        trajectory = []
        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            result = tracker.track(frame)
            if result['ball'] is not None:
                trajectory.append(result['ball'])
        cap.release()

        # Temp clip hatao
        if os.path.exists(clip_path):
            os.unlink(clip_path)

        print(f"  Trajectory: {len(trajectory)} points")

        if len(trajectory) < 5:
            return {
                'decision': 'NO BALL TRACKED',
                'confidence': 0,
                'trajectory_points': len(trajectory),
                'processing_time_s': round(time.time() - t0, 1),
            }

        # 3. Cricket intelligence (speed, swing, spin)
        from core_processing.ball_physics import analyze_delivery
        physics = analyze_delivery(trajectory, fps=fps,
                                   frame_width=frame_w)

        # 4. LBW decision
        from core_processing.drs_logic import analyze_lbw_rules
        h = 720  # approximate
        lbw = analyze_lbw_rules(
            {'ball': trajectory[-1], 'trajectory': trajectory},
            frame_w, h
        )

        result = {
            'decision': lbw.get('decision', 'UNKNOWN') if lbw else 'UNKNOWN',
            'confidence': lbw.get('confidence', 0) if lbw else 0,
            'speed_kmh': physics.get('speed_kmh'),
            'delivery_type': physics.get('delivery_type'),
            'swing': physics.get('swing_direction'),
            'spin': physics.get('spin_direction'),
            'trajectory_points': len(trajectory),
            'processing_time_s': round(time.time() - t0, 1),
        }

        print(f"  Decision: {result['decision']} ({result['confidence']}%)")
        print(f"  {result['speed_kmh']} km/h, {result['delivery_type']}")
        return result

    def process_over(self, video_path, ball_times):
        """
        Poora over process karo.
        ball_times: [12.5, 45.0, 78.3, ...] — har ball ka start time (sec)
        """
        results = []
        for i, bt in enumerate(ball_times):
            print(f"\n--- Ball {i+1}/{len(ball_times)} ---")
            r = self.process_ball(video_path, bt)
            r['ball_number'] = i + 1
            r['ball_time_s'] = bt
            results.append(r)
            # 10 sec delay simulate (asli me yahan wait hoga)
            # time.sleep(self.delay_sec)  # comment out for testing
        return results
