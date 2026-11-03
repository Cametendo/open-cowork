#!/usr/bin/env bash
# Run Open Cowork locally without Docker.
#
#   ./start.sh            install what's missing, build the UI if needed, start on :3001
#   ./start.sh --dev      start the API with auto-reload + the Vite dev server on :5173
#   ./start.sh --rebuild  force a fresh frontend build
#
# Requirements: Python 3.11+, Node.js 20+ (only to build the UI), git.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
# Outside Docker, Ollama usually runs on localhost
if [[ "${OLLAMA_BASE_URL:-}" == *host.docker.internal* ]]; then
  export OLLAMA_BASE_URL="http://localhost:11434"
fi
export REPO_DIR="${REPO_DIR:-$ROOT/repo}"
export WORKSPACE_DIR="${WORKSPACE_DIR:-$ROOT/workspaces}"
PORT="${PORT:-${OPEN_COWORK_PORT:-3001}}"

MODE="start"
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --dev) MODE="dev" ;;
    --rebuild) REBUILD=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
  esac
done

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null; then echo "Python 3.11+ is required" >&2; exit 1; fi
if ! command -v git >/dev/null; then echo "git is required" >&2; exit 1; fi

# Backend virtualenv
if [[ ! -x backend/.venv/bin/python ]]; then
  echo "› Creating Python virtualenv"
  "$PY" -m venv backend/.venv
fi
if [[ ! -f backend/.venv/.deps-installed || backend/requirements.txt -nt backend/.venv/.deps-installed ]]; then
  echo "› Installing Python dependencies"
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -r backend/requirements.txt
  touch backend/.venv/.deps-installed
fi

# Frontend
need_node() {
  if ! command -v npm >/dev/null; then echo "Node.js 20+ (npm) is required to build the UI" >&2; exit 1; fi
}
if [[ ! -d frontend/node_modules || frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]]; then
  need_node
  echo "› Installing frontend dependencies"
  (cd frontend && npm ci --no-audit --no-fund)
  REBUILD=1
fi

mkdir -p "$REPO_DIR" "$WORKSPACE_DIR"

if [[ "$MODE" == "dev" ]]; then
  echo "› API on http://localhost:$PORT (reload) · UI on http://localhost:5173"
  (cd backend && exec .venv/bin/python -m open_cowork --port "$PORT" --reload) &
  API_PID=$!
  trap 'kill $API_PID 2>/dev/null || true' EXIT
  cd frontend && VITE_API_URL="http://localhost:$PORT" npm run dev
  exit 0
fi

if [[ $REBUILD -eq 1 || ! -f frontend/dist/index.html ]]; then
  need_node
  echo "› Building the UI"
  (cd frontend && npm run build)
fi

echo "› Open Cowork on http://localhost:$PORT"
echo "  repos: $REPO_DIR"
echo "  tasks: $WORKSPACE_DIR"
cd backend && exec .venv/bin/python -m open_cowork --port "$PORT"
