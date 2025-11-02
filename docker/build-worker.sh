#!/bin/bash
# Build script for Kafka Consumer Worker Docker image
# Usage: ./docker/build-worker.sh [tag]

set -e  # Exit on error

# Configuration
IMAGE_NAME="saas-platform-worker"
DEFAULT_TAG="latest"
TAG="${1:-$DEFAULT_TAG}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Building SaaS Platform Worker Docker Image${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "Image: ${YELLOW}${IMAGE_NAME}:${TAG}${NC}"
echo ""

# Check if Dockerfile exists
if [ ! -f "docker/Dockerfile.worker" ]; then
    echo -e "${RED}ERROR: docker/Dockerfile.worker not found${NC}"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Check if requirements.txt exists
if [ ! -f "backend/requirements.txt" ]; then
    echo -e "${RED}ERROR: backend/requirements.txt not found${NC}"
    exit 1
fi

# Check if worker consumer exists
if [ ! -f "backend/app/worker/consumer.py" ]; then
    echo -e "${RED}ERROR: backend/app/worker/consumer.py not found${NC}"
    echo "Worker consumer module is missing"
    exit 1
fi

# Build the image
echo -e "${GREEN}Building Docker image...${NC}"
docker build \
    -f docker/Dockerfile.worker \
    -t "${IMAGE_NAME}:${TAG}" \
    --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --build-arg VERSION="${TAG}" \
    .

# Check if build was successful
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}Build Successful!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo ""
    echo -e "Image: ${YELLOW}${IMAGE_NAME}:${TAG}${NC}"
    echo ""

    # Show image size
    IMAGE_SIZE=$(docker images "${IMAGE_NAME}:${TAG}" --format "{{.Size}}")
    echo -e "Size: ${YELLOW}${IMAGE_SIZE}${NC}"
    echo ""

    # Show next steps
    echo -e "${GREEN}Next steps:${NC}"
    echo ""
    echo "1. Run the container:"
    echo -e "   ${YELLOW}docker run --env-file .env ${IMAGE_NAME}:${TAG}${NC}"
    echo ""
    echo "2. Run with specific Kafka servers:"
    echo -e "   ${YELLOW}docker run -e KAFKA_BOOTSTRAP_SERVERS=kafka:9092 ${IMAGE_NAME}:${TAG}${NC}"
    echo ""
    echo "3. Check worker logs:"
    echo -e "   ${YELLOW}docker logs -f <container-id>${NC}"
    echo ""
    echo "4. Use with docker-compose:"
    echo -e "   ${YELLOW}docker-compose up worker${NC}"
    echo ""
    echo "5. Push to registry:"
    echo -e "   ${YELLOW}docker tag ${IMAGE_NAME}:${TAG} registry.example.com/${IMAGE_NAME}:${TAG}${NC}"
    echo -e "   ${YELLOW}docker push registry.example.com/${IMAGE_NAME}:${TAG}${NC}"
    echo ""
    echo -e "${YELLOW}Note: The worker requires Kafka and PostgreSQL to be running${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}================================================${NC}"
    echo -e "${RED}Build Failed!${NC}"
    echo -e "${RED}================================================${NC}"
    exit 1
fi
