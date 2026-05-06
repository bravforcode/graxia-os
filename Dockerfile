# Graxia OS Unified Dockerfile
# Multi-stage build for production deployment
# Replaces: Dockerfile.graxia, Dockerfile.quant, Dockerfile.unified, backend/Dockerfile, frontend/Dockerfile

# ── Backend Build Stage ─────────────────────────────────────────────────────
FROM python:3.12-slim AS backend-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Frontend Build Stage ─────────────────────────────────────────────────────
FROM oven/bun:1.3.6-alpine AS frontend-builder

WORKDIR /app
ARG VITE_API_BASE_URL
ARG VITE_AGENT_STREAM_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_AGENT_STREAM_URL=$VITE_AGENT_STREAM_URL
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

COPY frontend/package.json frontend/bun.lockb ./
RUN bun install --frozen-lockfile
COPY frontend/ .
RUN bun run build

# ── Runtime Image ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    age \
    curl \
    libpq5 \
    postgresql-client \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Copy backend dependencies and code
COPY --from=backend-builder /install /usr/local
COPY backend/ .

# Copy frontend build
COPY --from=frontend-builder --chown=graxia:graxia /app/dist /usr/share/nginx/html

# Setup user and directories
RUN groupadd --gid 1001 graxia \
    && useradd --uid 1001 --gid 1001 --create-home --shell /usr/sbin/nologin graxia \
    && mkdir -p /app/logs /app/backups \
    && chown -R graxia:graxia /app

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

USER 1001:1001

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start both backend and nginx
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 & nginx -g 'daemon off;'"]
