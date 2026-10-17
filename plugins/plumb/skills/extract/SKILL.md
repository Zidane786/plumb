---
name: extract
description: Extract the design system an existing app already has - inventory every colour, font, size, spacing, radius, shadow, duration and easing in use (counts and file:line), cluster near-duplicates into a clean token set shown as a before/after page, confirm it group by group, ask the product and UX questions the code cannot answer, generate the design system after the user approves the files, build the main prototype from the existing routes, and audit what does not match yet (with Slate tickets on offer).
argument-hint: "[UI folders]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/detect.py*), Bash(python *scripts/detect.py*), Bash(py -3 *scripts/detect.py*), Bash(python3 *scripts/scaffold.py*), Bash(python *scripts/scaffold.py*), Bash(py -3 *scripts/scaffold.py*), Bash(python3 *scripts/build-tokens.py*), Bash(python *scripts/build-tokens.py*), Bash(py -3 *scripts/build-tokens.py*), Bash(python3 *scripts/audit.py*), Bash(python *scripts/audit.py*), Bash(py -3 *scripts/audit.py*), Bash(python3 *scripts/build-prototype.py*), Bash(python *scripts/build-prototype.py*), Bash(py -3 *scripts/build-prototype.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git -C * status --short)
---

# /plumb:extract — the system you already ship, cleaned up

Only run when the user typed `/plumb:extract` (or `/plumb:init` routed here). Other skills offer it, never run it.
These instructions are already loaded: don't load this skill again with a skill tool.

```
0 roots ─▶ 1 placement ─▶ 2 UI folders ─▶ inventory ─▶ 3 page path ─▶ 4 each group ─▶ 5 questions the code can't answer
 ─▶ 6 theme switch ─▶ 7 reduced motion ─▶ 8 palette ─▶ 9 "Right?" ─▶ 10 token set ─▶ 11 file list ─▶ scaffold --confirm
 ─▶ 12 stylesheet diff ─▶ build ─▶ 13 theme variables ─▶ 14 each contrast fix ─▶ 15 components ─▶ record
 ─▶ 16 screens ─▶ 17 screen files ─▶ map ─▶ 18 each screen approved? ─▶ audit report ─▶ wire in ─▶ final checklist
```

**Rules.**
- **Nothing is written without the user's OK.** Steps 1–18 are checkpoints, each ending **STOP: ask, wait for the
  answer**: call the question tool and do nothing else until the user answers. Never skip one, merge two into one
  question, or run a checkpoint's action in the same shell call as the next one. A checkpoint that does not apply
  (no existing stylesheet, no `block-override`, no contrast error, design only): say which and why. A permission prompt
  from your tool (Copilot CLI asks before commands) is never the user's OK to a checkpoint.
- **What the user confirms goes inside the question**, in full: the question text, or the recommended option's preview
  when the tool has one (Claude Code's `AskUserQuestion`). Never only in a message before the question (Claude Code can
  hide it), never "the list above"; Copilot CLI's ask tool: in the question text ([interview.md](../../reference/interview.md), "How to ask").
- **Scripts give evidence, not answers:** check every script result (inventory, clusters, overrides, audit, route map)
  against the code, correct or add to it (marked `(corrected: <why>)` / `(added: <why>)`), show that inside the
  question. When a Plumb script or hook is wrong and you correct it, record the Plumb mistake with /plumb:feedback.
  **Investigate first** (interview.md): what the code shows is a `found: … (file:line)` to confirm.
- Questions go **one at a time**, the recommendation first marked "(Recommended)" and why. Light **and** dark by
  default. **Never install or download anything**; if something seems needed, **ask the user and wait**. App code
  changes only with the user's OK; the audit report (step 19) reports, it does not fix.
- Pre-approved commands: the `allowed-tools` above; anything else asks first. Copilot CLI asks for every command: run a
  checkpoint's script calls in one shell call joined with `&&` (Windows PowerShell 5.1 has no `&&`: join with `;`, or
  run them one by one); the prompts to expect: [copilot.md](../../reference/copilot.md).
- **Never run `--approve` (or record an approval) without the user's explicit yes to that screen** in this
  conversation. `audit.py`: **exit 1 means errors found, not a crash**. **End-of-turn check:** if it stops you after
  the user said not to fix now, report and stop.

## 0. Roots, first

- **Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
  If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
  `<plugin>/skills/extract`) + `/../..`, resolved to an absolute path. Check that `<ROOT>/reference/interview.md`
  exists; if not, resolve again, never guess. Plumb's references only as `<ROOT>/reference/<file>`; tokens format:
  [tokens-format.md](../../reference/tokens-format.md); placement: [placement.md](../../reference/placement.md).
