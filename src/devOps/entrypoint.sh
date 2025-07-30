#!/bin/bash

set -e  # Exit on any error
set -o pipefail

echo "[CI] Waiting for Docker daemon to be ready..."
while ! docker info > /dev/null 2>&1; do
  sleep 1
done
echo "[CI] Docker daemon is ready."

echo "[CI] Running docker-compose in /weight"
cd /weight
docker compose up -d --build || { echo "❌ Failed in /weight"; exit 1; }

echo "[CI] Running docker-compose in /billing"
cd /billing
docker compose up -d --build || { echo "❌ Failed in /billing"; exit 1; }

echo "[CI] Starting webhook server"
cd /app
exec python webhook_server.py
