---
name: init
description: Set up Plumb in this project - find the right home for the design system (detection is only a first guess; explore the folders and confirm with the user), link to a design system in another repo, or route to /plumb:create (no UI yet) or /plumb:extract (existing UI), then wire it in (PLUMB.md, the AGENTS.md/CLAUDE.md row, Makefile targets, the edit and end-of-turn checks, the Slate review check, Kiro steering). Re-running it shows status, resumes a half-finished setup and offers /plumb:upgrade; it never overwrites a design system.
argument-hint: "[project folder]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/detect.py*), Bash(python *scripts/detect.py*), Bash(py -3 *scripts/detect.py*), Bash(python3 *scripts/scaffold.py*), Bash(python *scripts/scaffold.py*), Bash(py -3 *scripts/scaffold.py*), Bash(python3 *scripts/build-tokens.py*), Bash(python *scripts/build-tokens.py*), Bash(py -3 *scripts/build-tokens.py*), Bash(python3 *scripts/audit.py*), Bash(python *scripts/audit.py*), Bash(py -3 *scripts/audit.py*), Bash(python3 *scripts/build-prototype.py*), Bash(python *scripts/build-prototype.py*), Bash(py -3 *scripts/build-prototype.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git -C * status --short)
---

# /plumb:init — find the home, route, wire it in

```
already set up? ─▶ status · resume a half-finished setup · offer /plumb:upgrade ─▶ STOP
find the home (detect → explore → "Plumb found … I'll create …" → you confirm) ─▶ linked? ─▶ linked PLUMB.md ─▶ wire in
existing or new? ─▶ /plumb:extract or /plumb:create ─▶ wire it in (each asked) ─▶ show what changed
```

**Rules.** **Nothing is written without the user's OK.** Everything detect.py or you find (project root, layout,
framework, styling, platforms, copy paths) is a **suggestion** shown for the user to confirm or correct, never used
silently. Ask one question at a time through the question tool, with options and the recommendation first, marked
"(Recommended)", and say why. Never write a file without saying where. **Never install or download anything**; if something seems
missing (Python, a package), say what and why, **ask the user and wait** for their decision. git is optional. Never
overwrite an existing design system. Announce each step in one line. Pre-approved commands (`allowed-tools`): Plumb's
`detect.py`, `scaffold.py`, `build-tokens.py`, `audit.py` and `build-prototype.py` (with `python3`, `python` or
`py -3`; init's list governs while it runs create or extract), `git rev-parse`,
`git -C <root> status --short`, `git config user.name`; anything else asks first.

**Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
`<plugin>/skills/init`) + `/../..`, resolved to an absolute path. Scripts are in `ROOT/scripts/`, templates in
`ROOT/templates/`, the plugin version in `ROOT/.claude-plugin/plugin.json` (`version`). Placement rules, layouts and
the detect.py fields: [reference/placement.md](../../reference/placement.md).

**Python command:** the `Python:` line of `PLUMB.md` when it exists; else the first of `python3`, `python`, `py -3`
for which `<cmd> -c "import sys; print(sys.version_info >= (3, 9))"` prints `True`. Use it wherever this file says
`python3`. None works → say Plumb needs Python 3.9+, ask the user how they want to proceed, and stop.

**Project root (`<root>`):** the absolute `root` from detect.py's JSON, as corrected and confirmed by the user in
step 1. **From step 1 on, every path is relative to `<root>` and every command names it explicitly
(`--project-root "<root>"`); never write outside it**, and never use `.` for it: the session may be open in a
subfolder or a parent folder. Two exceptions, each only as stated: the answers JSON for `scaffold.py` goes to the
system temp folder and is deleted after the scaffold; and a backend repo's linked `PLUMB.md` (step 1.4) is written
there only when the user says yes to that question.

## Step 0: already set up?

Run `python3 "<ROOT>/scripts/detect.py" --cwd . --json` (the folder the session opened in). When
`existing.plumb_md` is true (a `PLUMB.md` at `root`), take that `root` as `<root>`; when `enclosing.plumb_md` is
true (outside git, a `PLUMB.md` in a folder above), say so and take `enclosing.root` as `<root>` (never offer a
second setup inside a project that has one). Then:

