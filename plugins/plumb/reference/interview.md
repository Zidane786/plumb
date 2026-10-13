# The interview

Used by `/plumb:init`, `/plumb:create` (all of it) and `/plumb:extract` (only what the code cannot answer), and by
`/plumb:audit improve` and `/plumb:ux` for their "investigate first" step. Every answer lands in a file; nothing asked
is lost.

## Scripts give evidence, not answers

**No script output is golden.** Plumb's scripts are helpers: a floor and a first guess. You validate every result
against the code (search and read the files any time), correct or add to it, mark what you changed
`(corrected: <why>)` or `(added: <why>)`, and show that **inside the question** before the user decides. Never pass a
script's output to the user unchecked. This holds for every script:

- **`detect.py`** (layout, root, UI packages, UI files, routes, stack): check each against the files. Count the files
  each proposed UI-file pattern actually matches (a glob count in the shell, or the `checked` count of
  `audit.py --inventory`) and the UI files under each UI package. A pattern that matches 0 files, or far fewer than the
  package holds (patterns written from the repo root for a package in `frontend/`), is wrong: correct it (e.g.
  `frontend/src/**`) before asking. Check the root, the copy path, the route roots and the allowed raw paths
  (`frontend/src/components/ui/**`) exist on disk.
- **`scaffold.py`** (the dry-run list, `--verify` problems): does the list hold what the user agreed (the skill dir,
  the copy path, the docs folder) and nothing else? Is each `problem:` real, and is its `fix:` right for this repo?
- **`build-tokens.py`** (contrast fixes, the `--overrides` mapping, `note:` and warning lines): review each proposed
  value and mapping for meaning. `popover` is a raised surface like `card`; `sidebar-accent` mirrors `accent`, and
  its `-foreground` keeps the accent's text colour; a mapping that changes how the app looks (a different value in
  light or dark) is wrong. A contrast fix should stay close to the chosen hue.
- **`audit.py`** (every finding, and `--inventory` clusters): is each finding real, is the rule right here, is the fix
  right? A burst of identical errors right after setup (the same rule hundreds of times, e.g. every Tailwind palette
  class) usually means a setup gap (a setting, a mapping, a wrong pattern), not app debt: find and fix the gap, asked,
  before offering to fix the app. Add your own review beyond the rules. A cluster that merges two values with
  different jobs is split.
- **`build-prototype.py`** (the route map, `--check` results): does each mapped route exist, do its files match?
- **`screenshot.py`**: look at the picture; a blank or half-loaded shot is not evidence.

**When a script is wrong in a way that will recur**, say so and suggest the fix to Plumb: an audit rule's false
positive → offer to add the path to `PLUMB.md`'s `Allowed raw values:` (after the user's OK) and suggest reporting the
rule upstream (an issue on the Plumb repo); a detection miss → record the corrected setting (below) so no script
guesses again. **When a Plumb script or hook is wrong and you correct it, record the Plumb mistake with
/plumb:feedback:** one file in `~/.plumb/feedback/` (outside the project) with the command, what it gave, what was
right and the evidence, so Plumb's developers can fix it. Plumb mistakes only: the project's own design issues are
audit findings (`/plumb:audit`).

## Investigate first

Before asking anything, **go through the project yourself and gather every fact the code can answer.** Only what the
code cannot tell becomes a question. Right after `detect.py` (or, in audit improve and ux, right after reading
`PLUMB.md`), read what applies:

- **Layout:** the repo root, monorepo or workspace files (`pnpm-workspace.yaml`, `turbo.json`, `nx.json`,
  `package.json` `workspaces`, `lerna.json`), each package's manifest, backend-only parts, other repos it points at
  (linked design system, submodules), `.gitignore` (is the skill path ignored?), CI files.
