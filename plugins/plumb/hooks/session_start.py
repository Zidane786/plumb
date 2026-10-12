#!/usr/bin/env python3
"""Plumb SessionStart hook: one status line, and the session snapshot the end-of-turn check compares with.

Silent (no output, exit 0) in a project without a PLUMB.md. Otherwise prints

  Plumb: <skill name> <project's Plumb version> · tokens <up to date|stale> · <N> audit issues · read the skill before UI changes

Every script it runs is the plugin's own copy (`--root <the project's skill>`), never the project's (trust boundary).
- tokens: `build-tokens.py --check` (exit 0 up to date, 1 stale; "tokens not checked" when it cannot run, "no tokens
  yet" before the tokens file exists);
- audit issues: errors + warnings of a full `audit.py --json` run, capped at 2 seconds (PLUMB_AUDIT_TIMEOUT, in
  seconds, changes the cap; 0 skips it): "audit not run" when it does not finish or fails. Both run at the same time;
- a second line "Plumb X is installed; this project's design system is Y: run /plumb:upgrade" when PLUMB.md's version
  (its first line, `<!-- plumb vY`) is older than the plugin's;
- "this project's Plumb scripts are vX; the plugin is vY — run /plumb:upgrade" when the project's copied scripts
  (PLUMB_VERSION in its _plumb.py, read as text) differ from the plugin's;
- when the design-system folder PLUMB.md names (`Design system:`) is missing, "design system not found" and a
  warning: line + fix: line (a linked repo whose home repo is not there, or a moved skill).

Claude Code adds plain stdout to the session; GitHub Copilot CLI (COPILOT_CLI set) reads {"additionalContext": ...}.

Then it writes the session snapshot (audit.take_snapshot: in git, the hash and text of each UI or screen file that is
changed or untracked now, plus HEAD; elsewhere every UI and screen file's modification time) to
<OS temp>/plumb/<project hash>-<session id>.json, unless the session (a resume) already has one, and deletes snapshots
older than 7 days. Never fails the session: any problem leaves out that part (at most one stderr line), exit 0.
Standard library only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _hooklib as H  # noqa: E402

AUDIT_TIMEOUT = 2.0
TOKENS_TIMEOUT = 5.0


def _start(proj: H.Project, script: str, *args: str) -> Optional[subprocess.Popen]:
    """The plugin's own copy of a script, pointed at the project's design-system skill (--root): never the project's
    copy (trust boundary, see _hooklib)."""
    path = os.path.join(H.PLUGIN_SCRIPTS, script)
    if not os.path.isfile(path):
        return None
    try:
        return subprocess.Popen([sys.executable, path, *args, "--root", str(proj.skill_dir)], cwd=proj.root_s,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return None


def _finish(proc: Optional[subprocess.Popen], timeout: float) -> Optional[Tuple[int, str]]:
    if proc is None:
        return None
    try:
        out, _err = proc.communicate(timeout=max(timeout, 0.01))
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=2)
        except subprocess.SubprocessError:
            pass
        return None
    return proc.returncode, out.decode("utf-8", "replace")


def _audit_timeout() -> float:
    try:
        return float(os.environ.get("PLUMB_AUDIT_TIMEOUT", AUDIT_TIMEOUT))
    except ValueError:
        return AUDIT_TIMEOUT


def status(proj: H.Project) -> Tuple[str, Optional[str]]:
    """(the status line, the upgrade nudge or None)."""
    version = proj.version or "(unknown version)"
    nudge = None
    installed = H.plugin_version()
    mine, theirs = H.version_tuple(proj.version), H.version_tuple(installed)
    if mine is not None and theirs is not None and mine < theirs:
        nudge = f"Plumb {installed} is installed; this project's design system is {proj.version}: run /plumb:upgrade"
    has_tokens = any((proj.skill_dir / "assets" / "tokens").glob("*.tokens.json")) \
        if (proj.skill_dir / "assets" / "tokens").is_dir() else False  # type: ignore[operator]
    timeout = _audit_timeout()
    tokens_proc = _start(proj, "build-tokens.py", "--check") if has_tokens else None
    audit_proc = _start(proj, "audit.py", "--json") if timeout > 0 else None
    tokens = _finish(tokens_proc, TOKENS_TIMEOUT)
    audit = _finish(audit_proc, timeout)
    if not has_tokens:
        tokens_text = "no tokens yet"
    elif tokens is None or tokens[0] not in (0, 1):
        tokens_text = "tokens not checked"
    else:
        tokens_text = "tokens up to date" if tokens[0] == 0 else "tokens stale"
    audit_text = "audit not run"
    if audit is not None and audit[0] in (0, 1):
        try:
            data = json.loads(audit[1])
            n = int(data["errors"]) + int(data["warnings"])
            audit_text = f"{n} audit issue{'' if n == 1 else 's'}"
        except (ValueError, KeyError, TypeError):
            pass
    return (f"Plumb: {proj.name} {version} · {tokens_text} · {audit_text} · read the skill before UI changes", nudge)


def snapshot(proj: H.Project, session_id: str) -> None:
    H.clean_snapshots()
    path = H.snapshot_path(proj.root, session_id)
    if path.is_file():
        return  # a resumed session keeps the snapshot it started with
    A = H.load_script("audit.py", "plumb_audit")
    if A is None:
        return
    try:
        doc = A.load_doc(proj.skill_dir)
        settings = A.make_settings(proj.root, doc)
        H.write_json(path, A.take_snapshot(proj.root, proj.skill_dir, settings))
    except Exception as exc:  # noqa: BLE001
        H.note(f"no session snapshot, so the end-of-turn check stays quiet this session ({type(exc).__name__}: "
               f"{str(exc).splitlines()[0] if str(exc) else ''})")


def main() -> int:
    p = H.read_payload() or H.Payload({})
    proj = H.load_project(p)
    if proj is None:
        return 0
    lines = []
    version = proj.version or "(unknown version)"
    if not proj.skill_ok:
        lines.append(f"Plumb: {proj.name} {version} · design system not found · read the skill before UI changes")
        where = f"{proj.skill_rel}/" if proj.skill_rel else "(none)"
        if proj.linked:
            lines.append(f"warning: the linked design system {where} (Design system: in PLUMB.md) is missing, so the edit "
                         f"and end-of-turn checks are off")
            lines.append("fix: clone or pull the home repository so that path exists, or correct Design system: in PLUMB.md")
        else:
            lines.append(f"warning: the design system {where} (Design system: in PLUMB.md) is missing, so the edit and "
                         f"end-of-turn checks are off")
            lines.append("fix: correct Design system: in PLUMB.md, or run /plumb:init to set the design system up again")
    else:
        line, nudge = status(proj)
        lines.append(line)
        if nudge:
            lines.append(nudge)
        scripts = H.scripts_note(proj)
        if scripts:
            lines.append(scripts)
        snapshot(proj, p.session_id)
    text = "\n".join(lines)
    print(json.dumps({"additionalContext": text}) if p.copilot else text)
    return 0


if __name__ == "__main__":
    H.utf8_stdio()
    try:
        code = main()
    except Exception as _exc:  # noqa: BLE001 - a status line must never break the session
        H.note(f"session start skipped ({type(_exc).__name__})")
        code = 0
    sys.exit(code)
