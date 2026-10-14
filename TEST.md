# Testing Plumb on this machine

Hand this file to any coding agent (Claude Code, Copilot CLI, Codex, …) on a fresh clone of the Plumb repo, on
**Windows, macOS or Linux**, and say: *"Follow TEST.md and report the results."*

It has seven levels. Do them in order; stop and report at the first level that fails.

| Level | What it proves | Needs |
|---|---|---|
| 1. Automated tests | Every script, rule, hook and generated page works here | Python 3.9+, git, `pytest` (Playwright for the browser tests) |
| 2. Plugin check | Claude Code accepts the plugin and the marketplace | Claude Code CLI |
| 3. Hands-on scripts | A real design system, audit, prototype, variants and a tour work on this OS, with no agent | Python, git, a browser to look |
| 4. Claude Code live | The `/plumb:*` skills and the three hooks work in a real session | Claude Code, optionally tmux |
| 5. Copilot CLI live | The same plugin works in GitHub Copilot CLI, hooks included | Copilot CLI, optionally tmux |
| 6. Kiro live | The skills and hooks work in Kiro (**pending the live check**) | Kiro IDE or CLI v3+ |
| 7. Pages in a browser | The generated pages and `docs/what-you-get.html` render in light and dark, wide and phone | Playwright (headless) |

**Rules for the agent running this:** don't edit Plumb's source to make a check pass. Report failures with the exact
command and output. Work only in a scratch folder for levels 3–6 (never in a real project; copy a project to a
temporary folder if you want to try it on real code). Open browsers **headless only**. Plumb installs nothing: if a
check needs something that is missing, say so and skip that check.

---

## 0. Record the machine

```
python3 --version || python --version || py -3 --version
git --version
uname -a            # macOS / Linux
ver                 # Windows (cmd), or [System.Environment]::OSVersion in PowerShell
claude --version    # if installed
copilot --version   # if installed
kiro --version      # if installed
tmux -V             # if installed
```

Use the Python command that worked (`python3`, `python` or `py -3`) as `PY` below, and the absolute path of this clone
as `<repo>`.

---

## 1. Automated tests

From the repo root:

```
uv run --with pytest pytest -q -rs                      # or: PY -m pip install --user pytest, then PY -m pytest -q -rs
uv run --python 3.9 --with pytest pytest -q -rs         # the oldest supported Python, if available
```

**Expected:** every test passes. Skips are listed with their reason (`-rs`). Platform skips start with one of
`requires macOS`, `requires Windows`, `requires POSIX` or `requires xcrun` (for example the Windows-only `run.cmd` and
PowerShell hook tests, and, on macOS with xcrun, the Swift type-check of the generated theme). Other skips name what is
missing on this machine: `requires Playwright` for the browser tests, and a missing git, hook launcher (`sh` or
PowerShell) or Python command. Report the last line (`N passed, M skipped …`).

To run the browser tests too (they render every generated page in light and dark, headless):

```
uv run --with pytest --with playwright python -m playwright install chromium
uv run --with pytest --with playwright pytest -q -rs
```

**CI** (`.github/workflows/test.yml`) runs the whole suite on Ubuntu, macOS and Windows × Python 3.9 and 3.13, installs
Playwright and Chromium on every runner, and sets `PLUMB_STRICT_SKIPS=1`: `tests/conftest.py` allows only skips whose
reason starts with `requires macOS`, `requires Windows`, `requires POSIX` or `requires xcrun`; any other skip (such as
`requires Playwright`) fails the run. A missing git, hook launcher or Python command is not an allowed skip: in strict
mode it fails the run on purpose, because CI must have them.
To reproduce that locally: `PLUMB_STRICT_SKIPS=1 uv run --with pytest --with playwright pytest -q -rs`.

**Windows notes:** run from Git Bash or PowerShell. If many JSON or golden-file tests fail, check
`git config core.autocrlf` (should be `false` or `input`; `.gitattributes` pins LF for the files that need it).

---

## 2. Plugin check (needs Claude Code)

```
claude plugin validate --strict <repo>
claude plugin validate --strict <repo>/plugins/plumb
```

**Expected:** both pass with no errors and no warnings.

---

## 3. Hands-on scripts (no agent needed)

