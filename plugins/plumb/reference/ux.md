# The UX review method (`/plumb:ux`)

A review of one screen or flow as a user meets it: against the project's `references/ux.md`, its screen in the main
prototype, usability heuristics, accessibility beyond contrast, and a visual polish pass. `/plumb:audit` checks rules
across the product; this is the deep look at one place. The output is
`<docs>/ux-review-YYYY-MM-DD.html` with findings (severity, where, why, fix).

## 1. Gather

- The screen's prototype file (`<docs>/prototype/screens/<id>.html`) and its entry in `screens.json` (route, source
  files, approval): what was agreed.
- The source files that build it, and the components they use (`references/inventory.md`, `components.md`).
- The skill's `references/ux.md` (users, key tasks and flows, navigation, page anatomy, forms, states, feedback,
  destructive actions, onboarding, voice), `vocabulary.md`, `accessibility.md`, `motion.md`, `design.md`, and the
  platform guidelines (`references/web/ux-guidelines.md`, `references/mobile/…`).
- The decisions that affect the screen (`<docs>/decisions.md`, `Screens:` lines): a finding that contradicts a recorded
  decision says so and proposes revisiting it, it never quietly overrides it.

## 2. See it (both themes, both sizes)

Take screenshots of the **built screen** and its **prototype screen**, at phone (390 × 844) and desktop (1280 × 900)
widths, in light and dark, and walk the main path (each step of the key task), plus each state you can reach.

- **Browser, first available:** (a) the agent's own browser tool, if it has one and the organisation allows it; (b)
  `python3 "<ROOT>/scripts/screenshot.py" <url or file> --out <png> --width 390 --theme dark` (a Chrome, Edge or Chromium
  already installed; nothing is downloaded); (c) none: `screenshot.py` exits 3 with
  `note: visual comparison skipped: no browser found` and a `fix:` line: say so in the report and review the code
  instead. Never install a browser or Playwright; if the user wants screenshots, ask them and wait.
- The built screen needs the app running: ask the user for the URL of their dev server (never start installs); if it is
  not running, review the prototype screen visually and the code for the rest.
- Prototype screens: `<docs>/prototype.html#screen-<id>/<state>` opens one screen in one state. The phone/desktop toggle
  is inside the page; to compare at phone width use `--width 390`.
- Shots go in `<docs>/ux-review-YYYY-MM-DD/` (`<id>-<state>-<width>-<theme>-<built|prototype>.png`) and are shown side
  by side in the report.

## 3. Review, in this order

**Against the prototype (fidelity).** Same components, same states, same copy, same layout at both widths. A difference
is either a bug in the code or a change nobody approved: say which. Every state of the screen file exists in the code.

**Against `ux.md`.** The navigation model, page anatomy, form rules (labels, validation timing, errors in words that
say what to do), every state the screen needs, feedback and confirmation, destructive actions (confirm or undo),
onboarding and first run, voice and microcopy (words from `vocabulary.md`).

**Usability heuristics.**

1. Visibility of status: the user always knows what is happening (loading, saving, saved, failed).
2. Match with the real world: the users' words and order, not the database's.
3. User control and freedom: back, cancel, undo; no dead ends.
4. Consistency and standards: the same thing looks and works the same everywhere, and like the platform.
5. Error prevention: constraints, sensible defaults, confirmation for what cannot be undone.
6. Error recovery: errors say what happened and what to do, in plain words, next to the problem; input is kept.
7. Recognition over recall: options visible, labels on icons, no remembering across screens.
8. Minimal design: nothing that competes with the task; one primary action per view.
9. Help: empty states and first-run explain what to do next.

**Accessibility beyond contrast.** The keyboard path through the main task (Tab order follows the reading order,
nothing unreachable, no traps, Esc closes, focus moves to opened dialogs and back); a visible focus ring everywhere;
labels on every field and icon-only control; headings and landmarks; touch targets (44 px / 44 pt / 48 dp); status not
by colour alone; reduced motion respected; zoom to 200% and long text without breaking.

**Visual polish pass.** Consistent is not the same as polished. Look for:

- **Hierarchy:** one clear focal point and primary action; size, weight and colour used in that order; secondary
  things quieter.
- **Spacing rhythm:** spacing from the scale, used consistently (related things closer than unrelated ones; equal gaps
  for equal relations); no cramped or floating groups.
- **Alignment:** a shared left edge and grid; labels, values and icons aligned on baselines and centres.
- **Type details:** tabular numbers in tables and changing figures; line length 45–75 characters for reading text;
  no orphans in headings; sensible truncation with the full text available.
- **Density:** right for the audience and how often they use it (glanced at vs worked in all day).
- **Colour and dark mode:** accents used sparingly and meaningfully; in dark, elevation and boundaries still visible,
  no pure-black slabs, nothing vanishing.
- **Motion:** purposeful, quick, from the motion tokens; nothing that delays the task; calm with reduced motion.
- **States look designed:** loading keeps the layout (skeletons, not jumps); empty and error states look like part of
  the product.

## 4. Findings

Each finding: **severity** (`error` must change: broken task, inaccessible, contradicts the prototype; `warn` should
change; `suggest` could be better), **where** (`file:line` in the code, or the screen and state in the prototype), **what**
is wrong (what the user experiences), **why** it matters, and the **fix** (the token, component or words to use). Rank
by impact on the key task. Group by heuristic or area.

## 5. The report and what next

Write `<docs>/ux-review-YYYY-MM-DD.html`: a single file that opens from disk, nothing loaded from the network, light
and dark (`prefers-color-scheme` plus a toggle), readable at 390 px without horizontal scroll, using the project's token
block (`build-tokens.py --css-vars`) for its colours. Sections: summary (screen or flow, date, what was reviewed, how:
screenshots or code only, and the `note:` if the visual part was skipped), the screenshots side by side (built vs
prototype, light and dark, phone and desktop), findings ranked, and what to do next. Follow Effective HTML's
`design-artifact` when installed. It is a snapshot: never edit an old one, write a new one.

Then offer, one question at a time: fix now (anything that changes what the screen shows goes through the prototype
first: update the screen file, the user approves, then the code), or Slate tickets (when `kanban/board.py` exists:
grouped by area, written only with `board.py`, each linking the screen in "done when").
