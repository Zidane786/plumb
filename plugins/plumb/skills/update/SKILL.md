---
name: update
description: Change the project's design system - change or add tokens, components or variants, add a platform later (web, then iOS and Android), improve a part such as motion or dark mode, or apply the latest audit's system suggestions (missing or mergeable tokens, component variants, ux.md or design.md rules screens keep breaking) one at a time with the user's OK - then regenerate every theme, copy, prototype and proposal token block, record the decision, run the audit and show the diff.
argument-hint: "[what to change]"
disable-model-invocation: true
---

# /plumb:update [what] — change the design system, regenerate, record, audit

Only run when the user typed `/plumb:update` (other skills offer it, never run it); these instructions are already
loaded, so don't load this skill again with a skill tool. Values live only in the tokens file;
every theme, copy, specimen, prototype and proposal token block is regenerated from it. Tokens format:
[`tokens-format.md`](../../reference/tokens-format.md). Commands: [`scripts.md`](../../reference/scripts.md). Prototype rules:
[`prototypes.md`](../../reference/prototypes.md). Audit rules and the agent review: [`rules.md`](../../reference/rules.md).

**Rules.** Questions go **one at a time** through the question tool, options with the recommendation first marked "(Recommended)"; every change is
the user's choice. **Nothing is written without the user's OK:** before each edit, show exactly what changes and where,
and ask. Never install or download anything (no font files, icon sets or packages); if something is missing,
ask the user and wait. Every colour has a light and a dark value (unless `Themes: light-only`). Never hand-edit generated files
([G]) or Plumb's own files ([P]); regenerate. `audit.py`: **exit 1 means errors found, not a crash** (your tool may
show it as a failed command); read the findings.
**Scripts give evidence, not answers:** check each script result against the code (search and read any time),
correct or add to it (marked `(corrected: <why>)` / `(added: <why>)`) and show that inside the question before the
user decides; a script that is wrong in a way that will recur → say so and suggest the fix to Plumb
([interview.md](../../reference/interview.md), "Scripts give evidence, not answers").
When a Plumb script or hook is wrong and you correct it, record the Plumb mistake with /plumb:feedback. **What the user
confirms goes inside the question** (its text, or the recommended option's preview when the tool has one), never only in
a message before it: Claude Code can hide that text; Copilot CLI's ask tool takes it in the question text.

```
 what changes (or the audit's system suggestions, one at a time) ─▶ show before → after ─▶ ask ─▶ edit
   ─▶ build-tokens.py ─▶ contrast ok ─▶ build-prototype.py (main + proposals) ─▶ screens / components follow
   ─▶ record ─▶ audit ─▶ diff ─▶ STOP
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
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Role:`, `Python:` (**PY**, `python3` when unset), `Platforms:`,
   `Themes:`. **docs** (the docs folder): the tokens file's `$extensions.plumb.docs_dir`, default `docs/design`, which
   is where the scripts write. If `PLUMB.md`'s `## Prototype` `Main:` path sits in another folder, say so and ask the
   user which is right, then fix the other one after their OK (`<ROOT>/reference/scripts.md`, "The docs folder").
   `Role: linked` → the system lives in the home repo named by `Design system:`; updates happen there (say so and stop
   unless the user wants to work there).
4. `PY "<ROOT>/scripts/version.py" --project "<root>" --plugin "<ROOT>" --json`: `older` → recommend `/plumb:upgrade` first
   (the user decides; adding a platform requires it, step 2).
5. `PY SKILL/scripts/build-tokens.py --check`: stale → say so; the build in step 3 brings it up to date.

## Step 1: what changes

From the argument, or ask (one question): change or add tokens · a component or variant · add a platform · improve a
part (motion, dark mode, type, density, …) · **apply the latest audit's system suggestions** (recommend it when an audit
from the last weeks has any) · where Plumb looks (`PLUMB.md`'s `UI files:`, `Routes:`, `Allowed raw values:`; count
the files each pattern matches; each route root exists, recorded as `<path> (<kind>)` from the framework found
([interview.md](../../reference/interview.md) "What gets recorded"); evidence inside the question) · a tokens setting
(`web.theme_switch`, `motion.reduced`, `web.reset_palette`: turn the palette reset on once the app no longer uses
Tailwind's default colour classes).

**The audit's system suggestions** are exactly these two sources:

1. `PY SKILL/scripts/audit.py --json`: the findings of the rules that change the system: `missing-token`,
   `duplicate-tokens`, `unused-token`, `contrast-headroom`, `consolidate-components`, `missing-state`, `contrast` and
   `missing-dark-value`.
2. The latest `<docs>/audit-*.review.json` (the agent review of `/plumb:audit`): the **system proposals**, i.e. the
   entries whose `file` is a path under SKILL: the tokens file (`SKILL/assets/tokens/…`),
   `SKILL/references/components.md`, `SKILL/references/ux.md` or `SKILL/design.md`. Other entries are about screens and
   code, not the system: leave them to `/plumb:audit`.

Propose them **one at a time**, highest impact first: what it is, the evidence (`file:line`, how often), options (e.g.
"add `color.surface-raised` = #f4f6f8 / dark #1c2026", "use the existing `color.surface`", "skip"), and your
recommendation. Apply what the user approves (step 2).

## Step 2: make the change (show, ask, then write)

- **Tokens:** show every token that changes as **before → after, in light and in dark** (and `md` when it has one),
  e.g. `color.primary: #1f7a8c → #1a6f80 (light) · #4fb3c4 → #5cc0d1 (dark)`; for a new token, its name, both values and
  where it will be used. Ask; on yes edit only `SKILL/assets/tokens/<project>.tokens.json` (W3C DTCG: light in `$value`,
  dark in `$extensions.plumb.dark`, breakpoints in `md`; references `{group.token}`). New colours get a dark value or an
  explicit `"same-in-dark": true`. Renaming or removing a token used in code: list every use first; changing them is
  part of the same yes. Then show and ask for the matching lines in `SKILL/design.md`.
- **Components and variants:** show the spec change for `SKILL/references/components.md` (purpose, anatomy, sizes,
  states, tokens, accessibility) and the `inventory.md` line; ask; then write. Then propose the component change in the
  project's own framework (the framework's accessible primitives; only tokens), ask, write. No app yet →
  `SKILL/assets/platforms/<platform>/starter/`.
