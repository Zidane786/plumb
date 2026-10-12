# Wiring Plumb into a project

`/plumb:init` step 4 asks each item below **on its own**, one at a time, with the recommendation first. Nothing is
written without the user's OK. Paths are relative to the confirmed project root `<root>`; change nothing in these files
beyond the agreed lines.

## AGENTS.md / CLAUDE.md row

Fill `<ROOT>/templates/agents-row.md` (`{{SKILL_DIR}}` = the skill dir with a trailing `/`). Ask: AGENTS.md
(Recommended when it exists) · CLAUDE.md · both · skip.

- Add the row to the file's "read before you work" table.
- No such table: add a `## Read before you work` section with the header `| When | Read | Rule |` and the row.
- Neither file exists: offer to create `<root>/AGENTS.md` with that section (and a `CLAUDE.md` holding `@AGENTS.md`).
- `scaffold.py --verify` looks for this row (it names `/plumb:prototype`), so keep the template's wording.

## Makefile targets

`tokens`, `tokens-check` and `design-audit` from `<ROOT>/templates/Makefile.snippet`, with `{{PYTHON}}` (the Python
command) and `{{SKILL_DIR}}` filled. Append to `<root>/Makefile`; create one only on yes. When targets with those
names already exist, show them and ask what to do. No `make` on the machine: the plain commands in `PLUMB.md` are
enough; say so.

## Slate review check

Only when `<root>/kanban/board.py` exists. Ask: "Add the design audit to Slate's review checks?" (a) Yes
(Recommended) (b) No. On yes add `- Plumb design audit: \`make design-audit\` exits 0` (or the plain command) under
`## Extra review checks` in `SLATE.md`, replacing a lone `- none`. Never touch `kanban/`: tickets are written only
through Slate's `board.py`.

## Kiro steering

Ask only when `<root>/.kiro/` exists or the user mentions Kiro: "Write `.kiro/steering/plumb.md` so Kiro reads the
design system on every task?" On yes write front matter `inclusion: always` and one paragraph: before any UI change
read `<skill dir>/SKILL.md`; UI work is prototype first; never install or download anything, ask the user and wait.
Kiro's own skills and hooks come from `kiro.py install`: tell the user; never run it for them.

## Monorepo package pointer

When the session was opened inside a monorepo package, offer the one-line pointer in that package's
`AGENTS.md`/`CLAUDE.md` (see "The skill folder" in [placement.md](placement.md)).
