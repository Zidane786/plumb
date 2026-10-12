# Security policy

Please report security problems **privately** through GitHub:
**Security → Report a vulnerability** on https://github.com/Zidane786/plumb
(private vulnerability reporting is enabled). Don't open a public issue for security bugs.

Useful areas to look at: the hooks (`plugins/plumb/hooks/`), which read tool input and can block
edits (see "Trust boundary" below), and the scripts Plumb copies into projects (the token generator and the audit), which read
and write files in the project.

## Trust boundary

- **Hooks run only the plugin's installed code.** The session start, pre-edit and end-of-turn hooks import and run
  the scripts that ship with the plugin (`plugins/plumb/assets/skill/scripts/` in the installed plugin), never the
  copies in a project's design-system skill (`.claude/skills/<project>-design-system/scripts/`). A project is only
  read as data: `PLUMB.md`, the tokens JSON, `screens.json`, the screen files and the source files. Opening a
  repository, or editing in it, can never make a hook run that repository's code. When a project's copies are a
  different version, the hooks say so ("run /plumb:upgrade") and still check with the plugin's own scripts.
- **A project's copied scripts run only when someone runs them on purpose:** a Plumb command such as `/plumb:audit`,
  `make tokens` / `make design-audit`, or the project's CI. They are ordinary code in that repository.
- **A cloned repository's scripts are that repository's code.** Before running a cloned repo's design-system scripts
  (or a command that runs them), review them as you would any script in a repo you don't trust yet;
  `/plumb:upgrade` replaces them with the plugin's own copies.

You'll get an answer as soon as possible; fixes are released as a new plugin version with a
CHANGELOG entry.
