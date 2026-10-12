---
name: prototype
description: Prototype first - before building or changing a screen, tab, flow or interaction, make 2-3 variants on the project's design system (each as a clickable prototype and an every-state screens view, light and dark), let the user pick, write the chosen one into the main prototype with its default walkthrough, record the user's approval and the decision. The approved screen is the reference to build. Also updates an existing screen's prototype after its code changed. Use when asked to "prototype X", design a new screen or flow, change what a screen shows, or when the edit check says a screen has no approved prototype.
argument-hint: "<screen | flow | interaction>"
---

# /plumb:prototype <screen | flow | interaction> — prototype first, then build

The main prototype (`<docs>/prototype.html` + `screens.html`, built from one file per screen) is the reference every
screen is built from. This skill adds or changes screens in it, with the user choosing and approving. Screen file
contract, variants, approvals and the quality bar: `<ROOT>/reference/prototypes.md`. Tours: `<ROOT>/reference/tours.md`.
Every command: `<ROOT>/reference/scripts.md`.

**Rules.** Ask one question at a time through the question tool, with options and the recommendation first. Say where
you will write before writing. Never install or download anything (no package, font, icon set, image or tool); if
something seems missing, ask the user and wait for their decision. Both themes, unless `PLUMB.md` says
`Themes: light-only`. Never edit `prototype.html`, `screens.html`, `screens.json` or `tours/*.html`: `build-prototype.py`
writes them. Never run `--approve` without the user's yes to that screen in this conversation.

```
 brief ─▶ 2–3 variants (both views each) ─▶ user picks ─▶ write to main + default tour ─▶ build
   ─▶ user approves ─▶ --approve ─▶ record decision ─▶ (map when built) ─▶ STOP: build it to match
```

## Step 0: context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. Find `PLUMB.md` at the project root. Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Python:` (**PY**, `python3` when unset), `Themes:`, the `## Prototype`
   paths (**docs** is the folder holding `prototype.html`, default `docs/design`), `Platforms:`. `Role: linked` → the
   prototype lives in the home repo named by `Design system:`; say so and work there only if the user agrees.
4. `PY "<ROOT>/scripts/version.py" --project . --plugin "<ROOT>" --json`: `older` → say once "Plumb <plugin> is
   available for this project (on <project>): run `/plumb:upgrade` when ready." and continue; never run it yourself.
5. No tokens file yet in `SKILL/assets/tokens/` → the design system comes first: offer `/plumb:create` or
   `/plumb:extract` and stop.

## Step 1: brief

- Read `SKILL/references/ux.md` (users, key tasks, navigation, page anatomy, forms, states, voice), `components.md`,
  `inventory.md`, `vocabulary.md`, `design.md`, the decisions in `<docs>/decisions.md`, `screens.json` and the screen
  files around this one. In an existing app, also read the current screens and components it should sit beside.
- Settle, one question at a time (skip what the request already says): what the screen or flow is for and which key
  task; the states that matter (from `ux.md`'s `### States per screen` and the task: loading, empty, error, success,
  long text, zero, offline…); which platforms (from `Platforms:`).
- Decide the kind of change:
  - **A small fix** that changes neither what a screen shows nor how it behaves (logic bug, typo, data wiring): no
    prototype step. Say so and stop.
  - **A change to an existing screen:** ask "One updated version, or 2–3 variants?" (recommend one version for a small
    visible change, variants when the layout or flow changes).
  - **New screens, a new flow or a new interaction:** variants (recommended), or one version if the user prefers.
- **Code already changed** (the end-of-turn check stopped, or the audit reported `screen-drift`): update the screen file
  to show what the code now does (step 4), show it, then ask "Approve this as the screen?" (→ `--approve`) or "Mark it
  synced from code for later review?" (→ `--synced`).

## Step 2: variants (both views each)

- Name the proposal (`<name>`, e.g. `billing`) and say where it goes: `<docs>/prototype/proposals/<name>/`.
- Make 2–3 variants that differ in **UX** (layout, flow, density, navigation), all on the same design system. If the
  `html-prototype` and `design-artifact` skills are available in this session, follow them; otherwise follow the quality
  bar in `reference/prototypes.md` (real content, every state, working interactions, keyboard and focus, both themes,
  reduced motion, no generic look). Each variant must be a distinct, finished-looking option.