- **Stack:** framework and version (`package.json`, `next.config.*`, `vite.config.*`, `angular.json`, `*.xcodeproj`,
  `build.gradle*`), styling (Tailwind v3 or v4, `tailwind.config.*`, `postcss.config.*`), shadcn (`components.json`),
  the global stylesheet(s) and what they already define (`@theme`, `:root` variables, `.dark` blocks).
  - **Tailwind dark mode in config:** v4 `@custom-variant dark (&:is(.dark *))` in the CSS (every stock shadcn
    `globals.css` has it), v3 `darkMode: 'class' | 'media' | ['selector', '…']` in `tailwind.config.*`.
  - **Angular:** `angular.json` `styles` (the global stylesheet), an Angular Material theme
    (`@use '@angular/material'`, `mat.define-theme`), `*.routes.ts`.
  - **CSS-in-JS theme objects:** MUI `createTheme`, Chakra `extendTheme`, styled-components or Emotion
    `ThemeProvider` themes: their palette, type and spacing are the app's values.
  - **SwiftUI:** asset catalogs (`*.xcassets/*.colorset` with their dark "appearances"), `Color`/`Theme` files, fonts
    in `Info.plist` `UIAppFonts` and the font files they name.
  - **Compose:** `res/values/colors.xml` and `res/values-night/`, `themes.xml`, a `Theme.kt` / `MaterialTheme`
    (`lightColorScheme` / `darkColorScheme`), `Type.kt`, fonts in `res/font`.
- **Screens:** the routes or pages that exist on disk (where each stack keeps them: "What gets recorded" below),
  layouts, navigation (sidebar, tabs), component folders (`components/ui/`, `patterns/`), Storybook stories
  (`*.stories.*`: the components and variants in use).
- **Look and behaviour:** theme provider and how it switches (next-themes and its `attribute`, a `.dark` toggle,
  `prefers-color-scheme`), `prefers-reduced-motion` rules, font setup (`next/font`, `@font-face`, font files), the icon
  library in use, existing tokens or design docs (`docs/`, `design/`, a brand guide, a prototype).
- **Conventions:** `README*`, `AGENTS.md`/`CLAUDE.md`, `SLATE.md`, contributing notes, i18n message files
  (`messages/*.json`, `locales/`, `*.po`, `Localizable.strings`, `strings.xml`): the words the product already uses
  (vocabulary, C15), rules the team already follows.

Fill an **evidence table** as you go and keep it for the questions that follow:

| Fact | Value | Evidence | Confidence |
|---|---|---|---|
| UI package | `frontend/` (Next.js 16, Tailwind v4, shadcn) | `frontend/package.json:12`, `frontend/components.json:1` | high |
| UI files | `frontend/src/** · *.tsx *.css` (corrected: detect's `app/**` matched 0 of 113) | glob count: 113 files | high |
| Routes | `frontend/src/app (next-app)`: 21 pages | `frontend/src/app/**/page.tsx` on disk | high |
| Theme switch | next-themes `attribute="class"` → `class` | `frontend/src/components/providers.tsx:9` | high |
| Skill path git-ignored | `.claude/` is ignored | `.gitignore:14` | high |
| Brand accent | not found in the code | — | asking |

- **Facts the code answers are not asked as open questions.** Show them inside the confirmation question as
  `found: <value> (<file:line>)` for the user to OK or correct.
- **Only what the code cannot tell is asked:** audience, brand intent, priorities, which direction they prefer,
  anything ambiguous or conflicting. One question at a time, with a recommendation.
- **Unknowns and conflicts are said plainly:** "couldn't find a brand colour: asking", "two theme toggles disagree
  (`a.tsx:4` sets `.dark`, `b.tsx:9` sets `data-theme`): asking".

**What gets recorded.** Plumb's scripts and hooks never discover the layout on their own: they read what the user
confirmed. Init, create and extract fill these from the investigation (never from detect alone), show each with its
evidence and matched-file count inside the placement question, and write them to `PLUMB.md` (scaffold answers keys in
brackets): `UI packages:` (`ui_packages`), `UI files:` (`ui_files`: patterns from the repo root, each matching at least
one file, e.g. `frontend/src/** · *.tsx *.css`; `{a,b}` works as in a shell: `*.{tsx,css}`), `Routes:` (`routes`, below), `Allowed raw values:` (`allowed_raw`),
the copy paths (`web_copies`) and the tokens settings. `scaffold.py --verify` checks them (each route root exists;
each UI-file pattern matches a file). Changing them later: `/plumb:update` (or `/plumb:init` again); a project with no
`Routes:` recorded is told to run `/plumb:init` by status and audit.

**`Routes:` is `<path> (<kind>)`**, the app's page roots relative to the repo root, comma-separated when there are
several, or `none`. Record the kind from the evidence (the framework you found); **never leave the kind to be
guessed**: a bare path is guessed from its folder name, so a Nuxt `pages/` would read as Next.js pages and an Angular
`src/app` as the Next.js app router, and route discovery would silently find nothing.

| Stack | Where the pages are (each one checked on disk) | `Routes:` value |
|---|---|---|
| Next.js, app router | `app/**/page.*` (route groups `(x)` and `@slots` are not in the URL; `_folders` are private) | `frontend/src/app (next-app)` |
| Next.js, pages router | `pages/**` (not `_app`, `_document`, `api/`) | `src/pages (next-pages)` |
| Nuxt | `pages/**/*.vue` | `pages (nuxt)` |
| SvelteKit | `src/routes/**/+page.svelte` | `src/routes (sveltekit)` |
| Angular | `*.routes.ts` / `*routing.module.ts` | `src/app (angular)` |
| Vue Router, React Router, another router file | `router/index.*`, `createBrowserRouter` / `<Route path>` | `src/router/index.ts (router)` |
| iOS or Android only, design only, backend only; plain HTML pages, SwiftUI `NavigationStack` / `TabView`, Compose `NavHost`, React Native navigators | (screens still found for the prototype) | `none` (say the route checks stay off for them) |

## Layout cases

Init asks each of these as its own question (inside it: the evidence), then runs detect again with `--cwd <folder>`
when the folder changes:

- **Parent folder** (`layout: parent`): list `children` and ask which project; write nothing in the parent. Tell the
  user to open their next sessions in that folder (the hooks look for `PLUMB.md` from where a session opens).
- **New, empty folder** (`layout: new`): "This folder is empty: start a new project here?" (a) Yes, create the design
  system here (Recommended) (b) No, it is somewhere else: ask for the path. On (a) the route is create. No git is
  fine; offer `git init` once.
- **Backend only:** "Where will the UI live?" (a) The frontend is in another repo (Recommended) (b) It will live here
  (c) Design only for now. On (a) ask for its path and set Plumb up there (that path becomes `<root>`). Then ask
  separately: "Also write a linked `PLUMB.md` (and the AGENTS/CLAUDE row) in this backend repo, pointing at the
  frontend's design system?" (a) Yes (Recommended) (b) No; write it only on yes (the one write outside `<root>`). Tell
  the user to open the frontend repo for UI work. On (c): design only (`routes: none`).
- **React Native** (`framework: react-native`): React Native themes are not supported in Plumb 1.0.0 (a 1.1.0
  candidate). Offer only: (a) design only for now (Recommended) (b) web, when the repo has a web part (c) native iOS
  (SwiftUI) / Android (Compose) themes for native apps. Never write React Native components.
- **Inside a bigger project** (`enclosing` is set: outside git, a folder above has monorepo markers or a `PLUMB.md`):
  "Is the project `<enclosing.root>` (this folder is one of its packages)?" (a) Yes, use the enclosing folder
  (Recommended) (b) No, this folder is the project.

## Nothing is written without the user's OK

The user stays in the loop from the first detection to the last file. Each checkpoint is a question-tool step that
waits for the answer; the numbers are the create skill's (extract has the same checkpoints under its own numbers):

| # | Checkpoint | Inside the question |
|---|---|---|
| 1 | Placement (init) | The whole "Plumb found … I'll create …" block, with corrections, the UI-file and route evidence (matched-file counts) and any git-ignored path. |
| 2–3 | After the product questions | The five-line summary: "Right?" |
| 4–5 | Platforms, each design decision | Options, the recommendation and why (with the `file:line` it came from). |
| 6 | All decisions | Every decision on one screen. |
| 7–8 | Directions | The path to write; then each direction's name and idea to pick from. |
| 9 | Before generating | The full token set: colours light and dark, type, spacing, radius, shadows, motion, settings. |
| 10 | Before writing files | `scaffold.py --dry-run`'s full list of files and paths. |
| 11 | Before the first build, when a web copy is an existing file | `build-tokens.py --check`'s diff and what it means. |
| 12 | The project's own theme variables | The `--overrides` mapping, verified, corrections marked. |
| 13 | Each contrast fix | The failing pair, its ratio and the proposed value. |
| 14 | Before writing components | Which components, the framework and primitives, and the paths. |
| 16 | Prototypes | The key screens to prototype. |
| — | Wiring in | Each item (PLUMB.md values, checks, AGENTS/CLAUDE row, Makefile, Slate, Kiro) asked on its own. |

Extract adds: the UI folders to scan, each token group, the screens to prototype, the screen files to write, each
screen's approval.

## How to ask

- Use the question tool (Claude Code: `AskUserQuestion`; Copilot CLI: its ask-the-user tool). If there is none, ask
  in plain text with lettered options and wait.
- **The content goes inside the question.** Whatever the user confirms (the "Plumb found" block, the "Right?"
  summary, the decisions, the token set, the dry-run file list, a diff, a mapping, a fix) is part of the question
  itself: the question text, or the recommended option's preview when the tool has one (Claude Code's
  `AskUserQuestion` options take a `preview`). **Never only in a message before the question:** Claude Code can hide
  text written right before a question, so the user would be asked about something they cannot see. Never ask about
  "the setup above" or "the list above". Copilot CLI's ask tool takes it in the question text. Without a question tool:
  one message holding the content and the lettered options, then wait. **Never summarise a list of files or values**
  the user is confirming (every file of the dry run, every token). **A long diff** (more than about 60 lines, e.g. a
  whole `globals.css`) is the one exception: write the full diff to `<root>/.plumb-tmp/<copy name>.diff` with your
  write tool and put inside the question a summary (each file with its +/- counts, what each changed hunk does) and
  the first ~40 lines, plus that path for the user to open before answering.
