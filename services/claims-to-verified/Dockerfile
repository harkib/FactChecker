FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/claims-to-verified/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY services/shared/ /app/shared/

# Copy application code
COPY services/claims-to-verified/app/ ./app/

# Set PYTHONPATH so shared module can be found
ENV PYTHONPATH=/app

# Run the worker
CMD ["python", "app/main.py"]

