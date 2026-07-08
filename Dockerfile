FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python deps first (cached layer)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download the U2-Net model into the image layer
# Avoids cold-start delay on first request
RUN python -c "\
from rembg import new_session; \
s = new_session('u2net'); \
print('U2-Net model downloaded and ready.')"

# Copy backend application code
COPY backend/app ./app

# Copy frontend static files into a known path inside the container
COPY frontend ./frontend

# Create data directories for uploads, outputs, and SQLite DB
RUN mkdir -p /app/data/uploads /app/data/outputs

# Environment defaults (overridable at runtime)
ENV DATABASE_URL=/app/data/clearcut.db
ENV UPLOADS_DIR=/app/data/uploads
ENV OUTPUTS_DIR=/app/data/outputs
ENV FRONTEND_DIR=/app/frontend
ENV SERVE_STATIC=true

EXPOSE 8000

# Use shell form so Railway's injected $PORT env var is expanded at runtime
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
