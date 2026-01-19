# Kalshi AI Trading Bot - Deployment Guide 🚀

Complete guide for deploying the Kalshi AI Trading Bot using GitHub Actions CI/CD to DockerHub and Synology NAS.

## 📋 Prerequisites

### Required
- Docker installed on your development machine
- DockerHub account (free)
- GitHub repository with proper secrets configured
- Synology NAS with Docker package installed
- SSH access to Synology NAS
- Kalshi API credentials (demo or production)
- XAI (Grok) API key

### Optional
- OpenAI API key (for fallback models)

## 🚀 Automated Deployment (GitHub Actions CI/CD)

This project uses automated CI/CD with GitHub Actions that follows the same pattern as the trader-agent project.

### 1. Configure GitHub Repository Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions, and add these deployment secrets:

#### Required Deployment Secrets:
```
DOCKER_USERNAME          # Your DockerHub username  
DOCKER_TOKEN            # DockerHub access token (not password!)
ADRASTEA_SSH_KEY        # Private SSH key for Synology NAS
```

> **Note**: API keys (KALSHI_API_KEY, XAI_API_KEY, etc.) are managed via the `.env` file directly on your Synology NAS for better security and easier management. Only deployment-specific secrets are stored in GitHub.

#### Creating DockerHub Token:
1. Go to DockerHub → Account Settings → Security → Access Tokens
2. Click "New Access Token"
3. Name it "GitHub Actions" with Read/Write permissions
4. Copy the token and add it as `DOCKER_TOKEN` secret

#### SSH Key Setup:
1. Generate SSH key for GitHub Actions (if not already done)
2. Add public key to your Synology NAS authorized_keys
3. Add private key as `ADRASTEA_SSH_KEY` secret

### Testing Secrets Locally

To test your deployment configuration locally before pushing:

```bash
# Create a test script
cat > test_deployment.sh << 'EOF'
#!/bin/bash
source .env
echo "Testing Docker build..."
docker build -t test-kalshi-bot .
echo "Build successful!"
EOF

chmod +x test_deployment.sh
./test_deployment.sh
```

### 2. Automated Pipeline Workflow

The CI/CD pipeline automatically triggers on:
- Push to `master` branch
- Git tags starting with `v` (e.g., `v1.0.0`)

**Pipeline stages:**
1. **Verify**: Run tests and verify code quality
2. **Build**: Build multi-arch Docker image and push to DockerHub  
3. **Deploy**: Deploy to Synology NAS via SSH
4. **Notify**: Report deployment status

### 3. Deployment Process

When you push to master, the pipeline will:

1. **Build and Push Docker Image**:
   - Image: `elihebdon/kalshi-ai-trading-bot:latest`
   - Multi-architecture: `linux/amd64`, `linux/arm64`
   - Automatic versioning based on git commits

2. **Deploy to Synology NAS**:
   - Connect via SSH to `helloadrastea.synology.me:2222`
   - Stop and remove existing `kalshi-trading-bot` container
   - Pull latest image from DockerHub
   - Start new dual-service container with trading bot and dashboard
   - Expose port 8501 for dashboard access  
   - Mount volumes and load API keys from `.env` file
   - Verify deployment health and dashboard accessibility

### Container Health Checks

The Docker image includes built-in health checks:

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' kalshi-trading-bot

# View health check logs
docker inspect kalshi-trading-bot | jq '.[]?.State.Health'
```

Health check verifies:
- Python process is running
- Database is accessible
- Trading system can start
- Required environment variables are set
### 4. Synology NAS Directory Structure

Before first deployment, ensure these directories exist on your NAS:

```bash
ssh deimos@helloadrastea.synology.me -p 2222

# Create directory structure
sudo mkdir -p /volume3/docker/kalshi-trading-bot/{logs,shared,keys,data}

