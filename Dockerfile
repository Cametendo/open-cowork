# ---------------------------------------------------------------- frontend
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim-bookworm

# Tools the Cowork agent commonly needs inside workspaces
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git curl ca-certificates bash procps jq unzip ripgrep openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 # repos are bind-mounted from the host and may be owned by another uid
 && git config --system --add safe.directory '*' \
 && git config --system init.defaultBranch main

# Node.js + npm for JavaScript projects (copied from the build stage)
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && node --version && npm --version

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/open_cowork ./open_cowork
COPY --from=frontend /app/frontend/dist /app/frontend/dist

ENV PYTHONUNBUFFERED=1 \
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
