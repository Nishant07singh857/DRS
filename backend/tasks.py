from models.review import Review
from core_processing.video_preprocessor import preprocess_for_ai
from core_processing.tracking_engine import ObjectTracker
from core_processing.drs_logic import analyze_lbw_rules
from celery import current_app as celery
from app import db  # Import db from extensions
import cv2
import os

# Initialize tracker
tracker = ObjectTracker()

@celery.task(bind=True)
def process_video_task(self, video_path, user_id):
    """  
    Process video for DRS analysis using AI algorithms
    """  
    try:
        # Check if video file exists
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        cap = cv2.VideoCapture(video_path)  
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames == 0:
            raise ValueError("Video file has no frames")
            
        frame_number = 0  
        final_decision_data = None
        decisions = []

        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': total_frames,
                'status': 'Processing video...'
            }
        )

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break  
            
            frame_number += 1

            # Update progress
            if frame_number % 10 == 0:
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': frame_number,
                        'total': total_frames,
                        'status': f'Processing frame {frame_number}/{total_frames}'
                    }
                )

            # Preprocess frame for AI analysis
            processed_frame = preprocess_for_ai(frame)

            # Track objects in the frame
            tracking_data = tracker.track(processed_frame)

            # Analyze LBW rules
            lbw_analysis = analyze_lbw_rules(tracking_data, frame.shape[1])
            
            if lbw_analysis:
                decisions.append(lbw_analysis)
                final_decision_data = lbw_analysis

        cap.release()

        # Determine final decision
        if decisions:
            final_decision_data = max(decisions, key=lambda x: x.get('confidence', 0))
            
            # Save the result to database
            review = Review(
                user_id=user_id,
                video_path=video_path,
                decision=final_decision_data["final_decision"],
                confidence=final_decision_data["confidence"],
                analysis_data=final_decision_data
            )
            db.session.add(review)
            db.session.commit()

        return {
            'status': 'SUCCESS',
            'result': final_decision_data,
            'total_frames_processed': frame_number
        }

    except Exception as e:
        return {
            'status': 'FAILURE',
            'error': str(e)
        }