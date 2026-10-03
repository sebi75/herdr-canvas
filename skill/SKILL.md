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

The board has two layers. `turn.html` is this reply's news and is replaced every turn. `panels/` holds what outlives a turn, and each panel changes only when its content changes. The watcher assembles them within a second: news on top, then the panels written this turn (marked `updated`), then the rest (marked with the time they last changed), then the log. It keeps one snapshot of the whole board per turn under `history/`.

0. **Recall first.** Run `ls panels/` and read the panels this reply touches, plus the tail of `log.txt`. Open `history/turn-*.html` when an earlier turn matters.
1. **`turn.html`: overwrite it every reply.** This reply's news only: the status line and at most one or two visuals. It fits on one screen. Do not carry anything over from the last turn here. Anything worth carrying goes in a panel.
2. **`panels/<name>.html`: change only what changed.** A panel holds one thing that stays true across turns: the state (Decided / Open / Next), a plan, a system diagram, a findings table.
   - New topic: create the panel with Write.
   - A fact changed: Edit those lines. Leave a panel whose content still holds untouched, so its `updated` mark means something.
   - Done or wrong: delete the panel, or shrink it to one line in the state panel.
   - The file name is the heading: `open-questions.html` shows as "open questions". A number prefix such as `10-` sets the order and is not shown.
3. **`log.txt`: append one line** `t<N> <one-line summary of this turn>`. Newest 10 are shown.
4. **`title`**: set once, the session topic in 2-4 words. Change it if the topic changes.

- **A loop tick that found nothing leaves the canvas alone.** When the turn came from `/loop` and there is no news, do not touch `turn.html`, the panels, or the log. Replacing real content with "still waiting" loses what the canvas was for. When the tick does find something, update it normally.
- **Write the canvas last.** Do the work first, then describe what is true when the reply ends. A canvas written before the work freezes the plan and reads as stale a second later.

### What goes in `turn.html`

Match the reply. A quick answer gets a status line and nothing else. Anything with structure gets drawn: a process is a flow or a mermaid diagram, numbers are a chart, options are a table, a system is a diagram. Prefer a picture over prose whenever the content has parts, order, or quantity. Never pad.

- Always first: `<div class="status">one line, what this turn did<small>turn N · date · one key fact</small></div>`
- Then at most one or two of:
  - `.flow`: `<div class="flow"><div class="box ok"><b>Step</b><span>detail</span></div><div class="arrow">→</div>…</div>` for a pipeline, a chain, or a decision path. `.box.warn` for a problem.
  - `<table>`: comparisons, options, inventories.
  - `.cols`: `<div class="cols"><div class="col now"><h2>Now</h2><ul>…</ul></div><div class="col"><h2>Next</h2>…</div></div>` for side-by-side lists. Any headings, not only Now / Next.
  - Inline `<svg>` for a diagram. `<p>` for one or two sentences when words beat boxes.
- Wrap each visual in `<section><h2>label</h2>…</section>`. Use `<code>` for paths and commands, `<span class="tag">` for a short badge, `.tag.w` for a warning.

### What goes in a panel

- One topic per panel, at most about a third of a screen. Split a panel that grows past that.
- The same building blocks as `turn.html`, without the status line and without a `<section>` or `<h2>` wrapper. The watcher adds the frame and the heading.
- Keep about six panels at most. Delete the ones that no longer help.
- The usual first panel is `10-state.html`: `.cols` with Decided / Open / Next.

### When the user asks several questions

Answer every one, in order, in a table, so none gets lost:

```html
<section><h2>Questions</h2><table>
<tr><th>#</th><th>question</th><th>answer</th><th></th></tr>
<tr><td>1</td><td>short restatement</td><td>one or two lines</td><td><span class="tag">answered</span></td></tr>
<tr><td>2</td><td>…</td><td>…</td><td><span class="tag w">needs your call</span></td></tr>
</table></section>
```

The table goes in `turn.html`. Number the chat reply the same way. Anything not answered goes into the state panel as Open, and stays there until it is.

### Charts and diagrams (preferred over text)

The user wants things represented visually. Reach for these first, prose last.

- Diagrams (flows, sequences, state machines, trees): `<pre class="mermaid">flowchart LR …</pre>`. Rendered dark. Keep node labels short.
- Charts with up to ~20 values: inline `<svg viewBox="0 0 600 200">` with `<rect>` bars or a `<polyline>`, axis labels in `<text fill="#97A5A8" font-size="11">`, values written on the marks. Use `#57B8B2` for the main series, `#E0AB52` for a highlight.
- Bigger data: `<canvas>` plus an inline `<script>` that draws it. No external libraries besides mermaid.
- Comparisons and inventories stay tables.

### Length

One pane is about 1600x1200 px at 1.5x. Page 1 shows the news and then the panels updated this turn, so keep both short. The full board is paged up to 6 pages: the user pages with j/k or the mouse wheel. h/l (or left/right) steps back and forward through earlier turns, and any new write returns the pane to the live board. Never shrink text to fit.
