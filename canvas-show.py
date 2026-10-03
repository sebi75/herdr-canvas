#!/usr/bin/env python3
# ponytail: stdlib-only canvas watcher for a Herdr pane.
# Assembles canvas.html from template + turn.html (this turn's news) + panels/*.html
# (kept across turns, edited only when they change) + log.txt + title, renders it
# with headless Chrome at the pane's exact pixel width and the page's full height,
# and places the PNG in this pane through Herdr's pane.graphics.set. Content
# taller than the pane is paged: j/k, space/b, up/down, PgUp/PgDn, or the mouse
# wheel. One snapshot per turn goes to history/; h/l or left/right step through
# them. Re-renders when any input or the pane size changes.
# Ceiling: static picture, no clicks inside the page.
import base64
import fcntl
import glob
import html as H
import json
import math
import os
import re
import select
import socket
import struct
import subprocess
import sys
import termios
import time
import tty

CHROME = os.environ.get("CANVAS_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PANE = os.environ["HERDR_PANE_ID"]
SOCK = os.environ["HERDR_SOCKET_PATH"]
ZOOM = float(os.environ.get("CANVAS_ZOOM", "1.5"))  # text scale; image pixel size stays exact
MAX_PAGES = 6
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
MEASURE = ('<script>setTimeout(()=>{document.title="H:"+document.documentElement.scrollHeight},3000)</script>')
VENDOR_MERMAID = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "mermaid.min.js")
MERMAID_INIT = 'mermaid.initialize({startOnLoad:true,theme:"dark",themeVariables:{fontFamily:"IBM Plex Sans, sans-serif"}});'
MERMAID = (f'<script src="file://{VENDOR_MERMAID}"></script><script>{MERMAID_INIT}</script>'
           if os.path.exists(VENDOR_MERMAID) else
           '<script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";' + MERMAID_INIT + '</script>')


def rpc(method, params):
    s = socket.socket(socket.AF_UNIX)
    s.connect(SOCK)
    s.sendall((json.dumps({"id": method, "method": method, "params": params}) + "\n").encode())
    s.settimeout(15)
    buf = b""
    while b"\n" not in buf:
        buf += s.recv(1 << 16)
    s.close()
    return json.loads(buf.decode().split("\n", 1)[0])


def winsize():
    rows, cols, _, _ = struct.unpack(
        "HHHH", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
    )
    return rows, cols


def read(path, default=""):
    try:
        return open(path).read()
    except FileNotFoundError:
        return default


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except FileNotFoundError:
        return None


def turn_start(d):
    """When the current prompt arrived (the hook writes it), 0 before the first one."""
    try:
        return float(read(os.path.join(d, "turn"), "0") or 0)
    except ValueError:
        return 0.0


def panels(d):
    """[(file name, path, mtime)] of panels/*.html, sorted by name."""
    out = []
    for path in sorted(glob.glob(os.path.join(d, "panels", "*.html"))):
        t = mtime(path)
        if t is not None:  # deleted between glob and stat
            out.append((os.path.basename(path), path, t))
    return out


def board(d):
    """Panels written this turn first, marked updated; the rest after, with the time they last changed."""
    start, out = turn_start(d), []
    for name, path, t in sorted(panels(d), key=lambda p: (p[2] < start, p[0])):
        label = H.escape(re.sub(r"^\d+-", "", name[:-5]).replace("-", " "))
        if t >= start:
            out.append(f'<section class="panel new"><h2>{label}<span class="tag">updated</span></h2>\n{read(path)}\n</section>')
        else:
            when = time.strftime("%H:%M", time.localtime(t))
            out.append(f'<section class="panel"><h2>{label}<span class="since">since {when}</span></h2>\n{read(path)}\n</section>')
    return "\n".join(out)


def snapshots(d):
    return sorted(glob.glob(os.path.join(d, "history", "turn-*.html")))


def step(view, move, n):
    """Move through n snapshots. None is the live board, which is also the newest snapshot."""
    if not n or move not in ("older", "newer"):
        return view
    i = (n - 1 if view is None else view) + (1 if move == "newer" else -1)
    return None if i >= n - 1 else max(0, i)


