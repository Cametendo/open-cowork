# ---------------------------------------------------------------- frontend
# The UI build is plain static files, so it runs on the build machine's
# architecture even when building ARM images (much faster than emulation).
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Node.js for the target architecture, copied into the runtime image below
FROM node:22-bookworm-slim AS node-runtime

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim-bookworm

# Set by the release workflow (e.g. 0.2.0); shown in Settings › About
ARG APP_VERSION=""

# Tools the Cowork agent commonly needs inside workspaces
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git curl ca-certificates bash procps jq unzip ripgrep openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 # repos are bind-mounted from the host and may be owned by another uid
 && git config --system --add safe.directory '*' \
 && git config --system init.defaultBranch main

# Node.js + npm for JavaScript projects
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && node --version && npm --version

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/open_cowork ./open_cowork
COPY --from=frontend /app/frontend/dist /app/frontend/dist

ENV PYTHONUNBUFFERED=1 \
    OPEN_COWORK_VERSION=${APP_VERSION} \
    HOST=0.0.0.0 \
    PORT=8080 \
    DATA_DIR=/app/backend/data \
    REPO_DIR=/repo \
    WORKSPACE_DIR=/workspaces \
    FRONTEND_DIR=/app/frontend/dist \
    OLLAMA_BASE_URL=http://host.docker.internal:11434

RUN mkdir -p /app/backend/data /repo /workspaces
VOLUME ["/app/backend/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT}/api/health" || exit 1

CMD ["python", "-m", "open_cowork"]
