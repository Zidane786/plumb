---
name: ux
description: Deep UX review of one screen or flow - against the project's ux.md, its approved prototype screen, usability heuristics, accessibility beyond contrast (keyboard path, focus, labels, targets, reduced motion) and a visual polish pass (hierarchy, spacing rhythm, alignment, type details, density, motion) - with screenshots at phone and desktop widths in light and dark beside the prototype when a browser is available. Writes an HTML review and offers fixes or Slate tickets. Use after building a screen or flow, or when asked for a UX review, usability check or polish pass.
argument-hint: "<screen | flow>"
---

# /plumb:ux <screen | flow> — review one screen or flow as a user meets it

`/plumb:audit` checks rules across the product; this is the deep look at one place. The method (what to gather, the
heuristics, accessibility, the visual polish pass, findings, the report): `<ROOT>/reference/ux.md`. Commands:
`<ROOT>/reference/scripts.md`.

**Rules.** One question at a time through the question tool, options with the recommendation first. **Nothing is
written without the user's OK:** the review page and its screenshots are the output this command was asked for; any
other write (a fix, a screen file, `vocabulary.md`) is shown first (what and where) and made only on a yes. Never install or download anything (no browser, no Playwright, no packages); if something is
missing, ask the user and wait. Review in light and dark unless `Themes: light-only`. Anything that changes what a
screen shows goes through the prototype first.

```
 which screen(s) ─▶ gather (prototype, ux.md, code) ─▶ screenshots (browser?) ─▶ review in method order
   ─▶ findings ─▶ <docs>/ux-review-YYYY-MM-DD.html ─▶ offer fixes / tickets ─▶ STOP
```

## Step 0: context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. Find `PLUMB.md` at the project root. Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Python:` (**PY**, `python3` when unset), `Themes:`, and **docs**: the folder
   of the `## Prototype` `Main:` path (else the tokens file's `$extensions.plumb.docs_dir`, else `docs/design`).
4. Resolve the argument to screens using `<docs>/prototype/screens.json` (ids, titles, routes) and `ux.md`'s key flows.
   Unclear or none given → ask which screen or flow, listing the likely ones (recommend the most recently built).
5. A screen with no prototype screen → say so: the review compares against `ux.md` and the heuristics only, and offer
   `/plumb:prototype` afterwards.

## Step 1: gather

Follow `<ROOT>/reference/ux.md` §1: the screen file(s) and their `screens.json` entries, the source files, the components they
use, the skill's `ux.md`, `vocabulary.md`, `accessibility.md`, `motion.md`, `design.md`, the platform guidelines, and the
decisions that name these screens.

## Step 2: screenshots (when a browser is available)

Phone (390 × 844) and desktop (1280 × 900), light and dark, the built screen and its prototype screen side by side;
walk the main path and each state you can reach.

- Browser, first available: the agent's own browser tool → `PY "<ROOT>/scripts/screenshot.py" <url-or-file> --out <png>
  --width <w> --height <h> --theme <light|dark>` → none: `screenshot.py` exits 3 with
  `note: visual comparison skipped: no browser found` and a `fix:` line; say so in the report and review the code.
- Built screens need the app running: ask once for the dev server's URL (never start installs). Prototype screens open
  from disk: `<docs>/prototype.html#screen-<id>/<state>`.
- Save shots in `<docs>/ux-review-YYYY-MM-DD/` as `<id>-<state>-<width>-<theme>-<built|prototype>.png`, and look at
  them.

## Step 3: review, in the method's order

Fidelity to the prototype → `ux.md` → the nine heuristics → accessibility beyond contrast → the visual polish pass
(`<ROOT>/reference/ux.md` §3). Every finding: severity, where (`file:line`, or screen and state), what the user experiences,
why it matters, the fix (token, component or words to use). A finding that goes against a recorded decision names the
decision and proposes revisiting it.

## Step 4: the report

Write `<docs>/ux-review-YYYY-MM-DD.html` (the output this command was asked for; say the path) as
`<ROOT>/reference/ux.md` §5 describes: one file, opens from disk, nothing from the network, light and dark with a toggle, no horizontal scroll at 390 px, the project's token block
(`PY SKILL/scripts/build-tokens.py --css-vars`), the screenshots side by side, findings ranked by impact. Follow
Effective HTML's `design-artifact` when that skill is available. If a browser is available, open the report at 390 and
1280 px in both themes and fix what looks wrong.

## Step 5: summary and offers, then stop

Under 150 words: what was reviewed and how (screenshots or code only), counts by severity, the top three findings, the
report path. Then one question: fix now / Slate tickets / nothing now.

- **Fix now:** pick the findings together; a change to what a screen shows or how it behaves → its screen file first
  (`/plumb:prototype` flow: edit, rebuild, the user approves, `--approve`), then the code; words → `vocabulary.md`
  first when they are new; a token or spec change → ask the user to run `/plumb:update`. Then
  `PY SKILL/scripts/audit.py` reports no findings in the files you changed.
- **Slate tickets** (only when `kanban/board.py` exists): grouped by area, written only with `board.py`
  (`python3 kanban/board.py new --help`), each linking the review and the screen (`<docs>/prototype.html#screen-<id>`);
  a ticket that changes a screen starts with "prototype approved". Never edit `kanban/` yourself.
