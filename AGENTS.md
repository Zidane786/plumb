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
| How a release was built (contracts) | `docs/plans/*-build-plan.md` (newest last) |
| What a project gets, as a page | `docs/what-you-get.html` |
| User-facing overview | `README.md`, `plugins/plumb/README.md` |
| Every script command and flag, "use it when…" | `plugins/plumb/reference/` |
| What changed per version | `plugins/plumb/CHANGELOG.md` |
| How to test on a machine by hand | `TEST.md` |
| The exact output of `create` | `examples/caredesk/` |
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

```
.claude-plugin/marketplace.json      marketplace "plumb" → plugins/plumb
.claude/settings.json                 repo settings for agents (no AI attribution)
plugins/plumb/                        the installed plugin (only this folder ships)
  .claude-plugin/plugin.json          name + VERSION (source of truth for the plugin version)
  skills/<name>/SKILL.md              /plumb:init create extract audit update upgrade status
  assets/                             the design-system skill template copied into projects
                                      (SKILL.md, design.md, tokens, references, build-tokens.py, audit)
  hooks/                              hooks.json, run.sh / run.cmd (python launchers), the hook scripts
  templates/                          PLUMB.md and the CLAUDE.md / AGENTS.md rows for projects
  reference/                          shared reference all skills link
  upgrades/<version>.md               per-release "What's new" + upgrade steps
  CHANGELOG.md  README.md
examples/caredesk/                    golden example: the full skill `create` produces (a regression fixture)
tests/                                pytest suite
.github/workflows/test.yml            CI: Windows/macOS/Linux × Python 3.9/3.13
.github/workflows/release.yml         publishes vX.Y.Z releases from the CHANGELOG on merge
.github/dependabot.yml                keeps the GitHub Actions up to date
scripts/release_notes.py              prints a version's release notes from the CHANGELOG
scripts/check_version_bump.py         CI guard: plugin changes carry a new version + CHANGELOG section
TEST.md                               hands-on test guide for any machine
docs/                                 specs, build plans, what-you-get.html
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
  skips fail the run (`PLUMB_STRICT_SKIPS=1`, `tests/conftest.py`). A manual run always runs
  everything. Keep this list and the workflow's list in step.
- `tests/test_docs_consistency.py` fails if a skill/doc mentions a command that doesn't exist,
  or a skill doesn't link the reference — keep it green.

## 5. Keeping docs in step (do this in the SAME change as the feature)

Every feature, fix or behaviour change updates **all** that apply, before it's considered done:

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
- [ ] **This file (`AGENTS.md`)** if the rules, layout or workflow changed.

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
