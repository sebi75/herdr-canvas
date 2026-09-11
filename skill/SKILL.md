---
name: canvas
description: Turn on a live visual canvas for this session, rendered in a Herdr pane next to this one (no browser). Use when the user runs /canvas, says "canvas on", or asks for a visual status pane. "/canvas off" stops it.
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# Session canvas

A picture of this session's state, drawn into a Herdr pane beside the agent. No browser tab, nothing on claude.ai.

## Turn it on

Run once, with a 2-4 word title for this session's work:

```bash
~/.claude/canvas/canvas.sh on "<title>"
```

It prints the session directory. Idempotent. If it prints `not inside a Herdr pane`, tell the user and stop.

`/canvas off` runs `canvas.sh off`. `/canvas status` runs `canvas.sh status`.

## Every reply, for the rest of this session

Copy into every compaction summary: `Canvas is on in <dir>; reread ~/.claude/skills/canvas/SKILL.md before the next reply.` A Stop hook blocks the turn until this is done.

Three files in that directory. The watcher assembles and redraws them within a second, and archives every version under `history/`.

0. **Recall first.** Read the current `turn.html` and `log.txt` before writing. Open `history/` when an older version matters. The new fragment is built from the previous one plus this reply: keep what still holds, update what changed, drop what is done.
1. **`turn.html`: overwrite the whole file.** Two parts: this reply's news on top (status line, one visual), then a carried **State** section (`.cols` with Decided / Open / Next, or whatever headings fit) that you rewrite from the previous version every turn. Carried means reviewed and updated, never pasted unchanged and never mechanically left behind.
2. **`log.txt`: append one line** `t<N> <one-line summary of this turn>`. Newest 10 are shown.
3. **`title`**: set once, the session topic in 2-4 words. Change it if the topic changes.

### What goes in `turn.html`

Match the reply. A quick answer gets a status line and nothing else. Anything with structure gets drawn: a process is a flow or a mermaid diagram, numbers are a chart, options are a table, a system is a diagram. Prefer a picture over prose whenever the content has parts, order, or quantity. Never pad.

- Always first: `<div class="status">one line, what this turn did<small>turn N · date · one key fact</small></div>`
- Then at most one or two of:
  - `.flow`: `<div class="flow"><div class="box ok"><b>Step</b><span>detail</span></div><div class="arrow">→</div>…</div>` for a pipeline, a chain, or a decision path. `.box.warn` for a problem.
  - `<table>`: comparisons, options, inventories.
  - `.cols`: `<div class="cols"><div class="col now"><h2>Now</h2><ul>…</ul></div><div class="col"><h2>Next</h2>…</div></div>` when there is real state to track. Any headings, not only Now / Next.
  - Inline `<svg>` for a diagram. `<p>` for one or two sentences when words beat boxes.
- Wrap each visual in `<section><h2>label</h2>…</section>`. Use `<code>` for paths and commands, `<span class="tag">` for a short badge, `.tag.w` for a warning.

### When the user asks several questions

Answer every one, in order, in a table, so none gets lost:

```html
<section><h2>Questions</h2><table>
<tr><th>#</th><th>question</th><th>answer</th><th></th></tr>
<tr><td>1</td><td>short restatement</td><td>one or two lines</td><td><span class="tag">answered</span></td></tr>
<tr><td>2</td><td>…</td><td>…</td><td><span class="tag w">needs your call</span></td></tr>
</table></section>
```

Number the chat reply the same way. Anything not answered goes into the carried State section as Open, and stays there until it is.

### Charts and diagrams (preferred over text)

The user wants things represented visually. Reach for these first, prose last.

- Diagrams (flows, sequences, state machines, trees): `<pre class="mermaid">flowchart LR …</pre>`. Rendered dark. Keep node labels short.
- Charts with up to ~20 values: inline `<svg viewBox="0 0 600 200">` with `<rect>` bars or a `<polyline>`, axis labels in `<text fill="#97A5A8" font-size="11">`, values written on the marks. Use `#57B8B2` for the main series, `#E0AB52` for a highlight.
- Bigger data: `<canvas>` plus an inline `<script>` that draws it. No external libraries besides mermaid.
- Comparisons and inventories stay tables.

### Length

One pane is about 1600x1200 px at 1.5x. Longer content is paged: the watcher renders the full height (up to 6 pages) and the user pages with j/k or the mouse wheel in the canvas pane. Page 1 must stand alone: status, the answer, the main visual. Details, the State section, and the log can follow. Never shrink text to fit.
