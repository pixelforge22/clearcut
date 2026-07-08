FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed by rembg and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/outputs

# Environment defaults
ENV DATABASE_URL=/app/data/clearcut.db
ENV UPLOADS_DIR=/app/data/uploads
ENV OUTPUTS_DIR=/app/data/outputs
ENV SERVE_STATIC=true

# Expose port
EXPOSE 8000

# Download the U2-Net model at startup (runtime) to ensure it's cached, then start uvicorn
CMD python -c "from rembg import new_session; new_session('u2net')" && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
