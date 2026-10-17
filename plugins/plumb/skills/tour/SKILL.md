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
**Scripts give evidence, not answers:** check each script result against the code (search and read any time),
correct or add to it (marked `(corrected: <why>)` / `(added: <why>)`) and show that inside the question before the
user decides; a script that is wrong in a way that will recur → say so and suggest the fix to Plumb
([interview.md](../../reference/interview.md), "Scripts give evidence, not answers").
When a Plumb script or hook is wrong and you correct it, record the Plumb mistake with /plumb:feedback. **What the user
confirms goes inside the question** (its text, or the recommended option's preview when the tool has one), never only in
a message before it: Claude Code can hide that text; Copilot CLI's ask tool takes it in the question text.

**Pages.** Tour pages use Plumb's own walkthrough player (built by `build-prototype.py`). If you write any other HTML
for a tour (a screen hook it needs, a standalone intro page the user asked for), follow Effective HTML's
`design-artifact` when that skill is available in this session (optional; never install it), otherwise Plumb's built-in
quality bar in [prototypes.md](../../reference/prototypes.md) "The quality bar". **The project's design system
outranks Effective HTML:** its tokens, `design.md` and references decide palette, type, spacing, radius and motion;
Effective HTML guides craft only (content, states, interactions, accessibility, polish), and where they disagree the
system wins.

```
 audience + where it plays + purpose ─▶ screens, states, chapters ─▶ draft steps (table) ─▶ user OKs ─▶ write tours/<id>.json
   ─▶ build-prototype.py (targets checked) ─▶ --check-tour + check-tour.py (browser) ─▶ show both links ─▶ changes? ─▶ STOP
```

## Step 0: context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute. Check that `<ROOT>/reference/scripts.md`
   exists; if not, resolve again, never guess. Read Plumb's references only as `<ROOT>/reference/<file>`.
2. **Project root `<root>`:** the absolute path of the folder holding `PLUMB.md` (the folder the session opened in,
   else the nearest folder above it). Every path below is `<root>/…`; **SKILL** (step 3) is `<root>/<Design system:>`,
   made absolute; read the project's references as `SKILL/references/<file>`, never from a path you remember.
   Scratch files: `<root>/.plumb-tmp/` only (its `.gitignore` first); clean up your own files when the command
   ends; never write `setup-in-progress` (the setup marker); never `/tmp` or outside `<root>`.
   Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
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
2. **Where should it play?** *Full-window app (Recommended)* (`"view": "app"`, the default: the screens full window
   with the player on top, for a demo or training) · *Prototype page (with the screens list and the decisions rail, for
   a design review)* (`"view": "prototype"`). Record the answer as `"view"` in the tour file
   ([tours.md](../../reference/tours.md), "Where it plays").
3. **Purpose:** one sentence: what they should take away.
4. **Scope:** which flows, screens and states (list them from `screens.json`), across one flow or several; which
   non-happy states are worth showing (an error, an empty state).
5. Only when it matters: pacing (default speed, steps that need a longer hold), chapters (named parts of the story),
   the intro and closing cards ("what you'll see", "what to try next"), and which steps are `your_turn` (training: the
   learner does it on the real control; a wrong click gets the `hint`).

## Step 2: draft the steps

Show a short table, one row per step: chapter · screen/state · target (what is pointed at) · title and caption ·
pointer (spotlight, ring, arrow, beacon, zoom, cursor; labels, callout, note) · action (click, type, choose, wait) ·
your turn. Captions in the product's words (`SKILL/references/vocabulary.md`) and the audience's tone, one sentence
each; one pointer per step plus at most a callout or a set of labels. Ask: "Write this tour (it plays in <the
full-window app | the prototype page>) to `<docs>/prototype/tours/<id>.json`?" — Write it / Change steps.

Every target must exist in that screen file's markup (it may be hidden in its state). Prefer the hooks the screen
already has (`[data-test=…]`, a class). If a step needs an element the screen file lacks, say so: adding a hook changes
the screen file, which makes its approval stale, so ask before touching it and ask for the approval again afterwards
(`build-prototype.py --approve <id>`). **Never run `--approve` (or record an approval) without the
user's explicit yes to that screen** in this conversation.

## Step 3: write and build

- Write `<docs>/prototype/tours/<id>.json` (`<id>`: letters, digits, `_`, `-`; not `<another tour>-<n>`). The "Write it"
  answer in step 2 is the OK, so name this path in that question.
- `PY SKILL/scripts/build-prototype.py`. Exit 2 names the tour file, the line and the problem (an unknown screen or
  state, a selector that matches nothing, a bad field): fix the step and run it again until it exits 0.
- `PY SKILL/scripts/build-prototype.py --check` exits 0.
- `PY SKILL/scripts/build-prototype.py --check-tour <docs>/prototype/tours/<id>.json`: a `warning:` names a step whose
  element the screen's CSS shows only at some frame widths ("visible only when the frame is ≥ 48rem"). Fix the ones
  that matter for where the tour plays (another target, or the app view), or tell the user why it is fine.
- Then the browser pass: `PY "<ROOT>/scripts/check-tour.py" "<docs>/tours/<id>.html"` (both modes at 1280 and 1440).
  Exit 2 lists `step <n> (<title>): <problem> at <width> (<mode>)` lines: fix those steps (target, state, words) and
  rebuild until it exits 0. Exit 3 (no browser): say so, and ask whether to continue without the browser check.
  Exit 1 (the browser gave no result or hung): show the error and its fix, and ask: another installed browser with
  `--browser PATH`, or continue without the browser check. Never report the tour as checked then.

## Step 4: show it, then stop

- Show both links:
  - **the tour page** `<docs>/tours/<id>.html`: one file with every screen and this tour, opening straight into it in the
    view chosen (the full-window app, or the prototype page); it opens from disk with no network, so it can be emailed
    or put in training material;
  - **in the prototype** `<docs>/prototype.html#tour-<id>` (step n: `#tour-<id>-<n>`), whatever the view.
  Guide mode: Next/Back or the arrow keys, Esc to leave. Play mode: Space pauses, a marker per chapter, speed 0.5×–2×,
  Voice (or `V`, the browser's own speech; a step's optional `"say"`) and "Save subtitles (.vtt)" ([tours.md](../../reference/tours.md), "Voice and subtitles").
- If a browser is available (the agent's browser tool, else `PY "<ROOT>/scripts/screenshot.py"
  "<docs>/tours/<id>.html" --out …`), check the first steps render in light and dark.
- Ask: "Anything to change?" Iterate on the file, rebuild, show again. Done → stop. The user commits.

**A tour that broke** (a screen changed and `build-prototype.py` exits 2 on it): show the failing step and what changed
in the screen, propose the new selector, state or words, and fix the tour file. Approvals and `--map` still work while a
tour is broken (they warn and exit 0), but the pages are not rebuilt until it is fixed.
