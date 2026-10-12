#!/usr/bin/env python3
"""kiro.py: install Plumb's skills and hooks for Kiro (IDE and CLI v3), or remove them.

    kiro.py install   [--home DIR] [--project DIR] [--yes]
    kiro.py uninstall [--home DIR] [--project DIR] [--yes]

Kiro has no plugin marketplace, so this copies what Claude Code and Copilot CLI load from the plugin:

- every skill to <home>/.kiro/skills/plumb-<name>/SKILL.md (global: Kiro IDE) and, with --project, to
  <project>/.kiro/skills/plumb-<name>/SKILL.md (workspace: Kiro IDE and CLI). The copy is named plumb-<name> (the
  command is /plumb-<name>), `${CLAUDE_PLUGIN_ROOT}` becomes this plugin's absolute path, /plumb:<x> becomes
  /plumb-<x> and the links to reference/ point into the plugin;
- the hooks: <home>/.kiro/hooks/plumb.json (Kiro CLI) and, with --project, <project>/.kiro/hooks/plumb.json (the IDE reads
  workspace hooks), from kiro/plumb-hooks.json.tmpl: SessionStart -> session_start.py, PreToolUse (matchers write and
  shell) -> pre_edit.py, Stop -> stop_check.py, each run through this plugin's hooks/run.sh (run.cmd on Windows) by
  absolute path. A command whose launcher is gone (the plugin moved or was updated) exits 0, so it never blocks Kiro.
  The home file's commands carry --kiro-global: those hooks stand down in a workspace that has its own Plumb hooks
  file, so nothing runs twice (Kiro CLI runs global and workspace hooks side by side).

Every file written carries "installed by Plumb's kiro.py" (the SKILL.md as a comment, the hooks in each description):
install updates only such files and refuses to overwrite anything else; uninstall removes only such files (and a skill
folder left empty), never the user's own skills or hooks.

It prints every path it will write or remove, then writes only after --yes or a "y" typed at the prompt; without a
terminal and without --yes it writes nothing and says how to confirm. It never downloads, installs or runs anything.
After updating the Plumb plugin, run install again (the copies point at this plugin folder).

Kiro's formats are taken from its docs (# verify live: the live Kiro run confirms the hooks file schema, the shell
that runs a command on Windows, and whether the global skills folder is read by the CLI).

Exit codes: 0 done (or nothing to do), 1 the user said no, 2 refused (`error: ...` then `fix: ...` or `ask the user:
...`). Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATE = PLUGIN / "kiro" / "plumb-hooks.json.tmpl"
# The same constants as hooks/_hooklib.py (KIRO_MARK, KIRO_GLOBAL_ARG); tests/test_kiro.py keeps them in step.
KIRO_MARK = "installed by Plumb's kiro.py"
KIRO_GLOBAL_ARG = "--kiro-global"
WINDOWS = sys.platform == "win32"
SKILL_PREFIX = "plumb-"
# "(Claude Code and Copilot CLI fill this in ...). If it still reads literally ... + `/../..`, made absolute."
ROOT_FALLBACK = re.compile(r"\((?:Claude Code and Copilot CLI fill this in|filled in by Claude Code or Copilot CLI)"
                           r"[^)]*\)\.\s*If it still reads literally.*?(?:resolved to an absolute path|made absolute)\.",
                           re.S)


class KiroError(Exception):
    def __init__(self, what: str, then: str) -> None:
        super().__init__(f"error: {what}\n{then}")


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is not None:
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - leave an odd stream as it is
                pass


def interactive() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def plugin_version() -> str:
    try:
        doc = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))
        return str(doc.get("version") or "?")
    except (OSError, ValueError, AttributeError):
        return "?"


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_bytes().decode("utf-8-sig", "replace")
    except OSError:
        return None


# ---------------------------------------------------------------- what gets written


def root_text() -> str:
    """This plugin's absolute path as the skills show it (forward slashes on Windows too: Python and the shells take
    them)."""
    return PLUGIN.as_posix()


def kiro_skill(source: str, name: str, root: str, version: str) -> str:
    """A plugin skill's SKILL.md as Kiro's plumb-<name> skill."""
    text = source.replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?\n)---\n", text, re.S)
    if not m:
        raise KiroError(f"skills/{name}/SKILL.md has no front matter, so it cannot be installed for Kiro",
                        "fix: reinstall the Plumb plugin, then run this command again")
    front, body = m.group(1), text[m.end():]
    front = re.sub(r"(?m)^name:.*$", f"name: {SKILL_PREFIX}{name}", front, count=1)
    if not re.search(r"(?m)^name:", front):
        front = f"name: {SKILL_PREFIX}{name}\n" + front

    def kiroise(part: str) -> str:
        # The fallback for an unfilled ${CLAUDE_PLUGIN_ROOT} (the skill's base directory + /../..) is wrong for a copy
        # in .kiro/skills/: the path is written in instead.
        part = ROOT_FALLBACK.sub("(the Plumb plugin's folder, written in by kiro.py install).", part)
        part = part.replace("${CLAUDE_PLUGIN_ROOT}", root)
        part = part.replace("](../../", f"]({root}/")
        return re.sub(r"/plumb:(?=[a-z])", "/" + SKILL_PREFIX, part)

    mark = (f"<!-- {KIRO_MARK} (Plumb {version}, from {root}): kiro.py install updates this file, kiro.py uninstall "
            f"removes it; edit the plugin's skills/{name}/SKILL.md instead -->\n")
    return f"---\n{kiroise(front)}---\n{mark}{kiroise(body)}"


def _sh_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def hook_command(script: str, global_file: bool) -> str:
    """The command a Kiro hook runs: this plugin's launcher by absolute path, exit 0 when it is missing."""
    extra = f" {KIRO_GLOBAL_ARG}" if global_file else ""
    hooks = PLUGIN / "hooks"
    if WINDOWS:  # verify live: assumes Kiro runs a command through cmd.exe on Windows
        run = str(hooks / "run.cmd")
        if '"' in run or "%" in run:
            raise KiroError(f"the plugin folder {PLUGIN} has a \" or % in its path, which a Kiro hook command cannot "
                            "quote", "ask the user: move the Plumb plugin to a folder without \" or %, then run "
                            "kiro.py install again")
        return f'if exist "{run}" ("{run}" {script}{extra}) else (exit /b 0)'
    run = _sh_quote(str(hooks / "run.sh"))
    return f"[ -f {run} ] && exec sh {run} {script}{extra} || exit 0"


