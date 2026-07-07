#!/usr/bin/env bash
# Marketing showcase reel: the three things that make Chief more than
# `if urgent: notify()` — the funnel, the learning loop, the cost trace.
# Records to docs/assets/showcase.gif.
#
#   make showcase        # record + render (needs asciinema + agg)
#
# Tools: `uv tool install asciinema`; agg from
# https://github.com/asciinema/agg/releases (or `cargo install agg`).
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=docs/assets/showcase.gif
CAST=$(mktemp /tmp/chief-showcase-XXXX.cast)
STEPS=$(mktemp /tmp/chief-steps-XXXX.sh)

command -v asciinema >/dev/null || { echo "missing: asciinema (uv tool install asciinema)"; exit 1; }
command -v agg >/dev/null || { echo "missing: agg (https://github.com/asciinema/agg/releases)"; exit 1; }

# the reel, as a script the recording plays back
cat > "$STEPS" <<'REEL'
set -e
say() { printf "\n\033[1;36m# %s\033[0m\n" "$1"; sleep 2; }

say "1/3  A day of an engineer — 24 events in, interrupted exactly once"
uv run chief demo --fast
sleep 2

say "2/3  It learns your preferences — and proves it (reward loop, no labels)"
uv run chief eval --learning --out /tmp/chief-showcase-reports
sed -n '/Learning curve/,/^```$/p' /tmp/chief-showcase-reports/learning.md | tail -n +3 | head -n -1
sleep 3

say "3/3  Every decision is priced and explainable — nothing is a black box"
printf 'per-decision trace: stages, tokens (cache-aware), USD cost, prompt version\n'
printf 'try it yourself, zero keys, fully offline:\n\n    uvx agent-chief demo\n'
sleep 3
REEL

asciinema rec --overwrite --cols 100 --rows 44 -c "bash $STEPS" "$CAST"
agg --font-size 14 --speed 0.7 --theme monokai "$CAST" "$OUT"
rm -f "$CAST" "$STEPS"
echo "wrote $OUT"