def assemble(d):
    title = read(os.path.join(d, "title"), "Session Canvas").strip()
    turn = read(os.path.join(d, "turn.html"), '<div class="status">Canvas on. Waiting for the first turn.</div>')
    panes = board(d)
    lines = [l for l in read(os.path.join(d, "log.txt")).splitlines() if l.strip()][-10:][::-1]
    log = "\n".join(
        f'      <li><time>{H.escape(l.split(" ", 1)[0])}</time>{H.escape(l.split(" ", 1)[1] if " " in l else "")}</li>'
        for l in lines
    )
    page = (read(TEMPLATE).replace("{{TITLE}}", H.escape(title)).replace("{{TURN}}", turn)
            .replace("{{BOARD}}", panes).replace("{{LOG}}", log))
    if 'class="mermaid"' in turn + panes:  # diagrams: loaded only when the page uses them
        page += MERMAID
    page += MEASURE
    out = os.path.join(d, "canvas.html")
    open(out, "w").write(page)
    # One snapshot per turn, overwritten until the next prompt, so h/l and recall see each turn's final board.
    hist = os.path.join(d, "history"); os.makedirs(hist, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(turn_start(d)))
    open(os.path.join(hist, f"turn-{stamp}.html"), "w").write(page)
    return out


def inputs(d):
    """Changes when the agent writes anything the board shows."""
    return (tuple(mtime(os.path.join(d, n)) for n in ("turn.html", "log.txt", "title")),
            tuple((n, t) for n, _, t in panels(d)))


def chrome(args, w_css, h_css, html):
    return subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         "--virtual-time-budget=5000", f"--force-device-scale-factor={ZOOM}",
         f"--window-size={w_css},{h_css}", *args, f"file://{os.path.abspath(html)}"],
        check=True, capture_output=True, text=True, timeout=60,
    )


def measure(html, w, page_h):
    """How many pane-heights the page needs (capped)."""
    w_css, page_css = round(w / ZOOM), round(page_h / ZOOM)
    dom = chrome(["--dump-dom"], w_css, page_css, html).stdout
    m = re.search(r"<title>H:(\d+)</title>", dom)
    content_css = int(m.group(1)) if m else page_css
    return max(1, min(MAX_PAGES, math.ceil(content_css / page_css)))


def render_full(d, html, w, page_h, pages):
    """One screenshot of the whole page, so every page is cut from the same layout."""
    full = os.path.join(d, "canvas-full.png")
    w_css, page_css = round(w / ZOOM), round(page_h / ZOOM)
    chrome([f"--screenshot={full}"], w_css, pages * page_css, html)
    return full


def page_png(d, full, page, w, page_h):
    """Cut one pane-height out of the full render with sips (macOS built-in, ~0.1s). Cached.
    sips pads a box that overruns the image, so a render a pixel short is fine."""
    png = os.path.join(d, f"canvas-p{page}.png")
    if not os.path.exists(png):
        off = page * page_h
        h_full = struct.unpack(">I", open(full, "rb").read(24)[20:24])[0]
        if off and off + page_h == h_full:  # sips returns the whole image when the box ends exactly at the edge
            off -= 1
        subprocess.run(["sips", "-c", str(page_h), str(w), "--cropOffset", str(off), "0",
                        full, "--out", png], check=True, capture_output=True, timeout=30)
    return png


def agent_gone(d):
    """True when the pane this canvas was split from no longer exists."""
    try:
        pane = open(os.path.join(d, "agent_pane")).read().strip()
    except FileNotFoundError:
        return False
    try:
        return "error" in rpc("pane.get", {"pane_id": pane})
    except Exception:
        return False  # socket hiccup: keep running


def place(png, w, h, cols, rows):
    data = base64.b64encode(open(png, "rb").read()).decode()
    return rpc("pane.graphics.set", {
        "pane_id": PANE, "format": "png", "image_width": w, "image_height": h,
        "data_base64": data,
        "placement": {"viewport_col": 0, "viewport_row": 0, "grid_cols": cols, "grid_rows": rows},
    })


def keys(fd):
    """Non-blocking read of key presses and wheel events -> list of 'next'/'prev'/'top'/'older'/'newer'."""
    r, _, _ = select.select([fd], [], [], 0)
    if not r:
        return []
    buf = os.read(fd, 4096)
    out = []
    wheel = re.findall(rb"\x1b\[<(64|65);\d+;\d+[Mm]", buf)
    if wheel:  # a trackpad swipe sends dozens of ticks: one page per burst, then the rest is drained
        out.append("prev" if wheel[-1] == b"64" else "next")
    buf = re.sub(rb"\x1b\[<\d+;\d+;\d+[Mm]", b"", buf)
    for tok in (b"\x1b[B", b"\x1b[6~", b"j", b" "):
        out += ["next"] * buf.count(tok)
    for tok in (b"\x1b[A", b"\x1b[5~", b"k", b"b"):
        out += ["prev"] * buf.count(tok)
    for tok in (b"\x1b[D", b"h"):
        out += ["older"] * buf.count(tok)
    for tok in (b"\x1b[C", b"l"):
        out += ["newer"] * buf.count(tok)
    if b"g" in buf:
        out.append("top")
    return out


