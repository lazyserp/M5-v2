#!/bin/bash
set -e

echo "[+] Starting official Qdrant Vector Engine with Dashboard..."
cd /qdrant
./qdrant &

# Wait for Qdrant to be ready
until curl -s http://localhost:6333/healthz > /dev/null 2>&1; do
    sleep 0.5
done
echo "[OK] Qdrant Vector Engine & Web Dashboard are online on port 6333."

echo "[+] Starting M5 Context Engine on port 8000..."
cd /app
exec uvicorn src.server:app --host 0.0.0.0 --port 8000
