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
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 --retries 5 -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Copy application source (backend/.dockerignore excludes .env, venv, *.db, etc.)
COPY . .

EXPOSE 8000

# Run 4 Uvicorn workers for production throughput.
# Lower to 1 for debugging or single-core hosts.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
