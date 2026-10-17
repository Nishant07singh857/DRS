"""
YOLOv8 training script — cricket ball / pad / bat detector.

KAISE CHALAYEIN (GPU chahiye — Google Colab free tier kaafi hai):
  1. Dataset taiyaar karo (neeche DATASET GUIDE dekho) aur is folder me rakho:
       backend/ai_model/dataset/
         images/train/, images/val/
         labels/train/, labels/val/
     + dataset.yaml (sample neeche hai)
  2. Colab me GPU runtime on karo, phir:
       pip install ultralytics
       python backend/ai_model/train.py
  3. Best model yahan milega: backend/ai_model/runs/detect/train/weights/best.pt
     Use copy karke backend/ai_model/cricket_yolo_v8.pt naam do.

DATASET GUIDE (sabse important step):
  - Kam se kam 500-1000 images: cricket match videos ke frames (alag angles,
    alag lighting, alag grounds).
  - Har image me ball, pad, bat ko bounding box se label karo.
  - Free tools: Roboflow (roboflow.com) — upload, annotate, export YOLO format.
    Ya CVAT / LabelImg.
  - Train/val split 80/20. Classes EXACT order me rakho:
      0 = ball, 1 = pad, 2 = bat
"""

from ultralytics import YOLO

# --- Settings ---
DATA_YAML = "backend/ai_model/dataset.yaml"  # dataset ka config
BASE_MODEL = "yolov8n.pt"  # chhota, tez — pehle isse train karo; baad me yolov8m/l
EPOCHS = 100
IMG_SIZE = 640
BATCH = 16  # GPU memory kam ho to 8 karo

# dataset.yaml ka sample (is naam se file banao):
# path: backend/ai_model/dataset
# train: images/train
# val: images/val
# names:
#   0: ball
#   1: pad
#   2: bat


def main():
    model = YOLO(BASE_MODEL)  # COCO-pretrained se start (transfer learning)

    results = model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH,
        name="cricket_yolo_v8",
        project="backend/ai_model/runs",
        # Ball chhoti hoti hai — chhote objects ke liye helpful tweaks:
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=15.0,
        patience=20,  # 20 epochs tak improvement na ho to early stop
    )

    print("\nTraining complete.")
    print("Best model: backend/ai_model/runs/detect/cricket_yolo_v8/weights/best.pt")
    print("Use copy karke 'backend/ai_model/cricket_yolo_v8.pt' naam do.")

    # Quick validation report
    metrics = model.val()
    print(f"mAP50: {metrics.box.map50:.3f} | mAP50-95: {metrics.box.map:.3f}")


if __name__ == "__main__":
    main()
