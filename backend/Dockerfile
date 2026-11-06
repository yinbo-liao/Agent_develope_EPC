# syntax=docker/dockerfile:1.7
# =============================================================================
# FPSO EPC backend — multi-stage build
#
#   build: docker build -t fpso-backend ./backend
#   run:   docker run -p 8000:8000 \
#            -e FPSO_DATABASE_URL=postgresql+asyncpg://... \
#            -e FPSO_SECRET_KEY=... fpso-backend
#
# The final image runs as the unprivileged `fpso` user (UID/GID 1001), contains
# only the Python virtualenv and application code, and exposes /health for
# orchestrator health checks. PYTHONDONTWRITEBYTECODE keeps the filesystem
# read-only friendly.
# =============================================================================

# ---- Stage 1: dependency build ----------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# ---- Stage 2: runtime --------------------------------------------------------
FROM python:3.12-slim AS runtime

ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="fpso-epc-backend" \
      org.opencontainers.image.description="FPSO EPC Project Control System API" \
      org.opencontainers.image.version="4.0.0" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH"

# Unprivileged runtime user — no shell, no home-write requirements.
RUN groupadd --system --gid 1001 fpso \
 && useradd --system --uid 1001 --gid fpso --home-dir /app --shell /usr/sbin/nologin fpso

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=fpso:fpso . .

USER fpso

EXPOSE 8000

# Uses /health/live (process only) so a transient DB/Redis outage does not mark
# the container unhealthy. Or orchestrators can probe /health/ready instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

# --proxy-headers + forwarded-allow-ips keep client IPs correct behind nginx.
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
