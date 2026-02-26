# SPEC-10: Docker Infrastructure

**Status:** Final
**Version:** 3.0
**Date:** 2026-02-23

---

## Module Overview

Spec-10 defines the Docker containerization for Snatched v3. The application runs as a single container (`snatched`) integrated into the existing server infrastructure:

- **Master compose file:** `/home/dave/docker/compose/docker-compose.yml`
- **Build context:** `/home/dave/docker/compose/snatched/`
- **Base image:** `python:3.12-slim`
- **Networks:** `dashboard-net` (Traefik routing) + `memory-net` (PostgreSQL access)
- **Ports:** No direct host exposure — Traefik handles all routing
- **Database:** Dedicated `snatched` database on the existing `memory-store` PostgreSQL instance at 172.20.6.10

**Architecture:**
```
Traefik (172.20.1.10:80/443)
    |  Host: snatched.local (LAN HTTP)
    v
Snatched (172.20.1.30:8000)   <-- FastAPI / uvicorn
    |
    +-- PostgreSQL (172.20.6.10:5432)   <-- processing_jobs, users, job_events
    |   (memory-net)
    |
    +-- /data/{username}/proc.db        <-- per-user SQLite (mounted volume)
```

**Existing infrastructure reused:**
- `reverse-proxy` container (Traefik v3) at 172.20.1.10 — already running
- `memory-store` container (PostgreSQL 16) at 172.20.6.10 — already running
- Networks `dashboard-net` (172.20.1.0/24) and `memory-net` (172.20.6.0/24) — already external

---

## Files to Create

```
/home/dave/docker/compose/snatched/
├── Dockerfile                  # Multi-stage Python 3.12 build
├── requirements.txt            # Python dependencies (pinned)
├── entrypoint.sh               # Startup script: wait for PostgreSQL, then launch uvicorn
├── init-db.sql                 # One-time PostgreSQL database + user setup
└── snatched/                   # Application source (copied from project)
    ├── app.py
    ├── auth.py
    ├── models.py
    ├── jobs.py
    ├── config.py
    ├── routes/
    │   ├── __init__.py
    │   ├── pages.py
    │   ├── api.py
    │   └── uploads.py
    ├── templates/               # 8 Jinja2 templates (spec-09)
    ├── static/                  # CSS + htmx.min.js (spec-09)
    └── processing/              # v2 pipeline adapted for v3 (specs 02-06)
        ├── __init__.py
        ├── ingest.py
        ├── match.py
        ├── enrich.py
        ├── export.py
        ├── lanes.py
        ├── reprocess.py
        ├── chat_renderer.py
        └── sqlite.py

/home/dave/docker/volumes/snatched/
├── data/                        # User uploads, processing, output (mounted at /data)
└── logs/                        # Application logs (mounted at /app/logs)

/home/dave/docker/configs/snatched/
└── snatched.toml                # Server configuration (mounted read-only)

/home/dave/docker/secrets/
└── snatched_db_password         # PostgreSQL password for snatched user
```

---

## Dependencies

**Built after:**
- spec-08 (app.py, auth.py, jobs.py, routes/)
- spec-09 (templates/, static/)

**Requires existing infrastructure:**
- `memory-store` container (PostgreSQL 16) at 172.20.6.10 — must be healthy
- `dashboard-net` network — already created externally
- `memory-net` network — already created externally

---

## Function Signatures

N/A — This spec defines infrastructure files (Dockerfile, compose YAML, shell scripts), not Python modules. There are no callable Python functions. The entry point is `uvicorn snatched.app:create_app --factory --host 0.0.0.0 --port 8000`.

---

## Database Schema

The PostgreSQL database `snatched` is created on Dave's existing `memory-store` instance (172.20.6.10). The DDL is executed by `init-db.sql`:

```sql
-- init-db.sql — run once to create database and user
CREATE USER snatched WITH PASSWORD '<from /run/secrets/snatched_db_password>';
CREATE DATABASE snatched OWNER snatched;
GRANT ALL PRIVILEGES ON DATABASE snatched TO snatched;

-- Application tables are created automatically by FastAPI lifespan (app.py init_schema())
-- See spec-08 for the full PostgreSQL schema (users, processing_jobs, job_events tables)
```

