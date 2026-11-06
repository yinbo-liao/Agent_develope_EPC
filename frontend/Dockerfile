# syntax=docker/dockerfile:1.7
# =============================================================================
# FPSO EPC frontend — multi-stage build (node build -> nginx runtime)
#
#   build: docker build -t fpso-frontend ./frontend
#   run:   docker run -p 5173:80 fpso-frontend
#
# nginx listens on 80 inside the container and runs as the unprivileged
# `nginx` user (UID 101). It serves the SPA and reverse-proxies /api and /ws
# to backend:8000 on the compose/k8s network.
# =============================================================================

# ---- Stage 1: dependencies ---------------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---- Stage 2: build ----------------------------------------------------------
FROM deps AS build

WORKDIR /app
COPY . .

# Optional build-time API base URL. Empty (default) means same-origin requests
# through nginx (/api, /ws). See vite.config.ts for the dev proxy target.
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# ---- Stage 3: runtime --------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="fpso-epc-frontend" \
      org.opencontainers.image.description="FPSO EPC Project Control System dashboard" \
      org.opencontainers.image.version="4.0.0" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="Proprietary"

# Replace the stock server block with the SPA + reverse-proxy config.
RUN rm -f /etc/nginx/conf.d/default.conf \
 && chown -R nginx:nginx /var/cache/nginx /var/run

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
RUN chown -R nginx:nginx /usr/share/nginx/html /etc/nginx/conf.d

USER nginx

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/healthz

CMD ["nginx", "-g", "daemon off;"]
