# AGENTS.md — working on the Plumb repo

This repo is **Plumb**, a Claude Code (and GitHub Copilot CLI) plugin that creates, extracts,
audits and maintains a project's design system, so every screen an agent builds uses the same
tokens, components and words. A project gets a `<project>-design-system` skill: one W3C token file
that generates the web, iOS and Android themes, plus component specs, accessibility, motion,
dark mode with computed contrast evidence, and an audit that must exit 0. Always with a human in
the loop.

**This is the only instructions file.** `CLAUDE.md` just imports it (`@AGENTS.md`), so Claude Code,
Copilot CLI and other agent tools all read the same text. Edit this file, never `CLAUDE.md`.

## 1. Read first

| Need | Read |
|---|---|
| What Plumb is, every decision | `docs/specs/2026-10-11-plumb-design.md` |
| How a release is built: tasks, contracts, owner amendments | `docs/plans/*-build-plan.md` (newest last) |
| The complete usage guide | `docs/USAGE.md` |
| What a project gets, as a page | `docs/what-you-get.html` (offline; check it headless in both themes when you change it) |
| User-facing overview | `README.md`, `plugins/plumb/README.md` |
| Every script command and flag, "use it when…", the shared rules | `plugins/plumb/reference/` |
| What changed per version | `plugins/plumb/CHANGELOG.md` |
| How to test on a machine by hand | `TEST.md` (both CLIs, Kiro pending its live check) |
| The exact output of `create` | `examples/caredesk/` (added after the owner validates it, Task 19) |
| Reference implementations (**read only, never write there**) | below |

The spec is the source of truth while Plumb is being designed; update this file when it changes
the layout or the rules.

**Reference implementations.** Read them, copy the approach, never write in their folders (copy
to a temporary folder to test against them):

- **The target shape of a generated design system:** a hand-built one at
  `~/Desktop/Zidane/keel/.claude/skills/keel-design-system/` (SKILL.md, design.md, the W3C
  tokens JSON, `scripts/build-tokens.py`, `scripts/audit.sh`, `references/`,
  `assets/platforms/`), and how its project uses it (`AGENTS.md` "read before you work" row,
  `Makefile` `tokens` / `tokens-check`).
- **The target shape of the plugin and every development practice:** Slate,
  `~/Desktop/Projects/gdtc-ai-products/slate/` (`github.com/Zidane786/slate`): repo files, CI,
  releases, hooks for both tools, the versioned project copy and `/slate:upgrade`.
- **Visual output** (direction specimens, audit reports, what-you-get): the Effective HTML skills
  (`html`, `design-artifact`, `html-prototype`, `html-diagram`). Use them, and have the plugin use
  them when installed; fall back to Plumb's own simple HTML when they're not.
- **Audit test inputs:** the two HTML prototypes in
  `~/Desktop/Projects/gdtc-ai-products/agentathon-2026/practice-week/`
  (`caredesk-prototype.html`, `godesk-prototype.html`).

## 2. Layout

Marked *in progress* = planned in the build plan, not in the tree yet; remove the mark when it lands.

```
.claude-plugin/marketplace.json      marketplace "plumb" → plugins/plumb
.claude/settings.json                 repo settings for agents (no AI attribution)
plugins/plumb/                        the installed plugin (only this folder ships)
  .claude-plugin/plugin.json          name + VERSION (source of truth for the plugin version)
  skills/<name>/SKILL.md              the 10 commands: init create extract prototype tour audit ux
                                      update upgrade status
  reference/                          shared reference all skills link (scripts, rules, prototypes, tours, …)
  assets/skill/                       the design-system skill template copied into projects
    SKILL.md.tmpl  design.md.tmpl     filled from the interview answers
    references/                       reference templates (web/, mobile/ios, mobile/android)
    assets/                           icons, tokens, platforms/web (tokens.css templates)
    scripts/                          _plumb.py (shared core), build-tokens.py, audit.py,
                                      build-prototype.py: copied into projects, tested here
    templates/                        specimen, audit report, prototype shell, screens page and
                                      proposal index templates, player.js / player.css (the walkthrough player)
  scripts/                            plugin-side helpers the skills run (not copied into projects)
    detect.py  scaffold.py            repo layout + stack detection; copy/fill the template
    version.py  screenshot.py  kiro.py   project vs plugin version; headless screenshots; Kiro install
  hooks/                              hooks.json, run.sh / run.cmd, _hooklib.py, session_start / pre_edit / stop_check
  templates/                          PLUMB.md, agents-row.md, decision-entry.md, Makefile.snippet,
                                      directions.html (the fallback directions page)
  upgrades/<version>.md               per-release "What's new" + upgrade steps (README.md explains)
  CHANGELOG.md  README.md
examples/caredesk/                    golden example of `create` (regression fixture; after validation, Task 19)
tests/                                pytest suite; fixtures/ holds audit cases and sample projects;
                                      conftest.py enforces the skip rules
docs/                                 specs/, plans/, USAGE.md (the complete guide), what-you-get.html
scripts/                              repo tooling: release_notes.py, check_version_bump.py
.github/                              workflows/test.yml (CI: Windows/macOS/Linux × Python 3.9/3.13),
                                      workflows/release.yml (publishes vX.Y.Z from the CHANGELOG on
                                      merge), dependabot.yml (keeps the Actions up to date)
TEST.md                               hands-on test guide for any machine
```