# Set permissions
sudo chown -R 1000:1000 /volume3/docker/kalshi-trading-bot
sudo chmod 755 /volume3/docker/kalshi-trading-bot
sudo chmod 777 /volume3/docker/kalshi-trading-bot/{logs,shared,data}
sudo chmod 755 /volume3/docker/kalshi-trading-bot/keys
```

### 5. Setup Environment Variables on Synology

The API keys and private keys need to be set up on the NAS:

#### Step 1: Create .env file on Synology
```bash
# SSH to your Synology NAS
ssh deimos@helloadrastea.synology.me -p 2222

# Create .env file in the kalshi-trading-bot directory
cat > /volume3/docker/kalshi-trading-bot/.env << 'EOF'
# Kalshi API Configuration (Demo/Test Environment)
KALSHI_API_KEY=your_demo_api_key_here
KALSHI_BASE_URL=https://demo-api.kalshi.co
KALSHI_PRIVATE_KEY=kalshi_private_key.pem

# Kalshi Production API Configuration (if using live trading)
KALSHI_API_KEY_PROD=your_production_api_key_here
KALSHI_BASE_URL_PROD=https://api.elections.kalshi.com
KALSHI_PRIVATE_KEY_PROD=kalshi_private_key.prod.pem

# xAI API Configuration
XAI_API_KEY=your_xai_grok_api_key_here
EOF

# Set secure permissions
chmod 600 /volume3/docker/kalshi-trading-bot/.env
```

#### Step 2: Copy Private Keys to Synology
```bash
# Copy private keys from local machine to NAS
scp -P 2222 kalshi_private_key.pem deimos@helloadrastea.synology.me:/volume3/docker/kalshi-trading-bot/keys/
scp -P 2222 kalshi_private_key.prod.pem deimos@helloadrastea.synology.me:/volume3/docker/kalshi-trading-bot/keys/

# Set proper permissions
ssh deimos@helloadrastea.synology.me -p 2222 "chmod 400 /volume3/docker/kalshi-trading-bot/keys/*.pem"
```

## 🏗️ Manual Deployment (Alternative)

### 1. Prepare Your Environment

Create a `.env` file in the project root (copy from `.env.docker.example`):

```bash
cp .env.docker.example .env
# Edit .env with your actual credentials
```

Example `.env` (for local development/testing):
```env
# DockerHub Configuration (for manual builds only)
DOCKER_USERNAME=yourdockerhubusername

# Kalshi API Configuration (Demo/Test Environment)
KALSHI_API_KEY=your_demo_key
KALSHI_BASE_URL=https://demo-api.kalshi.co
KALSHI_PRIVATE_KEY=kalshi_private_key.pem

# Kalshi Production API Configuration (if using live trading)
KALSHI_API_KEY_PROD=your_prod_key
KALSHI_BASE_URL_PROD=https://api.elections.kalshi.com
KALSHI_PRIVATE_KEY_PROD=kalshi_private_key.prod.pem

# xAI API Configuration
XAI_API_KEY=your_xai_key

# System Configuration
TZ=America/Denver
```

> **Note**: For production deployment, API keys should be configured in the `.env` file directly on your Synology NAS as described in the automated deployment section above.

### 2. Build and Push to DockerHub

Make the build script executable:
```bash
chmod +x docker-build.sh
```

Run the build script:
```bash
DOCKER_USERNAME=yourusername ./docker-build.sh
```

This will:
- Build the Docker image
- Tag it with your DockerHub username
- Optionally push it to DockerHub

### 3. Manual Docker Build (Alternative)

If you prefer to build manually:

## 🏗️ Manual Deployment (Alternative)

If you prefer manual deployment or need to test the deployment process:

### 1. Prepare Your Environment

Create a `.env` file in the project root (copy from `.env.docker.example`):

```bash
cp .env.docker.example .env
# Edit .env with your actual credentials
```

Example `.env` (for local development/testing):
```env
# DockerHub Configuration (for manual builds only)
DOCKER_USERNAME=yourdockerhubusername

# Kalshi API Configuration (Demo/Test Environment)
KALSHI_API_KEY=your_demo_key
KALSHI_BASE_URL=https://demo-api.kalshi.co
KALSHI_PRIVATE_KEY=kalshi_private_key.pem

