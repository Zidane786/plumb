# Plumb design spec

- **Status:** draft for review · 2026-10-11
- **Release:** everything here ships in **1.0.0**
- **Repo:** `github.com/Zidane786/plumb` (default branch `main`)

A builder's plumb line keeps a wall true. Slate plans the work; **Plumb keeps the design true.**

## 1. Purpose

Plumb is a plugin for **Claude Code and GitHub Copilot CLI** (one plugin, same files). It helps
any project build and keep a **design system**, so every screen an agent builds uses the same
tokens, components, patterns and words, on the web and on phones.

It is repeatable: the process that produced one hand-built design system (one token source
generating web, SwiftUI and Compose themes, component specs, accessibility, motion, vocabulary,
dark mode with contrast evidence, an inventory and an audit that must exit 0) becomes commands any
project can run.

**Who uses it:**

- **Agentathon practice-week participants** create a design system on Day 1, prototype their
  screens, then build them.
- **The Agentathon starter kit** ships with Plumb installed.
- **Teams on existing codebases** extract the system they already have, clean it up and keep it.

**Success means:**

1. A new project goes from "an idea" to a design system, a chosen look and chosen screen
   prototypes in one guided session, with every decision recorded.
2. An existing project gets a design system that matches what it already ships, plus a ranked
   list of the inconsistencies that don't match.
3. While agents build, edits that bypass the system are stopped, and changed screens are checked
   before the agent hands back.
4. The same flow works in Claude Code and Copilot CLI, on macOS, Linux and Windows.

## 2. Decisions already made

| Topic | Decision |
|---|---|
| Name | **Plumb**. Commands `/plumb:<name>`. A project's system is named `<project>-design-system` (proposed from the project name, changeable). |
| Release | Everything in **1.0.0**. Then semver: patch for fixes, minor for compatible features, major only for work that reshapes existing projects. |
| Repo | Same files, CI, releases, settings and rulesets as Slate (done and verified identical). Default branch `main`. Every change through a PR the user merges. |
| Instructions | `AGENTS.md` is the only instructions file; `CLAUDE.md` imports it. |
| Tooling | Python 3.9+ standard library only for everything that ships. No npm/npx for Plumb's own tooling. Generated output may target the project's stack. |
| Tools | Claude Code and Copilot CLI, one plugin. VS Code Copilot Chat is not supported. |
| License | MIT. |
| Attribution | No AI attribution in commits or PRs. |

## 3. Commands

| Command | When | Does |
|---|---|---|
| `/plumb:init` | First time in a project | Finds the right home, routes to create or extract, wires Plumb into the project. |
| `/plumb:create` | New project | Product interview → design interview → 2–3 directions → the design system → prototypes of key screens. |
| `/plumb:extract` | Existing UI | Inventories every value in use → clusters → a clean token set → the same design system. |
| `/plumb:prototype` | A new screen, tab, flow or interaction | 2–3 variants, each as a clickable prototype and an every-state screens view → you pick → written into the main prototype, the reference to build. |
| `/plumb:tour` | An extra or custom walkthrough | Writes a walkthrough script beyond the default one prototype makes (a client demo, another audience, several flows); the prototype plays it in guide mode or play mode. |
| `/plumb:audit [fix\|improve]` | Any time | Report (HTML + terminal + exit code); `fix` repairs issues with your OK; `improve` finds and, with your OK, makes the system and screens better (prototype first). Offers Slate tickets. |
| `/plumb:ux` | After building a screen or flow | UX review against the project's UX rules and its prototype; HTML report; offers Slate tickets. |
| `/plumb:update` | The design changes | Change or add tokens and components, add a platform, improve a part; regenerate; record; audit. |
| `/plumb:upgrade` | The plugin has a new version | Brings the project's copied files, tokens format and `PLUMB.md` up to the plugin's version. |
| `/plumb:status` | Health | Version, platforms, stale files, audit counts, hooks on/off, linked repos. Writes no file; in a set-up project never suggests create or extract. |
| `/plumb:feedback` | Plumb itself got something wrong | Plumb mistakes only: the agent records each Plumb result it corrected in `~/.plumb/feedback/` (outside the project); typed, it reports every record grouped, most frequent first, and drafts GitHub issue text (never sent). Model-invocable. |

Every skill asks one question at a time through the question tool, with options and a
recommendation first, and never writes into a project without saying where. Skills that run a
heavy flow (create, extract, upgrade, update) only run when the user typed them; other skills may
*offer* them.