## 3. Rules that must hold in every change

- **Standard library only**, Python **3.9+**, in everything that ships (hooks, the token
  generator, the audit). No pip dependencies at runtime, no npm or npx for Plumb's own tooling.
  Generated web output may target the project's stack (Tailwind, CSS variables, shadcn).
- **Works on Windows, macOS, Linux, over SSH and in tmux.** Every Python entry point reconfigures
  stdout/stderr to UTF-8; every text read/write and subprocess call names `encoding="utf-8"`
  (`tests/test_portability.py` enforces both). UTF-8 + `\n` for every file write, pathlib, no
  `shell=True`, no POSIX-only calls without a Windows path. Hooks go through `hooks/run.sh`
  (finds python3 / python / py -3); on Windows, Copilot CLI runs each hook's `powershell`
  command, which goes through `hooks/run.cmd` (py -3 / python / python3).
- **One token source.** In a project, values live only in `<project>.tokens.json`; generated
  themes are never edited by hand. The guard hook blocks hand edits to them; don't weaken it.
- **Every error/refusal is actionable:** `error: …` then `fix: <exact command>` or
  `ask the user: …`. A test asserts this for every refusal path.
- **Backwards compatible.** Existing projects must keep working. Token and format changes are
  additive and go through `migrate`; `/plumb:upgrade` never deletes a project's values.
- **Design with the user before building.** New features and commands go through brainstorming:
  one question at a time (the question tool, options with a recommendation), the agreed design
  written to `docs/specs/`, a build plan in `docs/plans/`, and the user's approval of both before
  any code.
- **Human in the loop, always.** Skills ask one question at a time with options and a
  recommendation, never write into a project without saying where, never merge, never
  force-push. In this repo: never push to `main` (the ruleset blocks it); every change goes
  through a branch and a PR that the user merges.
- **A project's design system is `<project>-design-system`**, a skill at
  `.claude/skills/<project>-design-system/` by default (the repo root in a monorepo; the frontend
  repo when frontend and backend are separate). Both tools read it there: Copilot CLI loads skills
  from `.claude/skills`, `.github/skills`, `~/.copilot/skills` and `~/.agents/skills`.
- **Prototype first.** UI work goes prototype → the user approves → build. Hooks refuse a new
  page or route with no approved screen; skills never skip it for visual changes.
- **Light and dark, everywhere.** Every colour token has a dark value; a missing one is an audit
  error unless marked same-in-dark. Pages never write `dark:` overrides. Every generated page
  and check covers both themes. Light-only is allowed only as a recorded decision
  (`Themes: light-only` in `PLUMB.md` + the decision log).
- **No downloads.** Plumb and its skills never install or download anything (no pip, npm,
  browsers, fonts): they tell the user what is missing, ask, and wait.
- **Plumb's own files are guarded in projects.** The copied `[P]` files (`scripts/*.py`,
  `templates/*`) and the plugin's files are never hand-edited there; improvements go upstream to
  this repo and reach projects through `/plumb:upgrade`. The guard is off here (no `PLUMB.md`).
- **Scripts are the floor, not the ceiling.** `detect.py` is a first guess: the skill verifies it
  and the user confirms before anything is written. `audit.py` rules catch what can be
  expressed; an agent review pass covers the rest, and recurring findings become new rules.
- **Hooks run only the plugin's own code.** They never import or run a project's copied
  scripts (a cloned repo must not get code run by containing a `PLUMB.md`); the project is data
  only. Every hook git call goes through the hardened helper (config overrides as environment
  pairs, no lazy fetch, absolute git from PATH, shared 3 s budget, fail open). Keep
  `SECURITY.md` "Trust boundary" exact when this changes.
