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
- **Nothing is written without the user's OK.** Steps 1–18 are checkpoints. Each ends **STOP: ask, wait for the
  answer**: call the question tool and do nothing else until the user answers. Never skip one, merge two into one
  question, or run a checkpoint's action in the same shell call as the next one. A permission prompt from your tool
  (Copilot CLI asks before commands) is never the user's OK to a checkpoint.
- **What the user confirms goes inside the question:** a group's before/after, the summary, token set, file list,
  diff or mapping is the question text (or the recommended option's preview, when the question tool has one, as
  Claude Code's `AskUserQuestion` does), in full. Never only in a message before the question (Claude Code can hide
  it), never "the list above". Copilot CLI's ask tool: in the question text. ([interview.md](../../reference/interview.md), "How to ask".)
- **Scripts give evidence, not answers:** check every script result (inventory, clusters, overrides, audit, route map)
  against the code, correct or add to it (marked `(corrected: <why>)` / `(added: <why>)`) and show that inside the
  question. **Investigate first:** gather every fact the code can answer before asking (interview.md, "Investigate
  first"); what the code shows is a `found: … (file:line)` to confirm, never an open question.
- Questions go **one at a time**, options with the recommendation first marked "(Recommended)" and why. Light **and**
  dark by default. **Never install or download anything**; if something seems needed, say so, **ask the user and
  wait**. App code changes only with the user's OK; the audit report (step 19) reports, it does not fix.
- Pre-approved commands (`allowed-tools`): Plumb's `detect.py`, `scaffold.py`, `build-tokens.py`, `audit.py`,
  `build-prototype.py`, and the read-only git calls; anything else asks first. Copilot CLI asks for every command: run a
  checkpoint's script calls in one shell call joined with `&&` (Windows PowerShell 5.1 has no `&&`: join with `;`
  there, or run them one by one); the prompts to expect: [copilot.md](../../reference/copilot.md).
- **Never run `--approve` (or record an approval) without the user's explicit yes to that screen** in this
  conversation. `audit.py`: **exit 1 means errors found, not a crash**; read the findings. **End-of-turn check:** if it
  stops you after the user said not to fix now, report and stop.

## 0. Roots, first

- **Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
  If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
  `<plugin>/skills/extract`) + `/../..`, resolved to an absolute path. Check that `<ROOT>/reference/interview.md`
  exists; if not, resolve again, never guess. Read Plumb's references only as `<ROOT>/reference/<file>`. Tokens format:
  [tokens-format.md](../../reference/tokens-format.md); placement: [placement.md](../../reference/placement.md).
- **Project root (`<root>`):** the absolute root the user confirmed in `/plumb:init`. Every path is `<root>/…`, every
  command names it, never `.`; nothing is written outside `<root>`.
- **Scratch:** `<root>/.plumb-tmp/` only (inventory or overrides JSON you keep, a saved diff, the answers JSON;
  interview.md "Scratch files"): never `/tmp`, never next to the repo.

## 1. Placement — STOP

