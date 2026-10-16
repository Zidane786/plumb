# Plumb in GitHub Copilot CLI

Plumb is one plugin for Claude Code and GitHub Copilot CLI: the same `.claude-plugin/` manifest, skills, `reference/`
and Claude-format `hooks.json`. VS Code Copilot Chat is not supported.

## Install and update

```bash
copilot plugin marketplace add Zidane786/plumb
copilot plugin install plumb@plumb
```

Restart Copilot CLI (`/restart`, or quit and start it again). The commands are the same as in Claude Code:
`/plumb:init`, `/plumb:create`, `/plumb:prototype`, …

Update: `copilot plugin marketplace update plumb`, then `copilot plugin update plumb@plumb`, then restart. In Claude Code
the same steps are `claude plugin marketplace update plumb`, `claude plugin update plumb@plumb`, then `/reload-plugins`.
After a plugin update, `/plumb:upgrade` brings each project's copied files up to the new version (the session-start
check says when).

## What differs

- **Telling them apart:** `COPILOT_CLI=1` in the environment means Copilot CLI; otherwise it is Claude Code. Where a
  step differs, skills name both; follow the one for the tool you are in.
- **Plugin root:** skills resolve `ROOT` from `${CLAUDE_PLUGIN_ROOT}`; when it is not filled in, from the skill's base
  directory (printed when the skill loads) + `/../..`.
- **Skills location:** Copilot CLI loads skills from `.claude/skills`, `.github/skills`, `~/.copilot/skills` and
  `~/.agents/skills`, so the project's design-system skill in `.claude/skills/<project>-design-system/` works in both.
- **Questions:** both tools have a question tool; ask one question at a time with options and the recommendation first.
  What the user confirms (a block, summary, list, diff or mapping) goes in the question text itself, in full, in both
  tools (Claude Code can also take it as an option's preview); never only in a message before the question.
  Each checkpoint is a STOP: ask, then wait; no command or write before the answer. If there is no question tool, ask
  in plain text with numbered options, the content in the same message, and wait for the answer.
- **Hooks:** the same three hooks run in both (session start, edit check before edits and shell writes, end-of-turn
  check). In Copilot CLI edits arrive as `apply_patch` text (a header may be indented), input uses
  `toolName`/`toolArgs`, a refusal is a
  `{"permissionDecision": "deny", …}` answer on stdout (Copilot hides exit-2 stderr), and session start returns
  `{"additionalContext": …}`. The end-of-turn check makes Copilot continue: its `agentStop` answer arrives as a new
  prompt, which can override what the user said earlier. So when it stops you after the user said not to fix now,
  don't fix: report what it found and stop.
- **Browser tool:** if the Copilot session has no browser tool, `/plumb:ux` and `/plumb:audit` use
  `scripts/screenshot.py` (a Chrome, Edge or Chromium already installed) or skip the visual part with a note.

## Permission prompts

Copilot CLI ignores the `allowed-tools` line in a skill's frontmatter (Claude Code honours it), so every script run
asks for permission, and so does every file the agent writes with its edit tool (Copilot's default "manual" mode
auto-approves only reads). A permission prompt is never the user's answer to a Plumb checkpoint: the checkpoint
question comes first, then the command. The skills keep the count down:

- **One shell call per checkpoint.** Where a checkpoint runs several scripts, join them with `&&` in one shell call
  (e.g. the build and the audit, the dry run's checks, every `--map` of a step); `;` when each must run even after a
  failure (status runs all its checks in one call: one prompt). Windows PowerShell 5.1 has no `&&`: use `;` and read
  each output. Never join a checkpoint's action with the next checkpoint's (the dry run and the real scaffold are
  always two calls, with the user's OK between them).
- **Scratch files stay in the project:** `<root>/.plumb-tmp/` (git-ignored by its own `.gitignore`), never `/tmp`, a
  folder next to the repo or another session's folder, so no "Allow path access" prompt for them ("Scratch files" in
  [interview.md](interview.md)). Status writes no file at all.
- **Paths from the resolved roots:** every skill resolves the plugin root and `<root>` first and reads files only
  under them, so Copilot never asks for a path outside the project because of a guessed path.
- **Routes as one argument:** `--route=/`, never a separate `/` after `--route`; Copilot reads a bare `/` as a path
  and offers to allow access to it (and "remember for this session" would grant the whole disk).

**What to expect** (manual mode, batched as above): `/plumb:init` with create or extract asks for about 10–15 script
runs (detect, the dry run, the real scaffold, the stylesheet check, build + audit, the overrides, each contrast
rebuild, the component audit, the screens' map, `--verify`), plus one prompt per file the agent writes with its edit
tool (the directions or extract page, the skill's documents, components, screen files, `PLUMB.md`, `AGENTS.md`,
`Makefile`: often 15–25), plus one "Allow path access" for the plugin folder when it sits outside the project.
`/plumb:status` asks once; `/plumb:audit` two or three times.

**Fewer prompts: the user's choice.** The agent never changes Copilot's permissions and never suggests broader ones
than these. Copilot has no setting that pre-allows only Plumb's scripts: its `shell(…)` permission matches the
command's name (`python3`), not the script. What the user can do:

- answer "Yes, and remember … for this session" to a prompt (per command or path, this session only);
- start Copilot with `--add-dir <plugin folder>` (e.g. `~/.copilot/installed-plugins/plumb/plumb`): no "Allow path
  access" for the plugin's scripts and references;
- start Copilot with `--allow-tool 'shell(python3)'` (or `shell(python)`, `shell(py)` on Windows): every command of
  that name runs without asking, not only Plumb's: their call. File writes still ask
  (`--allow-tool 'write'` would allow every write: not recommended for a setup that should be reviewed).

## Other live-test notes

- **"Skill not found: plumb:init".** Copilot's skill tool lists only skills the model may start. `/plumb:init`,
  `/plumb:create`, `/plumb:extract`, `/plumb:update` and `/plumb:upgrade` run only when typed
  (`disable-model-invocation: true`), so they are not in that list. Typing the command has already loaded the skill;
  when the model also calls its skill tool for it, Copilot prints `✗ skill(plumb:init) Skill not found` and the flow
  goes on. Harmless; those skills say they are already loaded so the model skips the call. Keeping them user-only is
  deliberate. (Copilot names plugin skills by their bare name, `audit`, unless two plugins share one: `plumb:status`.)
- **Exit 1 shows as "✗ Shell".** `audit.py` (and `--check`) exit 1 when they find errors or stale files: a result,
  not a crash. Read the output; don't retry.
- **Never probe servers.** For screenshots of built screens, ask the user for the dev server's URL; never probe with
  `curl`, `wget` or guessed `localhost` ports.
- **Slate** is mentioned only when the project has it (`kanban/board.py`); otherwise no Slate tickets are offered.

## Windows needs Python

Plumb's scripts and hooks are Python 3.9+ standard library only; nothing else is installed. On Windows the launcher
tries `py -3`, then `python`, then `python3`; the hooks have a `powershell` command for Copilot on Windows and a
`run.cmd` launcher. If no Python 3.9+ is found the hooks fail open (they never block work) and the skills say so: ask the
user to install Python from python.org or the Microsoft Store and wait; Plumb never installs it. Record the command that
works in `PLUMB.md` (`Python: \`py -3\``); every skill and the Makefile use it.
