---
name: update
description: Change the project's design system - change or add tokens, components or variants, add a platform later (web, then iOS and Android), improve a part such as motion or dark mode, or apply the latest audit's system suggestions (missing or mergeable tokens, component variants, ux.md or design.md rules screens keep breaking) one at a time with the user's OK - then regenerate every theme, copy and prototype token block, refresh the proposals, record the decision, run the audit and show the diff.
argument-hint: "[what to change]"
disable-model-invocation: true
---

# /plumb:update [what] — change the design system, regenerate, record, audit

Only run when the user typed `/plumb:update` (other skills offer it, never run it). Values live only in the tokens file;
every theme, copy, specimen and prototype token block is regenerated from it. Tokens format:
`<ROOT>/reference/tokens-format.md`. Commands: `<ROOT>/reference/scripts.md`. Prototype rules:
`<ROOT>/reference/prototypes.md`. Audit rules: `<ROOT>/reference/rules.md`.

**Rules.** One question at a time through the question tool, options with the recommendation first; every change is
the user's choice. Say what you will change and where before writing. Never install or download anything (no font
files, icon sets or packages); if something is missing, ask the user and wait. Every colour has a light and a dark value
(unless `Themes: light-only`). Never hand-edit generated files ([G]) or Plumb's own files ([P]); regenerate.

```
 what changes (or the audit's suggestions, one at a time) ─▶ edit tokens / specs / references ─▶ build-tokens.py
   ─▶ contrast ok ─▶ proposals' token blocks ─▶ build-prototype.py ─▶ screens / components follow ─▶ record
   ─▶ audit ─▶ diff ─▶ STOP
```

## Step 0: context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. Find `PLUMB.md` at the project root. Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Role:`, `Python:` (**PY**, `python3` when unset), `Platforms:`,
   `Themes:`, the `## Prototype` paths (**docs**, default `docs/design`). `Role: linked` → the system lives in the home
   repo named by `Design system:`; updates happen there (say so and stop unless the user wants to work there).
4. `PY "<ROOT>/scripts/version.py" --project . --plugin "<ROOT>" --json`: `older` → recommend `/plumb:upgrade` first (the
   user decides).
5. `PY SKILL/scripts/build-tokens.py --check`: stale → say so; the build in step 3 brings it up to date.

## Step 1: what changes

From the argument, or ask (one question): change or add tokens · a component or variant · add a platform · improve a
part (motion, dark mode, type, density, …) · **apply the latest audit's system suggestions** (recommend it when an audit
from the last weeks has any).

**The audit's system suggestions.** Run `PY SKILL/scripts/audit.py --json` and take the findings that change the system:
`missing-token`, `duplicate-tokens`, `unused-token`, `contrast-headroom`, `consolidate-components`, `missing-state`,
`contrast` and `missing-dark-value`; plus the system proposals the agent wrote into the latest
`<docs>/audit-*.review.json` (from `/plumb:audit improve`: a component spec that needs a variant, a `ux.md` or
`design.md` rule that real screens keep breaking for a good reason). Propose them **one at a time**, highest impact
first: what it is, the evidence (`file:line`, how often), options (e.g. "add `color.surface-raised` = #f4f6f8 / dark
#1c2026", "use the existing `color.surface`", "skip"), and your recommendation. Apply what the user approves.

## Step 2: make the change

- **Tokens:** edit only `SKILL/assets/tokens/<project>.tokens.json` (W3C DTCG: light in `$value`, dark in
  `$extensions.plumb.dark`, breakpoints in `md`; references `{group.token}`). New colours get a dark value or an explicit
  `"same-in-dark": true`. Renaming or removing a token used in code: find every use first and change them in the same
  update (ask). Mirror the meaning in `SKILL/design.md` (colour, type, space, motion sections).
- **Components and variants:** update the spec in `SKILL/references/components.md` (purpose, anatomy, sizes, states,
  tokens, accessibility) and `inventory.md`; then write or change the component in the project's own framework from the
  spec (the framework's accessible primitives; only tokens). No app yet → `SKILL/assets/platforms/<platform>/starter/`.
- **Add a platform** (e.g. "web only, now add iOS and Android"): ask which; add it to the tokens file's
  `$extensions.plumb.platforms`; run `PY "<ROOT>/scripts/scaffold.py" --project-root . --name "<name>" --skill-dir
  <SKILL> --platforms <all platforms> --styling <styling> --docs-dir <docs> --dry-run`, show the new files (`wrote:`;
  your files show `skip: … (yours, kept)`), ask, then run it without `--dry-run`: it adds that platform's references and
  never overwrites yours. Update `PLUMB.md`'s `Platforms:` line (ask). Then fill the new references from `design.md` and
  `components.md`, and write the starter components for the platform.
- **Improve a part** (motion, dark mode, density…): read its reference (`motion.md`, `dark-mode.md`, …), propose the
  change with options, then change tokens and the reference together.
- **Rules screens keep breaking** (`ux.md`, `design.md`): show the evidence; options: change the rule, keep it and fix
  the screens, or allow a named exception; edit the file on the user's choice.

## Step 3: regenerate

1. `PY SKILL/scripts/build-tokens.py`: every web theme and copy, the iOS/Android themes, the contrast evidence in
   `dark-mode.md`, `<docs>/specimen.html`, and the token region of `prototype.html`, `screens.html` and `tours/*.html`.
   Exit 2 → fix the token it names.
2. Contrast: `PY SKILL/scripts/audit.py` — any `contrast` or `missing-dark-value` error → show the pair and the nearest
   passing value it suggests, ask, change the token, build again.
3. **Proposals:** in every page under `<docs>/prototype/proposals/` that has a `/* plumb:tokens */ … /* plumb:tokens:end */`
   block, replace the block with the output of `PY SKILL/scripts/build-tokens.py --css-vars` (markers kept), so old
   variants still render. Nothing else in them changes.
4. **Prototype:** `PY SKILL/scripts/build-prototype.py`. A spec or rule change that changes what screens show → update
   those screen files, rebuild, show the user and ask for approval again (`--approve <id>`); built screens then follow
   in code.

## Step 4: record

Append a decision to `<docs>/decisions.md` from `<ROOT>/templates/decision-entry.md` (id `DS-YYYYMMDD-<slug>`, date,
decided by git `user.name`, options considered, chosen, why, `Screens:` affected or `all`, Slate ticket if any); mirror
it into `docs/decisions.md` when the project keeps one; add a line to `SKILL/design.md`'s revision notes. Rebuild the
prototype once more so the decision shows.

## Step 5: check and show, then stop

- `PY SKILL/scripts/build-tokens.py --check` and `PY SKILL/scripts/build-prototype.py --check` exit 0.
- `PY SKILL/scripts/audit.py --html` — exits 0, or list what is left (offer `/plumb:audit fix`).
- `git diff --stat` and one line per changed file; say what needs sign-off (token and theme changes reach every screen).
  The user commits.
