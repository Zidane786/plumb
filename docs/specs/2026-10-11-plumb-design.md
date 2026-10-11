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
| `/plumb:audit` | Any time | Full consistency report (HTML + terminal + exit code); offers Slate tickets. |
| `/plumb:ux` | After building a screen or flow | UX review against the project's UX rules and its prototype; HTML report; offers Slate tickets. |
| `/plumb:update` | The design changes | Change or add tokens and components, add a platform, improve a part; regenerate; record; audit. |
| `/plumb:upgrade` | The plugin has a new version | Brings the project's copied files, tokens format and `PLUMB.md` up to the plugin's version. |
| `/plumb:status` | Health | Version, platforms, stale files, audit counts, hooks on/off, linked repos. |

Every skill asks one question at a time through the question tool, with options and a
recommendation first, and never writes into a project without saying where. Skills that run a
heavy flow (create, extract, upgrade, update) only run when the user typed them; other skills may
*offer* them.

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
newer. It never overwrites an existing design system.

### 3.2 `/plumb:create`

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

**One source per screen.** Both pages are assembled from `docs/design/prototype/screens/<id>.html`
(one file per screen, its states marked with `data-state`, its interactions inline) by
`build-prototype.py` (§6.3), which also writes `docs/design/prototype/screens.json`: each
screen's id, title, states, its route and the source files that implement it. Editing one screen
file updates both pages, so they cannot disagree. The token block in every page comes from
`build-tokens.py --css-vars`, so prototypes are token-true, and `audit.py` must exit 0 on them.

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

**Effective HTML is the reference for every prototype.** Variants, screen files and the shell
follow the `html-prototype` and `design-artifact` skills when installed; when they are not,
`reference/prototypes.md` carries the rules Plumb needs from them (real content, every state,
working interactions, keyboard and focus, both themes, reduced motion, no generic look).

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
    ├── build-tokens.py                 [P] write every theme · --check · --migrate · --contrast · --css-vars
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
├── tours/<tour>.html                   [G] one shareable file per tour: the prototype + that tour
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
project's copy is what runs everywhere (Make, the hooks, CI, Windows), so the hook and the full
audit always apply the same rules, and `upgrade` updates them together. The plugin repo keeps the
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
  the tokens schema additively. `--contrast` rewrites only the contrast block. `--css-vars` prints
  the plain-CSS export used by prototypes and the specimen.
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

### 6.3 `build-prototype.py`

Assembles the main prototype from the screen files: `prototype.html` (an app shell with
navigation, hash routing between screens, a state switcher, phone/desktop and light/dark toggles,
each screen's own interactions, the per-screen decisions panel plus a Decisions page from
`docs/design/decisions.md`, the per-screen guide panel, and the walkthrough player for every file
in `tours/`) and `screens.html` (sidebar navigation, every screen × every
`data-state`, and the control-state sheet generated from the tokens and components). It inlines
`build-tokens.py --css-vars`, a small dependency-free runtime, and each screen's scripts, so both
pages are single files that open from disk.

