# Changelog

## 1.0.0 — 2026-10-16

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
  light and dark and written as evidence in the skill's `dark-mode.md`. Pass or fail is decided on the unrounded ratio,
  as WCAG does (4.49995:1 fails 4.5:1), and every ratio is shown floored to 2 decimals (4.49), the same in the
  evidence, the specimen and the audit.
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
  `screens.html` stays small on a large prototype: each screen is stored once and drawn in every state and both themes
  by the page (a 20-screen × 10-state prototype stays under half a MB), every copy with its own state, theme and
  scripts. State names are read the same way in every page, spaces around them included (`data-state=" ready "`).
- **A size warning for large pages**: any page `build-prototype.py` writes (`prototype.html`, `app.html`,
  `screens.html`, the tour pages, the proposal pages) over 10 MB prints one `warning: <page> is <N> MB …` line naming
  every such page, also on `--check`, with the heaviest screen files and what helps: smaller screen files (inline
  `data:` images moved into image files), or git-ignoring the pages and running the build in CI instead of `--check`.
- **The app view**: `app.html`, every screen full window with no prototype panels, for a demo (prototype.html to
  review, app.html to demo). Links `#/screen` and `#/screen/state` (the prototype's `#screen-…` links work too), the
  screens' own scripts and theme toggle (the choice is remembered in the browser), the md breakpoint following the
  window, a `data-app-sidebar` that stays in view, and a dialog a click opens scrolled into view. Each proposal variant
  gets one too, linked from the proposal index next to its prototype. The prototype's **Open as app** link opens it on
  the screen and state you are looking at. A page already at one of the build's paths that Plumb didn't write (your own
  `app.html`, say) is never replaced: the build stops, names it and says how to move it out of the way. The tokens
  build leaves a `specimen.html` it did not write as it is too (it builds everything else and says how to move it).
- **`/plumb:prototype`**: 2–3 variants of a new screen, flow or interaction, each as a clickable prototype and as
  every state in light and dark, side by side on one page (`build-prototype.py --proposal <name>`); the one you pick
  joins the main prototype with a default walkthrough, and your approval is recorded per screen.
- **Change ids and shared screen files**: mark what a proposal changed with `data-guide="F01 · what changed and why"`
  and list the ids in the proposal's `changes.md` (`- **F01** title: what and why`); `--proposal` refuses an id that
  is not listed, warns about one no screen uses, and the proposal index lists the changes; the Guide panel shows each id
  as a chip (main screens are checked only when `<docs>/prototype/changes.md` exists). CSS and scripts several screens
  use go once in `screens/_shared/*.css` and `*.js` (main and each variant): the CSS is in every page once, each
  script runs for every screen before its own, and editing one makes those screens' approvals stale, named in the
  build output; the end-of-turn check counts a shared edit as a change to every screen and names the shared file.
- **Walkthroughs and `/plumb:tour`**: guide mode (step by step) and play mode (plays like a video, with speeds 0.5×
  to 2×, pause and scene markers), captions, callouts, labels, notes, title cards, spotlight, ring, arrow, beacon,
  zoom and a cursor, chapters, and "your turn" steps for training. Every tour is also a standalone page that opens
  offline, to send to a client.
- **Tours play full window**: a tour file's `"view"` says where its page plays it: `app` (the default) is the app
  view with the player on top, its closing card linking to the prototype; `prototype` is the prototype page with the
  screens list and decisions rail, for a design review. `/plumb:tour` asks "Where should it play?" (full-window app
  recommended) and shows both links; `prototype.html#tour-<id>` plays every tour. In the app view a step's element is
  kept clear of the screen's own fixed or sticky header, a zoom never pulls a screen's fixed layers out of place (a
  spotlight points instead), and moving through a tour adds no browser history entries.
- **Tour checks**: `build-prototype.py --check-tour <tour file>` checks one tour against the screens without writing
  anything, and warns when a step points at something the screen's own CSS shows only at some frame widths ("visible
  only when the frame is ≥ 48rem"). The plugin's `check-tour.py` plays a tour page headless in guide and play mode at
  1280 and 1440 wide with a Chrome, Edge or Chromium already on the machine, and names every step whose screen or
  state is wrong, whose element is hidden, zero-size, off the window or covered (by the screen's own fixed layer, or
  by the walkthrough panel only where the two overlap, read where the player put it, at the bottom or the top, so a
  corner toast beside the panel passes), or whose panel is covered. It judges the element the player points at (its
  first match on show), so one class used in several states is fine. `/plumb:tour` runs both after the build and
  fixes what they name; with no browser it says so and asks (nothing is installed).
- **The walkthrough player gets out of the way**: **Hide panel** (or the `H` key) swaps the panel for a small pill
  (the step's title in guide mode; in play mode the subtitle keeps narrating), remembered in the browser. While a tour
  runs, the screens list and the side rail fold away so screens keep their desktop layout. The panel, subtitle,
  cursor and labels always sit above a screen's own dialogs and toasts; hidden and off-canvas elements are never
  pointed at, and one scrolled away inside a table or list is scrolled into view; tall elements scroll so their first
  label shows; a step's labels come into view with its element (all of them when they fit, else the first), also when
  the element already was (a sticky sidebar); an element fixed to the window (a bottom-corner toast) is never scrolled
  to, and the panel (or its pill) moves to the top of the window, with the subtitle, for a step whose element it
  would cover at the bottom; title cards stay in the window; a hint or the end of play brings a hidden panel back for
  that moment; the player wears the project's tokens (primary, surface, outline, fonts, radius, shadow) where it has
  them.
- **Voice for tours and exact subtitles**: in play mode the **Voice** button (or `V`) reads the captions aloud with the
  browser's own speech and the voices already on the computer (nothing downloaded, works offline). Off by default and
  remembered; the same caption line the player shows, or a step's optional `"say"` for speech only; a calm pace that
  follows the speed (0.9 at 1×, capped at 1.3 at 2×) with a pause after each sentence, and each step waits for its
  speech, then its hold; pause, jumps, Hide panel and speed changes keep voice and screen in step. A tour that opens in
  play mode with its page starts from its first card: **Start with voice** or **Start without voice**. No speech in the
  browser: the button is disabled ("Voice isn't available in this browser") and the tour plays with captions; an error
  mid-tour says "Voice stopped: continuing with captions" and carries on. **Save subtitles (.vtt)** downloads
  `<tour id>.vtt` with the real times each caption showed in that run (kept in memory only, never stored).
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
  first, additive token migration, each step asked), and a read-only health report with the next step. Another build of
  the same version is noticed too: when Plumb's own files in the project differ from the plugin's, the session-start
  line and both commands say so, and the upgrade shows the evidence and asks before refreshing them.
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
  before each edit and shell write (refuses hand edits to, or removal of, generated files and Plumb's own files, a new
  page with no approved prototype, and an edit that adds design-system errors), and an end-of-turn check of the files
  changed in the session that stops the agent once when there are new errors. The edit, prototype-first and end-of-turn
  checks are switched in `PLUMB.md` (`Edit check`, `Prototype sync`, `End-of-turn check`); the session-start line and
  the guard on generated and Plumb's own files are always on in a project with a `PLUMB.md`. The generated pages it
  guards include the app view, the tour pages and each proposal's pages (`index.html` and a variant's `prototype.html`,
  `app.html`, `screens.html`); a page in those places (or at `specimen.html`, `prototype.html`, `app.html`,
  `screens.html` and in `tours/`) without the header Plumb's build writes is yours and left alone; one that is empty
  or cannot be read stays guarded.
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
- **The guard reads shell the way a shell runs it**: `bash -c "…"`, `sh -c`, `zsh -c`, `pwsh -c` and
  `powershell -Command` scripts are checked like any other command, here-documents are read as their command's input,
  and an arithmetic `$((a<<b))` is never mistaken for one.
