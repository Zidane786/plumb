---
name: tour
description: Write an extra or custom walkthrough for the project's prototype - a client demo, training with your-turn steps, teammate onboarding, a design review or a what's-new tour, across one flow or several - as a tour file the prototype plays in guide mode or play mode, plus a standalone shareable page. Asks who is watching, which steps and which words. Use when asked for a demo, a walkthrough, a guided tour or training of the prototype, or to fix a tour that broke when a screen changed.
argument-hint: "[tour id or flow]"
---

# /plumb:tour [id] — a custom walkthrough of the prototype

`/plumb:prototype` already writes a default walkthrough for every flow it builds. This skill writes the others: a
different audience, a story across several flows, a hands-on lesson. The format, the two modes, pointing and text,
`your_turn`, chapters and the rules for targets: [`tours.md`](../../reference/tours.md). Commands: [`scripts.md`](../../reference/scripts.md).

**Rules.** Questions go **one at a time** through the question tool, options with the recommendation first marked "(Recommended)". **Nothing is
written without the user's OK:** say what you will write and where, and ask; write only on a yes.
Never install or download anything; ask the user and wait. Tours play in light and dark. Never edit `tours/*.html` or `prototype.html`:
`build-prototype.py` writes them.

**Pages.** Tour pages use Plumb's own walkthrough player (built by `build-prototype.py`). If you write any other HTML
for a tour (a screen hook it needs, a standalone intro page the user asked for), follow Effective HTML's
`design-artifact` when that skill is available in this session (optional; never install it), otherwise Plumb's built-in
quality bar in [prototypes.md](../../reference/prototypes.md#the-quality-bar-effective-html) "The quality bar".

```
 audience + purpose ─▶ screens, states, chapters ─▶ draft steps (table) ─▶ user OKs ─▶ write tours/<id>.json
   ─▶ build-prototype.py (targets checked) ─▶ show both links ─▶ changes? ─▶ STOP
```

## Step 0: context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. Find `PLUMB.md` at the project root. Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Python:` (**PY**, `python3` when unset).
   **docs** (the docs folder): the tokens file's `$extensions.plumb.docs_dir`, default `docs/design`, which is
   where the scripts write. If `PLUMB.md`'s `## Prototype` `Main:` path sits in another folder, say so and ask
   the user which is right, then fix the other one after their OK (`<ROOT>/reference/scripts.md`, "The docs folder").
4. No screen files in `<docs>/prototype/screens/` → nothing to tour yet: offer `/plumb:prototype` and stop.
5. Read `<docs>/prototype/screens.json` (screens, their states) and the existing tours in `<docs>/prototype/tours/`.
   An id was given and that tour exists → show its steps as a table and ask what to change (skip to step 3).

## Step 1: who is watching, and why

Ask, one at a time:

1. **Audience:** a client or stakeholder demo (`client`, opens in play mode) · training for users (`training`, guide
   mode, with your-turn steps) · a design review (`review`) · teammate onboarding (`team`) · what's new (`whats-new`,
   play mode). Recommend from what the user said.
2. **Purpose:** one sentence: what they should take away.
3. **Scope:** which flows, screens and states (list them from `screens.json`), across one flow or several; which
   non-happy states are worth showing (an error, an empty state).
4. Only when it matters: pacing (default speed, steps that need a longer hold), chapters (named parts of the story),
   the intro and closing cards ("what you'll see", "what to try next"), and which steps are `your_turn` (training: the
   learner does it on the real control; a wrong click gets the `hint`).

## Step 2: draft the steps

Show a short table, one row per step: chapter · screen/state · target (what is pointed at) · title and caption ·
pointer (spotlight, ring, arrow, beacon, zoom, cursor; labels, callout, note) · action (click, type, choose, wait) ·
your turn. Captions in the product's words (`SKILL/references/vocabulary.md`) and the audience's tone, one sentence
each; one pointer per step plus at most a callout or a set of labels. Ask: "Write this tour to
`<docs>/prototype/tours/<id>.json`?" — Write it / Change steps.

Every target must exist in that screen file's markup (it may be hidden in its state). Prefer the hooks the screen
already has (`[data-test=…]`, a class). If a step needs an element the screen file lacks, say so: adding a hook changes
the screen file, which makes its approval stale, so ask before touching it and ask for the approval again afterwards
(`build-prototype.py --approve <id>`).

## Step 3: write and build

- Write `<docs>/prototype/tours/<id>.json` (`<id>`: letters, digits, `_`, `-`; not `<another tour>-<n>`). The "Write it"
  answer in step 2 is the OK, so name this path in that question.
- `PY SKILL/scripts/build-prototype.py`. Exit 2 names the tour file, the line and the problem (an unknown screen or
  state, a selector that matches nothing, a bad field): fix the step and run it again until it exits 0.
- `PY SKILL/scripts/build-prototype.py --check` exits 0.

## Step 4: show it, then stop

- In the prototype: `<docs>/prototype.html#tour-<id>` (step n: `#tour-<id>-<n>`). Guide mode: Next/Back or the arrow
  keys, Esc to leave. Play mode: Space pauses, a marker per chapter, speed 0.5×–2×.
- The shareable page: `<docs>/tours/<id>.html`, one file with the whole prototype and this tour, opening straight into
  it; it opens from disk with no network, so it can be emailed or put in training material.
- If a browser is available (the agent's browser tool, else `PY "<ROOT>/scripts/screenshot.py"
  "<docs>/prototype.html#tour-<id>" --out …`), check the first steps render in light and dark.
- Ask: "Anything to change?" Iterate on the file, rebuild, show again. Done → stop. The user commits.

**A tour that broke** (a screen changed and `build-prototype.py` exits 2 on it): show the failing step and what changed
in the screen, propose the new selector, state or words, and fix the tour file. Approvals and `--map` still work while a
tour is broken (they warn and exit 0), but the pages are not rebuilt until it is fixed.
