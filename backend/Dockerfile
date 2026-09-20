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

EXPOSE 8000

# Security: run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy Alembic entrypoint (runs migrations before uvicorn)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Transfer ownership of app directory to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Render free tier provides 512MB RAM. Use 1 worker to prevent OOM.
# Alembic migrations run automatically via entrypoint.sh before uvicorn starts.
ENTRYPOINT ["/entrypoint.sh"]
