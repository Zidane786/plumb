# Tokens format

The design system has **one source of values**: `<skill>/assets/tokens/<project>.tokens.json`, a W3C Design Tokens
(DTCG) file. Everything else (web CSS, Tailwind config, SwiftUI and Compose themes, the specimen, the prototype token
blocks, the contrast evidence) is generated from it by `build-tokens.py`. Edit only this file, then run the build.
Exactly one `*.tokens.json` lives in that folder.

## Shape of a token

```json
"primary": {
  "$value": "#0f6b66",
  "$description": "The accent: focus ring, active, primary action",
  "$extensions": { "plumb": { "dark": "#4fb3c4" } }
}
```

- `$value` is the **light** value (and the value below the `md` breakpoint).
- `$type` may sit on the token or on its group (`"color": { "$type": "color", ... }`); a token inherits its group's.
- `$description` says what the token is for, in words people use. Optional, but write one for every colour role.
- References use `{group.token}`: `"link": { "$value": "{color.primary}" }`. A reference follows its target in light,
  dark and `md`, so an alias needs no dark value of its own. Cycles are refused.

## `$extensions.plumb` on a token

| Key | Means | Example |
|---|---|---|
| `dark` | The value in dark mode. **Every colour token needs one** (a missing one is an audit error). | `"dark": "#4fb3c4"` |
| `same-in-dark` | `true` marks a deliberate constant (a brand fill that never changes). Replaces `dark`. | `"same-in-dark": true` |
| `md` | The value from the `md` breakpoint (48rem) up, on the web. For a composite token (typography) only the fields given change. | `"md": { "fontSize": "40px", "lineHeight": "48px" }` |

A shadow's `dark` is a full shadow array (dark shadows usually need more opacity). A project that decided on light only
records `Themes: light-only` in `PLUMB.md` (and a decision entry); then the dark rules are off.

## Groups

| Group | `$type` | Keys and notes |
|---|---|---|
| `color` | `color` | Roles, not hues: `background`, `surface`, `sunk`, `on-surface`, `on-surface-muted`, `primary`, `on-primary`, `outline`, `outline-input`, `danger`, `on-danger`, `success`, `on-success`, `warning`, `info`, `link`, `scrim` … Every `X` that text sits on has an `on-X`. Values `#rgb`, `#rrggbb`, `#rrggbbaa`. |
| `label` | `color` | Category or status label colours (tags, chips): `label.blue`, `label.amber`… Each with a dark value. CSS `--color-label-<name>`. |
| `font` | `fontFamily` | Arrays, first family then the system stack: `["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"]`. No hosted fonts: a project font is embedded from the project's own files. |
| `typography` | `typography` | Composite: `fontSize`, `lineHeight`, `fontWeight` (+ optional `letterSpacing`, `fontFamily`). Default names `display h1 h2 h3 body-lg body sm xs`; the names are the type scale the audit enforces. |
| `spacing` | `dimension` | **Keys are Tailwind steps**: `"1": "4px"`, `"2": "8px"`, `"3": "12px"`, `"4": "16px"` … `"16": "64px"`, so `p-2` is 8px and `gap-4` is 16px. A half step keeps its dot: `"0.5": "2px"` is `p-0.5`, CSS `--spacing-0_5` (the name Tailwind v4 looks up for `p-0.5`), referenced as `{spacing.0.5}`. Off-scale spacing is an audit error. |
| `radius` | `dimension` | `sm`, `md`, `lg` (+ `full` when pills are used). |
| `size` | `dimension` | Fixed sizes: `size.control-md`, `size.icon-sm`, `size.touch` (44px). |
| `border` | `dimension` | Border widths: `border.hairline`, `border.focus`. |
| `shadow` | `shadow` | Arrays of `{offsetX, offsetY, blur, spread, color}` (+ `inset`); `card`, `popover`, each with a dark array. |
| `motion` | `duration`, `cubicBezier` | `motion.duration.fast|mid|slow` (`"150ms"`), `motion.easing.out` (`[0.2, 0.8, 0.2, 1]`), optional `motion.distance.*`, `motion.scale.*`. Durations and easings off the tokens are audit errors. |
| `effect` | any | Anything else visual (focus ring width and offset, backdrop blur). |

Generated CSS names: `--color-<name>`, `--color-label-<name>`, `--text-<name>` (+ `--text-<name>--line-height`, …),
`--font-<name>`, `--radius-<name>`, `--spacing-<step>`, `--shadow-<name>`, `--duration-<name>`, `--ease-<name>`,
`--size-<name>`, `--border-<name>`. A decimal step's point becomes `_` in the variable (`spacing.0.5` → `--spacing-0_5`,
`spacing.1.5` → `--spacing-1_5`; in the Swift and Kotlin themes `s0_5`, `s1_5`, never clashing with `s15`); a dot
anywhere else in a name is refused (`error:` / `fix:` rename it). Numeric groups nested in numeric groups
(`"z": {"1": {"2": …}}`, path `z.1.2`) still mean three names (`--z-1-2`). In Tailwind v4 they become utilities (`bg-primary`, `text-sm`, `rounded-md`, `p-2`,
`shadow-card`, `duration-fast`, `ease-out`); in Tailwind v3 through the generated `tailwind.tokens.js`.

