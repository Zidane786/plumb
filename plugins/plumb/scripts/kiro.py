#!/usr/bin/env python3
"""kiro.py: install Plumb's skills and hooks for Kiro (IDE and CLI v3), or remove them.

    kiro.py install   [--home DIR | --project DIR] [--yes]
    kiro.py uninstall [--home DIR | --project DIR] [--yes]

Kiro has no plugin marketplace, so this copies what Claude Code and Copilot CLI load from the plugin into one place:
without --project the home folder (<home>/.kiro: global skills for the Kiro IDE, global hooks for Kiro CLI), with
--project only that Kiro workspace (<project>/.kiro: skills and hooks for the IDE and the CLI). In each:

- every skill as .kiro/skills/plumb-<name>/SKILL.md: named plumb-<name> (the command is /plumb-<name>), front matter
  cut to Agent Skills' name + description (Claude's allowed-tools, argument-hint and disable-model-invocation dropped),
  `${CLAUDE_PLUGIN_ROOT}` replaced by this plugin's absolute path, /plumb:<x> by /plumb-<x>, and the links to
  reference/ pointing into the plugin. Marked copies of skills this plugin no longer has are removed;
- the hooks as .kiro/hooks/plumb.json, from kiro/plumb-hooks.json.tmpl: SessionStart -> session_start.py, PreToolUse
  (matchers write and shell) -> pre_edit.py, Stop -> stop_check.py. Each command runs this plugin's own launcher by
  absolute path with --kiro (the hook then answers in Kiro's dialect) and, in the home file, --kiro-global (those hooks
  stand down where the workspace's own Plumb hooks file runs the same plugin: Kiro CLI runs both side by side):
    POSIX    [ -f '<plugin>/hooks/run.sh' ] && exec sh '<plugin>/hooks/run.sh' <script> --kiro ... || exit 0
    Windows  powershell -NoProfile -NonInteractive -EncodedCommand <base64 UTF-16LE of a script that runs
             cmd.exe /d /s /c "<plugin>\\hooks\\run.cmd" <script> --kiro ... with its own pipes, copies stdin, stdout
             and stderr through byte for byte, and exits with the hook's code (0 when run.cmd is gone or anything
             fails)>
             exit $LASTEXITCODE
  Line 1 is bare words (no quotes, parentheses, %, & or $), so cmd.exe, Windows PowerShell 5.1, pwsh 7 and Git Bash
  all run it the same way (verify live which one Kiro uses). Line 2 keeps the exit code (2 refuses) where the shell is
  PowerShell or Git Bash: PowerShell's -Command turns any failure into 1; cmd.exe stops at the line break. Running the
  launcher through PowerShell's own `&` would wrap its stderr as CLIXML and lose exit code 2, so the script does not. A launcher that is gone (the plugin
  moved or was updated) exits 0, so a hook never blocks Kiro (it blocks a PreToolUse on any non-zero exit); the
  SessionStart command then prints one line saying the checks are off and to run kiro.py install again.

Every file written carries "installed by Plumb's kiro.py" (the SKILL.md as a comment, the hooks in each description,
which also says what the hook runs): install updates only such files and refuses to overwrite anything else, or to
write through a symlink (.kiro itself included); uninstall removes only such files (and a skill folder left empty), never the
user's own skills or hooks.

It prints every path it will write or remove, then writes only after --yes or a "y" typed at the prompt. Without a
terminal and without --yes it writes nothing and says to ask the user (an agent never confirms for them). It never
downloads, installs or runs anything. After updating the Plumb plugin, run install again (the copies point at this
plugin folder; the Kiro session start says so when a newer Plumb sits next to it).

Kiro's formats are taken from its docs (# verify live: the hooks file schema, the shell that runs a command on
Windows, whether the Stop decision JSON makes Kiro continue, and which skills folder each Kiro reads).

Exit codes: 0 done (or nothing to do), 1 the user said no, 2 refused (`error: ...` then `fix: ...` or `ask the user:
...`). Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path, PureWindowsPath
from typing import List, Optional, Tuple

PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATE = PLUGIN / "kiro" / "plumb-hooks.json.tmpl"
# The same constants as hooks/_hooklib.py; tests/test_kiro.py keeps them in step.
KIRO_ARG = "--kiro"
KIRO_GLOBAL_ARG = "--kiro-global"
KIRO_MARK = "installed by Plumb's kiro.py"
WINDOWS = sys.platform == "win32"
SKILL_PREFIX = "plumb-"
# Agent Skills front matter keeps these; Claude Code's own keys (allowed-tools, argument-hint, disable-model-invocation)
# are dropped from the Kiro copies.
SKILL_KEYS = ("name", "description", "license", "compatibility", "metadata")
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


def _arg(text: str) -> str:
    return text if re.fullmatch(r"[\w.@+/:\\-]+", text) else '"' + text + '"'


def python_command() -> str:
    return os.environ.get("PLUMB_PYTHON") or ("py -3" if WINDOWS else "python3")


def this_script() -> str:
    return _arg(str(PLUGIN / "scripts" / "kiro.py"))


# ---------------------------------------------------------------- what gets written


def root_text() -> str:
    """This plugin's absolute path as the skills show it (forward slashes on Windows too: Python and the shells take
    them)."""
    return PLUGIN.as_posix()


def _front_matter(front: str, name: str) -> str:
    """Agent Skills keys only (each with its indented continuation lines), the name made plumb-<name>."""
    out: List[str] = []
    keep = False
    for line in front.splitlines():
        m = re.match(r"^([A-Za-z][\w-]*)\s*:", line)
        if m:
            keep = m.group(1) in SKILL_KEYS
            if m.group(1) == "name":
                line = f"name: {SKILL_PREFIX}{name}"
        if keep:
            out.append(line)
    if not any(line.startswith("name:") for line in out):
        out.insert(0, f"name: {SKILL_PREFIX}{name}")
    return "\n".join(out) + "\n"


def kiro_skill(source: str, name: str, root: str, version: str) -> str:
    """A plugin skill's SKILL.md as Kiro's plumb-<name> skill."""
    text = source.replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?\n)---\n", text, re.S)
    if not m:
        raise KiroError(f"skills/{name}/SKILL.md has no front matter, so it cannot be installed for Kiro",
                        "fix: reinstall the Plumb plugin, then run this command again")
    front, body = _front_matter(m.group(1), name), text[m.end():]

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


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def launcher(windows: bool = WINDOWS) -> str:
    run = PLUGIN / "hooks" / ("run.cmd" if windows else "run.sh")
    return str(PureWindowsPath(str(run))) if windows else str(run)  # from the text: 3.9 misreads a PosixPath


def gone_note(project: Optional[Path]) -> str:
    """What the SessionStart command prints when the plugin folder it points at is gone."""
    scope = f" --project {_arg(str(project))}" if project is not None else ""
    return (f"Plumb: the Kiro hooks point at a Plumb folder that is gone ({PLUGIN}), so Plumb's checks are off: ask the "
            f"user to run {python_command()} <the updated Plumb plugin folder>/scripts/kiro.py install{scope} again")


def hook_command(script: str, global_file: bool, windows: bool = WINDOWS, project: Optional[Path] = None) -> str:
    """The command a Kiro hook runs: this plugin's launcher by absolute path with --kiro (and --kiro-global for the
    home file); exit 0 when the launcher is missing, after one line at SessionStart."""
    args = " ".join([script, KIRO_ARG] + ([KIRO_GLOBAL_ARG] if global_file else []))
    note = gone_note(project) if script == "session_start.py" else None
    run = launcher(windows)
    if windows:
        gone = (f"$b=[Text.Encoding]::UTF8.GetBytes({_ps_quote(note)}+[char]10); "
                f"[Console]::OpenStandardOutput().Write($b,0,$b.Length); ") if note else ""
        # PowerShell would wrap a native command's stderr (as CLIXML under -EncodedCommand) and turn its exit code into
        # 1: the launcher runs through cmd.exe with its own pipes, and the bytes are copied through unchanged.
        body = ("$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
                f"$s={_ps_quote(run)}; if (-not (Test-Path -LiteralPath $s)) {{ {gone}exit 0 }}; try {{ "
                "try { [Console]::InputEncoding=New-Object Text.UTF8Encoding $false } catch {}; "
                "$i=New-Object Diagnostics.ProcessStartInfo; "
                "$i.FileName=[IO.Path]::Combine($env:SystemRoot,'System32','cmd.exe'); "
                f"""$i.Arguments='/d /s /c ""'+$s+'" {args}"'; """
                "$i.UseShellExecute=$false; $i.RedirectStandardInput=$true; $i.RedirectStandardOutput=$true; "
                "$i.RedirectStandardError=$true; $p=[Diagnostics.Process]::Start($i); "
                "$o=$p.StandardOutput.BaseStream.CopyToAsync([Console]::OpenStandardOutput()); "
                "$e=$p.StandardError.BaseStream.CopyToAsync([Console]::OpenStandardError()); "
                "[Console]::OpenStandardInput().CopyTo($p.StandardInput.BaseStream); $p.StandardInput.Close(); "
                "$p.WaitForExit(); $o.Wait(); $e.Wait(); exit $p.ExitCode } catch { exit 0 }")
        encoded = base64.b64encode(body.encode("utf-16-le")).decode("ascii")
        # No -ExecutionPolicy Bypass: an encoded command and run.cmd need no script policy, and that flag is what
        # endpoint protection flags (a blocked hook would fail closed). Line 2 keeps the exit code where PowerShell or
        # Git Bash is the shell (PowerShell's -Command would make any failure 1); cmd.exe stops at the line break.
        return f"powershell -NoProfile -NonInteractive -EncodedCommand {encoded}\nexit $LASTEXITCODE"
    quoted = _sh_quote(run)
    tail = f"{{ printf '%s\\n' {_sh_quote(note)}; exit 0; }}" if note else "exit 0"
    return f"[ -f {quoted} ] && exec sh {quoted} {args} || {tail}"


def windows_script(command: str) -> str:
    """The PowerShell a Windows hook command runs (it is base64-encoded in the command's first line)."""
    return base64.b64decode(command.split("\n", 1)[0].rsplit(" ", 1)[-1]).decode("utf-16-le")


def hooks_json(global_file: bool, project: Optional[Path]) -> str:
    try:
        tmpl = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KiroError(f"cannot read the plugin's {TEMPLATE.relative_to(PLUGIN).as_posix()} ({exc})",
                        "fix: reinstall the Plumb plugin, then run this command again") from None
    mark = f"({KIRO_MARK}; kiro.py uninstall removes it)"
    for h in tmpl.get("hooks", []):
        m = re.fullmatch(r"\{\{RUN:([\w.-]+\.py)\}\}", str(h.get("action", {}).get("command", "")))
        if not m:
            raise KiroError(f"the plugin's {TEMPLATE.name} has a hook without a {{{{RUN:<script>}}}} command",
                            "fix: reinstall the Plumb plugin, then run this command again")
        script = m.group(1)
        flags = " ".join([KIRO_ARG] + ([KIRO_GLOBAL_ARG] if global_file else []))
        h["action"]["command"] = hook_command(script, global_file, project=project)
        h["description"] = (str(h.get("description", "")).replace("{{MARK}}", mark)
                            + f" Runs {launcher()} {script} {flags}.")
    return json.dumps(tmpl, indent=2, ensure_ascii=False) + "\n"


def skill_names() -> List[str]:
    return sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md"))


def plan_install(base: Path, global_file: bool) -> Tuple[List[Tuple[Path, str]], List[Path]]:
    """(files to write, marked copies of skills the plugin no longer has, to remove)."""
    root, version = root_text(), plugin_version()
    kiro = base / ".kiro"
    names = skill_names()
    writes: List[Tuple[Path, str]] = []
    for name in names:
        source = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        writes.append((kiro / "skills" / f"{SKILL_PREFIX}{name}" / "SKILL.md", kiro_skill(source, name, root, version)))
    writes.append((kiro / "hooks" / "plumb.json", hooks_json(global_file, None if global_file else base)))
    wanted = {f"{SKILL_PREFIX}{n}" for n in names}
    retired = [p for p in plan_uninstall(base) if p.name == "SKILL.md" and p.parent.name not in wanted]
    return writes, retired


# ---------------------------------------------------------------- ownership and safety


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


def symlinks_below(base: Path, path: Path) -> List[Path]:
    """path and its parents up to <base>/.kiro itself that are symlinks (a dangling one included): writing there could
    land anywhere the link points."""
    kiro = base / ".kiro"
    found = []
    p = path
    while p == kiro or kiro in p.parents:
        if os.path.islink(str(p)):
            found.append(p)
        if p == kiro:
            break
        p = p.parent
    return found


def plan_uninstall(base: Path) -> List[Path]:
    out: List[Path] = []
    skills = base / ".kiro" / "skills"
    if skills.is_dir() and not os.path.islink(str(skills)):
        for p in sorted(skills.glob(f"{SKILL_PREFIX}*/SKILL.md")):
            if p.is_file() and not symlinks_below(base, p) and ours_skill(p):
                out.append(p)
    hooks = base / ".kiro" / "hooks" / "plumb.json"
    if hooks.is_file() and not symlinks_below(base, hooks) and ours_hooks(hooks):
        out.append(hooks)
    return out


# ---------------------------------------------------------------- the commands


def again(action: str, args: argparse.Namespace) -> str:
    """The exact command to run this again with --yes."""
    parts = [python_command(), this_script(), action]
    if args.project:
        parts += ["--project", _arg(str(args.project))]
    elif args.home:
        parts += ["--home", _arg(str(args.home))]
    return " ".join(parts + ["--yes"])


def confirmed(args: argparse.Namespace, question: str) -> Optional[bool]:
    """True to go on, False when the user said no, None when there is no one to ask (no terminal, no --yes)."""
    if args.yes:
        return True
    if not interactive():
        return None
    return ask(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def _remove(p: Path) -> None:
    p.unlink()
    if p.name == "SKILL.md":
        try:
            p.parent.rmdir()  # only when the folder is empty: the user's own files in it stay
        except OSError:
            print(f"  kept {p.parent} (it holds other files)")


def install(args: argparse.Namespace, base: Path, global_file: bool) -> int:
    writes, retired = plan_install(base, global_file)
    linked = sorted({str(s) for p, _ in writes for s in symlinks_below(base, p)})
    if linked:
        raise KiroError(f"{', '.join(linked)} {'is a symlink' if len(linked) == 1 else 'are symlinks'} inside "
                        f"{base / '.kiro'}, so writing there could land elsewhere; nothing was written",
                        "ask the user: remove or replace the symlink (check where it points first), then run "
                        f"{again('install', args)}")
    foreign = [p for p, _ in writes if p.exists() and not (p.is_file() and ours(p))]
    if foreign:
        listed = ", ".join(str(p) for p in foreign)
        raise KiroError(f"{listed} already exist{'s' if len(foreign) == 1 else ''} and {'is' if len(foreign) == 1 else 'are'} "
                        f"not Plumb's (no \"{KIRO_MARK}\" mark), so nothing was written",
                        "ask the user: move or rename it (it is theirs; Plumb never overwrites it), then run "
                        f"{again('install', args)}")
    print(f"Plumb {plugin_version()} for Kiro: install writes these {len(writes)} files"
          f"{f' and removes {len(retired)}' if retired else ''} in {base / '.kiro'}:")
    for p, _ in writes:
        print(f"  {'update' if p.exists() else 'write'} {p}")
    for p in retired:
        print(f"  remove {p} (no longer in this Plumb)")
    if WINDOWS:
        sample = hook_command("pre_edit.py", global_file, project=None if global_file else base)
        print(f"  each hook runs, through PowerShell: {windows_script(sample)}")
    ok = confirmed(args, "Write these files?")
    if ok is None:
        raise KiroError(f"nothing was written: kiro.py writes into {base / '.kiro'} only when the user confirms",
                        f"ask the user: run {again('install', args)} yourself (it writes the files listed above into "
                        f"{base / '.kiro'}), or tell me to run it")
    if not ok:
        print("nothing was written")
        return 1
    for p, text in writes:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    for p in retired:
        _remove(p)
    names = ", ".join(f"/{SKILL_PREFIX}{n}" for n in skill_names())
    print(f"Done: wrote {len(writes)} files. Restart Kiro (or start a new session) so it loads them.")
    print(f"Commands in Kiro: {names}.")
    print("After updating the Plumb plugin, run this install again; kiro.py uninstall removes these files.")
    return 0


def uninstall(args: argparse.Namespace, base: Path) -> int:
    plan = plan_uninstall(base)
    if not plan:
        print(f"Plumb for Kiro: nothing to remove in {base / '.kiro'}")
        return 0
    print(f"Plumb for Kiro: uninstall removes these {len(plan)} files (only the ones kiro.py installed):")
    for p in plan:
        print(f"  remove {p}")
    ok = confirmed(args, "Remove these files?")
    if ok is None:
        raise KiroError(f"nothing was removed: kiro.py removes files from {base / '.kiro'} only when the user confirms",
                        f"ask the user: run {again('uninstall', args)} yourself (it removes the files listed above), or "
                        f"tell me to run it")
    if not ok:
        print("nothing was removed")
        return 1
    for p in plan:
        _remove(p)
    print(f"Done: removed {len(plan)} files. Restart Kiro so it drops them.")
    return 0


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: {python_command()} {this_script()} --help\n")


def main(argv: Optional[List[str]] = None) -> int:
    utf8_stdio()
    parser = _Parser(prog="kiro.py", description="Install Plumb's skills and hooks for Kiro, or remove them.")
    parser.add_argument("action", choices=("install", "uninstall"))
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--home", type=Path, help="the home folder that holds .kiro (default: yours)")
    where.add_argument("--project", type=Path, help="this Kiro workspace instead of the home folder")
    parser.add_argument("--yes", action="store_true", help="write or remove without asking")
    args = parser.parse_args(argv)
    try:
        if args.project:
            base, global_file = Path(os.path.abspath(str(args.project))), False
            if not base.is_dir():
                raise KiroError(f"the project folder {base} does not exist, so nothing was written",
                                "ask the user: which folder is the Kiro workspace? Then run "
                                f"{python_command()} {this_script()} {args.action} --project <that folder>")
        else:
            base, global_file = Path(os.path.abspath(str(args.home if args.home else Path.home()))), True
        return install(args, base, global_file) if args.action == "install" else uninstall(args, base)
    except KiroError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc.strerror or exc}: {exc.filename or ''}\n"
              f"ask the user: check that folder can be written, then run {again(args.action, args)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    utf8_stdio()
    sys.exit(main())
