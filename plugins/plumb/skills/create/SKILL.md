---
name: create
description: Create a new design system for this project - the product interview first, then platforms and stack, then each design decision with a recommendation (including UX patterns and dark mode), 2-3 directions on one page, then, after the user approves the token set and the file list, generate the tokens, themes, contrast evidence, skill files and starter components (audit must pass), offer prototypes of the key screens, and record every decision in docs/design/decisions.md.
argument-hint: "[product name]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/detect.py*), Bash(python *scripts/detect.py*), Bash(py -3 *scripts/detect.py*), Bash(python3 *scripts/scaffold.py*), Bash(python *scripts/scaffold.py*), Bash(py -3 *scripts/scaffold.py*), Bash(python3 *scripts/build-tokens.py*), Bash(python *scripts/build-tokens.py*), Bash(py -3 *scripts/build-tokens.py*), Bash(python3 *scripts/audit.py*), Bash(python *scripts/audit.py*), Bash(py -3 *scripts/audit.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git -C * status --short)
---

# /plumb:create — from an idea to a design system

Only run when the user typed `/plumb:create` (or `/plumb:init` routed here). Other skills offer it, never run it.
These instructions are already loaded: don't load this skill again with a skill tool.

```
0 roots ─▶ 1 placement ─▶ 2 product ─▶ 3 "Right?" ─▶ 4 platforms ─▶ 5 decisions, one each ─▶ 6 all decisions
 ─▶ 7 directions page ─▶ 8 pick ─▶ 9 token set ─▶ 10 file list ─▶ scaffold --confirm ─▶ 11 stylesheet diff ─▶ build
 ─▶ 12 theme variables ─▶ 13 each contrast fix ─▶ 14 components ─▶ audit 0 ─▶ 15 record ─▶ 16 prototypes
 ─▶ 17 wire in (init step 4) ─▶ final checklist ─▶ .plumb-tmp/ removed ─▶ summary
```

**Rules.**
- **Nothing is written without the user's OK.** Steps 1–16 are checkpoints, each ending **STOP: ask, wait for the
  answer**: call the question tool and do nothing else until the user answers. Never skip one, merge two into one
  question, or run a checkpoint's action in the same shell call as the next one. A checkpoint that does not apply
  (no existing stylesheet, no `block-override`, no contrast error, design only): say which and why. A permission prompt
  from your tool (Copilot CLI asks before commands) is never the user's OK to a checkpoint.
- **What the user confirms goes inside the question**, in full: the question text, or the recommended option's preview
  when the tool has one (Claude Code's `AskUserQuestion`). Never only in a message before the question (Claude Code can
  hide it), never "the list above"; Copilot CLI's ask tool: in the question text ([interview.md](../../reference/interview.md), "How to ask").
- **Scripts give evidence, not answers:** check every script result against the code, correct or add to it (marked
  `(corrected: <why>)` / `(added: <why>)`), show that inside the question. **Investigate first:** gather every fact
  the code can answer before asking (interview.md); only what the code cannot tell is a question.
- **One at a time** (part A may group up to four), the recommendation first marked "(Recommended)" and **why**. Light
  **and** dark by default. **Never install or download anything**; if something seems needed, **ask the user and wait**.
- Pre-approved commands: the `allowed-tools` above; anything else asks first. Copilot CLI asks for every command: run a
  checkpoint's script calls in one shell call joined with `&&` (Windows PowerShell 5.1 has no `&&`: join with `;`, or
  run them one by one); the prompts to expect: [copilot.md](../../reference/copilot.md).
- **Never run `--approve` (or record an approval) without the user's explicit yes to that screen** in this
  conversation. `audit.py`: **exit 1 means errors found, not a crash**. **End-of-turn check:** if it stops you after
  the user said not to fix now, don't fix: report and stop.

## 0. Roots, first

- **Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
  If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
  `<plugin>/skills/create`) + `/../..`, resolved to an absolute path. Check that `<ROOT>/reference/interview.md` exists;
  if not, resolve again, never guess. Plumb's references only as `<ROOT>/reference/<file>`; tokens format:
  [tokens-format.md](../../reference/tokens-format.md); placement: [placement.md](../../reference/placement.md).
- **Project root (`<root>`):** the absolute root confirmed in `/plumb:init`. Every path is `<root>/…`, every command
  names it (`--project-root "<root>"`), never `.`; nothing is written outside `<root>`. Scratch: `<root>/.plumb-tmp/`
  only (interview.md, "Scratch files"), never `/tmp` or next to the repo.