Per-user SQLite databases are created automatically at `/data/{username}/proc.db` when a user's first job runs. The SQLite schema (12 tables) is applied by `processing/sqlite.py create_schema()`.

---

## Multi-User Adaptation

The Docker infrastructure enables multi-user operation:

1. **Data volume** — `/data/` is a Docker volume mapped to `~/docker/volumes/snatched/data`. Each user gets a subdirectory: `/data/{username}/` with `uploads/`, `processing/`, `output/`, and `proc.db`.
2. **Traefik + Authelia** — All requests pass through Traefik → Authelia before reaching Snatched. The container never handles raw authentication. Users are identified by the `X-Remote-User` header injected by Authelia.
3. **Resource limits** — 2GB RAM / 4GB boost prevents a single user's large export from starving other containers. The 4 CPU limit allows parallel exiftool/ffmpeg operations.
4. **PostgreSQL shared state** — The `memory-store` PostgreSQL instance on memory-net stores user accounts and job history, accessible to the Snatched container via Docker networking.
5. **No host port binding** — The container exposes port 8000 only on Docker networks, not on the host. All external access goes through Traefik on port 80/443.

---

## Code Examples

### Quick Deploy

```bash
# Build and start
sg docker -c "docker compose up -d --build snatched"

# Check health
sg docker -c "docker logs snatched --tail 20"
sg docker -c "docker exec snatched curl -sf http://127.0.0.1:8000/api/health"

# Test Traefik routing (add snatched.local to /etc/hosts first)
curl -H "Host: snatched.local" http://127.0.0.1/api/health
```

### Init PostgreSQL Database

```bash
# Create the snatched database on memory-store
sg docker -c "docker exec -i memory-store psql -U postgres < ~/docker/compose/snatched/init-db.sql"
```

---

## V2 Source Reference

**V2 source file:** `/home/dave/tools/snapfix/snatched.py`

The v2 pipeline runs as a CLI script on the host. V3 wraps it in a Docker container with a web interface. The processing code (`processing/` package) is a direct port of v2's functions with no algorithmic changes.

| V2 | V3 |
|----|-----|
| CLI invocation on host | FastAPI web app in container |
| Single user, single SQLite | Multi-user; PostgreSQL for jobs + per-user SQLite |
| `python snatched.py` | `uvicorn snatched.app:create_app --factory` |
| No auth | Authelia via Traefik X-Remote-User header |

---

## Dockerfile

**Path:** `/home/dave/docker/compose/snatched/Dockerfile`

**Multi-stage build:**
1. **Builder stage:** Install Python packages as wheels (compiles native extensions like `asyncpg`)
2. **Final stage:** Slim runtime image — no build tools, no pip, smaller attack surface

```dockerfile
# ============================================================
# BUILDER STAGE — installs dependencies, compiles wheels
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages to user site-packages
COPY requirements.txt .
RUN pip install --no-cache-dir --user \
    --no-warn-script-location \
    -r requirements.txt


# ============================================================
# FINAL STAGE — slim runtime only
# ============================================================
FROM python:3.12-slim

WORKDIR /app

# Runtime system packages:
#   exiftool      — EXIF metadata embedding (Phase 4)
#   ffmpeg        — Video processing (Phase 4)
#   imagemagick   — Image compositing / overlay burning (Phase 4)
#   fonts-*       — TrueType fonts for chat PNG renderer (spec-07)
#   curl          — Health check
#   libpq5        — PostgreSQL client library (asyncpg runtime dep)
#   postgresql-client — pg_isready for entrypoint.sh health wait
RUN apt-get update && apt-get install -y --no-install-recommends \
    exiftool \
    ffmpeg \
    imagemagick \
    fonts-dejavu-core \
    fonts-liberation \
    curl \
    libpq5 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (UID 1000 matches dave on host for volume permissions)
RUN useradd -m -u 1000 -s /bin/bash snatched

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/snatched/.local

# Copy application source code
COPY snatched/ /app/snatched/

# Create persistent data directory (volume mount point at runtime)
RUN mkdir -p /data /app/logs && chown snatched:snatched /data /app/logs

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Environment
ENV PATH=/home/snatched/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Switch to non-root user
USER snatched

# Expose port (Traefik connects to this)
EXPOSE 8000

# Health check — /api/health requires no auth
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://127.0.0.1:8000/api/health || exit 1

# Default command (overrideable for debugging)
ENTRYPOINT ["/app/entrypoint.sh"]
```

