FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

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
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 --retries 5 torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --default-timeout=100 --retries 5 -r requirements.txt

# Copy backend application source
COPY backend/ .

EXPOSE 8000

# Render free tier provides 512MB RAM. Use 1 worker to prevent OOM.
# Bind dynamically to $PORT provided by Render (default to 8000).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
