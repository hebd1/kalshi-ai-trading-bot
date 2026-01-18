#!/bin/bash

# docker-run.sh - Run Kalshi AI Trading Bot on Synology NAS

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
DOCKER_USERNAME=${DOCKER_USERNAME:-"yourusername"}
IMAGE_NAME="kalshi-ai-trading-bot"
VERSION=${VERSION:-"latest"}
CONTAINER_NAME="kalshi-trading-bot"

# Full image name
FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"

print_status "Kalshi AI Trading Bot - Docker Run Script"
echo "=========================================="

# Check if .env file exists
if [ ! -f .env ]; then
    print_error ".env file not found!"
    echo ""
    echo "Please create a .env file with the following variables:"
    echo "  KALSHI_API_KEY=your_api_key"
    echo "  XAI_API_KEY=your_xai_key"
    echo "  DOCKER_USERNAME=your_dockerhub_username"
    echo ""
    exit 1
fi

# Source the .env file to get DOCKER_USERNAME
source .env
FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"

# Check if private key files exist
if [ ! -f kalshi_private_key.pem ]; then
    print_warning "kalshi_private_key.pem not found - demo trading may not work"
fi

if [ ! -f kalshi_private_key.prod.pem ]; then
    print_warning "kalshi_private_key.prod.pem not found - live trading will not work"
fi

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p logs shared keys

# Copy keys to keys directory
if [ -f kalshi_private_key.pem ]; then
    cp kalshi_private_key.pem keys/
fi
if [ -f kalshi_private_key.prod.pem ]; then
    cp kalshi_private_key.prod.pem keys/
fi

# Check if container is already running
if [ "$(docker ps -q -f name=${CONTAINER_NAME})" ]; then
    print_warning "Container ${CONTAINER_NAME} is already running"
    read -p "Do you want to restart it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Stopping existing container..."
        docker stop ${CONTAINER_NAME}
        docker rm ${CONTAINER_NAME}
    else
        print_status "Exiting without changes"
        exit 0
    fi
fi

# Pull the latest image
print_status "Pulling latest image from DockerHub..."
docker pull ${FULL_IMAGE_NAME}

# Run the container
print_status "Starting Kalshi trading bot container..."
docker run -d \
    --name ${CONTAINER_NAME} \
    --restart unless-stopped \
    --env-file .env \
    -e PYTHONUNBUFFERED=1 \
    -e PYTHONPATH=/app \
    -v $(pwd)/logs:/app/logs \
    -v $(pwd)/shared:/app/shared \
    -v $(pwd)/keys:/app/keys:ro \
    -v $(pwd)/trading_system.db:/app/trading_system.db \
    ${FULL_IMAGE_NAME}

if [ $? -eq 0 ]; then
    print_success "Container started successfully!"
    echo ""
    print_status "Container information:"
    docker ps -f name=${CONTAINER_NAME}
    echo ""
    print_status "View logs with:"
    echo "  docker logs -f ${CONTAINER_NAME}"
    echo ""
    print_status "Stop container with:"
    echo "  docker stop ${CONTAINER_NAME}"
    echo ""
    print_status "Container stats:"
    docker stats ${CONTAINER_NAME} --no-stream
else
    print_error "Failed to start container"
    exit 1
fi
