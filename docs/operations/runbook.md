# CareVoice Platform — Operational Runbook & Production Guide

**Environment Version:** 1.0.0  
**Target Architecture:** Docker Compose / Modular Monolith  
**Date:** October 18, 2026  

---

## 1. Local Development Operations

### 1.1 Startup & Shutdown
Start the development stack (PostgreSQL, Backend, Frontend, Ollama, pgAdmin):
```sh
docker compose up -d --build
```

Inspect service health:
```sh
docker compose ps
```

Stream logs:
```sh
docker compose logs -f backend
docker compose logs -f frontend
```

Graceful shutdown (preserves database data volume `postgres_data`):
```sh
docker compose down
```

### 1.2 Database Migrations (Alembic)
Apply all pending schema migrations:
```sh
docker compose exec backend alembic upgrade head
```

Verify current revision and check for schema drift:
```sh
docker compose exec backend alembic current
docker compose exec backend alembic check
```

Generate a new migration after editing SQLAlchemy models:
```sh
docker compose exec backend alembic revision --autogenerate -m "describe_changes"
```

### 1.3 Running Automated Tests
Backend test suite (FastAPI, pytest, SQLite/PostgreSQL in-memory):
```sh
docker compose exec backend pytest -q
```

Frontend unit tests (Node.js native test runner):
```sh
docker compose exec frontend npm test
```

Frontend production bundle verification:
```sh
docker compose exec frontend npm run build
```

---

## 2. Production Deployment Operations

### 2.1 Production Configuration
1. Generate unique production secrets (do not use development placeholders):
   ```sh
   # JWT Secret Key (64 characters)
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   
   # PostgreSQL Password (at least 24 characters)
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   
   # One-time Admin Bootstrap Token
   openssl rand -hex 32
   ```

2. Configure `.env` with:
   - `APP_ENV=production`
   - `PAYMENT_MODE=live` (Demo mode is strictly prohibited in production)
   - Valid `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`
   - `BACKEND_CORS_ORIGINS=https://carevoice.yourhospital.org`
   - Secure `DATABASE_URL` pointing to PostgreSQL with URL-encoded password

3. Deploy with production compose specification:
   ```sh
   docker compose -f compose.production.yaml up -d --build
   ```

---

## 3. Disaster Recovery & Database Backup/Restore

### 3.1 Automated Database Backup
Execute a consistent PostgreSQL dump:
```sh
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker compose exec -T db pg_dump -U healthcare_user -d healthcare_db -F c -b -v > "./backups/carevoice_db_${TIMESTAMP}.dump"
```

### 3.2 Database Restoration Drill
To restore into an empty database instance:
```sh
cat "./backups/carevoice_db_backup.dump" | docker compose exec -T db pg_restore -U healthcare_user -d healthcare_db --clean --if-exists
```

---

## 4. Security Incident Response & Secret Rotation

### 4.1 Compromised User or Admin Account
1. Deactivate user account immediately:
   ```sh
   docker compose exec backend python -m app.cli update-user <user_id> --inactive
   ```
2. Revoke all active sessions for that user:
   The backend automatically revokes sessions upon deactivation or password reset.

### 4.2 JWT Secret Key Rotation
1. Update `JWT_SECRET_KEY` in `.env`.
2. Restart backend:
   ```sh
   docker compose restart backend
   ```
3. *Impact:* All active user sessions will be invalidated, requiring users to log in again. No user account data or appointments are lost.

### 4.3 Payment Gateway Credential Rotation
1. In Razorpay Dashboard, generate new Key Secret and Webhook Secret.
2. Update `.env` with new `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET`.
3. Restart backend service.
