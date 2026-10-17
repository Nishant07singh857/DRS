# DRS — AI Cricket LBW Decision Review System

Video upload karo, AI ball-tracking se LBW decision pao — Hawk-Eye style.
**Stack:** Flask + Celery + Redis + TimescaleDB (PostgreSQL) + YOLOv8 + React + Docker.

## Architecture

```
User -> React (nginx:80) -> Flask API (backend:5000)
                              |
                              +-> Celery worker -> YOLO tracking -> LBW decision -> TimescaleDB
                              |
                              +-> Redis (broker + result backend)
```

- **Backend** (`backend/`): Flask blueprints (`/api/auth`, `/api/analysis`, `/api`), JWT auth,
  Celery background video processing, SQLAlchemy models.
- **AI pipeline** (`backend/core_processing/`): OpenCV preprocessing -> YOLOv8 object
  tracking (ball/pad/bat) -> deterministic LBW rule engine (trajectory extrapolation).
- **Frontend** (`frontend/`): React 18 + Tailwind — login/register, video upload with
  live progress, review gallery (paginated), Hawk-Eye style decision visualization.
- **Infra**: `docker-compose.yml` — TimescaleDB, Redis, backend, Celery worker, frontend.

## Quickstart (Docker)

```bash
# 1. Env file banao
cp .env.example .env
# .env me SECRET_KEY, JWT_SECRET_KEY, POSTGRES_PASSWORD badlo:
#   python -c "import secrets; print(secrets.token_hex(32))"

# 2. Build + run
docker compose up --build -d

# 3. Database tables banao (pehli baar)
docker compose exec backend flask db upgrade

# 4. Kholo: http://localhost:3000
```

## Local dev (bina Docker)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # values bharo; DATABASE_HOST=localhost, REDIS_HOST=localhost
# PostgreSQL + Redis local me chalao, phir:
flask db upgrade
flask run --port 5001
celery -A app.celery worker --loglevel=info   # alag terminal me
```

## Tests

```bash
cd backend
DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_api.py -v
```
9 tests: auth flow, upload validation, video processing (eager Celery), pagination.

## YOLO model

- `backend/ai_model/cricket_yolo_v8.pt` — cricket ball/pad/bat par trained custom model.
  Ye file repo me nahi hai; khud train karke is path par rakho.
- **Training script ready hai**: `backend/ai_model/train.py` chalao (GPU chahiye —
  Google Colab ka free GPU kaafi hai). Poora guide script ke andar hai:
  dataset kaise banao (Roboflow se 500-1000 labeled images: ball/pad/bat),
  `dataset.yaml` template `backend/ai_model/dataset.yaml.template` me hai.
- **Fallback:** custom model na mile to COCO-pretrained `yolov8n` auto-download hokar
  `sports ball` detect karega (pad/bat nahi). Pipeline kaam karega, accuracy kam hogi.

## API (summary)

| Method | Endpoint | Auth | Kaam |
|---|---|---|---|
| POST | /api/auth/register | nahi | Naya user |
| POST | /api/auth/login | nahi | JWT token |
| GET | /api/auth/profile | haan | Profile |
| POST | /api/analysis/upload | haan | Video upload -> task_id (202) |
| GET | /api/tasks/<id>/status | nahi | PENDING / PROGRESS / SUCCESS / FAILURE |
| GET | /api/reviews?page=1 | haan | Paginated reviews |
| GET | /api/reviews/<id> | haan | Ek review ka detail |

Upload limits: sirf `.mp4 .avi .mov .mkv .webm`, max size `MAX_UPLOAD_MB` (default 500).

## Env variables

`MAX_UPLOAD_MB`, `TRACK_EVERY_N_FRAMES` (tracking speed vs accuracy),
`CORS_ORIGINS` (comma-separated frontend URLs) — details `.env.example` me.

## Security notes

- `.env` kabhi commit mat karo. Agar purani `.env` GitHub history me hai to
  **saare secrets rotate karo** (naye keys/passwords banao).
- Production me `CORS_ORIGINS` ko apne domain par set karo, `DEBUG` off rakho,
  HTTPS ke peeche chalao.