**Multi-stage build benefits:**
- Builder installs gcc, libpq-dev, and all pip packages
- Final stage starts fresh: only `libpq5` (runtime), no compilers, no pip cache
- Estimated final image size: ~450–550 MB (slim base + exiftool + ffmpeg + Python packages)

---

## requirements.txt

**Path:** `/home/dave/docker/compose/snatched/requirements.txt`

```
# Web framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6

# Database
asyncpg==0.29.0

# Templates + validation
jinja2==3.1.2
pydantic==2.5.0
pydantic-settings==2.1.0

# Configuration parsing
tomli==2.0.1

# Auth (dev-mode JWT fallback)
PyJWT==2.8.1

# Media processing (pipeline)
Pillow==10.1.0
python-magic==0.4.27

# Testing (optional — exclude from production image via separate requirements-dev.txt)
# pytest==7.4.3
# pytest-asyncio==0.21.1
# httpx==0.25.2
```

**Notes:**
- `asyncpg` requires `gcc` + `libpq-dev` at build time (handled in builder stage)
- `PyJWT` is used only for dev-mode auth fallback (not in production)
- `psycopg2-binary` is omitted — `asyncpg` is the only PostgreSQL driver needed
- Test dependencies are commented out; use a separate `requirements-dev.txt` for CI

---

## entrypoint.sh

**Path:** `/home/dave/docker/compose/snatched/entrypoint.sh`

```bash
#!/bin/bash
set -e

echo "[snatched] Startup script running..."
echo "[snatched] Python: $(python --version)"
echo "[snatched] Working directory: $(pwd)"

# Wait for PostgreSQL to be ready
echo "[snatched] Waiting for PostgreSQL at ${DB_HOST:-memory-store}..."
until pg_isready -h "${DB_HOST:-memory-store}" \
                 -U "${DB_USER:-snatched}" \
                 -d "${DB_NAME:-snatched}" \
                 -q 2>/dev/null; do
    echo "[snatched]   ... postgres not ready, retrying in 2s"
    sleep 2
done
echo "[snatched] PostgreSQL is ready."

# Database schema is created by FastAPI lifespan (init_schema()) on first startup.
echo "[snatched] Schema will be initialized by FastAPI lifespan on first request."

# Start uvicorn
echo "[snatched] Starting uvicorn on 0.0.0.0:8000 with 4 workers..."
exec uvicorn snatched.app:create_app \
    --factory \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info
```

**Make executable after writing:**
```bash
chmod +x /home/dave/docker/compose/snatched/entrypoint.sh
# Fix CRLF if written from Windows/WSL:
sed -i 's/\r$//' /home/dave/docker/compose/snatched/entrypoint.sh
```

---

## docker-compose.yml — Service Block

**Path:** `/home/dave/docker/compose/docker-compose.yml`

**Append this service block** to the existing `services:` section. Do NOT replace the existing file.

The existing compose file uses:
- Networks: `dashboard-net` (172.20.1.0/24), `memory-net` (172.20.6.0/24) — both external
- Existing services: `memory-store` (172.20.6.10), `dashboard` (172.20.1.20), `reverse-proxy` (172.20.1.10)
- Existing secrets block: `memory_db_password`, `rclone_config`, `backup_gpg_key`, `immich_db_password`

