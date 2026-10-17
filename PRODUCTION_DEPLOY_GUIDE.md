# Production Deployment Guide — DRS Cricket LBW System

Bechne se pehle ye sab karna ZAROORI hai. Development setup (`docker compose up`)
production ke liye kaafi nahi hai.

## 1. Secrets Rotate Karo (SABSE PEHLE!)

Purana `.env` git history me hai. Ye steps follow karo:

```bash
# Naye secrets generate karo
python3 -c "import secrets; print(secrets.token_hex(32))"  # SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"  # JWT_SECRET_KEY

# .env me daalo
# Purane secrets kahin bhi use ho rahe hain to wahan bhi update karo
```

**Option A (recommended):** Naya fresh repo banao, sirf saaf files push karo.
**Option B:** `git filter-repo` se history saaf karo (risky, backup lo pehle).

## 2. HTTPS Setup (Nginx + Let's Encrypt)

Bina HTTPS ke passwords khule me jayenge!

```bash
# Nginx install
sudo apt install nginx certbot python3-certbot-nginx

# Reverse proxy config (/etc/nginx/sites-available/drs)
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# SSL certificate (free!)
sudo certbot --nginx -d your-domain.com
```

## 3. Environment Variables (Production)

```bash
# .env (production)
FLASK_ENV=production
SECRET_KEY=<64-char random>
JWT_SECRET_KEY=<64-char random>
DATABASE_URL=postgresql://drs_prod:<strong-password>@db:5432/drs
REDIS_URL=redis://redis:6379/0
CORS_ORIGINS=https://your-domain.com
MAX_UPLOAD_MB=500
TRACK_PRESET=balanced
```

## 4. Database Backup (Roz!)

```bash
# Cron me daalo (roz raat 2 baje)
0 2 * * * docker compose exec -T db pg_dump -U drs_prod drs | gzip > /backup/drs-$(date +\%F).sql.gz

# 7 din se purane backups hatao
0 3 * * * find /backup -name "drs-*.sql.gz" -mtime +7 -delete
```

## 5. Monitoring (Kya chal raha hai?)

### Option A: Simple (shuruwat ke liye)
```bash
# Docker health check
docker compose ps

# Logs dekho
docker compose logs -f backend
docker compose logs -f celery-worker
```

### Option B: Proper (bad me)
- **Uptime:** UptimeRobot (free) — site down ho to SMS
- **Errors:** Sentry (free tier) — exceptions track karo
- **Metrics:** Prometheus + Grafana — FPS, latency, etc.

## 6. Firewall

```bash
# Sirf zaroori ports kholo
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 22/tcp    # SSH (apni IP se hi!)
sudo ufw enable
```

## 7. Updates

```bash
# Hafte me ek baar
docker compose pull
docker compose up -d --build

# Security updates
sudo apt update && sudo apt upgrade -y
```

## Checklist (Bechne Se Pehle)

- [ ] Secrets rotate kiye
- [ ] HTTPS chal raha hai
- [ ] Rate limiting test kiya (login par 5/min)
- [ ] Database backup cron lagaya
- [ ] Firewall on hai
- [ ] v3 model GitHub par upload kiya
- [ ] Ek poori video upload → LBW result test kiya
- [ ] Terms of Service + Privacy Policy pages banayi
- [ ] Payment integration (agar paid hai to)

## Cost Estimate (Monthly)

| Cheez | Cost |
|-------|------|
| VPS (4 CPU, 8GB RAM) | ₹800-1500 |
| Domain | ₹800/year |
| SSL | Free (Let's Encrypt) |
| Backup storage | ₹200 |
| **Total** | **~₹1000-1700/month** |

Hetzner/Contabo saste hain, AWS/GCP mehenge. Shuruwat me Hetzner best hai.
