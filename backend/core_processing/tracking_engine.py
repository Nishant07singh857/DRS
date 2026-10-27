import torch
from ultralytics import YOLO
from collections import deque

class ObjectTracker:
    """
    एक प्रशिक्षित YOLO मॉडल का उपयोग करके क्रिकेट की वस्तुओं को ट्रैक करने के लिए एक क्लास।
    """
    def __init__(self, model_path='ai_model/cricket_ball_v4.pt'):
        """
        ट्रैकर को इनिशियलाइज़ करता है और YOLO मॉडल को लोड करता है.

        NOTE: dead code — imported nowhere in production (CV-C4 scope note).
        Default repointed from the non-existent ai_model/cricket_yolo_v8.pt
        to the real v4 ball-specialist file, matching RealtimeTracker.
        Its COCO fallback below is retained only because this module is
        uncalled; do NOT revive it without the same loud-fail rule as
        RealtimeTracker.

        Args:
            model_path (str): प्रशिक्षित YOLO मॉडल का पथ (.pt फ़ाइल)।
        """
        # डिवाइस चुनें: अगर GPU उपलब्ध है तो CUDA का उपयोग करें, अन्यथा CPU
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"YOLO मॉडल के लिए डिवाइस का उपयोग किया जा रहा है: {self.device}")

        # Default ab v4 ball specialist hai (cricket_yolo_v8.pt maujood nahi).
        # Jab tak custom model nahi hai, COCO-pretrained yolov8n fallback use hoga
        # (sirf 'sports ball' detect karega — pad/bat nahi).
        self.using_fallback = False
        try:
            self.model = YOLO(model_path)
            self.model.to(self.device)
            self.class_map = {"ball": "ball", "pad": "pad", "bat": "bat"}
            print(f"YOLO model '{model_path}' se load ho gaya (custom cricket model).")
        except Exception as e:
            print(f"Custom model '{model_path}' nahi mila ({e}).")
            print("Fallback: COCO-pretrained 'yolov8n' load ho raha hai (sirf sports ball).")
            try:
                self.model = YOLO("yolov8n.pt")  # pehli baar me auto-download hoga
                self.model.to(self.device)
                self.class_map = {"sports ball": "ball"}
                self.using_fallback = True
                print("Fallback model ready — ball detection chalegi, pad/bat nahi.")
            except Exception as e2:
                print(f"Fallback bhi fail: {e2}")
                self.model = None
                self.class_map = {}

        # बॉल की ट्रैजेक्टरी को स्टोर करने के लिए
        self.ball_trajectory = deque(maxlen=20)

    def track(self, frame):
        """
        दिए गए फ्रेम में वस्तुओं का पता लगाता है।

        Args:
            frame: एक OpenCV BGR इमेज।

        Returns:
            एक डिक्शनरी जिसमें वस्तुओं के निर्देशांक और ट्रैजेक्टरी शामिल हैं।
        """
        results_dict = {
            "ball": None,
            "pad": None,
            "bat": None,
            "trajectory": list(self.ball_trajectory)
        }

        if not self.model:
            return results_dict
        
        # मॉडल से भविष्यवाणी करें
        results = self.model(frame, verbose=False)
        
        # परिणामों को प्रोसेस करें
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0]
                conf = box.conf[0]
                cls = int(box.cls[0])
                
                if conf > 0.4:  # 40% se zyada confidence
                    center_x = int((x1 + x2) / 2)
                    center_y = int((y1 + y2) / 2)

                    class_name = self.model.names[cls]
                    # class_map: model ke class name -> hamara standard naam
                    # (custom model: ball/pad/bat; COCO fallback: sports ball -> ball)
                    mapped = self.class_map.get(class_name)
                    if mapped == "ball":
                        results_dict["ball"] = (center_x, center_y)
                        self.ball_trajectory.append((center_x, center_y))
                    elif mapped == "pad":
                        results_dict["pad"] = (center_x, center_y)
                    elif mapped == "bat":
                        results_dict["bat"] = (center_x, center_y)

        # नवीनतम ट्रैजेक्टरी अपडेट करें
        results_dict['trajectory'] = list(self.ball_trajectory)
        return results_dict