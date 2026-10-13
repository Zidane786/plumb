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
- **Git, with fixed overrides.** To see what changed in a session the hooks run git in the project: `rev-parse`,
  `status`, `diff --name-only`, `ls-tree`, `cat-file --batch` (the stored blob of a file's old text) and
  `config --get-regexp` (to list filter drivers). Git is found as an absolute path by walking `PATH` (empty, `.` and
  relative entries and anything inside the project are skipped; on Windows only `git.exe`), never in the project.
  All the git calls of one hook run share a 3-second budget. Without git (not found, failing, or over the budget) the
  snapshot falls back to modification times and the end-of-turn check still runs on them; a session whose snapshot
  was taken with git finds no changes then, and stays quiet. Every call passes these overrides, as `GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n` (and as
  `-c` for older git): `core.fsmonitor=false`, `core.untrackedCache=false`, `core.hooksPath=<null device>`,
  `diff.external=` (empty), `core.pager=cat`, `protocol.allow=never`, and an empty `clean`, `smudge` and `process` for
  every `filter.<name>` the configuration lists (any name; on git older than 2.31 a name containing `=` cannot be
  emptied, so git is not run there). Every call also has `--no-optional-locks`, `--no-pager`, `GIT_NO_LAZY_FETCH=1`
  (no fetch from a promisor remote), `GIT_TERMINAL_PROMPT=0` and `GIT_PAGER=cat`, drops `GIT_DIR`, `GIT_WORK_TREE`,
  `GIT_EXTERNAL_DIFF`, `GIT_SSH*` and `GIT_ASKPASS`, and `diff` adds `--no-ext-diff --no-textconv
  --ignore-submodules=all`. Commit ids from a snapshot reach git only after a hex check.
- **What that guarantee is, and is not.** The hooks run only the plugin's own code, plus git with the overrides above.
  Git still reads the repository's configuration (`.git/config` and what it includes) for every other key, as any
  git command run there does. The overrides cover every configured command we know these read-only calls can reach;
  they are not a sandbox. A repository whose `.git/config` you didn't create yourself (an archive, a shared folder, a
  devcontainer) deserves the same care as its scripts.
- **The session snapshots** live in a folder private to you in the OS temp folder: `plumb-<uid>`, created 0700 (on
  Windows `plumb` in the per-user temp folder, `%LOCALAPPDATA%\Temp`, where permission bits mean nothing). If that
  folder is a symlink (or on Windows any reparse point, such as a junction), someone else's, or writable by others
  (POSIX), the hooks keep no snapshot and never read, write or delete there. Snapshot files are written 0600 without following
  symlinks; cleanup only removes your own regular files in that folder. A snapshot's commit hash is checked before it
  reaches git.
- **The feedback log** (Plumb's own mistakes, for Plumb's developers) lives outside every project, in
  `~/.plumb/feedback/` (`%USERPROFILE%\.plumb\feedback\` on Windows). Only a hook that failed open (a crash, a plugin
  script it cannot load, a timeout) in a project with a `PLUMB.md` writes there: one line appended to `hooks.md`, at
  most once a day for the same failure, never more than 512 KB in all. `~/.plumb` and `feedback/` are created 0700 and
  `hooks.md` 0600, without following symlinks; if either folder is a symlink (or on Windows any reparse point),
  someone else's, or writable by others (POSIX), or `hooks.md` is a symlink, nothing is written. The line holds the
  hook, the Plumb version, the CLI, the OS, the project folder's name, the event, tool and project-relative path, and
  the failure message (cut to one short line); never file contents or the shell command. A problem with the log never
  fails or blocks a hook. Nothing in it leaves the machine: `/plumb:feedback` reads it and drafts issue text that you
  post yourself, if you want to.
- **Windows launcher.** `hooks/run.cmd` sets `NoDefaultCurrentDirectoryInExePath`, so cmd.exe never runs a `py`,
  `python` or `python3` found in the project folder instead of the one on `PATH`.
- **A project's copied scripts run only when someone runs them on purpose:** a Plumb command such as `/plumb:audit`,
  `make tokens` / `make design-audit`, or the project's CI. They are ordinary code in that repository.
- **A cloned repository's scripts are that repository's code.** Before running a cloned repo's design-system scripts
  (or a command that runs them), review them as you would any script in a repo you don't trust yet;
  `/plumb:upgrade` replaces them with the plugin's own copies.

You'll get an answer as soon as possible; fixes are released as a new plugin version with a
CHANGELOG entry.
