---
name: extract
description: Extract the design system an existing app already has - inventory every colour, font, size, spacing, radius, shadow, duration and easing in use (counts and file:line), cluster near-duplicates into a clean token set shown as a before/after page, confirm it group by group, ask the product and UX questions the code cannot answer, generate the design system after the user approves the files, build the main prototype from the existing routes, and audit what does not match yet (with Slate tickets on offer).
argument-hint: "[UI folders]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/detect.py*), Bash(python *scripts/detect.py*), Bash(py -3 *scripts/detect.py*), Bash(python3 *scripts/scaffold.py*), Bash(python *scripts/scaffold.py*), Bash(py -3 *scripts/scaffold.py*), Bash(python3 *scripts/build-tokens.py*), Bash(python *scripts/build-tokens.py*), Bash(py -3 *scripts/build-tokens.py*), Bash(python3 *scripts/audit.py*), Bash(python *scripts/audit.py*), Bash(py -3 *scripts/audit.py*), Bash(python3 *scripts/build-prototype.py*), Bash(python *scripts/build-prototype.py*), Bash(py -3 *scripts/build-prototype.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git -C * status --short)
---

# /plumb:extract — the system you already ship, cleaned up

Only run when the user typed `/plumb:extract` (or `/plumb:init` routed here). Other skills offer it, never run it.

```
placement ─▶ 1–2 inventory (audit.py --inventory) ─▶ 3 clusters ─▶ 4 before/after page ─▶ each group OK?
   ─▶ 5 remaining product + UX questions ─▶ create E (token set OK? files OK? contrast OK? components OK?) + G
   ─▶ 6 screens to prototype OK? ─▶ screen files ─▶ 7 audit what does not match yet ─▶ Slate tickets on offer ─▶ wire in
```

**Rules.** **Nothing is written without the user's OK.** Each checkpoint (marked **OK?**) is a question-tool step
that waits for the answer. What the code shows (values, clusters, dark values, routes, components) is a
**suggestion** to confirm or correct, never used silently. Questions go **one at a time**, options with the
recommendation first marked "(Recommended)" and why. Questions and recommendations:
[reference/interview.md](../../reference/interview.md); the tokens format:
[reference/tokens-format.md](../../reference/tokens-format.md); placement:
[reference/placement.md](../../reference/placement.md). Light **and** dark by default. **Never install or download
anything**; if something seems needed, say so, **ask the user and wait**. App code changes only with the user's OK;
the audit in step 7 reports, it does not fix. Pre-approved commands (`allowed-tools`): Plumb's `detect.py`, `scaffold.py`,
`build-tokens.py`, `audit.py`, `build-prototype.py`, and the read-only git calls; anything else asks first.

**Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
`<plugin>/skills/extract`) + `/../..`, resolved to an absolute path.

**Project root (`<root>`):** the absolute root the user confirmed in `/plumb:init`. Every path below is relative to
`<root>` and every command names it explicitly; never write outside it, never use `.` for it. The one exception: the
answers JSON for `scaffold.py` goes to the system temp folder and is deleted right after the scaffold.

## Step 0: placement and Python