**What the user confirms is inside the question** (live test 2): the "Plumb found" block, the
"Right?" summary, decisions, the token set, the dry-run file list, a diff or a mapping is the
question text (or the recommended option's preview), never only a message before it, because
Claude Code can hide text printed right before a question; Copilot CLI's ask tool takes it in
the question text. **Scripts give evidence, not answers:** no script output is golden; the agent
checks every result against the code, corrects or adds to it (marked `(corrected: <why>)` /
`(added: <why>)`) and shows that inside the question; a script wrong in a way that will recur is
reported upstream (an audit false positive may go on `PLUMB.md`'s `Allowed raw values:` after the
user's OK), and every Plumb mistake the agent corrects is recorded with `/plumb:feedback` (§3.10). **Investigate first:** before asking, the agent gathers every fact the code can answer
into an evidence table (fact, value, `file:line`, confidence); facts are shown as `found: …` to
confirm, and only what the code cannot tell is asked. **Scripts read what the user confirmed;
they don't guess the layout:** the UI files and the route roots (`PLUMB.md` `UI files:` and
`Routes:`) come from the investigation, are confirmed with matched-file counts, and are what the
audit and the hooks read. Every skill resolves the plugin root and the project root first and
reads files only under them; scratch files go only in `<root>/.plumb-tmp/` (status writes none).

### 3.1 `/plumb:init`

```
/plumb:init
  1. find the home        detect the layout (§4) → show → you confirm
  2. linked?              "this repo uses a design system that lives in another repo"
                          → PLUMB.md with the path + the AGENTS/CLAUDE row pointing there → done
  3. existing or new?     asked, pre-filled from detection: UI code exists → extract, else → create
  4. wire it in           each asked: PLUMB.md · AGENTS.md/CLAUDE.md row · Makefile targets ·
                          both checks (recommended on) · Slate review check (if Slate is set up)
```

Re-running init in a set-up project shows status and offers `/plumb:upgrade` when the plugin is
newer. It never overwrites an existing design system. A skill path the repo's `.gitignore`
ignores is never accepted silently: init shows the ignoring line and asks (un-ignore the skill
folder with `.claude/*` + `!.claude/skills/`, recommended, or another location), and the check
runs again after the change. A leftover marker `<root>/.plumb-tmp/setup-in-progress` marks a
half-finished setup: init offers to resume. A new `AGENTS.md` is a
whole file (title, `## Read before you work`, the table header, the row).

### 3.2 `/plumb:create`

**Nothing is written without the user's OK.** Every fact Plumb detects (project root, framework,
styling, platforms, brand colours and fonts found in the code) is a suggestion the user confirms or
corrects. Before generating, the user approves the full token set (light and dark); before writing,
the dry-run list of every file and path; each contrast fix; and which components are written, in
which framework and where. When a web copy is a stylesheet the project already has (e.g.
`app/globals.css`), the build's change is shown first (`build-tokens.py --check` prints the diff)
and asked: Plumb adds and owns only a marked `plumb:start … plumb:end` block; the rest stays the
project's. When that stylesheet sets its own variables in the tokens' namespaces (a stock
create-next-app `@theme inline { --color-background; --color-foreground; --font-sans; --font-mono }`,
the audit's `block-override`), create and extract show each with the token it maps onto
(`build-tokens.py --overrides`) and ask once, "move them into the tokens" recommended; only on yes
does `--overrides --apply` add the tokens and remove the lines, so a fresh create on a stock app
ends with the audit at 0. Two choices become tokens settings the generator honours: how the app switches themes
(`$extensions.plumb.web.theme_switch`: `both`, `system`, `class` or `data-theme`, the attribute
next-themes sets by default; answers key `theme_switch`)
and reduced motion (`$extensions.plumb.motion.reduced`: `keep-fades` or `none`; answers key
`reduced_motion`); extract always asks both, recommending what the app already does. The same
applies to extract (each token group, the screens to prototype, the files to write) and to init's
wire-in steps. `PLUMB.md` names the direct commands; the `(make …)` hints are added only when the
user says yes to the Makefile targets, and `scaffold.py --verify` reports a make target `PLUMB.md`
names that the Makefile lacks.

**Checkpoints that stop and wait** (live test 2, where an agent skipped the direction pick, the
token set and the file list and ran the scaffold unasked): create and extract are numbered
checkpoints, each ending "STOP: ask, wait for the answer"; a tool's permission prompt never
counts as the user's OK. The real scaffold needs `--confirm <token>`, printed only by the dry run
the user approved (in create, extract, update and upgrade alike). Tailwind projects record
`$extensions.plumb.web.reset_palette` (answers key `reset_palette`; the reset covers all six
namespaces, and with `false` the audit still flags off-scale defaults such as `text-lg`): create
on a new app recommends the reset (only the tokens' values exist);
extract, or create on an app that already uses Tailwind's palette classes, recommends keeping
them, with the count, and the audit suggests moving them onto tokens. The theme-switch
recommendation follows one ordered rule (next-themes `attribute="class"` → `class`), with the
evidence `file:line` in the question; Tailwind's own dark config (v4 `@custom-variant dark`, v3
`darkMode`) counts as evidence, and an attribute Plumb doesn't follow leads to recommending a
switch to `class`. The UX patterns are seven questions. **Setup in progress is the marker file
`<root>/.plumb-tmp/setup-in-progress`**: only init, create and extract write it, from the
placement OK to the end of setup; the end-of-turn check stands down while it exists, and init's
resume check and status read it; setup ends by removing the whole `.plumb-tmp/`. Other commands
may keep scratch files in `.plumb-tmp/` and clean up their own, never writing the marker. A long
diff in a question is a summary plus the first ~40 lines, with the full diff in `.plumb-tmp/`.
`PLUMB.md` `Routes:` is `<path> (<kind>)` (`next-app`, `next-pages`, `nuxt`, `sveltekit`,
`router`, `angular`) or `none`; the kind comes from the investigation, never from a folder name.
Before saying done, the agent walks a final checklist: every checkpoint that applied asked (any
that did not: which and why), contrast evidence, components, the decision log, a first prototype
screen (or the user's "later"), the wire-in, `.plumb-tmp/` removed.

**A. The product first** (questions grouped up to four at a time, each with suggestions drawn from
the brief, README, `AGENTS.md`/`CLAUDE.md`, `SLATE.md` and any prototype or brand files found):

- what is being built, in one sentence;
- who it is for (suggested audiences), and their skill and context;
- where and how often it is used (desk, phone, both; glanced at or worked in all day);
- the key tasks and flows (the 3–5 things people come to do);
- the feel (with example products as reference points);
- existing brand: logo, colours, fonts, guidelines.

**B. Platforms and stack.** Web, iOS (SwiftUI), Android (Compose), multi-select. The web
framework (React/Next, Vue, Svelte, Angular, plain HTML, …) and styling (Tailwind v4, Tailwind
v3, plain CSS; shadcn when present) are detected, then confirmed.

**C. Design decisions**, one at a time, each with options and a recommendation that follows from
A: personality and register · audience density · accent · neutrals · semantic colours (success,
warning, danger, info) · label colours · type family and scale · spacing scale · radius ·
elevation · motion and reduced motion · icons · dark mode · accessibility target (WCAG 2.2 AA by
default) · vocabulary and voice · **UX patterns** (navigation model, page anatomy, forms,
feedback, empty/loading/error states, destructive actions, onboarding).

**D. Directions.** 2–3 directions as one Effective HTML page, `docs/design/directions.html`
(Plumb's own simple template when Effective HTML is not installed). Each shows the palette, type,
components and one real screen of the product in light and dark. You pick one or combine them.
**Quality bar:** directions and prototype variants follow Effective HTML's `design-artifact`
principles (a deliberate palette and type pairing, real hierarchy, real content, nothing that
looks generically machine-made); each direction must be a distinct, finished-looking option, not
three recolours of one layout.

**E. Generate**, in order: tokens JSON → `build-tokens.py` (themes) → contrast computed, failures
fixed with your OK → the skill files (§5) → the agent writes the starter components in the
project's own framework from the specs (§5.3) → `audit.py` exits 0 → `docs/design/specimen.html`.

**F. Prototypes.** Offers `/plumb:prototype` for the key screens from the key tasks in A; the
chosen variants become the first main prototype (`prototype.html` + `screens.html`, §3.4).

**G. Record** every choice in **`docs/design/decisions.md`**, Plumb's design decision log, always
written: one entry per decision with the date, what was decided, the options considered (with
links to the directions page or proposals), the one chosen and why, **who decided** (git
`user.name`), the screens it affects and the Slate ticket if any. Entries are append-only and
carry a collision-free id (`DS-YYYYMMDD-<slug>`), so several teams can add decisions on separate
branches without merge conflicts. Each entry is mirrored into `docs/decisions.md` when the project
keeps one, and noted in `design.md`'s revision notes.

### 3.3 `/plumb:extract`

1. **Scan** CSS, SCSS, Tailwind config, components, inline styles, HTML files, and Swift/Kotlin
   theme files.
2. **Inventory:** every colour, font family, size, weight, line height, spacing, radius, shadow,
   duration, easing and component variant actually used, with counts and `file:line`.
3. **Cluster** near-duplicates: colours by perceptual distance (CIEDE2000 ΔE below 3), sizes by
   step (within 1px or 6%). The most-used value of a cluster is proposed as its token.
4. **Propose** a clean token set as a before/after page (`docs/design/extract.html`); you confirm
   group by group, renaming or merging as you like.
5. The product and UX questions from create A and C that the code can't answer, then create
   **E–G** (no directions step: the look already exists).
6. **Main prototype** from the existing app: every route becomes a screen file with its states
   and interactions (§3.4), mapped in `screens.json`.
7. **Audit** what does not match the new system yet; offer Slate tickets.

### 3.4 `/plumb:prototype` and the main prototype

Every project with Plumb has **one main prototype of the whole product**, always matching the
real frontend:

- `docs/design/prototype.html`: the clickable app. Every screen, its navigation and its
  interactions work as they do in the real UI (links, tabs, dialogs, menus, form validation,
  toasts), with a state switcher, a phone/desktop toggle and a light/dark toggle.
- `docs/design/screens.html`: the catalogue. A navigation sidebar and every screen in every state
  (loading, empty, error, success, disabled, long text, zero, offline where relevant), plus every
  control state (default, hover, focus, pressed, disabled, loading).
- `docs/design/app.html`: the app view, for a demo. Every screen full window, with none of the
  prototype's panels (§3.4.2).

**One source per screen.** Both pages are assembled from `docs/design/prototype/screens/<id>.html`
(one file per screen, its states marked with `data-state`, its interactions inline) by
`build-prototype.py` (§6.3), which also writes `docs/design/prototype/screens.json`: each
screen's id, title, states, its route and the source files that implement it. Editing one screen
file updates both pages, so they cannot disagree. The token block in every page comes from
`build-tokens.py --css-vars`, so prototypes are token-true, and `audit.py` must exit 0 on them.

**Shared files.** CSS and scripts several screens use live once in `<screens folder>/_shared/*.css` and `*.js` (the
main `prototype/screens/` and each variant's `screens/`; the folder is reserved, nothing in it is a screen). The CSS
is inlined once per page in name order, selectors scoped by the author (`[data-screen]`; anything else is a warning);
each JS file runs for every screen, before the screen's own script, as `function (screen, plumb)` with the same API, in
name order, in every page (the catalogue's copies and the tour pages included). They are part of every screen's
approval hash (with none, it is the screen file's own hash, so approvals recorded before stand): editing one makes
those approvals stale, and the build names the file. Shared files are checked before they are inlined: no `</script>` /
`</style>` inside, nothing loaded from the network or another file.

**Change ids.** A change may mark each element it touched `data-guide="<ID> · what changed and why"`, `<ID>` a letter
and digits (`F01`). A proposal lists its ids in `proposals/<name>/changes.md` (`- **F01** title: what and why`);
`--proposal` refuses an id used but not listed (naming the screen and the id), warns about a listed id no screen uses,
and the index lists the changes. The main screens' ids are checked only when `docs/design/prototype/changes.md`
exists. The Guide panel shows the id as a chip; data-guide text without an id is never checked.

**Decisions are visible in the prototype.** `build-prototype.py` reads `docs/design/decisions.md`
and shows, on every screen, a "Why it looks like this" panel with the decisions that affect it
(id, date, who, the options considered, links to the proposals), and adds a Decisions page to both
`prototype.html` and `screens.html`. When several teams work on one product, anyone opening the
prototype sees what was decided for each screen and by whom, before changing it.

`/plumb:prototype <screen | flow | interaction>` (a whole new project, a new tab or screen, or a
single new interaction):

1. **Brief:** what the screen is for, which key task, which states matter; read
   `references/ux.md`, `components.md`, `inventory.md` and the main prototype. In an existing app,
   also read the current screens and components it should sit beside.
2. **Variants:** 2–3 variants of the same screen or flow that differ in UX (layout, flow, density,
   navigation), all on the same design system, built with Effective HTML's `html-prototype` when
   installed. **Each variant comes as both views:** its clickable prototype and its screens
   catalogue with every state, so you compare how loading, empty and error look, not only the
   happy path. Mobile platforms are shown in a phone frame with that platform's conventions.
3. **Choose:** an index page (`docs/design/prototype/proposals/<name>/index.html`) shows the
   variants side by side; you pick one or ask for changes.
4. **Write to main:** the chosen variant becomes `screens/<id>.html` source files, is linked into
   the main prototype's navigation, `build-prototype.py` rebuilds `prototype.html` and
   `screens.html`. The other variants stay in `proposals/<name>/` (both views) as the record;
   their token blocks are refreshed when tokens change so they still render, but they are not kept
   in step with code.
5. **Record:** an entry in `docs/design/decisions.md` (§3.2 G) linking the proposals and the
   chosen screen; `inventory.md` lists any new component the screen needs;
   `screens.json` marks the screen "to build" until its route and source files exist.
6. **Binding:** the main prototype is the reference to build. Agents read the screen before
   building it; `/plumb:audit` and `/plumb:ux` compare the built screen with it; Slate tickets
   link it in "done when".

**Prototype first, then build.** Every UI change that adds or changes a screen, tab, flow or
interaction follows one order: update or create the screen in the prototype → **you validate it**
→ then the real UI is built to match. Your approval is recorded per screen in `screens.json`
(who, when, and a hash of the approved screen file).

- **New screen or route:** the edit check refuses to create a page or route file that is not in
  `screens.json` (`error: app/billing/page.tsx is a new screen with no approved prototype`,
  `fix: /plumb:prototype billing`).
- **Changing an existing screen:** the agent updates its screen file first and asks you to
  validate; the end-of-turn check stops the agent once if code changed for a screen whose current
  prototype is not approved.
- **Small fixes** that don't change what a screen shows or how it behaves (a bug in logic, a
  typo, data wiring) need no prototype step.

**Always in step, both ways.** A UI change is not done until the main prototype shows it:

- prototype → code: a screen marked "to build" stays listed in `status` and the audit until its
  route exists;
- code → prototype: when a screen's source files (from `screens.json`) change in a session and its
  `screens/<id>.html` did not, the end-of-turn check stops the agent once ("update prototype
  screen booking: states loading, empty") and `/plumb:audit` reports the drift as an error;
- a new route or page with no screen in `screens.json` is reported as "not prototyped".

A screen file updated to match code that was already built (a small fix, or code written before
Plumb) is marked "synced from code" rather than approved; `status` and the audit list these for
you to confirm, without blocking.

`/plumb:create` builds the first main prototype from its key screens; `/plumb:extract` builds it
from the existing app (every route, at the same level of interaction). When tokens change,
`/plumb:update` rebuilds the token blocks and the drift check covers them.

**The project's design system outranks Effective HTML.** In a project, its
`<project>-design-system` (tokens, `design.md`, references) is the authority for every page and
screen Plumb produces. Variants, screen files and pages follow the `html-prototype` and
`design-artifact` skills when installed, for craft only (real content, every state, working
interactions, keyboard and focus, accessibility, polish); the palette, typography, spacing, radius
and motion always come from the system, and where the two disagree the system wins. When the skills
are not installed, `reference/prototypes.md` carries the same craft rules. Prototypes use only the
inlined token block and the audit exits 0 on them. The one exception is create's directions page,
written before any system exists: each direction is a candidate system.

### 3.4.1 Walkthroughs and `/plumb:tour`

Three things, kept apart: `/plumb:prototype` makes the **screens**; the **walkthrough player**
(guide mode and play mode) is built into every `prototype.html` by `build-prototype.py`, so every
prototype can play a walkthrough; a walkthrough's **script** (which steps, which words) is a tour
file. `/plumb:prototype` writes a default one for every flow it builds; `/plumb:tour` writes extra
or custom ones. The prototype stays fully clickable with or without them.

The prototype shell has a **walkthrough player** in every project. A walkthrough is a data file,
`docs/design/prototype/tours/<flow>.json`: an ordered list of steps, each naming a screen, a
state, the element to spotlight, a title, a caption, and an optional action (click, type, choose,
wait). One file drives two modes:

- **Guide mode:** step by step with Next and Back (arrow keys, Esc to leave), a spotlight and a
  coach mark on each step's element. For a reviewer or a new teammate.
- **Play mode:** plays the flow like a video for a client or a demo: the actions run by
  themselves, captions show what is happening, a progress bar has a marker per scene that you can
  jump to, and controls for pause and resume (Space), restart, and **speed (0.5×, 1×, 1.5×, 2×)**.

Also in the shell: a per-screen guide panel (what this screen is for, what you can do here,
"try it" buttons, and a feed of what just happened), and a link to any walkthrough or scene
(`prototype.html#tour-<flow>` / `#tour-<flow>-<n>`) to share with a client. With reduced motion,
play mode still plays by itself and only drops the cursor glide and other animation (an OS
setting must never turn Play into Guide). Captions are `aria-live`, and every control works by keyboard.

**Custom tours** serve demos, user training, teammate onboarding, design review and "what's
new". A tour file sets: its audience and purpose (which sets the caption tone and the mode that
opens first); the screens and states, across one flow or several; per step the target, title,
caption and action (click, type, choose, wait); pacing (default speed, a longer hold on a step);
**chapters** (named groups of steps, shown as scene markers); an **intro and a closing card**
("what you'll see", "what to try next"); and **"your turn" steps** for teaching: in guide mode
the tour waits until the learner performs the action on the real control in the prototype (a
wrong click gets a hint), while play mode performs it by itself, so one tour is both the demo and
the hands-on lesson.

Each step can **add text** and **point** in several ways, mixed freely:

- **Text:** a caption (subtitle line, play-mode narration); a callout bubble attached to an
  element on a chosen side; labels (numbered or named tags on several elements at once); a note
  placed anywhere; a title card between scenes (intro, chapter, closing); typed text entered into
  a real field (letter by letter in play mode).
- **Pointing:** spotlight (dims the rest), ring (outline, rest visible), arrow with a short
  label, beacon (a pulsing dot; static with reduced motion), zoom (enlarges an area), the cursor
  (moves and clicks in play mode), and several rings or labels in one step.

Annotations use the project's tokens and vocabulary, captions and callouts are announced to
screen readers, and every control stays keyboard-reachable. `build-prototype.py --check` validates
every target an annotation points at. **Every tour is also its own HTML file.** `build-prototype.py` writes
`docs/design/tours/<tour>.html` for each tour: one self-contained file with the whole prototype
(screens, tokens, interactions) and that tour, opening straight into it (play mode for a demo,
guide mode for training, from the tour's audience). It opens from disk with no server and no
network, so it can be emailed to a client or put in training material; viewers can leave the tour
and click around the prototype. It is generated: the guard blocks hand edits, `--check` fails when
it is stale, and it is rebuilt whenever a screen or the tour changes.

**Where a tour plays (owner amendment, 2026-10-14).** Each tour file has `"view": "app" | "prototype"`;
**missing means `app`**, and anything else exits 2 naming the tour file, the line and the fix.
`tours/<id>.html` follows it: `app` is the app view (§3.4.2) with the player on top, a `<base
href="../">`, opening straight into the tour, its closing card linking "Open the prototype";
`prototype` is the prototype page (its screens list and decisions rail fold away while the tour
runs). `prototype.html#tour-<id>` keeps playing every tour in the prototype, and `app.html` itself
carries no player. `/plumb:tour` asks **"Where should it play?"** right after the audience
question (*Full-window app (Recommended)* · *Prototype page (with the screens list and the decisions
rail, for a design review)*), records it and shows both links at the end; `/plumb:prototype`'s
default tours are written without `view`. In both views `#tour-<id>[-<n>]` links work and the
player moves between screens (also through the clicks it makes) without adding history entries.
Because the page scrolls in the app view, a step's element is brought into view clear of the
screen's own top-anchored fixed or sticky bars (those across its columns, sticking to the window,
under half its height), and a zoom step on a screen showing a fixed layer points with a spotlight
instead (a transform on the frame would make it the containing block of those layers and pull
them to the top of the page). Both shells take the player's `--pl-*` roles from one shared
template, `templates/chrome-roles.css`, and `prototype.html` links "Open as app" to
`app.html#/<screen>[/<state>]`.

**Tour checks (owner amendment, 2026-10-14).** `build-prototype.py --check-tour <file>` validates one tour file against
the screens, as the build does, and writes nothing (exit 0 / 2). It also **warns** when a step's target, label or
action element sits in an element the screen's own CSS hides at some frame widths (`display: none`, `visibility:
hidden` or an off-canvas `transform` outside an `@container plumb-frame (min-width: …)` rule that shows it again, or
the reverse): "visible only when the frame is ≥ 48rem". It reads the `_shared/*.css` files and the screen's own styles (in the page's order): their top-level rules and
`@container plumb-frame` blocks with a standard-library reader (cascade by `!important`, specificity and order) and the selector
subset above; what it cannot read is left out. The runtime pass is plugin-side (ruling B4), `scripts/check-tour.py
<docs>/tours/<id>.html` (not copied into projects, like `screenshot.py`): with a browser screenshot.py's search finds
(or `--browser`), it writes a scratch copy under `<project>/.plumb-tmp/` (its `<base>` pointed at the original's
folder) with a checker script, runs it headless with `--dump-dom` and `--virtual-time-budget` at 1280 and 1440 wide
(light theme), and the checker walks every step in guide and in play mode through the player's API (play paused at
once, nothing waits real time). Per step: the page shows the step's screen and state; each target, label and action
element is laid out, not `visibility: hidden` or `opacity: 0`, not zero-size, inside the window and not covered at
its centre (the panel, a screen's fixed or sticky layer); the dock is not
covered (`elementFromPoint` at its centre). The results come back as JSON in the dumped DOM. Problems: exit 2, one line
per step and problem with the widths and modes (`step 12 (Users › Invite): the target ".invite" is hidden
(visibility: hidden) at 1280 (guide, play)`); no result or a hung browser: exit 1; no browser: exit 3 with a note and
a fix. Nothing is downloaded. `/plumb:tour` runs both after the build, fixes the steps they name, and with no browser
says so and asks whether to continue.

Turning a tour into in-app onboarding in the live product is out of scope
for 1.0.0.

`/plumb:prototype` **always writes a default walkthrough** for each flow it builds (you review
its steps and words together with the screens), and updates it when the flow changes.
`/plumb:tour <flow>` is for extra or custom ones: a client demo, a different audience, or a story
across several flows; it asks which steps, which words, and who is watching. `build-prototype.py --check` fails when a
step names a screen, state or element that no longer exists, so walkthroughs stay in step with
the prototype.

**Figma:** for this workflow Plumb replaces Figma for screens, flows, states and handoff (real
HTML, real tokens, audited, clickable, kept in step with the code). Figma remains better for
freehand visual exploration and illustration, designers editing together on one canvas, and
handoff to teams that don't build with agents.

### 3.4.2 The app view (`app.html`)

`build-prototype.py` also writes `<docs>/app.html` from the same screens, tokens and scripts:
every screen full window, with no prototype panels (no screens list, state switcher, frame or theme
toggles, decisions rail or player). **prototype.html is for reviewing, app.html for demoing**;
`/plumb:prototype` and the proposal index name both.

- **Routes:** `#/ID` and `#/ID/STATE`; `#screen-ID[/STATE]` works too, so the screens' own links
  and the prototype's addresses keep working. It opens on the first screen by `data-order` (no
  project-specific forwarding); an unknown id opens that first screen.
- **The same screen-script API** as `prototype.html`: `function (screen, plumb)` with
  `plumb.setState`, `plumb.go`, `plumb.state`, `plumb.catalogue === false`, plus `window.plumbTheme`
  and `window.plumbPrototype` (`go`, `setState`, `current`, `screen`, `setTheme`, `on`).
- **Theme:** the system setting until a screen's own toggle picks one, then remembered in
  `localStorage` (a per-viewer convenience: when storage is off or throws, the page still renders
  and the choice lasts the visit).
- **The window is the frame:** the frame (`#pp-frame`, inside the stage `#pp-stage` a tour page's
  player draws over) is `container: plumb-frame / inline-size` and spans the window, so the md
  breakpoint follows the window; it has `isolation: isolate`, so a screen's z-indexes never cover
  what is drawn over it.
- **Sidebar hook:** an element with `data-app-sidebar` in a screen is `position: sticky; top: 0;
  height: 100dvh` from the md breakpoint. Nothing else about a screen's layout is assumed.
- **Dialogs:** a long screen scrolls the page, so a change that opens a dialog (`dialog[open]`,
  `role="dialog"` or `"alertdialog"`, `aria-modal="true"`) brings it into view: a state change on the
  same screen, `plumb.go(other, state)` or a link straight to that state. Only a dialog the change made
  visible counts (on another screen: compared with its first state), so a dialog that was showing
  already (a docked help panel) never moves the page.
- **Fixed elements:** the frame is an inline-size container, which is no containing block for
  `position: fixed`, so a screen's fixed toasts and bars sit on the window as in the product. The frame
  and stage must not get `transform`, `filter`, `perspective`, `contain: layout`/`paint` or the like.
- **The md breakpoint** is the frame's width, the window minus a classic scrollbar (about 17 px on
  Windows): a window just over 48rem with such a scrollbar shows the layout below md.
- Generated like the other pages (byte-stable, offline, light and dark; `--check` reports it stale
  or missing; the tokens build refreshes its token block). Each proposal variant gets its own
  `proposals/<name>/<variant>/app.html`. `app.html` itself carries no player.

### 3.5 `/plumb:audit`

Runs `audit.py` in full mode (§6.2) on the project's UI paths: every rule, cross-file checks,
contrast, drift, and **prototype fidelity**: every screen in `screens.json` has its route, the
built screen uses the same components, states and copy as its prototype file, and no source file
changed after its screen file. With a browser available, the skill also takes headless
screenshots of each built route and its prototype screen at the same width and theme and flags
layout differences above a threshold (pixel-perfect matching is not the goal; missing screens,
missing states, different components or copy, and layout drift are).

Writes `docs/design/audit-YYYY-MM-DD.html` (issues ranked by severity, each
with `file:line`, what's wrong, the token or component to use, the fix), prints a terminal summary
and exits 0 when there are no errors. When Slate is set up, it offers to create tickets for the
fixes, grouped by area, written only through `board.py`. With no design system yet (a prototype or
a project before extract) it runs in inconsistency-only mode.

**The script is the floor, not the ceiling.** `audit.py` catches everything that can be written as
a rule, the same way every time (and is what the hooks and CI rely on). The audit skill does not
rely on it alone: after the script, the agent reviews the screens in scope against `design.md`,
`ux.md` and the prototype for what no rule expresses (hierarchy broken while still using tokens,
two screens solving the same thing differently, wording off the vocabulary, an unhelpful state,
something that looks wrong in dark mode). Those findings are marked **agent review** in the report,
separate from rule findings; when the agent keeps finding the same kind of problem, it proposes it
as a new rule.

**Three modes.** `/plumb:audit` reports only (errors, warnings, and the Improvements list).
`/plumb:audit fix` fixes errors and warnings: it groups them (e.g. "12 raw colours → tokens"), shows
each group, asks, applies it, and re-runs until clean; anything that changes how a screen looks goes
through the prototype first. `/plumb:audit improve` is for a project that already passes (or after
`fix`): it goes beyond the rules with the suggestions plus a design pass across the product
(hierarchy, spacing rhythm, consistency between screens, states, dark-mode polish, accessibility
beyond AA), produces a ranked improvement plan, and for each item the user picks: prototype first →
approval → build. Changes to the design system itself are proposed here and made in `/plumb:update` (§3.7). `improve` also improves **the design
system itself** when the findings show it should change (a missing or mergeable token, a component
spec that needs a variant, a `ux.md` or `design.md` rule that screens keep breaking for a good
reason): with the user's OK, `/plumb:update` updates tokens and specs, regenerates the themes,
refreshes the prototypes, records the decision, and re-runs the audit. Every change is recorded in the decision
log; any item can become a Slate ticket instead. `/plumb:ux` remains the deep review of one screen
or flow; `audit improve` looks across the whole product and the system.

### 3.6 `/plumb:ux`

Reviews a screen or flow against `references/ux.md`, its screen in the main prototype,
usability heuristics (visibility of status, match with the real world, user control, consistency,
error prevention and recovery, recognition over recall, minimal design, help), accessibility
beyond contrast (keyboard path, focus order, labels, target sizes, reduced motion), and a **visual
polish pass** (hierarchy, spacing rhythm, alignment, type details such as tabular numbers and line
length, density, how motion feels), so screens are not only consistent but polished.

- With a browser available (the agent's browser tool, or `uv run --with playwright` when the
  project allows it), it takes headless screenshots at phone and desktop widths, light and dark,
  and walks the main path; it shows the built screen beside its prototype screen.
- Without one, it reviews the code.
- Writes `docs/design/ux-review-YYYY-MM-DD.html` with findings (severity, where, why, fix) and
  offers Slate tickets.

### 3.7 `/plumb:update`

Changes or adds tokens or components, adds a platform later ("web only, now add iOS and
Android": generates the themes, references and starters), or improves a part (e.g. motion).
Regenerates every output and prototype token block, records the decision, runs the audit and shows
the diff.

**Improving the system from the audit.** `/plumb:update` reads the latest audit's system-level
suggestions (missing or mergeable tokens, component specs that need a variant, `ux.md` or
`design.md` rules that real screens keep breaking for a good reason), proposes them one at a time
with options and a recommendation, and applies what the user approves: tokens and specs updated,
themes regenerated, prototypes refreshed, the decision recorded, and the audit re-run.

### 3.8 `/plumb:upgrade`

The Slate model:

1. Compare the `PLUMB.md` version line with the plugin's version.
2. Show "What's new" for every version in between (`upgrades/<v>.md`).
3. Replace the plugin-owned files (§5.1 `[P]`), regenerate `[G]` files.
4. Migrate the tokens JSON additively (`build-tokens.py --migrate`); never delete a value.
5. Run each version's upgrade steps in order, asking before each.
6. Update `PLUMB.md` (version line, new settings, "Plumb updates" log).
7. Run `status` until healthy, then show the diff.

The session-start hook nudges ("run /plumb:upgrade") when `PLUMB.md` is older than the plugin.
Upgrade never runs on its own.

### 3.9 `/plumb:status`

Plugin and project versions, platforms, home or linked repo, stale generated files
(`build-tokens.py --check`), audit error and warning counts, hooks on/off, prototypes and their
freshness.

### 3.10 `/plumb:feedback`

A local log of **Plumb's own mistakes**, for Plumb's developers (owner decision, 2026-10-13). Scripts give
evidence, not answers, so the agent corrects them; each correction is also a bug report for Plumb, and this command
keeps it.

- **Scope: Plumb mistakes only.** The test: *would fixing this mean changing Plumb, not the project?* In: a script's
  wrong or incomplete result the agent corrected; a hook's wrong refusal, missed refusal, crash or timeout that failed
  open, or confusing message; a skill step that was unclear, wrong or missing; a template or doc that disagrees with
  the code; a per-CLI quirk. Out: the project's design issues (→ `/plumb:audit`), decisions (→ the decision log), the
  project's own bugs, and its source code (a record holds only paths, `file:line`, the repo's shape and short exact
  text; never a secret). Examples: `detect.py` proposing `src/**` for a UI in `frontend/src/` is feedback; a
  hard-coded `#123456` in a page is an audit finding.
- **Where:** `~/.plumb/feedback/` (`%USERPROFILE%\.plumb\feedback\` on Windows), plain Markdown, outside every
  project, never written into one. One file per finding, `YYYY-MM-DD-<script>-<category>-<project>.md` (a `-2`, `-3`
  suffix when taken); `hooks.md` for the hooks' own failures (§8); `handled.md`, the index of groups marked handled.
- **One skill, model-invocable** (`skills/feedback/SKILL.md`, the single teacher and collector). Its description says
  when to use it: "Record a mistake in Plumb itself: a Plumb script, hook, skill, template or doc that gave a wrong,
  incomplete or confusing result you had to correct. Not for the project's own design issues — those are audit
  findings." Its first lines: "Plumb mistakes only", the test, where non-Plumb things go, the two examples.
- **Log mode** (the agent loads it after correcting a Plumb result, or the user types `/plumb:feedback log …`): one
  record with the fields When (date, Plumb version, CLI, OS) · Project shape · Where it failed (file → function, rule
  or step) · Command (exact, with cwd) · Given (exact output) · Expected · Evidence (`file:line`, match counts) · Repro
  (minimal repo shape) · Category (missed structure | wrong guess | false positive | missed problem | crash | timeout
  | confusing message | skill gap | docs mismatch | CLI quirk; `timeout` added in review, for the hooks' log) · Suggested fix in Plumb · Handled here; a crash adds the exit code
  and the traceback's last lines, a hook mistake its event, tool, path, exit code and message. Written with the
  agent's normal file-write tool: the CLI's permission mode governs; Plumb adds no question. Then one line to the user
  and back to the task.
- **Report mode** (the user types `/plumb:feedback`): read every record (all projects) and `hooks.md`; group by
  script · function · category with counts and projects, most frequent first, given vs expected; then one question at
  a time: show a group in full · draft a GitHub issue for Plumb (text only, projects only by shape, never sent) · mark
  a group handled (`handled in <version>` in `handled.md`; records are never deleted) · filter by project, script or
  date.
- **Pointers only; the format lives in the skill.** Every Plumb skill, next to "Scripts give evidence, not answers":
  "When a Plumb script or hook is wrong and you correct it, record the Plumb mistake with /plumb:feedback."; the
  `AGENTS.md`/`CLAUDE.md` row ends "· Plumb's own mistakes → /plumb:feedback"; `PLUMB.md` says "Plumb's own mistakes
  (a script, hook or skill got it wrong): /plumb:feedback. The project's design issues: /plumb:audit."; session start
  adds one short line, "Plumb mistakes (a Plumb script, hook or skill got it wrong) → /plumb:feedback" (it covers a
  project that declined the `AGENTS.md` offer); Kiro installs the skill as `/plumb-feedback`. Every pointer says
  "Plumb mistakes" or "Plumb's own mistakes" (a docs test enforces it).
- **Developer flow:** a group → a minimal repro → a failing test in the Plumb repo → the fix → a patch release → mark
  the group handled. Nothing leaves the machine.

## 4. Placement

Init never assumes the folder it was opened in is the project.

| Situation | Detected by | What init does |
|---|---|---|
| Opened at a parent folder (e.g. `~/Desktop`) | cwd not inside a git repo; child folders are | Lists the projects under it and asks which. Writes nothing in the parent. |
| Opened in a subfolder | `git rev-parse --show-toplevel` is higher | Uses the repo root. |
| Monorepo | `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json`, `package.json` workspaces, `apps/*` + `packages/*`, `frontend/` + `backend/` side by side | Skill + `PLUMB.md` at the **repo root**; each UI package listed in `PLUMB.md` with its stack and generated-copy path. |
| Separate frontend repo | UI dependencies (next, react, vue, svelte, angular, tailwind), Xcode project, Compose | Skill + `PLUMB.md` in this repo. |
| Backend-only repo | Python/Go/Java/… markers, no UI | Asks: (a) the frontend is in another repo (give the path; set up there), (b) the frontend will live here (create here), (c) design only for now (create here, platforms later). |
| Several UI repos share one system | Named at init | One **home** repo owns the system. Other repos get only `PLUMB.md` with `Design system: <path to the home skill>` and the AGENTS/CLAUDE row pointing there; agents read it there. The home's `build-tokens.py` can write generated copies into those repos (paths in its tokens JSON). |

**Detection is a first guess, never the decision.** `detect.py` only looks for well-known marker
files and folders, and no script can know every layout. The init skill must not rely on it alone:
it reads the result, and when the result is uncertain, empty or odd it looks through the folders
itself; it then always shows the user what it found and asks them to confirm or correct it. What
the user confirms is what gets written, and it is recorded in `PLUMB.md` so later commands never
guess again.

Before writing, init shows what it found and what it will create, and waits for confirmation:

```
Plumb found:
  project    ~/Projects/caredesk          (git root; you opened ~/Projects/caredesk/apps/web)
  layout     monorepo (pnpm workspaces)
  UI         apps/web   Next.js · Tailwind v4 · shadcn   (142 .tsx files → extract)
  no UI      apps/api   FastAPI
I'll create:
  .claude/skills/caredesk-design-system/   at the repo root
  PLUMB.md                                 at the repo root
  generated copy → apps/web/app/globals.css
OK, or change something?
```

**Moving it later.** If the design system ends up in the wrong place, or the user later wants it
elsewhere, `scaffold.py --relocate FROM TO` moves the skill and updates every reference in one step
(`PLUMB.md`, the `AGENTS.md`/`CLAUDE.md` row, Makefile targets), then runs the generator check.
`/plumb:status` runs `scaffold.py --verify` and offers the move when `PLUMB.md` and the actual
location disagree; init uses the same step when the user changes their placement answer. Files are
never moved by hand, so no reference is left pointing at the old place.

The default skill location is `.claude/skills/<project>-design-system/`; both tools read it
(Copilot CLI loads skills from `.claude/skills`, `.github/skills`, `~/.copilot/skills` and
`~/.agents/skills`). `.github/skills/` and `~/.claude/skills/` are offered as alternatives. If a
session opened inside a monorepo package does not load root skills (verified during the build),
init adds a one-line pointer to that package's `AGENTS.md`/`CLAUDE.md`, asked first.

## 5. The generated design system

### 5.1 Tree and ownership

`[P]` plugin-owned (upgrade replaces) · `[G]` generated from the tokens (never hand-edited; the
guard hook blocks it) · `[Y]` yours (written at create from your answers; changed through
`/plumb:update`) · `[A]` written by the agent in your framework (must pass the audit)

```
<project>-design-system/
├── SKILL.md                            [Y] when to use · files table · workflow · hard rules · done checklist
├── design.md                           [Y] the look in words; wins every disagreement; revision notes
├── assets/
│   ├── tokens/<project>.tokens.json    [Y] the ONE source (W3C DTCG)
│   ├── icons/icon-map.json             [Y] concept → lucide / SF Symbol / Material Symbol
│   └── platforms/
│       ├── README.md                   [P] what is generated, how to regenerate
│       ├── web/tokens.css.template     [Y] CSS structure for the project's styling mode
│       ├── web/tokens.css              [G] (+ an exact copy at the app's path, e.g. app/globals.css)
│       ├── web/tailwind.tokens.js      [G] Tailwind v3 only
│       ├── mobile/ios/<Project>Theme.swift        [G]
│       ├── mobile/android/<Project>Theme.kt       [G]
│       └── */starter/                  [A] only while no app exists yet
├── references/
│   ├── components.md                   [Y] framework-neutral spec per component: purpose, anatomy, sizes, states, tokens, a11y
│   ├── inventory.md                    [Y] which component exists where, on which platform; what is still to build
│   ├── ux.md                           [Y] users, key tasks and flows, navigation, page anatomy, forms, states, feedback, onboarding, voice
│   ├── accessibility.md                [Y] WCAG 2.2 AA checklist for every platform
│   ├── motion.md · vocabulary.md       [Y]
│   ├── dark-mode.md                    [Y] + a [G] block: the computed contrast table for every colour pair
│   ├── fidelity.md                     [Y] only when a prototype or brand guide existed before Plumb
│   ├── web/  stack.md · components.md · ux-guidelines.md · dark-mode.md     [Y] per chosen platform
│   └── mobile/  README.md · components.md · ios/ · android/                  [Y]
└── scripts/
    ├── build-tokens.py                 [P] write every theme · --check · --migrate · --contrast · --css-vars · --overrides
    ├── audit.py                        [P] full audit · --quick · --changed · --json · --html
    ├── build-prototype.py              [P] screens/*.html → prototype.html + screens.html + screens.json · --check
    └── _plumb.py                       [P] shared: token loading, colour maths, contrast, the inventory scanner
docs/design/
├── specimen.html                       [G] every token and component, light and dark (fixed template)
├── decisions.md                        [Y] the design decision log (every direction, variant and screen chosen)
├── directions.html                     the create directions (kept as the record)
├── prototype.html                      [G] the main prototype: the whole product, clickable
├── screens.html                        [G] every screen × every state, control states, navigation
├── prototype/screens/<id>.html         [Y] one source per screen (states + interactions)
├── prototype/screens.json              [G] screen → route, source files, states, sync status
├── prototype/tours/<flow>.json         [Y] walkthrough scripts (guide mode + play mode)
├── tours/<tour>.html                   [G] one shareable file per tour, in its view (app, default, or prototype)
├── prototype/proposals/<name>/         variants from /plumb:prototype (both views) + index.html
└── audit-*.html · ux-review-*.html · extract.html
```

`upgrade` may replace `[P]` and regenerate `[G]` files freely; it changes `[Y]` files only through
an upgrade step that asks first; it never touches `[A]` files.

### 5.2 Tokens format

W3C Design Tokens (DTCG). Light values in `$value`; dark values and breakpoint values in
`$extensions.plumb` (`dark`, `md`). Groups: `color`, `label`, `font`, `typography`, `radius`,
`spacing`, `size`, `border`, `shadow`, `motion` (`duration`, `easing`, `distance`, `scale`),
`effect`. References use `{group.token}`.

Machine settings live at the root, so the skill is self-contained and a linked repo can read it:

```json
{
  "$extensions": {
    "plumb": {
      "schema": 1,
      "project": "caredesk",
      "platforms": ["web"],
      "web": { "styling": "tailwind-v4", "copies": ["app/globals.css"] },
      "contrast": { "extra_pairs": [["on-primary-fill", "primary-fill", "text"]] }
    }
  },
  "color": {
    "$type": "color",
    "primary": { "$value": "#1f7a8c", "$description": "Accent: focus ring, active, primary",
                 "$extensions": { "plumb": { "dark": "#4fb3c4" } } }
  }
}
```

`schema` changes only with a migration in `build-tokens.py --migrate`, which only adds.

### 5.3 Components in the project's framework

The only fixed visual templates Plumb ships are `specimen.html`, the audit/UX report pages and
the prototype shell (navigation, toggles, state switcher) that `build-prototype.py` wraps around
the screen files.
Starter components (button, input, select, checkbox, card, chip/badge, dialog, sheet, menu, tabs,
toast, tooltip, empty state, error state, skeleton, page header, app shell) and any in-app design
page (e.g. a dev-only `/dev/design` route) are **written by the agent** (Claude or Copilot) in the
project's own framework, from `references/components.md`, and must pass `audit.py`.

- **The app exists:** they are written into it (e.g. `components/ui/`), using the framework's
  accessible primitives (shadcn/Radix on React, the native controls on SwiftUI and Compose, the
  framework's equivalent elsewhere); `inventory.md` points at them.
- **No app yet:** they go in `assets/platforms/<platform>/starter/` as ready-to-copy references.

## 6. Engine

Four standard-library Python 3.9 files, copied into each project's skill `scripts/`. The
project's copy is what explicit commands run (Make, CI, the skills), and `upgrade` keeps it in step
with the plugin. **The hooks never run a project's copy:** they run the plugin's own installed
scripts, so a cloned repository cannot get code executed just by containing a `PLUMB.md`; when the
project's copy is a different version, the hook says "run /plumb:upgrade" (trust boundary
documented in `SECURITY.md`). The plugin repo keeps the
masters in `plugins/plumb/assets/skill/scripts/`.

### 6.1 `build-tokens.py`

- Reads the tokens JSON and the web template; writes every platform output, the generated copies,
  and the contrast block in `dark-mode.md`. Output is deterministic (sorted, `\n`, UTF-8) and
  starts with a "GENERATED, do not edit" header naming the source and the command.
- Web modes: **tailwind-v4** (`@theme` + utilities + reduced-motion block), **tailwind-v3**
  (`tailwind.tokens.js` + CSS variables), **css** (custom properties). iOS: SwiftUI colours
  (light/dark), type, radii, spacing, motion, icons. Android: Compose Material 3 colour schemes,
  type, shapes, motion.
- `--check` exits 1 when any output, copy or prototype token block is stale. `--migrate` upgrades
  the tokens schema additively (and records the `theme_switch` / `motion.reduced` defaults the build
  applies when they are missing). `--contrast` rewrites only the contrast block. `--css-vars` prints
  the plain-CSS export used by prototypes and the specimen. `--overrides` prints, as JSON, a web
  copy's own variables in the tokens' namespaces with the token each maps onto and the exact edits;
  `--overrides --apply` makes them, only after the user's OK.
- **Contrast** is computed with WCAG 2.2 relative luminance, in light and dark: every `on-X` over
  `X`, every text token over every surface, plus `extra_pairs`. Thresholds: 4.5:1 text, 3:1 large
  text and UI boundaries. Failures are listed with the nearest passing value.
- Exit codes: 0 ok, 1 stale (`--check`), 2 bad input with `error: <token>: …` and `fix: …`.

### 6.2 `audit.py`

One rule table: id, severity (**error** blocks the hooks and fails the audit; **warn** is
reported only), platforms, check, and a token-aware fix (`#14857F` → `bg-primary`, `15px` →
`text-sm`).

| Kind | Rules |
|---|---|
| Per file (hooks + full) | raw colour · arbitrary design value · Tailwind default palette colour · off-scale type, radius, spacing · off-token duration or easing · `outline-none` · design properties in inline styles · second icon library · emoji in UI · `dark:` outside primitives · hand-rolled accessibility primitive · primitive restyled from outside · **Swift:** `Color(red:…)`, hex initialisers, `.font(.system(size:))`, literal `cornerRadius` · **Kotlin:** `Color(0xFF…)`, literal `sp`/`dp` for type and radius outside the theme |
| Cross file (full only) | near-duplicate colours and sizes · several components doing one job · contrast failures (light and dark) · missing dark values · inconsistent focus states · hover-only actions · touch targets under 44 px / 44 pt / 48 dp · no reduced-motion handling · generated files or prototype token blocks drifted · **prototype fidelity:** a screen in `screens.json` with no route, a route with no screen, a screen's source changed after its screen file, components/states/copy that differ from the screen file |

- **Always allowed:** arbitrary values for layout geometry (width, height, top/left, grid
  templates); paths on `PLUMB.md`'s allow list (e.g. `components/ui/**`, where primitives live).
  Exceptions are by path only, never by a comment in the line.
- **Files:** `.tsx .jsx .ts .js .vue .svelte .astro .html .css .scss` (web), `.swift`, `.kt`;
  never `node_modules`, build output or generated files.
- **Modes:** full (default: terminal summary, `--html` report, exit code) · `--quick FILE
  --before -` (one file, only errors the edit adds, JSON out; used by the edit check) ·
  `--changed SNAPSHOT` (files changed since a session snapshot; used by the end-of-turn check) ·
  `--json` · **inconsistency-only** (no tokens yet: infers the de-facto scales, flags outliers and
  near-duplicates; this is how prototypes and pre-Plumb code are audited).
- `extract`'s inventory uses the same scanner as inconsistency-only mode (in `_plumb.py`).
- Exit codes: 0 no errors, 1 errors found, 2 nothing checked or bad input (with `fix:`).

**Suggestions (improvements, not violations).** A third severity, `suggest`, never affects the
exit code. It says what could be better, with a reason and a concrete fix: a missing token (the
same raw value used 3+ times), unused or near-duplicate tokens in the system itself, components to
consolidate into a variant, contrast headroom (a pair that only just passes, in light or dark, with
a nearby value that passes comfortably), inconsistent spacing or radius for the same element, a
screen missing a state that `ux.md` asks for, dark-mode polish (an elevation or boundary barely
visible in dark), and accessibility beyond the minimum (icon-only controls without labels, weak
focus rings). The HTML report shows them in an **Improvements** section after the issues, ranked by
impact; each can become a Slate ticket, and `/plumb:update` can apply token suggestions with the
user's OK.

### 6.3 `build-prototype.py`

Assembles the main prototype from the screen files: `prototype.html` (an app shell with
navigation, hash routing between screens, a state switcher, phone/desktop and light/dark toggles,
each screen's own interactions, the per-screen decisions panel plus a Decisions page from
`docs/design/decisions.md`, the per-screen guide panel, and the walkthrough player for every file
in `tours/`), `app.html` (the app view of §3.4.2: every screen full window, hash routes `#/ID` and
`#/ID/STATE`, the same screen-script API, no panels, from `templates/app-shell.html.tmpl`),
`tours/<id>.html` per tour file (in the tour's `view`: the app shell with the player on top, the
default, or the prototype shell; §3.4.1) and
`screens.html` (sidebar navigation, every screen × every `data-state`, and the control-state sheet
generated from the tokens and components). The two shells take the `--pl-*` roles of Plumb's own
chrome from one shared template, `templates/chrome-roles.css`. It inlines `build-tokens.py --css-vars`, a small
dependency-free runtime, and each screen's scripts, so every page is a single file that opens from
disk. In `screens.html` each screen's markup, styles and scripts are in the page once (one
`<template>` each), shared by its light and dark copies in every state; the page builds each copy's
iframe from them and hides every outer state block but the copy's, and the token block is there
once, so the page grows with the screens, not screens × states × 2. Any page it writes (the main
pages, the tour pages, the proposal pages) over 10 MB prints one `warning: <page> is <N> MB, …`
line naming every such page (also on `--check`, exit code unchanged), a note naming the heaviest
screen files, and what helps: smaller screen files (every page holds each one once: inline `data:`
images and large SVG moved into image files, very long sample content cut), or git-ignoring the
pages with the build run in CI instead of `--check` (a git-ignored page is missing on a fresh
clone). Splitting a screen into several files does not help, since every page still holds all of
them.

It is the **only writer of `screens.json`** (as Slate's `board.py` is of `tickets.json`): skills
change it through commands, never by editing it. `--map <id> --route=<route> --files <globs>`
sets a screen's route and source files (confirmed with you); `--approve <id>` records your
approval (git `user.name`, date, hash of the screen file and of its folder's `_shared/` files, whose own
hashes are kept so a stale approval names the shared file that changed); `--synced <id>` marks a screen updated
from already-built code. `--check` exits 1 when a page (`app.html` included) is stale or missing,
the token blocks are stale, or a
walkthrough step names a screen, state or element that does not exist. Same exit-code and error conventions as §6.1.
`--check-tour <file>` checks one tour file the same way, writes nothing, and warns about a step element the screen's
CSS hides below or above a frame breakpoint (§3.4.1, "Tour checks"); the browser pass is the plugin's `check-tour.py`.

`--proposal <name>` builds `/plumb:prototype`'s variants instead of the main prototype: from each
`docs/design/prototype/proposals/<name>/<variant>/screens/*.html` (and an optional `idea.md` with the variant's idea and
trade-offs) it writes that variant's `prototype.html`, `app.html` and `screens.html` (light and dark, the token block
inlined) and `proposals/<name>/index.html` with the variants side by side, each linking prototype.html to review and
app.html to demo. The pages are generated (never edited) and
byte-stable; `--check --proposal <name>` exits 1 when one is stale; `screens.json` is not touched. A variant or
proposal folder that leads outside the proposals folder is refused. When tokens change, the main build and
`build-tokens.py` refresh the token block of every generated proposal page, so old variants keep rendering. With
`--proposal` (and `--check`) every change id a variant's screens use must be listed in `proposals/<name>/changes.md`
(exit 2 naming the screen file and the id; a listed id no screen uses is a warning; §3.4 "Change ids"); shared files
(§3.4 "Shared files") are read from each variant's `screens/_shared/` and inlined into that variant's pages only.

## 7. UX layer

`references/ux.md` is written at create (from the product interview and the UX decisions) and at
extract (from the existing screens, confirmed with you). It holds: who the users are and their
context; the key tasks and flows; the navigation model; page anatomy and templates; forms
(labels, validation, errors in words); every state (loading, empty, error, success, disabled,
long text, zero, offline); feedback and confirmation; destructive actions; onboarding and first
run; voice and microcopy (linked to `vocabulary.md`). Per-platform guidelines go in
`references/web/ux-guidelines.md` and `references/mobile/`.

UX is checked while building, not only after:

1. **Before:** the skill's workflow makes agents read `ux.md` and the screen's prototype file
   before building it.
2. **During:** the done checklist requires every state the prototype and `ux.md` name (loading,
   empty, error, success, long text, …), words from `vocabulary.md`, and the keyboard path.
3. **End of turn:** the check compares the built screen's components, states and copy with its
   prototype file (prototype fidelity, §6.2).
4. **After:** `/plumb:ux` (§3.6) reviews the screen against `ux.md`, the prototype and usability
   heuristics, with screenshots when a browser is available.

## 7a. Light and dark, everywhere

Every design system Plumb makes works in **both themes** by default; a light-only project is an
explicit decision recorded in the decision log and in `PLUMB.md` (`Themes: light-only`), which
turns the dark rules off.

- **Tokens:** every colour token has a dark value (`$extensions.plumb.dark`); a missing one is an
  audit **error**, unless the token is marked `"same-in-dark": true` (a deliberate constant).
- **Contrast:** every pair is computed in light and dark; the evidence table in `dark-mode.md`
  shows both.
- **Components:** built only from tokens, so they switch automatically; pages never write `dark:`
  overrides; raw colours are errors because they don't switch.
- **create / extract:** dark mode is part of the interview's design decisions by default;
  directions show each direction in light and dark.
- **Prototype:** `prototype.html` and every variant have a light/dark toggle; `screens.html`
  shows every screen in every state in **both themes side by side**; tours play in either theme.
- **Specimen, audit fidelity, `/plumb:ux`:** both themes (screenshots and checks in light and
  dark when a browser is available).
- **Tests:** browser checks render every generated page in light and dark.

## 8. Hooks

Three scripts behind Slate's launchers: `run.sh` (python3 / python / py -3, 3.9+), `run.cmd` and
a `powershell` command on every hook for Windows Copilot. All three apply in **both tools**.
In Kiro (§12b) the same scripts run with `--kiro`; on Windows each Kiro hook starts through PowerShell
(`powershell -NoProfile -NonInteractive -EncodedCommand …`, the same fail-open body as the
Copilot hooks), which adds about 0.3 s per hook.

| Script | Event · matcher | Job |
|---|---|---|
| `session_start.py` | SessionStart | One status line (`Plumb: caredesk-design-system 1.0.0 · tokens up to date · 3 audit issues · read the skill before UI changes`); "run /plumb:upgrade" when `PLUMB.md` is older than the plugin; a warning when a linked design system path is missing. Copilot: `{"additionalContext"}`. Takes the session snapshot (hash of every UI file already changed or untracked). Silent in projects without `PLUMB.md`. |
| `pre_edit.py` | PreToolUse · `Edit\|Write\|MultiEdit\|Bash\|PowerShell` | **Prototype first:** refuses creating a new page or route file that has no approved screen in `screens.json` (when prototype sync is on). **Guard:** refuses hand edits to generated files (themes, copies, `specimen.html`, `prototype.html`, `screens.html`, `screens.json`, `tours/*.html`) and to Plumb's own files: the `[P]` files in the project's design-system skill (`scripts/*.py`, `templates/*`) and the plugin's helpers and hooks ("this is Plumb's file; upgrades replace it: use `/plumb:update` for design changes, or propose the improvement to the Plumb repo"); only in projects with a `PLUMB.md`, so developing Plumb itself is never blocked; including shell writes, read for their real write targets (a redirect, `tee`, `sed -i`, the destination of `cp` / `mv`, `rm`, inline code's `open("…", "w")`, …; a read-only program's words, a here-document written to another file the same command does not run, and inline code that only reads or imports a guarded file are allowed); the earlier, stricter reading (`hooks/_shell_legacy.py`) decides, and its refusal becomes an allow only when the new reading proves a data text written to a file the command never runs, imports or uses again (and no program picks up by itself), a read-only program's words, inline code that only reads its guarded literals, or a `git commit` message; every other word must name no guarded path, even one not built yet; a command too long or too deeply nested to read, or one the reader fails on, is refused when it names a guarded path; running `build-tokens.py` is allowed. **Edit check** (when on): computes the file before and after the edit, runs `audit.py --quick`, refuses only errors the edit adds. |
| `stop_check.py` | Stop | **End-of-turn check** (when on): if no UI file changed since the snapshot, silent. Otherwise `audit.py --changed`, which includes **prototype sync** (a screen whose source files changed this session while its `screens/<id>.html` did not); new errors block the stop once with the list and fixes (`{"decision": "block", "reason": …}`); with `stop_hook_active` set it only reports, so it cannot loop. A clean run prints one line. |

**Copilot CLI differences** (pinned by `tests/test_copilot.py`): edits arrive as apply_patch text
(the `*** Update/Add File` sections are applied to the current file to get the "after"; if that
fails, only added lines are checked); camelCase `toolName`/`toolArgs` input; no
`permission_mode`; `tool_result` instead of `tool_response`; exit-2 stderr is hidden, so with
`COPILOT_CLI` set a refusal is `{"permissionDecision": "deny", …}` on stdout (flat and in
`hookSpecificOutput`) with exit 0; session start returns `{"additionalContext": …}`. A plugin's
`Stop` hook reaches Copilot's `agentStop` and makes it continue (live run, 2026-10-12): the block
arrives as a new prompt, so it can override an earlier "don't fix now"; the skills say to report
and stop then. Copilot ignores a skill's `allowed-tools`, so every script run asks: the skills run
a checkpoint's scripts in one shell call, keep temporary files in `<root>/.plumb-tmp/` (ignored
through its own `.gitignore`, removed at the end of setup or of the command) instead of the OS
temp folder, and pass routes as
`--route=<route>` (a bare `/` reads as a path). Copilot's skill tool lists only skills the model
may start, so the user-only skills say they are already loaded (else Copilot prints a harmless
`Skill not found`). Even batched, a full init with create or extract asks for about 10–15
script runs plus one per file the agent writes; Copilot has no setting that pre-allows only
Plumb's scripts (`--allow-tool 'shell(python3)'` allows every `python3` command, `--add-dir`
removes the plugin folder's path prompts): the user's choice, documented in `copilot.md`.

**Safety:** hooks fail open (no Python, no `PLUMB.md`, a missing or broken `audit.py`, unreadable
input → exit 0 with at most one stderr line); non-UI edits exit in about 50 ms and UI edits stay
under 1 s (a test measures it); at most 10 issues per refusal, each `error: line N: …` + `fix: …`;
snapshots go in the OS temp folder keyed by project and session, never in the repo; switches are
read from `PLUMB.md` on every run. **The hook log** (§3.10): a hook that fails open (a crash, a plugin script it
cannot load, a session-start script that times out or crashes) also appends one line to
`~/.plumb/feedback/hooks.md`, in Given / Expected form with the hook, Plumb version, CLI, OS, project folder name,
event, tool, project-relative path and exit code; only in a project with a `PLUMB.md`, the same line once a day (a
timeout once per project and Plumb version), at most 512 KB in all. Given and Expected are redacted (`redact`: quoted
literals over three characters → `'<redacted>'`, absolute paths outside the project → their base name, token-like
strings and key=value secrets → `<redacted>`). It is private like the snapshot folder: `~/.plumb` and `feedback/`
created 0700 (the user's own wider folders are tightened to 0700 through an `O_NOFOLLOW` handle, by the hooks and at
every session start; none is created there), `hooks.md` 0600 and created with its header already in it (a temporary
file hard-linked into place), nothing written when either folder is a symlink (or reparse point) or someone else's,
or when `hooks.md` is a symlink; a `PlumbError` (the project's own broken files) is not logged; the log never fails or
blocks a hook and never prints. Session start's last line is the pointer to `/plumb:feedback`. The setup marker `<root>/.plumb-tmp/setup-in-progress` is an
unprotected soft switch: anything that can write in the project can create it, and it turns off
only the end-of-turn check (never the edit check or the guards), for at most 6 hours from its
modification time; after that it is stale and session start says so.

## 9. `PLUMB.md`

Written by init from `templates/PLUMB.md`; read by every skill and by the hooks (simple
`Key: value` lines); updated by update and upgrade. Safe to edit.

```markdown
<!-- plumb v1.0.0 · written by /plumb:init, safe to edit values -->
# Plumb: the design system for CareDesk Lite

Design system: `.claude/skills/caredesk-design-system/`
Role: home                          (home = this repo owns the tokens; linked = uses another repo's)
Platforms: web
UI packages: . (Next.js · Tailwind v4 · shadcn)
Python: `python3`
No downloads: nothing is installed or downloaded; if something is missing, ask the user and wait for their decision.
Plumb's own mistakes (a script, hook or skill got it wrong): /plumb:feedback. The project's design issues: /plumb:audit.

## Checks
Edit check: on
End-of-turn check: on
Themes: light-and-dark          (light-and-dark | light-only: an explicit decision)
UI files: app/**, components/** · *.tsx *.jsx *.css
Allowed raw values: components/ui/**

## Commands
tokens `python3 .claude/skills/caredesk-design-system/scripts/build-tokens.py` (make tokens)
check `… build-tokens.py --check` (make tokens-check) · audit `… audit.py` (make design-audit)

## Prototype
Main: docs/design/prototype.html · app: docs/design/app.html · screens: docs/design/screens.html · map: docs/design/prototype/screens.json
Prototype sync: on               (end-of-turn check stops once when a built screen changed without its prototype)

## Plumb updates
- 2026-10-11 created with Plumb 1.0.0 (web; direction "Calm clinic")
```

A linked repo's `PLUMB.md` has `Role: linked` and `Design system: ../caredesk-web/.claude/skills/caredesk-design-system/`.

## 10. What a project gets besides the skill

Each asked first, never silent:

- a row in `AGENTS.md`/`CLAUDE.md` "read before you work": *before any UI change, read
  `<skill>/SKILL.md`; UI work is prototype first: update or create the screen with
  `/plumb:prototype`, get the user's approval, then build it to match. Don't install or download
  anything; if something is missing, ask the user and wait for their decision; never decide on
  their behalf · Plumb's own mistakes → /plumb:feedback*;
- `Makefile` targets `tokens`, `tokens-check`, `design-audit` (plain `python` commands in
  `PLUMB.md` for machines without make);
- the generated copy at the app's path (e.g. `app/globals.css`);
- `docs/design/` (specimen, directions, prototypes, reports);
- the decision log `docs/design/decisions.md`, mirrored into `docs/decisions.md` when it exists;
- both checks, with the choice recorded in `PLUMB.md`.

## 11. Working with Slate and Effective HTML

- **Slate** (when `kanban/board.py` exists, each asked): `make design-audit` is added to
  `SLATE.md`'s review checks; audit and UX findings can become tickets (grouped by area, written
  only through `board.py`); a ticket that adds or changes a screen starts with "prototype approved" as its first step and
  links the screen in the main prototype in "done when". Plumb never edits `kanban/`; Slate never edits the design system.
- **Effective HTML** (`html`, `design-artifact`, `html-prototype`, `html-diagram`): used for the
  directions page, prototype variants and the what-you-get page when installed; Plumb falls back
  to its own simple templates when not. `specimen.html`, the reports and the prototype shell are
  Plumb's fixed templates, designed once with the same principles.

## 12. Claude Code and Copilot CLI

Same `.claude-plugin/` manifest, skills and Claude-format `hooks.json`. Install in Copilot:
`copilot plugin marketplace add Zidane786/plumb`, `copilot plugin install plumb@plumb`, restart.
Commands are the same (`/plumb:init`, …). Skills resolve the plugin root from
`${CLAUDE_PLUGIN_ROOT}`, falling back to the skill's base directory. Windows needs Python
(`py -3`, `python` or `python3`). VS Code Copilot Chat is not supported.

## 12b. Kiro

Plumb also works in **Kiro** (IDE and CLI v3+), from the same files:

- **Skills:** Kiro follows the Agent Skills standard (`SKILL.md`). Kiro has no plugin marketplace,
  so `python3 <plumb>/scripts/kiro.py install [--project P]` copies Plumb's skills into
  `~/.kiro/skills/plumb-<name>/` (global, IDE) or `<project>/.kiro/skills/plumb-<name>/`
  (workspace, IDE and CLI), with `${CLAUDE_PLUGIN_ROOT}` replaced by the absolute plugin path;
  commands are `/plumb-init`, `/plumb-create`, …. `kiro.py uninstall` removes them.
- **Instructions:** Kiro loads `AGENTS.md` as steering, so Plumb's row applies; init can also write
  `.kiro/steering/plumb.md` (always included) pointing to the design-system skill, which stays in
  one place (no copy into `.kiro/skills/`).
- **Hooks:** `kiro.py install` writes `~/.kiro/hooks/plumb.json` (CLI) and, per project,
  `.kiro/hooks/plumb.json` (the IDE reads workspace hooks): `SessionStart` → `session_start.py`,
  `PreToolUse` (`write`, `shell`) → `pre_edit.py`, `Stop` → `stop_check.py`. A Kiro adapter in
  `_hooklib.py` reads `hook_event_name`, `tool_name`, `tool_input` (`fs_write`, `execute_bash`)
  and refuses with exit 2 + stderr; `Stop` blocks with `{"decision":"block","reason":…}`.
- **Verification:** built and CI-tested from Kiro's documented formats; the live Kiro run waits
  until Kiro can be installed on the test machine (which exit code blocks and the exact stdin
  fields are confirmed then).

## 12a. Dependencies and enterprise control

**Needed:** Python 3.9+ standard library (hooks, `build-tokens.py`, `audit.py`,
`build-prototype.py`), and Claude Code or Copilot CLI. git is optional (repo root, "decided by",
session snapshots); without it Plumb still works with fewer details.

**Never:** npm, npx or pip installs; downloads or network calls at run time. Generated pages
(prototype, screens, tours, specimen, reports, directions) load nothing from the network: no CDN,
no hosted web fonts. A project font is embedded from the project's own font files; otherwise a
system font stack is used. Every page opens offline from disk.

**Nothing is installed or downloaded.** A rule in every Plumb skill: never install or download
anything (no package, image, tool or file from the network); build components with what the
project already has. If a component really seems to need a new package, the agent says so
(`ask the user: …`) and waits for the user's decision, never deciding on their behalf. There is
no setting for this; the rule is stated in the `AGENTS.md`/`CLAUDE.md` row Plumb adds (§10) and in
one line of `PLUMB.md`, so every agent working in the project sees it. Enforcing it is outside
Plumb (a separate install guard can do that).

**Optional, each the organisation's choice:** Effective HTML skills (else Plumb's built-in rules
and templates), a browser tool (else audit and `/plumb:ux` review code instead of screenshots),
`make` (else the plain commands in `PLUMB.md`), Slate (else no tickets).

**No Playwright needed.** Most checks need no browser: `audit.py` reads code, CSS and prototype
HTML directly (token rules, computed contrast, prototype fidelity, drift, prototypes using only
the system's values). The visual extras (screenshot comparison in the audit and `/plumb:ux`) use
the first browser available, installing nothing: (a) the agent's own browser tool, if the
organisation allows one; (b) Chrome, Edge or Chromium already on the machine, run headless from
the standard library (`--headless --screenshot`, `--dump-dom`); (c) none: the visual part is
skipped and reported (`note: visual comparison skipped: no browser found` with a `fix:` line),
and every other check still runs. Playwright is used only in Plumb's own CI; locally, browser
tests skip with a reason when it is missing.

**Controlling the plugin:** one Git repo with no build step, so it can be mirrored or forked,
reviewed and installed from an internal copy; releases are tagged `vX.Y.Z` and can be pinned;
`/plumb:upgrade` never runs on its own. Test tools (pytest, Playwright) are used only by Plumb's
own CI.

## 13. The plugin repo

```
.claude-plugin/marketplace.json           marketplace "plumb" → plugins/plumb
plugins/plumb/
  .claude-plugin/plugin.json               version 1.0.0
  skills/{init,create,extract,prototype,tour,audit,ux,update,upgrade,status,feedback}/SKILL.md   lean
  reference/   interview.md · rules.md · tokens-format.md · placement.md · scripts.md ·
               prototypes.md · ux.md · copilot.md
  assets/skill/   the design-system template: SKILL.md, design.md and references/* skeletons;
                  scripts/{build-tokens.py, audit.py, build-prototype.py, _plumb.py};
                  web templates (v4, v3, css); specimen, report, prototype-shell and app-shell
                  templates
  hooks/       hooks.json · run.sh · run.cmd · session_start.py · pre_edit.py · stop_check.py
  templates/   PLUMB.md · the AGENTS/CLAUDE row · decision entry · Makefile snippet
  upgrades/    README.md · 1.0.0.md
  CHANGELOG.md · README.md
examples/caredesk/        the golden output of create on CareDesk Lite, with its input brief
tests/                    see §14
docs/specs · docs/plans · docs/what-you-get.html
docs/USAGE.md (the complete usage guide: start here; walkthroughs by situation; every command with an example session; the daily prototype-first loop; prototypes and tours; the design-system files and who owns them; hooks and their messages; team and enterprise use; troubleshooting and FAQ — linked from both READMEs) · TEST.md · README.md (like Slate's: what Plumb does, install in both tools, updating, a table
explaining what every command does and when to use it, how it flows, what a project gets, the
hooks, configuration, Slate and Effective HTML, releases) · AGENTS.md (+ CLAUDE.md) · SECURITY.md
.github/workflows/{test.yml, release.yml} · .github/dependabot.yml · scripts/
```

## 14. Testing and proof

- `test_build_tokens.py`: every platform and web mode, copies, `--check` drift, `--migrate`
  (additive, keeps every value), contrast maths against known pairs, every error path.
- `test_audit_rules.py`: per rule, one fixture that fails and one false-positive fixture that
  passes (e.g. layout geometry, allowed paths); modes `--quick`, `--changed`, inconsistency-only.
- `test_hooks.py`: guard (file and shell writes), prototype first (a new route without an
  approved screen), edit check (new-only), stop check (silent, block once, no loop, prototype
  sync), fail-open paths, timing budget.
- `test_bash_guard.py`: every shell write form refused on a Plumb file and a generated file (Claude Code and
  Copilot CLI payloads), and commands that only mention a guarded file allowed (a Makefile here-document,
  `json.load`, `importlib`, quoted `>`).
- `test_copilot.py`: apply_patch, camelCase input, deny JSON, additionalContext, `tool_result`,
  `powershell` on every hook.
- `test_placement.py`: every layout in §4 on fixture trees.
- `test_build_prototype.py`: assembling both pages from screen files, every state present in
  `screens.html`, the decisions panel, `--map` / `--approve` / `--synced`, `--check` drift, token
  blocks, walkthrough validation (missing screen, state or element).
- `test_example.py`: regenerating `examples/caredesk` reproduces the committed generated files
  (including its main prototype).
- `test_docs_consistency.py`, `test_portability.py`, `test_release_notes.py` (as in Slate).
- Headless browser checks for `specimen.html`, the report templates and the example prototypes.
- **Live runs in tmux, both CLIs:** `claude --plugin-dir plugins/plumb` and Copilot CLI with the
  plugin installed, driven through `TEST.md` (create → the hook blocks a raw hex → audit →
  prototype a new screen and choose it → change a built screen without its prototype and see the
  end-of-turn check stop → update adds iOS → upgrade from a fake older version), with pane
  captures as evidence. Headless browser checks of `prototype.html` (navigation, state switcher,
  toggles, interactions, guide mode, play mode at every speed, pause, jumping to a scene, the
  reduced-motion fallback) and `screens.html` (every state rendered).
- **What CI runs** (every PR that touches code; Ubuntu, macOS and Windows × Python 3.9 and 3.13,
  the six required checks): the whole pytest suite above. **The hooks are tested end to end
  there:** each hook script is run as the CLI would run it, through `run.sh` (and `run.cmd` on
  Windows), with real hook input in both Claude Code and Copilot CLI formats, on fixture projects,
  and the exit code, stdout JSON and stderr are asserted (refusals, passes, fail-open, timing).
  Browser checks of the generated pages (specimen, prototype, screens, walkthrough player) run
  in the same suite when Playwright is installed; CI installs it with Chromium on every runner (a
  test dependency, never a runtime one), and with `PLUMB_STRICT_SKIPS=1` any skip that is not a
  platform or tool skip (its reason starts with `requires macOS`, `requires Windows`,
  `requires POSIX` or `requires xcrun`)
  fails the run (`tests/conftest.py`); locally the browser tests skip with a reason when
  Playwright is missing. What CI cannot
  run: the two CLIs themselves (they need sign-in), so the live tmux runs below are done by hand
  before every release and recorded in the PR.
- **Three small sample apps:** a minimal Next.js + Tailwind v4 app, a minimal Angular app (plain
  CSS/SCSS) and a minimal SwiftUI app (its generated theme and views type-checked with `swiftc` on
  macOS), kept as source trees under `tests/fixtures/apps/`. Both CLIs run
  init, create or extract, prototype, tour, the hooks (edit check, prototype first, end-of-turn,
  guard) and audit on each, in tmux. If npm is reachable on the test machine, the apps are also
  run so the audit's screenshot comparison and `/plumb:ux` are exercised against the real pages;
  Plumb itself never needs npm.
- **Prototype checks in a browser** (headless script, or Playwright MCP where it helps): every
  screen and state renders, interactions and the walkthrough work, and the page uses only the
  design system's tokens (no colour, size or radius outside them).
- **Validate, then publish:** nothing is pushed for release until these runs pass in both tools.
- **Proof before the 1.0.0 PR:** create on CareDesk Lite, with the owner answering the interview
  and validating the directions, decisions, prototype and walkthrough as a real user would; only
  then is it committed as `examples/caredesk/`;
  extract on a temporary copy of the reference project, compared with its real system (accent
  `#14857F`; type scale `display, h1, h2, h3, body-lg, body-md, label-sm, sm, xs`); audit on that
  copy and on the two practice-week prototypes, with the HTML reports shown.

## 15. Errors and refusals

Every refusal is `error: <what>` then `fix: <exact command>` or `ask the user: <question>`, and
has a test. Scripts never raise tracebacks at users; bad input exits 2 with the token, file or
placeholder named.

## 16. Out of scope for 1.0.0

VS Code Copilot Chat; React Native and Flutter themes (React Native is a candidate for 1.1.0); shipped component templates for any
framework (components are agent-written from specs); a hosted or shared prototype server
(prototypes are local files; pixel-perfect visual diffing); importing from Figma.

## 17. Verified during the build (not assumed)

1. A plugin `Stop` hook in Copilot CLI: does it map to `agentStop`, and can it make the agent
   continue? Decides the Copilot end-of-turn behaviour in §8. (Live run 2026-10-12: yes, it
   continues.)
2. Do both tools load root `.claude/skills/` when a session opens inside a monorepo package?
   Decides the pointer row in §4.
3. Copilot's edit tool names for the PreToolUse matcher (Slate's matcher is the starting point).
