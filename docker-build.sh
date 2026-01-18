#!/bin/bash

# docker-build.sh - Build and push Kalshi AI Trading Bot to DockerHub

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
DOCKER_USERNAME=${DOCKER_USERNAME:-""}
IMAGE_NAME="kalshi-ai-trading-bot"
VERSION=${VERSION:-"latest"}

# Check if Docker username is set
if [ -z "$DOCKER_USERNAME" ]; then
    print_error "DOCKER_USERNAME environment variable is not set"
    echo "Usage: DOCKER_USERNAME=yourname ./docker-build.sh"
    exit 1
fi

# Full image name
FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"

print_status "Starting Docker build process"
echo "=================================="
echo "Image: ${FULL_IMAGE_NAME}"
echo "=================================="

# Build the Docker image
print_status "Building Docker image..."
docker build -t ${FULL_IMAGE_NAME} .

if [ $? -eq 0 ]; then
    print_success "Docker image built successfully: ${FULL_IMAGE_NAME}"
else
    print_error "Docker build failed"
    exit 1
fi

# Tag as latest if a specific version was provided
if [ "$VERSION" != "latest" ]; then
    print_status "Tagging image as latest..."
    docker tag ${FULL_IMAGE_NAME} ${DOCKER_USERNAME}/${IMAGE_NAME}:latest
fi

# Ask if user wants to push to DockerHub
read -p "Do you want to push the image to DockerHub? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Check if logged in to Docker
    print_status "Checking Docker login status..."
    if ! docker info | grep -q "Username"; then
        print_warning "Not logged in to Docker. Attempting login..."
        docker login
    fi
    
    # Push the image
    print_status "Pushing image to DockerHub..."
    docker push ${FULL_IMAGE_NAME}
    
    if [ "$VERSION" != "latest" ]; then
        print_status "Pushing latest tag..."
        docker push ${DOCKER_USERNAME}/${IMAGE_NAME}:latest
    fi
    
    print_success "Image pushed successfully!"
    echo ""
    echo "To pull this image on your Synology NAS:"
    echo "  docker pull ${FULL_IMAGE_NAME}"
else
    print_status "Skipping DockerHub push"
fi

# Display image info
print_status "Docker image information:"
docker images | grep ${IMAGE_NAME} | head -3

print_success "Build process complete!"
echo ""
echo "Next steps:"
echo "1. On your Synology NAS, pull the image:"
echo "   docker pull ${FULL_IMAGE_NAME}"
echo ""
echo "2. Create a .env file with your API keys"
echo ""
echo "3. Run the container using docker-compose:"
echo "   docker-compose up -d"
echo ""
echo "4. Check logs:"
echo "   docker-compose logs -f kalshi-trading-bot"
