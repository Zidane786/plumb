---
name: extract
description: Extract the design system an existing app already has - inventory every colour, font, size, spacing, radius, shadow, duration and easing in use (counts and file:line), cluster near-duplicates into a clean token set shown as a before/after page, confirm it group by group, ask the product and UX questions the code cannot answer, generate the design system, build the main prototype from the existing routes, and audit what does not match yet (with Slate tickets on offer).
argument-hint: "[UI folders]"
disable-model-invocation: true
allowed-tools: Bash(python3 *scripts/*.py*), Bash(python *scripts/*.py*), Bash(py -3 *scripts/*.py*), Bash(git rev-parse *), Bash(git config user.name), Bash(git status *)
---

# /plumb:extract — the system you already ship, cleaned up

Only run when the user typed `/plumb:extract` (or `/plumb:init` routed here). Other skills offer it, never run it.

```
placement ─▶ 1 scan + 2 inventory (audit.py --inventory) ─▶ 3 clusters ─▶ 4 before/after page ─▶ confirm group by group
   ─▶ 5 remaining product + UX questions ─▶ create E (generate) + G (record) ─▶ 6 main prototype from the routes
   ─▶ 7 audit what does not match yet ─▶ Slate tickets on offer ─▶ wire in (init step 4)
```

**Rules.** Questions go through the question tool, **one at a time**, options with the recommendation first marked
"(Recommended)". Questions and how to derive recommendations: [reference/interview.md](../../reference/interview.md);
the tokens format: [reference/tokens-format.md](../../reference/tokens-format.md); placement:
[reference/placement.md](../../reference/placement.md). Light **and** dark by default. **Never install or download
anything**; if something seems needed, say so, **ask the user and wait**. Never change app code in steps 1–6 without
asking; the audit in step 7 reports, it does not fix.

**Plugin root (`ROOT`):** `${CLAUDE_PLUGIN_ROOT}` (Claude Code and Copilot CLI fill this in for plugin skills).
If it still reads literally as `${CLAUDE_PLUGIN_ROOT}`, use this skill's base directory (printed when the skill loads,
`<root>/skills/extract`) + `/../..`, resolved to an absolute path.

## Step 0: placement and Python

Routed from `/plumb:init`: use its confirmed placement. Run directly: if a design system already exists, stop and
offer `/plumb:update`; otherwise do `/plumb:init` steps 1–2 first (`ROOT/skills/init/SKILL.md`), so the user
confirms where everything goes before anything is written.

## 1–2. Scan and inventory

Run the inventory with the plugin's own audit script (no design system exists yet):

```
python3 "<ROOT>/assets/skill/scripts/audit.py" <UI folders> --inventory --json --project . [--exclude "legacy/**"]
```

It reads CSS, SCSS, Tailwind classes, inline styles, `<style>` blocks, JS style objects, HTML, Swift and Kotlin
(skipping `node_modules`, build output and generated files) and returns, per kind (colour, font family, size, weight,
line height, spacing, radius, shadow, duration, easing), every value with its count and `file:line`, plus proposed
clusters. Ask first whether any folder should be left out (vendored, legacy, marketing). Then read the theme files the
script does not interpret (Tailwind config `theme.extend`, existing CSS variables, `Color`/`Theme` files) and list the
**component variants** in use (button kinds and sizes, card styles, badge colours) with where they live.

## 3. Clusters

Near-duplicates are already grouped: colours below CIEDE2000 3, sizes within 1px or 6%; the most-used value of each
group is the proposed token. Name each proposed token **by role** (`primary`, `on-surface-muted`, `danger`), never by
hue; map spacing onto Tailwind steps (`"2": "8px"`) and font sizes onto the type scale names. Existing dark values (a
`.dark` block, `prefers-color-scheme`, `dark:` classes) become `$extensions.plumb.dark`; colours with none get a
proposed dark value.

## 4. Before/after page, then confirm group by group

Write `docs/design/extract.html` (with Effective HTML's `design-artifact` when available, else a plain self-contained
page; nothing from the network): per group, **before** (every value with swatch, count and a few `file:line`) and
**after** (the proposed token, its value in light and dark, what merges into it), and a summary of how many values
become how many tokens. Give the path, then confirm **one group at a time**: accept (Recommended) · rename · merge
with another · split · leave out. Never merge two values the user wants apart.

## 5. What the code cannot answer

Ask only the interview questions the code does not answer: the product (A1–A6: what, who, where, key tasks, feel,
brand), dark mode when the app has none (C13), the accessibility target (C14), vocabulary and voice (C15) and the UX
patterns (C16) that the screens do not make clear. Present what the code shows as the recommendation ("the app uses a
left sidebar: keep it?").

## Generate and record (create E and G)

Follow `/plumb:create` steps **E** and **G** (read `ROOT/skills/create/SKILL.md`), with the confirmed tokens as the
answers and **no directions step** (the look already exists). In E5 the components exist already: map them to
`references/components.md` and `inventory.md`; write only the missing starters, and change existing components only
with the user's OK. `audit.py` must exit 0 on the design system itself (tokens, contrast, generated files, the
components you wrote); the rest of the app is step 7. In G, link each entry to `extract.html`.

## 6. Main prototype from the existing app

1. Find the routes: `python3 <skill dir>/scripts/audit.py --json` lists each route with no screen as
   `route-not-prototyped`; check the router yourself and show the list (route → screen id → source files). Ask which to
   include (all, Recommended).
2. For each screen write `docs/design/prototype/screens/<id>.html` from the real code, following the screen-file
   contract at the top of `<skill dir>/scripts/build-prototype.py`: real copy, the states the code handles (loading,
   empty, error, success, long text, …) as `data-state` blocks, the interactions inline (links, tabs, dialogs, menus,
   validation, toasts), tokens only (CSS variables), light and dark.
3. Map and mark each one: `python3 <skill dir>/scripts/build-prototype.py --map <id> --route <route> --files <globs>`
   then `--synced <id>` (synced from code: the user confirms later with `--approve`, without blocking).
4. `build-prototype.py` (build) and `build-prototype.py --check` exit 0. Give the paths of `docs/design/prototype.html`
   and `screens.html` and ask the user to look.

## 7. Audit what does not match yet

`python3 <skill dir>/scripts/audit.py --html` writes `docs/design/audit-YYYY-MM-DD.html`. Summarise errors and warnings
by area. When `kanban/board.py` exists, offer Slate tickets for the fixes, grouped by area, created only through
Slate's `board.py` (never edit `kanban/`). Otherwise offer `/plumb:audit fix`.

## Finish

Routed from init: return to `/plumb:init` step 4. Run directly: do init's step 4 now (each item asked). Show the
summary (values found → tokens, the files written, the prototype, the audit counts) and `git status --short`.

## Checklist

- [ ] The inventory came from `audit.py --inventory`; every proposed group was confirmed by the user
- [ ] `docs/design/extract.html` shows before and after; decisions link to it with who decided
- [ ] Every colour token has a dark value (or a recorded light-only decision); `build-tokens.py --check` exits 0
- [ ] Every confirmed route has a screen file, mapped and marked synced from code; `build-prototype.py --check` exits 0
- [ ] App code changed only with the user's OK; nothing was installed or downloaded