Routed from `/plumb:init`: use its confirmed placement and `<root>`. Run directly: if a design system already exists,
stop and offer `/plumb:update`; otherwise do `/plumb:init` steps 1–2 first (`ROOT/skills/init/SKILL.md`), so the user
confirms where everything goes before anything is written. **Design only** (a React Native app, or the user's choice):
platforms `web`, styling `css`, no web copies, no components inside the app (never React Native components; React
Native themes are a 1.1.0 candidate), an HTML prototype only.

## 1–2. Scan and inventory

**OK?** Which folders hold the UI, and should any be left out (vendored, legacy, marketing)? Then run the plugin's own
audit script (no design system exists yet; it only reads):

```
python3 "<ROOT>/assets/skill/scripts/audit.py" "<root>/<UI folder>"… --inventory --json --project "<root>" [--exclude "legacy/**"]
```

It reads CSS, SCSS, Tailwind classes, inline styles, `<style>` blocks, JS style objects, HTML, Swift and Kotlin
(skipping `node_modules`, build output and generated files) and returns, per kind (colour, font family, size, weight,
line height, spacing, radius, shadow, duration, easing), every value with its count and `file:line`, plus proposed
clusters. Then read what the script does not interpret (Tailwind config `theme.extend`, existing CSS variables,
`Color`/`Theme` files) and list the **component variants** in use (button kinds and sizes, card styles, badges).

## 3. Clusters

Near-duplicates are already grouped: colours below CIEDE2000 3, sizes within 1px or 6%; the most-used value of each
group is the proposed token. Name each proposed token **by role** (`primary`, `on-surface-muted`, `danger`), never by
hue; map spacing onto Tailwind steps (`"2": "8px"`) and font sizes onto the type scale names. Existing dark values (a
`.dark` block, `prefers-color-scheme`, `dark:` classes) become `$extensions.plumb.dark`; colours with none get a
proposed dark value.

## 4. Before/after page, then each group confirmed

**OK?** "I'll write the proposal page to `<root>/docs/design/extract.html`" (a) Write it (Recommended) (b) Another
path. Then write it (with Effective HTML's `design-artifact` when available, else a plain self-contained page;
nothing from the network): per group, **before** (every value with swatch, count
and a few `file:line`) and **after** (the proposed token, its value in light and dark, what merges into it), and how
many values become how many tokens. **OK? Each group, one at a time:** accept (Recommended) · rename · merge with
another · split · leave out. After three groups, also offer "Accept all remaining groups as proposed" next to "Keep
going one by one". Never merge two values the user wants apart.

## 5. What the code cannot answer

Ask only the interview questions the code does not answer: the product (A1–A6), dark mode when the app has none
(C13), the accessibility target (C14), vocabulary and voice (C15), and the UX patterns (C16) the screens do not make
clear. Offer what the code shows as the recommendation ("the app uses a left sidebar: keep it?"). **OK?** Summarise
in five lines: "Right?".

## Generate and record (create E and G)

Follow `/plumb:create` steps **E** and **G** (read `ROOT/skills/create/SKILL.md`), with every checkpoint: the full
token set (E1), the scaffold's dry-run file list (E2), each contrast fix (E5), the component plan (E6). The confirmed
groups are the answers; **no directions step** (the look already exists). In E6 the components exist already: map
them to `references/components.md` and `inventory.md`; propose only the missing starters, and change existing
components only with the user's OK. **The design system must pass:** `python3 "<root>/<skill dir>/scripts/audit.py"
"<root>/<folder of each component you wrote>"` exits 0 (contrast, missing dark values and generated-file drift run
with PATHS too); the rest of the app is step 7. In G, link each entry to `extract.html`.

## 6. Main prototype from the existing app

1. **Find the routes yourself** (primary): Next.js `app/**/page.*` (route groups `(x)` and `@slots` are not in the
   URL; `_folders` are private) or `pages/**` (not `_app`, `_document`, `api/`); Nuxt `pages/**/*.vue`; SvelteKit
   `src/routes/**/+page.svelte`; Angular `*.routes.ts` / `*routing.module.ts`; Vue Router `router/index.*`; React
   Router `createBrowserRouter` / `<Route path>`; plain HTML pages; SwiftUI `NavigationStack` destinations and
   `TabView` tabs; Compose `NavHost` `composable("…")`; React Native navigators (`Stack.Screen`, expo-router `app/`).
2. **OK? The screens to prototype:** show route → screen id → source files, all included (Recommended) or pick.
3. **OK? The files:** list the `docs/design/prototype/screens/<id>.html` files to write. Write each from the real code,
   following the screen-file contract at the top of `<skill dir>/scripts/build-prototype.py`: real copy, the states
   the code handles (loading, empty, error, success, long text, …) as `data-state` blocks, the interactions inline
   (links, tabs, dialogs, menus, validation, toasts), tokens only (CSS variables), light and dark.
4. Map and mark each: `python3 "<root>/<skill dir>/scripts/build-prototype.py" --map <id> --route <route> --files
   <globs>`, then `--synced <id>` (synced from code: the user confirms later with `--approve`, without blocking).
5. Once the first screen exists, `python3 "<root>/<skill dir>/scripts/audit.py" --json` reports any route still
   without a screen as `route-not-prototyped`: add the ones you missed (asked). `build-prototype.py --check` exits 0.
   Give the paths of `docs/design/prototype.html` and `screens.html` and ask the user to look.

## 7. Audit what does not match yet

`python3 "<root>/<skill dir>/scripts/audit.py" --html` writes `docs/design/audit-YYYY-MM-DD.html`. Summarise errors
and warnings by area. When `<root>/kanban/board.py` exists, offer Slate tickets for the fixes, grouped by area,
created only through Slate's `board.py` (never edit `kanban/`). Otherwise offer `/plumb:audit fix`.

## Finish

Routed from init: return to `/plumb:init` step 4. Run directly: do init's step 4 now (each item asked). Show the
summary (values found → tokens, the files written, the prototype, the audit counts) and `git -C "<root>" status --short`.

## Checklist

- [ ] The inventory came from `audit.py --inventory`; every token group was confirmed by the user
- [ ] The user approved the token set, the file list, each contrast fix, the components and the screens to prototype
- [ ] Every colour token has a dark value (or a recorded light-only decision); `build-tokens.py --check` exits 0
- [ ] Every confirmed route has a screen file, mapped and marked synced from code; `build-prototype.py --check` exits 0
- [ ] Nothing written outside `<root>`; app code changed only with the user's OK; nothing installed or downloaded
