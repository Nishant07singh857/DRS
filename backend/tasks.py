from models.review import Review
from core_processing.video_preprocessor import preprocess_for_ai
from core_processing.realtime_tracker import RealtimeTracker
from core_processing.drs_logic import analyze_lbw_rules
from celery import current_app as celery
from extensions import db
from config import Config
import cv2
import os

# Production tracker — RealtimeTracker (frame skipping, metrics).
# Preset env se: TRACK_PRESET=realtime|balanced|accurate (default: balanced).
# No FPS number is claimed here (CV-H2): the old "36+ FPS" comment
# measured inference only, not the end-to-end pipeline, and production
# uses the balanced preset, not the realtime one.
_tracker_preset = os.environ.get('TRACK_PRESET', 'balanced')
tracker = RealtimeTracker(preset=_tracker_preset)

# Har Nth frame par tracking chalao — poori video par YOLO chalana bahut slow hai.
# Env se badal sakte ho: TRACK_EVERY_N_FRAMES=1 (sab frames) ya 3 (tez, thoda kam accurate).
TRACK_EVERY_N_FRAMES = int(os.getenv("TRACK_EVERY_N_FRAMES", "2"))


def _final_lbw_decision(last_tracking, frame_width, frame_height,
                        effective_fps):
    """BE-H7: video ka decision EK baar, poori (impact tak ki)
    trajectory par — har frame par analyze karke max-confidence lena
    galat tha, kyunki early-frame fixed confidences (no-ball 100,
    outside-leg 95, bat 90, missing 85) baad ke sahi frame ko hara
    dete the. Decision impact frame ka hota hai, max-confidence frame
    ka nahi.

    Evidence pass-through: tracker jahan explicit evidence deta hai
    (bat_involved / is_no_ball / playing_shot / on_field_call /
    handedness keys), wahi analyze_lbw_rules ko jaata hai. Sirf bat
    ki maujoodgi (detections me 'bat' dikhna) bat-contact ka saboot
    NAHI hai — isliye usse bat_involved=True infer nahi kiya jaata;
    jab tak koi contact evidence source nahi hai, defaults rehte hain
    (playing_shot=True, bat_involved=False, is_no_ball=False, RHB).
    Returns: LBW result dict, ya None (koi ball/trajectory hi nahi)."""
    if not last_tracking:
        return None
    trajectory = last_tracking.get('trajectory') or []
    ball = last_tracking.get('ball')
    if not ball or len(trajectory) < 3:
        return None
    kwargs = {}
    for key in ('is_no_ball', 'playing_shot', 'bat_involved',
                'on_field_call', 'handedness', 'stumps_zone',
                'leg_side_x'):
        if key in last_tracking and last_tracking[key] is not None:
            kwargs[key] = last_tracking[key]
    return analyze_lbw_rules(last_tracking, frame_width, frame_height,
                             fps=effective_fps, **kwargs)


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

        # CV-C5: reset the module-global tracker for THIS video/task.
        # Without this, the previous video's ball_trajectory contaminated
        # the next video's decisions (cross-video contamination).
        # Phase 1's TaskOwnership write in analysis.py is untouched.
        # Defensive form: a tracker-like test double without reset()
        # (test_api's FakeTracker) still gets its trajectory cleared if
        # it exposes one, so the reset contract never breaks a caller.
        _reset = getattr(tracker, 'reset', None)
        if callable(_reset):
            _reset()
        elif hasattr(tracker, 'ball_trajectory'):
            try:
                tracker.ball_trajectory.clear()
            except Exception:
                pass

        cap = cv2.VideoCapture(video_path)
        # CV-C5: effective fps of the SAMPLED points. tasks samples every
        # TRACK_EVERY_N_FRAMES-th frame, so points are 1/(fps/N) s apart,
        # not 1/fps. Passing the camera fps alone overstated speed ~2x
        # at the default N=2. Fall back to 30 only if the container
        # reports no fps.
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if not video_fps or video_fps <= 0:
            video_fps = 30.0
        effective_fps = video_fps / max(1, TRACK_EVERY_N_FRAMES)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames <= 0:
            # Kuch codecs frame count nahi dete — us case me bhi aage badho,
            # read loop khud ruk jayega.
            total_frames = 1

        frame_number = 0
        # BE-H7: sirf AAKHRI tracking snapshot rakho — decision us par
        # ek baar hoga (loop ke baad), har sampled frame par nahi.
        last_tracking = None
        last_frame_width = None
        last_frame_height = None

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
            last_tracking = tracker.track(processed_frame)
            last_frame_width = frame.shape[1]
            last_frame_height = frame.shape[0]

        # BE-H7: decide ONCE, on the complete trajectory (jo impact par
        # khatam hoti hai) — CV-C5 effective fps ke saath.
        final_decision_data = _final_lbw_decision(
            last_tracking, last_frame_width, last_frame_height,
            effective_fps)

        if final_decision_data is None:
            # BE-H7: silent SUCCESS + no Review band — ab explicit
            # INCONCLUSIVE result milta hai, taaki caller jaan sake ki
            # koi decision nikla hi nahi (ball track nahi hui / video
            # bahut chhota), bajay iske ki SUCCESS dekhkar maan le ki
            # sab theek tha.
            return {
                "status": "INCONCLUSIVE",
                "result": None,
                "reason": "No ball trajectory / impact frame found — "
                          "koi LBW decision nahi nikla",
                "total_frames_processed": frame_number,
                "decisions_evaluated": 0,
            }

        # BE-H6: pipeline review ab workflow-consistent hai — AI
        # recommendation + status decision ke saath set hote hain, taaki
        # ReviewCenter ka canDecide gate fresh pipeline reviews par bhi
        # kaam kare (pehle status default 'pending' aur
        # ai_recommendation=None rehta tha, isliye confirm kabhi nahi
        # chalta tha jab tak complete AI decision ko overwrite na kare).
        review = Review(
            user_id=user_id,
            video_path=video_path,
            decision=final_decision_data["final_decision"],
            confidence=final_decision_data["confidence"],
            analysis_data=final_decision_data,
            ai_recommendation=final_decision_data["final_decision"],
            ai_confidence=final_decision_data["confidence"],
            status=('inconclusive'
                    if final_decision_data["final_decision"] == 'INCONCLUSIVE'
                    else 'completed'),
        )
        db.session.add(review)
        db.session.commit()

        return {
            "status": "SUCCESS",
            "result": final_decision_data,
            "total_frames_processed": frame_number,
            "decisions_evaluated": 1,
        }

    except Exception:
        db.session.rollback()
        # Exception ko dobara raise karo taaki Celery FAILURE state record kare
        raise
    finally:
        if cap is not None:
            cap.release()
