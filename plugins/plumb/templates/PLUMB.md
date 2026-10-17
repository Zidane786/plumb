<!-- plumb v1.0.0 · written by /plumb:init, safe to edit values -->
# Plumb: the design system for {{PROJECT}}

Design system: `{{SKILL_DIR}}`
Role: {{ROLE}}                          (home = this repo owns the tokens; linked = uses another repo's)
Platforms: {{PLATFORMS}}
UI packages: {{UI_PACKAGES}}
Python: `{{PYTHON}}`
No downloads: nothing is installed or downloaded; if something is missing, ask the user and wait for their decision.
Plumb's own mistakes (a script, hook or skill got it wrong): /plumb:feedback. The project's design issues: /plumb:audit.

## Checks
Edit check: {{EDIT_CHECK}}
End-of-turn check: {{END_CHECK}}
Themes: {{THEMES}}          (light-and-dark | light-only: an explicit decision)
UI files: {{UI_FILES}}
Routes: {{ROUTES}}          (the app's page roots, each path with its kind: next-app, next-pages, nuxt, sveltekit, angular or router; or none)
Allowed raw values: {{ALLOWED_RAW}}

## Commands
tokens `{{PYTHON}} {{SKILL_DIR}}scripts/build-tokens.py`
check `{{PYTHON}} {{SKILL_DIR}}scripts/build-tokens.py --check` · audit `{{PYTHON}} {{SKILL_DIR}}scripts/audit.py`

## Prototype
Main: {{PROTOTYPE_MAIN}} · app: {{APP_PAGE}} · screens: {{SCREENS_PAGE}} · map: {{SCREENS_MAP}}
Prototype sync: {{PROTOTYPE_SYNC}}               (end-of-turn check stops once when a built screen changed without its prototype)

## Plumb updates
- {{DATE}} created with Plumb 1.0.0 ({{PLATFORMS}}; direction "{{DIRECTION}}")
