---
name: init
description: Set up Plumb in this project - find the right home for the design system (detection is only a first guess; explore the folders and confirm with the user), link to a design system in another repo, or route to /plumb:create (no UI yet) or /plumb:extract (existing UI), then wire it in (PLUMB.md, the AGENTS.md/CLAUDE.md row, Makefile targets, the edit and end-of-turn checks, the Slate review check, Kiro steering). Re-running it shows status and offers /plumb:upgrade; it never overwrites a design system.
argument-hint: "[project folder]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/*.py*), Bash(python *scripts/*.py*), Bash(py -3 *scripts/*.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git status *)
---

# /plumb:init — find the home, route, wire it in

```
already set up? ─▶ status + offer /plumb:upgrade ─▶ STOP
find the home (detect → explore → "Plumb found … I'll create …" → you confirm) ─▶ linked? ─▶ linked PLUMB.md ─▶ wire in
existing or new? ─▶ /plumb:extract or /plumb:create ─▶ wire it in (each asked) ─▶ show what changed
```

**Rules.** Ask one question at a time through the question tool, with options and the recommendation first, marked
"(Recommended)". Never write a file without saying where. **Never install or download anything**; if something seems
missing (Python, git, a package), say what and why, **ask the user and wait** for their decision. Never overwrite an
existing design system. Announce each step in one line.

**Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
`<root>/skills/init`) + `/../..`, resolved to an absolute path. Scripts are in `ROOT/scripts/`, templates in
`ROOT/templates/`, the plugin version in `ROOT/.claude-plugin/plugin.json` (`version`). Placement rules, layouts and
the detect.py fields: [reference/placement.md](../../reference/placement.md).

**Python command:** the `Python:` line of `PLUMB.md` when it exists; else the first of `python3`, `python`, `py -3`
for which `<cmd> -c "import sys; print(sys.version_info >= (3, 9))"` prints `True`. Use it wherever this file says
`python3`. None works → say Plumb needs Python 3.9+, ask the user how they want to proceed, and stop.

## Step 0: already set up?

Run `python3 "<ROOT>/scripts/detect.py" --cwd . --json`. When `existing.plumb_md` is true (a `PLUMB.md` at the root):

1. Compare the version on `PLUMB.md`'s first line (`<!-- plumb vX.Y.Z …`) with the plugin's version. Older → offer
   "Run `/plumb:upgrade` now?" (never run it yourself). Newer → a teammate upgraded: suggest updating the plugin
   (`claude plugin marketplace update plumb` and `claude plugin update plumb@plumb`; Copilot CLI: `copilot plugin …`).
2. Run `python3 "<ROOT>/scripts/scaffold.py" --verify --project-root .` and show its `ok:`/`problem:` lines. A wrong
   location → offer the `--relocate` it prints (show `--dry-run` first, then run on yes).
3. Show a short status: role, design-system path, platforms, checks on/off, and `build-tokens.py --check` from the
   design-system skill (`/plumb:status` gives the full picture).
4. Offer any step 4 item that is missing (no row, no Makefile targets). Then stop. Never re-scaffold.

A `Role: linked` project: check the linked path still holds `SKILL.md`; if not, say so and ask for the new path.

## Step 1: find the home

1. Read the JSON's `confidence` and `reasons`. **Detection is a first guess, never the decision:** when confidence is
   not `high`, when it found nothing, when a UI package is `"supported": false` or its `global_css.exists` is false,
   or when anything looks odd, look through the folders yourself (manifests, global stylesheets, routes, screens) as
   [placement.md](../../reference/placement.md) says, and correct the picture.
2. **Parent folder** (`layout: parent`): list `children` and ask which project; write nothing in the parent; run
   detect again with `--cwd <child>` and continue there.
3. **Backend only:** ask (a) the frontend is in another repo (its path), (b) the frontend will live here,
   (c) design only for now.
4. **React Native:** explain that React Native themes are not supported in Plumb 1.0.0. Offer only web (when there is
   a web part), iOS (SwiftUI), Android (Compose), or design only for now.
5. **Always** show the block and wait, even at high confidence:

   ```
   Plumb found:
     project    <root>     (git root; you opened <opened>)
     layout     <layout>
     UI         <path>   <framework · styling · shadcn>   (<n> UI files → extract)
     no UI      <path>   <stack>
   I'll create:
     <skill dir>/   at the repo root
     PLUMB.md       at the repo root
     generated copy → <global css path>
   OK, or change something?
   ```

   Options: OK (Recommended) · change where the skill goes (`.github/skills/…`, another name) · change the UI
   packages or the copy path · something else. Repeat until the user says OK.
