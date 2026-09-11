#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────────
#  start.sh — Production entrypoint for the AI Assistant backend container.
#
#  Steps:
#    1. Wait for PostgreSQL to be reachable (up to 60 s, retries every 2 s).
#    2. Run "alembic upgrade head" — backward-compatible migrations only.
#    3. Start Uvicorn with 4 workers.
#
#  Zero-downtime guarantee:
#    Render also runs `preDeployCommand: alembic upgrade head` before the new
#    container starts receiving traffic. This script is a second safety net
#    so that the DB is definitely migrated even on first-deploy where
#    preDeployCommand may not yet be configured.
# ─────────────────────────────────────────────────────────────────────────────
set -e

# ── 1. Wait for the database ──────────────────────────────────────────────────
echo "⏳  Waiting for database…"
MAX_RETRIES=30
RETRY=0
until python -c "
import os, sys
try:
    import psycopg2
    conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=3)
    conn.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
    RETRY=$((RETRY + 1))
    if [ "$RETRY" -ge "$MAX_RETRIES" ]; then
        echo "❌  Database not reachable after ${MAX_RETRIES} retries. Aborting."
        exit 1
    fi
    echo "   Retry ${RETRY}/${MAX_RETRIES} — waiting 2 s…"
    sleep 2
done
echo "✅  Database is reachable."

# ── 2. Run Alembic migrations ─────────────────────────────────────────────────
echo "🔄  Running Alembic migrations…"
alembic upgrade head
echo "✅  Migrations complete."

# ── 3. Start Uvicorn ──────────────────────────────────────────────────────────
echo "🚀  Starting Uvicorn (4 workers)…"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 4