## Settings at the root

Machine settings live in the root `$extensions.plumb`, so the skill is self-contained and a linked repo can read it:

```json
{
  "$extensions": {
    "plumb": {
      "schema": 1,
      "project": "acme",
      "platforms": ["web", "ios"],
      "docs_dir": "docs/design",
      "web": { "styling": "tailwind-v4", "copies": ["app/globals.css"], "theme_switch": "both" },
      "motion": { "reduced": "keep-fades" },
      "contrast": {
        "surfaces": ["background", "surface", "sunk"],
        "ui": ["outline-input"],
        "extra_pairs": [["on-primary-fill", "primary-fill", "text"], {"fg": "primary", "bg": "background", "need": 3}]
      }
    }
  }
}
```

| Key | Means |
|---|---|
| `schema` | Tokens format version (now `1`). Changes only with a migration. |
| `project` | The project id (lower-case, hyphens). Names the tokens file, the themes (`AcmeTheme.swift`) and the skill. |
| `platforms` | `web`, `ios`, `android`. Adding one later is `/plumb:update`. |
| `docs_dir` | Where the design pages live (default `docs/design`). |
| `web.styling` | `tailwind-v4` (`@theme` + utilities), `tailwind-v3` (`tailwind.tokens.js` + CSS variables) or `css` (custom properties). |
| `web.copies` (`$extensions.plumb.web.copies`) | Project-relative stylesheets that hold the generated CSS in Plumb's marked block (e.g. `app/globals.css`; in a linked setup, paths into the other repo). Only the block, the `plumb:start … plumb:end` block (from the line `/* plumb:start — GENERATED by Plumb, do not edit inside */` to the line `/* plumb:end */`), is Plumb's; the rest of the file stays the project's (see [scripts.md](scripts.md)). |
| `web.theme_switch` (`$extensions.plumb.web.theme_switch`: `both` \| `system` \| `class`) | How the web app reaches dark mode: `both` (default: the system setting, unless `<html>` has `.light`, and the `.dark` class), `system` (only `prefers-color-scheme`), `class` (only `.dark`). `.light` always puts the light values back. Optional; a file without it builds as `both` once its web template has the `{{@dark}}` line. |
| `motion.reduced` (`$extensions.plumb.motion.reduced`: `keep-fades` \| `none`) | What `prefers-reduced-motion` keeps on the web: `none` (default: no animation or transition) or `keep-fades` (an element whose transition is only a fade keeps it: Tailwind's `transition-opacity` / `transition-colors`, or the class `motion-fade` on an element whose own CSS transition is a fade; every other transition and every animation stops; no element gains a transition it did not have). Record the decision here when the user makes it. |
| `contrast.surfaces` | Exactly the surfaces text is checked over (default: background, page, sidebar, sunk, column, surface*, *-container). |
| `contrast.ui` | Extra UI boundary tokens checked at 3:1 (`outline-input` is always checked). |
| `contrast.extra_pairs` | More pairs: `[fg, bg, kind]` with kind `text` (4.5:1), `large` or `ui` (3:1), or `{"fg", "bg", "need", "note"}`. |

Unknown keys are kept, never removed. `web.theme_switch` and `motion.reduced` are additions to schema 1: create and
`scaffold.py` always write both; in an older file `--migrate` does not add them, the defaults apply and the build prints
a `note:` asking to record the choice; an unknown value exits 2 with `error:` / `fix:`.

## Contrast

`build-tokens.py` computes WCAG 2.x contrast in light **and** dark: every `on-X` over `X`, every text token over every
surface, `outline-input` and `contrast.ui` over every plain surface at 3:1, plus `extra_pairs`. The evidence table is
written into `references/dark-mode.md` between `<!-- plumb:contrast:start -->` and `<!-- plumb:contrast:end -->`.
A failing pair is an audit error whose fix names the nearest passing value (stepped darker in light, lighter in dark),
aimed at the minimum plus 0.5 so the audit's `contrast-headroom` suggestion (under 0.3) never flags a value Plumb
proposed.
Plumb never changes a colour on its own: show the pair, the ratio and the proposed value, and apply it with the user's OK.

## Schema and migration

- `build-tokens.py --migrate` brings an older file to schema `1` by **adding** missing settings; it never removes or
  changes a value. A file with a newer schema than the scripts is refused (update the plugin, then `/plumb:upgrade`).
- `build-tokens.py --check` exits 1 naming every stale generated file; `--contrast` rewrites only the contrast block;
  `--css-vars` prints plain CSS variables (used by the prototypes and the specimen).
- A broken file exits 2 with `error: <token>: …` and `fix: …`. Fix the file, never the generated output.

## Rules of thumb

- Name tokens by role (`danger`, `on-surface-muted`), never by hue (`red-500`); hues belong in `label`.
- Add a token only when a value is used for a reason that will recur; a one-off is a layout value, not a token.
- Every new colour gets its dark value and its `on-` partner at the same time, then run the build and read the contrast.
- After any change: `build-tokens.py`, then `audit.py`; record the change in `docs/design/decisions.md`.
