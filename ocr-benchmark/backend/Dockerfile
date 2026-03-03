FROM python:3.11-slim

WORKDIR /app

# ---- system deps (important for opencv, easyocr, camelot/pdf tools) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    poppler-utils \
    ghostscript \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better docker caching)
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --default-timeout=300 --retries=10 -r /app/requirements.txt

# Copy the backend code
COPY . /app

# Expose FastAPI port
EXPOSE 8000

# Run server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]