Routed from `/plumb:init`: use its confirmed placement (UI files and routes as recorded) and `<root>`. Run directly: if
a design system already exists, stop and offer `/plumb:update`; otherwise do `/plumb:init` steps 0–1 first
(`ROOT/skills/init/SKILL.md`): the placement question holds the whole block. **STOP: ask, wait for the answer.** Then
create `<root>/.plumb-tmp/` with its `.gitignore` (`*`), say so in one line (it stays until setup ends). **Design only**
(a React Native app, or the user's choice): platforms `web`, styling `css`, no web copies, no components inside the app
(never React Native components), an HTML prototype only.

## 2. The UI folders — STOP, then the inventory

Inside the question: the UI folders found (each with its file count) and anything to leave out (vendored, legacy,
marketing). **STOP: ask, wait for the answer.** Then run the plugin's own audit script (it only reads):
`python3 "<ROOT>/assets/skill/scripts/audit.py" "<root>/<UI folder>"… --inventory --json --project "<root>"
[--exclude "legacy/**"]`. It returns, per kind (colour, font family, size, weight, line height, spacing, radius, shadow,
duration, easing), every value with its count and `file:line`, plus proposed clusters (colours below CIEDE2000 3,
sizes within 1px or 6%; the most-used value is the proposed token). Check its `checked` count against the files in
those folders. Then read what it does not interpret (Tailwind config `theme.extend`, CSS variables, `Color`/`Theme`
files) and list the **component variants** in use. Name each proposed token **by role** (`primary`,
`on-surface-muted`, `danger`), never by hue; spacing onto Tailwind steps (`"2": "8px"`), font sizes onto the type scale
names. Existing dark values (a `.dark` block, `prefers-color-scheme`, `dark:` classes) become
`$extensions.plumb.dark`; colours with none get a proposed dark value. Split a cluster that merges values with
different jobs `(corrected: …)`.

## 3. The before/after page — STOP

"I'll write the proposal page to `<root>/docs/design/extract.html`" (a) Write it (Recommended) (b) Another path.
**STOP: ask, wait for the answer.** Then write it: one self-contained page, light and dark, nothing from the network,
with Effective HTML's `design-artifact` when available (optional; never install it), otherwise Plumb's built-in quality
bar in [prototypes.md](../../reference/prototypes.md). **The project's design system outranks Effective HTML:**
Effective HTML guides craft only (content, states, interactions, accessibility, polish); the look comes from the
project (before the tokens exist, the app's own values), and where they disagree the system wins. Per group:
**before** (every value with swatch, count, a few `file:line`) and **after** (the token, its light and dark value,
what merges into it).

## 4. Each group — STOP per group

Inside the question: the group's before → after (values, counts, the token and its light/dark value, corrections
marked). Accept (Recommended) · rename · merge with another · split · leave out. After three groups also offer
"Accept all remaining groups as proposed". **STOP: ask, wait for the answer.** Never merge values the user wants apart.

## 5. What the code cannot answer — STOP per question

Only what the evidence table leaves open: the product (A1–A6), dark mode when the app has none (C13), the
accessibility target (C14), vocabulary and voice (C15), and the UX patterns (C16: seven, ask each the screens don't
make clear and say which you skip and why). What the code shows is the recommendation ("found: a left sidebar
(`app/layout.tsx:20`): keep it?"). **STOP after each: ask, wait for the answer.**

## 6–8. Theme switch, reduced motion, palette — STOP after each

Always ask these, one at a time, recommending what the app already does so extract keeps it:
- **6. How the app switches themes** (`theme_switch`): only interview.md "Theme switch" decides the recommendation
  (first matching row; next-themes `attribute="class"` → `class`), with the evidence `file:line` inside the question.
- **7. Reduced motion** (`reduced_motion`): an existing `prefers-reduced-motion` rule that keeps opacity transitions →
  `keep-fades`; one that turns every animation off → `none`; none yet → `keep-fades`. On keep fades in a plain-CSS app,
  say in one line: add the class `motion-fade` to each element whose own transition is only a fade.
- **8. Tailwind's default palette** (`reset_palette`, Tailwind only): recommend **keep** (`false`) and explain inside
  the question, with the count of palette classes the app uses: a reset makes each colourless at the first build; the
  audit suggests moving them onto tokens, and `/plumb:update` can switch the reset on later (interview.md).

They become `$extensions.plumb.web.theme_switch`, `$extensions.plumb.motion.reduced` and
`$extensions.plumb.web.reset_palette` (answers keys, step 11). **STOP after each: ask, wait for the answer.**

## 9. "Right?" — STOP

The five-line summary (product, users, key tasks, voice, the settings) **inside the question**: "Right?" **STOP: ask,
wait for the answer.**

## 10–15. Generate (as create 9–15) — STOP at each

Follow `/plumb:create` checkpoints 9–15 (`ROOT/skills/create/SKILL.md`), each a STOP with its content inside the
question; the confirmed groups are the answers; **no directions step** (the look already exists):
- **10. The full token set** — STOP.
- **11. The file list:** the dry run's full list inside the question — STOP; the real scaffold only with
  `--confirm <token>` from that dry run.
- **12. The existing stylesheet** (e.g. `app/globals.css`: Plumb owns only its marked block): `--check`'s diff inside
  the question — STOP; never skipped.
- **13. The app's own theme variables** (`build-tokens.py --overrides`: the inventoried values are tokens now, so they
  move into them): the verified mapping inside the question — STOP; errors left after `--apply` are the app's own, for
  step 19 and `/plumb:audit fix`.
- **14. Each contrast fix** — STOP per fix.
- **15. Components:** they exist already: map them to `references/components.md` and `inventory.md`; propose only the
  missing starters, change existing components only with the user's OK — STOP. **The design system must pass:**
  `audit.py "<root>/<folder of each component you wrote>"` exits 0; the rest of the app is step 19.
Then record (create 15): entries link `extract.html`.

## 16. The screens to prototype — STOP

**Find the routes yourself** under the recorded `Routes:` roots: Next.js `app/**/page.*` (route groups `(x)` and
`@slots` are not in the URL; `_folders` are private) or `pages/**` (not `_app`, `_document`, `api/`); Nuxt
`pages/**/*.vue`; SvelteKit `src/routes/**/+page.svelte`; Angular `*.routes.ts` / `*routing.module.ts`; Vue Router
`router/index.*`; React Router `createBrowserRouter` / `<Route path>`; plain HTML pages; SwiftUI `NavigationStack` and
`TabView`; Compose `NavHost` `composable("…")`; React Native navigators. Inside the question: route → screen id → source
files (each checked on disk), all included (Recommended) or pick. **STOP: ask, wait for the answer.**

## 17. The screen files — STOP, then map

Inside the question: the `docs/design/prototype/screens/<id>.html` files to write. **STOP: ask, wait for the answer.**
Write each from the real code, following the screen-file contract at the top of `<skill dir>/scripts/build-prototype.py`:
real copy, the states the code handles as `data-state` blocks, the interactions inline, tokens only, light and dark.
Then map and mark every screen in one shell call, the route as one argument (`--route=/`, so Copilot doesn't read `/`
as a path): `python3 "<root>/<skill dir>/scripts/build-prototype.py" --map <id> --route=<route> --files <globs> && …
--synced <id>`. Synced from code means waiting for the user; **never chain `--approve` after `--synced`**. `audit.py
--json` reports a route still without a screen as `route-not-prototyped`: add the ones you missed (asked).
`build-prototype.py --check` exits 0.

## 18. Each screen approved? — STOP per screen

Give the paths of `docs/design/prototype.html` and `screens.html`, then per screen: "Approve <screen> as the reference
to build?" Approve (Recommended when it matches the app) · leave it synced for later · change something. **STOP: ask,
wait for the answer.** Only on an explicit approve: `build-prototype.py --approve <id>`.

## 19. Audit what does not match yet

`python3 "<root>/<skill dir>/scripts/audit.py" --html` writes `docs/design/audit-YYYY-MM-DD.html` (exit 1 = errors
found). Read the findings critically (a burst of one rule right after setup is a setup gap: fix the gap, asked), then
summarise by area and offer `/plumb:audit fix`. Only when `<root>/kanban/board.py` exists, also offer Slate tickets
by area, created only through Slate's `board.py` (never edit `kanban/`); otherwise never mention Slate.

## 20. Wire in, then finish

Routed from init: return to `/plumb:init` step 4 now (init walks this checklist at its end). Run directly: do init's
step 4 now, then walk the checklist. Never skip it: every item is asked, also when `AGENTS.md` or a `Makefile` is missing.

## Final checklist — walk it before you say done

Check each line yourself; a line that does not hold is not done: go back to its checkpoint (asked).

- [ ] Checkpoints 1–18 were each asked and answered, the content inside each question; the inventory came from
      `audit.py --inventory` and every group was confirmed
- [ ] The token set and the dry-run list were OK'd; the real scaffold ran with `--confirm` from that dry run
- [ ] The stylesheet diff and the theme-variables mapping were shown and OK'd; `theme_switch`, `motion.reduced` (and
      for Tailwind `reset_palette`) are in the tokens file
- [ ] Contrast evidence in `references/dark-mode.md`, no `contrast` error left (each fix asked); every colour has a
      dark value; `build-tokens.py --check` exits 0
- [ ] Components mapped (missing starters written only on OK); the audit on what you wrote exits 0
- [ ] `docs/design/decisions.md` has an entry per decision with who decided
- [ ] Every confirmed route has a screen file, mapped and synced; approved only on an explicit yes;
      `build-prototype.py --check` exits 0
- [ ] Init step 4 was asked item by item; then `<root>/.plumb-tmp/` is removed, last
- [ ] Nothing written outside `<root>`; app code changed only with the user's OK; nothing installed or downloaded

Then the summary: values found → tokens, the files written, the prototype, the audit counts, and
`git -C "<root>" status --short`.
