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
  read as data: `PLUMB.md`, the tokens JSON, `screens.json`, the screen files and the source files. When a project's
  copies are a different version, the hooks say so ("run /plumb:upgrade") and still check with the plugin's own
  scripts.
- **Git, read-only.** To see what changed in a session the hooks run `git rev-parse`, `git status`, `git diff
  --name-only`, `git show` and `git config --get-regexp` (to list filter drivers) in the project. Every call turns off
  the commands a repository's config can name: `core.fsmonitor`, `core.hooksPath` (set to the null device),
  `diff.external` and `--no-ext-diff`, `--no-textconv`, the pager (`--no-pager`, `GIT_PAGER=cat`), every
  `filter.<name>.clean` / `smudge` / `process` the config lists (emptied), submodules (`--ignore-submodules=all`); it
  also passes `--no-optional-locks` and `GIT_TERMINAL_PROMPT=0`, and puts `--end-of-options` before revisions. Git
  itself still reads the repository's config for every other key (as any git command you run there does); none of the
  commands above runs anything those keys name, as far as git's documentation and Plumb's tests show.
- **The session snapshots** live in a folder private to you in the OS temp folder (`plumb-<uid>`, created 0700; on
  Windows the per-user temp folder). If that folder is a symlink, someone else's, or writable by others, the hooks
  keep no snapshot and never read, write or delete there. Snapshot files are written 0600 without following
  symlinks; cleanup only removes your own regular files in that folder. A snapshot's commit hash is checked before it
  reaches git.
- **Windows launcher.** `hooks/run.cmd` sets `NoDefaultCurrentDirectoryInExePath`, so cmd.exe never runs a `py`,
  `python` or `python3` found in the project folder instead of the one on `PATH`.
- **A project's copied scripts run only when someone runs them on purpose:** a Plumb command such as `/plumb:audit`,
  `make tokens` / `make design-audit`, or the project's CI. They are ordinary code in that repository.
- **A cloned repository's scripts are that repository's code.** Before running a cloned repo's design-system scripts
  (or a command that runs them), review them as you would any script in a repo you don't trust yet;
  `/plumb:upgrade` replaces them with the plugin's own copies.

You'll get an answer as soon as possible; fixes are released as a new plugin version with a
CHANGELOG entry.