```yaml
  # --- Snatched: Snapchat Export Processor ---
  snatched:
    build:
      context: ./snatched
      dockerfile: Dockerfile
    container_name: snatched
    hostname: snatched
    networks:
      dashboard-net:
        ipv4_address: 172.20.1.30
      memory-net:
        ipv4_address: 172.20.6.21

    volumes:
      # Persistent user data: uploads, processing working dir, output files
      - /home/dave/docker/volumes/snatched/data:/data

      # Server configuration (read-only)
      - /home/dave/docker/configs/snatched/snatched.toml:/app/snatched.toml:ro

      # Application logs
      - /home/dave/docker/volumes/snatched/logs:/app/logs

      # Optional: store output on NAS instead of SSD
      # - /mnt/nas-pool/snatched/output:/nas-output:rw

    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "4.0"
        reservations:
          memory: 1G
          cpus: "2.0"

    restart: unless-stopped

    environment:
      # PostgreSQL connection
      - DB_HOST=memory-store
      - DB_USER=snatched
      - DB_NAME=snatched
      - SNATCHED_DB_URL=postgresql://snatched:${SNATCHED_DB_PASSWORD}@memory-store:5432/snatched

      # Application settings
      - SNATCHED_DATA_DIR=/data
      - SNATCHED_MAX_UPLOAD_BYTES=5368709120
      - SNATCHED_DEV_MODE=0

      # Timezone (must match host)
      - TZ=America/Chicago

    secrets:
      - snatched_db_password

    healthcheck:
      test: ["CMD", "curl", "-sf", "http://127.0.0.1:8000/api/health"]
      interval: 30s
      timeout: 10s
      start_period: 15s
      retries: 3

    depends_on:
      memory-store:
        condition: service_healthy

    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

    labels:
      com.dave.zone: "dashboard"
      com.dave.role: "snatched"

      # Traefik LAN routing (HTTP, no auth — LAN only)
      traefik.enable: "true"
      traefik.http.routers.snatched-lan.rule: "Host(`snatched.local`)"
      traefik.http.routers.snatched-lan.service: "snatched-svc"
      traefik.http.routers.snatched-lan.entrypoints: "web"
      traefik.http.services.snatched-svc.loadbalancer.server.port: "8000"

      # Traefik HTTPS routing (after Step 9 — uncomment when domain + TLS are configured)
      # traefik.http.routers.snatched-https.rule: "Host(`snatched.yourdomain.com`)"
      # traefik.http.routers.snatched-https.service: "snatched-svc"
      # traefik.http.routers.snatched-https.entrypoints: "websecure"
      # traefik.http.routers.snatched-https.tls.certresolver: "letsencrypt"
      # traefik.http.middlewares.snatched-auth.forwardauth.address: "http://authelia:9091/api/verify?rd=https://auth.yourdomain.com"
      # traefik.http.routers.snatched-https.middlewares: "snatched-auth"
```

**Add to the existing `secrets:` block at the top of docker-compose.yml:**

```yaml
  # Add this entry alongside the existing secrets:
  snatched_db_password:
    file: /home/dave/docker/secrets/snatched_db_password
```

The existing secrets block looks like:
```yaml
secrets:
  memory_db_password:
    file: /home/dave/docker/secrets/memory_db_password
  rclone_config:
    file: /home/dave/docker/secrets/rclone.conf
  backup_gpg_key:
    file: /home/dave/docker/secrets/backup-gpg-public.asc
  immich_db_password:
    file: /home/dave/docker/secrets/immich_db_password
  # Add here:
  snatched_db_password:
    file: /home/dave/docker/secrets/snatched_db_password
```

---

## PostgreSQL Setup

**One-time setup.** Run before starting the snatched container for the first time.

### Step 1: Generate the Database Password

```bash
# Generate a random 32-character password
openssl rand -base64 32 > /home/dave/docker/secrets/snatched_db_password
chmod 600 /home/dave/docker/secrets/snatched_db_password

# Save the password for use below
SNATCHED_PASS=$(cat /home/dave/docker/secrets/snatched_db_password)
echo "Password: $SNATCHED_PASS"
```

### Step 2: Create Database and User

