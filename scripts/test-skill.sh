#!/usr/bin/env bash
# Offline tests for the ulanzi-deck skill: no Ulanzi Studio, device or installed apps needed.
# Uses uv when available (it provides Pillow from the script's inline metadata), else python3.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"
if command -v uv >/dev/null 2>&1; then
  run=(uv run --quiet --with "pillow>=10.1" python)
else
  run=(python3)
fi
"${run[@]}" -m py_compile skills/ulanzi-deck/scripts/ulanzi.py
"${run[@]}" -m unittest discover -s tests -v
