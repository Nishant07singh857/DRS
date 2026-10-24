# Model Card — cricket_yolo_v0.pt

## Ye kya hai
DRS ke liye pehla custom YOLOv8n model: cricket **ball**, **pad**, **bat** detect karta hai.
COCO-pretrained weights se transfer learning par bana hai.

## Training data (v0)
- **55 images** — web se ikatthi ki gayi cricket batting/bowling photos
- **Labels**: AI auto-labeling (visual grounding) + spot-check
  - ball: 30 boxes | pad: 121 boxes | bat: 52 boxes
- **Split**: 44 train / 11 val
- **Augmentation**: YOLOv8 defaults (flip, mosaic, HSV jitter)

## Training config
- Base: yolov8n.pt (COCO pretrained)
- epochs=50, patience=15, imgsz=416, batch=8, optimizer=Adam, lr0=0.001
- Hardware: CPU-only

## Results (validation set, 11 images)

| Class | Precision | Recall | mAP50 | mAP50-95 |
|-------|-----------|--------|-------|----------|
| ball  | 1.00 | 0.21 | 0.425 | 0.260 |
| pad   | 0.23 | 0.42 | 0.382 | 0.174 |
| bat   | 0.12 | 0.18 | 0.078 | 0.024 |
| all   | 0.45 | 0.27 | 0.295 | 0.153 |

Padhne ka tarika: ball par precision 1.0 matlab jab model "ball" kehta hai to sahi
kehta hai — lekin recall 0.21 matlab 79% balls miss ho jati hain. v0 ke liye
expected hai; zyada data se recall badhega.

## Imaandaar limitations
1. **Chhota dataset** — 55 images production ke liye kaafi nahi. Ball (chhoti, tez)
   sabse mushkil class hai; sirf 30 ball examples hain.
2. **Auto-label noise** — kuch boxes galat ho sakte hain; human review nahi hua.
3. **Domain gap** — training photos (stills) vs match video frames (motion blur)
   me farak hai.
4. Ye **v0 / proof-of-concept** hai — COCO fallback se behtar, lekin asli
   accuracy ke liye 500+ human-verified images + GPU training chahiye
   (dekho: `DRS_Dataset_Shortcut_Guide.md`).

## Agla step
- 200-500 aur images jodkar v1 train karo (Colab free GPU par)
- Galat detections ko correct karke active learning loop chalao
