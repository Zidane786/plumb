# Plumb

**Plumb keeps a project's design true.** It is a plugin for Claude Code and GitHub Copilot CLI that creates,
extracts, audits and maintains a project's design system, so every screen an agent builds uses the same colours, type,
spacing, components and words, on the web and on phones. You stay in charge: Plumb asks one question at a time and
writes nothing without your OK.

- **New project:** Plumb asks what you're building and who it's for, walks you through the design decisions one at a
  time, shows 2–3 directions to pick from, and writes a design-system skill into the project: one token file that
  generates the web, iOS and Android themes, plus component specs, accessibility and dark-mode rules with computed
  contrast, and an audit.
- **Existing project:** Plumb reads the UI you already have, lists every colour, size and component actually used,
  merges near-duplicates, and builds the same skill from what's there, plus a prototype of every existing screen.
- **Prototype first:** every new or changed screen is a clickable prototype you approve before it's built, with every
  state in light and dark, and walkthroughs you can play for a client.
- **While an agent builds:** hooks stop edits that bypass the design system and check the changed screens before the
  agent hands back.

**The complete guide: [docs/USAGE.md](docs/USAGE.md)** (install, a walkthrough for every situation, every command
with an example session, prototypes and tours, hooks, teams, troubleshooting, FAQ).
**What a project gets, as a page: [docs/what-you-get.html](docs/what-you-get.html)** (download it and open it from
disk; it works offline).

## Install

In a terminal:

```
claude plugin marketplace add Zidane786/plumb
claude plugin install plumb@plumb
```

Or inside Claude Code:

```
/plugin marketplace add Zidane786/plumb
/plugin install plumb@plumb
```

Then, inside your project:

```
/plumb:init
```

Plumb needs **Python 3.9+** (standard library only; on Windows `py -3`, `python` or `python3`). git is optional.

### GitHub Copilot CLI

The same plugin works in Copilot CLI: the same skills, hooks and commands.

```
copilot plugin marketplace add Zidane786/plumb
copilot plugin install plumb@plumb
```

Restart Copilot (`/restart`), then run `/plumb:init` in your project. Update with
`copilot plugin marketplace update plumb` and `copilot plugin update plumb@plumb`, then `/restart`. On Windows the
hooks run through PowerShell. VS Code's Copilot Chat isn't supported.

### Kiro (preview)

