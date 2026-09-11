#!/usr/bin/env bash
# Per-session canvas pane in Herdr.
#   canvas.sh on [title]   split a pane to the right, start the watcher, print the session dir
#   canvas.sh off          stop the watcher and close the pane
#   canvas.sh status       print dir, pane, watcher pid
# Running "on" twice is safe: it reuses a live pane and watcher.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSIONS="${CANVAS_SESSIONS:-$ROOT/sessions}"
SID="${CLAUDE_CODE_SESSION_ID:-${CODEX_THREAD_ID:-${HERDR_PANE_ID:-manual}}}"
DIR="$SESSIONS/${SID//:/_}"
PANEFILE="$DIR/pane"
PIDFILE="$DIR/watcher.pid"
RATIO="${CANVAS_RATIO:-0.45}"

alive() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }
pane_ok() { [ -f "$PANEFILE" ] && herdr pane get "$(cat "$PANEFILE")" >/dev/null 2>&1; }

case "${1:-on}" in
  on)
    [ -n "${HERDR_PANE_ID:-}" ] || { echo "not inside a Herdr pane"; exit 1; }
    command -v herdr >/dev/null || { echo "herdr not found in PATH"; exit 1; }
    mkdir -p "$DIR"
    [ -f "$DIR/title" ] || echo "${2:-Session Canvas}" > "$DIR/title"
    [ -f "$DIR/log.txt" ] || echo "t0 canvas on $(date +%H:%M)" > "$DIR/log.txt"
    [ -f "$DIR/turn.html" ] || echo '<div class="status">Canvas on. Waiting for the first turn.</div>' > "$DIR/turn.html"
    if pane_ok && alive; then echo "$DIR"; exit 0; fi
    if ! pane_ok; then
      herdr pane split "$HERDR_PANE_ID" --direction right --ratio "$RATIO" --cwd "$DIR" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])' > "$PANEFILE"
      herdr pane rename "$(cat "$PANEFILE")" "canvas · $HERDR_PANE_ID" >/dev/null
    fi
    herdr pane run "$(cat "$PANEFILE")" python3 "$ROOT/canvas-show.py" "$DIR" >/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do alive && break; sleep 0.3; done
    echo "$DIR"
    ;;
  off)
    alive && kill "$(cat "$PIDFILE")" 2>/dev/null || true
    pkill -f "canvas-show.py $DIR" 2>/dev/null || true
    pane_ok && herdr pane close "$(cat "$PANEFILE")" >/dev/null 2>&1 || true
    rm -f "$PIDFILE" "$PANEFILE"
    echo "canvas off"
    ;;
  status)
    echo "dir: $DIR"
    echo "pane: $(cat "$PANEFILE" 2>/dev/null || echo none)"
    alive && echo "watcher: $(cat "$PIDFILE")" || echo "watcher: not running"
    ;;
  *)
    echo "usage: canvas.sh on [title] | off | status"; exit 2 ;;
esac
