#!/bin/bash

BRANCH=$1
REPO_PATH="/home/ubuntu/myrepo"
LOG_FILE="/log/${BRANCH}.log"

echo "[Runner] Starting test for branch: $BRANCH" >> $LOG_FILE
cd "$REPO_PATH"

# Fetch latest changes from the branch
echo "[Runner] Pulling latest $BRANCH..." >> $LOG_FILE
git fetch origin $BRANCH >> $LOG_FILE 2>&1
git checkout $BRANCH >> $LOG_FILE 2>&1
git reset --hard origin/$BRANCH >> $LOG_FILE 2>&1

#git pull repo somehow
# Navigate to docker-compose location
cd src/chat || { echo "[Runner] chat/ folder not found" >> $LOG_FILE; exit 1; }

# Run docker compose up
echo "[Runner] Running docker-compose up..." >> $LOG_FILE
docker-compose up -d >> $LOG_FILE 2>&1

# Simple test: Check if containers are up
echo "[Runner] Verifying containers..." >> $LOG_FILE
docker ps --filter "name=chat" --format "{{.Names}}: {{.Status}}" >> $LOG_FILE 2>&1

echo "[Runner] Test completed at $(date)" >> $LOG_FILE

