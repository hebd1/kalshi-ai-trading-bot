#!/bin/bash

# Kalshi Trading Bot - Post-Deployment Verification Script
# This script verifies that the Docker deployment is working correctly after deployment

set -e

echo "🔍 Verifying Kalshi Trading Bot Deployment..."
echo "================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        "SUCCESS")
            echo -e "${GREEN}✅ $message${NC}"
            ;;
        "WARNING")
            echo -e "${YELLOW}⚠️  $message${NC}"
            ;;
        "ERROR")
            echo -e "${RED}❌ $message${NC}"
            ;;
        "INFO")
            echo -e "${BLUE}ℹ️  $message${NC}"
            ;;
    esac
}

# Check if Docker is running
print_status "INFO" "Checking Docker daemon..."
if ! docker info > /dev/null 2>&1; then
    print_status "ERROR" "Docker daemon is not running"
    exit 1
fi
print_status "SUCCESS" "Docker daemon is running"

# Check container is running
print_status "INFO" "Checking if container is running..."
CONTAINER_ID=$(docker ps -q -f name=kalshi-trading-bot)
if [ -z "$CONTAINER_ID" ]; then
    print_status "ERROR" "Container is not running"
    echo "Try: docker-compose up -d"
    exit 1
fi
print_status "SUCCESS" "Container is running (ID: $CONTAINER_ID)"

# Check container health
print_status "INFO" "Checking container health..."
HEALTH=$(docker inspect --format='{{.State.Health.Status}}' kalshi-trading-bot 2>/dev/null)
case $HEALTH in
    "healthy")
        print_status "SUCCESS" "Container is healthy"
        ;;
    "unhealthy")
        print_status "ERROR" "Container is unhealthy"
        echo "Check logs: docker logs kalshi-trading-bot"
        ;;
    "starting")
        print_status "WARNING" "Container health check is starting..."
        ;;
    *)
        print_status "WARNING" "Container health status: $HEALTH"
        ;;
esac

# Check container uptime
print_status "INFO" "Checking container uptime..."
UPTIME=$(docker inspect --format='{{.State.StartedAt}}' kalshi-trading-bot)
print_status "INFO" "Container started at: $UPTIME"

# Check logs for recent errors
print_status "INFO" "Checking recent logs for errors..."
ERROR_COUNT=$(docker logs --since="5m" kalshi-trading-bot 2>&1 | grep -i error | wc -l)
if [ "$ERROR_COUNT" -eq 0 ]; then
    print_status "SUCCESS" "No errors in recent logs"
else
    print_status "WARNING" "Found $ERROR_COUNT error(s) in recent logs (last 5 minutes)"
    echo "Recent errors:"
    docker logs --since="5m" kalshi-trading-bot 2>&1 | grep -i error | tail -5
fi

# Check if Python process is running
print_status "INFO" "Checking Python processes..."
PYTHON_PROCS=$(docker exec kalshi-trading-bot ps aux | grep python | grep -v grep | wc -l)
if [ "$PYTHON_PROCS" -gt 0 ]; then
    print_status "SUCCESS" "Python processes are running ($PYTHON_PROCS processes)"
else
    print_status "ERROR" "No Python processes found"
fi

# Check database file
print_status "INFO" "Checking database file..."
if docker exec kalshi-trading-bot test -f /app/trading_system.db; then
    DB_SIZE=$(docker exec kalshi-trading-bot stat -c%s /app/trading_system.db)
    print_status "SUCCESS" "Database file exists (size: $DB_SIZE bytes)"
else
    print_status "WARNING" "Database file not found (will be created on first run)"
fi

# Check API keys
print_status "INFO" "Checking API key configuration..."
if docker exec kalshi-trading-bot test -f /app/keys/kalshi_private_key.pem; then
    KEY_PERMS=$(docker exec kalshi-trading-bot stat -c%a /app/keys/kalshi_private_key.pem)
    if [ "$KEY_PERMS" = "400" ] || [ "$KEY_PERMS" = "600" ]; then
        print_status "SUCCESS" "Private key file found with correct permissions ($KEY_PERMS)"
    else
        print_status "WARNING" "Private key permissions are $KEY_PERMS (recommend 400)"
    fi
else
    print_status "ERROR" "Private key file not found"
fi

# Check environment variables
print_status "INFO" "Checking environment variables..."
ENV_VARS=("KALSHI_API_KEY" "XAI_API_KEY" "KALSHI_PRIVATE_KEY")
for var in "${ENV_VARS[@]}"; do
    if docker exec kalshi-trading-bot printenv "$var" > /dev/null 2>&1; then
        print_status "SUCCESS" "$var is set"
    else
        print_status "ERROR" "$var is not set"
    fi
done

# Test API connectivity (optional - requires valid credentials)
print_status "INFO" "Testing API connectivity..."
if docker exec kalshi-trading-bot python -c "
import asyncio
import sys
sys.path.append('/app')
from src.clients.kalshi_client import KalshiClient

async def test_api():
    try:
        client = KalshiClient()
        balance = await client.get_balance()
        await client.close()
        print('API test successful')
        return True
    except Exception as e:
        print(f'API test failed: {e}')
        return False

result = asyncio.run(test_api())
sys.exit(0 if result else 1)
" > /dev/null 2>&1; then
    print_status "SUCCESS" "API connectivity test passed"
else
    print_status "WARNING" "API connectivity test failed (check credentials and network)"
fi

# Check volume mounts
print_status "INFO" "Checking volume mounts..."
MOUNTS=$(docker inspect kalshi-trading-bot --format '{{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}')
if [ -n "$MOUNTS" ]; then
    print_status "SUCCESS" "Volume mounts configured"
    echo "  $MOUNTS"
else
    print_status "WARNING" "No volume mounts found"
fi

# Check resource usage
print_status "INFO" "Checking resource usage..."
STATS=$(docker stats kalshi-trading-bot --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | tail -1)
if [ -n "$STATS" ]; then
    print_status "INFO" "Resource usage: $STATS"
else
    print_status "WARNING" "Could not retrieve resource stats"
fi

# Final summary
echo ""
echo "================================================="
echo "🎉 Deployment verification complete!"
echo ""

# Show recent log tail
print_status "INFO" "Recent log output (last 10 lines):"
echo "---"
docker logs --tail 10 kalshi-trading-bot
echo "---"

echo ""
echo "📖 Useful commands:"
echo "  View logs:       docker logs -f kalshi-trading-bot"
echo "  Check status:    docker ps -f name=kalshi-trading-bot"
echo "  Container shell: docker exec -it kalshi-trading-bot bash"
echo "  Restart:         docker-compose restart"
echo "  Stop:            docker-compose down"
echo ""