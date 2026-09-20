#!/bin/sh
# entrypoint.sh — Run Alembic migrations then start the server.
# This ensures the database schema is always up-to-date before serving traffic.

set -e

echo "[entrypoint] Running Alembic migrations..."
cd /app
alembic upgrade head
echo "[entrypoint] Migrations complete. Starting uvicorn..."

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1
