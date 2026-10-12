# Audit rules: every rule `audit.py` checks

The rule table lives in the project's `<skill>/scripts/audit.py` (a Plumb file: upgrades replace it, nobody edits it).
This page is for agents explaining a finding or fixing it. Every finding prints as
`file:line: <severity> <rule>: <message>` then `  fix: <fix>`; the fix is token-aware (it names the token or utility to
use, e.g. `bg-[#14857F]` → `bg-primary (color.primary = #14857f)`).

**Severities.** `error` fails the audit (exit 1), and the edit check refuses an edit that adds one. `warn` is reported
only. `suggest` is an improvement: it never changes the exit code, says why it matters, and is ranked by impact in the
report's Improvements section (the rule's weight × how often it occurs). A design value with no close token is never
"fixed" by inventing one in code: add the token with `/plumb:update`, then use it.

**Always allowed:** arbitrary values for layout geometry (width, height, top/left, grid templates, z-index), and every
rule except `outline-none`, `icon-library` and `emoji` on the paths in `PLUMB.md`'s `Allowed raw values:` (where the
primitives live, e.g. `components/ui/**`). Exceptions are by path only, never by a comment in the line.

**Where it looks:** `.tsx .jsx .ts .js .vue .svelte .astro .html .css .scss` (web), `.swift` (iOS), `.kt` (Android);
never `node_modules`, build output or files over 5 MB; a `GENERATED … do not edit` header exempts a file only on the
paths Plumb's generators own. In a web copy (`$extensions.plumb.web.copies`, e.g. `app/globals.css`) only Plumb's block
(`/* plumb:start … */` to `/* plumb:end */`) is exempt: the rest of the file is the project's and is checked like any
stylesheet. `PLUMB.md`'s `UI files:` narrows a whole-project run.

**Named Tailwind steps are the project's.** `text-sm`, `rounded-lg`, `gap-4` (and `p-0.5`) mean the project's own token
when the tokens define that step (`typography.sm`, `radius.lg`, `spacing.4`, `spacing.0.5`): the rules and the
inventory behind `missing-token` count them at the token's value, never at Tailwind's default (in a project where
`radius.lg` is 10px, `rounded-lg` is 10px, not 8px).

## Per file (the edit check and the full audit)

| Rule | Severity | What it means | How to fix |
|---|---|---|---|
| `raw-colour` | error | A hex, `rgb()`, `hsl()` or similar colour in UI code. It does not switch with the theme and drifts from the system. | Use the colour token the fix names (`bg-primary`, `var(--color-primary)`). No close token: `/plumb:update` to add one. |
| `arbitrary-value` | error | A Tailwind arbitrary design value such as `p-[13px]`, `text-[15px]`, `rounded-[6px]`. | Use the token utility the fix names; layout geometry (`w-[…]`, `top-[…]`, grid templates) is allowed. |
| `palette-colour` | error | A Tailwind default palette colour (`text-gray-500`, `bg-blue-600`, `text-white`). | Use a colour token utility (`text-on-surface-muted`, `bg-primary`, `text-on-primary`). |
| `off-scale-type` | error | A font size that is not a typography token. | Use the typography token the fix names (`text-sm`, `var(--text-sm)`). |
| `off-scale-radius` | error | A border radius not on the radius scale. | Use a radius token (`rounded-md`, `var(--radius-md)`); `rounded-full` and `rounded-none` are always fine. |
| `off-scale-spacing` | error | Padding, margin or gap not on the spacing scale (a step the tokens name, like `p-4` with `spacing.4`, is always on it). | Use a spacing step (`p-4`, `var(--spacing-4)`). |
| `off-token-duration` | error | A transition or animation duration that is not a `motion.duration` token. | Use the motion token; `transition-none` turns a transition off. |
| `off-token-easing` | error | An easing curve that is not a `motion.easing` token. | Use the motion easing token. |
| `block-override` | error | In a web copy, outside Plumb's block: the project's own `@custom-variant dark`, or a token variable (`--color-*`, `--radius-*`, `--text-*`, `--font-*`, `--shadow-*`, `--ease-*`, `--spacing-*`, `--duration-*`) set in an `@theme` block. It overrides the design system without anyone seeing it. | Delete it there; put the value in the tokens with `/plumb:update` (how dark mode switches is `web.theme_switch`), then rebuild. Applies on allowed paths too. |
| `outline-none` | error | `outline: none` / `outline-none` removes the focus outline (also in forced-colours mode). | Keep a forced-colours outline (`outline-hidden`, or `outline: 2px solid transparent`) plus the focus-ring token. Applies on allowed paths too. |
| `inline-style` | error | A design property (colour, font, spacing, radius, shadow…) in a `style=` attribute or object. | Style with token utilities or classes; inline style is only for layout geometry. |
| `icon-library` | error | A second icon library imported next to the project's one. | Use the project's library through the icon map (`assets/icons/icon-map.json`). |
| `emoji` | error | An emoji in UI source (copy, labels, icons). | An icon from the icon map, or plain words. |
| `dark-variant` | warn | A `dark:` utility outside the primitives. Tokens already switch under `.dark`. | Fix the token's dark value (`/plumb:update`) or the primitive instead. |
| `hand-rolled-primitive` | warn | A hand-built dialog, menu, tabs, tooltip, select, checkbox, or a clickable `div`. | Use the accessible primitive from the components folder; a clickable thing is a `<button>` or a link. |
| `restyled-primitive` | warn | A primitive (`<Button className="…">`) restyled from outside. | Add a named variant or size inside the primitive and flag it for sign-off. |
| `swift-raw-colour` | error | `Color(red:…)` (or another component initialiser) or a hex initialiser in Swift code outside the theme. | A colour from the generated theme (`assets/platforms/mobile/ios/`). |
| `swift-font-size` | error | `.font(.system(size:))` with a literal size. | A text style from the generated theme. |
| `swift-corner-radius` | error | A literal `cornerRadius`. | A radius from the generated theme. |
| `kotlin-raw-colour` | error | `Color(0xFF…)` or another literal colour in Compose code outside the theme. | `MaterialTheme.colorScheme` or the project's generated colours. |
| `kotlin-font-size` | error | A literal `sp` type size outside the theme. | `MaterialTheme.typography`. |
| `kotlin-corner-radius` | error | A literal `dp` radius outside the theme. | `MaterialTheme.shapes`. |