- **STOP: ask, wait for the answer.** A checkpoint is a question and nothing else in that turn: no write and no command
  before the answer, never two checkpoints in one question, never a checkpoint's action in the same shell call as the
  next one. A permission prompt from the tool (Copilot CLI asks before commands) is not the user's OK to a checkpoint.
- **One question at a time.** Only part A may group up to four related questions in one call.
- 2–4 options per question, **the recommendation first, marked "(Recommended)"**, each with a one-line consequence.
  The user can always answer in their own words.
- Every recommendation **follows from what you already know**: the evidence table, the brief, earlier answers. Say why
  in one short clause ("dense: people work in it all day"; "next-themes sets `.dark`: `providers.tsx:9`").
- Skip a question whose answer is already certain (from files or earlier answers); state it as `found: …` in the next
  confirmation instead.
- Never install or download anything to answer a question (no fonts, icon packs or images from the network). If an
  answer seems to need something the project does not have, say so and ask the user what to do, then wait.

## A. The product first

Before any design question. Read the sources above first and pre-fill suggestions from them.

| # | Question | Options to offer | Lands in |
|---|---|---|---|
| A1 | What is being built, in one sentence? | A sentence drafted from the README/brief (Recommended); "let me write it" | `design.md`, `SKILL.md`, answers `description` |
| A2 | Who is it for, and how skilled are they? | 2–3 audiences inferred from the brief (e.g. "clinic staff, trained, daily"; "first-time visitors") | `ux.md` Users, answers `audience` |
| A3 | Where and how often is it used? | desk all day · phone on the go · both · glanced at now and then | density (C2), platforms (B1), `ux.md` Context |
| A4 | The 3–5 key tasks people come to do | Tasks drafted from the brief, routes or tickets | `ux.md` Key tasks and flows, the key screens for F |
| A5 | The feel, with reference products | 3 pairs drawn from A1–A3 (e.g. "calm and clinical, like Linear"; "warm and friendly, like Airbnb"; "bold and editorial") | personality (C1), directions (D) |
| A6 | Existing brand: logo, colours, fonts, guidelines | "use the files I found: <paths>" (Recommended when found) · "no brand yet" · "I'll point you to them" | accent (C3), type (C7), `references/fidelity.md` |

Group A1–A4 in one call and A5–A6 in a second. Then put the five-line summary of A **inside** the question "Right?"
before part B.

## B. Platforms and stack

| # | Question | Options | Recommendation from |
|---|---|---|---|
| B1 | Which platforms? (multi-select) | Web · iOS (SwiftUI) · Android (Compose) | detection (`ui_packages[].platforms`), A3 (phone use → also mobile) |
| B2 | Web framework (confirm) | the detected one (Recommended) · React/Next · Vue · Svelte · Angular · plain HTML | `ui_packages[].framework`, else ask |
| B3 | Styling (confirm) | detected `tailwind-v4` / `tailwind-v3` / `css` (Recommended); shadcn noted when `components.json` exists | `ui_packages[].styling`; a new project with no stack: Tailwind v4 |

Detected values are `found: …` facts with their evidence: show them and ask the user to confirm or correct. React
Native is not supported in 1.0.0 (a 1.1.0 candidate): offer design only, web, iOS or Android, never React Native
components. **Design only** (no app yet, a backend repo, a React Native app) skips B: web, plain CSS, no copies,
reference starters only, an HTML prototype. Platforms can be added later with `/plumb:update`.

