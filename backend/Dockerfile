# Keep pip cache small
# Tells pip not to cache packages → smaller image size.
# ENV PIP_NO_CACHE_DIR=1
# Prevents .pyc files from being generated. Not needed inside Docker.
# ENV PYTHONDONTWRITEBYTECODE=1
# Ensures logs are printed immediately to the console, helpful for debugging.
# ENV PYTHONUNBUFFERED=1

# Base image with Python
FROM python:3.13-slim

# Make builds predictable and logs immediate
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create app dir inside the container to /app. All following commands (COPY, RUN, CMD) run from this folder. Makes app self-contained inside /app.
WORKDIR /app

# Install OS-level tools BEFORE Python deps (many libs need a C/C++ compiler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Select which requirements file to install (default to full)
ARG PIP_REQUIREMENTS=requirements.txt

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r ${PIP_REQUIREMENTS}

# Copy application code
COPY app /app/app

EXPOSE 8060

# Run the API
CMD ["/bin/sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${SERVER_PORT:-8060}"]
