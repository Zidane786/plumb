---
name: upgrade
description: Upgrade this project's design system to the installed Plumb plugin's version - compare versions, show "What's new" for every version in between, refresh Plumb's own files in the project (scripts and templates), migrate the tokens file additively, regenerate every generated file, run each version's upgrade steps asking before each, record the upgrade in PLUMB.md, check until healthy, show the diff.
disable-model-invocation: true
---

# /plumb:upgrade — bring the project's copied files up to the plugin's version

Only run when the user typed `/plumb:upgrade` (other skills and the session-start check offer it, never run it).
These instructions are already loaded: don't load this skill again with a skill tool.
How the version files work: `<ROOT>/upgrades/README.md`. Commands: [`scripts.md`](../../reference/scripts.md). Copilot CLI (update commands, hooks): [`copilot.md`](../../reference/copilot.md).

**Ownership** (what an upgrade may touch): `[P]` Plumb's files (`<skill>/scripts/*`, `<skill>/templates/*`,
`assets/platforms/README.md`) are replaced; `[G]` generated files are regenerated; `[Y]` your files (tokens,
`design.md`, references, screen files, tours, `PLUMB.md`, decisions) change only through a version step the user said
yes to, and the tokens file only by additive migration (no value is ever deleted or changed); `[A]` agent-written
components are never touched. **Nothing is written without the user's OK.** Never commit, push or delete data.
Never install or download anything yourself (update the plugin included): print the commands for the user to run, then ask the user and wait.
Questions go **one at a time** through the question tool, options with the recommendation first marked "(Recommended)"; keep every value the project already set.
**Scripts give evidence, not answers:** check each script result against the code (search and read any time),
correct or add to it (marked `(corrected: <why>)` / `(added: <why>)`) and show that inside the question before the
user decides; a script that is wrong in a way that will recur → say so and suggest the fix to Plumb
([interview.md](../../reference/interview.md), "Scripts give evidence, not answers").
When a Plumb script or hook is wrong and you correct it, record the Plumb mistake with /plumb:feedback. **What the user
confirms goes inside the question** (its text, or the recommended option's preview when the tool has one), never only in
a message before it: Claude Code can hide that text; Copilot CLI's ask tool takes it in the question text.

```
 versions ─▶ What's new (every version in between) ─▶ ask ─▶ refresh [P] (scaffold.py) ─▶ --migrate ─▶ regenerate [G]
   ─▶ upgrades/<v>.md steps, in order, asking before EACH ─▶ PLUMB.md (version line, settings, Plumb updates)
   ─▶ checks until healthy ─▶ summary + diff ─▶ STOP
```

## Step 0: versions

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute. Check that `<ROOT>/reference/scripts.md`
   exists; if not, resolve again, never guess. Read Plumb's references only as `<ROOT>/reference/<file>`.
2. **Project root `<root>`:** the absolute path of the folder holding `PLUMB.md` (the folder the session opened in,
   else the nearest folder above it). Every path below is `<root>/…`; **SKILL** (step 3) is `<root>/<Design system:>`,
   made absolute; read the project's references as `SKILL/references/<file>`, never from a path you remember.
   Scratch files: `<root>/.plumb-tmp/` only (its `.gitignore` first); clean up your own files when the command
   ends; never write `setup-in-progress` (the setup marker); never `/tmp` or outside `<root>`.
   Missing → "This project isn't set up for Plumb yet — run `/plumb:init`." Stop.
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Role:`, `Python:` (**PY**, `python3` when unset), `Platforms:`.
   **docs** (the docs folder): the tokens file's `$extensions.plumb.docs_dir`, default `docs/design`, which is where the
   scripts write. If `PLUMB.md`'s `## Prototype` `Main:` path sits in another folder, say so and ask the user which is
   right, then fix the other one after their OK (`<ROOT>/reference/scripts.md`, "The docs folder"). Settle this before
   step 2: the agreed folder is what `scaffold.py --docs-dir` gets.
4. `PY "<ROOT>/scripts/version.py" --project "<root>" --plugin "<ROOT>" --json` → **OLD** (`project`), **NEW** (`plugin`),
   `between`:
   - `same` with `files_differ` empty → "Already on Plumb <NEW>." Still run step 5's checks; if `scaffold.py --verify`
     or a `--check` reports a problem, offer to fix it. Otherwise stop.
   - `same` with `files_differ` → another build of the same version, or a hand edit: Plumb's own files differ from
     the plugin's, and the files cannot tell which is newer. Gather the evidence: `git log -1 --format=%cs -- <file>`
     for each listed file, `git status --short` on them (a local edit), `PLUMB.md`'s latest "Plumb updates" line, and
     the plugin's own date: `git -C "<ROOT>" log -1 --format=%cs` when `<ROOT>` is a git checkout (a plugin loaded
     from a clone), else the modified date of `<ROOT>/.claude-plugin/plugin.json` (when it was installed or updated).
     Skip step 1 (no version in between) and run the rest in order: item 6 below; step 2, whose step-3 question takes
     the place of step 1's: put the `files_differ` list, that evidence and the dry-run list in it, with **Refresh from
     this plugin** recommended unless the evidence shows the project's copy is newer (a teammate's later refresh, a
     commit after this plugin was installed), then **Keep the project's files** is recommended; step 3 with
     `<NEW>.md` alone (a project set up with an earlier build of this version may still need its steps: each step's
     Check says, and a done one is "not needed"); step 4 (the version line stays; the "Plumb updates" line says
     `refreshed Plumb <NEW>'s files`); step 5; step 6. Every other question in those steps is still asked.
   - `newer` → the project is newer than the plugin (a teammate upgraded): never downgrade. Print the commands for the
     user to run in their own terminal: `claude plugin marketplace update plumb`, then
     `claude plugin update plumb@plumb`, then `/reload-plugins` (Copilot CLI: `copilot plugin marketplace update plumb`,
     then `copilot plugin update plumb@plumb`, then `/restart`). Ask them to say "done" and run `/plumb:upgrade` again;
     stop.
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
   when the project has no web platform), `--docs-dir` (**docs**, the folder agreed in step 0).
