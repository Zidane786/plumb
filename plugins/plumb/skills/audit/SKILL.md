---
name: audit
description: Audit the project's UI against its design system - run audit.py (every rule, contrast in light and dark, drift, prototype fidelity, suggestions) with the HTML report, then an agent review for what no rule expresses (marked agent review in the report), with screenshots of built screens beside their prototype when a browser is available; offers Slate tickets. Modes - no argument reports only; "fix" repairs errors and warnings group by group with the user's OK until clean (prototype first for visual changes); "improve" ranks improvements to the screens and the system itself and builds the ones the user picks (prototype first; system changes through /plumb:update). Use when asked to audit, check, review the design system, fix design issues or improve the UI.
argument-hint: "[fix | improve] [paths]"
---

# /plumb:audit [fix | improve] — check the UI against the design system

**The script is the floor, not the ceiling.** `audit.py` checks everything that can be written as a rule, the same way
every time (the hooks and CI rely on it). Then you review what no rule expresses. Rules and how to fix each:
[`rules.md`](../../reference/rules.md). Commands: [`scripts.md`](../../reference/scripts.md). Prototype rules: [`prototypes.md`](../../reference/prototypes.md). Copilot CLI differences: [`copilot.md`](../../reference/copilot.md).

**Rules.** Questions go **one at a time** through the question tool, options with the recommendation first marked "(Recommended)". **Nothing is
written without the user's OK:** the report, its review file and the screenshots are the output this command was asked
for; any other write (a code fix, a screen file, a rule, a decision) is shown first (what and where) and made only on a
yes. Never install or download anything; if something seems missing, ask the user and wait. Check both themes unless
`Themes: light-only`. Never edit generated files or Plumb's own scripts and templates (regenerate; propose
rule changes upstream). Anything that changes how a screen looks goes through the prototype first. **Never run
`--approve` (or record an approval) without the user's explicit yes to that screen** in this conversation.
**End-of-turn check:** if Plumb's end-of-turn check stops you after the user said not to fix now (or chose report
only), don't fix: report and stop.
**Scripts give evidence, not answers:** check each script result against the code (search and read any time),
correct or add to it (marked `(corrected: <why>)` / `(added: <why>)`) and show that inside the question before the
user decides; a script that is wrong in a way that will recur → say so and suggest the fix to Plumb
([interview.md](../../reference/interview.md), "Scripts give evidence, not answers").
When a Plumb script or hook is wrong and you correct it, record the Plumb mistake with /plumb:feedback. **What the user
confirms goes inside the question** (its text, or the recommended option's preview when the tool has one), never only in
a message before it: Claude Code can hide that text; Copilot CLI's ask tool takes it in the question text. **Investigate
first** (interview.md, "Investigate first"): gather every fact the code can answer before asking; what the code shows is
a `found: … (file:line)` to confirm, never an open question.

```
 audit.py --html ─▶ visual fidelity (browser?) ─▶ agent review ─▶ --add-review ─▶ summary + offers ─▶ STOP
 fix:     groups of errors/warnings ─▶ show ─▶ ask ─▶ apply ─▶ re-run … until clean
 improve: ranked plan (screens + system) ─▶ user picks ─▶ prototype first ─▶ approval ─▶ build; system → /plumb:update
```

## Step 0: context

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute. Check that `<ROOT>/reference/scripts.md`
   exists; if not, resolve again, never guess. Read Plumb's references only as `<ROOT>/reference/<file>`.
2. **Project root `<root>`:** the absolute path of the folder holding `PLUMB.md` (the folder the session opened in,
   else the nearest folder above it). Every path below is `<root>/…`; **SKILL** (step 3) is `<root>/<Design system:>`,
   made absolute; read the project's references as `SKILL/references/<file>`, never from a path you remember.
   Scratch files: `<root>/.plumb-tmp/` only (its `.gitignore` first); clean up your own files when the command
   ends; never write `setup-in-progress` (the setup marker); never `/tmp` or outside `<root>`.
   Missing → offer `/plumb:init`; with no design system yet the audit can still run
   in inconsistency-only mode on the folders the user names (ask which).
3. From `PLUMB.md`: `Design system:` (**SKILL**), `Role:`, `Python:` (**PY**, `python3` when unset), `Themes:`.
   **docs** (the docs folder): the tokens file's `$extensions.plumb.docs_dir`, default `docs/design`, which is
   where the scripts write. If `PLUMB.md`'s `## Prototype` `Main:` path sits in another folder, say so and ask
   the user which is right, then fix the other one after their OK (`<ROOT>/reference/scripts.md`, "The docs folder").
   `Role: linked` → run the home repo's `audit.py` on this repo's UI folders:
   `PY <SKILL>/scripts/audit.py <ui folders> --html <docs>/audit-YYYY-MM-DD.html`.
4. `PY "<ROOT>/scripts/version.py" --project "<root>" --plugin "<ROOT>" --json`: `older` → say once that `/plumb:upgrade` is
   available, then continue.
   `same` with `files_differ`: say once that `/plumb:upgrade` can refresh Plumb's files (they differ from the plugin's).