Kiro has no plugin marketplace, so a script copies Plumb's skills and hook files in, one scope per run:
`python3 <plumb>/plugins/plumb/scripts/kiro.py install` (your home folder) or `… install --project <folder>` (that
workspace only). It lists every path and asks first (`--yes` skips the question); run it again after updating Plumb.
The commands are `/plumb-init`, `/plumb-create`, …. This was built from Kiro's documented formats; **the live check on
a real Kiro is pending**. See
[docs/USAGE.md](docs/USAGE.md#kiro-built-from-kiros-docs-live-check-pending).

## Update to a new version

**Easiest — turn on auto-update once.** Inside Claude Code run `/plugin`, open the **Marketplaces** tab → **plumb** →
**Enable auto-update**.

**Or update by hand.** In a terminal:

```
claude plugin marketplace update plumb
claude plugin update plumb@plumb
```

**Then** load the new version (`/reload-plugins`, or restart Claude Code) and, in each project, run:

```
/plumb:upgrade
```

The session-start line tells you when a project is older than the plugin. `/plumb:upgrade` shows **what's new** for
every version in between, replaces Plumb's own scripts and templates in the project, migrates the tokens file by adding
only (it never deletes or changes your values), runs that version's steps asking before each, records the upgrade in
`PLUMB.md`, checks until healthy, and shows the diff for you to commit. It never runs by itself.

## The ten commands

| Command | Use it when | What it does |
|---|---|---|
| `/plumb:init` | First time in a project | Finds the right home (monorepo, separate frontend, parent folder, linked repos), shows what it found and waits for your OK, routes to create or extract, then wires Plumb in: `PLUMB.md`, the `AGENTS.md`/`CLAUDE.md` row, Makefile targets, the checks, the Slate review check. Re-run: status, resume, upgrade offer. |
| `/plumb:create` | A new project | The product first, then platforms, then each design decision with a recommendation, 2–3 directions on one page, then (after you approve the token set and the files) the design system, contrast evidence, starter components that pass the audit, and prototypes of the key screens. |
| `/plumb:extract` | A project with UI already | Inventories every colour, font, size, spacing, radius, shadow and motion value in use, clusters near-duplicates into a clean token set you confirm group by group, builds the same design system and a prototype of every route, and audits what doesn't match yet. |
| `/plumb:prototype` | A new screen, tab, flow or interaction, or a visible change to one | 2–3 variants on your design system, each clickable and with every state in light and dark; you pick and approve one; it joins the main prototype with a default walkthrough. The approved screen is the reference to build. |
| `/plumb:tour` | A client demo, training, onboarding, a design review, what's new | Writes a custom walkthrough the prototype plays in guide mode or play mode (captions, callouts, pointing, chapters, "your turn" steps), plus a standalone page to share. |
| `/plumb:audit [fix \| improve]` | Any time | Every rule, contrast in light and dark, drift, prototype fidelity, then an agent review; an HTML report, a terminal summary, an exit code. `fix` repairs issues group by group with your OK; `improve` ranks improvements to the screens and the system. Offers Slate tickets. |
| `/plumb:ux` | After building a screen or flow | A deep UX review against the prototype, your UX rules, usability heuristics, accessibility beyond contrast and a visual polish pass, with screenshots when a browser is available. |
| `/plumb:update` | The design changes | Change or add tokens and components, add a platform (web, then iOS and Android), improve a part, or apply the audit's system suggestions; regenerates everything, records the decision, audits. |
| `/plumb:upgrade` | Plumb has a new version | Brings the project's copied files, tokens format and `PLUMB.md` up to the plugin's version, showing what's new first. |
| `/plumb:status` | You want a health check | Read-only: versions, placement, stale files, audit counts, the prototype (built, to build, approvals, drift), the checks, the next step. |

Every command asks one question at a time with options and a recommendation, says what it will write and where before
writing, and never installs or downloads anything. The heavy flows (init, create, extract, update, upgrade) run only
when you type them.

## How it flows

```
  /plumb:init ── finds the project, you confirm ──┬── new ────▶ /plumb:create ── interview ─▶ directions ─▶ you pick
                                                  └── existing ▶ /plumb:extract ── inventory ─▶ token groups ─▶ you confirm
                                                                         │
                                         the design system (one tokens file → web, iOS, Android themes)
                                                                         │
                                                                         ▼
  /plumb:prototype <screen> ─▶ 2–3 variants, every state ─▶ you pick ─▶ you approve ─▶ the agent builds it to match
         ▲                                                                                   │
         │            hooks: guard · prototype first · edit check · end-of-turn check ◀──────┤
         │                                                                                   ▼
  /plumb:update ◀── system changes ── /plumb:audit [fix | improve] · /plumb:ux ── reports ──▶ you commit
```

**Prototype first.** Every UI change that adds or changes a screen, tab, flow or interaction goes: the screen in the
prototype → you approve it → the real UI is built to match. Small fixes that change neither what a screen shows nor how
it behaves need no prototype step.

## What a project gets

See it as a page: **[docs/what-you-get.html](docs/what-you-get.html)**. In short:

```
.claude/skills/<project>-design-system/   the design system, as a skill both tools load
  SKILL.md · design.md                    when to use it, the workflow, hard rules; the look in words
  assets/tokens/<project>.tokens.json     the ONE source of every value (W3C design tokens), light and dark
  assets/platforms/                       generated themes: web CSS (Tailwind v4 / v3 / plain CSS), SwiftUI, Compose
  references/                             components, inventory, UX, accessibility, motion, vocabulary, dark mode
  scripts/                                build-tokens.py · audit.py · build-prototype.py (Python, standard library)
docs/design/
  decisions.md                            every design choice: the options, the one chosen, why, who decided
  prototype.html · screens.html           the whole product, clickable; every screen in every state, light and dark
  prototype/screens/<id>.html             one source file per screen
  tours/<id>.html                         shareable walkthroughs that open offline
  specimen.html · audit-*.html            every token and component; audit reports
PLUMB.md                                  Plumb's settings for this project (safe to edit)
```

Plus, each asked first: a row in `AGENTS.md`/`CLAUDE.md` ("before any UI change, read the skill; UI work is prototype
first; don't install or download anything"), Makefile targets `tokens`, `tokens-check` and `design-audit`, and the
generated CSS copy at your app's path (e.g. `app/globals.css`).

## Hooks

Three hooks run in Claude Code and Copilot CLI, only in projects with a `PLUMB.md`:

- **Session start:** one status line
  (`Plumb: acme-design-system 1.0.0 · tokens up to date · 0 audit issues · read the skill before UI changes`) and a nudge
  when the project is older than the plugin.
- **Before each edit and shell write:** refuses hand edits to, or removal of, generated files and Plumb's own files; refuses a new
  page or route with no approved prototype (`fix: /plumb:prototype <screen>`); refuses an edit that **adds**
  design-system errors (a raw colour, an off-scale size…), each with the token to use. Older code never blocks you.
- **End of the turn:** checks the UI files changed in the session, including a built screen that changed without its
  prototype; new errors stop the agent once, never in a loop.

The hooks run only the plugin's own scripts, never the copies inside a project (see [SECURITY.md](SECURITY.md), "Trust
boundary"), and they fail open: a missing Python or a broken file never blocks your work. In Copilot CLI, refusals come
back as a "deny" answer with the same reason; whether the end-of-turn check can make Copilot continue depends on its
`agentStop` support, and where it can't, the edit check is the hard guard there.

## Configuration

`PLUMB.md` at the project root holds Plumb's settings, as plain `Key: value` lines read on every run:

| Setting | What it does |
|---|---|
| `Edit check: on` | Refuse edits that add design-system errors |
| `End-of-turn check: on` | Check the files changed in a session at the end of each turn |
| `Prototype sync: on` | Prototype first: refuse a new page with no approved screen; stop once when code changes without its screen |
| `Themes: light-and-dark` | Or `light-only`, an explicit, recorded decision that turns the dark rules off |
| `UI files:` · `Allowed raw values:` | Which files count as UI; the paths where primitives may use raw values (exceptions are by path, never by a comment) |
| `Python:` | The command every skill, the Makefile and the fix lines use |
| `Design system:` · `Role:` | Where the skill is; `home` or `linked` (a repo that uses another repo's system) |

Every setting, with examples: [docs/USAGE.md](docs/USAGE.md#plumbmd).

## Slate and Effective HTML

- **[Slate](https://github.com/Zidane786/slate)** (when a project uses it): Plumb adds `make design-audit` to Slate's
  review checks, offers audit and UX findings as tickets (written only through Slate's `board.py`), and a ticket that
  changes a screen starts with "prototype approved" and links the screen. Plumb never edits `kanban/`; Slate never edits
  the design system.
- **[Effective HTML](https://github.com/plannotator/effective-html)** (`html`, `design-artifact`, `html-prototype`,
  `html-diagram`) is **optional, used when installed, with Plumb's built-in quality bar otherwise**. When its skills
  are in the session, Plumb follows them for the create directions, the prototype variants and screen files, the
  extract page and the UX review page; without them it follows "The quality bar" in
  `plugins/plumb/reference/prototypes.md` and its own directions template. Either way every page opens offline in light
  and dark. `/plumb:init` says whether it is available and `/plumb:status` reports it. To add it, run in Claude Code
  `/plugin marketplace add plannotator/effective-html`, then `/plugin install plannotator-effective-html@effective-html`
  (Plumb never installs it).

## Dependencies and enterprise control

- **Needs:** Python 3.9+ standard library, and Claude Code or Copilot CLI. git is optional.
- **Never:** npm, npx or pip installs, downloads or network calls at run time. Every generated page loads nothing from
  the network (no CDN, no hosted fonts). Agents are told, in the row Plumb adds to `AGENTS.md`/`CLAUDE.md`, never to
  install or download anything: they ask you and wait.
- **Optional, each with a fallback:** Effective HTML skills, a browser for screenshots (the agent's own tool, or a
  Chrome, Edge or Chromium already installed; otherwise the visual part is skipped with a note), `make`, Slate.
- **Control:** one Git repository with no build step, so it can be mirrored, reviewed and installed from an internal
  copy; releases are tagged `vX.Y.Z` and can be pinned; `/plumb:upgrade` never runs on its own; test tools (pytest,
  Playwright) are used only in Plumb's own CI.
- **Operating systems:** macOS, Linux and Windows, over SSH and in tmux, tested in CI on all three with Python 3.9 and
  3.13.

## Releases

Every change to the plugin is a release with a version bump and a changelog entry; merging it to `main` publishes
`vX.Y.Z` with that version's notes. What changed in each version:
[Releases](https://github.com/Zidane786/plumb/releases) (also in
[plugins/plumb/CHANGELOG.md](plugins/plumb/CHANGELOG.md)). Security reports: privately, see [SECURITY.md](SECURITY.md).

## Developing Plumb

```
plugins/plumb/     the plugin: skills/, reference/, assets/skill/ (the design-system template and its scripts),
                   hooks/, scripts/ (detect, scaffold, version, screenshot, kiro), templates/, upgrades/
tests/             pytest: the token generator, every audit rule, the hooks (Claude Code, Copilot CLI and Kiro input),
                   placement, the prototype builder, the pages in a headless browser, docs consistency, portability
docs/              the design spec, build plans, USAGE.md, what-you-get.html
```

```
uv run --with pytest pytest -q                    # the full suite
uv run --python 3.9 --with pytest pytest -q       # the oldest supported Python
claude plugin validate --strict .
claude plugin validate --strict plugins/plumb
claude --plugin-dir plugins/plumb                 # try it in a scratch project
```

CI runs the suite on Ubuntu, macOS and Windows × Python 3.9 and 3.13, with Playwright and Chromium installed on every
runner so the browser tests run everywhere. Only platform and tool skips are allowed: their reasons start with
`requires macOS`, `requires Windows`, `requires POSIX` or `requires xcrun`; any other skip fails the run. The hands-on guide for any machine, both
CLIs and Kiro is [TEST.md](TEST.md). How to work on this repo: [AGENTS.md](AGENTS.md).

## License

[MIT](LICENSE)
