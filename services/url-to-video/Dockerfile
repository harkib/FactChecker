FROM python:3.13-slim

WORKDIR /app

# Install system dependencies (build tools for asyncpg compilation)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    python3-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Lambda Runtime Interface Client
RUN pip install --no-cache-dir awslambdaric

# Copy requirements and install Python dependencies
COPY services/url-to-video/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY services/shared/ /app/shared/

# Copy application code
COPY services/url-to-video/app/ ./app/

# Set PYTHONPATH so shared module can be found
ENV PYTHONPATH=/app

# Set Lambda handler
ENTRYPOINT [ "python", "-m", "awslambdaric" ]
CMD [ "app.lambda_handler.handler" ]

