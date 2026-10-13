---
name: status
description: Report the health of the project's design system, read-only - Plumb version (project vs plugin), platforms, home or linked repo and its placement (scaffold.py --verify), stale generated files, audit error, warning and suggestion counts, the checks on or off, the prototype (screens built and to build, approvals pending, screens synced from code to confirm, drift, tours) and what to do next. Use when asked "design status", "is the design system healthy", "what's left to build", or at the start of UI work.
---

# /plumb:status — how healthy is the design system?

**Read-only.** Change nothing: no regeneration, no audit fixes, no approvals, no upgrade. The one exception: when the
placement check offers a move and the user says yes, run that `--relocate` command. Never install or download anything;
if something is missing (Python, git, the home repo of a linked system), report it, ask the user and wait.
Commands: [`scripts.md`](../../reference/scripts.md).
**Scripts give evidence, not answers:** check each script result against the code (search and read any time),
correct or add to it (marked `(corrected: <why>)` / `(added: <why>)`) and show that inside the question before the
user decides; a script that is wrong in a way that will recur → say so and suggest the fix to Plumb
([interview.md](../../reference/interview.md), "Scripts give evidence, not answers").
When a Plumb script or hook is wrong and you correct it, record the Plumb mistake with /plumb:feedback. **What the user
confirms goes inside the question** (its text, or the recommended option's preview when the tool has one), never only in
a message before it: Claude Code can hide that text; Copilot CLI's ask tool takes it in the question text.

## Step 0: context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute. Check that `<ROOT>/reference/scripts.md`
   exists; if not, resolve again, never guess. Read Plumb's references only as `<ROOT>/reference/<file>`.
2. **Project root `<root>`:** the absolute path of the folder holding `PLUMB.md` (the folder the session opened in,
   else the nearest folder above it). Every path below is `<root>/…`; **SKILL** (step 3) is `<root>/<Design system:>`,
   made absolute; read the project's references as `SKILL/references/<file>`, never from a path you remember.
   **Status writes no file at all**, not even a scratch file (no `/tmp`, no `.plumb-tmp/`, nothing next to the repo);
   it writes nothing itself: recording a Plumb mistake goes through /plumb:feedback (its own skill, outside the project).
   Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Role:`, `Platforms:`, `UI packages:`, `Python:` (**PY**, `python3`
   when unset), `## Checks` (`Edit check`, `End-of-turn check`, `Themes`), `Prototype sync`, the last
   `## Plumb updates` line. **docs**: the tokens file's `$extensions.plumb.docs_dir` (default `docs/design`), where the
   scripts write. If `PLUMB.md`'s `## Prototype` `Main:` path sits in another folder, report it as a health problem and
   the question to settle ("which is right?"); status changes nothing.

## Gather

```bash
PY "<ROOT>/scripts/version.py" --project "<root>" --plugin "<ROOT>" --json
PY "<ROOT>/scripts/scaffold.py" --verify --project-root "<root>"
PY "SKILL/scripts/build-tokens.py" --check
PY "SKILL/scripts/audit.py"
PY "SKILL/scripts/build-prototype.py" --check      # only when <docs>/prototype/screens/ has screen files
git -C "<root>" status --short                      # skip it when the project is not a git repo
```

Run them in **one shell call** (`;` between them, so each still runs): Copilot CLI then asks once (one prompt for
status). `audit.py`: **exit 1 means errors found, not a crash** (Claude Code shows "Error: Exit code 1", Copilot CLI
"✗ Shell"); report the counts, never as a failure of status. Read each output directly; when the audit's output is too
long for your tool, read its last lines (the summary counts) and the rule names; **never save output to a file** to
read it later. Check what the scripts say against the files before you report it (a burst of one rule usually means a
setup gap: say so). `<root>/.plumb-tmp/setup-in-progress` exists → a setup is running or stopped midway; the
end-of-turn check is off while the marker is under 6 hours old: report it ("resume with `/plumb:init`, or delete
`.plumb-tmp/`"). Older than 6 hours → "a setup marker from <time> is stale — finish /plumb:init or remove .plumb-tmp/"
(the end-of-turn check runs again).

- `Role: linked` → check that the `Design system:` path exists (a missing path is the first thing to report, with
  "the home repo is not where PLUMB.md says: clone it there or correct the path"); the audit and generator commands are
  the home skill's.
- From `<docs>/prototype/screens.json` (read it, never write it): screens by `status` (`built`, `to-build`); approval of
  each (approved and current, changed since approval, synced from code, never approved); the routes of `to-build`
  screens. The tours in `<docs>/prototype/tours/`. The newest `<docs>/audit-*.html` and `ux-review-*.html` dates.
- From the audit's output: errors, warnings, suggestions; the prototype-fidelity findings (`screen-drift`,
  `screen-unapproved`, `route-not-prototyped`, `synced-from-code`, `screen-not-built`) by screen; inconsistency-only
  mode means there are no tokens yet.
- `PLUMB.md` has no `Routes:` line → the prototype-first check and `route-not-prototyped` cannot see the app's pages:
  report it with "run `/plumb:init` to record the route roots". A `--verify` problem that the skill folder, `PLUMB.md`
  or the docs folder is git-ignored → report it first (teammates would get nothing) with "`/plumb:init` asks how to fix
  it".
- Checks: the edit check, the end-of-turn check and prototype sync are each on or off as `PLUMB.md` says (its
  `## Checks` and `## Prototype` lines); report those switches, nothing else.
- A script that exits 2 → report its `error:` and `fix:` lines as a health problem; never fix it here.

## Report (under 200 words)

1. **Version:** project <v> · plugin <v>; `older` → "run `/plumb:upgrade`"; `newer` → "update the plugin" (the commands
   in [`copilot.md`](../../reference/copilot.md)).
2. **System:** the skill path, home or linked, platforms, styling, themes (light and dark, or light-only by decision).
3. **Placement:** `scaffold.py --verify` ok, or each `problem:` line; when it prints a suggested `--relocate` command,
   offer the move (one question: "Move the design system to <TO> and update every reference?"); run it only on yes.
4. **Generated files:** up to date, or the stale ones and the tokens command from `PLUMB.md` → Commands.
5. **Audit:** N errors · N warnings · N suggestions, the top rules, the last report's date; errors → `/plumb:audit fix`;
   clean → `/plumb:audit improve`.
6. **Prototype:** N screens (N built, N to build, with routes), approvals pending, synced from code to confirm, drift
   (code changed after approval), routes not prototyped, N tours, and whether the pages are stale
   (`build-prototype.py --check`). Prototype sync on or off.
7. **Checks:** edit check on/off, end-of-turn check on/off (from `PLUMB.md`).
   **Effective HTML:** "available in this session" when its skills (`design-artifact`, `html-prototype`, `html`) are
   listed in this session, else "not available — using Plumb's built-in quality bar" (optional; never install it;
   [prototypes.md](../../reference/prototypes.md)).
8. **Uncommitted** design files from `git status`, when there are any.
9. **Next:** the one most useful next step (e.g. "approve the booking screen", "build `billing` (to build)",
   "`/plumb:prototype <screen>`", "`/plumb:audit fix` for 3 errors", "`/plumb:audit improve`", "`/plumb:update`",
   "`/plumb:upgrade`"). `PLUMB.md` exists, so the project is set up: **never suggest the setup commands create or
   extract** (a half-finished setup or no `Routes:` recorded → "`/plumb:init` resumes it"). Say "healthy" in one word
   when there is nothing.
