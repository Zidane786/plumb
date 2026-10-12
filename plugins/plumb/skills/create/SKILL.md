---
name: create
description: Create a new design system for this project - the product interview first, then platforms and stack, then each design decision with a recommendation (including UX patterns and dark mode), 2-3 directions on one page, then, after the user approves the token set and the file list, generate the tokens, themes, contrast evidence, skill files and starter components (audit must pass), offer prototypes of the key screens, and record every decision in docs/design/decisions.md.
argument-hint: "[product name]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/detect.py*), Bash(python *scripts/detect.py*), Bash(py -3 *scripts/detect.py*), Bash(python3 *scripts/scaffold.py*), Bash(python *scripts/scaffold.py*), Bash(py -3 *scripts/scaffold.py*), Bash(python3 *scripts/build-tokens.py*), Bash(python *scripts/build-tokens.py*), Bash(py -3 *scripts/build-tokens.py*), Bash(python3 *scripts/audit.py*), Bash(python *scripts/audit.py*), Bash(py -3 *scripts/audit.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git -C * status --short)
---

# /plumb:create — from an idea to a design system

Only run when the user typed `/plumb:create` (or `/plumb:init` routed here). Other skills offer it, never run it.

```
placement ─▶ A product ─▶ "Right?" ─▶ B platforms ─▶ C decisions (one at a time) ─▶ D directions ─▶ you pick
   ─▶ E: token set OK? ─▶ file list OK? ─▶ scaffold ─▶ themes ─▶ each contrast fix OK? ─▶ components OK? ─▶ audit 0
   ─▶ G record decisions ─▶ F prototypes of the key screens ─▶ wire in (init step 4) ─▶ summary
```

**Rules.** **Nothing is written without the user's OK.** Each checkpoint below (marked **OK?**) is a question-tool
step that waits for the answer. Facts found in the project (framework, styling, platforms, brand colours or fonts in
the code) are **suggestions** to confirm or correct, never used silently. Questions go **one at a time** (part A may
group up to four), options with the recommendation first marked "(Recommended)" and **why**, each recommendation
following from what the user said. Every question and how to derive its recommendation:
[reference/interview.md](../../reference/interview.md). Light **and** dark are designed by default; light-only is an
explicit, recorded decision. **Never install or download anything** (no packages, fonts, icon sets, images); if
something seems needed, say so, **ask the user and wait**. Pre-approved commands (`allowed-tools`): Plumb's `detect.py`,
`scaffold.py`, `build-tokens.py`, `audit.py`, and the read-only git calls; anything else asks first.

**Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
`<plugin>/skills/create`) + `/../..`, resolved to an absolute path. The tokens format:
[reference/tokens-format.md](../../reference/tokens-format.md). Placement: [reference/placement.md](../../reference/placement.md).

**Project root (`<root>`):** the absolute root the user confirmed in `/plumb:init`. Every path below is relative to
`<root>` and every command names it explicitly; never write outside it, never use `.` for it. The one exception: the
answers JSON for `scaffold.py` goes to the system temp folder and is deleted right after the scaffold.

## Step 0: placement and Python

- Routed from `/plumb:init`: use its confirmed placement, `<root>` and Python command.
- Run directly: if `PLUMB.md` names a design system that already exists, stop: "This project already has a design
  system. Use `/plumb:update` to change it." Otherwise do `/plumb:init` steps 1–2 first (read `ROOT/skills/init/SKILL.md`):
  the user confirms the "Plumb found … I'll create …" block before anything is written.