- **The guard refuses real writes, not mentions**: a shell command is refused when a guarded file is a real write
  target (a redirect, `tee`, `sed -i`, `perl -i`, the destination of `cp` / `mv` / `install` / `rsync` / `ln`, `rm`,
  `truncate`, `dd of=`, and in inline code `open("…", "w")`, `Path("…").write_text` and the like). A stricter first
  reading decides, and its refusal becomes an allow only in four provable cases: a here-document, `echo`, `printf` or
  `tee` text written to a file the same command doesn't run, import, name again or leave where a program picks it up
  by itself (`sitecustomize.py`, `.bashrc`, a git hook …); a read-only program's words (`cat`, `grep`, `diff` …);
  inline code that only reads its guarded paths (`json.load` of `screens.json`, `importlib` on a Plumb script) and
  writes only to plain paths away from them; and a `git commit` message (`-m`, `-F`, a here-document), unless git is
  given an option that runs something, a variable is set before it, or the command wrote a hook. Every other word must
  name no guarded path, file or folder, even one not built yet. A file a command writes and then runs is read as code.
  It also reads the writes that are easy to miss: `eval`, `find -exec`, `curl -o` /
  `--output-dir`, `wget -O`, `perl -0pi`, `sort -o`, `uniq IN OUT`, sed's `w FILE`, `sh -c '… "$1"'`, `source <(echo
  …)`, a copy into the folder of a guarded file, a recursive copy or move into a folder that holds one, shell
  variables (`OUT=…; echo > "$OUT"`), `$PWD`, `$'…'` escapes, globs and braces, write targets put together in code
  (`os.path.join(d, …)`, `Path(d) / …`, f-strings, `%`, `.format`, `${}`), code piped to an interpreter or on
  `/dev/stdin`, and `os.remove` / `shutil.rmtree` in inline code. A command over 64 KB, one nested deeper than the
  reader reads, and one the reader fails on are refused when they name a guarded file or folder (or a parent of one).
  Loop variables are followed: a target that uses a `for` / `select` / `while read` variable is refused when the
  variable could hold a guarded path, or a name the target turns into one, judged against the guarded paths only (`for
  f in docs/design/*.html; do sed -i … "$f"; done` and `ls docs/design | while read f; do rm "docs/design/$f"; done`
  are refused, `for f in app/*.tsx; …` and `find app -name '*.tsx' | while read f; …` are not). A write or removal
  target the reader can't work out (`$( … )`, backticks, `${…}`) is refused when its text or the value of a variable
  it uses names a guarded file or a folder Plumb owns whole by its full path (`cat a > "$(dirname
  docs/design/screens.html)/screens.html"`).
- **The guard reads paths the way the file system does**: it compares them without case on Windows and macOS, and on
  Linux when the project's file system ignores case (asked of the file system itself: a folder that ignores case, a
  Windows drive in WSL); on Windows it reads Git for Windows' Bash drive paths (`/c/Users/…`,
  `/cygdrive/c/…`) as well as `\` and `/`, drive letters in either case and quoted paths with spaces. Its time budget
  runs on a fine-grained clock on every platform, and each folder's real path is worked out once per command, so a
  long command stays well inside the hook's timeout, on a Windows runner too.
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
- **Token mapping and contrast fixes**: `build-tokens.py --overrides` maps shadcn's `--sidebar-<x>` names onto the
  project's own `color.sidebar-<role>` / `color.on-sidebar-<role>` token when there is one (`accent` and `active` are
  synonyms) before the generic role; it tells you when a next/font variable is applied on `<body>` rather than on
  `<html>` (the font stack would be undefined on `:root`), read from the recorded `Routes:` (Next.js app router only;
  no `Routes:`, no check); a variable named after a token whose value in the app differs from the token's (its
  colours, or a length such as `--radius-md` worked out from the app's `--radius`) gets a "the look changes" note
  with both values, so the skill asks before the token takes over; and a failing white-or-black (or near-white or
  near-black) text on its own fill (`on-X` on `X`) gets two fixes with their ratios per theme, the fill stepped (same
  hue, text unchanged) first, then the text, in `--contrast` and the audit's `contrast` fix. `build-prototype.py
  --proposal` with a name that is not a folder name answers with one exact command.
- **`Allowed raw values:` where your primitives are**: in `PLUMB.md` it defaults to the folder your UI primitives
  really live in (for example `web/src/components/ui/**` for a UI package in `web/`), read from the package's
  `components.json` and `tsconfig`. Your own answer wins, and `scaffold.py --verify` warns (with a fix) when an
  allowed pattern matches no file.
- **The inventory reads your theme**: `audit.py --inventory` reads a Tailwind `rounded-*` class at the project's own
  `@theme` radius (a base `--radius` with `calc()` steps renders `rounded-lg` as that value), with Tailwind's defaults
  only for sizes the project does not define; its colour clusters stay within one source kind and say which, so a
  named CSS variable's colour (a theme or chart colour) is never merged with Tailwind palette-class colours.

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
  512 KB, and a problem with it never fails or blocks the hook. Each append holds a short exclusive lock (waiting at
  most half a second, else leaving its line out), so hooks failing at the same moment never lose or interleave lines,
  also on Windows, where appends from several processes are not atomic.
- Nothing is installed or downloaded, and no network call is made at run time.
- Every screen file is checked before it is inlined, as the shared files are: a hosted font `<link>`, a remote
  `<img>`, `<iframe>`, `<video>` or `<source>`, an `@import` or remote `url()` in its styles, or a `fetch(` in its
  script exits 2 naming the file and line, so a generated page never loads anything from the network.
- `audit.py --html <path>` writes only its own report: an existing page it did not write (`--html app/landing.html`,
  meaning "audit this page") is refused, exit 2, and keeps every byte.
- The scripts read only regular files from a project, each up to 8 MB (pages and screen files up to 256 MB): a FIFO,
  a device or a link to one (a committed symlink to `/dev/zero`) is skipped by every walk, refused as unreadable when a
  command needs it (the tokens file), and never written into, so it cannot make a check hang or fill memory.
