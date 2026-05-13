# MathCraft OCR Web Server Dockerfile
# =====================================
# Build:  docker build -t mathcraft-ocr-server -f web/Dockerfile .
# Run:    docker run -p 8000:8000 -v mathcraft-models:/root/.mathcraft mathcraft-ocr-server
#
# Models are auto-downloaded on first use and cached in /root/.mathcraft.

FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies for opencv + onnxruntime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install mathcraft_ocr (the OCR engine)
COPY pyproject.toml requirements.txt ./
COPY mathcraft_ocr/ mathcraft_ocr/
RUN pip install --no-cache-dir -e ".[cpu]" && \
    pip install --no-cache-dir -r requirements.txt

# Copy web server and install web deps
COPY web/requirements.txt web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt

COPY web/ web/

# Expose port
EXPOSE 8000

# Start server
CMD ["python", "-m", "uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8000"]
