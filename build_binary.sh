#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

PY="$ROOT/.venv/bin/python"
PYI="$ROOT/.venv/bin/pyinstaller"

APP_NAME="${APP_NAME:-ai-agent}"
# macOS only: arm64 | x86_64 | universal2 (defaults to current arch)
TARGET_ARCH="${TARGET_ARCH:-}"
# If set to 1, output name becomes: <APP_NAME>-<os>-<arch>
NAME_WITH_PLATFORM="${NAME_WITH_PLATFORM:-0}"

usage() {
  cat <<'EOF'
Usage:
  ./build_binary.sh

Optional env vars:
  APP_NAME=ai-agent
  TARGET_ARCH=arm64|x86_64|universal2   (macOS only)
  NAME_WITH_PLATFORM=1                 (suffix name with os/arch)

Examples:
  NAME_WITH_PLATFORM=1 ./build_binary.sh
  TARGET_ARCH=universal2 NAME_WITH_PLATFORM=1 ./build_binary.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -x "$PY" ]]; then
  echo "Missing venv python at: $PY" >&2
  echo "Create it with: ./install.sh  (or: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.lock.txt)" >&2
  exit 1
fi

if [[ ! -x "$PYI" ]]; then
  "$PY" -m pip install -U pyinstaller
fi

# Determine platform tag
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
NAME="$APP_NAME"
if [[ "$NAME_WITH_PLATFORM" == "1" ]]; then
  NAME="${APP_NAME}-${OS}-${ARCH}"
fi

# macOS arch selection (PyInstaller supports --target-arch on macOS)
PYI_ARCH_ARGS=()
if [[ "$OS" == "darwin" && -n "$TARGET_ARCH" ]]; then
  case "$TARGET_ARCH" in
    arm64|x86_64|universal2)
      PYI_ARCH_ARGS=(--target-arch "$TARGET_ARCH")
      if [[ "$NAME_WITH_PLATFORM" == "1" ]]; then
        NAME="${APP_NAME}-${OS}-${TARGET_ARCH}"
      fi
      ;;
    *)
      echo "Invalid TARGET_ARCH: $TARGET_ARCH (expected: arm64|x86_64|universal2)" >&2
      exit 2
      ;;
  esac
fi

# Keep PyInstaller cache/config inside the repo to avoid macOS sandbox/home-dir permission issues.
export PYINSTALLER_CONFIG_DIR="$ROOT/.pyinstaller"
export PYINSTALLER_CACHE_DIR="$ROOT/.pyinstaller_cache"

rm -rf "$ROOT/build" "$ROOT/dist"
rm -f "$ROOT/$APP_NAME.spec" "$ROOT/ai-agent.spec"

"$PYI" \
  --clean \
  --onefile \
  --name "$NAME" \
  "${PYI_ARCH_ARGS[@]}" \
  "$ROOT/main.py"

echo "Built: $ROOT/dist/$NAME"