2. `PY "<ROOT>/scripts/scaffold.py" --project-root "<root>" --name "<name>" --skill-dir <SKILL> --platforms <list>
   --styling <styling> --docs-dir <docs> --dry-run`. It lists `would write:` for Plumb's files (`scripts/*.py`,
   `templates/*`, `assets/platforms/README.md`) and for any file new in this version, `skip: … (yours, kept)` for every
   file of yours, and ends with a `confirm:` line naming `--confirm <token>`. Check the list (anything of the project's
   that would be written other than a new file → stop and ask; a `warning: … git-ignored` line → ask as `/plumb:init`
   step 1.5 does).
3. Ask "Replace Plumb's files as listed?" with the **full** list inside the question. **STOP: ask, wait for the
   answer.** On yes, in a new shell call: the same command without `--dry-run`, plus `--confirm <token>` exactly as the
   dry run printed it (a stale token is refused: run the dry run again and ask again).
4. `PY SKILL/scripts/build-tokens.py --migrate` (adds new settings to the tokens file; never removes or changes a
   value; with Tailwind it records `web.reset_palette: true`: when the app's UI files use Tailwind's palette classes,
   say how many inside a question and offer keep, `false`, recommended, as interview.md "Tailwind's default palette"
   says, before the build), then `PY SKILL/scripts/build-tokens.py` (every theme, copy, the specimen and the prototype and proposal token
   blocks), then, when the project has screen files, `PY SKILL/scripts/build-prototype.py`. Exit 2 → show the `error:`
   and its `fix:`; never hand-edit a generated file or Plumb's scripts to make it pass. `error: <page> is not Plumb's`
   (a page the new build writes, e.g. `app.html`, is already there, made by another tool or by hand) → ask the user
   whether to move it to the `.before-plumb.html` name the fix gives (recommended: nothing is lost) or keep it and skip
   the prototype pages for now (say inside the question what keeping costs: `build-prototype.py --check` exits 1 until
   it is moved, and so does a CI that runs it, and Step 5 cannot come out clean; `build-tokens.py --check` and
   `make tokens-check` are not affected); move it only on their yes, then build again. The tokens build's `warning:
   <docs>/specimen.html is not Plumb's` (everything else was built; the specimen was left as it is) → the same
   question for the specimen (what keeping costs there: `build-tokens.py --check` exits 1 until it is moved, so
   `make tokens-check` in CI stays red, the session line says "tokens stale", the audit warns, and Step 5 cannot come
   out clean).
5. **Rolling back** (only if something failed and the user agrees): restore Plumb's own files only, one path at a
   time, from the `would write:` list of the dry run:
   - a path git knows (`git ls-files --error-unmatch <path>` exits 0): `git checkout -- <path>`;
   - a path not in `HEAD` (new in this version): leave it, note it, and at the end list these new files and ask
     whether to delete them; delete only the ones the user says yes to. Never delete anything without asking.

   Then regenerate with `PY SKILL/scripts/build-tokens.py`. Never `git checkout` the whole skill folder or `<docs>`:
   that would discard the user's own files.

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
- [ ] Compare with `<ROOT>/templates/PLUMB.md`: add any section or setting line it has that `PLUMB.md` lacks (fill it
      the way `/plumb:init` would, asking for anything unknown; the version steps say how). Change no existing value.
      A missing `Routes:` line (or `UI files:` patterns that match no file): investigate the app's page roots, count
      what they match, and offer the line (`<path> (<kind>)` from the framework found, or `none`; interview.md "What
      gets recorded") with that evidence inside the question; the user may change them here.
- [ ] `## Plumb updates`: add one dated line, e.g.
      `- 2026-11-02 upgraded Plumb 1.0.0 → 1.1.0: <the main new things from What's new>`.

## Step 5: check until healthy

Run, report what each finds, fix it with the user's OK, and repeat until clean:

```bash
PY "<ROOT>/scripts/version.py" --project "<root>" --plugin "<ROOT>"      # expect: up to date
PY "<ROOT>/scripts/scaffold.py" --verify --project-root "<root>"
PY SKILL/scripts/build-tokens.py --check
PY SKILL/scripts/build-prototype.py --check                       # when the project has screen files
PY SKILL/scripts/audit.py
```

`audit.py`: **exit 1 means errors found, not a crash** (your tool may show it as a failed command). A new audit rule
may find things the old version did not: those are not part of the upgrade. List the counts and offer
`/plumb:audit fix`. Run these checks in one shell call where you can (Copilot CLI asks for every command).

## Step 6: show the result, then stop

- "Now on Plumb <NEW>. New for you: …" (two or three lines from What's new), the steps run and kept, the check results.
- `git diff --stat` and one line per changed file. Tell the user to commit it (e.g. `Plumb: upgrade to v<NEW>`) and that
  teammates need the plugin updated (print the commands from step 0); linked repos run `/plumb:upgrade` for their
  `PLUMB.md` line. Do not commit unless asked.
