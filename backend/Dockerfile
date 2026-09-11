FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Use /app as the working directory so volume mounts (vector_db, uploads)
# resolve correctly against /app/vector_db and /app/uploads.
WORKDIR /app

# Install system dependencies including PostgreSQL dev tools and OCR tools
RUN apt-get update -o Acquire::Retries=3 && apt-get install -y -o Acquire::Retries=3 --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 --retries 5 torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --default-timeout=100 --retries 5 -r requirements.txt

# Copy application source (backend/.dockerignore excludes .env, venv, *.db, etc.)
COPY . .

# Make startup script executable
RUN chmod +x /app/start.sh

EXPOSE 8000

# Container-level health check (Render also probes /api/v1/health via HTTP)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Entrypoint: waits for DB → runs Alembic migrations → starts Uvicorn
CMD ["/app/start.sh"]
