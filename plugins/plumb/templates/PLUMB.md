<!-- plumb v1.0.0 · written by /plumb:init, safe to edit values -->
# Plumb: the design system for {{PROJECT}}

Design system: `{{SKILL_DIR}}`
Role: {{ROLE}}                          (home = this repo owns the tokens; linked = uses another repo's)
Platforms: {{PLATFORMS}}
UI packages: {{UI_PACKAGES}}
Python: `{{PYTHON}}`
No downloads: nothing is installed or downloaded; if something is missing, ask the user and wait for their decision.

## Checks
Edit check: {{EDIT_CHECK}}
End-of-turn check: {{END_CHECK}}
UI files: {{UI_FILES}}
Allowed raw values: {{ALLOWED_RAW}}

## Commands
tokens `{{PYTHON}} {{SKILL_DIR}}scripts/build-tokens.py` (make tokens)
check `… build-tokens.py --check` (make tokens-check) · audit `… audit.py` (make design-audit)

## Prototype
Main: {{PROTOTYPE_MAIN}} · screens: {{SCREENS_PAGE}} · map: {{SCREENS_MAP}}
Prototype sync: {{PROTOTYPE_SYNC}}               (end-of-turn check stops once when a built screen changed without its prototype)

## Plumb updates
- {{DATE}} created with Plumb 1.0.0 ({{PLATFORMS}}; direction "{{DIRECTION}}")
