---
name: status
description: Report the health of the project's design system, read-only - Plumb version (project vs plugin), platforms, home or linked repo and its placement (scaffold.py --verify), stale generated files, audit error, warning and suggestion counts, the checks on or off, the prototype (screens built and to build, approvals pending, screens synced from code to confirm, drift, tours) and what to do next. Use when asked "design status", "is the design system healthy", "what's left to build", or at the start of UI work.
---

# /plumb:status — how healthy is the design system?

**Read-only.** Change nothing: no regeneration, no audit fixes, no approvals, no upgrade. The one exception: when the
placement check offers a move and the user says yes, run that `--relocate` command. Never install or download anything;
if something is missing (Python, git, the home repo of a linked system), report it and ask the user what to do. Commands:
`<ROOT>/reference/scripts.md`.

## Step 0: context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. Find `PLUMB.md` at the project root. Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Role:`, `Platforms:`, `UI packages:`, `Python:` (**PY**, `python3`
   when unset), `## Checks` (`Edit check`, `End-of-turn check`, `Themes`), **docs** (the folder of the
   `## Prototype` `Main:` path, else the tokens file's `$extensions.plumb.docs_dir`, else `docs/design`), `Prototype
   sync`, the last `## Plumb updates` line.

## Gather

```bash
PY "<ROOT>/scripts/version.py" --project . --plugin "<ROOT>" --json
PY "<ROOT>/scripts/scaffold.py" --verify --project-root .
PY SKILL/scripts/build-tokens.py --check
PY SKILL/scripts/audit.py --json
PY SKILL/scripts/build-prototype.py --check        # only when <docs>/prototype/screens/ has screen files
git status --short                                   # skip it when the project is not a git repo
```

- `Role: linked` → check that the `Design system:` path exists (a missing path is the first thing to report, with
  "the home repo is not where PLUMB.md says: clone it there or correct the path"); the audit and generator commands are
  the home skill's.
- From `<docs>/prototype/screens.json` (read it, never write it): screens by `status` (`built`, `to-build`); approval of
  each (approved and current, changed since approval, synced from code, never approved); the routes of `to-build`
  screens. The tours in `<docs>/prototype/tours/`. The newest `<docs>/audit-*.html` and `ux-review-*.html` dates.
- From `audit.py --json`: errors, warnings, suggestions; the prototype-fidelity findings (`screen-drift`,
  `screen-unapproved`, `route-not-prototyped`, `synced-from-code`, `screen-not-built`) by screen; `mode`
  (inconsistency-only means there are no tokens yet).
- Checks: the edit check, the end-of-turn check and prototype sync are each on or off as `PLUMB.md` says (its
  `## Checks` and `## Prototype` lines); report those switches, nothing else.
- A script that exits 2 → report its `error:` and `fix:` lines as a health problem; never fix it here.

## Report (under 200 words)

1. **Version:** project <v> · plugin <v>; `older` → "run `/plumb:upgrade`"; `newer` → "update the plugin" (the commands
   in `<ROOT>/reference/copilot.md`).
2. **System:** the skill path, home or linked, platforms, styling, themes (light and dark, or light-only by decision).
3. **Placement:** `scaffold.py --verify` ok, or each `problem:` line; when it prints a suggested `--relocate` command,
   offer the move (one question: "Move the design system to <TO> and update every reference?"); run it only on yes.
4. **Generated files:** up to date, or the stale ones and "run `PY SKILL/scripts/build-tokens.py`" (`make tokens`).
5. **Audit:** N errors · N warnings · N suggestions, the top rules, the last report's date; errors → `/plumb:audit fix`;
   clean → `/plumb:audit improve`.
6. **Prototype:** N screens (N built, N to build, with routes), approvals pending, synced from code to confirm, drift
   (code changed after approval), routes not prototyped, N tours, and whether the pages are stale
   (`build-prototype.py --check`). Prototype sync on or off.
7. **Checks:** edit check on/off, end-of-turn check on/off (from `PLUMB.md`).
8. **Uncommitted** design files from `git status`, when there are any.
9. **Next:** the one most useful next step (e.g. "approve the booking screen", "build `billing` (to build)",
   "`/plumb:audit fix` for 3 errors", "`/plumb:upgrade`"). Say "healthy" in one word when there is nothing.
