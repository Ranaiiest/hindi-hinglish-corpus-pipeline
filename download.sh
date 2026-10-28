#!/usr/bin/env bash
set -euo pipefail
RAW="${1:-raw}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$HERE/../.venv/bin/python" ]; then
  PY="$(cd "$HERE/../.venv/bin" && pwd)/python"
elif [ -x "$HERE/.venv/bin/python" ]; then
  PY="$(cd "$HERE/.venv/bin" && pwd)/python"
else
  PY="python3"
fi
"$PY" -m pip install -q huggingface_hub pyarrow
"$PY" "$HERE/scripts/download.py" "$RAW"
echo "raw data in $RAW  (do NOT edit these files; run.sh starts from them)"
