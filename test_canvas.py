# Self-check for the board and turn stepping: python3 test_canvas.py
import importlib.util, os, tempfile, time

os.environ.setdefault("HERDR_PANE_ID", "test")
os.environ.setdefault("HERDR_SOCKET_PATH", "/dev/null")
spec = importlib.util.spec_from_file_location("show", os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas-show.py"))
show = importlib.util.module_from_spec(spec); spec.loader.exec_module(show)

d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "panels"))
for name, body in (("10-state.html", "<p>old</p>"), ("open-questions.html", "<p>new</p>")):
    open(os.path.join(d, "panels", name), "w").write(body)
old = time.time() - 600
os.utime(os.path.join(d, "panels", "10-state.html"), (old, old))
open(os.path.join(d, "turn"), "w").write(str(time.time() - 60))

b = show.board(d)
assert b.index("open questions") < b.index(">state<"), "panel written this turn comes first"
assert b.count('class="panel new"') == 1 and "since " in b, "only the new panel is marked updated"
assert "10-" not in b, "numeric prefix is hidden"

show.assemble(d)
assert len(show.snapshots(d)) == 1
show.assemble(d)
assert len(show.snapshots(d)) == 1, "same turn overwrites its snapshot"

assert show.step(None, "older", 3) == 1
assert show.step(1, "older", 3) == 0 and show.step(0, "older", 3) == 0
assert show.step(1, "newer", 3) is None, "stepping onto the newest snapshot is the live board"
assert show.step(None, "newer", 3) is None and show.step(None, "older", 0) is None
print("ok")
