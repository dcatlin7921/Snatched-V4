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

# Wait for Redis to be ready
REDIS_HOST="${SNATCHED_REDIS_HOST:-immich-redis}"
REDIS_PORT="${SNATCHED_REDIS_PORT:-6379}"
echo "[snatched] Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT}..."
until python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('${REDIS_HOST}', ${REDIS_PORT})); s.close()" 2>/dev/null; do
    echo "[snatched]   ... redis not ready, retrying in 2s"
    sleep 2
done
echo "[snatched] Redis is ready."

# Start ARQ worker in the background
echo "[snatched] Starting ARQ worker (max_jobs=${SNATCHED_MAX_WORKER_JOBS:-4})..."
arq snatched.worker.WorkerSettings &
ARQ_PID=$!

# Start uvicorn in the foreground
echo "[snatched] Starting uvicorn on 0.0.0.0:8000 with 4 workers..."
uvicorn snatched.app:create_app \
    --factory \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info &
UVICORN_PID=$!

# Trap SIGTERM/SIGINT and forward to both processes
trap 'echo "[snatched] Shutting down..."; kill $UVICORN_PID $ARQ_PID 2>/dev/null; wait' SIGTERM SIGINT

# Wait for either process to exit
wait -n $UVICORN_PID $ARQ_PID
EXIT_CODE=$?
echo "[snatched] Process exited with code $EXIT_CODE, shutting down..."
kill $UVICORN_PID $ARQ_PID 2>/dev/null
wait
exit $EXIT_CODE
