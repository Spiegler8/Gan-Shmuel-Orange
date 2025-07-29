#!/bin/bash

BRANCH="$1" # arg
REPO_URL="https://github.com/Spiegler8/Gan-Shmuel-Orange.git"  # 🔁 Replace with your real URL
TMP_DIR="/tmp/ci_run_$(date +%s)"

#shouldnt be here !!
# Load Slack webhook from env file
# source ~/slack.env
# # Function to send Slack message
# send_slack_msg() {
#   local msg="$1"
#   curl -X POST -H 'Content-type: application/json' \
#     --data "{\"text\":\"$msg\"}" \
#     "$CI_BOT_CHANNEL"
# }
# # Send start message
# send_slack_msg "*[CI]* :wave: Hello from run_tests.sh on branch *$BRANCH*"
# 
# 
# echo "[CI] 🚀 Starting CI for branch: $BRANCH" #log

# Clone the repo
echo "[CI] Cloning $BRANCH..."
git clone --quiet --depth=1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR"
if [ $? -ne 0 ]; then
    echo "[CI] ❌ Clone failed"
    exit 1
fi

cd "$TMP_DIR/src" || { echo "[CI] ❌ Missing src dir"; exit 1; }

# Select correct service path
if [[ "$BRANCH" == "billing-main" ]]; then
    SERVICE_DIR="billing_team"
    COMPOSE_FILE="docker-compose.yml"
    CONTAINER_NAME="billing_app" # name convantion , service or container ?
elif [[ "$BRANCH" == "weight-main" ]]; then
    SERVICE_DIR="Weight-Team"
    COMPOSE_FILE="docker-compose.yml"
    CONTAINER_NAME="weight_app" #name convantion , service or container ?
elif [[ "$BRANCH" == "CI/testenv" ]]; then 
	SERVICE_DIR="devOps"
    COMPOSE_FILE="docker-compose.yml"
    CONTAINER_NAME="ci-portal" # name convantion , service or container ?
else
    echo "[CI] ℹ️ No CI action needed for branch: $BRANCH"
    rm -rf "$TMP_DIR"
    exit 0
fi

cd "$SERVICE_DIR" || { echo "[CI] ❌ Missing $SERVICE_DIR"; exit 1; }

# Start docker-compose
echo "[CI] 🔧 Running docker-compose up..."
docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1
docker compose -f "$COMPOSE_FILE" up -d --build >/dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "[CI] ❌ Docker compose failed"
    docker-compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1
    rm -rf "$TMP_DIR"
    exit 1
fi

# Run pytest inside container
echo "[CI] 🧪 Running pytest in container: $CONTAINER_NAME"
docker compose -f "$COMPOSE_FILE" exec -T "$CONTAINER_NAME" pytest tests/
STATUS=$?

# Cleanup
echo "[CI] 🧹 Cleaning up..."
docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1
rm -rf "$TMP_DIR"

# Final result
if [ $STATUS -eq 0 ]; then
    echo "[CI] ✅ Tests PASSED for $BRANCH"
else
    echo "[CI] ❌ Tests FAILED for $BRANCH"
fi

exit $STATUS
