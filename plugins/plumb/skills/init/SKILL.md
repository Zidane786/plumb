---
name: init
description: Set up Plumb in this project - find the right home for the design system (detection is only a first guess; explore the folders and confirm with the user), link to a design system in another repo, or route to /plumb:create (no UI yet) or /plumb:extract (existing UI), then wire it in (PLUMB.md, the AGENTS.md/CLAUDE.md row, Makefile targets, the edit and end-of-turn checks, the Slate review check, Kiro steering). Re-running it shows status, resumes a half-finished setup and offers /plumb:upgrade; it never overwrites a design system.
argument-hint: "[project folder]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/detect.py*), Bash(python *scripts/detect.py*), Bash(py -3 *scripts/detect.py*), Bash(python3 *scripts/scaffold.py*), Bash(python *scripts/scaffold.py*), Bash(py -3 *scripts/scaffold.py*), Bash(python3 *scripts/build-tokens.py*), Bash(python *scripts/build-tokens.py*), Bash(py -3 *scripts/build-tokens.py*), Bash(python3 *scripts/audit.py*), Bash(python *scripts/audit.py*), Bash(py -3 *scripts/audit.py*), Bash(python3 *scripts/build-prototype.py*), Bash(python *scripts/build-prototype.py*), Bash(py -3 *scripts/build-prototype.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git -C * status --short), Bash(git -C * check-ignore *)
---

# /plumb:init — find the home, route, wire it in

These instructions are already loaded: follow them; don't load this skill again with a skill tool (Copilot CLI then
shows a harmless `Skill not found: plumb:init`).

```
roots ─▶ already set up? ─▶ status · resume a half-finished setup · offer /plumb:upgrade ─▶ STOP
detect ─▶ investigate + verify ─▶ the placement question (the whole block inside it) ─▶ linked? ─▶ linked PLUMB.md
existing or new? ─▶ /plumb:extract or /plumb:create ─▶ wire it in (each asked) ─▶ final checklist ─▶ what changed
```

**Rules.**
- **Nothing is written without the user's OK.** What detect.py or you find (root, layout, stack, UI files, routes,
  copy paths) is a suggestion for the user to confirm or correct. Never overwrite a design system.
- **Scripts give evidence, not answers:** check every script result against the files, correct or add to it (marked
  `(corrected: <why>)` / `(added: <why>)`), show that inside the question ([interview.md](../../reference/interview.md)).
- **Investigate first** (interview.md, "Investigate first"): gather every fact the code can answer before asking.
- **What the user confirms goes inside the question** (its text, or the recommended option's preview when the tool has
  one, as Claude Code's `AskUserQuestion` does), never only in a message before it: Claude Code can hide text printed
  right before a question; Copilot CLI's ask tool takes it in the question text.
- One question at a time, the recommendation first, marked "(Recommended)", and why; each is a **STOP: ask, wait for
  the answer**. Announce each step in one line.
- **Never install or download anything**; if something seems missing, say what and why, **ask the user and wait**.
  git is optional.
- Commands: the `allowed-tools` above; anything else asks first. Copilot CLI asks for each command: run each step's
  script calls in **one shell call** joined with `&&` (Windows PowerShell 5.1 has no `&&`: join with `;`, or run them
  one by one); the prompts to expect: [reference/copilot.md](../../reference/copilot.md).

**Plugin root (`ROOT`), first:** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
`<plugin>/skills/init`) + `/../..`, resolved to an absolute path. Check that `<ROOT>/scripts/detect.py` exists; if not,
resolve again, never guess. Scripts in `ROOT/scripts/`, templates in `ROOT/templates/`, references only as
`<ROOT>/reference/<file>`, the version in `ROOT/.claude-plugin/plugin.json`; placement: [placement.md](../../reference/placement.md).

**Python command:** `PLUMB.md`'s `Python:` line; else the first of `python3`, `python`, `py -3` for which
`<cmd> -c "import sys; print(sys.version_info >= (3, 9))"` prints `True`, used wherever this file says `python3`. None
works → say Plumb needs Python 3.9+, ask the user how they want to proceed, and stop.

**Project root (`<root>`):** the absolute `root` from detect.py's JSON, as corrected and confirmed in step 1. **From
step 1 on, every path is relative to `<root>` and every command names it (`--project-root "<root>"`); never write
outside it**, never `.` for it. Scratch files: `<root>/.plumb-tmp/` only (interview.md, "Scratch files"), never `/tmp`
or next to the repo. One exception: a backend repo's linked `PLUMB.md` (step 1.2), written only on the user's yes.

## Step 0: already set up?

Run, in one shell call (the folder the session opened in): `python3 "<ROOT>/scripts/detect.py" --cwd . --json &&
python3 "<ROOT>/scripts/detect.py" --cwd .` — the JSON for you, then the text block for step 1.6. When
`existing.plumb_md` is true, take that `root` as `<root>`; when `enclosing.plumb_md` is true (a `PLUMB.md` in a
folder above), say so and take `enclosing.root` (never offer a second setup inside a project that has one). Then:

1. Compare the version on `PLUMB.md`'s first line with the plugin's. Older → offer "Run `/plumb:upgrade` now?" (never
   run it yourself). Newer → a teammate upgraded: tell the user to update their plugin (`claude plugin marketplace
   update plumb`, `claude plugin update plumb@plumb`; Copilot CLI: `copilot plugin …`). **The user runs these.**
2. Run `python3 "<ROOT>/scripts/scaffold.py" --verify --project-root "<root>"`, check each line against the files, and
   show its `ok:`/`problem:` lines (a git-ignored skill path: step 1.5). A wrong location → offer the `--relocate` it
   prints (`--dry-run` first, run on yes). No `Routes:` recorded → offer to record it (step 1.4).
3. **Half-finished setup?** `<root>/.plumb-tmp/setup-in-progress` exists (a setup stopped midway; the end-of-turn check
   is off while it does), or a stage is missing, in order: the skill folder and tokens · generated files current
   (`build-tokens.py --check`) · components (`references/inventory.md`) · a screen in `docs/design/prototype/screens/`
   · decision entries · the wire-in items of step 4. Ask: (a) Resume `/plumb:create` (or `/plumb:extract`) from
   "<stage>" (Recommended) (b) Just show status. On (a) rewrite the marker (it keeps the end-of-turn check standing
   down), read that skill's `SKILL.md` and continue at that checkpoint.
4. Otherwise a short status (role, path, platforms, checks; `/plumb:status` for more). Never re-scaffold. Stop.

A `Role: linked` project: check the linked path still holds `SKILL.md`; if not, say so and ask for the new path.

## Step 1: find the home

1. **Investigate, then verify detect.** Read `layout`, `confidence` and `reasons`, then go through the project as
   interview.md "Investigate first" says and fill the evidence table. **Detection is a first guess, never the
   decision:** check every field against the files ([placement.md](../../reference/placement.md)).
2. **Layout cases**, each its own question, as interview.md "Layout cases" says: a parent folder of projects (ask
   which; write nothing in the parent) · a new, empty folder (start here?) · backend only (where will the UI live; a
   linked `PLUMB.md` here only on a separate yes) · React Native (design only, web or native themes; never React Native
   components) · inside a bigger project (use the enclosing folder?). After a change of folder, run detect again with
   `--cwd <folder>` and continue there.
