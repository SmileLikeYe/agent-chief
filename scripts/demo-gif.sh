#!/usr/bin/env bash
# Reproducible README demo GIF: asciinema (record) + agg (render).
#   make demo-gif
# Tools: `uv tool install asciinema`; agg from
# https://github.com/asciinema/agg/releases (or `cargo install agg`).
set -euo pipefail

cd "$(dirname "$0")/.."
OUT=docs/assets/demo.gif
CAST=$(mktemp /tmp/chief-demo-XXXX.cast)

command -v asciinema >/dev/null || { echo "missing: asciinema (uv tool install asciinema)"; exit 1; }
command -v agg >/dev/null || { echo "missing: agg (https://github.com/asciinema/agg/releases)"; exit 1; }

asciinema rec --overwrite --cols 100 --rows 42 \
  -c "uv run chief demo --fast" "$CAST"
agg --font-size 14 --speed 0.6 --theme monokai "$CAST" "$OUT"
rm -f "$CAST"
echo "wrote $OUT"