Make a scratch project and lay a design system into it with the same script `/plumb:create` uses:

```
mkdir plumb-scratch && cd plumb-scratch && git init
PY <repo>/plugins/plumb/scripts/scaffold.py --project-root . --name Demo --skill-dir .claude/skills/demo-design-system --platforms web,ios,android --styling css --dry-run
PY <repo>/plugins/plumb/scripts/scaffold.py --project-root . --name Demo --skill-dir .claude/skills/demo-design-system --platforms web,ios,android --styling css
PY <repo>/plugins/plumb/scripts/scaffold.py --project-root . --name Demo --skill-dir .claude/skills/demo-design-system --platforms web,ios,android --styling css --confirm <token>
```

**Expected:** the dry run lists `would write:` lines, writes nothing and ends with
`confirm: show the user this list; after their OK run the same command without --dry-run, plus --confirm <token>`
(12 hex characters). The second command (no token) is refused with
`error: the scaffold writes into the project only after the user approved the dry-run list` and writes nothing. The
third, with the token the dry run printed, ends `done: 38 written, 0 kept`.
`PLUMB.md` exists and starts with `<!-- plumb v1.0.0 · written by /plumb:init, safe to edit values -->`.

Below, `SKILL` is `.claude/skills/demo-design-system`.

### 3.1 Tokens → every theme

1. `PY SKILL/scripts/build-tokens.py`
   **Expect:** `wrote …` for `DemoTheme.kt`, `DemoTheme.swift`, `tokens.css`, `references/dark-mode.md` and
   `docs/design/specimen.html`.
2. `PY SKILL/scripts/build-tokens.py --check` → `ok: 5 generated files are up to date`, exit 0. Run step 1 again:
   nothing changes (`git status` shows the same files).
3. Change `color.primary`'s `$value` in `SKILL/assets/tokens/demo.tokens.json`, then `--check` again.
   **Expect:** exit 1 with a `stale: …` line per output and a `fix:` line. Run step 1; `--check` exits 0.
4. Open `docs/design/specimen.html` from disk: every token and component, light and dark; nothing loads from the
   network.
5. Break the JSON (add a trailing comma), run step 1. **Expect:** exit 2,
   `error: demo.tokens.json: invalid JSON at line N, column M: …` and a `fix:` line; no traceback. Undo it.

### 3.2 The audit

1. `mkdir ui` and write `ui/card.css` containing `.card { color: #ff0000; }`.
2. `PY SKILL/scripts/audit.py ui`
   **Expect:** exit 1 with `ui/card.css:1: error raw-colour: raw colour #ff0000` and a `fix:` line naming the nearest
   colour token, then `audit: 1 error, …`.
3. `PY SKILL/scripts/audit.py ui --html` → also writes `docs/design/audit-YYYY-MM-DD.html`. Open it: summary, Issues,
   Improvements, filters, light and dark.
4. `PY SKILL/scripts/audit.py nowhere` → exit 2 with `error:` and `fix:` (nothing checked).

### 3.3 The main prototype

1. Write `docs/design/prototype/screens/home.html`:
   ```html
   <section data-screen="home" data-title="Home">
     <h2>Today</h2>
     <div data-state="ready"><ul class="list"><li>Booking for Zoë Brontë, 19:30</li></ul>
       <button type="button" data-test="new">New booking</button></div>
     <div data-state="empty"><p>No bookings yet. Take the first one.</p></div>
     <div data-state="error"><p role="alert">Bookings could not load. Try again.</p></div>
   </section>
   ```
2. `PY SKILL/scripts/build-prototype.py` → `wrote` `prototype.html`, `screens.html` and `prototype/screens.json`; a
   summary line `1 screens: … 1 not approved; 1 to build`; exit 0.
3. Open `docs/design/prototype.html` from disk: the Home screen, the state switcher (ready, empty, error), the
   phone/desktop and light/dark toggles. Open `docs/design/screens.html`: every state in light and dark side by side.
