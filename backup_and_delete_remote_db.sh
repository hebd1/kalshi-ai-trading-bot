#!/bin/bash

# Backup and Delete Remote Database Script
# This script backs up the trading_system.db from the remote adrastea host
# and then completely deletes it from the Docker container

set -e  # Exit on error

# Configuration
REMOTE_HOST="adrastea"
CONTAINER_NAME="kalshi-trading-bot"
REMOTE_DB_PATH="/app/data/trading_system.db"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILENAME="trading_system_backup_${TIMESTAMP}.db"

# Synology Docker path (update if different on your system)
DOCKER_CMD="/usr/local/bin/docker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "  Remote Database Backup & Deletion Tool"
echo "=================================================="
echo ""

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Step 1: Check container status
echo -e "${YELLOW}[1/5] Checking container status...${NC}"
CONTAINER_STATUS=$(ssh $REMOTE_HOST "$DOCKER_CMD ps --filter name=$CONTAINER_NAME --format '{{.Status}}'" 2>/dev/null || echo "")

# Check if container exists (running or stopped)
CONTAINER_EXISTS=$(ssh $REMOTE_HOST "$DOCKER_CMD ps -a --filter name=$CONTAINER_NAME --format '{{.Names}}'" 2>/dev/null)

if [[ -z "$CONTAINER_EXISTS" ]]; then
    echo -e "${RED}❌ Container '$CONTAINER_NAME' not found on $REMOTE_HOST${NC}"
    exit 1
fi

if [[ -n "$CONTAINER_STATUS" ]]; then
    echo -e "${GREEN}✅ Container is running: $CONTAINER_STATUS${NC}"
    CONTAINER_RUNNING=true
else
    echo -e "${YELLOW}⚠️  Container exists but is stopped${NC}"
    CONTAINER_RUNNING=false
fi
echo ""

# Step 2: Check if database exists (using host filesystem path)
echo -e "${YELLOW}[2/5] Checking if database exists...${NC}"

# Find the database on the host filesystem
HOST_DB_PATH="/volume3/docker/kalshi-trading-bot/data"
DB_EXISTS=$(ssh $REMOTE_HOST "test -f $HOST_DB_PATH/trading_system.db && echo 'yes' || echo 'no'" 2>/dev/null)

if [[ "$DB_EXISTS" != "yes" ]]; then
    echo -e "${RED}❌ Database not found at $HOST_DB_PATH/trading_system.db${NC}"
    exit 1
fi

# Get database size from host filesystem
DB_SIZE=$(ssh $REMOTE_HOST "ls -lh $HOST_DB_PATH/trading_system.db | awk '{print \$5}'")
echo -e "${GREEN}✅ Database found (Size: $DB_SIZE)${NC}"
echo ""

# Step 3: Create backup
echo -e "${YELLOW}[3/5] Creating backup...${NC}"
echo "Copying database from host to temp location..."

# Copy from host filesystem to remote temp location
ssh $REMOTE_HOST "cp $HOST_DB_PATH/trading_system.db /tmp/$BACKUP_FILENAME"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to copy database from host${NC}"
    exit 1
fi

echo "Downloading backup to local machine..."
scp $REMOTE_HOST:/tmp/$BACKUP_FILENAME "$BACKUP_DIR/$BACKUP_FILENAME"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to download backup${NC}"
    ssh $REMOTE_HOST "rm -f /tmp/$BACKUP_FILENAME"  # Cleanup
    exit 1
fi

# Clean up temp file on remote
ssh $REMOTE_HOST "rm -f /tmp/$BACKUP_FILENAME"

echo -e "${GREEN}✅ Backup saved to: $BACKUP_DIR/$BACKUP_FILENAME${NC}"
echo ""

# Step 4: Verify backup
echo -e "${YELLOW}[4/5] Verifying backup integrity...${NC}"

if [ ! -f "$BACKUP_DIR/$BACKUP_FILENAME" ]; then
    echo -e "${RED}❌ Backup file not found locally${NC}"
    exit 1
fi

