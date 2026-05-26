#!/usr/bin/env bash
# LitPilot 本地测试门禁：后端 pytest + 前端 vitest + 前端类型检查
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Backend pytest"
cd "$ROOT/backend"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python -m pytest tests/ -q
else
  python3 -m pytest tests/ -q
fi

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

echo "All gates passed."