- **Design only** (placement says so: a backend repo, a React Native app, or the user's choice): platforms `web`,
  styling `css`, no web copies (answers `web_copies: []`, `ui_packages: "none yet: design only"`), no components
  inside an app (reference starters only), an HTML prototype only. Skip B.

## A. The product first

Read `README*`, `AGENTS.md`/`CLAUDE.md`, `SLATE.md`, `docs/`, and any brief, prototype or brand files. Ask A1–A6 from
interview.md (up to four together), with suggestions drawn from them; brand colours or fonts found in the code are
offered as suggestions. **OK?** Summarise A in five lines and ask "Right?"; correct until it is.

## B. Platforms and stack

Web, iOS (SwiftUI), Android (Compose), multi-select. The detected framework and styling (Tailwind v4, Tailwind v3,
plain CSS; shadcn when present) are suggestions: **OK?** confirm or correct. React Native is not supported in 1.0.0
(a 1.1.0 candidate): offer design only, web, iOS or Android; never write React Native components.

## C. Design decisions

C1–C16 from interview.md, **one question each**, each with options, the recommendation and why: personality and
register · density · accent · neutrals · semantic colours · label colours · type family and scale · spacing · radius ·
elevation · motion and reduced motion · icons · dark mode · accessibility target (WCAG 2.2 AA by default) · vocabulary
and voice · UX patterns (navigation, page anatomy, forms, feedback, empty/loading/error states, destructive actions,
onboarding: one sub-question each). Show colours as hex with their dark value. **OK?** Show every decision on one
screen and ask to continue.

## D. Directions

**OK?** "I'll write the directions page to `<root>/docs/design/directions.html`" (a) Write it (Recommended)
(b) Another path. Then write 2–3 **distinct, finished-looking** directions: palette, type, components and one real
screen of a key task, each in light and dark. When the Effective HTML skills
(`design-artifact`, `html`, `html-prototype`) are available in this session, follow them; otherwise use Plumb's
built-in quality bar: start from `ROOT/templates/directions.html` and its rules, and
[prototypes.md](../../reference/prototypes.md#the-quality-bar-effective-html) "The quality bar". Effective HTML is
optional; never install it. Nothing from the network. **OK?** pick one · combine (which parts) ·
change something.

## E. Generate (each checkpoint waits for the user)

1. **OK? The full token set.** Show every value that will be written: colours light and dark (contrast is measured
   right after the build, in E5), type family and scale, spacing, radius, shadows, motion, labels; point at the chosen direction in
   `directions.html` as the preview. Change what the user asks; continue only on their OK.
2. **OK? The files.** Write the answers JSON (keys in interview.md, including the confirmed placement: `ui_packages`,
   `ui_files`, `allowed_raw`, `web_copies`, `python`, `role`) to a file in the system temp folder (deleted after the scaffold). Run
   `python3 "<ROOT>/scripts/scaffold.py" --project-root "<root>" --name "<Name>" --skill-dir <skill dir>
   --platforms <list> --styling <mode> --answers <file> --docs-dir docs/design --dry-run`, show its **full** list of
   files and paths, and run it without `--dry-run` only on the user's OK.
3. Add what the scaffold has no key for to the tokens file (warning, info, `label.*`, `md` values, sizes), exactly as
   approved in E1 (tokens-format.md). Write `design.md`, `references/ux.md`, `vocabulary.md`, `motion.md`,
   `accessibility.md` from the answers, replacing every "to fill" prompt.
4. `python3 "<root>/<skill dir>/scripts/build-tokens.py"` writes the themes, the copies, the contrast block and
   `docs/design/specimen.html`.
5. **OK? Each contrast fix.** `python3 "<root>/<skill dir>/scripts/audit.py" --json`; for each `contrast` error show
   the failing pair, its ratio (light or dark) and the proposed passing value; apply each only on the user's OK,
   rebuild, repeat until none is left.
6. **OK? The components.** Propose which starter components (button, input, select, checkbox, card, chip/badge,
   dialog, sheet, menu, tabs, toast, tooltip, empty state, error state, skeleton, page header, app shell), the
   framework and primitives (shadcn/Radix on React when the project has them, native controls on SwiftUI and
   Compose), and the paths (app exists → e.g. `components/ui/`; no app or design only →
   `<skill dir>/assets/platforms/<platform>/starter/`). On OK **you write them** from `references/components.md`,
   tokens only, never adding a dependency (a missing primitive → ask the user and wait). Update `references/inventory.md`.
7. **The design system must pass:** `python3 "<root>/<skill dir>/scripts/audit.py" "<root>/<folder of each component
   you wrote>"` (e.g. `"<root>/components/ui"` or the `starter/` folder) exits 0. Contrast, missing dark values and
   generated-file drift are cross-file rules: they run with these PATHS too. A "no prototype yet" warning is expected
   until F. `build-tokens.py --check` exits 0. Give the path of `docs/design/specimen.html`.

## G. Record (before F, so the prototype's "Why it looks like this" panels show the decisions)

Append one entry per decision (direction, each C decision, contrast fixes) to `<root>/docs/design/decisions.md`, in
the format of `ROOT/templates/decision-entry.md`: id `DS-YYYYMMDD-<slug>` (today's date, a short slug), date, **who
decided** (`git config user.name`; without git, ask the user's name), the options considered with links
(`directions.html#d2`), the one chosen and why in the user's words, the screens affected (`all` for tokens), the Slate
ticket if any. Append only: never edit or reorder earlier entries. Mirror each entry into `docs/decisions.md` when the
project keeps one, and add a line to `design.md`'s revision notes.

## F. Prototypes of the key screens

**OK?** "Prototype the key screens now? Each comes as 2–3 variants to choose from, and the chosen ones become the main
prototype (`docs/design/prototype.html` + `screens.html`)." (a) Yes, the key screens from A4 (Recommended) (b) pick
which (c) later with `/plumb:prototype`. On yes, follow `ROOT/skills/prototype/SKILL.md` for each screen or flow, one
at a time; it records its own decisions.

## Finish

- Routed from init: return to `/plumb:init` step 4. Run directly: do init's step 4 now (each item asked).
- Summary: the design-system folder, `PLUMB.md`, `docs/design/` (directions, specimen, decisions, prototype), the
  audit result, and `git -C "<root>" status --short`. Suggest committing.

## Checklist

- [ ] Product questions came before design questions; every question offered a recommendation and why
- [ ] The user approved the token set, the scaffold's file list, each contrast fix and the component plan
- [ ] Tokens have a dark value for every colour (or a recorded light-only decision)
- [ ] Components written by you from `components.md`; the audit on them exits 0; `build-tokens.py --check` exits 0
- [ ] Every decision is in `docs/design/decisions.md` with who decided; nothing written outside `<root>`, nothing
      installed or downloaded