LOCAL_SIZE=$(ls -lh "$BACKUP_DIR/$BACKUP_FILENAME" | awk '{print $5}')
echo -e "${GREEN}✅ Backup verified (Size: $LOCAL_SIZE)${NC}"
echo ""

# Step 5: Confirmation prompt
echo -e "${RED}⚠️  WARNING: You are about to DELETE the database from the remote container!${NC}"
echo -e "${RED}⚠️  This action CANNOT be undone!${NC}"
echo ""
echo "Backup location: $BACKUP_DIR/$BACKUP_FILENAME"
echo "Remote database: $REMOTE_HOST:$CONTAINER_NAME:$REMOTE_DB_PATH"
echo ""
read -p "Are you sure you want to delete the remote database? (type 'YES' to confirm): " CONFIRMATION

if [[ "$CONFIRMATION" != "YES" ]]; then
    echo -e "${YELLOW}❌ Deletion cancelled by user${NC}"
    echo -e "${GREEN}✅ Backup is still available at: $BACKUP_DIR/$BACKUP_FILENAME${NC}"
    exit 0
fi

# Step 5: Delete database from remote container
echo ""
echo -e "${YELLOW}[5/5] Deleting database from remote container...${NC}"

# Find the volume mount path on the host
echo "Finding database location on host..."
HOST_DB_PATH=$(ssh $REMOTE_HOST "$DOCKER_CMD inspect $CONTAINER_NAME --format '{{range .Mounts}}{{if eq .Destination \"/app/data\"}}{{.Source}}{{end}}{{end}}'")

if [[ -z "$HOST_DB_PATH" ]]; then
    echo -e "${YELLOW}⚠️  Could not auto-detect volume mount path${NC}"
    echo "Using known path for this system: /volume3/docker/kalshi-trading-bot/data"
    HOST_DB_PATH="/volume3/docker/kalshi-trading-bot/data"
fi

echo "Database location on host: $HOST_DB_PATH"
echo "Full database path: $HOST_DB_PATH/trading_system.db"

# Verify the database file exists before attempting deletion
if ssh $REMOTE_HOST "test -f $HOST_DB_PATH/trading_system.db"; then
    echo "✓ Database file confirmed at: $HOST_DB_PATH/trading_system.db"
    echo "Deleting database file from host filesystem..."
    echo "✓ Database file confirmed at: $HOST_DB_PATH/trading_system.db"
    echo "Deleting database file from host filesystem..."
    ssh $REMOTE_HOST "rm -f $HOST_DB_PATH/trading_system.db"
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Failed to delete database from host${NC}"
        exit 1
    fi
    
    # Verify deletion
    if ssh $REMOTE_HOST "test -f $HOST_DB_PATH/trading_system.db"; then
        echo -e "${RED}❌ Database still exists after deletion attempt${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Database successfully deleted from host filesystem${NC}"
else
    echo -e "${RED}❌ Database file not found at: $HOST_DB_PATH/trading_system.db${NC}"
    exit 1
fi

echo ""

# Restart the container to ensure clean state
read -p "Restart the container now? (y/n, default: y): " RESTART_CONTAINER
RESTART_CONTAINER=${RESTART_CONTAINER:-y}

if [[ "$RESTART_CONTAINER" == "y" ]] || [[ "$RESTART_CONTAINER" == "Y" ]]; then
    echo "Restarting container..."
    ssh $REMOTE_HOST "$DOCKER_CMD restart $CONTAINER_NAME"
    echo -e "${GREEN}✅ Container restarted${NC}"
fi

# Summary
echo ""
echo "=================================================="
echo -e "${GREEN}✅ OPERATION COMPLETED SUCCESSFULLY${NC}"
echo "=================================================="
echo ""
echo "Summary:"
echo "  • Backup created: $BACKUP_DIR/$BACKUP_FILENAME"
echo "  • Backup size: $LOCAL_SIZE"
echo "  • Remote database: DELETED"
echo "  • Container status: RUNNING (with fresh database)"
echo ""
echo "Notes:"
echo "  - The bot will create a new empty database on next run"
echo "  - To restore the backup, use: ./restore_remote_db.sh"
echo "  - Keep the backup file safe!"
echo ""
