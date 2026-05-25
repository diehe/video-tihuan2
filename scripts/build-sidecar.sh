#!/usr/bin/env bash
set -euo pipefail

mkdir -p sidecars

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required to build the packaged app with audio support." >&2
  echo "Install ffmpeg on the build machine, then run this script again." >&2
  exit 1
fi

if [[ -z "${PYTHON:-}" ]]; then
  if [[ "$(uname -s)" == "Darwin" && -x "/opt/homebrew/bin/python3.12" ]]; then
    PYTHON="/opt/homebrew/bin/python3.12"
  else
    PYTHON="python3"
  fi
fi

SIDECAR_VENV="${SIDECAR_VENV:-.venv-sidecar}"
"$PYTHON" -m venv "$SIDECAR_VENV"
"$SIDECAR_VENV/bin/python" -m pip install --upgrade pip
"$SIDECAR_VENV/bin/python" -m pip install -r requirements.txt pyinstaller
"$SIDECAR_VENV/bin/python" -m PyInstaller \
  --clean \
  --distpath build/sidecar-dist \
  --workpath build/sidecar-work \
  packaging/video-tihuan-engine.spec

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)
    target="aarch64-apple-darwin"
    ;;
  Darwin-x86_64)
    target="x86_64-apple-darwin"
    ;;
  Linux-x86_64)
    target="x86_64-unknown-linux-gnu"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    target="x86_64-pc-windows-msvc"
    ;;
  *)
    echo "Unsupported sidecar build platform: $(uname -s)-$(uname -m)" >&2
    exit 1
    ;;
esac

cp "build/sidecar-dist/video-tihuan-engine" "sidecars/video-tihuan-engine-${target}"
