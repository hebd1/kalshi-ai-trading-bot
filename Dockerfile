# Use slim Python base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies first
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files and install Python dependencies first
COPY requirements.txt /app/
COPY dashboard_requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r dashboard_requirements.txt

# Create necessary directory structure
RUN mkdir -p /app/logs /app/shared /app/data /app/keys

# Copy the application code
COPY src/ /app/src/
COPY beast_mode_bot.py /app/
COPY beast_mode_dashboard.py /app/
COPY performance_analysis.py /app/
COPY performance_system_manager.py /app/
COPY get_positions.py /app/
COPY launch_dashboard.py /app/
COPY trading_dashboard.py /app/
COPY start_services.sh /app/

# Make startup script executable
RUN chmod +x /app/start_services.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DB_PATH=/app/data/trading_system.db

# Health check - check if database directory exists and is writable
HEALTHCHECK --interval=5m --timeout=30s --start-period=30s --retries=3 \
    CMD python -c "import os; db_path='${DB_PATH:-/app/data/trading_system.db}'; os.makedirs(os.path.dirname(db_path), exist_ok=True); import sqlite3; db = sqlite3.connect(db_path); db.close(); print('Health check passed')" || exit 1

# Expose dashboard port
EXPOSE 8501

# Run both services via startup script
CMD ["/app/start_services.sh"]
