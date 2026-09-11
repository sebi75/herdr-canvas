# Install

Instructions for an agent. Run each step, check the result, and stop if a check fails.

## 1. Check the environment

    echo "$HERDR_PANE_ID"          # must be set: you are inside a Herdr pane
    herdr --version                # 0.7 or newer
    python3 --version              # 3.9 or newer
    ls "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"   # macOS

On Linux, find the Chrome or Chromium binary and note the path for step 4.
If `HERDR_PANE_ID` is empty, stop and tell the user to run their agent inside Herdr.

## 2. Copy the files

    mkdir -p ~/.claude/canvas
    cp canvas.sh canvas-show.py hook.py template.html ~/.claude/canvas/
    cp -r vendor ~/.claude/canvas/
    chmod +x ~/.claude/canvas/canvas.sh ~/.claude/canvas/canvas-show.py

    mkdir -p ~/.claude/skills/canvas
    cp skill/SKILL.md ~/.claude/skills/canvas/

## 3. Register the hooks

Add two entries to `~/.claude/settings.json`, keeping anything already there:

```python
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.claude/settings.json")
s = json.load(open(p)) if os.path.exists(p) else {}
hooks = s.setdefault("hooks", {})
cmd = {"type": "command", "command": "python3 ~/.claude/canvas/hook.py"}
for event in ("UserPromptSubmit", "Stop"):
    lst = hooks.setdefault(event, [])
    if not any("canvas/hook.py" in h.get("command", "") for e in lst for h in e.get("hooks", [])):
        lst.append({"hooks": [cmd]})
json.dump(s, open(p, "w"), indent=2)
print({k: len(v) for k, v in hooks.items()})
PY
```

To open the canvas automatically in every session instead of on `/canvas`, add the same
command under `SessionStart` with matcher `startup|resume|clear`. Leave it out otherwise.

## 4. Non-default Chrome path

If Chrome is somewhere else, set it where your agent's shell will see it:

    export CANVAS_CHROME=/usr/bin/chromium

## 5. Turn on Herdr's graphics

Pane images are off unless the flag is set. Add this to `~/.config/herdr/config.toml`:

```toml
[experimental]
kitty_graphics = true
```

Then:

    herdr server reload-config

The server picks up the flag, but the client only reports the terminal's cell size when it
attaches. **Ask the user to detach and rerun `herdr`** — their agent sessions survive, the
server keeps them. Without the reattach the API answers `cell_size_unavailable`.

Check it:

    python3 - <<'PY'
    import socket, json, os
    s = socket.socket(socket.AF_UNIX); s.connect(os.environ["HERDR_SOCKET_PATH"])
    s.sendall((json.dumps({"id":"1","method":"pane.graphics.info",
                           "params":{"pane_id":os.environ["HERDR_PANE_ID"]}})+"\n").encode())
    print(s.recv(4096).decode())
    PY

You want `cell_width_px` and `cell_height_px` back. `feature_disabled` means the flag is not
applied, `cell_size_unavailable` means the client has not reattached.

## 6. Verify

    ~/.claude/canvas/canvas.sh on "Install check"

A pane opens to the right and shows the canvas within a couple of seconds. If it stays
blank, read `sessions/<id>/watcher.log`. Then:

    ~/.claude/canvas/canvas.sh off

Tell the user to run `/canvas` in a new session.

## Notes

macOS may ask for Screen Recording permission if you take screenshots to check the pane
yourself. That is for your screenshots, not for the canvas, and macOS only applies it after
the terminal restarts. Rendering needs no permission.

Herdr's graphics API is under `[experimental]` and the method names may change between
releases. If `pane.graphics.set` returns an unknown-method error, check `herdr api schema
--json` for the current name.
