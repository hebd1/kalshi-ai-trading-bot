#!/bin/bash

# Startup script for running both trading bot and dashboard
set -e

echo "🚀 Starting Kalshi AI Trading Bot with Dashboard..."

# Function to handle shutdown
shutdown_handler() {
    echo "🛑 Shutdown signal received..."
    
    # Kill dashboard process if running
    if [ ! -z "$DASHBOARD_PID" ]; then
        echo "⏹️ Stopping dashboard (PID: $DASHBOARD_PID)..."
        kill $DASHBOARD_PID 2>/dev/null || true
        wait $DASHBOARD_PID 2>/dev/null || true
    fi
    
    # Kill trading bot process if running
    if [ ! -z "$TRADING_BOT_PID" ]; then
        echo "⏹️ Stopping trading bot (PID: $TRADING_BOT_PID)..."
        kill $TRADING_BOT_PID 2>/dev/null || true
        wait $TRADING_BOT_PID 2>/dev/null || true
    fi
    
    echo "✅ All processes stopped gracefully"
    exit 0
}

# Set up signal handlers
trap shutdown_handler SIGTERM SIGINT SIGQUIT

# Initialize database if it doesn't exist
echo "🔧 Checking database..."
DB_PATH="${DB_PATH:-/app/data/trading_system.db}"

# Create data directory if it doesn't exist
mkdir -p "$(dirname "$DB_PATH")"

if [ ! -f "$DB_PATH" ]; then
    echo "📊 Database not found, initializing new database at $DB_PATH..."
    python -c "import asyncio; from src.utils.database import DatabaseManager; asyncio.run(DatabaseManager('$DB_PATH').initialize())"
    echo "✅ Database initialized successfully"
else
    echo "✅ Database found at $DB_PATH"
    # Get database size
    DB_SIZE=$(stat -f%z "$DB_PATH" 2>/dev/null || stat -c%s "$DB_PATH" 2>/dev/null || echo "unknown")
    echo "   Database size: $DB_SIZE bytes"
fi

# Start the dashboard in the background
echo "📊 Starting Streamlit dashboard on port 8501..."
python launch_dashboard.py &
DASHBOARD_PID=$!
echo "✅ Dashboard started with PID: $DASHBOARD_PID"

# Give dashboard time to start
sleep 10

# Verify dashboard is running
if ! kill -0 $DASHBOARD_PID 2>/dev/null; then
    echo "❌ Dashboard failed to start, checking logs..."
    cat /app/logs/latest.log 2>/dev/null || echo "No logs available"
    exit 1
fi

echo "✅ Dashboard is running and accessible on port 8501"

# Start the trading bot
echo "🤖 Starting trading bot..."
python beast_mode_bot.py &
TRADING_BOT_PID=$!
echo "✅ Trading bot started with PID: $TRADING_BOT_PID"

# Wait for both processes and monitor them
while true; do
    # Check if dashboard is still running
    if ! kill -0 $DASHBOARD_PID 2>/dev/null; then
        echo "❌ Dashboard process died unexpectedly!"
        shutdown_handler
        exit 1
    fi
    
    # Check if trading bot is still running
    if ! kill -0 $TRADING_BOT_PID 2>/dev/null; then
        echo "❌ Trading bot process died unexpectedly!"
        shutdown_handler
        exit 1
    fi
    
    # Wait before checking again
    sleep 30
done