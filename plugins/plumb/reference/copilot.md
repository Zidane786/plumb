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
  If it is not available, ask in plain text with numbered options and wait for the answer.
- **Hooks:** the same three hooks run in both (session start, edit check before edits and shell writes, end-of-turn
  check). In Copilot CLI edits arrive as `apply_patch` text, input uses `toolName`/`toolArgs`, a refusal is a
  `{"permissionDecision": "deny", …}` answer on stdout (Copilot hides exit-2 stderr), and session start returns
  `{"additionalContext": …}`. Whether the end-of-turn check can make Copilot continue depends on Copilot's `agentStop`
  support; where it cannot, Copilot shows the end-of-turn summary only and the edit check remains the hard guard.
- **Browser tool:** if the Copilot session has no browser tool, `/plumb:ux` and `/plumb:audit` use
  `scripts/screenshot.py` (a Chrome, Edge or Chromium already installed) or skip the visual part with a note.

## Windows needs Python

Plumb's scripts and hooks are Python 3.9+ standard library only; nothing else is installed. On Windows the launcher
tries `py -3`, then `python`, then `python3`; the hooks have a `powershell` command for Copilot on Windows and a
`run.cmd` launcher. If no Python 3.9+ is found the hooks fail open (they never block work) and the skills say so: ask the
user to install Python from python.org or the Microsoft Store and wait; Plumb never installs it. Record the command that
works in `PLUMB.md` (`Python: \`py -3\``); every skill and the Makefile use it.
