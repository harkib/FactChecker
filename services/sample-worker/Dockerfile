FROM python:3.13-slim

WORKDIR /app

# Install system dependencies (build tools for asyncpg compilation)
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/sample-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY services/shared/ /app/shared/

# Copy application code
COPY services/sample-worker/app/ ./app/

# Set PYTHONPATH so shared module can be found
ENV PYTHONPATH=/app

# Run the worker
CMD ["python", "app/main.py"]
