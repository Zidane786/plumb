---
name: create
description: Create a new design system for this project - the product interview first, then platforms and stack, then each design decision with a recommendation (including UX patterns and dark mode), 2-3 directions on one page, then generate the tokens, themes, contrast evidence, skill files and starter components (audit must pass), offer prototypes of the key screens, and record every decision in docs/design/decisions.md.
argument-hint: "[product name]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/*.py*), Bash(python *scripts/*.py*), Bash(py -3 *scripts/*.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git status *)
---

# /plumb:create — from an idea to a design system

Only run when the user typed `/plumb:create` (or `/plumb:init` routed here). Other skills offer it, never run it.

```
placement ─▶ A product ─▶ B platforms ─▶ C decisions (one at a time) ─▶ D directions page ─▶ you pick
   ─▶ E generate (scaffold → tokens → themes → contrast OK → skill files → components → audit exits 0)
   ─▶ G record decisions ─▶ F prototypes of the key screens ─▶ wire in (init step 4) ─▶ summary
```

**Rules.** Questions go through the question tool, **one at a time** (part A may group up to four), options with the
recommendation first marked "(Recommended)", each recommendation following from what the user already said. Every
question, its options and how to derive the recommendation: [reference/interview.md](../../reference/interview.md).
Light **and** dark are designed by default; light-only is an explicit, recorded decision. **Never install or download
anything** (no packages, fonts, icon sets, images); if something seems needed, say so, **ask the user and wait**. Say
where you write before writing.

**Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
`<root>/skills/create`) + `/../..`, resolved to an absolute path. The tokens format:
[reference/tokens-format.md](../../reference/tokens-format.md). Placement: [reference/placement.md](../../reference/placement.md).

## Step 0: placement and Python

- Routed from `/plumb:init`: use its confirmed placement and Python command.
- Run directly: if `PLUMB.md` names a design system that already exists, stop: "This project already has a design
  system. Use `/plumb:update` to change it." Otherwise do `/plumb:init` steps 1–2 first (read `ROOT/skills/init/SKILL.md`):
  the user confirms the "Plumb found … I'll create …" block before anything is written.

## A. The product first

Read `README*`, `AGENTS.md`/`CLAUDE.md`, `SLATE.md`, `docs/`, and any brief, prototype or brand files. Ask A1–A6 from
interview.md (up to four together), with suggestions drawn from them. Summarise in five lines; ask "Right?".

## B. Platforms and stack

Web, iOS (SwiftUI), Android (Compose), multi-select. Confirm the detected framework and styling (Tailwind v4,
Tailwind v3, plain CSS; shadcn when present). React Native is not supported in 1.0.0: offer the others only.

## C. Design decisions

C1–C16 from interview.md, **one question each**, in order: personality and register · density · accent · neutrals ·
semantic colours · label colours · type family and scale · spacing · radius · elevation · motion and reduced motion ·
icons · dark mode · accessibility target (WCAG 2.2 AA by default) · vocabulary and voice · UX patterns (navigation,
page anatomy, forms, feedback, empty/loading/error states, destructive actions, onboarding: one sub-question each).
Show colours as hex with their dark value. Then show every decision on one screen and ask to continue.

## D. Directions

Write 2–3 **distinct, finished-looking** directions to `docs/design/directions.html` (palette, type, components and one
real screen of a key task, each in light and dark). When the Effective HTML skills (`design-artifact`, `html`,
`html-prototype`) are available in this session, follow them; otherwise start from `ROOT/templates/directions.html`
and its rules. Nothing from the network. Give the path; ask: pick one · combine (which parts) · change something.

## E. Generate

1. Write the answers JSON (keys in interview.md) to a temp file outside the repo, including the confirmed placement
   (`ui_packages`, `ui_files`, `allowed_raw`, `web_copies`, `python`, `role`) so `PLUMB.md` records it. Run
   `python3 "<ROOT>/scripts/scaffold.py" --project-root . --name "<Name>" --skill-dir <skill dir> --platforms <list>
   --styling <mode> --answers <file> --docs-dir docs/design --dry-run`, show the list, then run it without `--dry-run`.
2. Add what the scaffold has no key for to the tokens file (warning, info, `label.*`, `md` values, sizes): see
   tokens-format.md. Write `design.md`, `references/ux.md`, `vocabulary.md`, `motion.md`, `accessibility.md` from the
   answers, replacing every "to fill" prompt.
3. `python3 <skill dir>/scripts/build-tokens.py` writes the themes, the copies, the contrast block and
   `docs/design/specimen.html`.
4. **Contrast:** `python3 <skill dir>/scripts/audit.py --json`; for each `contrast` error show the pair, its ratio in
   light or dark and the proposed passing value. Apply only with the user's OK (grouped is fine), rebuild, repeat until
   none is left.
5. **Starter components** (button, input, select, checkbox, card, chip/badge, dialog, sheet, menu, tabs, toast,
   tooltip, empty state, error state, skeleton, page header, app shell): **you write them** in the project's own
   framework from `references/components.md`, using tokens only and the accessible primitives the project already
   has (shadcn/Radix on React, native controls on SwiftUI and Compose). App exists → into the app (e.g.
   `components/ui/`); no app yet → `<skill dir>/assets/platforms/<platform>/starter/`. Never add a dependency: if a
   primitive is missing, ask the user and wait. Update `references/inventory.md`.
6. `python3 <skill dir>/scripts/audit.py` must exit 0 (a "no prototype yet" warning is expected until F); fix and
   re-run. `build-tokens.py --check` exits 0. Give the user the path of `docs/design/specimen.html`.

## G. Record (before F, so the prototype's "Why it looks like this" panels show the decisions)

Append one entry per decision (direction, each C decision, contrast fixes) to `docs/design/decisions.md`, in the
format of `ROOT/templates/decision-entry.md`: id `DS-YYYYMMDD-<slug>` (today's date, a short slug of the decision),
date, **who decided** (`git config user.name`; without git, ask the user's name), the options considered with links
(`directions.html#d2`), the one chosen and why in the user's words, the screens affected (`all` for tokens), the Slate
ticket if any. Append only: never edit or reorder earlier entries. Mirror each entry into `docs/decisions.md` when the
project keeps one, and add a line to `design.md`'s revision notes.

## F. Prototypes of the key screens

Offer: "Prototype the key screens now? Each comes as 2–3 variants to choose from, and the chosen ones become the main
prototype (`docs/design/prototype.html` + `screens.html`)." (a) Yes, the key screens from A4 (Recommended) (b) pick
which (c) later with `/plumb:prototype`. On yes, follow `ROOT/skills/prototype/SKILL.md` for each screen or flow, one
at a time; it records its own decisions.

## Finish

- Routed from init: return to `/plumb:init` step 4. Run directly: do init's step 4 now (each item asked).
- Summary: the design-system folder, `PLUMB.md`, `docs/design/` (directions, specimen, decisions, prototype), the
  audit result, and `git status --short`. Suggest committing.

## Checklist

- [ ] Product questions came before design questions; every question offered a recommendation
- [ ] Directions were distinct and shown in light and dark; the user chose
- [ ] Tokens have a dark value for every colour (or a recorded light-only decision); contrast fixes had the user's OK
- [ ] Components written by you from `components.md`; `audit.py` exits 0; `build-tokens.py --check` exits 0
- [ ] Every decision is in `docs/design/decisions.md` with who decided; nothing was installed or downloaded