## 1. Placement — STOP

Routed from `/plumb:init`: use its placement (UI files, routes), `<root>` and Python. Run directly: an existing system →
stop, offer `/plumb:update`; else do `/plumb:init` steps 0–1 (`ROOT/skills/init/SKILL.md`): the placement question
holds the whole block. **STOP: ask, wait for the answer.** Then write `<root>/.plumb-tmp/.gitignore` (`*`) and the
marker `<root>/.plumb-tmp/setup-in-progress`; say so in one line. **Design only:** `web`, `css`, `web_copies: []`,
`routes: none`, reference starters, an HTML prototype; step 4 does not apply.

## 2. The product — STOP

Investigate first (`README*`, `AGENTS.md`/`CLAUDE.md`, `SLATE.md`, `docs/`, briefs, prototypes, brand files). Ask
A1–A4 in one call, then A5–A6 (interview.md A), with suggestions drawn from them. **STOP: ask, wait for the answer.**

## 3. "Right?" — STOP

The five-line summary of A **inside the question**: "Right?" (a) Right (Recommended) (b) Change something. Repeat until
it is right. **STOP: ask, wait for the answer.**

## 4. Platforms and stack — STOP

Web, iOS (SwiftUI), Android (Compose), multi-select; the framework and styling found (`found: Tailwind v4
(app/globals.css:1)`) recommended (interview.md B). React Native is not supported in 1.0.0: offer design only, web,
iOS or Android, never React Native components. **STOP: ask, wait for the answer.**

## 5. Design decisions, one each — STOP after each

C1–C16 from interview.md C, **one question each**, the recommendation and why; colours as hex with their dark value.
C11: motion, then reduced motion as its own question. C13: dark mode, then how the app switches as its own question
(`both` · `system` · `class` · `data-theme`), recommended only from interview.md "Theme switch" (first matching row;
the evidence `file:line` inside the question). Tailwind: the default palette (interview.md): no UI code yet → reset
(Recommended); an app already using palette classes → keep; record `reset_palette`. C16 is **seven** questions: ask
all seven, or say which you skip and why. Keep fades in plain CSS → name `motion-fade` in one line. **STOP after each
question: ask, wait for the answer.**

## 6. Every decision — STOP

Every decision on one screen **inside the question**: "Generate directions from these?" (a) Yes (Recommended)
(b) Change one. **STOP: ask, wait for the answer.**

## 7. Directions page — STOP

"I'll write the directions page to `<root>/docs/design/directions.html`" (a) Write it (Recommended) (b) Another path.
**STOP: ask, wait for the answer.** Then write 2–3 **distinct, finished-looking** directions (interview.md D), with
Effective HTML (`design-artifact`, `html`, `html-prototype`) when available (optional; never install it), else Plumb's
built-in quality bar ([prototypes.md](../../reference/prototypes.md)). **The project's design system outranks
Effective HTML:** it guides craft only; where they disagree the system wins. The directions page is the one exception
(each direction is a candidate system); from 9 on the system wins.

## 8. Pick a direction — STOP

Inside the question: the page's path and each direction's name and idea; pick one (recommend one and why) · combine
(which parts) · change something. **STOP: ask, wait for the answer.** No direction picked → no step 9.

## 9. The full token set — STOP

Inside the question, every value to be written: colours light and dark (contrast is measured in 13), type family and
scale, spacing, radius, shadows, motion, labels, and `theme_switch`, `reduced_motion`, `reset_palette`; the chosen
direction as the preview. (a) OK (Recommended) (b) Change something. **STOP: ask, wait for the answer.**

## 10. The file list — STOP, then the scaffold with `--confirm`

Write the answers (interview.md "The answers file": the confirmed `ui_packages`, `ui_files`, `routes`, `allowed_raw`,
`web_copies`, `python`, `role`, and `theme_switch` / `reduced_motion` / `reset_palette`) to
`<root>/.plumb-tmp/answers.json`, then `python3 "<ROOT>/scripts/scaffold.py" --project-root "<root>" --name "<Name>"
--skill-dir <skill dir> --platforms <list> --styling <mode> --answers "<root>/.plumb-tmp/answers.json" --docs-dir
docs/design --dry-run`. Check the list (only the agreed paths), then its **full** output inside the question: "Write
these files?" (a) Write them (Recommended) (b) Change something. **STOP: ask, wait for the answer.** Only on yes, in a
new shell call: the same command without `--dry-run`, plus `--confirm <token>` exactly as the dry run printed it.
Never run the real scaffold without a dry run the user OK'd; a changed answer → a new dry run, a new question.