3. **Linked or design only, moving a system later** (`scaffold.py --relocate`, never by hand): placement.md.
4. **Verify the UI files and routes before asking.** Count the files each proposed UI-file pattern matches and the UI
   files under each UI package; a pattern matching 0 files or far fewer than the package holds is wrong (root patterns
   for a package in `frontend/`): correct it (`frontend/src/**`). Find the route roots and record each as
   `<path> (<kind>)` from the framework you found (`frontend/src/app (next-app)`; kinds and `none`: interview.md "What
   gets recorded"), checked on disk; never leave the kind to be guessed. Check the copy path and the allowed raw path
   exist. They go into `PLUMB.md` (`UI files:`, `Routes:`); scripts and hooks only read what is recorded.
5. **Git-ignored?** Run `git -C "<root>" check-ignore -v <skill dir>/SKILL.md` (and read what detect, `--verify` or
   a dry run's `warning:` say; their `fix:` names the file the pattern is in and the exact lines). Ignored → the
   design system would never be committed. Never proceed silently: ask, with the source and line (`.gitignore:14`,
   `.git/info/exclude:1` or the global excludes file) inside the question: (a) Un-ignore the skill folder
   (Recommended), in the file the pattern is in: `.claude/` → `.claude/*` + `!.claude/skills/`; `.claude/**` → add
   `!.claude/skills/` and `!.claude/skills/**`; `.claude/*` → add `!.claude/skills/` (git cannot re-include a folder
   whose parent folder is ignored). A global excludes file applies to every repo: offer instead `!.claude/`,
   `.claude/*`, `!.claude/skills/` in this repo's `.gitignore` (it wins over that file and `.git/info/exclude`)
   (b) Another location (e.g. `.github/skills/<project>-design-system/`). **STOP: ask, wait for the answer.** Run the
   check again after the edit or a move with `git -C "<root>" check-ignore -q <skill dir>/SKILL.md`: exit 1 = kept
   (good); exit 0 = still ignored → `-v` says by which file and line, ask again (with `-v`, a `!` line means kept).
6. **The placement question — the whole block inside it, even at high confidence.** detect.py's text block **verbatim**,
   every line, is the question text (or the recommended option's preview), in a code block. **Never summarise it**,
   never put only part of it in the question, never ask about "the setup above". Mark lines you changed
   `(corrected: <why>)` or `(added: <why>)` with the evidence (matched-file counts, `file:line`). It lists
   **everything** that will be written, so the first page written later is covered:

   ```
   Plumb found:
     project    <root>     (git root; you opened <opened>)
     layout     <layout>
     UI         <path>   <framework · styling · shadcn>   (<n> UI files → extract)
     no UI      <path>   <stack>
   I'll create:
     <skill dir>/   in <root>
     PLUMB.md       in <root>
     docs/design/   in <root>   (directions or extract page, decision log, prototype, reports)
     generated copy → <global css path>
       <global css path> exists: Plumb adds and owns only a marked plumb:start … plumb:end block; the rest stays yours
     UI files   <patterns>   (<n> files match; what the audit and the checks cover)
     routes     <path> (<kind>)   (<n> pages)
   OK, or change something?
   ```

   Options: OK (Recommended) · change where the skill goes · change the project root · change the UI packages, the
   copy path, the UI files, the routes or the docs folder · something else. **STOP: ask, wait for the answer.** Repeat
   (the whole block again) until OK. Keep the confirmed placement; create or extract writes it into `PLUMB.md`.
7. Say once, no question: whether Effective HTML (`design-artifact`, `html-prototype`, `html`) is available here;
   optional, it only raises the craft; else Plumb's built-in quality bar ([prototypes.md](../../reference/prototypes.md)). Never install it.

## Step 2: linked to another repo?

Ask: "Does this repo use a design system that lives in another repo?" (a) No, this repo owns it (Recommended)
(b) Yes, it lives in another repo. On (b) follow "Linked repos" in placement.md (ask the path, check it, write
`<root>/PLUMB.md` from `ROOT/templates/PLUMB.md` with `Role: linked`), then step 4 (row and checks only).

## Step 3: existing or new?

Pre-fill from the evidence: UI files exist → extract, none → create. Ask: (a) "Extract the system you already have
from the code" (b) "Create a new design system", the pre-filled one first and marked (Recommended), with the count
inside the question. Then read `ROOT/skills/extract/SKILL.md` or `ROOT/skills/create/SKILL.md` and do every checkpoint
of it with the confirmed placement and `<root>` (its placement checkpoint is this step 1). Come back for step 4.

## Step 4: wire it in (each asked, one at a time; never skipped)

After create or extract, in the same session. **Ask every item even when the file does not exist yet** (no
`AGENTS.md` → offer to create it; no `Makefile` → offer to create one): a missing file, or a `note:` from
`scaffold.py --verify`, is never a reason to skip the question. Each item: what changes inside the question; STOP.

1. **PLUMB.md.** Show `<root>/PLUMB.md` inside the question; check the placement lines (UI files, routes) match what
   the user confirmed; change only what they agree. Keep the first line exactly
   `<!-- plumb v<plugin version> · written by /plumb:init, safe to edit values -->`.
2. **Checks.** "Turn on both checks? The edit check refuses edits that add design-system errors; the end-of-turn check
   reviews changed screens before the agent hands back." (a) Both on (Recommended) (b) edit check only (c) end-of-turn
   only (d) both off → set `Edit check:` and `End-of-turn check:` in `PLUMB.md`.
3. **The AGENTS.md / CLAUDE.md row** ([reference/wire-in.md](../../reference/wire-in.md)): a new `AGENTS.md` is a whole
   file (title, `## Read before you work`, the table header, the row), never a bare row.
4. **The Makefile targets.** `PLUMB.md` already names the direct commands. On yes, write the targets and add the
   `(make …)` hints to its `## Commands` lines (wire-in.md); on no, change nothing.
5. **The rest, each on its own** (wire-in.md): the Slate review check (only when `<root>/kanban/board.py` exists), Kiro
   steering (when Kiro is used; [reference/kiro.md](../../reference/kiro.md)), the monorepo package pointer.

Then `python3 "<ROOT>/scripts/scaffold.py" --verify --project-root "<root>"`: check each line, fix what it reports
(asked). A `problem: PLUMB.md names make …` line: ask whether to add the target or drop the hint.

## Step 5: final checklist, then what you did

Walk create's or extract's final checklist (a line that does not hold goes back to its checkpoint, asked), then this
one; remove the whole `<root>/.plumb-tmp/` (marker included) last.

- [ ] The whole "Plumb found … I'll create …" block was inside the placement question and confirmed before anything
      was written; UI files and routes (with their kinds) were verified and recorded; a git-ignored path was asked about
- [ ] `PLUMB.md` records the confirmed layout and starts with the version line
- [ ] Each wire-in item was asked (also when the file did not exist); `PLUMB.md` names no missing `make` target;
      nothing outside the agreed lines changed in AGENTS.md, CLAUDE.md, SLATE.md, Makefile, `.gitignore`
- [ ] `scaffold.py --verify` shows no `problem:` lines; `.plumb-tmp/` is gone; nothing written outside `<root>`;
      nothing installed or downloaded

Then `git -C "<root>" status --short` (without git: the files you wrote), one line each on why. Next: commit; a new
session in `<root>` so the hooks load; UI work is prototype first (`/plumb:prototype <screen>`); `/plumb:status`.
