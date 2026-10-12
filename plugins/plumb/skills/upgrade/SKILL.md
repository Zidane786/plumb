---
name: upgrade
description: Upgrade this project's design system to the installed Plumb plugin's version - compare versions, show "What's new" for every version in between, refresh Plumb's own files in the project (scripts and templates), migrate the tokens file additively, regenerate every generated file, run each version's upgrade steps asking before each, record the upgrade in PLUMB.md, check until healthy, show the diff.
disable-model-invocation: true
---

# /plumb:upgrade — bring the project's copied files up to the plugin's version

Only run when the user typed `/plumb:upgrade` (other skills and the session-start check offer it, never run it).
How the version files work: `<ROOT>/upgrades/README.md`. Commands: `<ROOT>/reference/scripts.md`.

**Ownership** (what an upgrade may touch): `[P]` Plumb's files (`<skill>/scripts/*`, `<skill>/templates/*`,
`assets/platforms/README.md`) are replaced; `[G]` generated files are regenerated; `[Y]` your files (tokens, `design.md`,
references, screen files, tours, `PLUMB.md`, decisions) change only through a version step the user said yes to, and
the tokens file only by additive migration (no value is ever deleted or changed); `[A]` agent-written components are
never touched. **Nothing is written without the user's OK.** Never commit, push or delete data. Never install, update or
download anything yourself, the plugin included: print the commands for the user to run and wait. One question at a
time, options with the recommendation first; keep every value the project already set.

```
 versions ─▶ What's new (every version in between) ─▶ ask ─▶ refresh [P] (scaffold.py) ─▶ --migrate ─▶ regenerate [G]
   ─▶ upgrades/<v>.md steps, in order, asking before EACH ─▶ PLUMB.md (version line, settings, Plumb updates)
   ─▶ checks until healthy ─▶ summary + diff ─▶ STOP
```

## Step 0: versions

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute.
2. Find `PLUMB.md` at the project root. Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Role:`, `Python:` (**PY**, `python3` when unset), `Platforms:`.
   **docs** (one source of truth): the folder of `PLUMB.md`'s `## Prototype` `Main:` path; only when `PLUMB.md` has no
   such line, the tokens file's `$extensions.plumb.docs_dir`; else `docs/design`. When the two disagree, `PLUMB.md` wins
   and you say so.
4. `PY "<ROOT>/scripts/version.py" --project . --plugin "<ROOT>" --json` → **OLD** (`project`), **NEW** (`plugin`),
   `between`:
   - `same` → "Already on Plumb <NEW>." Still run step 5's checks; if `scaffold.py --verify` or a `--check` reports a
     problem, offer to fix it. Otherwise stop.
   - `newer` → the project is newer than the plugin (a teammate upgraded): never downgrade. Print the commands for the
     user to run in their own terminal: `claude plugin marketplace update plumb`, then `claude plugin update plumb@plumb`,
     then `/reload-plugins` (Copilot CLI: `copilot plugin marketplace update plumb`, then
     `copilot plugin update plumb@plumb`, then `/restart`). Ask them to say "done" and run `/plumb:upgrade` again; stop.
   - `older` → continue.
5. `Role: linked` → this repo holds only `PLUMB.md`; its design system is upgraded in the home repo. Here, only step 4
   (the version line and the Plumb updates line) applies: say so, ask, do it on a yes, stop.
6. `git status --short -- <SKILL> PLUMB.md <docs>`: uncommitted changes → say so and ask whether to continue (Plumb's
   files are replaced; local edits to them are not kept).

## Step 1: What's new — before changing anything

- For each version in `between` (ascending), read `<ROOT>/upgrades/<v>.md` and show its **What's new** in plain words
  (what the user can now do, one example command each); group by version, keep it short. The full changelog:
  `<ROOT>/CHANGELOG.md`.
- Say what the upgrade changes, using the ownership list above.
- Ask: "Upgrade from <OLD> to <NEW> now?" Continue only on yes.

## Step 2: refresh Plumb's files, migrate, regenerate

