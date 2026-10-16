#!/usr/bin/env python3
"""Plumb SessionStart hook: one status line, and the session snapshot the end-of-turn check compares with.

Silent (no output, exit 0) in a project without a PLUMB.md. Otherwise prints

  Plumb: <skill name> <project's Plumb version> · tokens <up to date|stale> · <N> audit issues · read the skill before UI changes

Every script it runs is the plugin's own copy (`--root <the project's skill>`), never the project's (trust boundary).
- tokens: `build-tokens.py --check` (exit 0 up to date, 1 stale; "tokens not checked" when it cannot run, "no tokens
  yet" before the tokens file exists, "tokens not checked (scripts vX ≠ vY)" when the project's copied scripts are
  another version: the plugin's generator could call output stale that the project's own version wrote);
- audit issues: errors + warnings of a full `audit.py --json` run, capped at 2 seconds (PLUMB_AUDIT_TIMEOUT, in
  seconds, changes the cap; 0 skips it): "audit not run" when it does not finish or fails. Both run at the same time;
- a second line "Plumb X is installed; this project's design system is Y: run /plumb:upgrade" when PLUMB.md's version
  (its first line, `<!-- plumb vY`) is older than the plugin's;
- "this project's Plumb scripts are vX; the plugin is vY — run /plumb:upgrade" when the project's copied scripts
  (PLUMB_VERSION in its _plumb.py, read as text) differ from the plugin's;
- when the design-system folder PLUMB.md names (`Design system:`) is missing, "design system not found" and a
  warning: line + fix: line (a linked repo whose home repo is not there, or a moved skill);
- one pointer line, "Plumb mistakes (a Plumb script, hook or skill got it wrong) → /plumb:feedback", so an agent knows
  where Plumb's own mistakes go even in a project with no AGENTS.md or CLAUDE.md;
- "Routes not recorded — run /plumb:init to record them" when PLUMB.md has no `Routes:` value (the route checks stay
  off: scripts never guess the app's layout) and a note for each entry _plumb.parse_routes cannot use, only where a
  route check would run (Prototype sync on, a web platform; never for `Routes: none`), and a note while
  <root>/.plumb-tmp/setup-in-progress exists (the end-of-turn check stands down during a setup).

Claude Code adds plain stdout to the session; GitHub Copilot CLI (COPILOT_CLI set) reads {"additionalContext": ...}.
Kiro (--kiro on the command) reads plain stdout too, with commands written /plumb-<name>, plus a line when a newer Plumb
sits next to the plugin folder Kiro's copies point at ("Plumb X is installed but Kiro still uses Y: ask the user to run
... kiro.py install").

Then it writes the session snapshot (audit.take_snapshot: in git, the hash and text of each UI or screen file that is
changed or untracked now, plus HEAD; elsewhere every UI and screen file's modification time) to
<OS temp>/plumb/<project hash>-<session id>.json, unless the session (a resume) already has one, and deletes snapshots
older than 7 days. Never fails the session: any problem leaves out that part (at most one stderr line), exit 0. A
crash or a timeout that failed open is also written, one line, to ~/.plumb/feedback/hooks.md (H.log_failure), for
Plumb's developers; never into the project. An existing ~/.plumb/feedback of the user's own is made 0700 again
(H.feedback_dir(create=False): the agent's records may have created it under a wider umask); none is created.
Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import time
import subprocess
import sys
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _hooklib as H  # noqa: E402

AUDIT_TIMEOUT = 2.0
# The last stderr line of a Python crash (a SyntaxError prints no "Traceback" header); a script's own refusal is
# "error: …" (exit 2), the project's problem, never this.
CRASH_LINE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Exit)\b")
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


def _finish(proc: Optional[subprocess.Popen], timeout: float, label: str = "") -> Optional[Tuple[int, str]]:
    """(exit code, stdout) of a script session start runs, or None when it did not finish in time. A timeout or a crash
    (a traceback, or an exit code other than 0, 1 and 2, the scripts' refusal) is logged for Plumb's developers
    (H.log_failure, ~/.plumb/feedback/hooks.md); the session never sees it beyond the status line."""
    if proc is None:
        return None
    try:
        out, err = proc.communicate(timeout=max(timeout, 0.01))
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=2)
        except subprocess.SubprocessError:
            pass
        H.log_failure(f"{label} did not finish within {timeout:g} s, so the status line says it was not run",
                      f"{label} finishes within {timeout:g} s", category="timeout")
        return None
    errors = err.decode("utf-8", "replace")
    tail = [ln.strip() for ln in errors.splitlines() if ln.strip()][-1:] or ["(no output)"]
    if proc.returncode not in (0, 1, 2) or "Traceback (most recent call last)" in errors or CRASH_LINE.match(tail[0]):
        H.log_failure(f"{label} crashed (exit {proc.returncode}): {tail[0]}",
                      f"{label} exits 0 or 1 with its normal output")
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
    mine, plugin = H.script_versions(proj)
    other = mine is not None and plugin is not None and mine != plugin  # another generator: its output may differ
    tokens_proc = _start(proj, "build-tokens.py", "--check") if has_tokens and not other else None
    audit_proc = _start(proj, "audit.py", "--json") if timeout > 0 else None
    tokens = _finish(tokens_proc, TOKENS_TIMEOUT, "build-tokens.py --check")
    audit = _finish(audit_proc, timeout, "audit.py --json")
    if not has_tokens:
        tokens_text = "no tokens yet"
    elif other:
        tokens_text = f"tokens not checked (scripts v{mine} \u2260 v{plugin})"
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
    if path is None or os.path.lexists(str(path)):
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
        H.log_failure(f"no session snapshot ({type(exc).__name__}: {exc}), so the end-of-turn check stays quiet",
                      "the session snapshot is written", exc=exc)


# One short pointer for the agent (also in projects with no AGENTS.md or CLAUDE.md): where Plumb's own mistakes go.
FEEDBACK_POINTER = "Plumb mistakes (a Plumb script, hook or skill got it wrong) \u2192 /plumb:feedback"
ROUTE_KINDS = ("next-app", "next-pages", "nuxt", "sveltekit", "angular", "router")  # as _plumb.ROUTE_KINDS (a test)
ROUTES_NOT_RECORDED = ("Routes not recorded \u2014 run /plumb:init to record them (PLUMB.md `Routes:`, the app's page "
                       "roots); until then the prototype-first check and route-not-prototyped are off")


def route_checks_run(proj: H.Project) -> bool:
    """A route check could run here: Prototype sync is on and the project has a web platform (or names none). A
    mobile-only project, or one with Prototype sync off, is never told about Routes."""
    if not H._ON.match(str(proj.keys.get("Prototype sync", "") or "")):
        return False
    platforms = [p.strip().lower() for p in re.split(r"[,\s]+", str(proj.keys.get("Platforms", "") or "")) if p.strip()]
    return not platforms or "web" in platforms


def setup_notes(proj: H.Project) -> list:
    """Lines for a project whose setup is not finished: PLUMB.md has no `Routes:`, or names an entry the shared parser
    (_plumb.parse_routes) cannot use (Plumb never guesses the app's layout, so the route checks skip it) \u2014 only where a
    route check would run (route_checks_run) \u2014, or the setup marker <root>/.plumb-tmp/setup-in-progress is there (a
    setup in progress, or one left behind: the end-of-turn check stands down while it exists)."""
    out = []
    core = H.load_script("_plumb.py", "_plumb") if route_checks_run(proj) else None
    if core is not None:
        roots, problems = core.parse_routes(proj.keys.get("Routes"))
        if roots is None:
            out.append(ROUTES_NOT_RECORDED)
        for problem in problems:
            out.append(f"note: {problem}; the route checks skip it until PLUMB.md is corrected (/plumb:init)")
    stale = H.setup_marker_stale(proj.root_s)
    if stale is not None:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(stale))
        out.append(f"note: a setup marker from {when} is stale \u2014 finish /plumb:init or remove {H.SETUP_TMP}/ (ask "
                   f"the user first); the end-of-turn check runs again")
    elif H.setup_in_progress(proj.root_s):
        out.append(f"note: {H.SETUP_MARKER} is in the project, so the end-of-turn check stands down (a Plumb setup is "
                   f"running); when no setup is running, delete {H.SETUP_TMP}/ (ask the user first)")
    return out


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
        scripts = H.scripts_note(proj) or H.files_note(proj)
        if scripts:
            lines.append(scripts)
        lines += setup_notes(proj)
        snapshot(proj, p.session_id)
    lines.append(FEEDBACK_POINTER)
    H.feedback_dir(create=False)  # an existing ~/.plumb/feedback of the user's own is kept private (0700); none is made
    if H.kiro_run():
        stale = kiro_stale_note(proj, p)
        if stale:
            lines.append(stale)
    text = H.tool_text("\n".join(lines))
    print(json.dumps({"additionalContext": text}) if p.copilot else text)
    return 0


def kiro_stale_note(proj: H.Project, p: H.Payload) -> Optional[str]:
    """Kiro's copies (skills, hooks) point at one plugin folder: when a newer Plumb sits next to it, say how to move
    them over (the user runs kiro.py; never the agent)."""
    newer = H.newer_plugin()
    if newer is None:
        return None
    version, folder = newer
    kiro = H._safe_arg(os.path.join(folder, "scripts", "kiro.py"))
    scope = "" if H.KIRO_GLOBAL_ARG in sys.argv[1:] else f" --project {H._safe_arg(p.cwd or os.getcwd())}"
    return (f"Plumb {version} is installed but Kiro still uses {H.plugin_version() or '(unknown)'}: ask the user to run "
            f"{proj.python} {kiro} install{scope} (Kiro's Plumb skills and hooks point at the old folder)")


if __name__ == "__main__":
    H.utf8_stdio()
    try:
        code = main()
    except Exception as _exc:  # noqa: BLE001 - a status line must never break the session
        H.note(f"session start skipped ({type(_exc).__name__})")
        H.log_failure(f"session start skipped ({type(_exc).__name__}: {_exc})", "the status line is printed",
                      exc=_exc)
        code = 0
    sys.exit(code)
