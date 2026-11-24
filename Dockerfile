# ═══════════════════════════════════════════════════════════════════════════
# Stage 1: Build Frontend (React + Vite)
# ═══════════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS frontend-builder

WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ═══════════════════════════════════════════════════════════════════════════
# Stage 2: Backend + Headless Chromium + Static UI
# ═══════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEADLESS=true \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies required for headless Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    gnupg \
    ca-certificates \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libasound2 \
    libxshmfence1 \
    libxfixes3 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Patchright Chromium browser binary and OS dependencies
RUN python -m patchright install --with-deps chromium

# Copy application source code
COPY app ./app
COPY login.py .
COPY pyproject.toml .

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/web/dist ./web/dist

# Create persistent storage directories
RUN mkdir -p data/session data/screenshots data/captcha data/users

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