- **Add a platform** (e.g. "web only, now add iOS and Android"): **when version.py said `older`, require
  `/plumb:upgrade` first** (a new platform needs the current scaffold and generator; adding it on old files gives a
  partial upgrade) and stop until the user has run it; only if the user explicitly declines, continue and say plainly in
  the dry-run review that Plumb's files will also be refreshed to the plugin's version. Ask which platforms; show and
  ask for the tokens file's `$extensions.plumb.platforms` change; run `PY "<ROOT>/scripts/scaffold.py" --project-root "<root>"
  --name "<name>" --skill-dir <SKILL> --platforms <all platforms> --styling <styling> --docs-dir <docs> --dry-run`, put
  the full list inside the question (`would write:`; your files show `skip: … (yours, kept)`), **STOP: ask, wait for the
  answer**, then, in a new shell call, the same command without `--dry-run` plus `--confirm <token>` exactly as the
  dry run printed it: it adds that platform's references and never overwrites yours. Ask before updating `PLUMB.md`'s
  `Platforms:` line (and `Routes:`: `none` for a mobile-only app, or as interview.md "What gets recorded"). Then fill
  the new references from `design.md` and `components.md` and write the platform's starter components, each shown and
  asked first.
- **Improve a part** (motion, dark mode, density…): read its reference (`motion.md`, `dark-mode.md`, …), propose the
  change with options, show the token and reference edits, ask, then write them together.
- **Rules screens keep breaking** (`ux.md`, `design.md`): show the evidence; options: change the rule, keep it and fix
  the screens, or allow a named exception; show the exact edit and write it on the user's choice.

## Step 3: regenerate

1. `PY SKILL/scripts/build-tokens.py`: every web theme and copy, the iOS/Android themes, the contrast evidence in
   `dark-mode.md`, `<docs>/specimen.html`, and the token region of `prototype.html`, `app.html`, `screens.html`, `tours/*.html` and
   every proposal page built by `build-prototype.py --proposal`. Exit 2 → fix the token it names (ask first).
2. Contrast: `PY SKILL/scripts/audit.py` — any `contrast` or `missing-dark-value` error → show the pair and the nearest
   passing value it suggests, ask, change the token, build again.
3. **Prototype and proposals:** `PY SKILL/scripts/build-prototype.py` rebuilds the main pages and refreshes the token
   block of every proposal (`<docs>/prototype/proposals/*/`), so old variants still render; their screen files are never
   touched. A proposal folder whose pages were written by hand (before `--proposal` existed) is not refreshed: when its
   variants have `screens/` folders, offer `PY SKILL/scripts/build-prototype.py --proposal <name>`, saying that it
   **replaces** the hand-written `index.html` and each variant's `prototype.html`, `app.html` and `screens.html` in that folder
   with generated ones (the screen files stay); run it only on a yes.
4. A spec or rule change that changes what screens show → propose the screen-file edits, ask, edit, rebuild, show the
   user and ask for approval again (`--approve <id>`); built screens then follow in code.
   **Never run `--approve` (or record an approval) without the user's explicit yes to that screen.**

## Step 4: record (show, ask, then write)

A decision in `<docs>/decisions.md` from `<ROOT>/templates/decision-entry.md` (id `DS-YYYYMMDD-<slug>`, date, decided by
git `user.name`, options considered, chosen, why, `Screens:` affected or `all`, Slate ticket if any); mirrored into
`docs/decisions.md` when the project keeps one; a line in `SKILL/design.md`'s revision notes. Rebuild the prototype once
more so the decision shows.

## Step 5: check and show, then stop

- `PY SKILL/scripts/build-tokens.py --check` and `PY SKILL/scripts/build-prototype.py --check` exit 0.
- `PY SKILL/scripts/audit.py --html` — exits 0, or list what is left (offer `/plumb:audit fix`).
- `git diff --stat` and one line per changed file; say what needs sign-off (token and theme changes reach every screen).
  The user commits.
