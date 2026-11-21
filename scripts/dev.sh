#!/usr/bin/env bash
# Desenvolvimento no browser: backend FastAPI (127.0.0.1:8765) + Vite (127.0.0.1:1420).
# Os dados de desenvolvimento ficam em ./.dev-data (separados dos dados reais da app).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .dev-token ]]; then
  python3 -c "import secrets; print(secrets.token_urlsafe(32))" > .dev-token
  chmod 600 .dev-token
fi
export UANJI_TOKEN="$(cat .dev-token)"
export UANJI_DATA_DIR="$ROOT/.dev-data"
export UANJI_PORT="${UANJI_PORT:-8765}"
export UANJI_ENV=development

cleanup() { [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd backend && .venv/bin/python -m uanji) &
BACK_PID=$!

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:$UANJI_PORT/health" >/dev/null && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$UANJI_PORT/health" >/dev/null || { echo "O backend não arrancou."; exit 1; }
echo "Backend pronto em http://127.0.0.1:$UANJI_PORT  (documentação OpenAPI em /docs)"

cd frontend && npm run dev