5. The mode is the first argument: none → report only; `fix`; `improve`. Other arguments are paths to check.

## Step 1: run the script

`PY SKILL/scripts/audit.py [paths] --html`. It prints every finding (`file:line: severity rule: message` + `fix:`), a
summary, and writes `<docs>/audit-YYYY-MM-DD.html`. Exit 0 = no errors; **exit 1 means errors found, not a crash**
(Claude Code shows "Error: Exit code 1", Copilot CLI "✗ Shell": read the findings, don't retry or debug the script);
2 = bad input or nothing checked: show the `error:` and do what its `fix:` says (or ask). No tokens yet → it runs in
inconsistency-only mode by itself. **Read the findings critically before you report or fix them:** is each real, is
the rule right here, is the fix right? A burst of one rule (hundreds of palette-colour errors right after setup)
usually means a setup gap (a setting such as `reset_palette`, a mapping, a wrong `UI files:` pattern), not app debt:
say so and propose fixing the gap first. A false positive that will recur → offer to add the path to `PLUMB.md`'s
`Allowed raw values:` (after the user's OK) and suggest reporting the rule to Plumb. `PLUMB.md` has no `Routes:` line
→ say the prototype checks cannot see the app's pages and recommend `/plumb:init` to record the route roots.

## Step 2: visual fidelity (when a browser is available)

For each **built** screen in `<docs>/prototype/screens.json` (status `built`, with a route): screenshot the built route
and its prototype screen at the same width and theme (1280 and 390 px; light and dark), and compare: missing screens or
states, different components or copy, layout drift. Pixel-perfect matching is not the goal: a layout difference worth
flagging is a block that is missing, added or moved (a different order or column), a different component, or a clearly
different size or spacing; anti-aliasing, font hinting and sub-pixel shifts are not.

- Browser, first available: the agent's own browser tool → `PY "<ROOT>/scripts/screenshot.py" <url-or-file> --out <png>
  --width <w> --theme <light|dark>` (a Chrome, Edge or Chromium already installed) → none: `screenshot.py` exits 3 with
  `note: visual comparison skipped: no browser found` and a `fix:` line; put both in the summary and go on.
- The built route needs the app running: ask the user once for the dev server's URL; not running → skip the built
  side. **Never probe for a server yourself** (no `curl`, `wget`, port scans or guessed `localhost` URLs).
- Prototype screens: `<docs>/prototype.html#screen-<id>/<state>`. Shots go in `<docs>/audit-YYYY-MM-DD/`.

## Step 3: agent review

Read the screens in scope (the paths given, else every screen in `screens.json` and the UI files changed since the last
audit) against `SKILL/design.md`, `SKILL/references/ux.md`, `vocabulary.md` and their prototype screens. Look for what
no rule expresses: hierarchy broken while still using tokens, two screens solving the same thing differently, words off
the vocabulary, an unhelpful empty or error state, a missing state the flow needs, something that looks wrong in dark
mode, the layout drift from step 2. Each finding: severity (`error` must change, `warn` should, `suggest` could be
better), file and line (line optional), message, fix, why. Don't repeat what a rule already reported.

Write them to `<docs>/audit-YYYY-MM-DD.review.json` (a JSON list, format in `<ROOT>/reference/rules.md`) and run
`PY SKILL/scripts/audit.py [paths] --html --add-review <docs>/audit-YYYY-MM-DD.review.json`: the report gets an
**Agent review** section, each finding marked so; the exit code stays the rules'. The review file is kept with the
report as its record.

**Recurring problems:** when the same kind of finding shows up in 3+ places (or in the previous audit's review file
too), propose it to the user as a new rule (`<ROOT>/reference/rules.md`, "Proposing a new rule"): on a yes, write it
into `design.md` or `ux.md`, and offer to propose it to Plumb as an audit rule.

## Step 4: summary (every mode), then stop unless fix or improve

Under 200 words: the verdict (pass / errors), counts (errors, warnings, suggestions, agent review), the top issues
grouped by rule with how many, the three highest-impact improvements, the visual note if it was skipped, and the report
path. Then offer, one question: `/plumb:audit fix` (when there are errors or warnings) · `/plumb:audit improve` (when it
passes) · Slate tickets (only when `<root>/kanban/board.py` exists; otherwise never mention Slate) · nothing now.

**Slate tickets** (only when `kanban/board.py` exists and the user says yes): group findings by area (one ticket per
area or rule group, not per line), show the list, ask, then write them only with Slate's `board.py`
(`python3 kanban/board.py new --help` for the flags; `add --dry-run --file <batch>` for several, then `add`), with the
Python command from `SLATE.md`. Each ticket: what to fix, the files, the fix, "the audit exits 0" in done-when
(`make design-audit` when the Makefile has it, else the audit command from `PLUMB.md`); a ticket that changes a
screen starts with "prototype approved" and links `<docs>/prototype.html#screen-<id>`. Never edit `kanban/` yourself.

## Mode `fix`: repair errors and warnings, with the user's OK

1. Group the errors and warnings by what fixes them, largest first (e.g. "12 raw colours → colour tokens",
   "3 screens drifted from the prototype", "2 contrast failures"). For each group: show how many, the files, the fix,
   one before → after example; ask "Apply this group?" — Apply / Show every change first / Skip.
2. Apply it:
   - code-level fixes (raw values → the token the fix names, `outline-none`, inline styles, emoji, icon library): the
     group's yes covers exactly the changes shown; when a value has no close token, don't invent one: collect it for
     `/plumb:update`.
   - `generated-drift`: `PY SKILL/scripts/build-tokens.py` (never edit the generated file).
   - token-level (`contrast`, `missing-dark-value`, a missing token): these change the system; list them and ask the
     user to run `/plumb:update` (only the user starts it).
   - prototype fidelity: `screen-drift` / `synced-from-code` → update the screen file to show the code, ask, then
     `build-prototype.py --approve <id>` (or `--synced`); `route-not-prototyped` → `/plumb:prototype <screen>`;
     `screen-unapproved` → show the screen, ask, `--approve`.
   - **anything that changes how a screen looks** → its screen file first, the user approves, then the code.
3. Re-run `PY SKILL/scripts/audit.py [paths]` after each group; repeat until it exits 0 and the warnings are fixed or
   the user chose to keep them. Then step 1's `--html` (with the review) for the final report, `git diff --stat`, and a
   short summary. The user commits.

## Mode `improve`: make the screens and the system better

1. It needs a passing audit: errors left → offer `fix` first. Investigate first (interview.md): read the screens,
   layouts, components and `ux.md` yourself before proposing anything; ask only what the code cannot tell.
2. Build a ranked plan from: the report's Improvements (suggestions, ranked by impact), the agent review, and a design
   pass across the whole product (hierarchy, spacing rhythm, consistency between screens, every state, dark-mode polish,
   accessibility beyond AA). Include **the design system itself** when the findings show it should change: a missing or
   mergeable token, a component spec that needs a variant, a `ux.md` or `design.md` rule that real screens keep breaking
   for a good reason. Rank by impact on the key tasks and how many screens it reaches; say the effort.
3. Add the plan to the report as agent-review `suggest` findings (`--add-review`), and show it as a numbered list.
   **A system proposal** is an entry whose `file` is a path under SKILL: the tokens file
   (`SKILL/assets/tokens/<project>.tokens.json`), `SKILL/references/components.md`, `SKILL/references/ux.md` or
   `SKILL/design.md`. That is exactly what `/plumb:update` reads as the audit's system suggestions, so write system
   changes that way (message: the change; fix: the proposed value or wording; why: the evidence) and screen changes
   with the screen's or the code's path.
4. Ask which items to do (multi-select; recommend the top ones). For each picked item:
   - a screen change: prototype first (`/plumb:prototype` flow: screen file, user approval, `--approve`), then build it
     to match, then audit;
   - a system change (tokens, component specs, `ux.md`/`design.md` rules): it is already a system proposal in the review
     file (step 3); ask the user to run `/plumb:update`, which applies the audit's system suggestions one at a time,
     regenerates, refreshes the prototypes, records the decision and re-runs the audit;
   - or a Slate ticket instead (only when `kanban/board.py` exists).
5. Every change made is recorded in `<docs>/decisions.md` (`<ROOT>/templates/decision-entry.md`). End with the audit
   run again, `git diff --stat` and a summary. The user commits.
