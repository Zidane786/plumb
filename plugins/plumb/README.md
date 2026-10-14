# Plumb

Create, extract, prototype, audit and maintain a project's design system, so every screen an agent builds stays
consistent: one token file that generates the web, iOS and Android themes, a clickable prototype of the whole product
that you approve before anything is built (and the same screens full window, `app.html`, to demo), and checks that
stop drift while the agent works. Claude Code and GitHub Copilot CLI, macOS, Linux and Windows. You stay in charge: one
question at a time, nothing written without your OK, nothing installed or downloaded.

**The complete guide:** [docs/USAGE.md](https://github.com/Zidane786/plumb/blob/main/docs/USAGE.md) ·
**what a project gets:** [docs/what-you-get.html](https://github.com/Zidane786/plumb/blob/main/docs/what-you-get.html)

## Install

In a terminal:

```
claude plugin marketplace add Zidane786/plumb
claude plugin install plumb@plumb
```

Or inside Claude Code: `/plugin marketplace add Zidane786/plumb`, then `/plugin install plumb@plumb`. Then, inside your
project:

```
/plumb:init
```

**GitHub Copilot CLI:** `copilot plugin marketplace add Zidane786/plumb`, then `copilot plugin install plumb@plumb`,
then `/restart`. The commands are the same. Copilot asks permission for each script run and file write (a full setup:
about 10–15 script prompts plus one per file); a permission prompt is never your answer to a Plumb question. To cut
the prompts, see the "Permission prompts" notes in `reference/copilot.md` (`--add-dir`, `--allow-tool`: your call).

**Kiro (preview, live check pending):** `python3 <plumb>/scripts/kiro.py install` (your home folder) or
`… install --project <folder>` (that workspace only) copies the skills (`/plumb-init`, …) and the hook files, asking
first (`--yes` skips the question); run it again after updating Plumb. Details: [reference/kiro.md](reference/kiro.md).

Needs Python 3.9+ (standard library only; `py -3`, `python` or `python3` on Windows). git is optional.

## Update

Turn on auto-update once (`/plugin` → **Marketplaces** → **plumb** → **Enable auto-update**), or by hand:
`claude plugin marketplace update plumb`, `claude plugin update plumb@plumb`, then `/reload-plugins`. In Copilot CLI:
`copilot plugin marketplace update plumb`, `copilot plugin update plumb@plumb`, `/restart`. Then run `/plumb:upgrade`
in each project (the session-start line says when). What changed: [CHANGELOG.md](CHANGELOG.md).

## Commands

| Command | Use it when | What it does |
|---|---|---|
| `/plumb:init` | First time in a project | Finds the home, routes to create or extract, wires Plumb in |
| `/plumb:create` | A new project | Product interview → design decisions → 2–3 directions → the design system → key screens |
| `/plumb:extract` | A project with UI already | Inventory of every value in use → token groups you confirm → the same design system and a prototype of every route |
| `/plumb:prototype` | A new or changed screen, tab, flow or interaction | 2–3 variants, each clickable with every state → you pick and approve → joins the main prototype |
| `/plumb:tour` | A demo, training or onboarding walkthrough | A custom walkthrough in guide or play mode, plus a shareable offline page |
| `/plumb:audit [fix \| improve]` | Any time | Rules, contrast, drift, prototype fidelity and an agent review; `fix` repairs with your OK; `improve` makes it better |
| `/plumb:ux` | After building a screen or flow | Deep UX review against the prototype, UX rules, heuristics, accessibility and visual polish |
| `/plumb:update` | The design changes | Tokens, components, a new platform, the audit's system suggestions; regenerate, record, audit |
| `/plumb:upgrade` | Plumb has a new version | Brings the project's copied files and settings up to the plugin's version, what's new first |
| `/plumb:status` | A health check | Read-only: versions, stale files, audit counts, prototype state, checks, the next step |
| `/plumb:feedback` | Plumb itself got something wrong | Plumb mistakes only: the agent records each in `~/.plumb/feedback/` (outside the project); typed, it reports them grouped and drafts issue text, never sent |

## Hooks

Three hooks run in both tools, only in projects with a `PLUMB.md`: a status line at session start; a check before each
edit and shell write (refuses hand edits to, or removal of, generated files and Plumb's own files, a new page with no approved
prototype, and an edit that adds design-system errors); and an end-of-turn check of the files changed in the session,
which stops the agent once when there are new errors. Switch them in `PLUMB.md` (`Edit check`, `End-of-turn check`,
`Prototype sync`). They run only the plugin's own scripts, never the copies in a project (see SECURITY.md, "Trust
boundary"), and fail open; a hook that fails open (a crash, a timeout) writes one line to `~/.plumb/feedback/hooks.md`
for `/plumb:feedback` (Plumb mistakes only, never in the project). Session start also points the agent there: Plumb
mistakes → `/plumb:feedback`. In Copilot CLI, refusals arrive as a "deny" answer with the same reason; whether the
end-of-turn check can make Copilot continue depends on its `agentStop` support, and where it can't, the edit check is
the hard guard there.

## Effective HTML (optional)

Plumb uses the [Effective HTML](https://github.com/plannotator/effective-html) skills (`design-artifact`, `html`,
`html-prototype`) when they are installed in the session. They add craft guidance (a deliberate palette and type
pairing, real hierarchy, nothing generic-looking) to the pages an agent writes: the create directions, the prototype
variants and screen files, the extract before/after page and the UX review page.

**Without them** nothing breaks: Plumb follows its built-in quality bar ("The quality bar" in
[reference/prototypes.md](reference/prototypes.md)) and its own directions template (`templates/directions.html`).
Every page still opens offline, in light and dark. `/plumb:init` says whether they are available and `/plumb:status`
reports it.

**To add them**, run these yourself in Claude Code (from Effective HTML's README; Plumb never installs anything):

```
/plugin marketplace add plannotator/effective-html
/plugin install plannotator-effective-html@effective-html
```

Copilot CLI and other agents: see [Effective HTML's README](https://github.com/plannotator/effective-html#install)
for how to install it there.

Every script command and flag for agents: [reference/scripts.md](reference/scripts.md); every audit rule:
[reference/rules.md](reference/rules.md). Full docs, design and source: https://github.com/Zidane786/plumb
