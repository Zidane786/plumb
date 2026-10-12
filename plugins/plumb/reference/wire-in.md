# Wiring Plumb into a project

`/plumb:init` step 4 asks each item below **on its own**, one at a time, with the recommendation first, right after
create or extract. Nothing is written without the user's OK. Paths are relative to the confirmed project root `<root>`;
change nothing in these files beyond the agreed lines.

**Never skip an item.** Ask it even when the file does not exist yet: then the question is whether to create it. A
`note:` from `scaffold.py --verify` (no row, no Makefile targets) is not a reason to skip; it is the question still
to ask. The only items that depend on the project are the Slate check (`kanban/board.py`), Kiro (`.kiro/` or the
user mentions it) and the package pointer (opened inside a package).

## AGENTS.md / CLAUDE.md row

Fill `<ROOT>/templates/agents-row.md` (`{{SKILL_DIR}}` = the skill dir with a trailing `/`). Ask: AGENTS.md
(Recommended when it exists) · CLAUDE.md · both · skip.

- Add the row to the file's "read before you work" table.
- No such table: add a `## Read before you work` section with the header `| When | Read | Rule |` and the row.
- Neither file exists: offer to create `<root>/AGENTS.md` with that section (and a `CLAUDE.md` holding `@AGENTS.md`).
- `scaffold.py --verify` looks for this row (it names `/plumb:prototype`), so keep the template's wording.

## Makefile targets

`tokens`, `tokens-check` and `design-audit` from `<ROOT>/templates/Makefile.snippet`, with `{{PYTHON}}` (the Python
command) and `{{SKILL_DIR}}` filled. Ask: add them to `<root>/Makefile` (Recommended when it exists) · create a
`Makefile` with them (Recommended when it does not and `make` is on the machine) · no Makefile. When targets with
those names already exist, show them and ask what to do.

**No Makefile (declined, or no `make` on the machine): `PLUMB.md` must not name `make` targets.** The scaffold writes
`(make tokens)` hints into its `## Commands` lines; replace those two lines with the direct commands (the user's no
covers this edit; say so), `{{PYTHON}}` and `{{SKILL_DIR}}` filled:

```
tokens `{{PYTHON}} {{SKILL_DIR}}scripts/build-tokens.py`
check `{{PYTHON}} {{SKILL_DIR}}scripts/build-tokens.py --check` · audit `{{PYTHON}} {{SKILL_DIR}}scripts/audit.py`
```

`scaffold.py --verify` reports `problem: PLUMB.md names make …` while a named target is missing.

## Slate review check

Only when `<root>/kanban/board.py` exists. Ask: "Add the design audit to Slate's review checks?" (a) Yes
(Recommended) (b) No. On yes add `- Plumb design audit: \`make design-audit\` exits 0` (the direct audit command
when there is no Makefile) under `## Extra review checks` in `SLATE.md`, replacing a lone `- none`. Never touch
`kanban/`: tickets are written only through Slate's `board.py`.

## Kiro steering

Ask only when `<root>/.kiro/` exists or the user mentions Kiro: "Write `.kiro/steering/plumb.md` so Kiro reads the
design system on every task?" On yes write front matter `inclusion: always` and one paragraph: before any UI change
read `<skill dir>/SKILL.md`; UI work is prototype first; never install or download anything, ask the user and wait.
Kiro's own skills and hooks come from `kiro.py install`: tell the user; never run it for them.

## Monorepo package pointer

When the session was opened inside a monorepo package, offer the one-line pointer in that package's
`AGENTS.md`/`CLAUDE.md` (see "The skill folder" in [placement.md](placement.md)).