- **Project root (`<root>`):** the absolute root confirmed in `/plumb:init`. Every path is `<root>/…`, every command
  names it, never `.`; nothing is written outside `<root>`. Scratch (inventory or overrides JSON, a saved diff, the
  answers): `<root>/.plumb-tmp/` only (interview.md, "Scratch files"), never `/tmp` or next to the repo.

## 1. Placement — STOP

Routed from `/plumb:init`: use its confirmed placement (UI files, routes) and `<root>`. Run directly: an existing design
system → stop, offer `/plumb:update`; else do `/plumb:init` steps 0–1 (`ROOT/skills/init/SKILL.md`): the placement
question holds the whole block. **STOP: ask, wait for the answer.** Then write `<root>/.plumb-tmp/.gitignore` (`*`) and
the marker `<root>/.plumb-tmp/setup-in-progress` (rewrite it at every checkpoint); say so in one line. **Design
only** (React Native, or the user's choice): `web`, `css`, no web copies, no components in the app, `routes: none`,
an HTML prototype only.

## 2. The UI folders — STOP, then the inventory

Inside the question: the UI folders found (each with its file count) and anything to leave out (vendored, legacy,
marketing). **STOP: ask, wait for the answer.** Then (read-only): `python3 "<ROOT>/assets/skill/scripts/audit.py"
"<root>/<UI folder>"… --inventory --json --project "<root>" [--exclude "legacy/**"]`: per kind (colour, font family, size,
weight, line height, spacing, radius, shadow, duration, easing) every value with its count and `file:line`, and proposed
clusters (colours below CIEDE2000 3 per source: CSS variable, palette class, literal; sizes within 1px or 6%; same hex, two
sources: two groups, one candidate). Check its `checked` count against the folders; read what it does not interpret (the
sources in interview.md "Investigate first": Tailwind `theme.extend`, CSS variables, theme objects, asset catalogs,
`themes.xml`) and list the **component variants** in use. Name tokens **by role** (`primary`, `on-surface-muted`, `danger`),
never by hue; spacing onto Tailwind steps, sizes onto the type scale. Existing dark values become `$extensions.plumb.dark`;
others get a proposed one. Split a cluster merging values with different jobs `(corrected: …)`.

## 3. The before/after page — STOP

"I'll write the proposal page to `<root>/docs/design/extract.html`" (a) Write it (Recommended) (b) Another path.
**STOP: ask, wait for the answer.** One self-contained page, light and dark, nothing from the network, with Effective
HTML's `design-artifact` when available (optional; never install it), else Plumb's built-in quality bar
([prototypes.md](../../reference/prototypes.md)). **The project's design system outranks Effective HTML:** it guides
craft only; the look is the project's (before the tokens exist, the app's own values), and where they disagree the
system wins. Per group: **before** (each value, swatch, count, a few `file:line`) and **after** (the token, light/dark).

## 4. Each group — STOP per group

Inside the question: the group's before → after (values, counts, the token and its light/dark value, corrections
marked). Accept (Recommended) · rename · merge with another · split · leave out. After three groups also offer
"Accept all remaining groups as proposed". **STOP: ask, wait for the answer.** Never merge values the user wants apart.

## 5. What the code cannot answer — STOP per question

Only what the evidence table leaves open: the product (A1–A6), dark mode when the app has none (C13), the
accessibility target (C14), vocabulary and voice (C15; the i18n files are evidence), the UX patterns (C16: seven; say
which you skip and why). What the code shows is the recommendation ("found: a left sidebar (`app/layout.tsx:20`): keep
it?"). **STOP after each: ask, wait for the answer.**

## 6–8. Theme switch, reduced motion, palette — STOP after each

Always ask these, one at a time, recommending what the app already does so extract keeps it:
- **6. How the app switches themes** (`theme_switch`): only interview.md "Theme switch" decides the recommendation
  (first matching row; next-themes `attribute="class"` → `class`), with the evidence `file:line` inside the question.
- **7. Reduced motion** (`reduced_motion`): an existing `prefers-reduced-motion` rule that keeps opacity transitions →
  `keep-fades`; one that turns every animation off → `none`; none yet → `keep-fades`. Keep fades in plain CSS → say in
  one line: add the class `motion-fade` to each element whose own transition is only a fade.
- **8. Tailwind's default palette** (`reset_palette`, Tailwind only): recommend keep (`false`) and explain inside the
  question, with the count of palette classes the app uses: a reset (all six namespaces: colours, radii, shadows, text
  sizes, fonts, easings) makes each colourless at the first build; keep leaves them working, the audit suggests moving
  them onto tokens and still flags off-scale defaults like `text-lg`; `/plumb:update` can switch the reset on later.

They become `$extensions.plumb.web.theme_switch`, `$extensions.plumb.motion.reduced` and
`$extensions.plumb.web.reset_palette` (answers keys, step 11). **STOP after each: ask, wait for the answer.**

## 9. "Right?" — STOP

The five-line summary (product, users, key tasks, voice, the settings) **inside the question**: "Right?" **STOP: ask,
wait for the answer.**

## 10–15. Generate (as create 9–14) — STOP at each

Follow `/plumb:create` checkpoints 9–14 (`ROOT/skills/create/SKILL.md`), the content inside each question; the
confirmed groups are the answers; **no directions step**. **STOP at each: ask, wait for the answer.**
- **10. The full token set.** **11. The file list:** the dry run's full list (a `git-ignored` warning → ask as init
  step 1.5); the real scaffold only with `--confirm <token>` from that dry run, in a new shell call.