# Kalshi Production API Configuration (if using live trading)
KALSHI_API_KEY_PROD=your_prod_key
KALSHI_BASE_URL_PROD=https://api.elections.kalshi.com
KALSHI_PRIVATE_KEY_PROD=kalshi_private_key.prod.pem

# xAI API Configuration
XAI_API_KEY=your_xai_key

# System Configuration
TZ=America/Denver
```

> **Note**: For production deployment, API keys should be configured in the `.env` file directly on your Synology NAS as described in the automated deployment section above.

### 2. Build and Push to DockerHub

Make the build script executable:
```bash
chmod +x docker-build.sh
```

Run the build script:
```bash
DOCKER_USERNAME=yourusername ./docker-build.sh
```

This will:
- Build the Docker image
- Tag it with your DockerHub username
- Optionally push it to DockerHub

### 3. Manual Docker Build (Alternative)

If you prefer to build manually:

```bash
# Build the image
docker build -t yourusername/kalshi-ai-trading-bot:latest .

# Tag specific version
docker tag yourusername/kalshi-ai-trading-bot:latest yourusername/kalshi-ai-trading-bot:v1.0.0

# Push to DockerHub
docker login
docker push yourusername/kalshi-ai-trading-bot:latest
docker push yourusername/kalshi-ai-trading-bot:v1.0.0
```

## 🖥️ Deploying to Synology NAS (Dual-Service Mode)

The deployment automatically starts both the trading bot and dashboard simultaneously. The dashboard will be accessible at `http://your-nas-ip:8501`.

### Option 1: Using Docker Compose (Recommended)

#### Step 1: Prepare Synology Directories

SSH into your Synology NAS:

```bash
ssh admin@your-nas-ip

# Create directory structure
mkdir -p /volume3/docker/kalshi-trading-bot/{logs,shared,keys,data}

# Navigate to the directory
cd /volume3/docker/kalshi-trading-bot
```

#### Step 2: Copy API Keys

Copy your private key files to the NAS:

```bash
# From your local machine
scp kalshi_private_key.pem admin@your-nas-ip:/volume3/docker/kalshi-trading-bot/keys/
scp kalshi_private_key.prod.pem admin@your-nas-ip:/volume3/docker/kalshi-trading-bot/keys/

# Set proper permissions
ssh admin@your-nas-ip "chmod 400 /volume3/docker/kalshi-trading-bot/keys/*.pem"
```

#### Step 3: Create Environment File

Create `.env` file on your NAS:

```bash
cat > /volume3/docker/kalshi-trading-bot/.env << 'EOF'
DOCKER_USERNAME=yourusername
KALSHI_API_KEY=your_demo_key
KALSHI_API_KEY_PROD=your_prod_key
XAI_API_KEY=your_xai_key
TZ=America/Denver
VERSION=latest
EOF
```

#### Step 4: Copy Docker Compose File

```bash
scp docker-compose.synology.yml admin@your-nas-ip:/volume3/docker/kalshi-trading-bot/docker-compose.yml
```

#### Step 5: Start the Container

```bash
ssh admin@your-nas-ip
cd /volume3/docker/kalshi-trading-bot

# Pull the image
docker-compose pull

# Start the container
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f kalshi-trading-bot
```

### Option 2: Using docker-run.sh Script

Make the script executable and run it:

```bash
chmod +x docker-run.sh
DOCKER_USERNAME=yourusername ./docker-run.sh
```

### Option 3: Using Synology Docker GUI

