# Changelog

## 1.0.0 — 2026-10-11

### Highlights

- The first release of Plumb: one plugin for Claude Code and GitHub Copilot CLI that gives a project one design system
  and keeps every new screen consistent with it, with you deciding every step.
- Start from nothing (`/plumb:create`: a few plain questions, 2–3 directions to pick from) or from the colours, type
  and spacing your app already uses (`/plumb:extract`).
- Prototype first: every new or changed screen is a clickable prototype you approve before it is built, with every
  state in light and dark, and walkthroughs you can play for a client or use for training.
- While an agent builds, hooks stop edits that bypass the design system and check the changed screens before it hands
  back.
- The complete guide is `docs/USAGE.md`; what a project gets, as a page, is `docs/what-you-get.html`.

### Added

- **`/plumb:init`** finds the right home for the design system (one repo, a monorepo, a separate frontend, a parent
  folder, several repos sharing one system, design only), shows what it found and waits for your OK, then runs create
  or extract and wires Plumb in, asking about each item: `PLUMB.md`, a row in `AGENTS.md`/`CLAUDE.md`, Makefile
  targets, the checks, the Slate review check, Kiro steering. Running it again shows status and resumes a half-finished
  setup; it never overwrites a design system.
- **`/plumb:create`**: the product first, then platforms and stack, then each design decision one at a time with a
  recommendation (including UX patterns, dark mode and the accessibility target), 2–3 directions on one page, then the
  design system after you approve the token set and the list of files, contrast computed and fixed with your OK,
  starter components written in your framework that must pass the audit, and prototypes of the key screens.
- **`/plumb:extract`**: every colour, font, size, spacing, radius, shadow, duration and easing in use, with counts and
  `file:line`; near-duplicates clustered into a clean token set you confirm group by group on a before/after page; the
  same design system; a prototype of every existing route; and an audit of what doesn't match yet.