## C. Design decisions, one at a time

Each answer becomes token values, a line in `design.md`, and a decision entry (G). Recommend from A, B and the
evidence table, and say why in one clause with every recommendation. Brand colours or fonts found in the code are
offered as suggestions.

| # | Decision | Options (recommendation first, chosen from A) | Lands in |
|---|---|---|---|
| C1 | Personality and register | 3 named registers from A5, e.g. "calm and precise" · "warm and approachable" · "bold and expressive" | `design.md` Direction, every later default |
| C2 | Density | compact (all-day work tools, tables) · comfortable (most apps) · spacious (marketing, occasional use) — from A3 | spacing scale, type sizes, control heights |
| C3 | Accent colour | the brand colour (A6) · 2–3 accents that fit C1, each shown as a hex with its dark value | `color.primary` + `on-primary` (light and dark) |
| C4 | Neutrals | tinted toward the accent (Recommended for most) · pure grey · warm · cool | `background surface sunk on-surface on-surface-muted outline outline-input` |
| C5 | Semantic colours | a set derived from C3/C4 that passes contrast: success, warning, danger, info | `color.success`, `warning`, `danger`, `info` + `on-` partners |
| C6 | Label colours (tags, statuses, categories) | none · 4–6 hues tuned to the neutrals · "match our status names: …" (from A4) | `label.*` |
| C7 | Type family and scale | the brand font when the project has its files (A6) · the system stack (Recommended when none: no downloads) · a mono for code; scale: the default 8 steps tuned for C2 | `font.sans`, `font.mono`, `typography.*` |
| C8 | Spacing scale | 4px base (Recommended) · 8px base for spacious; keys are Tailwind steps (`"2": "8px"`) | `spacing.*` |
| C9 | Radius | sharp (2/4/6) · soft (4/8/12, Recommended for most) · round (8/12/16 + full) — from C1 | `radius.*` |
| C10 | Elevation | flat with borders (dense tools) · soft shadows (Recommended) · layered — and how dark mode shows depth (lighter surfaces) | `shadow.*`, `design.md` |
| C11 | Motion, then (its own question) reduced motion | subtle and fast 150/200/300ms (Recommended) · expressive · minimal; reduced motion: drop movement, keep fades (Recommended) · no animation at all | `motion.*`, `references/motion.md`, `$extensions.plumb.motion.reduced` (`"keep-fades"` \| `"none"`) |
| C12 | Icons | the icon set already in the project (never a second one) · Lucide on web, SF Symbols on iOS, Material Symbols on Android (Recommended when none) | `icon-map.json` |
| C13 | Dark mode, then (its own question) how the app switches | light and dark, both designed (Recommended, the default) · light only (an explicit decision, recorded; `Themes: light-only`). Then the switch: see "Theme switch" below | every colour's `dark` value, `PLUMB.md` `Themes:`, `$extensions.plumb.web.theme_switch` (`"both"` \| `"system"` \| `"class"` \| `"data-theme"`) |
| C14 | Accessibility target | WCAG 2.2 AA (Recommended, the default) · AAA for text · AA plus larger targets for A2's audience | `references/accessibility.md`, contrast |
| C15 | Vocabulary and voice | a voice from C1 ("plain and calm, verbs on buttons") · the words for the key objects and statuses from A4 | `references/vocabulary.md`, answers `voice` |
| C16 | **UX patterns**: seven questions, below | recommendations from A2–A4 and the screens | `references/ux.md` |

**C16 is seven questions, one each:** (a) navigation model (sidebar · top tabs · bottom tabs on phones · hub and
spoke); (b) page anatomy (header + actions + content; list → detail); (c) forms (labels above, validate on blur,
errors in words); (d) feedback (toasts for background results, inline for errors); (e) empty, loading and error states
(skeletons for lists, a next step in every empty state, errors say what happened and what to do); (f) destructive
actions (confirm with the object named · undo instead of confirm); (g) onboarding (none · first-run checklist ·
sample data). Ask all seven. Skip one only when the code already answers it for certain (extract: the app has a left
sidebar) and then say which you skipped and why, with the evidence (`found: left sidebar (app/layout.tsx:20)`).

After C, put a one-screen summary of every decision **inside** the question "Generate directions from these?"