**Path:** `/home/dave/docker/compose/snatched/init-db.sql`

```sql
-- One-time setup: create snatched database and user.
-- Run as memory_admin against the postgres database.
-- IMPORTANT: Replace PLACEHOLDER_PASSWORD with the actual password.

-- Create database
CREATE DATABASE snatched
    ENCODING 'UTF8'
    LC_COLLATE 'en_US.UTF-8'
    LC_CTYPE 'en_US.UTF-8'
    TEMPLATE template0;

-- Create user
CREATE USER snatched WITH PASSWORD 'PLACEHOLDER_PASSWORD';

-- Grant privileges
ALTER ROLE snatched SET client_encoding TO 'utf8';
ALTER ROLE snatched SET default_transaction_isolation TO 'read committed';
ALTER ROLE snatched SET timezone TO 'UTC';

GRANT ALL PRIVILEGES ON DATABASE snatched TO snatched;
ALTER DATABASE snatched OWNER TO snatched;

-- Connect to snatched database and grant schema privileges
\c snatched
GRANT ALL ON SCHEMA public TO snatched;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO snatched;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO snatched;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO snatched;
```

**Run against the memory-store container:**

```bash
# Substitute the real password into the SQL file
SNATCHED_PASS=$(cat /home/dave/docker/secrets/snatched_db_password)

sed "s/PLACEHOLDER_PASSWORD/${SNATCHED_PASS}/g" \
    /home/dave/docker/compose/snatched/init-db.sql \
  | sg docker -c "docker exec -i memory-store psql -U memory_admin -d postgres"
```

**Verify the setup:**

```bash
sg docker -c "docker exec -it memory-store psql -U snatched -d snatched -c 'SELECT version();'"
```

### Step 3: Update snatched.toml with the Password

```bash
SNATCHED_PASS=$(cat /home/dave/docker/secrets/snatched_db_password)
sed -i "s|REPLACE_WITH_PASSWORD|${SNATCHED_PASS}|g" \
    /home/dave/docker/configs/snatched/snatched.toml
```

---

## snatched.toml Configuration

**Path:** `/home/dave/docker/configs/snatched/snatched.toml`

Mounted read-only into the container at `/app/snatched.toml`.

```toml
# Snatched v3 — Server Configuration

[server]
host = "0.0.0.0"
port = 8000
data_dir = "/data"
max_upload_bytes = 5368709120  # 5 GB

# Dev mode: accepts JWT cookie instead of Authelia header
# Set to false in production
dev_mode = false
dev_jwt_secret = "change-me-in-production"

[database]
# PostgreSQL connection URL
# Password injected at startup via SNATCHED_DB_URL environment variable
# This value is the fallback if env var is not set
postgres_url = "postgresql://snatched:REPLACE_WITH_PASSWORD@memory-store:5432/snatched"
pool_min_size = 5
pool_max_size = 20
pool_timeout_seconds = 30

[pipeline]
batch_size = 500
gps_window_seconds = 300
workers = 4

[exif]
enabled = true
tool = "exiftool"
stay_open = true

[xmp]
enabled = false
alongside_exif = true
include_snatched_ns = true
xmp_fields = ["Title", "Description", "DateCreated", "Creator", "Subject", "Keywords"]

[lanes.memories]
enabled = true
burn_overlays = true
folder_pattern = "memories/{YYYY}/{MM}"

[lanes.chats]
enabled = true
export_text = true
export_png = true
dark_mode = false
folder_pattern = "chat/{ConvName}"

[lanes.stories]
enabled = true
folder_pattern = "stories"

[storage]
default_quota_bytes = 10737418240  # 10 GB per user
upload_retention_days = 30

[logging]
level = "info"
format = "json"
```

**Create config directory and file:**

```bash
mkdir -p /home/dave/docker/configs/snatched
chmod 750 /home/dave/docker/configs/snatched

# Write the config (replace REPLACE_WITH_PASSWORD with actual password afterward)
# Use the sed command from Step 3 above after writing
```

---

## Directory Structure & Permissions

