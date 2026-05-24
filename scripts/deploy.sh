#!/bin/bash
set -e  # Exit on any error

# Change to project root directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "🚀 Starting deployment at $(date)"
echo "📂 Working directory: $(pwd)"

if [ ! -f .env ]; then
    echo "❌ Missing .env file. Create one from .env.sample before deploying."
    exit 1
fi

# Step 1: Build new image with a temporary tag
echo "📦 Building new image..."
docker build --no-cache -t crypto-monitor:new .

# Step 2: Stop and remove old container if it exists (any state)
OLD_CONTAINER=$(docker ps -aq -f name=^/crypto-monitor$)
if [ -n "$OLD_CONTAINER" ]; then
    echo "🛑 Stopping and removing old container (any state)..."
    docker rm -f crypto-monitor || true
fi

# Step 3: Start new container
echo "▶️ Starting new container..."
docker run -d --name crypto-monitor --restart unless-stopped --env-file .env crypto-monitor:new

# Step 4: Wait a moment for container to start
sleep 5

# Step 5: Verify new container is running
if [ ! "$(docker ps -q -f name=crypto-monitor)" ]; then
    echo "❌ Container failed to start!"
    docker logs crypto-monitor || true
    exit 1
fi

# Step 6: Show container status
echo "✅ Container is running:"
docker ps -f name=crypto-monitor

# Step 7: Clean up images safely
echo "🧹 Deployment successful. Cleaning up..."
docker tag crypto-monitor:new crypto-monitor:latest
docker rmi crypto-monitor:new || true
docker image prune -f

echo "🎉 Deployment completed successfully at $(date)"
