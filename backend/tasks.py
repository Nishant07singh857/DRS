from models.review import Review
from core_processing.video_preprocessor import preprocess_for_ai
from core_processing.tracking_engine import ObjectTracker
from core_processing.drs_logic import analyze_lbw_rules
from celery import current_app as celery
from extensions import db
from config import Config
import cv2
import os

# Tracker ek baar worker start hone par load hota hai (YOLO model heavy hai).
tracker = ObjectTracker()

# Har Nth frame par tracking chalao — poori video par YOLO chalana bahut slow hai.
# Env se badal sakte ho: TRACK_EVERY_N_FRAMES=1 (sab frames) ya 3 (tez, thoda kam accurate).
TRACK_EVERY_N_FRAMES = int(os.getenv("TRACK_EVERY_N_FRAMES", "2"))


@celery.task(bind=True)
def process_video_task(self, video_path, user_id):
    """
    DRS analysis ke liye video process karo.

    Failure par exception raise hota hai taaki Celery task ko sahi me
    FAILURE mark kare (pehle exception nigal kar SUCCESS jaisa response
    lautata tha — wo bug tha).
    """
    cap = None
    try:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames <= 0:
            # Kuch codecs frame count nahi dete — us case me bhi aage badho,
            # read loop khud ruk jayega.
            total_frames = 1

        frame_number = 0
        decisions = []

        self.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": total_frames, "status": "Processing video..."},
        )

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_number += 1

            if frame_number % 10 == 0:
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "current": frame_number,
                        "total": total_frames,
                        "status": f"Processing frame {frame_number}/{total_frames}",
                    },
                )

            # Sampling: har Nth frame par hi heavy tracking chalao
            if frame_number % TRACK_EVERY_N_FRAMES != 0:
                continue

            processed_frame = preprocess_for_ai(frame)
            tracking_data = tracker.track(processed_frame)
            lbw_analysis = analyze_lbw_rules(
                tracking_data, frame.shape[1], frame.shape[0]
            )

            if lbw_analysis:
                decisions.append(lbw_analysis)

        final_decision_data = None
        if decisions:
            final_decision_data = max(decisions, key=lambda x: x.get("confidence", 0))

            review = Review(
                user_id=user_id,
                video_path=video_path,
                decision=final_decision_data["final_decision"],
                confidence=final_decision_data["confidence"],
                analysis_data=final_decision_data,
            )
            db.session.add(review)
            db.session.commit()

        return {
            "status": "SUCCESS",
            "result": final_decision_data,
            "total_frames_processed": frame_number,
            "decisions_evaluated": len(decisions),
        }

    except Exception:
        db.session.rollback()
        # Exception ko dobara raise karo taaki Celery FAILURE state record kare
        raise
    finally:
        if cap is not None:
            cap.release()