- **Exceptions by path, never by comment.** Audit allowances live on `PLUMB.md`'s allow list
  (e.g. `components/ui/**`); no `// plumb-ignore` style comments.
- **Generated pages load nothing from the network:** no CDN, no hosted fonts; system font
  stacks or the project's own files. Generated files start with a `GENERATED … do not edit`
  header.
- **Every design choice goes in the decision log** (`docs/design/decisions.md` in a project):
  directions, variants, screens, light-only. The prototype shows it.
- **Kiro is supported too** (skills via `scripts/kiro.py`, hooks through an adapter in
  `_hooklib.py`), built from Kiro's documented formats; the live check on a real Kiro is pending.
- **Lean skills.** `SKILL.md` files stay short; details go in `reference/` and are loaded only
  when needed.
- **Product text never mentions internal projects.** Plumb is generic.
- **Claude Code and GitHub Copilot CLI, one plugin.** Copilot CLI loads the same
  `.claude-plugin/` manifest, skills and Claude-format `hooks.json`. Hook code must work for both:
  Copilot sends apply_patch text for edits, no `permission_mode`, `tool_result` (not
  `tool_response`), hides exit-2 stderr (refuse with JSON when `COPILOT_CLI` is set) and needs
  `{"additionalContext"}` at session start. Every hook has a `powershell` command (Windows
  Copilot). `tests/test_copilot.py` pins all of this. VS Code Copilot Chat isn't supported;
  don't add half-support.

## 4. Develop and test

```
uv run --with pytest pytest -q                  # full suite
uv run --python 3.9 --with pytest pytest -q     # oldest supported Python
claude plugin validate --strict .
claude plugin validate --strict plugins/plumb
```

- Write tests first for every change: happy path + every refusal. The token generator has a test
  for every platform output, the drift check and additive migration; every audit rule has a
  fixture that fails and a false-positive fixture that passes.
- Contrast is computed, never guessed; the evidence goes in the project's `dark-mode.md`.
- Any HTML Plumb generates (specimens, audit reports, what-you-get) gets a real-browser check,
  **headless only**: your own script, e.g. `uv run --with playwright python x.py` with
  `launch(headless=True)`. Never open a visible browser window.
- Live-test skills in a throwaway repo: `claude --plugin-dir plugins/plumb`, and in Copilot CLI
  (`copilot plugin marketplace add Zidane786/plumb`, `copilot plugin install plumb@plumb`,
  restart). Never write in a reference project; copy it to a temporary folder first.
- **Proof runs before a release that changes create, extract or audit:** regenerate
  `examples/caredesk/` (CareDesk Lite: clinic front desk, Next.js + Tailwind, calm clinical
  register) and diff it; run `extract` on a temporary copy of the reference design system's
  project and compare (accent `#14857F`, type scale `display, h1, h2, h3, body-lg, body-md,
  label-sm, sm, xs`); run `audit` on that copy and on the two prototypes and look at the HTML
  reports.
- **CI (`.github/workflows/test.yml`)** runs on every PR and push to `main`, but the full suite
  runs only when one of these changed: `plugins/**`, `tests/**`, `examples/**`,
  `scripts/**`, `.github/workflows/**`, `.claude-plugin/**`, `.gitattributes`. Docs-only changes
  (README, TEST.md, CLAUDE.md, AGENTS.md, SECURITY.md, `docs/**`) pass in seconds with "no code
  changed". CI installs Playwright + Chromium and runs the browser tests on every OS; unexpected
  skips fail the run (`PLUMB_STRICT_SKIPS=1`, `tests/conftest.py`: a skip reason must start with
  `requires macOS`, `requires Windows`, `requires POSIX` or `requires xcrun`, e.g.
  `requires POSIX: FIFO`; `tests/test_skip_reasons.py` pins the list). A manual run always runs
  everything. Keep this list and the workflow's list in step.
- `tests/test_docs_consistency.py` fails if a skill, reference or user doc (README.md, the plugin README,
  `docs/USAGE.md`, TEST.md, `docs/what-you-get.html`) mentions a command that doesn't exist, a skill doesn't link
  the reference, a link points nowhere, `docs/USAGE.md` lacks a section for a command, a README doesn't link
  `docs/USAGE.md` near the top, a message the docs quote is no longer printed by the code, the what-you-get page
  loads anything from the network, TEST.md's expected output no longer matches the code that prints it, or an
  internal project name appears under `plugins/` or in the user docs (extra names, uncommitted:
  `PLUMB_INTERNAL_NAMES=a,b`) — keep it green.
  `tests/test_portability.py` covers every `.py` in `plugins/`, `scripts/` and `tests/`.
