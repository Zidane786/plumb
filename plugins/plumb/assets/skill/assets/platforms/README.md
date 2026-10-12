# Platform outputs

Everything here is made from the one tokens file, `../tokens/<project>.tokens.json`. Never edit a generated file; edit the
tokens file and regenerate. This README is plugin-owned and is refreshed by Plumb upgrades.

| Output | Made by | Notes |
|---|---|---|
| `web/tokens.css` | `scripts/build-tokens.py` | Light on `:root`, dark under `.dark`, plus the md breakpoint. Also copied to each path in `$extensions.plumb.web.copies`. |
| `web/tailwind.tokens.js` | `scripts/build-tokens.py` | Tailwind v3 projects only. |
| `mobile/ios/<Project>Theme.swift` | `scripts/build-tokens.py` | SwiftUI colours, type, radii, spacing, motion, icons. |
| `mobile/android/<Project>Theme.kt` | `scripts/build-tokens.py` | Compose theme, shapes, type, motion, icons. |
| `web/tokens.css.template` | you | The CSS structure for the project's styling mode; values stay in the tokens JSON. |
| `*/starter/` | the agent | Starter components, only while no app exists yet; they must pass the audit. |

## Regenerate

```
make tokens          # write every output
make tokens-check    # fail when an output is stale or missing
```

Without make, run the Python command in `PLUMB.md` (`build-tokens.py`, add `--check` to verify). The specimen page
(`docs/design/specimen.html` by default) and the contrast table in `references/dark-mode.md` are refreshed by the same command.

## Nothing is downloaded

The generated files load no fonts, scripts or styles from the network. If a font file or tool is missing, ask the user and wait.
