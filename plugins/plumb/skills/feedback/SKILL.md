---
name: feedback
description: "Record a mistake in Plumb itself: a Plumb script, hook, skill, template or doc that gave a wrong, incomplete or confusing result you had to correct. Not for the project's own design issues — those are audit findings. Writes one Markdown file per Plumb mistake to ~/.plumb/feedback/, outside the project. When the user types /plumb:feedback it reports every Plumb mistake recorded on this machine (all projects, plus the hooks' own failures), grouped by script, function and category, and drafts GitHub issue text for Plumb that is never sent."
argument-hint: "[report | log <what went wrong>]"
---

# /plumb:feedback — Plumb's own mistakes, recorded and reported

**Plumb mistakes only.** The test: **would fixing this mean changing Plumb, not the project?** Yes → record it here.
No → it goes elsewhere: the project's design issues (a raw colour, an off-scale size, drift, a contrast failure) are
audit findings → `/plumb:audit`; a design choice → the decision log (`docs/design/decisions.md`); the project's own
bugs → its own tracker. Two examples:

- **Feedback:** `detect.py` proposed the UI files `src/**` in a monorepo whose UI is in `frontend/src/` (0 files
  matched); you corrected it to `frontend/src/**` (48 files). Fixing that means changing `detect.py`.
- **Not feedback (audit):** a hard-coded `#123456` in `app/page.tsx`. Fixing that means changing the project.

**In scope:** a script's wrong or incomplete result that you corrected (`detect.py`, `scaffold.py`, `build-tokens.py`,
`audit.py`, `build-prototype.py`, `screenshot.py`, `version.py`, `kiro.py`); a hook's wrong refusal, missed refusal,
crash or timeout that failed open, or confusing message; a skill step that was unclear, wrong or missing; a template
or doc that disagrees with what the code does; a quirk of one CLI (Claude Code, Copilot CLI, Kiro).
**Out of scope:** the project's design issues, decisions, the project's own bugs, and its source code: a record holds
only paths, `file:line`, the repo's shape and short exact text, never a source dump and never a secret (no tokens,
keys, passwords, environment values or customer data).

