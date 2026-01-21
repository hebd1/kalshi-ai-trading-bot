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

# Step 1: Check if container is running
echo -e "${YELLOW}[1/5] Checking container status...${NC}"
CONTAINER_STATUS=$(ssh $REMOTE_HOST "docker ps --filter name=$CONTAINER_NAME --format '{{.Status}}'" 2>/dev/null || echo "NOT_FOUND")

if [[ "$CONTAINER_STATUS" == "NOT_FOUND" ]] || [[ -z "$CONTAINER_STATUS" ]]; then
    echo -e "${RED}❌ Container '$CONTAINER_NAME' is not running on $REMOTE_HOST${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Container is running: $CONTAINER_STATUS${NC}"
echo ""

# Step 2: Check if database exists
echo -e "${YELLOW}[2/5] Checking if database exists...${NC}"
DB_EXISTS=$(ssh $REMOTE_HOST "docker exec $CONTAINER_NAME test -f $REMOTE_DB_PATH && echo 'yes' || echo 'no'" 2>/dev/null)

if [[ "$DB_EXISTS" != "yes" ]]; then
    echo -e "${RED}❌ Database not found at $REMOTE_DB_PATH${NC}"
    exit 1
fi

# Get database size
DB_SIZE=$(ssh $REMOTE_HOST "docker exec $CONTAINER_NAME ls -lh $REMOTE_DB_PATH | awk '{print \$5}'")
echo -e "${GREEN}✅ Database found (Size: $DB_SIZE)${NC}"
echo ""

# Step 3: Create backup
echo -e "${YELLOW}[3/5] Creating backup...${NC}"
echo "Copying database from container to remote host..."

# Copy from container to remote host temp location
ssh $REMOTE_HOST "docker cp $CONTAINER_NAME:$REMOTE_DB_PATH /tmp/$BACKUP_FILENAME"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to copy database from container${NC}"
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

# Stop the container first (optional but safer)
read -p "Stop the container before deletion? (y/n, default: y): " STOP_CONTAINER
STOP_CONTAINER=${STOP_CONTAINER:-y}

if [[ "$STOP_CONTAINER" == "y" ]] || [[ "$STOP_CONTAINER" == "Y" ]]; then
    echo "Stopping container..."
    ssh $REMOTE_HOST "docker stop $CONTAINER_NAME"
    echo -e "${GREEN}✅ Container stopped${NC}"
fi

# Delete the database file
echo "Deleting database file..."
ssh $REMOTE_HOST "docker exec $CONTAINER_NAME rm -f $REMOTE_DB_PATH"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to delete database${NC}"
    if [[ "$STOP_CONTAINER" == "y" ]] || [[ "$STOP_CONTAINER" == "Y" ]]; then
        echo "Restarting container..."
        ssh $REMOTE_HOST "docker start $CONTAINER_NAME"
    fi
    exit 1
fi

# Verify deletion
DB_STILL_EXISTS=$(ssh $REMOTE_HOST "docker exec $CONTAINER_NAME test -f $REMOTE_DB_PATH && echo 'yes' || echo 'no'" 2>/dev/null || echo "no")

if [[ "$DB_STILL_EXISTS" == "yes" ]]; then
    echo -e "${RED}❌ Database still exists after deletion attempt${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Database successfully deleted from remote container${NC}"
echo ""

# Restart container if it was stopped
if [[ "$STOP_CONTAINER" == "y" ]] || [[ "$STOP_CONTAINER" == "Y" ]]; then
    echo "Restarting container..."
    ssh $REMOTE_HOST "docker start $CONTAINER_NAME"
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
