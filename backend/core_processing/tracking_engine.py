import torch
from ultralytics import YOLO
from collections import deque

class ObjectTracker:
    """
    एक प्रशिक्षित YOLO मॉडल का उपयोग करके क्रिकेट की वस्तुओं को ट्रैक करने के लिए एक क्लास।
    """
    def __init__(self, model_path='ai_model/cricket_yolo_v8.pt'):
        """
        ट्रैकर को इनिशियलाइज़ करता है और YOLO मॉडल को लोड करता है।

        Args:
            model_path (str): प्रशिक्षित YOLO मॉडल का पथ (.pt फ़ाइल)।
        """
        # डिवाइस चुनें: अगर GPU उपलब्ध है तो CUDA का उपयोग करें, अन्यथा CPU
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"YOLO मॉडल के लिए डिवाइस का उपयोग किया जा रहा है: {self.device}")

        # नोट: आपको क्रिकेट की छवियों (बॉल, पैड, बैट) पर एक YOLOv8 मॉडल को
        # प्रशिक्षित करके 'cricket_yolo_v8.pt' फ़ाइल खुद बनानी होगी।
        try:
            self.model = YOLO(model_path)
            self.model.to(self.device)
            print(f"✅ YOLO मॉडल '{model_path}' से सफलतापूर्वक लोड हो गया।")
        except Exception as e:
            print(f"❌ चेतावनी: YOLO मॉडल '{model_path}' नहीं मिला। {e}")
            self.model = None

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
                
                if conf > 0.4: # 40% से ज़्यादा आत्मविश्वास
                    center_x = int((x1 + x2) / 2)
                    center_y = int((y1 + y2) / 2)
                    
                    class_name = self.model.names[cls] # क्लास का नाम (जैसे 'ball')

                    if class_name == 'ball':
                        results_dict['ball'] = (center_x, center_y)
                        self.ball_trajectory.append((center_x, center_y))
                    elif class_name == 'pad':
                        results_dict['pad'] = (center_x, center_y)
                    elif class_name == 'bat':
                        results_dict['bat'] = (center_x, center_y)

        # नवीनतम ट्रैजेक्टरी अपडेट करें
        results_dict['trajectory'] = list(self.ball_trajectory)
        return results_dict