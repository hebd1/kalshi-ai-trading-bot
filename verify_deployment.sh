#!/bin/bash

# Deployment Verification Script for Kalshi AI Trading Bot
# This script verifies that all necessary components are in place for deployment

set -e

echo "🔍 Kalshi AI Trading Bot Deployment Verification"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track verification status
ERRORS=0
WARNINGS=0

# Function to check file existence
check_file() {
    if [ -f "$1" ]; then
        echo -e "✅ ${GREEN}$1${NC} exists"
    else
        echo -e "❌ ${RED}$1${NC} is missing"
        ((ERRORS++))
    fi
}

# Function to check directory existence
check_directory() {
    if [ -d "$1" ]; then
        echo -e "✅ ${GREEN}$1${NC} directory exists"
    else
        echo -e "❌ ${RED}$1${NC} directory is missing"
        ((ERRORS++))
    fi
}

# Function to check optional file
check_optional_file() {
    if [ -f "$1" ]; then
        echo -e "✅ ${GREEN}$1${NC} exists (optional)"
    else
        echo -e "⚠️  ${YELLOW}$1${NC} is missing (optional)"
        ((WARNINGS++))
    fi
}

echo ""
echo "📦 Checking Docker Configuration Files"
echo "-------------------------------------"
check_file "Dockerfile"
check_file ".dockerignore"
check_file "docker-compose.yml"
check_file "docker-compose.synology.yml"
check_file "requirements.txt"

echo ""
echo "🔧 Checking GitHub Actions Configuration"
echo "----------------------------------------"
check_directory ".github/workflows"
check_file ".github/workflows/ci-cd.yml"

echo ""
echo "🐍 Checking Python Application Files"
echo "------------------------------------"
check_file "beast_mode_bot.py"
check_file "src/__init__.py"
check_directory "src/clients"
check_directory "src/jobs"
check_directory "src/strategies"
check_directory "src/utils"
check_directory "src/config"

echo ""
echo "📝 Checking Configuration Templates"
echo "-----------------------------------"
check_file ".env.docker.example"
check_optional_file "env.template"

echo ""
echo "🔒 Checking Security Files (should exist for production)"
echo "--------------------------------------------------------"
check_optional_file "kalshi_private_key.pem"
check_optional_file "kalshi_private_key.prod.pem"
if [ ! -f "kalshi_private_key.pem" ] && [ ! -f "kalshi_private_key.prod.pem" ]; then
    echo -e "⚠️  ${YELLOW}No API key files found - ensure they are available on deployment target${NC}"
    ((WARNINGS++))
fi

echo ""
echo "🧪 Checking Test Configuration"
echo "------------------------------"
check_file "run_tests.py"
check_directory "tests"
check_optional_file "requirements-dev.txt"

echo ""
echo "📊 Python Dependency Check"
echo "---------------------------"
if command -v python3 &> /dev/null; then
    echo -e "✅ ${GREEN}Python 3${NC} is available"
    python3 --version
else
    echo -e "❌ ${RED}Python 3${NC} is not available"
    ((ERRORS++))
fi

if command -v pip3 &> /dev/null; then
    echo -e "✅ ${GREEN}pip3${NC} is available"
else
    echo -e "❌ ${RED}pip3${NC} is not available"
    ((ERRORS++))
fi

echo ""
echo "🐳 Docker Environment Check"
echo "---------------------------"
if command -v docker &> /dev/null; then
    echo -e "✅ ${GREEN}Docker${NC} is available"
    docker --version
else
    echo -e "❌ ${RED}Docker${NC} is not available"
    ((ERRORS++))
fi

echo ""
echo "📋 Environment Variables Check"
echo "------------------------------"
ENV_VARS=("KALSHI_API_KEY" "XAI_API_KEY" "DOCKER_USERNAME" "DOCKER_TOKEN")
for var in "${ENV_VARS[@]}"; do
    if [ -n "${!var}" ]; then
        echo -e "✅ ${GREEN}$var${NC} is set"
    else
        echo -e "⚠️  ${YELLOW}$var${NC} environment variable not set (needed for CI/CD)"
        ((WARNINGS++))
    fi
done

echo ""
echo "🏗️ Build Test"
echo "-------------"
if [ -f "Dockerfile" ]; then
    echo "Testing Docker build (this may take a few minutes)..."
    if docker build -t kalshi-ai-trading-bot-test . > /dev/null 2>&1; then
        echo -e "✅ ${GREEN}Docker build successful${NC}"
        # Clean up test image
        docker rmi kalshi-ai-trading-bot-test > /dev/null 2>&1
    else
        echo -e "❌ ${RED}Docker build failed${NC}"
        ((ERRORS++))
    fi
fi

echo ""
echo "📋 Summary"
echo "=========="
if [ $ERRORS -eq 0 ]; then
    echo -e "🎉 ${GREEN}All critical checks passed!${NC}"
    if [ $WARNINGS -eq 0 ]; then
        echo -e "✨ ${GREEN}No warnings found. Ready for deployment!${NC}"
        exit 0
    else
        echo -e "⚠️  ${WARNINGS} ${YELLOW}warnings found. Review optional items above.${NC}"
        exit 0
    fi
else
    echo -e "❌ ${RED}${ERRORS} critical errors found.${NC} Please fix these issues before deployment."
    if [ $WARNINGS -gt 0 ]; then
        echo -e "⚠️  Also ${WARNINGS} ${YELLOW}warnings found.${NC}"
    fi
    exit 1
fi