- For each variant write its screen files (`<variant>/screens/<id>.html`, the contract in `reference/prototypes.md`) and
  **both views**: `<variant>/prototype.html` (clickable, state switcher, phone/desktop and light/dark toggles) and
  `<variant>/screens.html` (every screen × every state, light and dark side by side). Inline the token block from
  `PY SKILL/scripts/build-tokens.py --css-vars` between `/* plumb:tokens */` and `/* plumb:tokens:end */`. Mobile
  platforms sit in a phone frame with that platform's conventions.
- `<docs>/prototype/proposals/<name>/index.html`: the variants side by side, each with its idea, trade-offs and links to
  both views, light and dark.
- Check: `PY SKILL/scripts/audit.py <docs>/prototype/proposals/<name>/<variant>/screens` exits 0 for each variant (only
  tokens; fix what it reports; the pages themselves carry the raw token block, so audit the screen files). With
  a browser (the agent's browser tool, else `PY "<ROOT>/scripts/screenshot.py" … --theme dark`), look at each variant
  at 390 and 1280 px in both themes and fix what looks wrong.

## Step 3: choose

Tell the user to open `<docs>/prototype/proposals/<name>/index.html`, then ask: "Which variant?" with options A, B, C
(recommend one and say why, from the key task) and "Combine or change something". Iterate until they pick one.

## Step 4: write to main, with the default walkthrough

- Copy the chosen screen files to `<docs>/prototype/screens/<id>.html` (or edit the existing screen file). Link new
  screens from the screens that lead to them (`<a href="#screen-<id>">` or `plumb.go`). The other variants stay in
  `proposals/<name>/` as the record.
- **Default walkthrough:** write or update `<docs>/prototype/tours/<flow>.json` for each flow this builds or changes:
  the happy path, one step per meaningful screen or action, plus the most important non-happy state;
  `"audience": "review"`; captions in the product's words; every target present in the screen file's markup
  (`reference/tours.md`).
- `PY SKILL/scripts/build-prototype.py`. Exit 2 → fix what it names (a screen file, a tour step) and run it again.
  `PY SKILL/scripts/audit.py <docs>/prototype/screens` exits 0.
- Show the user `<docs>/prototype.html#screen-<id>` (each new or changed screen), `<docs>/screens.html` (every state, both
  themes) and the walkthrough (`prototype.html#tour-<flow>`, or the standalone `<docs>/tours/<flow>.html`). Ask, per
  screen: "Approve <screen> as the reference to build?" — Approve (recommended when they are happy) / Change something.
  Changes → edit the screen file or tour, rebuild, ask again.
- On each yes: `PY SKILL/scripts/build-prototype.py --approve <id>`.

## Step 5: record

- Append a decision to `<docs>/decisions.md` from `<ROOT>/templates/decision-entry.md`: id `DS-YYYYMMDD-<slug>`, date,
  `Decided by:` (git `user.name`), the options considered with a link to `prototype/proposals/<name>/index.html`, the
  one chosen and why (the user's words), `Screens:` the screen ids, the Slate ticket if any. Mirror it into
  `docs/decisions.md` when the project keeps one; add a line to `SKILL/design.md`'s revision notes.
- New component the screen needs → list it in `SKILL/references/inventory.md` (still to build) and spec it in
  `components.md` if it is new to the system.
- Route and source files already known (an existing screen, or agreed now)? Confirm them with the user, then
  `PY SKILL/scripts/build-prototype.py --map <id> --route <route> --files <globs>`. A new screen stays "to build" until
  its route exists.
- `PY SKILL/scripts/build-prototype.py` once more so the decision shows on the screen.

## Step 6: the reference to build, then stop

Say: "<screen> is approved: build it to match `<docs>/prototype.html#screen-<id>` (every state, both themes, the words
in the screen file)." Offer, one question: build it now / a Slate ticket (when `kanban/board.py` exists: written only
with `board.py`; its first acceptance item is "prototype approved" and "done when" links the screen) / later. When the
screen is built: `--map` it (route and files) and run `PY SKILL/scripts/audit.py` until it exits 0.
