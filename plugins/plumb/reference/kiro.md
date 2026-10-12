# Plumb in Kiro

**Kiro: unverified until the live check.** Plumb's Kiro support is built and tested from Kiro's documented formats
(IDE and CLI v3); the hooks file schema, the stdin fields, which exit code blocks, the shell that runs a hook command on
Windows, and whether the CLI reads the global skills folder are confirmed by the first live Kiro run.

## Install, update, remove

Kiro has no plugin marketplace. With Plumb installed in Claude Code or Copilot CLI (or a checkout of the Plumb repo),
the user runs, from any folder:

```bash
python3 "<ROOT>/scripts/kiro.py" install                      # ~/.kiro: skills (Kiro IDE) + hooks (Kiro CLI)
python3 "<ROOT>/scripts/kiro.py" install --project <folder>   # also the workspace: skills + hooks (IDE and CLI)
python3 "<ROOT>/scripts/kiro.py" uninstall [--project <folder>]
```

| Flag | Does |
|---|---|
| `install` | Writes `<home>/.kiro/skills/plumb-<name>/SKILL.md` for every skill and `<home>/.kiro/hooks/plumb.json`. |
| `uninstall` | Removes only the files `kiro.py` installed (each carries "installed by Plumb's kiro.py"); never the user's own skills or hooks. |
| `--project DIR` | Also that Kiro workspace: `DIR/.kiro/skills/plumb-<name>/` and `DIR/.kiro/hooks/plumb.json`. |
| `--home DIR` | The folder holding `.kiro` (default: the user's home). |
| `--yes` | Write or remove without asking. Without it, `kiro.py` lists every path and asks `[y/N]`; with no terminal it writes nothing and prints the exact command with `--yes`. |

It never downloads, installs or runs anything, and refuses to overwrite a file it did not write. It writes into the
user's home folder: an agent tells the user the command and never runs it for them. After updating the Plumb plugin,
run `install` again (the copies point at the plugin's folder); a hook whose plugin folder is gone exits 0 and never
blocks Kiro.

## What differs

- **Commands** are `/plumb-init`, `/plumb-create`, … (Kiro skill names cannot hold `:`). The copies name the plugin
  folder as `ROOT` and link the plugin's `reference/`.
- **Steering:** Kiro reads `AGENTS.md`, so Plumb's "read before you work" row applies; `/plumb-init` can also write
  `.kiro/steering/plumb.md` ([wire-in.md](wire-in.md)). The project's design-system skill stays in one place.
- **Hooks:** the same three scripts. `SessionStart` → session start (plain text), `PreToolUse` with the matchers `write`
  (`fs_write`: create, str_replace, insert, append) and `shell` (`execute_bash`) → the edit check, `Stop` → the
  end-of-turn check (`{"decision": "block", "reason": …}`). A refusal is exit 2 with `error:` / `fix:` on stderr.
  The home hooks stand down in a workspace that has its own Plumb hooks file, so nothing runs twice.