6. Keep the confirmed **placement**: project name and id, skill dir, platforms, styling per package, UI packages
   (`PLUMB.md` `UI packages:`), copy paths, UI file globs, allowed raw paths (`components/ui/**` where primitives
   live), docs dir (`docs/design`), Python command, role. It is what create or extract writes into `PLUMB.md` and the
   tokens file, so no later command guesses again.

If the user changes the placement of a design system that already exists, move it only with
`scaffold.py --relocate FROM TO --project-root .` (dry run first), never by hand.

## Step 2: linked to another repo?

Ask: "Does this repo use a design system that lives in another repo?" (a) No, this repo owns it (Recommended)
(b) Yes, it lives in another repo. On (b): ask for the path to that design-system skill folder, check it holds
`SKILL.md` and `assets/tokens/*.tokens.json`, write `PLUMB.md` from `ROOT/templates/PLUMB.md` with `Role: linked` and
`Design system:` set to that path (see "Linked repos" in placement.md), then go to step 4 (row and checks only).

## Step 3: existing or new?

Pre-fill from detection and your own look: UI files exist → extract, none → create. Ask:
(a) "Extract the system you already have from the code" (b) "Create a new design system", the pre-filled one first and
marked (Recommended). Then read `ROOT/skills/extract/SKILL.md` or `ROOT/skills/create/SKILL.md` and do every step of
it with the confirmed placement (it skips its own placement step). Come back here for step 4 when it finishes.

## Step 4: wire it in (each asked, one at a time)

1. **PLUMB.md.** Show its lines. Check the placement lines match what the user confirmed; change only what they agree.
   Keep the first line exactly `<!-- plumb v<plugin version> · written by /plumb:init, safe to edit values -->`.
2. **Checks.** "Turn on both checks? The edit check refuses edits that add design-system errors; the end-of-turn check
   reviews changed screens before the agent hands back." (a) Both on (Recommended) (b) edit check only (c) end-of-turn
   only (d) both off → set `Edit check:` and `End-of-turn check:` in `PLUMB.md`.
3. **AGENTS.md / CLAUDE.md row.** Fill `ROOT/templates/agents-row.md` (`{{SKILL_DIR}}` = the skill dir with a trailing
   `/`). Options: AGENTS.md (Recommended when it exists) · CLAUDE.md · both · skip. Add the row to the file's "read
   before you work" table; if there is none, add a `## Read before you work` section with `| When | Read | Rule |`.
   If neither file exists, offer to create `AGENTS.md` with that section (and `CLAUDE.md` holding `@AGENTS.md`).
   Change nothing else in those files.
4. **Makefile targets** `tokens`, `tokens-check`, `design-audit` from `ROOT/templates/Makefile.snippet`
   (`{{PYTHON}}`, `{{SKILL_DIR}}` filled). Append to the Makefile (create one only on yes). Targets with those names
   already → show them and ask. No `make` → the commands in `PLUMB.md` are enough; say so.
5. **Slate** (only when `kanban/board.py` exists): "Add the design audit to Slate's review checks?" (a) Yes
   (Recommended) (b) No. On yes add `- Plumb design audit: \`make design-audit\` exits 0` (or the plain command)
   under `## Extra review checks` in `SLATE.md`, replacing a lone `- none`. Never touch `kanban/`.
6. **Kiro** (ask only when `.kiro/` exists or the user mentions Kiro): "Write `.kiro/steering/plumb.md` so Kiro reads
   the design system on every task?" On yes write front matter `inclusion: always` and one paragraph: before any UI
   change read `<skill dir>/SKILL.md`; UI work is prototype first; never install or download anything, ask the user and
   wait. Kiro's own skills and hooks come from `kiro.py install` (tell the user; do not run it for them).
7. **Monorepo package** (the session was opened inside a package): offer the one-line pointer in that package's
   `AGENTS.md`/`CLAUDE.md` from placement.md.

Then run `python3 "<ROOT>/scripts/scaffold.py" --verify --project-root .` and fix what it reports (asked).

## Step 5: show what you did

- `git status --short`: every file created or changed, one line each on why.
- Next steps: commit these files; start a new session so the hooks load; UI work is prototype first
  (`/plumb:prototype <screen>`); `/plumb:audit` any time; `/plumb:status` for health.

## Checklist before you finish

- [ ] The user confirmed the "Plumb found … I'll create …" block before anything was written
- [ ] `PLUMB.md` records the confirmed layout and starts with the version line
- [ ] Each wire-in item was asked; nothing outside the agreed lines changed in AGENTS.md, CLAUDE.md, SLATE.md, Makefile
- [ ] `scaffold.py --verify` shows no `problem:` lines; nothing was installed or downloaded
