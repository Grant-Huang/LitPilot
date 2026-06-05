#!/usr/bin/env bash
# 使用 backend/.venv 运行 pytest；若虚拟环境或 pytest 缺失则自动创建/安装。
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

PYTHON_BIN=".venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "==> Creating backend/.venv"
  python3 -m venv .venv
fi

if ! "$PYTHON_BIN" -m pytest --version >/dev/null 2>&1; then
  echo "==> Installing backend dependencies (requirements.txt)"
  .venv/bin/pip install -r requirements.txt
fi

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
exec "$PYTHON_BIN" -m pytest "$@"
