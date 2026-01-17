FROM python:3.13-slim

WORKDIR /app

# Install system dependencies including ffmpeg, git, and build tools for asyncpg compilation
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Lambda Runtime Interface Client
RUN pip install --no-cache-dir awslambdaric

# Install CPU-only PyTorch (required by whisper, avoid GPU version being installed as dependency)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy requirements and install Python dependencies
COPY services/video-to-transcript/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY services/shared/ /app/shared/

# Copy application code
COPY services/video-to-transcript/app/ ./app/

# Set PYTHONPATH so shared module can be found
ENV PYTHONPATH=/app

# Set Lambda handler
ENTRYPOINT [ "python", "-m", "awslambdaric" ]
CMD [ "app.lambda_handler.handler" ]