def main():
    d = sys.argv[1]
    live = os.path.join(d, "canvas.html")
    open(os.path.join(d, "watcher.pid"), "w").write(str(os.getpid()))
    log = open(os.path.join(d, "watcher.log"), "a")
    log.write(f"{time.strftime('%H:%M:%S')} start pid={os.getpid()} pane={PANE}\n")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    sys.stdout.write("\x1b[?1000h\x1b[?1006h\x1b[?25l\x1b[2J\x1b[H")  # wheel events, hide cursor
    sys.stdout.flush()
    seen, shown, view, page, pages, w, page_h, full = None, None, None, 0, 1, 0, 0, None
    tick = 0
    try:
        while True:
            tick += 1
            if tick % 10 == 0 and agent_gone(d):  # agent session closed
                log.write(f"{time.strftime('%H:%M:%S')} agent pane gone, closing\n"); log.flush()
                try:
                    rpc("pane.graphics.clear", {"pane_id": PANE})
                    rpc("pane.close", {"pane_id": PANE})
                except Exception:
                    pass
                return
            rows, cols = winsize()
            grid_rows = max(rows - 1, 1)
            moves = keys(fd)
            now = inputs(d)
            if now != seen:  # the agent wrote something: rebuild and go back to the live board
                try:
                    assemble(d)
                except Exception as e:  # keep the watcher alive
                    log.write(f"{time.strftime('%H:%M:%S')} assemble err {e!r}\n"); log.flush()
                seen, view = now, None
            snaps = snapshots(d)
            for mv in moves:
                view = step(view, mv, len(snaps))
            target = live if view is None else snaps[view]
            want = (target, mtime(target), rows, cols)
            if want != shown:
                try:
                    info = rpc("pane.graphics.info", {"pane_id": PANE})["result"]
                    cw, ch = info["cell_width_px"], info["cell_height_px"]
                    w, page_h = cols * cw, grid_rows * ch
                    for f in os.listdir(d):  # drop cached pages from the previous render
                        if f.startswith("canvas-p"):
                            os.remove(os.path.join(d, f))
                    pages = measure(target, w, page_h)
                    full = render_full(d, target, w, page_h, pages)
                    for p in range(pages):  # pre-cut every page so flips are instant
                        page_png(d, full, p, w, page_h)
                    page = 0
                    moves = ["top"]
                    log.write(f"{time.strftime('%H:%M:%S')} {os.path.basename(target)} {w}x{page_h} pages={pages}\n")
                except Exception as e:  # keep the watcher alive
                    log.write(f"{time.strftime('%H:%M:%S')} err {e!r}\n")
                log.flush()
                shown = want
            if moves and full:
                for mv in moves:
                    if mv == "top":
                        page = 0
                    elif mv in ("next", "prev"):
                        page = min(pages - 1, max(0, page + (1 if mv == "next" else -1)))
                try:
                    r = place(page_png(d, full, page, w, page_h), w, page_h, cols, grid_rows)
                    name = os.path.basename(target)
                    where = "live" if view is None else f"{name[14:16]}:{name[16:18]}  l: newer"
                    hint = "  j/k page" if pages > 1 else ""
                    turns = "  h: older" if len(snaps) > 1 and view != 0 else ""
                    sys.stdout.write(
                        f"\x1b[{rows};1H\x1b[2Kturn {len(snaps) if view is None else view + 1}/{len(snaps)} {where}"
                        f"  page {page + 1}/{pages}{hint}{turns}  {'ok' if 'result' in r else r.get('error')}"
                    )
                    sys.stdout.flush()
                except Exception as e:
                    log.write(f"{time.strftime('%H:%M:%S')} place err {e!r}\n"); log.flush()
                time.sleep(0.25); keys(fd)  # drain the rest of a wheel burst
            select.select([fd], [], [], 0.4)  # wake on a key at once, poll files otherwise
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[?1000l\x1b[?1006l\x1b[?25h")


if __name__ == "__main__":
    main()
