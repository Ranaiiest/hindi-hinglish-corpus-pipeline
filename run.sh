#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then echo "usage: ./run.sh <raw_dir> <out_dir>" >&2; exit 2; fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$HERE/../.venv/bin/python" ]; then
  PY="$(cd "$HERE/../.venv/bin" && pwd)/python"
elif [ -x "$HERE/.venv/bin/python" ]; then
  PY="$(cd "$HERE/.venv/bin" && pwd)/python"
else
  PY="python3"
fi
RAW="$(cd "$1" && pwd)"
mkdir -p "$2"
OUT="$(cd "$2" && pwd)"
export PYTHONHASHSEED=0 PYTHONPATH="$HERE/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m indicpipe.pipeline "$RAW" "$OUT" ${CONFIG:+--config "$CONFIG"}
