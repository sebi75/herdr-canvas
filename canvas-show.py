#!/usr/bin/env python3
# ponytail: stdlib-only canvas watcher for a Herdr pane.
# Assembles canvas.html from template + turn.html + log.txt + title, renders it
# with headless Chrome at the pane's exact pixel width and the page's full height,
# and places the PNG in this pane through Herdr's pane.graphics.set. Content
# taller than the pane is paged: j/k, space/b, arrows, PgUp/PgDn, or the mouse
# wheel inside the pane. Re-renders when any input or the pane size changes.
# Ceiling: static picture, no clicks inside the page.
import base64
import fcntl
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


def archive(d):
    """Keep every version of turn.html under history/ for recall."""
    src = os.path.join(d, "turn.html")
    if not os.path.exists(src):
        return
    hist = os.path.join(d, "history"); os.makedirs(hist, exist_ok=True)
    n = len([l for l in read(os.path.join(d, "log.txt")).splitlines() if l.strip()])
    dst = os.path.join(hist, f"t{n:03d}-{time.strftime('%H%M%S')}.html")
    if not os.path.exists(dst):
        open(dst, "w").write(read(src))


def assemble(d):
    archive(d)
    title = read(os.path.join(d, "title"), "Session Canvas").strip()
    turn = read(os.path.join(d, "turn.html"), '<div class="status">Canvas on. Waiting for the first turn.</div>')
    lines = [l for l in read(os.path.join(d, "log.txt")).splitlines() if l.strip()][-10:][::-1]
    log = "\n".join(
        f'      <li><time>{H.escape(l.split(" ", 1)[0])}</time>{H.escape(l.split(" ", 1)[1] if " " in l else "")}</li>'
        for l in lines
    )
    page = read(TEMPLATE).replace("{{TITLE}}", H.escape(title)).replace("{{TURN}}", turn).replace("{{LOG}}", log)
    if 'class="mermaid"' in turn:  # diagrams: loaded only when a turn uses them
        page += MERMAID
    page += MEASURE
    out = os.path.join(d, "canvas.html")
    open(out, "w").write(page)
    return out


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
    """Cut one pane-height out of the full render by showing it shifted in a tiny page. Cached."""
    png = os.path.join(d, f"canvas-p{page}.png")
    if not os.path.exists(png):
        w_css, page_css = round(w / ZOOM), round(page_h / ZOOM)
        variant = os.path.join(d, f"canvas-p{page}.html")
        open(variant, "w").write(
            f'<body style="margin:0;background:#131A1C"><img src="file://{full}" '
            f'style="display:block;width:{w_css}px;margin-top:-{page * page_css}px"></body>')
        chrome([f"--screenshot={png}"], w_css, page_css, variant)
    return png


def place(png, w, h, cols, rows):
    data = base64.b64encode(open(png, "rb").read()).decode()
    return rpc("pane.graphics.set", {
        "pane_id": PANE, "format": "png", "image_width": w, "image_height": h,
        "data_base64": data,
        "placement": {"viewport_col": 0, "viewport_row": 0, "grid_cols": cols, "grid_rows": rows},
    })


def keys(fd):
    """Non-blocking read of key presses and wheel events -> list of 'next'/'prev'/'top'."""
    r, _, _ = select.select([fd], [], [], 0)
    if not r:
        return []
    buf = os.read(fd, 4096)
    out = []
    for m in re.finditer(rb"\x1b\[<(64|65);\d+;\d+[Mm]", buf):
        out.append("prev" if m.group(1) == b"64" else "next")
    buf = re.sub(rb"\x1b\[<\d+;\d+;\d+[Mm]", b"", buf)
    for tok in (b"\x1b[B", b"\x1b[6~", b"j", b" "):
        out += ["next"] * buf.count(tok)
    for tok in (b"\x1b[A", b"\x1b[5~", b"k", b"b"):
        out += ["prev"] * buf.count(tok)
    if b"g" in buf:
        out.append("top")
    return out


def main():
    d = sys.argv[1]
    inputs = [os.path.join(d, n) for n in ("turn.html", "log.txt", "title")]
    open(os.path.join(d, "watcher.pid"), "w").write(str(os.getpid()))
    log = open(os.path.join(d, "watcher.log"), "a")
    log.write(f"{time.strftime('%H:%M:%S')} start pid={os.getpid()} pane={PANE}\n")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    sys.stdout.write("\x1b[?1000h\x1b[?1006h\x1b[?25l\x1b[2J\x1b[H")  # wheel events, hide cursor
    sys.stdout.flush()
    last, page, pages, w, page_h, full = None, 0, 1, 0, 0, None
    try:
        while True:
            rows, cols = winsize()
            grid_rows = max(rows - 1, 1)
            key = (tuple(mtime(p) for p in inputs), rows, cols)
            moves = keys(fd)
            if key != last:
                try:
                    info = rpc("pane.graphics.info", {"pane_id": PANE})["result"]
                    cw, ch = info["cell_width_px"], info["cell_height_px"]
                    w, page_h = cols * cw, grid_rows * ch
                    for f in os.listdir(d):  # drop cached pages from the previous render
                        if f.startswith("canvas-p"):
                            os.remove(os.path.join(d, f))
                    html = assemble(d)
                    pages = measure(html, w, page_h)
                    full = render_full(d, html, w, page_h, pages)
                    page = 0
                    moves = ["top"]
                    log.write(f"{time.strftime('%H:%M:%S')} {w}x{page_h} pages={pages}\n")
                except Exception as e:  # keep the watcher alive
                    log.write(f"{time.strftime('%H:%M:%S')} err {e!r}\n")
                log.flush()
                last = key
            if moves and full:
                for mv in moves:
                    page = 0 if mv == "top" else min(pages - 1, max(0, page + (1 if mv == "next" else -1)))
                try:
                    r = place(page_png(d, full, page, w, page_h), w, page_h, cols, grid_rows)
                    hint = "  j/k or wheel to page" if pages > 1 else ""
                    sys.stdout.write(
                        f"\x1b[{rows};1H\x1b[2K{time.strftime('%H:%M:%S')}  page {page + 1}/{pages}{hint}  "
                        f"{'ok' if 'result' in r else r.get('error')}"
                    )
                    sys.stdout.flush()
                except Exception as e:
                    log.write(f"{time.strftime('%H:%M:%S')} place err {e!r}\n"); log.flush()
            time.sleep(0.1 if moves else 0.4)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[?1000l\x1b[?1006l\x1b[?25h")


if __name__ == "__main__":
    main()