1. Open **Docker** package on your Synology
2. Go to **Registry** and search for your image: `yourusername/kalshi-ai-trading-bot`
3. Click **Download** and select `latest` tag
4. Go to **Image** tab and wait for download to complete
5. Go to **Container** tab and click **Create**
6. Configure the container:
   - **Container Name**: kalshi-trading-bot
   - **Enable auto-restart**: ✓
   - **Volume Settings**:
     - Add: `/volume3/docker/kalshi-trading-bot/logs` → `/app/logs`
     - Add: `/volume3/docker/kalshi-trading-bot/shared` → `/app/shared`
     - Add: `/volume3/docker/kalshi-trading-bot/keys` → `/app/keys` (Read-only)
     - Add: `/volume3/docker/kalshi-trading-bot/data` → `/app/data`
   - **Environment Variables**:
     - `KALSHI_API_KEY`: your_demo_key
     - `KALSHI_API_KEY_PROD`: your_prod_key
     - `XAI_API_KEY`: your_xai_key
     - `KALSHI_PRIVATE_KEY`: /app/keys/kalshi_private_key.pem
     - `KALSHI_PRIVATE_KEY_PROD`: /app/keys/kalshi_private_key.prod.pem
     - `PYTHONUNBUFFERED`: 1
     - `TZ`: America/Denver
     - `DB_PATH`: /app/data/trading_system.db
7. Click **Apply** and **Start**

## 🔍 Monitoring & Management

### Check Container Status

```bash
docker ps -f name=kalshi-trading-bot
```

### View Logs

```bash
# Real-time logs
docker logs -f kalshi-trading-bot

# Last 100 lines
docker logs --tail 100 kalshi-trading-bot

# Using docker-compose
docker-compose logs -f
```

### Check Container Stats

```bash
docker stats kalshi-trading-bot
```

### Restart Container

```bash
# Using docker
docker restart kalshi-trading-bot

# Using docker-compose
docker-compose restart
```

### Stop Container

```bash
# Using docker
docker stop kalshi-trading-bot

# Using docker-compose
docker-compose down
```

### Update to Latest Version

```bash
# Pull latest image
docker pull yourusername/kalshi-ai-trading-bot:latest

# Stop old container
docker-compose down

# Start new container
docker-compose up -d

# Or using docker commands
docker stop kalshi-trading-bot
docker rm kalshi-trading-bot
./docker-run.sh
```

## 🐛 Troubleshooting

### Container Won't Start

Check logs for errors:
```bash
docker logs kalshi-trading-bot
```

Common issues:
- Missing API keys in environment variables
- Private key files not found or incorrect permissions
- Insufficient memory/CPU resources

### Can't Connect to Kalshi API

1. Verify API keys are correct
2. Check network connectivity from container:
   ```bash
   docker exec kalshi-trading-bot ping api.kalshi.co
   ```
3. Verify private key file is accessible:
   ```bash
   docker exec kalshi-trading-bot ls -la /app/keys/
   ```

### High Memory Usage

Adjust resource limits in `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 1G
```

### Database Locked

If you get database locked errors:
1. Stop the container
2. Check if database file is corrupted
3. Restore from backup or start fresh

## 📊 Dashboard Access

The trading bot automatically includes a web dashboard that runs simultaneously with the trading system. No additional configuration required!

**Dashboard Features:**
- Real-time performance monitoring
- Live position tracking
- Strategy analytics
- Risk management metrics

**Access URL:** `http://your-nas-ip:8501`

The dashboard starts automatically when you deploy the container and is accessible immediately after deployment.

## 🔒 Security Best Practices

1. **Never commit API keys** to git
2. **Use read-only mounts** for sensitive files
3. **Rotate API keys** regularly
4. **Monitor logs** for suspicious activity
5. **Use firewall rules** to restrict access
6. **Keep Docker images updated**
7. **Use Docker secrets** for sensitive data in production
8. **Enable container security scanning**
9. **Run containers as non-root user** (already configured)
10. **Use multi-stage builds** to minimize attack surface

### Docker Security Commands

```bash
# Scan image for vulnerabilities
docker scout cves elihebdon/kalshi-ai-trading-bot:latest

# Check running processes in container
docker exec kalshi-trading-bot ps aux

# Verify user context
docker exec kalshi-trading-bot whoami

# Check file permissions
docker exec kalshi-trading-bot ls -la /app/keys/
```

