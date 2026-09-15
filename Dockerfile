# ==============================================================================
# Stage 1: Build Modern React Frontend SPA
# ==============================================================================
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# ==============================================================================
# Stage 2: Production Python Runner (FastAPI + CLI Engine)
# ==============================================================================
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8080

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy configuration and application source code
COPY pyproject.toml README.md ./
COPY config/ /app/config/
COPY sql/ /app/sql/
COPY mindthespot/ /app/mindthespot/

# Install Python package and CLI entrypoint
RUN pip install --no-cache-dir .

# Copy compiled frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose Cloud Run service port
EXPOSE 8080

# Run FastAPI serving backend and compiled frontend
CMD ["sh", "-c", "uvicorn mindthespot.api.app:app --host 0.0.0.0 --port ${PORT}"]
