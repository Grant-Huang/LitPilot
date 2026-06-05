#!/usr/bin/env bash
# LitPilot 本地测试门禁：后端 pytest + Vercel 部署检查 + 前端 vitest + 类型检查 + next build
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_TEST="$ROOT/backend/scripts/test.sh"

echo "==> Backend pytest (full)"
"$BACKEND_TEST" tests/ -q

echo "==> Vercel deploy defaults (backend seed)"
"$BACKEND_TEST" tests/test_deploy_defaults.py -q

echo "==> Vercel backend entrypoint smoke"
cd "$ROOT/backend"
export PYTHONPATH="$(pwd)"
"$ROOT/backend/.venv/bin/python" -c "from app.main import app; assert app is not None"

echo "==> Frontend vitest"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  echo "Run: cd frontend && pnpm install" >&2
  exit 1
fi
if pnpm exec vitest run 2>/dev/null; then
  :
elif command -v pnpm >/dev/null 2>&1; then
  pnpm dlx vitest@2.1.9 run
else
  npx vitest@2.1.9 run
fi

echo "==> Frontend type-check"
pnpm run type-check

echo "==> Frontend Vercel build (next build)"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}" pnpm run build

echo "All gates passed (including Vercel-oriented checks)."