4. `PY SKILL/scripts/build-prototype.py --approve home` → `approved home (<your git name>, <today>)`.
5. `PY SKILL/scripts/audit.py docs/design/prototype/screens` → no errors (warnings such as `screen-not-built` are
   expected: the screen isn't built yet).

### 3.4 Prototype variants (`build-prototype.py --proposal`)

1. Make two variants of the screen:
   ```bash
   mkdir -p docs/design/prototype/proposals/demo/a-calm/screens docs/design/prototype/proposals/demo/b-dense/screens
   cp docs/design/prototype/screens/home.html docs/design/prototype/proposals/demo/a-calm/screens/
   cp docs/design/prototype/screens/home.html docs/design/prototype/proposals/demo/b-dense/screens/
   printf '# Calm\n\nMore space, one action.\n\n- Easy to scan\n- Longer page\n' > docs/design/prototype/proposals/demo/a-calm/idea.md
   ```
   Change the heading in `b-dense/screens/home.html` so the two differ.
2. `PY SKILL/scripts/build-prototype.py --proposal demo`
   **Expect:** `wrote …` lines for `demo/a-calm/prototype.html`, `demo/a-calm/screens.html`, the same two for
   `b-dense`, and `demo/index.html`, then `proposal demo: 2 variants (a-calm: 1 screen, b-dense: 1 screen)`, exit 0.
   `docs/design/prototype/screens.json` is unchanged.
3. Open `docs/design/prototype/proposals/demo/index.html` from disk.
   **Expect:** two cards side by side ("Calm" with its idea and two trade-offs, "B dense"), each with "Clickable
   prototype" and "Every state, light and dark" links that open that variant's pages; the theme toggle switches light
   and dark; nothing is loaded from the network.
4. Run step 2 again. **Expect:** `ok: proposal demo: 2 variants (…): up to date` and no file changed.
5. In `b-dense/screens/home.html`, change its heading text again (a comment alone doesn't change the pages), then `PY SKILL/scripts/build-prototype.py --check --proposal demo`.
   **Expect:** exit 1 listing `stale: …/b-dense/prototype.html` and `…/b-dense/screens.html` and a `fix:` line with
   `--proposal demo`.
6. Change a colour in the tokens file and run `PY SKILL/scripts/build-tokens.py`.
   **Expect:** the proposal pages are rewritten too, and `PY SKILL/scripts/build-tokens.py --check` exits 0.
7. `PY SKILL/scripts/build-prototype.py --proposal ../x` and `--proposal missing`.
   **Expect:** exit 2 with an `error:` line and a `fix:` line each; nothing written.

### 3.5 A walkthrough

1. Write `docs/design/prototype/tours/first-look.json`:
   ```json
   {"title": "First look", "audience": "client", "steps": [
     {"screen": "home", "title": "Today", "caption": "Every booking for today.", "target": ".list", "point": "spotlight"},
     {"screen": "home", "title": "Start a booking", "caption": "One button starts a booking.", "target": "[data-test=new]", "point": "ring"},
     {"screen": "home", "state": "empty", "title": "A quiet day", "caption": "The page says what to do next.", "target": "p", "point": "beacon"}
   ]}
   ```
2. `PY SKILL/scripts/build-prototype.py` → also `wrote docs/design/tours/first-look.html` and
   `1 tour: first-look (3 steps, play mode)`.
3. Open `docs/design/tours/first-look.html` from disk: it starts playing (a client tour opens in play mode). Check
   pause and resume (Space), the speeds 0.5×–2×, jumping to a step marker, and switching to guide mode (Next/Back,
   the arrow keys, Esc leaves). With the OS set to reduce motion, play mode still plays by itself.
4. Rename `data-test="new"` to `data-test="add"` in `home.html`, then `PY SKILL/scripts/build-prototype.py --check`.
   **Expect:** exit 2 with `error: docs/design/prototype/tours/first-look.json:3: steps[1].target "[data-test=new]"
   matches nothing …` and a `fix:` line. Undo it.

### 3.6 Screenshots with a browser already installed

`PY <repo>/plugins/plumb/scripts/screenshot.py "docs/design/prototype.html#screen-home/empty" --out shot.png --width 390 --theme dark`

**Expect:** `wrote: shot.png (<browser>, 390x900, dark)` when Chrome, Edge or Chromium is installed; otherwise exit 3
with `note: visual comparison skipped: no browser found` and a `fix:` line. Nothing is downloaded either way.

### 3.7 The hooks' feedback log (Plumb's own mistakes)

A hook that fails open writes one line to `~/.plumb/feedback/hooks.md`. Try it with a broken copy of the plugin and a
stand-in home folder, so your real `~/.plumb` is never touched (macOS and Linux; on Windows use Git Bash and set
`USERPROFILE` the same way as `HOME`):

```
cp -R <repo>/plugins/plumb ../plumb-broken && echo 'def broken(:' > ../plumb-broken/assets/skill/scripts/audit.py
mkdir -p ../fake-home
echo '{"hook_event_name": "SessionStart", "session_id": "t1", "cwd": "'"$PWD"'"}' | HOME="$PWD/../fake-home" CLAUDE_PLUGIN_ROOT="$PWD/../plumb-broken" sh ../plumb-broken/hooks/run.sh session_start.py
```

**Expect:** exit 0; stdout is the `Plumb: demo-design-system 1.0.0 · … · audit not run · read the skill before UI
changes` line and, last, `Plumb mistakes (a Plumb script, hook or skill got it wrong) → /plumb:feedback`; at most one
`plumb: …` note on stderr. `../fake-home/.plumb/feedback/hooks.md` starts `# Plumb hook failures` and holds lines like
`- <date> <time> session_start.py · crash · Plumb 1.0.0 · claude-code · <os> · project plumb-scratch · event
SessionStart · … · Given: cannot load the plugin's audit.py (SyntaxError: …) … · Expected: …`. `ls -ld` shows
`drwx------` for `.plumb` and `.plumb/feedback` and `-rw-------` for `hooks.md`. Run the command again: no new line
(the same failure is written once a day). Nothing new in the project (`git status`). Then
`rm -rf ../fake-home/.plumb && ln -s "$PWD" ../fake-home/.plumb` and run it again: still exit 0, and nothing is
written in the project through the link. Remove `../plumb-broken` and `../fake-home`.

---

## 4. Claude Code live (the real thing)

Use a fresh scratch project (a small app is best: a Next.js + Tailwind folder works without `npm install`; Plumb never
needs it). Load the plugin from your clone:

```
cd plumb-live && git init
claude --plugin-dir <repo>/plugins/plumb
```

Try, in order, and report what happens. Use tmux (or a second terminal) if you want pane captures as evidence.

- [ ] `/plumb:init` → the **whole** "Plumb found … I'll create … OK, or change something?" block is **inside the
      question** (its text, or the recommended option's preview), not only printed before it: project, layout, UI,
      the skill dir, `PLUMB.md`, `docs/design/`, the generated copy with its `exists:` line when the stylesheet already
      exists, the UI files with how many files they match, the routes; never a one-line summary or "the setup above".
      The same for the "Right?" summary, the token set, the dry-run list and the stylesheet diff later on. Nothing is
      written before you say OK; then "existing or new?" with the detected one marked (Recommended).
- [ ] **Monorepo** (UI in `frontend/`, the repo root holding `frontend/` and `backend/`): the UI files are
      `frontend/…` patterns (a root `src/**` that matches nothing is shown `(corrected: …)` with the file counts), the
      routes line names `frontend/src/app (next-app)` (the page folder with its kind; `none` in a mobile-only or
      design-only project), and both land in `PLUMB.md` (`UI files:`, `Routes:`), and `Allowed raw values:` names the UI
      package's primitives folder (e.g. `frontend/src/components/ui/**`), not a bare `components/ui/**`.
      `scaffold.py --verify` ends `verify: ok` (an allowed pattern that matches no file would print a `warning:` and
      a `fix:`).
- [ ] **Git-ignored skill folder:** in a repo whose `.gitignore` has `.claude/`, init shows that line inside a question
      and offers to un-ignore the skill folder (`.claude/*` + `!.claude/skills/`, recommended) or another location;
      it never goes on silently, and after the change it runs `git check-ignore` again and shows the result.
- [ ] In a stock shadcn app with no next-themes (`@custom-variant dark (&:is(.dark *))` in `globals.css`), the theme
      switch recommends **class** and cites that line.
- [ ] Choose **create**. The product questions come before any design question; every question has options with one
      marked (Recommended) and a reason; it asks before writing `docs/design/directions.html`; the directions page
      opens from disk and shows 2–3 distinct directions in light and dark.
- [ ] Dark mode asks how the app switches themes as its own question (system · class · both · data-theme; both
      recommended in a new app; in an app with next-themes `attribute="class"`, **class** recommended with the
      `file:line` inside the question) and reduced motion asks keep fades or none; both land in the tokens file
      (`$extensions.plumb.web.theme_switch`, `$extensions.plumb.motion.reduced`). The UX patterns are seven questions
      (or it names the ones it skips and why). With Tailwind it asks about the palette reset (reset recommended for a
      new app; keep recommended, with the count of palette classes, in an existing one; the question says the reset
      covers all six namespaces and that with keep the audit still flags off-scale defaults like `text-lg`):
      `web.reset_palette` in the tokens file. Keep → `bg-emerald-500` still renders after the first build.
- [ ] In an app whose `globals.css` has shadcn variables, the overrides question lists each mapping, and any "the look
      changes; ask the user" note sits on its own line with the app's value and the token's.
- [ ] It asks you to pick a direction, then shows the full token set (light and dark) and the `scaffold.py --dry-run`
      file list, each inside a question, and writes only after you say OK; the real scaffold runs with the
      `--confirm <token>` the dry run printed, in its own shell call. Scratch files go in `<project>/.plumb-tmp/`
      (never `/tmp` or next to the repo); the marker `.plumb-tmp/setup-in-progress` exists until the end of setup (the
      end-of-turn check doesn't fire meanwhile) and the folder is gone when init finishes. Stop the session midway and
      run `/plumb:init` again: it offers to resume. A long stylesheet diff comes as a summary and its first ~40 lines,
      with the full diff in `.plumb-tmp/` to open.
      Before the first build it says what changes in your existing stylesheet (e.g. `app/globals.css`: only a marked
      `plumb:start … plumb:end` block is Plumb's) and asks. The audit on the components it writes exits 0;
      `docs/design/specimen.html` exists.
- [ ] On a fresh `npx create-next-app` app (its stock `globals.css`): after the first build the audit reports
      `block-override` for `--color-background`, `--color-foreground`, `--font-sans`, `--font-mono`. Create shows
      each with the token it maps onto (from `build-tokens.py --overrides`) and asks once, "move them into the tokens"
      recommended. Say yes → the `@theme inline`, `:root` and dark `--background`/`--foreground` lines are gone, `body`
      uses `var(--color-background)` / `var(--color-foreground)` / `var(--font-sans)`, the tokens gain
      `color.foreground`, and the audit exits 0. Say no → nothing in `globals.css` changes. In a plain-CSS app,
      choosing keep fades tells you to add `motion-fade` to fade-only elements.
- [ ] Every decision is in `docs/design/decisions.md` with `Decided by:` your git name.
- [ ] Init's wire-in: each item is asked on its own (`PLUMB.md`, both checks, the `AGENTS.md` row, the Makefile),
      also in a project with no `AGENTS.md` and no `Makefile`. Say no to the Makefile → `PLUMB.md`'s `## Commands`
      lines keep the direct commands (no `make …`), the generated skill names no `make` target, and
      `scaffold.py --verify` ends `verify: ok`. Say yes → the targets are written and the `(make …)` hints added.
- [ ] Start a **new** session. The first context line is
      `Plumb: <project>-design-system 1.0.0 · tokens up to date · N audit issues · read the skill before UI changes`
      (ask the agent "what did the Plumb session note say?").
- [ ] Ask the agent to add `className="bg-[#3b6fd4]"` to a component → **refused** by the edit check:
      `Plumb edit check: this edit adds 1 design-system error …`, `error: line N: raw colour #3b6fd4` and a `fix:`.
      The agent then uses a token instead.
- [ ] Ask the agent to edit the generated CSS copy (e.g. `app/globals.css`) by hand, and then with
      `sed -i` → both **refused** (`… is generated from the design tokens; a hand edit is lost on the next build`).
      Then ask it to delete that file (`rm`, or `Remove-Item` on Windows) and to `mv` it away → both **refused** the
      same way. The same through `bash -c "rm app/globals.css"` → **refused**.
- [ ] Create `.plumb-tmp/setup-in-progress` and set its time 7 hours back (`touch -t`): a new session says
      `a setup marker from … is stale — finish /plumb:init or remove .plumb-tmp/`, and the end-of-turn check runs
      again.
- [ ] Ask the agent to create a new page (`app/reports/page.tsx`) → **refused**:
      `error: app/reports/page.tsx is a new screen with no approved prototype` / `fix: /plumb:prototype reports …`.
- [ ] `/plumb:prototype reports` → 2–3 variants, `proposals/reports/index.html` side by side, both views each; you pick
      one; it asks before writing it to main; `prototype.html#screen-reports` shows it with a default walkthrough; it
      asks you to approve it, then records the decision. Now the agent can create the page.
- [ ] `/plumb:tour` → asks who is watching; shows the steps as a table; writes `tours/<id>.json` only on your OK;
      `docs/design/tours/<id>.html` plays offline.
- [ ] Map the built screen (`build-prototype.py --map reports --route=/reports --files "app/reports/**"`), then ask the
      agent to change what the reports page shows **without** touching its screen file → at the end of the turn the
      agent is stopped once with `Plumb end-of-turn check: …`; it updates the screen file and asks you to approve it.
      It does not loop.
- [ ] `/plumb:audit` → terminal summary, `docs/design/audit-YYYY-MM-DD.html` with an Agent review section; exit 1 is
      reported as "errors found", not as a crash; it asks for the dev server's URL instead of probing `localhost`; it
      offers Slate tickets only in a project with `kanban/board.py`. Then `/plumb:audit fix` groups the issues and asks
      before each group.
- [ ] `/plumb:ux reports` → asks for the dev server URL (say "not running": it reviews the prototype and the code),
      writes `ux-review-YYYY-MM-DD.html`.
- [ ] `/plumb:update add iOS` → shows the dry-run list (your files `skip: … (yours, kept)`), asks, then writes the
      iOS theme; the decision is recorded; the audit runs.
- [ ] **Upgrade from an older version:** change `PLUMB.md`'s first line to `<!-- plumb v0.9.0 · …` and start a new
      session → the second context line says `… run /plumb:upgrade`. `/plumb:upgrade` shows What's new for 1.0.0,
      asks, refreshes Plumb's files, migrates, runs the checks, sets the version line back to 1.0.0 and adds a dated
      "Plumb updates" line. It never deletes a value.
- [ ] Remove `theme_switch` and `motion` from the tokens file's `$extensions.plumb` and build: two `note:` lines say
      the defaults apply and name `build-tokens.py --migrate`. Run it → it prints `added … theme_switch = "both"` and
      `added … motion.reduced = "none"`, the next build prints no note, and the generated CSS is unchanged.
- [ ] `/plumb:status` → a short read-only report ending with the next step, never "/plumb:create" or
      "/plumb:extract" in a set-up project; it writes no file (no `/tmp`, no `.plumb-tmp/`).
- [ ] **Plumb's own mistakes:** the new session's context ends with `Plumb mistakes (a Plumb script, hook or skill got
      it wrong) → /plumb:feedback`. In the monorepo run above, when the agent corrected a `detect.py` result
      (`(corrected: …)`), it also said `Recorded a Plumb mistake: ~/.plumb/feedback/<date>-detect-…-<project>.md` and
      carried on; that file has every field (When, Project shape, Where it failed, Command, Given, Expected, Evidence,
      Repro, Category, Suggested fix in Plumb, Handled here) and no source code; nothing was written in the project.
      `/plumb:feedback log the raw hex in app/page.tsx` → the agent writes nothing and says that is an audit finding
      (`/plumb:audit`). `/plumb:feedback` → the groups, most frequent first, with given vs expected, then one question
      at a time: a drafted issue is text only (no `gh` command runs), "mark handled" adds a line to
      `~/.plumb/feedback/handled.md`, and no record is deleted.
- [ ] Before saying done, create and extract walk their final checklist: contrast evidence in `dark-mode.md`,
      components, the decision log, a first prototype screen (or your "later"), the wire-in asked, `.plumb-tmp/` gone.

**tmux / SSH:** repeat one refusal and `/plumb:status` inside tmux, and over SSH if you can; open the pages on the
machine that holds the files.

---

## 5. Copilot CLI live (if you have GitHub Copilot CLI)

Install from the marketplace (or load the clone with `copilot --plugin-dir <repo>/plugins/plumb`):

```
copilot plugin marketplace add Zidane786/plumb
copilot plugin install plumb@plumb
```

Restart Copilot, open the same kind of scratch project, and report:

- [ ] Type `/plumb` → the eleven commands are listed (`/plumb:init`, `/plumb:create`, …, `/plumb:feedback`).
- [ ] Ask "what does the Plumb session note say?" (no tools) → it quotes the `Plumb: … read the skill before UI
      changes` line (session start reached Copilot as additional context).
- [ ] The raw-colour edit, the hand edit to a generated file (with the edit tool and with a shell write) and the new
      page are **refused with Plumb's reason** (the `error:` and `fix:` text), not just "hook exited with code 2".
- [ ] `/plumb:prototype`, `/plumb:status` and `/plumb:feedback` run as in level 4 (the same `~/.plumb/feedback/`
      folder; the session context ends with the `Plumb mistakes … → /plumb:feedback` pointer).
- [ ] `/plumb:init` on a scratch app with UI (it routes to extract): the full placement block is inside Copilot's ask
      question; screens are mapped with `--route=/` (no "Allow path access" prompt for `/`); scratch files stay in
      `.plumb-tmp/`; the agent never runs `build-prototype.py --approve` before you said yes to that screen; the
      wire-in asks the `AGENTS.md` row and the Makefile even when neither file exists (a new `AGENTS.md` has a title,
      the `## Read before you work` heading, the table header and the row). A `✗ skill(plumb:init) Skill not found`
      line at the start is expected and harmless. Count the permission prompts (Copilot ignores `allowed-tools`):
      about 10–15 script runs plus one per file written is expected.
- [ ] `/plumb:init` choosing **create** in Copilot: every checkpoint is its own question and Copilot waits for each
      (the direction pick, the token set, the dry-run list, the stylesheet diff, each contrast fix, the components, the
      prototypes); it never runs the real scaffold or the first build before your answer, even when you approve the
      command's permission prompt. It ends with the final checklist and no `.plumb-tmp/` left.
- [ ] End-of-turn: change a UI file with a raw colour while the edit check is off (`Edit check: off` in `PLUMB.md`):
      Copilot continues (its `agentStop` honours the block). Then repeat after telling the agent "don't fix it now":
      it reports what the check found and stops.
- [ ] **Windows only:** the same refusals in PowerShell (the hooks run `hooks/run.cmd`); a machine without Python must
      not block any tool call.

---

## 6. Kiro live (pending the live check)

Kiro support was built from Kiro's documented formats and is tested in CI with Kiro-shaped input; this level is the
first run on a real Kiro. Record everything, including what differs.

```
PY <repo>/plugins/plumb/scripts/kiro.py install --project <scratch project>
```

- [ ] It lists every path it will write and asks `[y/N]`; answer `y`. (Run from a non-terminal without `--yes`, it
      writes nothing and prints `ask the user: run … --yes yourself, or tell me to run it`.)
- [ ] `<scratch>/.kiro/skills/plumb-<name>/SKILL.md` exists for every command, and `<scratch>/.kiro/hooks/plumb.json`
      is written; nothing was written in your home `~/.kiro` (`--project` is that workspace only). Every hook command
      in the file runs the plugin's launcher with `--kiro`.
- [ ] In Kiro, `/plumb-init` runs the init flow (questions one at a time); `/plumb-feedback` exists and reports the
      same `~/.plumb/feedback/` folder.
- [ ] Session start shows the `Plumb: …` line, with commands written `/plumb-…`.
- [ ] A raw-colour edit with Kiro's write tool, and a shell write to a generated file, are refused with Plumb's
      `error:` / `fix:` text. Record which exit code blocks and the exact hook input fields Kiro sends (the spec waits on
      this).
- [ ] **The Stop decision:** let a change with a new error reach the end of the turn (set `Edit check: off` in
      `PLUMB.md` first). The hook answers `{"decision": "block", "reason": …}` on stdout, exit 0. Record whether Kiro
      makes the agent continue and fix it, or only adds the text to its context; and whether the report-only follow-up
      (`{"systemMessage": …}`) shows as raw JSON. Either is acceptable for now; record which, in the IDE and the CLI.
- [ ] Ask the agent to edit `.kiro/hooks/plumb.json` by hand → refused (change the checks in `PLUMB.md`, refresh with
      `kiro.py install`). Ask it to run `rm .kiro/hooks/plumb.json` (Windows: `Remove-Item .kiro\hooks\plumb.json`) →
      refused too.
- [ ] In another scratch folder, make `.kiro` a symlink to some other folder, then run `kiro.py install --project
      <that folder>` → it refuses to write through the symlink, with `error:` and `ask the user:` lines; nothing written.
- [ ] **Windows:** run the same install from cmd.exe, PowerShell and Git Bash; each hook command is a
      `powershell -NoProfile -NonInteractive -EncodedCommand …` line. Check the refusals and the
      session line work, note the extra start-up time (about 0.3 s per hook is expected), and check that a machine
      without Python never blocks a tool call.
- [ ] `PY <repo>/plugins/plumb/scripts/kiro.py uninstall --project <scratch project>` removes only Plumb's files (your
      own skills and hooks stay).

---

## 7. Pages in a browser (headless only)

Write a small script (never open a visible window), e.g. `check_pages.py`:

```python
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

pages = [Path(p).resolve() for p in sys.argv[1:]]
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    for path in pages:
        for scheme in ("light", "dark"):
            for width in (1280, 390):
                page = browser.new_page(viewport={"width": width, "height": 900}, color_scheme=scheme)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("request", lambda r: r.url.startswith("http") and errors.append("network: " + r.url))
                page.goto(path.as_uri())
                overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
                page.screenshot(path=f"{path.stem}-{width}-{scheme}.png", full_page=True)
                print(path.name, width, scheme, "errors:", errors or "none", "| horizontal scroll:", overflow)
                page.close()
    browser.close()
```

```
uv run --with playwright python check_pages.py <repo>/docs/what-you-get.html plumb-scratch/docs/design/specimen.html plumb-scratch/docs/design/prototype.html plumb-scratch/docs/design/screens.html
```

**Expected:** no errors, no network requests, no horizontal scroll at 390 px, and both themes readable in the
screenshots.

**The walkthrough player** (still headless): in the same script, open `plumb-scratch/docs/design/tours/first-look.html`
(from 3.5) at 1440 and 1280 wide, wait for the tour to start, then:

```python
frame = page.evaluate("document.getElementById('pp-frame').getBoundingClientRect().width")
cols = page.evaluate("[...document.querySelectorAll('.pp-side, #pp-rail')].filter(e => e.getClientRects().length).length")
page.keyboard.press("h")
pill = page.inner_text(".pl-pill")
dock = page.evaluate("document.querySelector('.pl-dock').hidden")
print("frame", frame, "| side columns shown", cols, "| pill", pill, "| dock hidden", dock)
```

**Expected:** `frame` at least 768 at both widths (the screens list and the rail fold away while the tour runs),
`side columns shown 0`, `pill Show panel` (play mode: only the button; the subtitle keeps playing), `dock hidden True`.
Press `h` again: the panel is back. Reload: a panel you hid stays hidden until you show it. Press Esc: the screens
list and the rail come back. In guide mode on a "your turn" step with the panel hidden, the pill offers "Do it for
me", and a wrong click brings the panel back with the hint.

---

## Report format

```
Machine: <OS + version>, Python <ver> (<command>), git <ver>, Claude Code <ver|none>, Copilot CLI <ver|none>, Kiro <ver|none>, tmux <ver|none>
Level 1: <N passed, M skipped (reasons) / failures with names>
Level 2: <pass/fail>
Level 3: <each step: pass/fail + notes>
Level 4: <each checkbox: pass/fail + notes>
Level 5: <each checkbox: pass/fail + notes, or skipped>
Level 6: <each checkbox: pass/fail + notes, or skipped>
Level 7: <each page × width × theme: pass/fail>
Problems: <exact command + output for every failure>
```

## Cleanup

Delete the scratch folders. For Kiro: `kiro.py uninstall --project <path>` for each project you installed into, and
`kiro.py uninstall` if you also installed into your home folder.

---

*Maintainers: keep this file in step with the features — see "Keeping docs in step" in AGENTS.md.*