1. Compare the version on `PLUMB.md`'s first line (`<!-- plumb vX.Y.Z …`) with the plugin's version. Older → offer
   "Run `/plumb:upgrade` now?" (never run it yourself). Newer → a teammate upgraded: tell the user they can update
   their plugin themselves (`claude plugin marketplace update plumb`, then `claude plugin update plumb@plumb`;
   Copilot CLI: `copilot plugin …`). **The user runs these; you never do** (they download).
2. Run `python3 "<ROOT>/scripts/scaffold.py" --verify --project-root "<root>"` and show its `ok:`/`problem:` lines. A
   wrong location → offer the `--relocate` it prints (show `--dry-run` first, then run on yes).
3. **Half-finished setup?** Check each stage in order: the skill folder and tokens file exist · generated files are
   current (`build-tokens.py --check`) · components exist (`references/inventory.md` names them) · a prototype exists
   (`docs/design/prototype/screens/` holds at least one `.html` screen; the scaffold leaves only a `.gitkeep`) · the decision log has entries · the wire-in items of step 4 exist. When one is
   missing, offer to resume from the first missing stage: (a) Resume `/plumb:create` (or `/plumb:extract`) from
   "<stage>" (Recommended) (b) Just show status. On (a) read that skill's `SKILL.md` and continue at that stage.
4. Otherwise show a short status (role, design-system path, platforms, checks on/off; `/plumb:status` gives the full
   picture). Never re-scaffold. Stop.

A `Role: linked` project: check the linked path still holds `SKILL.md`; if not, say so and ask for the new path.

## Step 1: find the home

1. Read the JSON's `layout`, `confidence` and `reasons`. **Detection is a first guess, never the decision:** when
   confidence is not `high`, when it found nothing, when a UI package is `"supported": false` or its
   `global_css.exists` is false, or when anything looks odd, look through the folders yourself (manifests, global
   stylesheets, routes, screens) as [placement.md](../../reference/placement.md) says, and correct the picture.
2. **Parent folder** (`layout: parent`): list `children` and ask which project; write nothing in the parent. Run
   detect again with `--cwd <child>` and continue there. Tell the user to open their next sessions in that folder
   (the hooks look for `PLUMB.md` from where a session opens).
3. **New, empty folder** (`layout: new`): "This folder is empty: start a new project here?" (a) Yes, create the design
   system here (Recommended) (b) No, it is somewhere else: ask for the path, run detect again with `--cwd <that path>` and take its `root` as
   `<root>`. On (a) the route in step 3 is create.
   No git is fine; offer `git init` once (the user decides; it is optional).
4. **Backend only:** "Where will the UI live?" (a) The frontend is in another repo (Recommended) (b) It will live here
   (c) Design only for now. On (a) ask for its path, run detect with `--cwd <that path>`, set Plumb up there (that
   path becomes `<root>`). Then ask separately: "Also write a linked `PLUMB.md` (and the AGENTS/CLAUDE row) in this
   backend repo, pointing at the frontend's design system?" (a) Yes (Recommended) (b) No; write it only on yes, as in step 2
   (the one write outside `<root>`). Tell the user to open the frontend repo for UI work. On (c) follow the design-only rules below.
5. **React Native** (`framework: react-native`): say plainly that React Native themes are not supported in Plumb
   1.0.0 (a candidate for 1.1.0). Offer only: (a) design only for now (Recommended) (b) web, when the repo has a web
   part (c) native iOS (SwiftUI) / Android (Compose) themes for native apps. Never write React Native components.
6. **Inside a bigger project?** (`enclosing` is set: outside git, a folder above has monorepo markers or a
   `PLUMB.md`): "Is the project `<enclosing.root>` (this folder is one of its packages)?" (a) Yes, use the enclosing
   folder (Recommended) (b) No, this folder is the project. On (a) run detect with `--cwd <enclosing.root>` and use it.