1. Collect the scaffold values, keeping what the project set: `--name` (the product name in `PLUMB.md`'s title
   `# Plumb: the design system for <name>`), `--skill-dir` (SKILL), `--platforms` (the tokens file's
   `$extensions.plumb.platforms`, else `PLUMB.md`'s `Platforms:`), `--styling` (`$extensions.plumb.web.styling`, `css`
   when the project has no web platform), `--docs-dir` (**docs**, step 0).
2. `PY "<ROOT>/scripts/scaffold.py" --project-root . --name "<name>" --skill-dir <SKILL> --platforms <list> --styling
   <styling> --docs-dir <docs> --dry-run`. It lists `would write:` for Plumb's files (`scripts/*.py`, `templates/*`,
   `assets/platforms/README.md`) and for any file new in this version, and `skip: … (yours, kept)` for every file of
   yours. Show the list; anything of the project's that would be written other than a new file → stop and ask.
3. Ask "Replace Plumb's files as listed?"; on yes, run the same command without `--dry-run`.
4. `PY SKILL/scripts/build-tokens.py --migrate` (adds new settings to the tokens file; never removes or changes a value),
   then `PY SKILL/scripts/build-tokens.py` (every theme, copy, the specimen and the prototype and proposal token blocks),
   then, when the project has screen files, `PY SKILL/scripts/build-prototype.py`. Exit 2 → show the `error:` and its
   `fix:`; never hand-edit a generated file or Plumb's scripts to make it pass.
5. **Rolling back** (only if something failed and the user agrees): restore Plumb's own files only,
   `git checkout -- <SKILL>/scripts <SKILL>/templates <SKILL>/assets/platforms/README.md`, then regenerate with
   `PY SKILL/scripts/build-tokens.py`. Never `git checkout` the whole skill folder or `<docs>`: that would discard the
   user's own files.

## Step 3: each version's upgrade steps, asking before each

For every file in `between`, in ascending order, read its `## Steps` and take each numbered step in order:

1. Run its **Check** and show the result in one line: "needed" or "not needed (already done)". Not needed → say so and
   go to the next step.
2. Needed → show what its **Do** will run or change (the exact commands, the files and the lines), then ask:
   "Run step <n> (<title>)?" — **Keep as is (default)** / Run it. Recommend running it when the step says it is
   recommended.
3. On "Run it": do exactly what the Do says, using PY in every command; its own questions (values to set) are asked one
   at a time, with the project's current value as the default. On "Keep": record it as skipped for the summary.

Ask before anything that changes meaning or touches files the project owns (`.gitignore`, `PLUMB.md`, `AGENTS.md`,
`Makefile`, git config, the tokens file). Steps are idempotent: running the upgrade again finds them "not needed".

## Step 4: PLUMB.md (show the changes, ask, then write)

- [ ] Replace the first line with `<!-- plumb v<NEW> · written by /plumb:init, safe to edit values -->`.
- [ ] Compare with `<ROOT>/templates/PLUMB.md`: add any section or setting line it has that `PLUMB.md` lacks (fill it the
      way `/plumb:init` would, asking for anything unknown; the version steps say how). Change no existing value.
- [ ] `## Plumb updates`: add one dated line, e.g.
      `- 2026-11-02 upgraded Plumb 1.0.0 → 1.1.0: <the main new things from What's new>`.

## Step 5: check until healthy

Run, report what each finds, fix it with the user's OK, and repeat until clean:

```bash
PY "<ROOT>/scripts/version.py" --project . --plugin "<ROOT>"      # expect: up to date
PY "<ROOT>/scripts/scaffold.py" --verify --project-root .
PY SKILL/scripts/build-tokens.py --check
PY SKILL/scripts/build-prototype.py --check                       # when the project has screen files
PY SKILL/scripts/audit.py
```

A new audit rule may find things the old version did not: those are not part of the upgrade. List the counts and offer
`/plumb:audit fix`.

## Step 6: show the result, then stop

- "Now on Plumb <NEW>. New for you: …" (two or three lines from What's new), the steps run and kept, the check results.
- `git diff --stat` and one line per changed file. Tell the user to commit it (e.g. `Plumb: upgrade to v<NEW>`) and that
  teammates need the plugin updated (print the commands from step 0); linked repos run `/plumb:upgrade` for their
  `PLUMB.md` line. Do not commit unless asked.
