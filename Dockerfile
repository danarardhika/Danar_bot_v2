# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies untuk matplotlib
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements dan install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua file
COPY main.py .

# Create directories
RUN mkdir -p data charts logs

# Health check untuk Railway
HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Run bot
CMD ["python", "-u", "main.py"]