It is the **only writer of `screens.json`** (as Slate's `board.py` is of `tickets.json`): skills
change it through commands, never by editing it. `--map <id> --route <route> --files <globs>`
sets a screen's route and source files (confirmed with you); `--approve <id>` records your
approval (git `user.name`, date, hash of the screen file); `--synced <id>` marks a screen updated
from already-built code. `--check` exits 1 when either page or the token blocks are stale, or a
walkthrough step names a screen, state or element that does not exist. Same exit-code and error conventions as §6.1.

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

## 8. Hooks

Three scripts behind Slate's launchers: `run.sh` (python3 / python / py -3, 3.9+), `run.cmd` and
a `powershell` command on every hook for Windows Copilot. All three apply in **both tools**.

| Script | Event · matcher | Job |
|---|---|---|
| `session_start.py` | SessionStart | One status line (`Plumb: caredesk-design-system 1.0.0 · tokens up to date · 3 audit issues · read the skill before UI changes`); "run /plumb:upgrade" when `PLUMB.md` is older than the plugin; a warning when a linked design system path is missing. Copilot: `{"additionalContext"}`. Takes the session snapshot (hash of every UI file already changed or untracked). Silent in projects without `PLUMB.md`. |
| `pre_edit.py` | PreToolUse · `Edit\|Write\|MultiEdit\|Bash\|PowerShell` | **Prototype first:** refuses creating a new page or route file that has no approved screen in `screens.json` (when prototype sync is on). **Guard:** refuses hand edits to generated files (themes, copies, `specimen.html`, `prototype.html`, `screens.html`, `screens.json`, `tours/*.html`), including shell writes (`sed -i`, `>`, `tee`, …, parsed as Slate parses them); running `build-tokens.py` is allowed. **Edit check** (when on): computes the file before and after the edit, runs `audit.py --quick`, refuses only errors the edit adds. |
| `stop_check.py` | Stop | **End-of-turn check** (when on): if no UI file changed since the snapshot, silent. Otherwise `audit.py --changed`, which includes **prototype sync** (a screen whose source files changed this session while its `screens/<id>.html` did not); new errors block the stop once with the list and fixes (`{"decision": "block", "reason": …}`); with `stop_hook_active` set it only reports, so it cannot loop. A clean run prints one line. |

**Copilot CLI differences** (pinned by `tests/test_copilot.py`): edits arrive as apply_patch text
(the `*** Update/Add File` sections are applied to the current file to get the "after"; if that
fails, only added lines are checked); camelCase `toolName`/`toolArgs` input; no
`permission_mode`; `tool_result` instead of `tool_response`; exit-2 stderr is hidden, so with
`COPILOT_CLI` set a refusal is `{"permissionDecision": "deny", …}` on stdout (flat and in
`hookSpecificOutput`) with exit 0; session start returns `{"additionalContext": …}`. Whether a
plugin's `Stop` hook reaches Copilot's `agentStop` and can make it continue is verified first in
the build; if not, Copilot shows the end-of-turn summary only and the edit check remains the hard
guard there, and the README says so.

**Safety:** hooks fail open (no Python, no `PLUMB.md`, a missing or broken `audit.py`, unreadable
input → exit 0 with at most one stderr line); non-UI edits exit in about 50 ms and UI edits stay
under 1 s (a test measures it); at most 10 issues per refusal, each `error: line N: …` + `fix: …`;
snapshots go in the OS temp folder keyed by project and session, never in the repo; switches are
read from `PLUMB.md` on every run.

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

## Checks
Edit check: on
End-of-turn check: on
New dependencies: ask              (ask | never)
UI files: app/**, components/** · *.tsx *.jsx *.css
Allowed raw values: components/ui/**

## Commands
tokens `python3 .claude/skills/caredesk-design-system/scripts/build-tokens.py` (make tokens)
check `… build-tokens.py --check` (make tokens-check) · audit `… audit.py` (make design-audit)

## Prototype
Main: docs/design/prototype.html · screens: docs/design/screens.html · map: docs/design/prototype/screens.json
Prototype sync: on               (end-of-turn check stops once when a built screen changed without its prototype)

## Plumb updates
- 2026-10-11 created with Plumb 1.0.0 (web; direction "Calm clinic")
```

A linked repo's `PLUMB.md` has `Role: linked` and `Design system: ../caredesk-web/.claude/skills/caredesk-design-system/`.

## 10. What a project gets besides the skill

Each asked first, never silent:

- a row in `AGENTS.md`/`CLAUDE.md` "read before you work": *before any UI change, read
  `<skill>/SKILL.md`; UI work is prototype first: update or create the screen with
  `/plumb:prototype`, get the user's approval, then build it to match*;
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

## 12a. Dependencies and enterprise control

**Needed:** Python 3.9+ standard library (hooks, `build-tokens.py`, `audit.py`,
`build-prototype.py`), and Claude Code or Copilot CLI. git is optional (repo root, "decided by",
session snapshots); without it Plumb still works with fewer details.

**Never:** npm, npx or pip installs; downloads or network calls at run time. Generated pages
(prototype, screens, tours, specimen, reports, directions) load nothing from the network: no CDN,
no hosted web fonts. A project font is embedded from the project's own font files; otherwise a
system font stack is used. Every page opens offline from disk.

**New dependencies in the project:** when a component the agent writes would need a package the
project doesn't have, Plumb asks first and records the answer in the decision log. `PLUMB.md`
`New dependencies: ask | never` (default `ask`); with `never`, components are built from what
the project already has.

**Optional, each the organisation's choice:** Effective HTML skills (else Plumb's built-in rules
and templates), a browser tool (else audit and `/plumb:ux` review code instead of screenshots),
`make` (else the plain commands in `PLUMB.md`), Slate (else no tickets).

**Controlling the plugin:** one Git repo with no build step, so it can be mirrored or forked,
reviewed and installed from an internal copy; releases are tagged `vX.Y.Z` and can be pinned;
`/plumb:upgrade` never runs on its own. Test tools (pytest, Playwright) are used only by Plumb's
own CI.

## 13. The plugin repo

```
.claude-plugin/marketplace.json           marketplace "plumb" → plugins/plumb
plugins/plumb/
  .claude-plugin/plugin.json               version 1.0.0
  skills/{init,create,extract,prototype,tour,audit,ux,update,upgrade,status}/SKILL.md   lean
  reference/   interview.md · rules.md · tokens-format.md · placement.md · scripts.md ·
               prototypes.md · ux.md · copilot.md
  assets/skill/   the design-system template: SKILL.md, design.md and references/* skeletons;
                  scripts/{build-tokens.py, audit.py, build-prototype.py, _plumb.py};
                  web templates (v4, v3, css); specimen, report and prototype-shell templates
  hooks/       hooks.json · run.sh · run.cmd · session_start.py · pre_edit.py · stop_check.py
  templates/   PLUMB.md · the AGENTS/CLAUDE row · decision entry · Makefile snippet
  upgrades/    README.md · 1.0.0.md
  CHANGELOG.md · README.md
examples/caredesk/        the golden output of create on CareDesk Lite, with its input brief
tests/                    see §14
docs/specs · docs/plans · docs/what-you-get.html
TEST.md · README.md (like Slate's: what Plumb does, install in both tools, updating, a table
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
  in the same suite when Playwright is installed; CI installs it on the Ubuntu jobs only (a test
  dependency, never a runtime one), and the tests skip with a reason elsewhere. What CI cannot
  run: the two CLIs themselves (they need sign-in), so the live tmux runs below are done by hand
  before every release and recorded in the PR.
- **Two small sample apps, one per path:** a minimal Next.js + Tailwind v4 app and a minimal
  Angular app (plain CSS/SCSS), kept as source trees under `tests/fixtures/apps/`. Both CLIs run
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

VS Code Copilot Chat; React Native and Flutter themes; shipped component templates for any
framework (components are agent-written from specs); a hosted or shared prototype server
(prototypes are local files; pixel-perfect visual diffing); importing from Figma.

## 17. Verified during the build (not assumed)

1. A plugin `Stop` hook in Copilot CLI: does it map to `agentStop`, and can it make the agent
   continue? Decides the Copilot end-of-turn behaviour in §8.
2. Do both tools load root `.claude/skills/` when a session opens inside a monorepo package?
   Decides the pointer row in §4.
3. Copilot's edit tool names for the PreToolUse matcher (Slate's matcher is the starting point).
