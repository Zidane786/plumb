# The interview

Used by `/plumb:create` (all of it) and `/plumb:extract` (only what the code cannot answer). Every answer lands in a
file; nothing asked is lost.

## Nothing is written without the user's OK

The user stays in the loop from the first detection to the last file. Each checkpoint is a question-tool step that
waits for the answer:

| # | Checkpoint | Shown to the user |
|---|---|---|
| 1 | Detected facts | Project root, framework, styling, platforms, brand colours and fonts found in the code: **suggestions** to confirm or correct, never used silently. |
| 2 | After the product questions | A five-line summary: "Right?" |
| 3 | Each design decision | Options, the recommendation and why. |
| 4 | Before generating | The full token set: colours light and dark, type, spacing, radius, shadows, motion (the chosen direction as the preview). |
| 5 | Before writing files | `scaffold.py --dry-run`'s full list of files and paths. |
| 6 | Each contrast fix | The failing pair, its ratio and the proposed value. |
| 7 | Before writing components | Which components, the framework and primitives, and the paths. |
| 8 | Wiring in | Each item (PLUMB.md values, checks, AGENTS/CLAUDE row, Makefile, Slate, Kiro) asked on its own. |

Extract adds: the UI folders to scan, each token group, the screens to prototype and the screen files to write.

## How to ask

- Use the question tool (Claude Code: `AskUserQuestion`; Copilot CLI: its ask-the-user tool). If there is none, ask
  in plain text with lettered options and wait.
- **One question at a time.** Only part A may group up to four related questions in one call.
- 2–4 options per question, **the recommendation first, marked "(Recommended)"**, each with a one-line consequence.
  The user can always answer in their own words.
- Every recommendation **follows from what you already know**: the brief, `README*`, `AGENTS.md`/`CLAUDE.md`,
  `SLATE.md`, any prototype, brand or design files in the repo, and earlier answers. Say why in one short clause
  ("dense: people work in it all day").
- Skip a question whose answer is already certain (from files or earlier answers); state the answer instead and move on.
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

Group A1–A4 in one call and A5–A6 in a second. Then summarise A in five lines and ask "Right?" before part B.

## B. Platforms and stack

| # | Question | Options | Recommendation from |
|---|---|---|---|
| B1 | Which platforms? (multi-select) | Web · iOS (SwiftUI) · Android (Compose) | detection (`ui_packages[].platforms`), A3 (phone use → also mobile) |
| B2 | Web framework (confirm) | the detected one (Recommended) · React/Next · Vue · Svelte · Angular · plain HTML | `ui_packages[].framework`, else ask |
| B3 | Styling (confirm) | detected `tailwind-v4` / `tailwind-v3` / `css` (Recommended); shadcn noted when `components.json` exists | `ui_packages[].styling`; a new project with no stack: Tailwind v4 |

Detected values are suggestions: show them and ask the user to confirm or correct. React Native is not supported in
1.0.0 (a 1.1.0 candidate): offer design only, web, iOS or Android, never React Native components. **Design only**
(no app yet, a backend repo, a React Native app) skips B: web, plain CSS, no copies, reference starters only, an HTML
prototype. Platforms can be added later with `/plumb:update`.

## C. Design decisions, one at a time

Each answer becomes token values, a line in `design.md`, and a decision entry (G). Recommend from A and B, and say
why in one clause with every recommendation. Brand colours or fonts found in the code are offered as suggestions.

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
| C11 | Motion and reduced motion | subtle and fast 150/200/300ms (Recommended) · expressive · minimal; reduced motion always drops movement, keeps fades | `motion.*`, `references/motion.md` |
| C12 | Icons | Lucide on web, SF Symbols on iOS, Material Symbols on Android (Recommended) · the icon set already in the project (never a second one) | `icon-map.json` |
| C13 | Dark mode | light and dark, both designed (Recommended, the default) · light only (an explicit decision, recorded; `Themes: light-only`) | every colour's `dark` value, `PLUMB.md` `Themes:` |
| C14 | Accessibility target | WCAG 2.2 AA (Recommended, the default) · AAA for text · AA plus larger targets for A2's audience | `references/accessibility.md`, contrast |
| C15 | Vocabulary and voice | a voice from C1 ("plain and calm, verbs on buttons") · the words for the key objects and statuses from A4 | `references/vocabulary.md`, answers `voice` |
| C16 | **UX patterns**, one sub-question each: navigation model (sidebar · top tabs · bottom tabs on phones · hub and spoke); page anatomy (header + actions + content; list → detail); forms (labels above, validate on blur, errors in words); feedback (toasts for background results, inline for errors); empty, loading and error states (skeletons for lists, a next step in every empty state, errors say what happened and what to do); destructive actions (confirm with the object named · undo instead of confirm); onboarding (none · first-run checklist · sample data) | recommendations from A2–A4 | `references/ux.md` |

After C, show a one-screen summary of every decision and ask "Generate directions from these?"

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

Tell the user the file path and ask: pick one · combine (say which parts from which) · change something. The page stays
as the record and is linked from the decision entry.

## The answers file for scaffold.py

**Before generating**, show the full token set (colours light and dark, type, spacing, radius, shadows, motion; the
chosen direction is the preview) and wait for the user's OK. Then write the confirmed answers as JSON to a temporary
file **outside the repo** (the system temp folder) and pass it to `scaffold.py --answers`, first with `--dry-run`:
show its full file list and paths, and run it for real only on the user's OK. Keys (all optional; see `scaffold.py`'s docstring for the exact names): `description`,
`audience`, `direction`, `voice`, `themes`, `python`, `role`, `ui_packages`, `ui_files`, `allowed_raw`, `web_copies`,
`colors` (`light`/`dark` for background, surface, sunk, on-surface, on-surface-muted, primary, on-primary, outline,
outline-input, danger, on-danger, success, on-success, scrim), `fonts` (`sans`, `mono`), `type_scale`
(`display h1 h2 h3 body-lg body sm xs` → `[size, line height]`), `spacing` (Tailwind steps), `radius` (`sm md lg`),
`shadows` (`card`, `popover`, each `light`/`dark`), `motion` (`fast mid slow`), `icons`.

Anything the scaffold has no key for (warning, info, `label.*`, `md` values, extra tokens) goes into the tokens file
right after scaffolding, before the first build (see `tokens-format.md`).

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
| Every decision | `docs/design/decisions.md` (one entry each, see the create skill, step G) |
