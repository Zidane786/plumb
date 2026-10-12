# Plumb's scripts: every command and flag

Skills link here instead of repeating the list. `<script> --help` is the final word on flags.

**Who runs what.** The project's design-system skill holds its own copies of the engine
(`<skill>/scripts/build-tokens.py`, `audit.py`, `build-prototype.py`, `_plumb.py`): those are what the hooks, `make`,
CI and the skills run, so everyone applies the same rules. `<skill>` is the `Design system:` path in `PLUMB.md`. The
plugin's helpers (`detect.py`, `scaffold.py`, `version.py`, `screenshot.py`) run from `<ROOT>/scripts/`, where `ROOT` is
the plugin root (`${CLAUDE_PLUGIN_ROOT}`, or the skill's base directory + `/../..`).

**Python.** Every command starts with the project's Python command from `PLUMB.md` (`Python: \`python3\``; `py -3` or
`python` on Windows). Below it is written `python3`. Run from the project root. Commands never need a shell feature
(no pipes, no `cd … &&`).

**Errors.** Every script prints `error: <what>` then `fix: <exact command>` (or `ask the user: …`) and never a
traceback. Bad input exits 2. Do what the `fix:` line says, or ask the user when it says so; never guess.

**Never by hand.** Generated files (`[G]`: `tokens.css` and its copies, `tailwind.tokens.js`, the Swift and Kotlin
themes, `specimen.html`, `prototype.html`, `screens.html`, `prototype/screens.json`, `tours/*.html`, the proposal pages,
`audit-*.html`) are
written only by these scripts; Plumb's own files (`[P]`: `<skill>/scripts/*`, `<skill>/templates/*`,
`assets/platforms/README.md`) only by `scaffold.py` during `/plumb:upgrade`. The edit check refuses hand edits to both.

## build-tokens.py: the tokens → every theme

`python3 <skill>/scripts/build-tokens.py [--check | --contrast | --migrate | --css-vars] [--root SKILL_DIR] [--project PATH]`

| Flag | Does |
|---|---|
| (none) | Writes every output from the one tokens file: web CSS (`tailwind-v4`, `tailwind-v3` + `tailwind.tokens.js`, or `css`), the copies in `$extensions.plumb.web.copies`, the iOS and Android themes for the platforms listed, the contrast block in `references/dark-mode.md`, `<docs>/specimen.html`, and the token region of `prototype.html`, `screens.html`, `tours/*.html` and the generated proposal pages when they exist. Deterministic: running it twice changes nothing. |
| `--check` | Writes nothing; exit 1 naming every stale or missing output, copy or prototype token block. |
| `--contrast` | Rewrites only the contrast evidence block of `references/dark-mode.md` (exit 2 if the file or its markers are missing). Exits 0 even when pairs fail: the audit is the gate. |
| `--migrate` | Brings the tokens JSON up to the current schema by **adding** missing settings; never removes or changes a value. Used by `/plumb:upgrade`. |
| `--css-vars` | Prints the tokens as plain CSS custom properties (`:root`, the md breakpoint, `.dark` and `prefers-color-scheme`): the block prototypes and proposals inline. |
| `--root SKILL_DIR` | The design-system skill folder (default: the skill this script sits in). |
| `--project PATH` | The project root when no `PLUMB.md` is found above the skill. |

Exit codes: 0 ok · 1 stale (`--check`) · 2 bad input (`error: <token>: …`).

## audit.py: the design audit

`python3 <skill>/scripts/audit.py [PATHS...] [--json] [--html [OUT.html]] [--add-review REVIEW.json] [--no-tokens] [--root SKILL_DIR] [--project PATH]`
`python3 <skill>/scripts/audit.py --quick FILE [--before -|PATH]`

