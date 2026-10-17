# Model Card — cricket_yolo_v8.pt

## Ye kya hai
DRS ke liye custom YOLOv8n model: cricket **ball**, **pad**, **bat** detect karta hai.
COCO-pretrained weights se transfer learning par bana hai.

## v1 (current) — video data shamil
- **88 images** — 55 web photos + 33 match video frames (Wikimedia Commons, 4 videos)
- **Labels**: AI auto-labeling + spot-check
  - ball: 50 boxes | pad: 235 boxes | bat: 99 boxes
- **Split**: 71 train / 17 val
- Base: v0 weights se fine-tune (epochs=80, patience=20, lr0=0.0005, imgsz=416)

### Results v1 (val, 17 images)

| Class | Precision | Recall | mAP50 | mAP50-95 |
|-------|-----------|--------|-------|----------|
| ball  | 0.415 | 0.25 | 0.245 | 0.075 |
| pad   | 0.755 | 0.556 | 0.653 | 0.264 |
| bat   | 0.587 | 0.333 | 0.383 | 0.111 |
| all   | 0.586 | 0.38 | **0.427** | 0.150 |

### v0 vs v1 (imaandaar tulna)
- **Overall**: v1 behtar — mAP50 0.295 → **0.427** (+45%)
- **Pad**: 0.382 → **0.653** (+71%) — zabardast sudhaar
- **Bat**: 0.078 → **0.383** (+391%) — bahut behtar
- **Ball**: 0.425 → 0.245 (-42%) — **peeche hua** ⚠️
  - Video frames me ball chhoti + motion-blur wali hai, mushkil hai
  - Recall thoda badha (0.21 → 0.25) lekin precision/mAP gira
  - LBW ke liye ball sabse zaroori class hai — ye abhi bhi kamzor hai

## Imaandaar limitations
1. **Ball detection abhi bhi kamzor** — dono versions me ball recall 25% se kam.
   Asli match me tez ball ke liye aur data + behtar labeling chahiye.
2. **Chhota dataset** — 88 images production ke liye kaafi nahi.
3. **Auto-label noise** — human review nahi hua.
4. Ye **v1 / improved proof-of-concept** hai — v0 se behtar, lekin "master"
   banne ke liye 500+ human-verified images + GPU training chahiye.

## Agla step
- Ball par focus: zyada ball examples, motion-blur augmentation
- 200-500 aur images jodkar v2 train karo (Colab free GPU par)

---
## v0 (purana) — record ke liye
- 55 images, 44 train / 11 val; ball 30 / pad 121 / bat 52 boxes
- mAP50: ball 0.425, pad 0.382, bat 0.078, all 0.295