def _fill(node, values: dict, global_file: bool):
    if isinstance(node, dict):
        return {k: _fill(v, values, global_file) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, values, global_file) for v in node]
    if isinstance(node, str):
        m = re.fullmatch(r"\{\{RUN:([\w.-]+\.py)\}\}", node)
        if m:
            return hook_command(m.group(1), global_file)
        for key, value in values.items():
            node = node.replace("{{" + key + "}}", value)
    return node


def hooks_json(global_file: bool) -> str:
    try:
        tmpl = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KiroError(f"cannot read the plugin's {TEMPLATE.relative_to(PLUGIN).as_posix()} ({exc})",
                        "fix: reinstall the Plumb plugin, then run this command again") from None
    return json.dumps(_fill(tmpl, {"MARK": f"({KIRO_MARK}; kiro.py uninstall removes it)"}, global_file), indent=2, ensure_ascii=False) + "\n"


def skill_names() -> List[str]:
    return sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md"))


def plan_install(home: Path, project: Optional[Path]) -> List[Tuple[Path, str]]:
    root, version = root_text(), plugin_version()
    skills = []
    for name in skill_names():
        source = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        skills.append((name, kiro_skill(source, name, root, version)))
    out: List[Tuple[Path, str]] = []
    for base, global_file in ((home, True), (project, False)):
        if base is None:
            continue
        kiro = base / ".kiro"
        out += [(kiro / "skills" / f"{SKILL_PREFIX}{name}" / "SKILL.md", text) for name, text in skills]
        out.append((kiro / "hooks" / "plumb.json", hooks_json(global_file)))
    return out


# ---------------------------------------------------------------- ownership


def ours_skill(path: Path) -> bool:
    text = _read(path)
    return text is not None and KIRO_MARK in text


def ours_hooks(path: Path) -> bool:
    """A hooks file kiro.py wrote: every hook in it carries the mark."""
    try:
        doc = json.loads(_read(path) or "")
    except ValueError:
        return False
    hooks = doc.get("hooks") if isinstance(doc, dict) else None
    return bool(hooks) and isinstance(hooks, list) and all(
        isinstance(h, dict) and KIRO_MARK in str(h.get("description") or "") for h in hooks)


def ours(path: Path) -> bool:
    return ours_hooks(path) if path.suffix == ".json" else ours_skill(path)


def plan_uninstall(bases: List[Path]) -> List[Path]:
    out: List[Path] = []
    for base in bases:
        skills = base / ".kiro" / "skills"
        if skills.is_dir():
            out += [p for p in sorted(skills.glob(f"{SKILL_PREFIX}*/SKILL.md")) if p.is_file() and ours_skill(p)]
        hooks = base / ".kiro" / "hooks" / "plumb.json"
        if hooks.is_file() and ours_hooks(hooks):
            out.append(hooks)
    return out


# ---------------------------------------------------------------- the commands


def _arg(text: str) -> str:
    return text if re.fullmatch(r"[\w.@+/:\\-]+", text) else '"' + text + '"'


