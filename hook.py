#!/usr/bin/env python3
"""Claude Code hooks for the session canvas.

UserPromptSubmit stamps the start of a turn, and marks it when the prompt is a
/loop firing. PostToolUse records the last piece of real work. Stop refuses to
end a turn whose turn.html is missing, older than the prompt, or older than that
last piece of work, and lets a quiet loop tick through untouched.
SessionEnd closes the canvas pane so it does not outlive the agent. SessionStart
opens the canvas automatically, and is only used if you register it.
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
last_tool = os.path.join(sdir, "last_tool")
loop_tick = os.path.join(sdir, "loop_tick")


def is_loop(prompt):
    """A /loop firing re-sends its own prompt, so quiet ticks should not force a rewrite."""
    p = (prompt or "").lstrip()
    return p.startswith("/loop") or "<<autonomous-loop" in p


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

if event == "SessionEnd":
    if d.get("reason") != "clear":  # /clear keeps the session, keep its canvas
        subprocess.run([os.path.join(ROOT, "canvas.sh"), "off"],
                       env=dict(os.environ, CLAUDE_CODE_SESSION_ID=sid),
                       capture_output=True, timeout=10)
    sys.exit(0)

if event == "UserPromptSubmit":
    open(stamp, "w").write(str(time.time()))
    for f in (last_tool, loop_tick):
        if os.path.exists(f):
            os.remove(f)
    if is_loop(d.get("prompt")):
        open(loop_tick, "w").write("1")
elif event == "PostToolUse":
    # Record work done this turn, ignoring the calls that write the canvas itself.
    blob = json.dumps(d.get("tool_input", {}))
    if sdir not in blob and "turn.html" not in blob:  # paths are often shell variables
        open(last_tool, "w").write(str(time.time()))
elif event == "Stop" and not d.get("stop_hook_active"):
    if not os.path.exists(stamp):  # no prompt seen yet in this session
        sys.exit(0)
    if os.path.exists(loop_tick):  # a loop tick updates the canvas only when it found something
        sys.exit(0)
    if not os.path.exists(turn_html) or os.path.getmtime(turn_html) < os.path.getmtime(stamp):
        print(json.dumps({"decision": "block", "reason":
            f"Canvas is on but {turn_html} was not rewritten this turn. "
            "Write this reply's turn.html and append a log line as the canvas skill "
            "describes, then finish."}))
    elif os.path.exists(last_tool) and os.path.getmtime(turn_html) < os.path.getmtime(last_tool):
        print(json.dumps({"decision": "block", "reason":
            f"{turn_html} was written before the rest of this turn's work, so it "
            "describes the plan instead of the result. Rewrite it to say what is "
            "true now, then finish."}))
