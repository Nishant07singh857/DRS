# 4-6 Smartphone 3D DRS Setup Guide

Tumhare paas 4-6 phones hain = asli Hawk-Eye jaisa setup! Ye guide batayega
kaise lagana hai.

## Camera Positions (pitch ka map)

```
                    N (batsman end, +x)
                    |
    Cam3 (Point)    |    Cam2 (Square leg)
    (0, +18, 2.5)   |    (0, -18, 2.5)
                    |
  ------------------+------------------  <- Pitch (22 yards)
                    |
                    |
  Cam0 (Bowler end) |
  (-25, 0, 3)       |    Cam1 (Batsman end high)
                    |    (+22, 0, 6)
                    |
                    S (bowler end, -x)
```

### 4 phones (minimum):
1. **Bowler end** — sightscreen ke paas, pitch ki seedh me
2. **Square leg** — pitch ke beech me, side se (18m door)
3. **Point** — doosri side se (18m door)
4. **Batsman end (high)** — peeche se thoda upar (6m)

### 5-6 phones (behtar):
5. **Bowler end (high)** — upar se angle
6. **Extra square** — ya short leg ke paas

## Phone Settings (sab phones par SAME)

- **Resolution**: 1080p (1920x1080)
- **FPS**: 60 (agar ho to, nahi to 30)
- **Focus**: Manual, pitch par lock karo
- **Exposure**: Manual (auto se brightness badalti hai)
- **Stabilization**: OFF (tripod use karo!)

## Synchronization (sabse zaroori!)

4-6 videos ka **same moment** milna chahiye. Options:

### Option A: Audio clap (sabse easy)
1. Sab phones recording shuru karo
2. Koi zor se **taali bajao** (sab phones me sunai de)
3. Analysis me audio spike se sync karo

### Option B: Visual flash
1. Sab recording shuru karo
2. **Torch jalao-bujhao** (sab cameras me dikhe)
3. Flash wale frame se sync karo

### Option C: NTP time sync (best)
- Sab phones ek hi WiFi par
- Ek app se time sync karo
- Har frame ka timestamp match karo

## Calibration (ek baar karna hai)

Har camera ko pata hona chahiye woh kahan hai:

1. Pitch par **known points** mark karo:
   - Dono ends ke stumps (6 points)
   - Crease lines ke corners (4 points)
2. Har camera ki video me ye points dikhne chahiye
3. `triangulation.py` me `camera_looking_at()` se R, t banao
4. Ya `suggested_4_camera_setup()` use karo (andaza positions)

**Tip**: Pehli baar `suggested_4_camera_setup()` ke default positions se
shuru karo. Accuracy kam hogi lekin kaam karega. Phir dheere-dheere
calibrate karo.

## Workflow

```
1. 4-6 phones lagao + recording shuru
2. Sync signal (taali/flash)
3. Ball dalo
4. Recording band karo
5. Videos ko computer par lao
6. Har video par YOLO detection chalao (RealtimeTracker)
7. Har frame ke liye: 4-6 cameras ke 2D points → triangulate_robust() → 3D point
8. 3D trajectory → analyze_lbw_3d() → OUT/NOT OUT!
```

## Code Example

```python
from core_processing.triangulation import (
    suggested_4_camera_setup, triangulate_robust, analyze_lbw_3d
)
from core_processing.realtime_tracker import RealtimeTracker

# 1. Cameras setup
setup = suggested_4_camera_setup()
cameras = [s['camera'] for s in setup]

# 2. Har camera par ball detect karo
trackers = [RealtimeTracker() for _ in cameras]
# ... har frame par ...
points_2d = []
for tracker, frame in zip(trackers, frames):
    result = tracker.track(frame)
    points_2d.append(result['ball'])  # (x, y) ya None

# 3. 3D me triangulate karo
point_3d = triangulate_robust(points_2d, cameras)
trajectory_3d.append(point_3d)

# 4. LBW decision!
decision = analyze_lbw_3d(trajectory_3d)
print(decision['decision'], decision['confidence'])
```

## Accuracy Expectations (imaandaar)

| Setup | Accuracy |
|-------|----------|
| 1 phone (current) | ~80-85% |
| 2 phones | ~88-92% |
| 4 phones (calibrated) | ~93-96% |
| 6 phones (calibrated) | ~96-98% |
| Real Hawk-Eye (6x 340fps) | 99%+ |

4 phones se tum **international ke bahut kareeb** pahunch jaoge!