def again(action: str, args: argparse.Namespace) -> str:
    """The exact command to run this again with --yes."""
    python = os.environ.get("PLUMB_PYTHON") or ("py -3" if WINDOWS else "python3")
    parts = [python, _arg(str(Path(__file__).resolve())), action]
    if args.home:
        parts += ["--home", _arg(str(args.home))]
    if args.project:
        parts += ["--project", _arg(str(args.project))]
    return " ".join(parts + ["--yes"])


def confirmed(args: argparse.Namespace, action: str, question: str) -> Optional[bool]:
    """True to go on, False when the user said no, None when there is no one to ask (no terminal, no --yes)."""
    if args.yes:
        return True
    if not interactive():
        return None
    return ask(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def install(args: argparse.Namespace, home: Path, project: Optional[Path]) -> int:
    plan = plan_install(home, project)
    foreign = [p for p, _ in plan if p.exists() and not (p.is_file() and ours(p))]
    if foreign:
        listed = ", ".join(str(p) for p in foreign)
        raise KiroError(f"{listed} already exist{'s' if len(foreign) == 1 else ''} and {'is' if len(foreign) == 1 else 'are'} "
                        f"not Plumb's (no \"{KIRO_MARK}\" mark), so nothing was written",
                        "ask the user: move or rename it (it is theirs; Plumb never overwrites it), then run "
                        f"{again('install', args)}")
    print(f"Plumb {plugin_version()} for Kiro: install writes these {len(plan)} files:")
    for p, _ in plan:
        print(f"  {'update' if p.exists() else 'write'} {p}")
    ok = confirmed(args, "install", "Write these files?")
    if ok is None:
        raise KiroError(f"nothing was written: kiro.py writes into {home / '.kiro'}"
                        f"{' and ' + str(project / '.kiro') if project else ''} only when you confirm",
                        f"fix: {again('install', args)}")
    if not ok:
        print("nothing was written")
        return 1
    for p, text in plan:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    names = ", ".join(f"/{SKILL_PREFIX}{n}" for n in skill_names())
    print(f"Done: wrote {len(plan)} files. Restart Kiro (or start a new session) so it loads them.")
    print(f"Commands in Kiro: {names}.")
    print("After updating the Plumb plugin, run this install again; kiro.py uninstall removes these files.")
    return 0


def uninstall(args: argparse.Namespace, home: Path, project: Optional[Path]) -> int:
    bases = [home] + ([project] if project else [])
    plan = plan_uninstall(bases)
    if not plan:
        print(f"Plumb for Kiro: nothing to remove in {', '.join(str(b / '.kiro') for b in bases)}")
        return 0
    print(f"Plumb for Kiro: uninstall removes these {len(plan)} files (only the ones kiro.py installed):")
    for p in plan:
        print(f"  remove {p}")
    ok = confirmed(args, "uninstall", "Remove these files?")
    if ok is None:
        raise KiroError("nothing was removed: kiro.py removes files only when you confirm",
                        f"fix: {again('uninstall', args)}")
    if not ok:
        print("nothing was removed")
        return 1
    for p in plan:
        p.unlink()
        if p.name == "SKILL.md":
            try:
                p.parent.rmdir()  # only when the folder is empty: the user's own files in it stay
            except OSError:
                print(f"  kept {p.parent} (it holds other files)")
    print(f"Done: removed {len(plan)} files. Restart Kiro so it drops them.")
    return 0


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: python3 kiro.py install [--home DIR] [--project DIR] [--yes]\n")


def main(argv: Optional[List[str]] = None) -> int:
    utf8_stdio()
    parser = _Parser(prog="kiro.py", description="Install Plumb's skills and hooks for Kiro, or remove them.")
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("--home", type=Path, help="the home folder that holds .kiro (default: yours)")
    parser.add_argument("--project", type=Path, help="also this project (Kiro workspace): its .kiro/skills and hooks")
    parser.add_argument("--yes", action="store_true", help="write or remove without asking")
    args = parser.parse_args(argv)
    try:
        home = Path(os.path.abspath(str(args.home if args.home else Path.home())))
        project = Path(os.path.abspath(str(args.project))) if args.project else None
        if project is not None and not project.is_dir():
            raise KiroError(f"the project folder {project} does not exist, so nothing was written",
                            "ask the user: which folder is the Kiro workspace? Then run kiro.py "
                            f"{args.action} --project <that folder>")
        return install(args, home, project) if args.action == "install" else uninstall(args, home, project)
    except KiroError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc.strerror or exc}: {exc.filename or ''}\n"
              f"ask the user: check that folder can be written, then run kiro.py {args.action} again", file=sys.stderr)
        return 2


if __name__ == "__main__":
    utf8_stdio()
    sys.exit(main())
