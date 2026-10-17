# DRS API Documentation

Base URL: `http://localhost:5000` (dev) ya `https://your-domain.com/api` (prod)

Sab requests me `Content-Type: application/json` header bhejo (upload ke alawa).

## Authentication

### Register
```http
POST /api/auth/register
```
```json
{
  "username": "virat",
  "email": "virat@example.com",
  "password": "strongpassword123"
}
```
**Rate limit:** 10/hour per IP  
**Response (201):**
```json
{"message": "User created successfully"}
```

### Login
```http
POST /api/auth/login
```
```json
{
  "username": "virat",
  "password": "strongpassword123"
}
```
**Rate limit:** 5/minute per IP (brute-force protection)  
**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "username": "virat"
}
```

Agale requests me header bhejo:
```http
Authorization: Bearer <access_token>
```

## Video Analysis

### Upload Video
```http
POST /api/analysis/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data
```
Form field: `video` = video file (.mp4, .avi, .mov, .webm)

**Limits:**
- Max size: 500MB (configurable via `MAX_UPLOAD_MB`)
- Max duration: 10 minutes
- Rate limit: 10/hour per user

**Response (202):**
```json
{
  "message": "Video accepted for processing",
  "task_id": "a1b2c3d4-...",
  "filename": "uuid.mp4"
}
```

### Check Task Status
```http
GET /api/analysis/status/<task_id>
Authorization: Bearer <token>
```
**Response (200):**
```json
{
  "task_id": "a1b2c3d4-...",
  "status": "PROCESSING",  // PENDING | PROCESSING | SUCCESS | FAILURE
  "progress": 45
}
```

### Get LBW Result
```http
GET /api/analysis/result/<task_id>
Authorization: Bearer <token>
```
**Response (200):**
```json
{
  "decision": "OUT",
  "confidence": 87.5,
  "pitch_3d": [2.8, 0.05, 0.18],
  "impact_3d": [9.1, 0.05, 0.32],
  "hitting_stumps": true,
  "delivery_analysis": {
    "speed_kmh": 135.7,
    "delivery_type": "Good length",
    "swing_direction": "in",
    "spin_direction": null
  },
  "trajectory_2d": [[100, 200], [105, 195], ...],
  "processing_time_s": 12.3
}
```

## Reviews (History)

### List Reviews
```http
GET /api/reviews?page=1&per_page=20
Authorization: Bearer <token>
```
**Response (200):**
```json
{
  "reviews": [...],
  "total": 45,
  "page": 1,
  "pages": 3
}
```

### Get Single Review
```http
GET /api/reviews/<review_id>
Authorization: Bearer <token>
```

## Multi-Camera 3D (Advanced)

### Sync Videos
```python
from core_processing.audio_sync import sync_videos, apply_offset_info

offsets = sync_videos(['cam0.mp4', 'cam1.mp4', 'cam2.mp4', 'cam3.mp4'])
print(apply_offset_info(offsets))
```

### Triangulate
```python
from core_processing.triangulation import (
    suggested_4_camera_setup, triangulate_robust, analyze_lbw_3d
)

setup = suggested_4_camera_setup()
cameras = [s['camera'] for s in setup]

# Har frame par:
points_2d = [tracker0_result['ball'], tracker1_result['ball'], ...]
point_3d = triangulate_robust(points_2d, cameras)
trajectory_3d.append(point_3d)

# Final:
decision = analyze_lbw_3d(trajectory_3d)
```

## Error Codes

| Code | Matlab |
|------|--------|
| 400 | Galat request (validation fail) |
| 401 | Login zaroori / token expire |
| 404 | Nahi mila |
| 413 | File bahut badi |
| 429 | Rate limit cross (thoda ruko!) |
| 500 | Server error |

**429 aaye to:** `Retry-After` header dekho, utne sec ruko, phir retry karo.

## Pitch Map & Over Summary

### Pitch Map
```http
POST /api/reviews/pitch-map
Authorization: Bearer <token>
```
```json
{
  "bowler": "Bumrah",
  "deliveries": [
    {"pitch_x": 4.5, "pitch_y": 0.1, "outcome": "dot", "speed_kmh": 142}
  ]
}
```
Returns: `{"svg": "...", "stats": {...}}`

### Over Summary
```http
POST /api/reviews/over-summary
Authorization: Bearer <token>
```
```json
{
  "over": 1, "bowler": "Bumrah", "batsman": "Kohli",
  "balls": [{"pitch_3d": [5.5, 0.1, 0.2], "outcome": "dot", "runs": 0, ...}]
}
```
Returns: `{"summary": {...}, "html": "...", "pitch_map_svg": "..."}`