**Create all required directories before starting the container:**

```bash
# Volume directories
mkdir -p /home/dave/docker/volumes/snatched/data
mkdir -p /home/dave/docker/volumes/snatched/logs
chmod 750 /home/dave/docker/volumes/snatched/data

# Config directory (already created above)
mkdir -p /home/dave/docker/configs/snatched
chmod 750 /home/dave/docker/configs/snatched

# Secrets directory (already exists)
ls -la /home/dave/docker/secrets/snatched_db_password

# Build context directories
mkdir -p /home/dave/docker/compose/snatched/snatched/routes
mkdir -p /home/dave/docker/compose/snatched/snatched/processing
mkdir -p /home/dave/docker/compose/snatched/snatched/templates
mkdir -p /home/dave/docker/compose/snatched/snatched/static

# Verify
ls -la /home/dave/docker/volumes/snatched/
ls -la /home/dave/docker/compose/snatched/
```

---

## Networking & Port Map

```
Internet / LAN
    |
    | :80 (HTTP)
    v
Traefik (172.20.1.10)       <-- reverse-proxy container, already running
    |
    | Host: snatched.local → 172.20.1.30:8000
    v
Snatched (172.20.1.30)      <-- FastAPI container (this spec)
    |
    | (memory-net)
    v
PostgreSQL (172.20.6.10)    <-- memory-store container, already running
    port 5432
    database: snatched
```

**Port Allocation:**

| Service | Container IP | Port | Exposure |
|---------|-------------|------|----------|
| snatched | 172.20.1.30 | 8000 | Via Traefik only (no direct host binding) |
| memory-store | 172.20.6.10 | 5432 | Internal only (memory-net) |
| reverse-proxy | 172.20.1.10 | 80 | Host port 80 → external |

**No direct port binding to host.** Traefik routes `snatched.local` on port 80 to the snatched container.

---

## Build & Deploy Steps

### Step 1: Verify Source Files Are in Place

```bash
ls -la /home/dave/docker/compose/snatched/snatched/
ls -la /home/dave/docker/compose/snatched/requirements.txt
ls -la /home/dave/docker/configs/snatched/snatched.toml
ls -la /home/dave/docker/secrets/snatched_db_password
```

### Step 2: Run One-Time PostgreSQL Setup

```bash
# (Only if not already done)
SNATCHED_PASS=$(cat /home/dave/docker/secrets/snatched_db_password)
sed "s/PLACEHOLDER_PASSWORD/${SNATCHED_PASS}/g" \
    /home/dave/docker/compose/snatched/init-db.sql \
  | sg docker -c "docker exec -i memory-store psql -U memory_admin -d postgres"
```

### Step 3: Build the Docker Image

```bash
sg docker -c "docker build -t snatched:3.0 /home/dave/docker/compose/snatched"

# Check image size
sg docker -c "docker images | grep snatched"
```

### Step 4: Validate Compose File

```bash
sg docker -c "docker compose -f /home/dave/docker/compose/docker-compose.yml config --quiet"
```

### Step 5: Start the Container

```bash
sg docker -c "docker compose -f /home/dave/docker/compose/docker-compose.yml up -d snatched"

# Watch logs
sg docker -c "docker compose -f /home/dave/docker/compose/docker-compose.yml logs -f snatched"

# Check health
sg docker -c "docker ps | grep snatched"
```

### Step 6: Verify Connectivity

```bash
# Direct health check
sg docker -c "docker exec snatched curl -s http://127.0.0.1:8000/api/health"

# Via Traefik (snatched.local must resolve to 127.0.0.1 in /etc/hosts or DNS)
curl -H "Host: snatched.local" http://127.0.0.1/api/health

# PostgreSQL connection from inside container
sg docker -c "docker exec snatched pg_isready -h memory-store -U snatched -d snatched"
```

---

## Troubleshooting

### Container Won't Start

