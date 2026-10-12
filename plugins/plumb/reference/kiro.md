# Plumb in Kiro

**Kiro: unverified until the live check.** Plumb's Kiro support is built and tested from Kiro's documented formats
(IDE and CLI v3). The first live Kiro run confirms: the hooks file schema, the stdin fields, which exit code blocks, the
shell that runs a hook command on Windows, whether the Stop decision JSON makes Kiro continue, and which skills folder
each Kiro (IDE, CLI) reads.

## Install, update, remove

Kiro has no plugin marketplace. With Plumb installed in Claude Code or Copilot CLI (or a checkout of the Plumb repo),
the user runs, from any folder, one scope at a time:

```bash
python3 "<ROOT>/scripts/kiro.py" install                      # ~/.kiro only: skills (Kiro IDE) + hooks (Kiro CLI)
python3 "<ROOT>/scripts/kiro.py" install --project <folder>   # that workspace only: skills + hooks (IDE and CLI)
python3 "<ROOT>/scripts/kiro.py" uninstall [--project <folder>]
```

| Flag | Does |
|---|---|
| `install` | Writes `.kiro/skills/plumb-<name>/SKILL.md` for every skill and `.kiro/hooks/plumb.json`, in the home folder (or the project with `--project`). Removes marked copies of skills this Plumb no longer has. |
| `uninstall` | Removes only the files `kiro.py` installed in that scope (each carries "installed by Plumb's kiro.py"); never the user's own skills or hooks. |
| `--project DIR` | That Kiro workspace instead of the home folder: `DIR/.kiro/skills/plumb-<name>/` and `DIR/.kiro/hooks/plumb.json`. |
| `--home DIR` | The folder holding `.kiro` (default: the user's home). Not with `--project`. |
| `--yes` | Write or remove without asking. Without it, `kiro.py` lists every path and asks `[y/N]`; with no terminal it writes nothing and says `ask the user: run … --yes yourself, or tell me to run it`. |

It never downloads, installs or runs anything. It refuses to overwrite a file it did not write, or to write through a
symlink (`.kiro` itself included). It writes into the user's folders: an agent tells the user the command and runs it
only when the user says so.

**After updating the Plumb plugin**, run `install` again: the copies point at one plugin folder. The Kiro session start
says so when a newer Plumb sits next to that folder ("Plumb X is installed but Kiro still uses Y: ask the user to run
… kiro.py install"). When the folder is gone, every hook exits 0 (Kiro blocks a tool on any non-zero exit) and the
session start prints one line: the checks are off, run `kiro.py install` again.

## What differs

- **Commands** are `/plumb-init`, `/plumb-create`, … (Kiro skill names cannot hold `:`); the hooks write them that way
  in every refusal and nudge. The copies name the plugin folder as `ROOT`, link the plugin's `reference/`, and keep
  only Agent Skills front matter (`name`, `description`).
- **Steering:** Kiro reads `AGENTS.md`, so Plumb's "read before you work" row applies; `/plumb-init` can also write
  `.kiro/steering/plumb.md` ([wire-in.md](wire-in.md)). The project's design-system skill stays in one place.
- **Hooks:** the same three scripts, each command run with `--kiro` (the hook answers in Kiro's dialect).
  `SessionStart` → session start (plain text), `PreToolUse` with the matchers `write` (`fs_write`: create,
  str_replace, insert, append) and `shell` (`execute_bash`, `execute_cmd`) → the edit check, `Stop` → the end-of-turn
  check. A refusal is exit 2 with `error:` and `fix:` / `ask the user:` on stderr.
- **Stop:** the block is `{"decision": "block", "reason": …}` on stdout, exit 0. Kiro's docs show that JSON for CLI v3;
  elsewhere exit-0 stdout is only added to the agent's context, so the live check confirms the agent really continues.
  The report-only follow-up (`{"systemMessage": …}`) may show as raw JSON there.
- **Windows:** each command is `powershell -NoProfile -NonInteractive -EncodedCommand …` and a second line
  `exit $LASTEXITCODE` (the script is printed by `install`). It runs the launcher through cmd.exe and passes stdin,
  stdout and stderr through byte for byte with the hook's exit code (2 refuses), from cmd.exe, PowerShell 5.1 and 7
  and Git Bash alike (cmd.exe stops at the line break; the second line keeps the exit code under PowerShell and Git
  Bash); a launcher that is gone exits 0. PowerShell's start-up adds about 0.3 s per hook. No `-ExecutionPolicy Bypass`: it is not needed, and endpoint protection flags it.
- **Home and workspace:** Kiro CLI runs both hooks files side by side. A home hook stands down only where the
  workspace's own file (in the workspace root) runs the same plugin with that hook enabled; otherwise both run, which
  is never less safe.
- **Guarded:** the edit check refuses hand edits to the marked `.kiro/hooks/plumb.json` and `.kiro/skills/plumb-*/`
  (project and home), file edits, shell writes and removals (`rm`, `mv`, `Remove-Item`, …; paths under `~`, `$HOME`,
  `%USERPROFILE%` included) alike: change the checks in `PLUMB.md`, refresh with `kiro.py install`.