## Across files (full audit only)

| Rule | Severity | What it means | How to fix |
|---|---|---|---|
| `generated-drift` | error | A generated file (theme CSS, Plumb's block in a web copy, Swift/Kotlin themes, specimen, prototype token blocks) differs from what the tokens produce. Only the block of a copy counts. | Run the tokens command (`<python> <skill>/scripts/build-tokens.py`); never hand-edit the generated file. |
| `contrast` | error | A colour pair below 4.5:1 (text) or 3:1 (large text, UI boundaries), in light or dark. The finding names the nearest value that passes with 0.5 to spare (so `contrast-headroom` never flags it once applied; when the hue cannot get that far, with 0.3, else the nearest that passes). | Change the token with `/plumb:update`, regenerate. Light-only projects (`Themes: light-only`) check light only. |
| `missing-dark-value` | error | A colour token with no `$extensions.plumb.dark`. | Add the dark value, or mark a deliberate constant `"same-in-dark": true` (`/plumb:update`). Off with `Themes: light-only`. |
| `near-duplicate-colour` | warn | Colours within ΔE 3 of each other (inconsistency-only mode). | Use the most-used value of the group. |
| `near-duplicate-size` | warn | Sizes within 1px or 6% of each other (inconsistency-only mode). | Use the most-used value of the group. |
| `outlier-value` | warn | A one-off value while a near-duplicate is used 5+ times (inconsistency-only mode). | Use the common value. |
| `duplicate-component` | warn | Several components doing one job (e.g. three hand-made buttons). | Use the primitive with a variant. |
| `focus-state` | warn | A primitive with no focus style, or primitives showing focus differently (ring vs outline vs shadow). | One visible focus style with the focus-ring token. |
| `hover-only` | warn | An action revealed only on hover (keyboard and touch users never see it). | Reveal it on focus too (`group-focus-within:`), or always show it. |
| `touch-target` | warn | A tap target under 44 px (web, without a `pointer-coarse:` size), 44 pt (SwiftUI) or 48 dp (Compose). | Make it at least 44px / 44pt / 48dp on touch. |
| `reduced-motion` | warn | Animation with no `prefers-reduced-motion` handling anywhere. | Add a reduced-motion block (see the skill's `references/motion.md`). |

### Prototype fidelity (full audit, when the project has a prototype)

| Rule | Severity | What it means | How to fix |
|---|---|---|---|
| `route-not-prototyped` | error (warn unless `Prototype sync: on`) | A route or page in the code that no screen in `screens.json` covers. | `/plumb:prototype <screen>`, the user approves, then `build-prototype.py --map <id> --route=<route> --files <globs>`. |
| `no-prototype` | warn | `Prototype sync: on` but there are no screen files and no `screens.json`. | `/plumb:extract` (existing app) or `/plumb:prototype`. |
| `screen-drift` | error (warn with no baseline) | A built screen's source files changed after its approval (or sync) while its screen file did not. | Update `screens/<id>.html` to show the change, ask the user, and only after their yes `--approve <id>` (or `--synced <id>` for a small fix already built). |
| `screen-unapproved` | error once built, warn while to-build | The screen file changed after its approval: don't build from it until it is approved again. Or the code of a never-approved screen changed. | Show the user the screen and ask; only after their yes to that screen, `build-prototype.py --approve <id>`. The finding prints this as an `ask the user:` line. |
| `screen-not-built` | warn | A screen with no route or source files yet, or whose globs match nothing. Expected until it is built. | Build it, then `--map` it. |
| `synced-from-code` | warn | A screen updated to match code that was already built. | Ask the user to confirm it in the prototype; only after their yes, `--approve <id>`. |
| `state-missing-in-code` | warn | A state of a built screen (loading, empty, error, success, offline…) with no handling in its source files. | Build the state as the screen file shows it. |
| `copy-missing-in-code` | suggest | A heading, button, field label or legend of the screen file not found in its source files. | Use the prototype's words, or update the screen file and get it approved. |
| `component-missing-in-code` | suggest | A component the screen file names (`data-component="BookingCard"`) not used in its source files. | Use that component, or update the screen file. |
| `missing-state` | suggest | A state `references/ux.md` (`### States per screen`) requires of a screen that its screen file lacks. | Add the state with `/plumb:prototype`. |

## Suggestions (improvements to the code and the system)

| Rule | Weight | What it means | How to fix |
|---|---|---|---|
| `missing-token` | 3 | The same raw value used 3+ times with no close token (the finding proposes a name). | Add the token with `/plumb:update`, then use it. |
| `contrast-headroom` | 3 | A pair that passes by less than 0.3 (light or dark). The finding names a value with 0.5 to spare. | Nudge the token with `/plumb:update`. |
| `duplicate-tokens` | 2 | Two tokens within ΔE 3 in every theme, or within 1px. Quiet while the system is new (below). | Merge them with `/plumb:update`. |
| `consolidate-components` | 2 | Components that differ only in padding or radius. | One component with a variant. |
| `consistency` | 2 | The same control with a different padding or radius across files. | Pick the majority value. |
| `unused-token` | 1 | A token nothing in the code uses (one per group; not run for explicit paths or under 5 UI files). Quiet while the system is new (below). | Remove it with `/plumb:update`, or use it. |

**A new system's own tokens.** For the first 14 days after the date on `PLUMB.md`'s `- YYYY-MM-DD created with Plumb …`
line (under `## Plumb updates`), `unused-token` and `duplicate-tokens` stay quiet: every token was just chosen on purpose
with the user and the UI that will use them is still being built, so housekeeping suggestions about them are noise.
From day 14 they run as usual. A project with no such line is not treated as new. The other suggestions
(`missing-token`, `contrast-headroom`, …) are about the code or about accessibility and always run.

The fidelity suggestions (`copy-missing-in-code`, `component-missing-in-code`, `missing-state`) are listed above with
their rules.

## Inconsistency-only mode

With no tokens file (a prototype, code before `/plumb:extract`) or with `--no-tokens`, the audit infers the de-facto
scales from the code, prints them, and reports `near-duplicate-colour`, `near-duplicate-size` and `outlier-value`. Raw
values are not errors in this mode (there are no tokens to point to), so it fails only on the rules that need no tokens
(`emoji`, `outline-none`, …).

## Agent review (not a rule)

`/plumb:audit` reads the screens after the script, against `design.md`, `ux.md` and the prototype, for what no rule can
express: hierarchy broken while still using tokens, two screens solving the same thing differently, words off the
vocabulary, an unhelpful empty or error state, something that looks wrong in dark mode. Those findings go into the HTML
report with `audit.py --html --add-review <review.json>`, in their own **Agent review** section, each marked so. They
never change the exit code; the rules stay the gate. The review file is a JSON list:

```json
[{"severity": "warn", "file": "app/booking/page.tsx", "line": 12,
  "message": "Two primary buttons compete on the booking screen",
  "fix": "Make Cancel a secondary button", "why": "One primary action per view keeps the next step obvious."}]
```

`severity` is `error` (must change), `warn` (should change) or `suggest` (could be better); `line` is optional (leave it
out for a whole-file finding); `why` is optional but recommended; no other keys.

**System proposals.** An entry whose `file` is a path under the design-system skill is a proposal to change **the
system itself**, not a screen: the tokens file (`<skill>/assets/tokens/<project>.tokens.json`),
`<skill>/references/components.md`, `<skill>/references/ux.md` or `<skill>/design.md`. Write it with the change as the
`message`, the proposed value or wording as the `fix`, and the evidence (which screens, how often) as the `why`.
`/plumb:audit improve` writes system changes this way, and `/plumb:update` reads exactly these entries (from the latest
`<docs>/audit-*.review.json`), together with the audit's system rules (`missing-token`, `duplicate-tokens`,
`unused-token`, `contrast-headroom`, `consolidate-components`, `missing-state`, `contrast`, `missing-dark-value`), and
proposes them one at a time. Every other entry is about screens or code and stays with `/plumb:audit`.

**Proposing a new rule.** When the review keeps finding the same kind of problem (the same kind in 3+ places, or in two
audits running), propose it to the user as a rule: say what it would check, one failing and one passing example, and its
severity. On a yes, write it into the project's `design.md` or `ux.md` (agents follow it from the next screen on), and
offer to propose it to Plumb as an audit rule (an issue or PR on the Plumb repo). Never edit the project's copy of
`audit.py`: it is Plumb's file and an upgrade replaces it.