- **Parallel work, safely.** Each task runs in its own isolated git worktree, branched from
  `feat/1.0.0`, and is reviewed before it merges. Merge one at a time, with a merge commit. After
  every merge run the full suite, Playwright included, on Python 3.13 and 3.9 before pushing.
  Never force-push.

## 5. Keeping docs in step (do this in the SAME change as the feature)

Every feature, fix or behaviour change updates **all** that apply, before it's considered done:

- [ ] **`docs/USAGE.md`**, the complete usage guide (every command, flag and flow).
- [ ] **`plugins/plumb/reference/`** — new/changed commands and flags, "use it when…".
- [ ] **Skills** (`plugins/plumb/skills/*/SKILL.md`) that should use or mention it.
- [ ] **`plugins/plumb/templates/PLUMB.md`** if projects need to know or configure it.
- [ ] **Files copied into projects** (`plugins/plumb/assets/`) and **`examples/caredesk/`**,
      regenerated so the golden example matches.
- [ ] **`README.md`** and **`plugins/plumb/README.md`** for anything user-visible.
- [ ] **`plugins/plumb/CHANGELOG.md`** — plain-words entry under the next version.
- [ ] **`plugins/plumb/upgrades/<next-version>.md`** — "What's new" line + upgrade step if
      existing projects need anything (scripts, tokens migrate, PLUMB.md, questions).
- [ ] **`TEST.md`** — add or adjust the hands-on check for the feature (and the expected result).
- [ ] **Spec** (`docs/specs/…`) for new decisions or commands.
- [ ] **Tests** — unit tests, docs-consistency, portability and Copilot checks as relevant.
- [ ] **This file (`AGENTS.md`)** whenever layout, rules or workflow change, in the same change.

## 6. Releasing a version

**Every PR that changes `plugins/**` is a release.** CI (`scripts/check_version_bump.py`) fails
unless it bumps the version above `main`'s and adds that version's CHANGELOG section; there is no
"Unreleased" section. Claude Code only updates installed plugins when the version changes, so an
unversioned change would never reach users. Docs-only PRs outside `plugins/` (README, TEST.md,
this file, `docs/**`) need no bump: CI passes in seconds and nothing is released.
Each CHANGELOG section lists **only** what changed since the previous version; a released
version's section is frozen (the same CI check fails if it changes). New changes go under the
new version.

**Versioning (semver).** The first release is **1.0.0**, with every command, hook and platform.
After that: **patch** (1.0.x) for fixes and wording, **minor** (1.x.0) for new features, rules,
tokens or options that existing projects keep working with, **major** (x.0.0) only for major
work: a change that needs `/plumb:upgrade` to reshape existing projects, or drops something.

1. Bump the version in **all** of: `plugins/plumb/.claude-plugin/plugin.json`, the script
   headers (token generator, audit), `templates/PLUMB.md` (first line), and the tokens schema
   version + `migrate` if the format changed.
2. Finish `CHANGELOG.md` and `upgrades/<version>.md` (What's new first, then steps). The
   CHANGELOG section for the version is `## X.Y.Z — YYYY-MM-DD` with the headings **Highlights**,
   **Added**, **Changed**, **Fixed**, **Security**, **Removed**, **Upgrade notes** (leave out
   empty ones). `tests/test_release_notes.py` enforces this; preview the notes with
   `python3 scripts/release_notes.py`.
3. Full suite on 3.13 and 3.9, `claude plugin validate --strict`, `TEST.md` on at least one
   machine (Claude Code and Copilot CLI), CI green on all three OSes.
4. Branch `feat/<version>`, draft PR with summary, verification and follow-ups; merge only when
   the user says so. Default branch is `main`, protected by a ruleset: no direct pushes (PR
   required, squash only, review threads resolved), all 6 CI checks must pass, no force-push or
   deletion, no bypass. Merged branches are deleted automatically.
5. **Releases are automatic:** when a merge to `main` carries a new version in `plugin.json`,
   `.github/workflows/release.yml` tags `vX.Y.Z` and publishes a GitHub Release with that
   CHANGELOG section. Don't create release tags by hand (tags `v*` are protected).

## 7. Commits

Small, focused commits: `<area>: <what changed>` with a short body listing verification. Never
commit generated files (`__pycache__`, `.pytest_cache`, `.DS_Store` — see `.gitignore`).
**No AI attribution** anywhere: no `Co-Authored-By` trailer, no "Generated with" line in commits
or PR descriptions (`.claude/settings.json` turns Claude Code's off). Tell subagents the same.