## 11. Fill in, then the existing stylesheet — STOP

Fill in the tokens and documents (interview.md "E. Generate, in detail"; the settings `motion.reduced`,
`web.theme_switch`, Tailwind's `web.reset_palette`). When a web copy is an existing file (e.g. `app/globals.css`),
`build-tokens.py --check` prints the diff: inside the question the diff (a long one as interview.md "How to ask" says)
and what it means: Plumb adds a marked `plumb:start … plumb:end` block and owns only it; the rest stays the project's;
with `reset_palette: true` Tailwind's default colour classes stop working. **STOP: ask, wait for the answer.** Build
only on yes: `python3 "<root>/<skill dir>/scripts/build-tokens.py" && python3 "<root>/<skill dir>/scripts/audit.py"
--json` in one shell call (themes, copies, contrast block, `docs/design/specimen.html`, the findings).

## 12. The project's own theme variables — STOP

When the findings include `block-override`: run `build-tokens.py --overrides`, verify each mapping, put the table
(corrections marked) inside the question (interview.md "E. Generate, in detail"): move them into the tokens
(Recommended) · leave them for now. **STOP: ask, wait for the answer.** Only on yes:
`build-tokens.py --overrides --apply && build-tokens.py && audit.py --json`; the `used_in` files change only when
asked. What the audit still reports is the app's own code: say so, offer `/plumb:audit fix`.

## 13. Each contrast fix — STOP per fix

Per `contrast` error, inside the question: the failing pair, its ratio (light or dark), the proposed passing value.
**STOP per fix: ask, wait for the answer.** Apply only on OK, rebuild, repeat until none is left.

## 14. Components — STOP

Inside the question: which starter components, the framework and primitives, the paths (interview.md). **STOP: ask,
wait for the answer.** On OK **you write them** from `references/components.md`, tokens only, no new dependency;
update `references/inventory.md`. Then `python3 "<root>/<skill dir>/scripts/audit.py" "<root>/<folder of each
component you wrote>" && python3 "<root>/<skill dir>/scripts/build-tokens.py" --check` in one call: both exit 0 ("no
prototype yet" is expected until 16). Give the path of `docs/design/specimen.html`.

## 15. Record the decisions

Before 16 (its "Why it looks like this" panels show them): one entry per decision appended to
`<root>/docs/design/decisions.md` (`ROOT/templates/decision-entry.md`; interview.md "Record (G)").

## 16. Prototypes of the key screens — STOP

"Prototype the key screens now (2–3 variants each)?" (a) Yes, the key screens from A4 (Recommended) (b) Pick which
(c) Later with `/plumb:prototype`. **STOP: ask, wait for the answer.** On yes, follow `ROOT/skills/prototype/SKILL.md`.

## 17. Wire in, then finish

Routed from init: return to `/plumb:init` step 4 now (init walks this checklist at its end). Run directly: do init's
step 4, then walk the checklist. Never skip it: every item is asked, also when `AGENTS.md` or a `Makefile` is missing.

## Final checklist — walk it before you say done

Check each line yourself; one that does not hold is not done: go back to its checkpoint (asked).

- [ ] Every checkpoint that applied (1–16) was asked and answered, its content inside the question; any not
      applicable: say which and why
- [ ] A direction was picked (8); the token set (9), the dry-run list (10), the stylesheet diff (11) and the mapping
      (12) were OK'd where they applied; the real scaffold ran with `--confirm` from that dry run
- [ ] Contrast evidence: `references/dark-mode.md` holds the computed contrast block; no `contrast` error is left
- [ ] Components written by you; their audit and `build-tokens.py --check` exit 0; `docs/design/decisions.md` has an
      entry per decision with who decided
- [ ] A first prototype screen exists in `docs/design/prototype/screens/`, or the user chose "later" in 16
- [ ] `motion.reduced`, `web.theme_switch` (Tailwind: `web.reset_palette`) are in the tokens file; nothing written
      outside `<root>`, nothing installed or downloaded
- [ ] Init step 4 was asked item by item; then remove the whole `<root>/.plumb-tmp/` (marker included), last

Then the summary (the skill folder, `PLUMB.md`, `docs/design/`, the audit, `git -C "<root>" status --short`); suggest committing.