```bash
# View full logs
sg docker -c "docker logs snatched"

# Check entrypoint
sg docker -c "docker exec snatched cat /app/entrypoint.sh"

# Check if PostgreSQL is reachable
sg docker -c "docker exec snatched pg_isready -h memory-store -U snatched"

# Verify config is mounted
sg docker -c "docker exec snatched cat /app/snatched.toml | head -10"
```

### PostgreSQL Connection Error

```bash
# Check password
cat /home/dave/docker/secrets/snatched_db_password

# Verify database exists
sg docker -c "docker exec memory-store psql -U memory_admin -l | grep snatched"

# Test connection manually
PASS=$(cat /home/dave/docker/secrets/snatched_db_password)
sg docker -c "docker exec memory-store psql -U snatched -d snatched -c '\\dp'"
```

### Health Check Failing

```bash
# Check if FastAPI started
sg docker -c "docker exec snatched curl -v http://127.0.0.1:8000/api/health"

# Verify exiftool is available
sg docker -c "docker exec snatched which exiftool && exiftool -ver"

# Verify ffmpeg is available
sg docker -c "docker exec snatched which ffmpeg"

# Verify fonts are installed
sg docker -c "docker exec snatched ls /usr/share/fonts/truetype/dejavu/"
```

### File Permission Issues

```bash
# Check volume ownership (should be UID 1000 = snatched)
ls -la /home/dave/docker/volumes/snatched/data

# Fix if needed (UID 1000 = both dave on host and snatched in container)
sudo chown -R 1000:1000 /home/dave/docker/volumes/snatched/data
sudo chmod 750 /home/dave/docker/volumes/snatched/data

# Verify inside container
sg docker -c "docker exec snatched ls -la /data"
```

---

## Monitoring & Logs

```bash
# Follow application logs
sg docker -c "docker logs -f snatched"

# Get last 50 lines
sg docker -c "docker logs --tail 50 snatched"

# Logs with timestamps
sg docker -c "docker logs -t snatched | tail -20"

# Real-time resource stats
sg docker -c "docker stats snatched"

# Shell access for debugging
sg docker -c "docker exec -it snatched /bin/bash"

# Check environment variables
sg docker -c "docker exec snatched env | grep SNATCHED"
```

---

## Acceptance Criteria

- [ ] Dockerfile builds without errors: `docker build -t snatched:3.0 ./snatched`
- [ ] Final image size is reasonable (less than 600 MB)
- [ ] Multi-stage build reduces image size vs. single-stage
- [ ] Non-root user `snatched` (UID 1000) runs the process
- [ ] `postgresql-client` installed (provides `pg_isready` for `entrypoint.sh`)
- [ ] `fonts-dejavu-core` and `fonts-liberation` installed (for chat renderer)
- [ ] `exiftool`, `ffmpeg`, `imagemagick` all available in container
- [ ] Health check passes: `docker exec snatched curl -sf http://127.0.0.1:8000/api/health`
- [ ] Compose file validates: `docker compose config --quiet`
- [ ] `snatched` service starts: `docker compose up -d snatched`
- [ ] Container reaches HEALTHY state within 60s
- [ ] PostgreSQL connection confirmed: `docker exec snatched pg_isready -h memory-store -U snatched`
- [ ] Traefik routes `snatched.local` to container: `curl -H "Host: snatched.local" http://127.0.0.1/api/health`
- [ ] `/data/` volume persists across container restart
- [ ] Config file mounted read-only at `/app/snatched.toml`
- [ ] Secret mounted at `/run/secrets/snatched_db_password`
- [ ] Logs visible via `docker logs snatched`
- [ ] Resource limits enforced: 2 GB RAM, 4 CPUs
- [ ] Restart policy: `unless-stopped` (container auto-restarts after crash)
- [ ] `init-db.sql` creates `snatched` database and user with correct privileges
- [ ] `entrypoint.sh` waits for PostgreSQL before launching uvicorn
- [ ] `entrypoint.sh` has no CRLF line endings (`sed -i 's/\r$//'`)
- [ ] `snatched_db_password` secret added to compose secrets block
- [ ] IP 172.20.1.30 is not already used by another container

---

**End of Spec 10**