7. **Always** show the block and wait, even at high confidence. It lists **everything** that will be written,
   including the docs folder, so the first page written later (directions or extract page) is covered by this OK:

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
   OK, or change something?
   ```

   Options: OK (Recommended) · change where the skill goes (`.github/skills/…`, another name) · change the project
   root · change the UI packages, the copy path or the docs folder · something else. Repeat until the user says OK.
8. Keep the confirmed **placement**: `<root>`, project name and id, skill dir, platforms, styling per package, UI
   packages (`PLUMB.md` `UI packages:`), copy paths, UI file globs, allowed raw paths (`components/ui/**` where
   primitives live), docs dir (`docs/design`), Python command, role, and whether it is **design only**. Create or
   extract writes it into `PLUMB.md` and the tokens file, so no later command guesses again.
9. Say once, no question: whether the Effective HTML skills (`design-artifact`, `html-prototype`, `html`) are available
   in this session; they are optional and only raise the craft of the pages; without them Plumb uses its built-in
   quality bar ([prototypes.md](../../reference/prototypes.md#the-quality-bar-effective-html)). Never install them.

**Design only** (a backend repo, a React Native app, or the user's choice) and moving an existing system
(`scaffold.py --relocate`, never by hand): "Design only" and "Moving it later" in placement.md.

## Step 2: linked to another repo?

Ask: "Does this repo use a design system that lives in another repo?" (a) No, this repo owns it (Recommended)
(b) Yes, it lives in another repo. On (b) follow "Linked repos" in placement.md (ask the path, check it, write
`<root>/PLUMB.md` from `ROOT/templates/PLUMB.md` with `Role: linked`), then step 4 (row and checks only).

## Step 3: existing or new?

Pre-fill from detection and your own look: UI files exist → extract, none → create. Ask:
(a) "Extract the system you already have from the code" (b) "Create a new design system", the pre-filled one first and
marked (Recommended). Then read `ROOT/skills/extract/SKILL.md` or `ROOT/skills/create/SKILL.md` and do every step of
it with the confirmed placement and `<root>` (it skips its own placement step). Come back here for step 4.

## Step 4: wire it in (each asked, one at a time)

1. **PLUMB.md.** Show `<root>/PLUMB.md`. Check the placement lines match what the user confirmed; change only what
   they agree. Keep the first line exactly `<!-- plumb v<plugin version> · written by /plumb:init, safe to edit values -->`.
2. **Checks.** "Turn on both checks? The edit check refuses edits that add design-system errors; the end-of-turn check
   reviews changed screens before the agent hands back." (a) Both on (Recommended) (b) edit check only (c) end-of-turn
   only (d) both off → set `Edit check:` and `End-of-turn check:` in `PLUMB.md`.
3. **The rest, each asked on its own** as [reference/wire-in.md](../../reference/wire-in.md) says: the AGENTS.md /
   CLAUDE.md row, the Makefile targets, the Slate review check (when `kanban/board.py` exists), Kiro steering (when
   Kiro is used), and the monorepo package pointer (when opened inside a package).

Then run `python3 "<ROOT>/scripts/scaffold.py" --verify --project-root "<root>"` and fix what it reports (asked).

## Step 5: show what you did

- `git -C "<root>" status --short` (without git: list the files you wrote), one line each on why.
- Next steps: commit these files; start a new session in `<root>` so the hooks load; UI work is prototype first
  (`/plumb:prototype <screen>`); `/plumb:audit` any time; `/plumb:status` for health.

## Checklist before you finish

- [ ] The user confirmed the "Plumb found … I'll create …" block before anything was written; every command named
      `<root>` and nothing was written outside it
- [ ] `PLUMB.md` records the confirmed layout and starts with the version line
- [ ] Each wire-in item was asked; nothing outside the agreed lines changed in AGENTS.md, CLAUDE.md, SLATE.md, Makefile
- [ ] `scaffold.py --verify` shows no `problem:` lines; nothing was installed or downloaded
