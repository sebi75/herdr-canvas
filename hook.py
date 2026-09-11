#!/usr/bin/env python3
"""Claude Code hooks for the session canvas.

UserPromptSubmit stamps the start of a turn. Stop refuses to end a turn whose
turn.html is older than that stamp, so the canvas cannot silently go stale.
SessionStart opens the canvas automatically, and is only used if you register it.
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
SESSIONS = os.environ.get("CANVAS_SESSIONS", os.path.join(ROOT, "sessions"))

d = json.load(sys.stdin)
sid = d.get("session_id", "")
event = d.get("hook_event_name")
sdir = os.path.join(SESSIONS, sid)
turn_html, pane, stamp = (os.path.join(sdir, n) for n in ("turn.html", "pane", "turn"))

if event == "SessionStart":
    if not os.environ.get("HERDR_PANE_ID"):
        sys.exit(0)
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=sid)
    r = subprocess.run([os.path.join(ROOT, "canvas.sh"), "on", "Session Canvas"],
                       env=env, capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        print(f"Canvas is on in {r.stdout.strip()}. Follow the canvas skill every reply.")
    sys.exit(0)

if not os.path.exists(pane):  # canvas not on for this session
    sys.exit(0)

if event == "UserPromptSubmit":
    open(stamp, "w").write(str(time.time()))
elif event == "Stop" and not d.get("stop_hook_active"):
    if not os.path.exists(stamp):  # no prompt seen yet in this session
        sys.exit(0)
    if not os.path.exists(turn_html) or os.path.getmtime(turn_html) < os.path.getmtime(stamp):
        print(json.dumps({"decision": "block", "reason":
            f"Canvas is on but {turn_html} was not rewritten this turn. "
            "Write this reply's turn.html and append a log line as the canvas skill "
            "describes, then finish."}))
