# Placement: where the design system lives

`/plumb:init` decides where the design-system skill and `PLUMB.md` go, **with the user**. Init never assumes the
folder it was opened in is the project. **Nothing is written without the user's OK**: every detected fact (project
root, layout, framework, styling, platforms, copy paths) is a suggestion the user confirms or corrects.

**The project root (`<root>`)** is the absolute `root` from detect.py, as the user confirmed or corrected it. From then
on every path is relative to `<root>` and every command names it explicitly (`--project-root "<root>"`,
`"<root>/<skill dir>/scripts/…"`); never write outside it, and never use `.` for it (the session may be open in a
subfolder of the project, or in a parent folder of several).

## Detection is a first guess, never the decision

`python3 "<ROOT>/scripts/detect.py" --cwd <the folder the session opened in> --json` only looks for well-known marker
files and folders. No script knows every layout, so:

1. Read the JSON. Note `confidence` (`high`, `medium`, `low`) and every line in `reasons`.
2. When `confidence` is not `high`, when `ui_packages` and `no_ui` are both empty, when a UI package has
   `"supported": false`, when a `global_css` has `"exists": false`, or when anything looks odd (a UI folder you
   expected is missing, a count of UI files that seems wrong), **look through the folders yourself**: list the top two
   levels, open the manifests (`package.json`, `angular.json`, `vite.config.*`, `*.xcodeproj`, `build.gradle*`,
   `settings.gradle*`), find where the global stylesheet really is (search for `@import "tailwindcss"`, `@tailwind`,
   `:root {`), and where the routes or screens live.
3. **Always** show the user what was found and what will be created, in the block below, and wait for "OK" or a
   correction. Even at `high` confidence.
4. What the user confirms is what gets written, and it is recorded in `PLUMB.md` (`Design system:`, `Role:`,
   `Platforms:`, `UI packages:`, `UI files:`, the copy paths in the tokens file), so later commands never guess again.

```
Plumb found:
  project    ~/Projects/acme          (git root; you opened ~/Projects/acme/apps/web)
  layout     monorepo (pnpm workspaces)
  UI         apps/web   Next.js · Tailwind v4 · shadcn   (142 UI files → extract)
  no UI      apps/api   FastAPI
I'll create:
  .claude/skills/acme-design-system/   in ~/Projects/acme
  PLUMB.md                             in ~/Projects/acme
  generated copy → apps/web/app/globals.css
OK, or change something?
```

`detect.py` without `--json` prints this block; use it as the starting point and correct it with what you found.

## detect.py fields

| Field | Means |
|---|---|
| `root`, `opened` | The repo root (git, else the nearest folder with `.git`; outside git, the folder opened) and where the session was opened, relative to it. |
| `in_repo`, `git`, `git_available` | Inside a repo; a git repo with git working; git installed. git is optional: outside a repo the opened folder is the project when it has markers. |
| `layout` | `parent` (outside git, no markers here but child folders have some), `new` (outside git and empty, or only dotfiles), `monorepo`, `mixed` (UI and backend without monorepo markers), `frontend`, `backend`, `single` (nothing recognised). |
| `monorepo` | The marker found: `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json`, `rush.json`, `package.json workspaces`, `apps/ + packages/`, `frontend/ + backend/`. |
| `ui_packages[]` | `path`, `framework` (`next react vue svelte angular html swiftui uikit compose android-views react-native`), `styling` (`tailwind-v4 tailwind-v3 css native`), `shadcn`, `platforms`, `files` (UI file count), `supported`, `note`, `global_css {path, exists}`. |
| `no_ui[]` | Backend packages: `path`, `stack` (`fastapi django flask go java rust rails express …`). |
| `children[]` | Only for `parent`: `name`, `is_repo`, `has_ui`. |
| `existing` | `plumb_md` (a `PLUMB.md` is there), `skill`, `role`. |
| `proposal` | `project` (kebab-case name), `skill_dir`, `plumb_md`, `copies` (generated CSS copy paths), `platforms`, `alternatives`. |
| `confidence`, `reasons` | How sure the guess is and why not more. `low`: no markers, a guessed CSS path, several UI packages without monorepo markers, a parent folder. `medium`: an unsupported stack, backend and UI side by side, not a git repo. |

## Layouts