- **12. The existing stylesheet** (e.g. `app/globals.css`: Plumb owns only its marked block), when it applies.
- **13. The app's own theme variables** (`build-tokens.py --overrides`: the inventoried values are tokens now, so they
  move into them): the verified mapping, each "the look changes" note on its own line with both values; errors left
  after `--apply` are the app's own (step 19, `/plumb:audit fix`).
- **14. Each contrast fix.** **15. Components:** they exist: map them to `references/components.md` and
  `inventory.md`; propose only the missing starters; change existing ones only with the user's OK. `audit.py
  "<root>/<folder of each component you wrote>"` exits 0; the rest of the app is step 19.
Then record (create 15): entries link `extract.html`.

## 16. The screens to prototype — STOP

**Find the screens yourself** under the recorded `Routes:` roots, each `<path> (<kind>)` (where each stack keeps its
pages: interview.md "What gets recorded"; `none` → native or plain screens, still found from the code). Inside the
question: route → screen id → source files (each checked on disk), all included (Recommended) or pick. **STOP: ask,
wait for the answer.**

## 17. The screen files — STOP, then map

Inside the question: the `docs/design/prototype/screens/<id>.html` files to write. **STOP: ask, wait for the answer.**
Write each from the real code (the contract at the top of `<skill dir>/scripts/build-prototype.py`: real copy, the
code's states as `data-state` blocks, interactions inline, tokens only, light and dark). Then map and mark every screen
in one shell call, the route as one argument (`--route=/`, so Copilot doesn't read `/` as a path):
`python3 "<root>/<skill dir>/scripts/build-prototype.py" --map <id> --route=<route> --files <globs> && … --synced <id>`.
Synced from code means waiting for the user; **never chain `--approve` after `--synced`**. `audit.py --json` reports a
route without a screen as `route-not-prototyped`: add those (asked). `build-prototype.py --check` exits 0.

## 18. Each screen approved? — STOP per screen

Give the paths of `docs/design/prototype.html` (to review), `app.html` (to demo) and `screens.html`, then per screen: "Approve <screen> as the reference
to build?" Approve (Recommended when it matches the app) · leave it synced for later · change something. **STOP: ask,
wait for the answer.** Only on an explicit approve: `build-prototype.py --approve <id>`.

## 19. Audit what does not match yet

`python3 "<root>/<skill dir>/scripts/audit.py" --html` writes `docs/design/audit-YYYY-MM-DD.html` (exit 1 = errors
found). Read the findings critically (a burst of one rule after setup is a setup gap: fix it, asked), summarise by area,
offer `/plumb:audit fix`. Only when `<root>/kanban/board.py` exists, also offer Slate tickets by area, created only
through Slate's `board.py` (never edit `kanban/`); otherwise never mention Slate.

## 20. Wire in, then finish

Routed from init: return to `/plumb:init` step 4 now (init walks this checklist at its end). Run directly: do init's
step 4, then walk the checklist. Never skip it: every item is asked, also when `AGENTS.md` or a `Makefile` is missing.

## Final checklist — walk it before you say done

Check each line yourself; one that does not hold is not done: go back to its checkpoint (asked).

- [ ] Every checkpoint that applied (1–18) was asked and answered, its content inside the question; any not
      applicable: say which and why; the inventory came from `audit.py --inventory`; every group was confirmed
- [ ] The token set, the dry-run list, the stylesheet diff and the mapping were OK'd where they applied; the real
      scaffold ran with `--confirm`; `theme_switch`, `motion.reduced` (Tailwind: `reset_palette`) are in the tokens
- [ ] Contrast evidence in `references/dark-mode.md`, no `contrast` error left; every colour has a dark value;
      `build-tokens.py --check` exits 0; components mapped, the audit on what you wrote exits 0
- [ ] `docs/design/decisions.md` has an entry per decision with who decided
- [ ] Every confirmed route has a screen file, mapped and synced, approved only on an explicit yes; `--check` exits 0
- [ ] Init step 4 was asked item by item; then remove the whole `<root>/.plumb-tmp/` (marker included), last
- [ ] Nothing written outside `<root>`; app code changed only with the user's OK; nothing installed or downloaded

Then the summary: values → tokens, the files written, the prototype, the audit counts, `git -C "<root>" status --short`.
