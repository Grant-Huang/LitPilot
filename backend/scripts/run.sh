#!/usr/bin/env bash
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