- **One token file** (W3C design tokens, light and dark) generates the web theme (Tailwind v4, Tailwind v3 or plain
  CSS, plus an exact copy at your app's path), a SwiftUI theme and a Compose Material 3 theme. Contrast is computed in
  light and dark and written as evidence in the skill's `dark-mode.md`.
- **Your stylesheet stays yours**: in a stylesheet you already have (e.g. `app/globals.css`), Plumb adds and owns only
  a marked block, shown as a diff and asked first. When the file sets its own theme variables (a stock
  create-next-app or shadcn `globals.css`), create and extract show the token each maps onto and, on your OK, move
  them into the tokens (`build-tokens.py --overrides`, which reads shadcn's `oklch()` values and role names), so the
  audit passes on a fresh app. Dark mode follows the system setting, a `.dark` class, both, or next-themes'
  `data-theme` attribute.
- **The design-system skill** each project gets: `SKILL.md`, `design.md`, component specs, inventory, UX rules,
  accessibility, motion, vocabulary and dark-mode references, and the scripts (`build-tokens.py`, `audit.py`,
  `build-prototype.py`), Python standard library only.
- **The main prototype**: `prototype.html` (the whole product, clickable, with a state switcher, phone/desktop and
  light/dark toggles, the decisions behind each screen and a guide panel) and `screens.html` (every screen in every
  state, light and dark side by side), both built from one file per screen and kept in step with the code both ways.
- **The app view**: `app.html`, every screen full window with no prototype panels, for a demo (prototype.html to
  review, app.html to demo). Links `#/screen` and `#/screen/state` (the prototype's `#screen-…` links work too), the
  screens' own scripts and theme toggle (the choice is remembered in the browser), the md breakpoint following the
  window, a `data-app-sidebar` that stays in view, and a dialog a click opens scrolled into view. Each proposal variant
  gets one too, linked from the proposal index next to its prototype.
- **`/plumb:prototype`**: 2–3 variants of a new screen, flow or interaction, each as a clickable prototype and as
  every state in light and dark, side by side on one page (`build-prototype.py --proposal <name>`); the one you pick
  joins the main prototype with a default walkthrough, and your approval is recorded per screen.
- **Walkthroughs and `/plumb:tour`**: guide mode (step by step) and play mode (plays like a video, with speeds 0.5×
  to 2×, pause and scene markers), captions, callouts, labels, notes, title cards, spotlight, ring, arrow, beacon,
  zoom and a cursor, chapters, and "your turn" steps for training. Every tour is also a standalone page that opens
  offline, to send to a client.
- **The walkthrough player gets out of the way**: **Hide panel** (or the `H` key) swaps the panel for a small pill
  (the step's title in guide mode; in play mode the subtitle keeps narrating), remembered in the browser. While a tour
  runs, the screens list and the side rail fold away so screens keep their desktop layout. The panel, subtitle,
  cursor and labels always sit above a screen's own dialogs and toasts; hidden and off-canvas elements are never
  pointed at, and one scrolled away inside a table or list is scrolled into view; tall elements scroll so their first
  label shows; title cards stay in the window; a hint or the end of play brings a hidden panel back for that moment;
  the player wears the project's tokens (primary, surface, outline, fonts, radius, shadow) where it has them.
- **A screen's fixed layers stay in its frame**: in `prototype.html` a `position: fixed` scrim, dialog or toast sits
  inside the screen's frame (as on a device of that width), never over the toolbar or the screens list; a state change
  that opens a dialog scrolls it into view.
- **`/plumb:audit`**: every rule (raw colours, arbitrary and off-scale values, inline styles, a second icon library,
  emoji, missing focus, hover-only actions, small touch targets, Swift and Kotlin literals…), contrast in light and
  dark, missing dark values, generated files that drifted, and prototype fidelity, then an agent review of what no rule
  expresses; an HTML report, a terminal summary and an exit code. `/plumb:audit fix` repairs issues group by group with
  your OK; `/plumb:audit improve` ranks improvements to the screens and to the system itself. Without a design system
  yet, it runs in inconsistency-only mode.
- **`/plumb:ux`**: a deep review of one screen or flow against its prototype, the project's UX rules, usability
  heuristics, accessibility beyond contrast and a visual polish pass, with screenshots at phone and desktop widths in
  light and dark when a browser is available.
- **`/plumb:update`**: change or add tokens and components, add a platform later (web, then iOS and Android), improve a
  part, or apply the audit's system suggestions one at a time; everything is regenerated, the decision recorded, the
  audit run.
- **`/plumb:upgrade`** and **`/plumb:status`**: bring a project's copied files up to the plugin's version (what's new
  first, additive token migration, each step asked), and a read-only health report with the next step.
- **`/plumb:feedback`**: Plumb's own mistakes, recorded for Plumb's developers. When a Plumb script, hook or skill gets
  something wrong and the agent corrects it, the agent records that Plumb mistake (only Plumb's: your project's design
  issues stay audit findings) as one Markdown file in `~/.plumb/feedback/` (`%USERPROFILE%\.plumb\feedback\` on
  Windows), outside the project: the command, what it gave, what was right, the evidence, a repro and a suggested fix.
  Typed, `/plumb:feedback` reports every record on the machine grouped by script, function and category, most frequent
  first, and drafts GitHub issue text for Plumb that is never sent. Every skill, the `AGENTS.md` row, `PLUMB.md` and
  the session-start line point to it; Kiro has it as `/plumb-feedback`.
- **The decision log** (`docs/design/decisions.md`): every direction, variant, screen and token change, who decided
  and why, append-only with collision-free ids so several teams can add decisions on separate branches. The prototype
  shows each screen's decisions.
- **Three hooks**, in Claude Code and Copilot CLI: a status line at session start (with an upgrade nudge), a check
  before each edit and shell write (refuses hand edits to, or removal of, generated files and Plumb's own files, a new page with no
  approved prototype, and an edit that adds design-system errors), and an end-of-turn check of the files changed in
  the session that stops the agent once when there are new errors. The edit, prototype-first and end-of-turn checks
  are switched in `PLUMB.md` (`Edit check`, `Prototype sync`, `End-of-turn check`); the session-start line and the
  guard on generated and Plumb's own files are always on in a project with a `PLUMB.md`.
- **Screenshots without installing anything**: `screenshot.py` uses a Chrome, Edge or Chromium already on the machine,
  headless; with none, the visual part is skipped with a note and every other check still runs.
- **You confirm what you can see, at every checkpoint**: what you are asked to confirm (the setup Plumb found, the
  "Right?" summary, the token set, the file list, a stylesheet diff, a mapping) is inside the question itself, never
  only above it. Create and extract are numbered checkpoints that each stop and wait for your answer, and end with a
  checklist (contrast evidence, components, decisions, a first prototype screen) before they say done. The real
  scaffold runs only with the `--confirm <token>` its dry run printed after you approved that list (also in
  `/plumb:update` and `/plumb:upgrade`).
- **Scripts give evidence, not answers**: the agent investigates your project first (configs, routes, theme provider,
  Tailwind dark config, asset catalogs, theme objects, i18n files) and checks every script result against the code,
  marking what it corrected; only what the code can't tell is asked.
- **Your layout is recorded, not guessed**: `PLUMB.md` `UI files:` and `Routes:` (`<path> (<kind>)`: next-app,
  next-pages, nuxt, sveltekit, angular, router; or `none`) come from that investigation and your OK, so monorepos
  (`frontend/src/app`) get prototype-first and `route-not-prototyped`; `scaffold.py --verify` checks both. Patterns
  may use `{a,b}` (`src/**/*.{routes,router}.ts`).
- **An existing app keeps Tailwind's built-in scales**: `$extensions.plumb.web.reset_palette` (`reset_palette` in the
  answers) is asked; a new app resets all six namespaces so only tokens exist, an app that already uses classes like
  `bg-emerald-500` keeps them working (the audit suggests moving them onto tokens).
- **A git-ignored design system is caught**: the dry run, `--verify` and init say when the skill folder, `PLUMB.md`
  or the docs folder is git-ignored and ask how to fix it (un-ignore with `.claude/*` + `!.claude/skills/`, or another
  place).
- **Setup in progress is marked**: `.plumb-tmp/setup-in-progress` lives from the placement OK to the end of setup
  (the end-of-turn check stands down meanwhile, for at most 6 hours; init offers to resume a stopped setup); every
  temporary file stays in `<project>/.plumb-tmp/`, never in `/tmp` or next to the repo.
- **The guard reads more shell**: `bash -c "…"`, `sh -c`, `zsh -c`, `pwsh -c` and `powershell -Command` scripts are
  checked like any other command, here-documents are read as their command's input, and an arithmetic `$((a<<b))` is
  never mistaken for one.
- **`unknown-token-reference`** (audit, warn): the skill's `components.md` or `design.md` names a token the tokens file
  no longer has.
- **Kiro (preview)**: `scripts/kiro.py install` (your home folder) or `install --project <folder>` (that workspace
  only) copies the skills (`/plumb-init`, …) and the hook files into Kiro after you confirm (`--yes` skips the
  question); `uninstall` removes only what it wrote. Built from Kiro's documented formats; the live check on a real
  Kiro is pending.
- **Slate and Effective HTML**: audit and UX findings can become Slate tickets (through Slate's `board.py`), and
  `make design-audit` can join Slate's review checks; the Effective HTML skills are optional: used when installed for
  the directions, prototype variants and screens, the extract page and the UX review page, with Plumb's built-in
  quality bar otherwise; `/plumb:init` and `/plumb:status` say which is in use.
- Works on macOS, Linux and Windows (`py -3`, `python` or `python3`), over SSH and in tmux; every generated page opens
  offline (no CDN, no hosted fonts).
- **Token mapping and contrast fixes from the field:** `build-tokens.py --overrides` maps shadcn's `--sidebar-<x>`
  names onto the project's own `color.sidebar-<role>` / `color.on-sidebar-<role>` token when there is one (`accent`
  and `active` are synonyms) before the generic role; it tells you when a next/font variable is applied on `<body>`
  instead of `<html>` (the font stack would be undefined on `:root`), read from the recorded `Routes:` (Next.js app
  router only; no `Routes:`, no check); and a failing white-or-black (or near-white or near-black) text on its own fill (`on-X` on `X`) now offers
  two fixes with their ratios per theme, the fill stepped (same hue, text unchanged) first, then the text, in
  `--contrast` and the audit's `contrast` fix.

### Fixed

- `Allowed raw values:` in `PLUMB.md` now defaults to the folder where your UI primitives really are (for example
  `web/src/components/ui/**` for a UI package in `web/`), read from the package's `components.json` and `tsconfig`
  instead of always `components/ui/**` from the repo root. Your own answer still wins. `scaffold.py --verify` warns
  (with a fix) when an allowed pattern matches no file.
- `audit.py --inventory` reads a Tailwind `rounded-*` class at the project's own `@theme` radius (a base `--radius`
  with `calc()` steps renders `rounded-lg` as that value, not 8px); Tailwind's defaults remain for sizes the project
  does not define.
- `audit.py --inventory` no longer merges a named CSS variable's colour (a theme or chart colour) with Tailwind
  palette-class colours: clusters stay within one source kind and say which.

### Security

- The hooks run only the plugin's own installed scripts, never the copies inside a project, so a cloned repository
  cannot get code run just by containing a `PLUMB.md`. The project is read as data only. See `SECURITY.md`, "Trust
  boundary".
- Every git call the hooks make finds git on `PATH` (never inside the project), passes fixed overrides that turn off
  configured helpers (fsmonitor, hooks, external diff, filters, pagers, lazy fetch), and shares a 3-second budget; the
  hooks fail open without git.
- Session snapshots live in a private folder in the OS temp folder, written without following symlinks; the Windows
  launcher never runs a Python found in the project folder.
- A hook that fails open (a crash, a plugin script it cannot load, a timeout) writes one line to
  `~/.plumb/feedback/hooks.md`, never into the project: the folders are kept 0700 (your own wider ones are tightened)
  and the file 0600, nothing is written through a symlink or into someone else's folder, the message is redacted
  (quoted literals, absolute paths outside the project, token-like strings and secret values), the log stops at
  512 KB, and a problem with it never fails or blocks the hook.
- Nothing is installed or downloaded, and no network call is made at run time.
