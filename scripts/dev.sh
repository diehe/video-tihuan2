#!/usr/bin/env bash
set -euo pipefail

python3 -m engine --host 127.0.0.1 --port 8765 &
ENGINE_PID=$!
trap 'kill "$ENGINE_PID" 2>/dev/null || true' EXIT

npm run dev
