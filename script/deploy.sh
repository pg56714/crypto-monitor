#!/bin/bash
set -e  # Exit on any error

echo "🚀 Starting deployment at $(date)"

# Step 1: Build new image with a temporary tag
echo "📦 Building new image..."
docker build --no-cache -t crypto-notifier:new .

# Step 2: Stop and remove old container if it exists (any state)
OLD_CONTAINER=$(docker ps -aq -f name=^/crypto-notifier$)
if [ -n "$OLD_CONTAINER" ]; then
    echo "🛑 Stopping and removing old container (any state)..."
    docker rm -f crypto-notifier || true
fi

# Step 3: Start new container
echo "▶️ Starting new container..."
docker run -d --name crypto-notifier --restart unless-stopped crypto-notifier:new

# Step 4: Wait a moment for container to start
sleep 5

# Step 5: Verify new container is running
if [ ! "$(docker ps -q -f name=crypto-notifier)" ]; then
    echo "❌ Container failed to start!"
    docker logs crypto-notifier || true
    exit 1
fi

# Step 6: Show container status
echo "✅ Container is running:"
docker ps -f name=crypto-notifier

# Step 7: Clean up images safely
echo "🧹 Deployment successful. Cleaning up..."
docker tag crypto-notifier:new crypto-notifier:latest
docker rmi crypto-notifier:new || true
docker image prune -f

echo "🎉 Deployment completed successfully at $(date)"