**Settings the generator honours.** C11 and C13 also set values in the tokens file, passed as the answers keys
`reduced_motion` and `theme_switch` (create checkpoint 10; checked in 11; tokens-format.md), and Tailwind projects add
`reset_palette` (below). Extract always asks them, recommending what the app already does:
`$extensions.plumb.motion.reduced` — `"keep-fades"` (the generated `prefers-reduced-motion` block stops movement but
keeps opacity fades) or `"none"` (every animation and transition off) — and `$extensions.plumb.web.theme_switch` —
`"both"`, `"system"`, `"class"` or `"data-theme"` — which decides whether the generated web theme answers
`prefers-color-scheme`, a `.dark` class, both, or a `data-theme` attribute. Without them the generated CSS may not match
what the user chose (a `.dark` theme nothing turns on, fades removed the user wanted kept). On keep fades in a
plain-CSS app, tell the user in one line to add the class `motion-fade` to each element whose own transition is only a
fade (Tailwind's `transition-opacity` / `transition-colors` need nothing).

## Theme switch: what to recommend

One rule for every tool. Look for the evidence first (the theme provider, the code that toggles dark mode, the global
stylesheet), then take the **first row that matches**: its value is the recommendation, marked "(Recommended)". Never
recommend `both` when a row above it matches.

| The code shows | Recommend |
|---|---|
| next-themes `<ThemeProvider attribute="class">` (with or without `enableSystem`: next-themes follows the system setting by setting the class itself) | `class` |
| next-themes `attribute="data-theme"`, or no `attribute` (next-themes' default) | `data-theme` |
| next-themes with an array (`["class", "data-theme"]`): `class` when it holds "class", else `data-theme` | as said |
| next-themes with another attribute (`data-mode`): Plumb follows only a class or `data-theme`, so recommend switching the app's attribute to `class` (a one-line change in the provider, asked; Tailwind's `dark:` follows it), explain, and still ask (options: `class` with that change · `data-theme` with that change · `both`, leaving the app as it is) | `class` |
| other code that toggles a `.dark` class on `<html>` | `class` |
| other code that sets a `data-theme` attribute | `data-theme` |
| Tailwind v4 `@custom-variant dark (&:is(.dark *))` (on `.dark`; stock shadcn), or v3 `darkMode: 'class'` / `['selector', '.dark']` | `class` |
| Tailwind v4 `@custom-variant dark` on `[data-theme=dark]`, or v3 `darkMode: ['selector', '[data-theme="dark"]']` | `data-theme` |
| Tailwind v3 `darkMode: 'media'` (or no `darkMode`: v3's default), with no `.dark` toggle | `system` |
| only `@media (prefers-color-scheme: dark)` | `system` |
| a `.dark` class and the media rule | `both` |
| no dark mode in the code (a new app) | `both` |

Put the evidence **inside the question**: "How does the app switch themes? found: next-themes `attribute="class"`
(`src/components/providers.tsx:9`)" with "class (Recommended): what the app does" first. Ask anyway; the user decides.

## Tailwind's default palette (`reset_palette`)

Only for Tailwind styling (v4 or v3); plain CSS skips it. Plumb's generated block can switch off Tailwind's built-in
scales so only the tokens' values exist: the tokens setting `$extensions.plumb.web.reset_palette`, answers key
`reset_palette`. The reset covers **all six namespaces**, not only colours: colours (`bg-emerald-500`, `text-white`,
`bg-black/50`), radii (`rounded-xl`), shadows (`shadow-md`), text sizes (`text-lg`), fonts (`font-serif`) and easings
(`ease-in-out`). `false` keeps all six open.

- **Create, no UI code yet:** reset (`true`, Recommended): new screens use only tokens from the start. Ask only when
  Tailwind is the styling; otherwise record nothing.
- **Create on an existing app, or extract:** count the app's uses of Tailwind palette classes (evidence: the count and
  a few `file:line`). Recommend **keep** (`false`): resetting would make every one of those classes colourless (and
  the other default classes lose their value) the moment the first build runs. The audit lists palette colours as
  suggestions to move onto tokens over time; switch the reset on later with `/plumb:update` once they are gone.
- Say what to expect with `false`: the default classes keep working, but the audit still reports the default sizes
  that are not on the project's scales (`text-lg`, `rounded-xl`) as off-scale errors, as before; those are the app's
  own findings for `/plumb:audit fix`, not a setup gap.
- Put the count and the consequence inside the question, and say it again in the stylesheet-diff checkpoint.
- Older projects: `build-tokens.py --migrate` records `reset_palette: true` (what their block already did); `/plumb:upgrade`
  offers keep (`false`) when the app uses palette classes.

## D. Directions

2–3 directions on one page, `docs/design/directions.html`. Each direction is a **distinct, finished-looking option**
(different palette, type pairing and layout feel, all within the answers of C), never three recolours of one layout.
Each shows: its name and one-line idea; the palette with hex values (light and dark); the type scale with real text;
the core components (button variants, input with error, card, chip, toast); and **one real screen of the product**
(a key task from A4) with real content, in **light and dark side by side**.

- **Effective HTML installed** (the `design-artifact` and `html` or `html-prototype` skills are available in this
  session): follow them for the page.
- **Not installed:** start from `<ROOT>/templates/directions.html` and keep its rules: one self-contained file, nothing
  from the network (no CDN, no hosted fonts: system stacks or fonts embedded from the project's own files), each
  direction's values as CSS custom properties scoped to its section, both themes visible, real content, keyboard
  reachable, `prefers-reduced-motion` respected.

Then ask, with the path and each direction's name and idea inside the question: pick one · combine (say which parts
from which) · change something. The page stays as the record and is linked from the decision entry.

## The answers file for scaffold.py

After the user's OK to the full token set, write the confirmed answers as JSON to `<root>/.plumb-tmp/answers.json`
(the folder holds a `.gitignore` with `*`; it lives until setup ends: "Scratch files" below) and run `scaffold.py
--answers` with `--dry-run`. Put its full file list inside the question; on yes run the same command without
`--dry-run` and with `--confirm <token>`, the token the dry run printed on its last line (`confirm: show the user this
list; after their OK run the same command without --dry-run, plus --confirm <12-hex token>`). The token covers the
answers and the file list, so a changed answer, or a file written in between, makes it stale: the real run refuses
it; run the dry run again and ask again. A `warning: … git-ignored` line in the dry run is asked as init step 1.5.
Keys (all optional; see `scaffold.py`'s docstring for the exact names): `description`, `audience`,
`direction`, `voice`, `themes`, `python`, `role`, `ui_packages`, `ui_files`, `routes`, `allowed_raw`, `web_copies`,
`colors` (`light`/`dark` for background, surface, sunk, on-surface, on-surface-muted, primary, on-primary, outline,
outline-input, danger, on-danger, success, on-success, scrim), `fonts` (`sans`, `mono`), `type_scale`
(`display h1 h2 h3 body-lg body sm xs` → `[size, line height]`), `spacing` (Tailwind steps), `radius` (`sm md lg`),
`shadows` (`card`, `popover`, each `light`/`dark`), `motion` (`fast mid slow`), `icons`, `theme_switch` (`both`
`system` `class` `data-theme`), `reduced_motion` (`keep-fades` `none`), `reset_palette` (`true` `false`; Tailwind).

Anything the scaffold has no key for (warning, info, `label.*`, `md` values, extra tokens) goes into the tokens file
right after scaffolding, before the first build (see `tokens-format.md`).

## Scratch files

Every temporary file (the answers JSON, a saved diff, an inventory or overrides JSON you keep to read again) goes in
**`<root>/.plumb-tmp/`**, nowhere else: never `/tmp`, `%TEMP%`, a folder next to the repo or another session's
scratch folder (they sit outside the project, so Copilot CLI asks for path access, and nothing outside `<root>` is
written). Write `<root>/.plumb-tmp/.gitignore` containing `*` first when the folder is new.

**The setup marker.** A setup in progress is the marker file **`<root>/.plumb-tmp/setup-in-progress`**, and only init,
create and extract write it: right after the placement OK (one line in it: the command, the date and the
checkpoint), and they rewrite the marker at every checkpoint and when init resumes a setup, so only an abandoned
setup goes stale. The end-of-turn
check stands down while the marker exists and is under 6 hours old, so it does not stop a half-built setup (an older
marker is stale: the check runs again and session start and status say "a setup marker from <time> is stale — finish
/plumb:init or remove .plumb-tmp/"); init's resume check and status's half-setup report look for the marker file,
never for the folder. **When setup ends** (the final checklist), remove
the whole `.plumb-tmp/` folder, last. Every other command may use `.plumb-tmp/` for scratch, never writes the marker,
and must clean up their own files when it ends (and the folder, when it created it).

## E. Generate, in detail

- **Fill in (create checkpoint 11).** Add what the scaffold has no key for to the tokens file exactly as approved in
  the token set. Check the settings are there as answered and add any the scaffold did not write:
  `$extensions.plumb.motion.reduced`, `$extensions.plumb.web.theme_switch`, and for Tailwind
  `$extensions.plumb.web.reset_palette`. Write `design.md`, `references/ux.md`, `vocabulary.md`, `motion.md`,
  `accessibility.md` from the answers, replacing every "to fill" prompt.
- **The existing stylesheet.** When a web copy (`$extensions.plumb.web.copies`) is a file that already exists (e.g.
  `app/globals.css`), `build-tokens.py --check` prints the diff for that file. Inside the question: the diff and what
  it means (Plumb adds a marked `plumb:start … plumb:end` block with the generated theme and owns only that block; the
  rest stays the project's, still edited by hand), and with `reset_palette: true` that Tailwind's default colour
  classes stop working (the count of uses). Build only on yes (no → another path for the copy, or none).
- **The project's own theme variables.** When the audit reports `block-override` (a stock create-next-app or shadcn
  `globals.css` sets `--color-background`, `--font-sans` … in its own `@theme`), run `build-tokens.py --overrides`,
  verify each mapping (above), and show inside the question each variable, the token it maps onto (`kind` token: the
  token wins; new-name: a token is added, e.g. `color.foreground` = `{color.on-surface}`; a font the app loads goes
  first in its font token), the project's values light and dark, the lines that go, its `notes`, each `by_hand` item
  and your corrections. A note that says **"the look changes; ask the user"** (a variable keeps its role token because
  no token has the app's exact colours) goes inside the question on its own line, with both values (the app's today,
  the token's): offer keep the role token (the look changes as shown) · add a token with the app's colours (asked,
  through the token set) · map it to another token you name. Ask once: move them into the tokens (Recommended: the app's utilities keep working and the
  audit can pass) · leave them for now (the audit fails until then). Only on yes: apply your corrections to the tokens
  file, then `build-tokens.py --overrides --apply && build-tokens.py && audit.py --json`. Files in each
  `project_variables` entry's `used_in` still read a removed variable: show them and, asked first, point them at the
  token's variable. What the audit still reports after that is the app's own code (raw colours in its keyframes,
  off-token durations…): read it critically (above), say so and offer `/plumb:audit fix`.
- **Contrast fixes.** For each `contrast` error: the failing pair, its ratio (light or dark) and the proposed passing
  value inside the question; apply each only on the user's OK, rebuild, repeat until none is left. The evidence is the
  generated contrast block in `references/dark-mode.md`.
- **Components.** Propose which starter components (button, input, select, checkbox, card, chip/badge, dialog, sheet,
  menu, tabs, toast, tooltip, empty state, error state, skeleton, page header, app shell), the framework and
  primitives (shadcn/Radix on React when the project has them, native controls on SwiftUI and Compose), and the paths
  (app exists → e.g. `components/ui/`; no app or design only → `<skill dir>/assets/platforms/<platform>/starter/`). On
  OK the agent writes them from `references/components.md`, tokens only, never adding a dependency (a missing
  primitive → ask the user and wait), and updates `references/inventory.md`. Extract: the components exist already:
  map them, propose only the missing starters, change existing components only with the user's OK.
- **Record (G).** One entry per decision (direction, each C decision, contrast fixes) appended to
  `<root>/docs/design/decisions.md` in the format of `<ROOT>/templates/decision-entry.md`: id `DS-YYYYMMDD-<slug>`,
  date, **who decided** (`git config user.name`; without git, ask the user's name), the options considered with links
  (`directions.html#d2`, or `extract.html` for extract), the one chosen and why in the user's words, the screens
  affected (`all` for tokens), the Slate ticket if any. Append only. Mirror each entry into `docs/decisions.md` when
  the project keeps one, and add a line to `design.md`'s revision notes.

## Where the rest lands

| Answers | File in the skill |
|---|---|
| A1, C1, C3–C10, the chosen direction | `design.md` (the look in words; wins every disagreement) |
| A2–A4, C16 | `references/ux.md` (users, context, key tasks and flows, navigation, page anatomy, forms, states, feedback, onboarding) |
| C11 | `references/motion.md` |
| C14 | `references/accessibility.md` |
| C15 | `references/vocabulary.md` |
| C13 | `references/dark-mode.md` (the contrast block is generated) |
| A6 (a prototype or brand guide existed) | `references/fidelity.md` |
| Every decision | `docs/design/decisions.md` (one entry each, "Record (G)" above) |
