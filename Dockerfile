#  Base Python Image
FROM python:3.11-slim

#  Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

#  Set working directory
WORKDIR /app

# Install system dependencies for Tree-Sitter & C/C++ compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

#  Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

#  Copy workspace source code
COPY . .

# Expose REST API port
EXPOSE 8000

# Start M5 v2 FastAPI Server
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