**Rules.** Questions (report mode) go **one at a time** through the question tool, options with the recommendation
first marked "(Recommended)" and why. **What the user confirms goes inside the question** (its text, or the
recommended option's preview), never only in a message before it: Claude Code can hide that text; Copilot CLI's ask
tool takes it in the question text. Never install or download anything; if something is missing, ask the user and
wait. **The log lives outside the project and is never written into the project:** `~/.plumb/feedback/`
(`%USERPROFILE%\.plumb\feedback\` on Windows). Nothing leaves the machine: no issue is ever sent, no `gh` command run.
Never write `setup-in-progress`; this skill writes no other file (clean up your own files if you made any).
**Scripts give evidence, not answers:** every skill checks each script result against the code and shows what it
changed, marked `(corrected: <why>)` / `(added: <why>)`, inside the question
([interview.md](../../reference/interview.md), "Scripts give evidence, not answers"). When the script was wrong, the
correction stays in the project; the Plumb mistake behind it is recorded here.

## Step 0: context and mode

1. `ROOT` = `${CLAUDE_PLUGIN_ROOT}` (filled in by Claude Code or Copilot CLI). If it still reads literally, use this
   skill's base directory (printed when the skill loads) + `/../..`, made absolute. Check that
   `<ROOT>/.claude-plugin/plugin.json` exists; if not, resolve again, never guess. Its `version` is the Plumb version.
2. **Project root `<root>`:** the absolute path of the folder holding `PLUMB.md` (the folder the session opened in,
   else the nearest folder above it); none is fine (a setup that failed before `PLUMB.md` existed). Read a project's
   files only under `<root>`, never from a path you remember. **FEEDBACK** = the home folder (`$HOME`;
   `%USERPROFILE%` on Windows) + `/.plumb/feedback/`, made absolute.
3. **Mode.** You loaded this skill yourself, after correcting a Plumb result → **Log**. The user typed
   `/plumb:feedback log <what went wrong>` → **Log**, for what they describe. The user typed `/plumb:feedback` or
   `/plumb:feedback report` → **Report**.

## Log: one Plumb mistake, one file

1. **Apply the test.** Not Plumb's mistake → write nothing; say in one line where it goes (above) and carry on.
2. **Gather the facts** you already have: the exact command and its output, the files you checked (with `file:line`
   and match counts), what was right. Read more only to pin the place in Plumb (`<ROOT>/scripts/…`,
   `<ROOT>/assets/skill/scripts/…`, `<ROOT>/hooks/…`, `<ROOT>/skills/…`): the function, rule or step.
3. **Write the file** `FEEDBACK/YYYY-MM-DD-<script>-<category>-<project>.md` (lower case, `a-z0-9-` only:
   e.g. `2026-10-13-detect-missed-structure-shop-web.md`; `<project>` = the project folder's name; the file exists →
   add `-2`, `-3`, …). Use your normal file-write tool: the CLI's permission mode governs it, Plumb adds no question.
   The same mistake again in the same project on the same day → add a "Seen again" line to that file instead.
4. **Say it in one line** ("Recorded a Plumb mistake: `<path>`") and go back to the task you were on. Never stop the
   user's flow for this, and never ask them to fix Plumb.

The record (every field; write "unknown" rather than guess):

```markdown
# <script, hook or skill> — <category>

- **When:** <YYYY-MM-DD> · Plumb <version> · <Claude Code | Copilot CLI | Kiro> · <OS and version>
- **Project shape:** <layout, stack, UI folders, platforms; e.g. monorepo, UI in frontend/ (Next.js · Tailwind v4)>
- **Where it failed:** <file> → <function | audit rule | skill step>   e.g. scripts/detect.py → ui_patterns()
- **Command:** `<the exact command>` (cwd: `<folder>`)
- **Given:** <the exact output, only the lines that matter, in a fenced block when longer than one line>
- **Expected:** <what was right, and how you know>
- **Evidence:** <file:line, match counts; e.g. `src/**` matched 0 files, `frontend/src/**` matches 48>
- **Repro:** <the smallest repo shape that shows it: folders, one or two files, the command>
- **Category:** <missed structure | wrong guess | false positive | missed problem | crash | timeout |
  confusing message | skill gap | docs mismatch | CLI quirk>
- **Suggested fix in Plumb:** <the file and the change, in a sentence>
- **Handled here:** <what you did in this project instead: the (corrected: …) you showed, a setting recorded>
```

A **crash** adds `- **Exit code:** <n>` and `- **Traceback (last lines):**` with the last 5–10 lines, fenced. A
**hook** mistake adds `- **Hook:** <event> · <tool> · <path> · exit <n> · <its message, exact>`. The hooks record
their own crashes and timeouts in `FEEDBACK/hooks.md`, one line each; you never edit that file.

## Report: what Plumb got wrong, most frequent first

1. **Read** every `*.md` in FEEDBACK (all projects), the lines of `hooks.md` and the index `handled.md`. FEEDBACK
   missing or empty → "No Plumb mistakes recorded yet (`<FEEDBACK>`)." Stop. Read only; never move or delete a record.
2. **Group** by **script or hook or skill · function, rule or step · category** (a `hooks.md` line: the hook · what
   its Given says · its category). For each group: the count, the projects, the first and last date, the Plumb
   versions and CLIs, one example's **Given vs Expected**. Most frequent first. Groups listed in `handled.md` go last,
   as "handled in <version>"; one seen again on a version at or after that → "came back", listed with the open ones.
3. **Show** the groups (up to 10; say how many more), then ask, one question at a time, what to do next:
   (a) Show a group in full (Recommended when one group stands out: name it and why) · (b) Draft a GitHub issue for
   Plumb · (c) Mark a group handled · (d) Filter by project, script or date · (e) Done. After each, ask again until
   the user picks Done.
   - **Show in full:** every record of the group, verbatim, with each file's path.
   - **Draft an issue:** a title (`<script>: <what goes wrong>`), then Given / Expected / Evidence / Repro / Suggested
     fix, the count, Plumb versions and CLIs. Projects only by shape, never by name. Text in your reply, **never
     sent**: the user may post it at `https://github.com/Zidane786/plumb/issues` themselves.
   - **Mark handled:** ask for the version that fixed it (Recommended: the installed Plumb version from step 0), then
     append `- <group> · handled in <version> · <date>` to `FEEDBACK/handled.md` (create it with a
     `# Plumb feedback: handled` title). Only the index changes; the records stay.
   - **Filter:** ask which (project, script, date range), then show the groups again for that slice.

**For Plumb's developers** (the full flow is in the usage guide): a group → a minimal repro → a failing test in the
Plumb repo → the fix → a patch release → mark the group handled. The files are plain Markdown: open the folder in any
editor too. Kiro runs this skill as `/plumb-feedback` (installed with the others by `kiro.py install`,
[kiro.md](../../reference/kiro.md)).
