FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY main.py .

# Create directories for data
RUN mkdir -p data charts

# Run bot
CMD ["python", "main.py"]