| Situation | What init does |
|---|---|
| **Parent folder** (`layout: parent`, e.g. opened at `~/Desktop`) | List `children` (repo or folder, has UI) and ask which project. Write **nothing** in the parent. Run detect again with `--cwd <child>` and continue there; tell the user to open future sessions in that folder (the hooks look for `PLUMB.md` upwards from where a session opens). |
| **New, empty folder** (`layout: new`) | Ask "Start a new project here?" (a) Yes (Recommended) (b) it is somewhere else (ask the path). On yes route to `/plumb:create` in this folder. git is optional; offer `git init` once, the user decides. |
| **Not a git repo, with project markers** (`in_repo: false`) | The opened folder is the project root. Say so in the block; confirm it is the whole project and not a package of a bigger one. |
| **Opened in a subfolder** (`opened` is not `.`) | Use the repo root as `<root>`. Say so in the block ("you opened apps/web"). |
| **Monorepo** | Skill and `PLUMB.md` at the **repo root**. Every UI package is listed in `PLUMB.md` `UI packages:` with its stack, and each one's global CSS is a generated copy in `web.copies`. A package that is not UI is listed as "no UI". |
| **Separate frontend repo** | Skill and `PLUMB.md` in this repo. |
| **Backend-only repo** | Ask "Where will the UI live?" (a) the frontend is in another repo (Recommended): ask for its path, run detect with `--cwd <that path>`, set Plumb up there (it becomes `<root>`), then offer this repo a linked `PLUMB.md` and row, and tell the user to open the frontend repo for UI work; (b) the frontend will live here (create here, platforms chosen in the interview); (c) design only for now (below). |
| **Several UI repos share one system** | One **home** repo owns the tokens (`Role: home`). The others get only a linked `PLUMB.md` and the AGENTS/CLAUDE row pointing at the home skill. The home's `build-tokens.py` can write generated copies into the other repos (their paths in the home tokens' `web.copies`), asked in the home repo. |
| **React Native** (`framework: react-native`, `supported: false`) | Say plainly: React Native themes are not supported in Plumb 1.0.0 (a candidate for 1.1.0). Offer only: design only (Recommended, below), web (when the repo has a web part), or iOS (SwiftUI) / Android (Compose) themes for native apps. Never generate a React Native theme or write React Native components. |
| **Nothing recognised** (`layout: single`, low confidence) | Explore (above). If there really is no UI yet, the project is new: route to `/plumb:create`. |

## Design only

Chosen for a backend repo, a React Native app, or by the user ("design only for now"). The system is made but nothing
goes into an app: `scaffold.py --platforms web --styling css`, no `web_copies`, no components inside the app (reference
starters only, in `<skill dir>/assets/platforms/web/starter/`), and the prototype is HTML only. `PLUMB.md` records the
choice in `UI packages:` ("none yet: design only"). Platforms are added later with `/plumb:update`.

## The skill folder

- Default: `.claude/skills/<project>-design-system/` at the root of the home repo. Claude Code and Copilot CLI both
  load it (Copilot CLI reads `.claude/skills`, `.github/skills`, `~/.copilot/skills`, `~/.agents/skills`).
- Alternatives (from `proposal.alternatives`): `.github/skills/<project>-design-system/`, or `~/.claude/skills/…` for a
  personal system that is not committed (not recommended for a team).
- The name is proposed from the project (`<project>-design-system`) and can be changed.
- Inside a monorepo package, a session may not load root skills. When the user works from a package folder, offer a
  one-line pointer in that package's `AGENTS.md`/`CLAUDE.md` (asked first): `Design system: read
  <relative path>/.claude/skills/<project>-design-system/SKILL.md before any UI change.`

## Linked repos

A repo that uses another repo's system gets only `PLUMB.md` (from `<ROOT>/templates/PLUMB.md`) with:

```
Design system: `../acme-web/.claude/skills/acme-design-system/`
Role: linked
```

The other lines are filled from the home's tokens file (platforms) and this repo (UI packages, UI files, Python); the
commands point at the home's scripts. Check the path holds `SKILL.md` and `assets/tokens/*.tokens.json` before writing;
if not, say so and ask for the right path. Then add the AGENTS/CLAUDE row (from `<ROOT>/templates/agents-row.md`) with
the home's path. Nothing else is copied into a linked repo.

## Moving it later

If the system ends up in the wrong place, or the user changes their placement answer, never move files by hand:

```
python3 "<ROOT>/scripts/scaffold.py" --relocate FROM TO --project-root "<root>" --dry-run   # show every change first
python3 "<ROOT>/scripts/scaffold.py" --relocate FROM TO --project-root "<root>"
```

It moves the skill folder and updates `PLUMB.md` (the `Design system:` line and the commands), the Plumb row in
`AGENTS.md`/`CLAUDE.md`, and the Makefile lines, then runs the moved `build-tokens.py --check` (regenerating once,
because generated headers name the old path). It refuses when `TO` exists and is not empty, is outside the project, or
`FROM` is not a Plumb design-system skill. Show the dry run, ask, then run it.

`python3 "<ROOT>/scripts/scaffold.py" --verify --project-root "<root>"` checks that `PLUMB.md`, the row, the Makefile and the
copy targets agree with where the skill actually is, and prints the `--relocate` command when they do not
(`/plumb:status` runs it too).
