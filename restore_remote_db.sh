#!/bin/bash

# Restore Remote Database Script
# This script restores a backed up database to the remote adrastea host

set -e  # Exit on error

# Configuration
REMOTE_HOST="adrastea"
CONTAINER_NAME="kalshi-trading-bot"
REMOTE_DB_PATH="/app/data/trading_system.db"
BACKUP_DIR="./backups"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "  Remote Database Restore Tool"
echo "=================================================="
echo ""

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}❌ Backup directory not found: $BACKUP_DIR${NC}"
    exit 1
fi

# List available backups
echo "Available backups:"
echo ""
BACKUPS=($(ls -1t "$BACKUP_DIR"/*.db 2>/dev/null))

if [ ${#BACKUPS[@]} -eq 0 ]; then
    echo -e "${RED}❌ No backup files found in $BACKUP_DIR${NC}"
    exit 1
fi

# Display backups with numbers
for i in "${!BACKUPS[@]}"; do
    BACKUP_FILE="${BACKUPS[$i]}"
    SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
    DATE=$(stat -c %y "$BACKUP_FILE" 2>/dev/null || stat -f "%Sm" "$BACKUP_FILE" 2>/dev/null)
    echo "  [$((i+1))] $(basename "$BACKUP_FILE") - Size: $SIZE"
done

echo ""
read -p "Select backup number to restore (or 'q' to quit): " SELECTION

if [[ "$SELECTION" == "q" ]] || [[ "$SELECTION" == "Q" ]]; then
    echo "Restore cancelled"
    exit 0
fi

# Validate selection
if ! [[ "$SELECTION" =~ ^[0-9]+$ ]] || [ "$SELECTION" -lt 1 ] || [ "$SELECTION" -gt ${#BACKUPS[@]} ]; then
    echo -e "${RED}❌ Invalid selection${NC}"
    exit 1
fi

SELECTED_BACKUP="${BACKUPS[$((SELECTION-1))]}"
echo ""
echo -e "${GREEN}Selected backup: $(basename "$SELECTED_BACKUP")${NC}"
echo ""

# Check container status
echo -e "${YELLOW}[1/4] Checking container status...${NC}"
CONTAINER_STATUS=$(ssh $REMOTE_HOST "docker ps --filter name=$CONTAINER_NAME --format '{{.Status}}'" 2>/dev/null || echo "NOT_FOUND")

if [[ "$CONTAINER_STATUS" == "NOT_FOUND" ]] || [[ -z "$CONTAINER_STATUS" ]]; then
    echo -e "${RED}❌ Container '$CONTAINER_NAME' is not running on $REMOTE_HOST${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Container is running${NC}"
echo ""

# Check if database already exists
echo -e "${YELLOW}[2/4] Checking existing database...${NC}"
DB_EXISTS=$(ssh $REMOTE_HOST "docker exec $CONTAINER_NAME test -f $REMOTE_DB_PATH && echo 'yes' || echo 'no'" 2>/dev/null)

if [[ "$DB_EXISTS" == "yes" ]]; then
    echo -e "${YELLOW}⚠️  Database already exists on remote container${NC}"
    read -p "Overwrite existing database? (type 'YES' to confirm): " CONFIRM_OVERWRITE
    
    if [[ "$CONFIRM_OVERWRITE" != "YES" ]]; then
        echo "Restore cancelled"
        exit 0
    fi
fi

# Stop container
echo -e "${YELLOW}[3/4] Stopping container...${NC}"
ssh $REMOTE_HOST "docker stop $CONTAINER_NAME"
echo -e "${GREEN}✅ Container stopped${NC}"
echo ""

# Upload and restore
echo -e "${YELLOW}[4/4] Restoring database...${NC}"

# Upload to remote host
echo "Uploading backup to remote host..."
scp "$SELECTED_BACKUP" "$REMOTE_HOST:/tmp/restore_db.db"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to upload backup${NC}"
    ssh $REMOTE_HOST "docker start $CONTAINER_NAME"
    exit 1
fi

# Copy to container
echo "Copying database to container..."
ssh $REMOTE_HOST "docker cp /tmp/restore_db.db $CONTAINER_NAME:$REMOTE_DB_PATH"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to copy database to container${NC}"
    ssh $REMOTE_HOST "rm -f /tmp/restore_db.db"
    ssh $REMOTE_HOST "docker start $CONTAINER_NAME"
    exit 1
fi

# Clean up temp file
ssh $REMOTE_HOST "rm -f /tmp/restore_db.db"

echo -e "${GREEN}✅ Database restored${NC}"
echo ""

# Restart container
echo "Restarting container..."
ssh $REMOTE_HOST "docker start $CONTAINER_NAME"
echo -e "${GREEN}✅ Container restarted${NC}"
echo ""

# Summary
echo "=================================================="
echo -e "${GREEN}✅ DATABASE RESTORED SUCCESSFULLY${NC}"
echo "=================================================="
echo ""
echo "Restored from: $(basename "$SELECTED_BACKUP")"
echo "Container: $CONTAINER_NAME on $REMOTE_HOST"
echo ""