## 📈 Performance Optimization

### For Synology NAS:

1. **Enable SSD Cache** (if available)
2. **Allocate sufficient RAM** (minimum 2GB recommended)
3. **Use docker-compose.synology.yml** for optimized settings
4. **Monitor CPU/Memory usage** regularly
5. **Set up log rotation** to prevent disk filling

### Resource Recommendations:

- **Minimum**: 1 CPU core, 512MB RAM
- **Recommended**: 2 CPU cores, 1-2GB RAM
- **Optimal**: 4 CPU cores, 2-4GB RAM

## 🔄 Backup & Recovery

### Backup Important Files

```bash
# Create backup directory
mkdir -p /volume3/backup/kalshi-trading-bot

# Backup database
cp /volume3/docker/kalshi-trading-bot/trading_system.db \
   /volume3/backup/kalshi-trading-bot/trading_system_$(date +%Y%m%d).db

# Backup logs
tar -czf /volume3/backup/kalshi-trading-bot/logs_$(date +%Y%m%d).tar.gz \
   /volume3/docker/kalshi-trading-bot/logs/
```

### Automated Backups

Create a cron job on Synology:
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /volume3/docker/kalshi-trading-bot/backup.sh
```

## 📞 Support

For issues or questions:
1. Check the logs first
2. Review the README.md
3. Check COMMANDS_REFERENCE.md for troubleshooting
4. Open an issue on GitHub

## 🚦 CI/CD Pipeline Status

Monitor your deployments:

```bash
# Check latest deployment status
curl -s "https://api.github.com/repos/yourusername/kalshi-ai-trading-bot/actions/runs" | jq '.workflow_runs[0] | {status, conclusion, created_at}'

# Get deployment logs from GitHub Actions
gh run list --limit 5
gh run view --log
```

### Deployment Verification

After deployment, verify everything is working:

```bash
# Test script to verify deployment
cat > verify_deployment.sh << 'EOF'
#!/bin/bash
echo "🔍 Verifying Kalshi Trading Bot Deployment..."

# Check container is running
if docker ps | grep -q kalshi-trading-bot; then
    echo "✅ Container is running"
else
    echo "❌ Container is not running"
    exit 1
fi

# Check health status
HEALTH=$(docker inspect --format='{{.State.Health.Status}}' kalshi-trading-bot 2>/dev/null)
if [ "$HEALTH" = "healthy" ]; then
    echo "✅ Container is healthy"
else
    echo "⚠️ Container health: $HEALTH"
fi

# Check logs for errors
ERRORS=$(docker logs kalshi-trading-bot 2>&1 | grep -i error | wc -l)
if [ "$ERRORS" -eq 0 ]; then
    echo "✅ No errors in logs"
else
    echo "⚠️ Found $ERRORS error(s) in logs"
fi

# Check API connectivity
docker exec kalshi-trading-bot python -c "from src.clients.kalshi_client import KalshiClient; import asyncio; asyncio.run(KalshiClient().get_balance())"
if [ $? -eq 0 ]; then
    echo "✅ API connectivity working"
else
    echo "❌ API connectivity failed"
fi

echo "🎉 Deployment verification complete!"
EOF

chmod +x verify_deployment.sh
```

## 🎉 Next Steps

After successful deployment:
1. Run the verification script: `./verify_deployment.sh`
2. Monitor the bot for 24-48 hours in demo mode
3. Review logs and performance metrics
4. Set up automated monitoring and alerts
5. Configure backup strategies
6. When ready, switch to production mode with proper risk management

### Production Readiness Checklist

- [ ] All tests passing in CI/CD pipeline
- [ ] Demo trading running successfully for 48+ hours
- [ ] Logs showing no errors or warnings
- [ ] API rate limits respected
- [ ] Database backups configured
- [ ] Monitoring and alerting set up
- [ ] Risk management parameters reviewed
- [ ] Production API keys configured in .env file on Synology NAS
- [ ] Disaster recovery plan in place

Happy trading! 🚀
