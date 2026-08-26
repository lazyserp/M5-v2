# Base Python Image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    QDRANT_URL=http://qdrant:6333 \
    WORKSPACE_ROOT=/workspace

# Set working directory
WORKDIR /app

# Install system dependencies, git, curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy workspace source code
COPY . .

# Expose M5 Context Engine (8000)
EXPOSE 8000

# Start M5 Server
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