| Flag | Does |
|---|---|
| `PATHS...` | Files or folders to check (default: the whole project, narrowed by `PLUMB.md`'s `UI files:`). Put flags after them. |
| (full mode) | Every per-file rule, then the cross-file rules (contrast, drift, prototype fidelity, suggestions). Prints `file:line: <severity> <rule>: <message>` + `  fix:` per finding and a summary. Rules: [rules.md](rules.md). |
| `--json` | The findings as JSON: `{"version","mode","checked","errors","warnings","suggestions","findings":[{"rule","severity","file","line","message","fix"}]}` (+ `scales` in inconsistency-only mode, + `agent_review` with `--add-review`). |
| `--html [OUT.html]` | Also writes the report page (default `<docs>/audit-YYYY-MM-DD.html`): summary, Issues, Improvements ranked by impact, filters, light and dark. Terminal output and exit code are unchanged. Write `--html=OUT.html` or put it after the PATHS. |
| `--add-review REVIEW.json` | With `--html`: merges the agent's review (a JSON list of `{severity, file, line?, message, fix, why?}`) into the report as a separate **Agent review** section, each finding marked so. Never changes the terminal findings, the counts or the exit code. Bad file → exit 2 naming the entry and key, no report written. See [rules.md](rules.md#agent-review-not-a-rule). |
| `--no-tokens` | Inconsistency-only mode even when a tokens file exists (infers the scales from the code). Automatic when there are no tokens yet. |
| `--quick FILE` | One file, only the errors an edit adds, JSON out (what the edit check runs). `--before -` reads the old text on stdin; `--before PATH` from a file; without it the file counts as new. Never runs the cross-file rules. |
| `--inventory` | Added for `/plumb:extract`: every value in use with counts and `file:line`, and the proposed clusters (see the extract skill). |
| `--root`, `--project` | As for build-tokens.py. |

Exit codes: 0 no errors (warnings and suggestions allowed) · 1 errors found · 2 nothing checked or bad input.

## build-prototype.py: the main prototype and its map

`python3 <skill>/scripts/build-prototype.py [--check] [--map ID --route ROUTE --files GLOB ...] [--approve ID] [--synced ID] [--root SKILL_DIR] [--project PATH]`
`python3 <skill>/scripts/build-prototype.py --proposal NAME [--check]`

| Flag | Does |
|---|---|
| (none) | Assembles `<docs>/prototype.html` (the clickable app, the walkthrough player, decisions), `<docs>/screens.html` (every screen × state, light and dark side by side, control states) and `<docs>/prototype/screens.json` from `<docs>/prototype/screens/*.html`, `<docs>/decisions.md` and `<docs>/prototype/tours/*.json`; writes `<docs>/tours/<tour>.html` per tour. No timestamps: rebuilding gives the same bytes. |
| `--check` | Writes nothing; exit 1 naming each stale or missing page (or a stale token block). A tour step naming a screen, state or element that does not exist exits 2. |
| `--map ID --route ROUTE --files GLOB ...` | Records a screen's route (`/billing`, `/b/:id`) and source files (globs from the project root) and their hash, the baseline the audit compares against. `status` becomes `built` once every glob matches a file. Confirm route and files with the user first. |
| `--approve ID` | Records the user's approval: git `user.name` (else `$USER`/`%USERNAME%`), today's date, the screen file's hash; clears "synced from code". Run it only after the user said yes to that screen. Editing the screen afterwards makes the approval stale. |
| `--synced ID` | Marks a screen updated to match code that was already built (a small fix, code written before Plumb); listed for the user to confirm, never blocking. |
| `--proposal NAME` | Builds `/plumb:prototype`'s variants instead of the main prototype: for each `<docs>/prototype/proposals/NAME/<variant>/screens/*.html` (+ optional `idea.md`), that variant's `prototype.html` and `screens.html` (both views, light and dark, the token block inlined), and `NAME/index.html` with the variants side by side. Generated and byte-stable; `screens.json` is not touched. With `--check`, exit 1 when one is stale. Does not combine with `--map`, `--approve` or `--synced`. The main build (and build-tokens.py) refreshes the token block of every generated proposal page. |
| `--root`, `--project` | As for build-tokens.py. |

`screens.json` is written only by this script (never by hand). Every command rebuilds the pages. **A broken tour does not
block the map:** `--map`, `--approve` and `--synced` still write `screens.json`, print a warning naming the tour problem,
leave the pages as they were and exit 0; the next build or `--check` exits 2 on the tour until it is fixed.

Exit codes: 0 ok · 1 stale (`--check`) · 2 bad input (a screen file with no `data-screen`, a broken tour, …).

## scaffold.py (plugin): lay the skill into a project, move it, verify it

`python3 "<ROOT>/scripts/scaffold.py" --project-root P --name NAME --skill-dir D --platforms web,ios,android --styling tailwind-v4|tailwind-v3|css [--answers answers.json] [--docs-dir docs/design] [--dry-run]`

| Flag | Does |
|---|---|
| `--project-root P` | The project root (required in every mode). |
| `--name`, `--skill-dir`, `--platforms`, `--styling` | Required to lay the skill: product name, skill folder relative to the root (`.claude/skills/<project>-design-system`), platforms, web styling. |
| `--answers answers.json` | The interview answers (colours, type scale, spacing, radius, motion, icons, PLUMB.md values…); see the script's docstring. |
| `--docs-dir` | Where the design pages live (default `docs/design`). |
| `--dry-run` | Prints `would write:` / `skip:` and writes nothing. |
| `--relocate FROM TO` | Moves the skill folder and updates every reference (PLUMB.md, the AGENTS.md/CLAUDE.md row, Makefile), then runs the moved `build-tokens.py --check` (regenerating once when only the header paths changed). |
| `--verify` | Checks that PLUMB.md's skill path exists and that the AGENTS/CLAUDE row, the Makefile and the copy targets point at it; prints `ok:` / `problem:` / `note:` and the `--relocate` command when the skill sits elsewhere. Exit 1 on any problem. |

**Ownership.** `[P]` files (`scripts/*.py`, `templates/*`, `assets/platforms/README.md`) are always overwritten
(`wrote:`); `[Y]` files are written only when absent (`skip: … (yours, kept)`). That is why `/plumb:upgrade` re-runs the
same command to refresh Plumb's files: the project's own files are never touched. Exit codes: 0 ok (`--verify`: 1 on
problems) · 2 bad input.

## detect.py (plugin): repo layout and stack

`python3 "<ROOT>/scripts/detect.py" --cwd PATH [--json]`: where the project and its UI live (git root, monorepo
packages, frameworks, styling, UI file counts, an existing `PLUMB.md`). Read-only; a first guess that `/plumb:init`
always shows the user to confirm.

## version.py (plugin): project vs plugin version

`python3 "<ROOT>/scripts/version.py" --project P --plugin "<ROOT>" [--json]`

| Flag | Does |
|---|---|
| `--project P` | The project root (or its `PLUMB.md`); the version is `PLUMB.md`'s first line `<!-- plumb vX.Y.Z · … -->`. |
| `--plugin R` | The plugin root (its `.claude-plugin/plugin.json` and `upgrades/`). |
| `--json` | `{"project": "1.0.0", "plugin": "1.2.0", "state": "same" \| "older" \| "newer", "between": ["1.1.0", "1.2.0"]}`: `between` is every `upgrades/<v>.md` with project < v ≤ plugin, ascending, compared as numbers; empty unless `older`. |

`older` → offer `/plumb:upgrade`. `newer` → a teammate upgraded with a newer plugin: print the commands for the user to
run in their own terminal (`claude plugin marketplace update plumb`, then `claude plugin update plumb@plumb`; in Copilot
CLI `copilot plugin marketplace update plumb`, then `copilot plugin update plumb@plumb`) and wait; never run them
yourself, and never downgrade the project.
Exit codes: 0 · 2 bad input (no `PLUMB.md`, no version line, a damaged `plugin.json`).

## screenshot.py (plugin): a headless screenshot with a browser already installed

`python3 "<ROOT>/scripts/screenshot.py" URL_OR_FILE --out PNG [--width W] [--height H] [--theme light|dark] [--wait MS] [--timeout S] [--browser PATH]`

| Flag | Does |
|---|---|
| `URL_OR_FILE` | An `http(s)://` or `file://` URL, or a local HTML file, optionally with a `#fragment`: `docs/design/prototype.html#screen-booking/empty` opens that screen in that state. |
| `--out PNG` | The PNG to write (folders created; an existing file is replaced only by a good shot). |
| `--width`, `--height` | Viewport in CSS px (default 1280 × 900; 390 × 844 for a phone). |
| `--theme` | `light` (default) or `dark`: the page's `prefers-color-scheme`. |
| `--wait MS` | Page time before the shot, so scripts can render (default 2000). |
| `--timeout S` | Stops a browser that hangs (default 60). |
| `--browser PATH` | Use this browser executable instead of searching. |

It finds Chrome, Edge or Chromium already on the machine: the PATH names `google-chrome`, `chromium`,
`chromium-browser`, `microsoft-edge` (and `-stable`, `chrome`, `msedge`); macOS app bundles in `/Applications` and
`~/Applications`; Windows `chrome.exe` / `msedge.exe` under Program Files and LocalAppData. It runs it headless with a
throwaway profile and background networking off. **It never installs or downloads a browser.** Exit codes: 0 written ·
1 the browser ran but wrote no screenshot (or hung) · 2 bad input · 3 no browser:
`note: visual comparison skipped: no browser found` + `fix:`; skip the visual part, say so in the report, and run every
other check. A `#fragment` that scrolls to an anchor can come out blank in headless Chrome and Edge; the prototype's
`#screen-ID/STATE` routes work.

**Which browser, in order:** (1) the agent's own browser tool, if it has one and the organisation allows it; (2)
`screenshot.py` (a Chrome, Edge or Chromium already installed); (3) none: skip the visual part with the `note:` and its
`fix:` line in the report. Playwright is never installed for a project; it is used only in Plumb's own CI.
