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

**Expected:** every test passes. Skips are listed with their reason (`-rs`). Every platform or tool skip reason starts
with one of `requires macOS`, `requires Windows`, `requires POSIX` or `requires xcrun` (for example the Windows-only
`run.cmd` and PowerShell hook tests, and, on macOS with xcrun, the Swift type-check of the generated theme); browser
tests skip with `requires Playwright` when Playwright isn't installed. Report the last line (`N passed, M skipped …`).

To run the browser tests too (they render every generated page in light and dark, headless):

```
uv run --with pytest --with playwright python -m playwright install chromium
uv run --with pytest --with playwright pytest -q -rs
```

**CI** (`.github/workflows/test.yml`) runs the whole suite on Ubuntu, macOS and Windows × Python 3.9 and 3.13, installs
Playwright and Chromium on every runner, and sets `PLUMB_STRICT_SKIPS=1`: `tests/conftest.py` allows only skips whose
reason starts with `requires macOS`, `requires Windows`, `requires POSIX` or `requires xcrun`; any other skip (such as
`requires Playwright`) fails the run.
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
```

**Expected:** the dry run lists `would write:` lines and writes nothing; the real run ends `done: 38 written, 0 kept`.
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

---

## 4. Claude Code live (the real thing)

Use a fresh scratch project (a small app is best: a Next.js + Tailwind folder works without `npm install`; Plumb never
needs it). Load the plugin from your clone:

```
cd plumb-live && git init
claude --plugin-dir <repo>/plugins/plumb
```

Try, in order, and report what happens. Use tmux (or a second terminal) if you want pane captures as evidence.

- [ ] `/plumb:init` → the "Plumb found … I'll create … OK, or change something?" block, nothing written before you say
      OK; then "existing or new?" with the detected one marked (Recommended).
- [ ] Choose **create**. The product questions come before any design question; every question has options with one
      marked (Recommended) and a reason; it asks before writing `docs/design/directions.html`; the directions page
      opens from disk and shows 2–3 distinct directions in light and dark.
- [ ] It shows the full token set (light and dark) and the `scaffold.py --dry-run` file list, and writes only after you
      say OK. The audit on the components it writes exits 0; `docs/design/specimen.html` exists.
- [ ] Every decision is in `docs/design/decisions.md` with `Decided by:` your git name.
- [ ] Init's wire-in: each item is asked on its own (`PLUMB.md`, both checks, the `AGENTS.md` row, the Makefile).
- [ ] Start a **new** session. The first context line is
      `Plumb: <project>-design-system 1.0.0 · tokens up to date · N audit issues · read the skill before UI changes`
      (ask the agent "what did the Plumb session note say?").
- [ ] Ask the agent to add `className="bg-[#3b6fd4]"` to a component → **refused** by the edit check:
      `Plumb edit check: this edit adds 1 design-system error …`, `error: line N: raw colour #3b6fd4` and a `fix:`.
      The agent then uses a token instead.
- [ ] Ask the agent to edit the generated CSS copy (e.g. `app/globals.css`) by hand, and then with
      `sed -i` → both **refused** (`… is generated from the design tokens; a hand edit is lost on the next build`).
- [ ] Ask the agent to create a new page (`app/reports/page.tsx`) → **refused**:
      `error: app/reports/page.tsx is a new screen with no approved prototype` / `fix: /plumb:prototype reports …`.
- [ ] `/plumb:prototype reports` → 2–3 variants, `proposals/reports/index.html` side by side, both views each; you pick
      one; it asks before writing it to main; `prototype.html#screen-reports` shows it with a default walkthrough; it
      asks you to approve it, then records the decision. Now the agent can create the page.
- [ ] `/plumb:tour` → asks who is watching; shows the steps as a table; writes `tours/<id>.json` only on your OK;
      `docs/design/tours/<id>.html` plays offline.
- [ ] Map the built screen (`build-prototype.py --map reports --route /reports --files "app/reports/**"`), then ask the
      agent to change what the reports page shows **without** touching its screen file → at the end of the turn the
      agent is stopped once with `Plumb end-of-turn check: …`; it updates the screen file and asks you to approve it.
      It does not loop.
- [ ] `/plumb:audit` → terminal summary, `docs/design/audit-YYYY-MM-DD.html` with an Agent review section; then
      `/plumb:audit fix` groups the issues and asks before each group.
- [ ] `/plumb:ux reports` → asks for the dev server URL (say "not running": it reviews the prototype and the code),
      writes `ux-review-YYYY-MM-DD.html`.
- [ ] `/plumb:update add iOS` → shows the dry-run list (your files `skip: … (yours, kept)`), asks, then writes the
      iOS theme; the decision is recorded; the audit runs.
- [ ] **Upgrade from an older version:** change `PLUMB.md`'s first line to `<!-- plumb v0.9.0 · …` and start a new
      session → the second context line says `… run /plumb:upgrade`. `/plumb:upgrade` shows What's new for 1.0.0,
      asks, refreshes Plumb's files, migrates, runs the checks, sets the version line back to 1.0.0 and adds a dated
      "Plumb updates" line. It never deletes a value.
- [ ] `/plumb:status` → a short read-only report ending with the next step.

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

- [ ] Type `/plumb` → the ten commands are listed (`/plumb:init`, `/plumb:create`, …).
- [ ] Ask "what does the Plumb session note say?" (no tools) → it quotes the `Plumb: … read the skill before UI
      changes` line (session start reached Copilot as additional context).
- [ ] The raw-colour edit, the hand edit to a generated file (with the edit tool and with a shell write) and the new
      page are **refused with Plumb's reason** (the `error:` and `fix:` text), not just "hook exited with code 2".
- [ ] `/plumb:prototype` and `/plumb:status` run as in level 4.
- [ ] End-of-turn: change a UI file with a raw colour while the edit check is off (`Edit check: off` in `PLUMB.md`),
      and record whether Copilot continues to fix it (its `agentStop` honours the block) or only shows the summary.
      Either is acceptable; record which.
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
- [ ] In Kiro, `/plumb-init` runs the init flow (questions one at a time).
- [ ] Session start shows the `Plumb: …` line, with commands written `/plumb-…`.
- [ ] A raw-colour edit with Kiro's write tool, and a shell write to a generated file, are refused with Plumb's
      `error:` / `fix:` text. Record which exit code blocks and the exact hook input fields Kiro sends (the spec waits on
      this).
- [ ] **The Stop decision:** let a change with a new error reach the end of the turn (set `Edit check: off` in
      `PLUMB.md` first). The hook answers `{"decision": "block", "reason": …}` on stdout, exit 0. Record whether Kiro
      makes the agent continue and fix it, or only adds the text to its context; and whether the report-only follow-up
      (`{"systemMessage": …}`) shows as raw JSON. Either is acceptable for now; record which, in the IDE and the CLI.
- [ ] Ask the agent to edit `.kiro/hooks/plumb.json` by hand → refused (change the checks in `PLUMB.md`, refresh with
      `kiro.py install`).
- [ ] **Windows:** run the same install from cmd.exe, PowerShell and Git Bash; each hook command is a
      `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand …` line. Check the refusals and the
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
