"""Shared helpers for the hook tests (test_hooks.py, test_copilot.py, test_run_sh.py).

Every hook test runs the hook the way the CLI runs it: through hooks/run.sh with `sh` (macOS, Linux and Git Bash on
Windows) and, on Windows only, through the `powershell` command of hooks.json (run.cmd). Payloads come from the real
payload samples in tests/fixtures/hooks/{claude,copilot}/*.json, with {{PLACEHOLDERS}} filled in.

The test project is the prototype-fidelity Next.js fixture (three approved, built screens: home, booking, menü) plus a
design-system skill (.claude/skills/demo-design-system/: the scripts, templates, a tokens file with web, iOS and Android
and the copy app/globals.css) and a PLUMB.md with every check on. It is built once (build-tokens.py and
build-prototype.py really run) and copied into a folder with a non-ASCII name for each test.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "plumb"
HOOKS = PLUGIN / "hooks"
SKILL_SRC = PLUGIN / "assets" / "skill"
SCRIPTS_SRC = SKILL_SRC / "scripts"
FIXTURES = REPO / "tests" / "fixtures"
PAYLOADS = FIXTURES / "hooks"
SKILL_REL = ".claude/skills/demo-design-system"
SCREENS = "docs/design/prototype/screens"
MAP = "docs/design/prototype/screens.json"
BUILD_TOKENS = f"python3 {SKILL_REL}/scripts/build-tokens.py"
BUILD_PROTOTYPE = f"python3 {SKILL_REL}/scripts/build-prototype.py"
WINDOWS = sys.platform == "win32"
SH = shutil.which("sh")
POWERSHELL = (shutil.which("powershell") or shutil.which("pwsh")) if WINDOWS else None
CI = bool(os.environ.get("CI"))

# Every launcher a CLI uses on this OS: run.sh everywhere a POSIX sh exists; run.cmd through PowerShell on Windows.
LAUNCHERS = (["sh"] if SH else []) + (["powershell"] if WINDOWS else [])
SCRIPT_EVENT = {"session_start.py": "SessionStart", "pre_edit.py": "PreToolUse", "stop_check.py": "Stop"}

PLUMB_MD = """<!-- plumb v{version} · written by /plumb:init, safe to edit values -->
# Plumb: the design system for Demo

Design system: `{skill}/`
Role: {role}                          (home = this repo owns the tokens; linked = uses another repo's)
Platforms: web, ios, android
UI packages: . (Next.js · Tailwind v4)
Python: `python3`
No downloads: nothing is installed or downloaded; if something is missing, ask the user and wait for their decision.

## Checks
Edit check: {edit}
End-of-turn check: {stop}
Themes: light-and-dark          (light-and-dark | light-only: an explicit decision)
UI files: app/**, components/** · *.tsx *.jsx *.ts *.css
Allowed raw values: components/ui/**

## Commands
tokens `python3 {skill}/scripts/build-tokens.py` (make tokens)

## Prototype
Main: docs/design/prototype.html · screens: docs/design/screens.html · map: docs/design/prototype/screens.json
Prototype sync: {sync}               (end-of-turn check stops once when a built screen changed without its prototype)

## Plumb updates
- 2026-10-11 created with Plumb 1.0.0 (web; direction "Calm")
"""


def write(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def plumb_md(version: str = "1.0.0", skill: str = SKILL_REL, role: str = "home", edit: str = "on", stop: str = "on",
             sync: str = "on") -> str:
    return PLUMB_MD.format(version=version, skill=skill, role=role, edit=edit, stop=stop, sync=sync)


def set_plumb(project: Path, **kw: str) -> None:
    write(project / "PLUMB.md", plumb_md(**kw))


def _clean_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    drop = ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "COPILOT_CLI", "PLUMB_PYTHON", "PLUMB_AUDIT_TIMEOUT")
    env = {k: v for k, v in os.environ.items() if k not in drop and not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "USER": "tester", "USERNAME": "tester", "PYTHONDONTWRITEBYTECODE": "1"})
    env.update(extra or {})
    return env


def run_script(project: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    env = _clean_env({"GIT_CEILING_DIRECTORIES": str(project.parent)})
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts" / script), *args], cwd=str(project),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)


_BASE: List[Path] = []


def _base_project() -> Path:
    """Built once per test run: the fidelity Next.js fixture + the design-system skill, tokens built, prototype built."""
    if _BASE:
        return _BASE[0]
    tmp = Path(tempfile.mkdtemp(prefix="plumb-hooks-"))
    atexit.register(shutil.rmtree, str(tmp), True)
    dest = tmp / "base"
    src = FIXTURES / "projects" / "fidelity" / "next"
    for f in sorted(src.rglob("*")):
        if f.is_file():
            write(dest / f.relative_to(src), read(f))
    skill = dest / SKILL_REL
    for name in ("_plumb.py", "audit.py", "build-tokens.py", "build-prototype.py"):
        write(skill / "scripts" / name, read(SCRIPTS_SRC / name))
    for f in sorted((SKILL_SRC / "templates").iterdir()):
        if f.is_file():
            write(skill / "templates" / f.name, read(f))
    write(skill / "assets/platforms/README.md", read(SKILL_SRC / "assets/platforms/README.md"))
    write(skill / "assets/platforms/web/tokens.css.template",
          read(SKILL_SRC / "assets/platforms/web/tokens.css.template.tailwind-v4"))
    doc = json.loads(read(FIXTURES / "pages" / "tokens.json"))
    plumb = doc["$extensions"]["plumb"]
    plumb.update({"project": "Demo", "platforms": ["web", "ios", "android"]})
    plumb["web"]["copies"] = ["app/globals.css"]
    write(skill / "assets/tokens/demo.tokens.json", json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    write(dest / "PLUMB.md", plumb_md())
    write(dest / "README.md", "# Demo\n\nNotes.\n")
    write(dest / "components/ui/button.tsx", 'export function Button() {\n  return <button className="bg-primary">Go</button>;\n}\n')
    for script in ("build-tokens.py", "build-prototype.py"):
        r = run_script(dest, script)
        assert r.returncode == 0, r.stdout + r.stderr
    _BASE.append(dest)
    return dest


def make_project(tmp_path: Path, name: str = "Café Ünïcode") -> Path:
    """A fresh copy of the built test project under tmp_path/<name>/demo."""
    dest = tmp_path / name / "demo"
    shutil.copytree(str(_base_project()), str(dest))
    return dest


def git_init(project: Path) -> None:
    env = _clean_env({"GIT_CEILING_DIRECTORIES": str(project.parent)})
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "Tester"],
                 ["config", "core.autocrlf", "false"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", *args], cwd=str(project), check=True, capture_output=True, env=env, timeout=60)


def git(project: Path, *args: str) -> None:
    env = _clean_env({"GIT_CEILING_DIRECTORIES": str(project.parent)})
    subprocess.run(["git", *args], cwd=str(project), check=True, capture_output=True, env=env, timeout=60)


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


# ---------------------------------------------------------------- payloads


def _fill(node: Any, values: Dict[str, Any]) -> Any:
    if isinstance(node, dict):
        return {k: _fill(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, values) for v in node]
    if isinstance(node, str):
        for key, value in values.items():
            mark = "{{" + key + "}}"
            if node == mark:
                return value  # the whole string: any JSON value (bool, number, object)
            if mark in node:
                node = node.replace(mark, str(value))
        return node
    return node


def payload(tool: str, name: str, stringify: Optional[str] = None, **values: Any) -> str:
    """The payload sample tests/fixtures/hooks/<tool>/<name>.json with {{KEY}} filled in from values, as stdin text.
    stringify names a top-level key whose value is sent as a JSON string (Copilot's toolArgs can be either)."""
    doc = json.loads(read(PAYLOADS / tool / f"{name}.json"))
    values.setdefault("SESSION", "sess-1")
    doc = _fill(doc, values)
    if stringify:
        doc[stringify] = json.dumps(doc[stringify])
    return json.dumps(doc)


# ---------------------------------------------------------------- running a hook as the CLI does


def plumb_tmp(tmp_path: Path) -> Path:
    """The hooks' private folder in the OS temp folder hook_env() sets: plumb-<uid> (plumb-<user> on Windows)."""
    if hasattr(os, "getuid"):
        name = f"plumb-{os.getuid()}"
    else:
        import getpass
        import re
        name = "plumb-" + (re.sub(r"[^\w.-]", "_", getpass.getuser() or "") or "user")
    return tmp_path / "os-tmp" / name


def hook_env(tmp_path: Path, copilot: bool = False, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    ostmp = tmp_path / "os-tmp"
    ostmp.mkdir(exist_ok=True)
    env = _clean_env({"CLAUDE_PLUGIN_ROOT": str(PLUGIN), "TMPDIR": str(ostmp), "TEMP": str(ostmp), "TMP": str(ostmp),
                      "GIT_CEILING_DIRECTORIES": str(tmp_path)})
    env.pop("PYTHONDONTWRITEBYTECODE", None)  # hooks run as users run them (bytecode cache allowed)
    if copilot:
        env["COPILOT_CLI"] = "1"
    env.update(extra or {})
    return env


def _hook_entry(event: str) -> Dict[str, Any]:
    hooks = json.loads(read(HOOKS / "hooks.json"))["hooks"]
    (entry,) = [h for e in hooks[event] for h in e["hooks"]]
    return entry


def run_hook(launcher: str, script: str, stdin: str, cwd: Path, env: Dict[str, str],
             timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a hook through a launcher as the CLI does: "sh" = `sh hooks/run.sh <script>` (hooks.json's command: Claude
    Code everywhere, Copilot CLI on macOS and Linux); "powershell" = hooks.json's powershell command (run.cmd), which
    only Copilot CLI runs (on Windows), so COPILOT_CLI=1 is set for it. r.copilot says which dialect to expect."""
    hooks = Path(env.get("CLAUDE_PLUGIN_ROOT") or PLUGIN) / "hooks"  # a test may run a copy of the plugin
    if launcher == "sh":
        cmd = [str(SH), str(hooks / "run.sh"), script]
    else:
        cmd = [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", _hook_entry(SCRIPT_EVENT[script])["powershell"]]
        env = {**env, "COPILOT_CLI": "1"}
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                       cwd=str(cwd), timeout=timeout)
    if "no Python 3.9+" in r.stderr:
        pytest.skip("no python3/python/py -3 on PATH for the launcher")
    assert "Traceback" not in r.stderr, r.stderr
    r.copilot = bool(env.get("COPILOT_CLI"))  # type: ignore[attr-defined]
    return r


def plugin_copy(tmp_path: Path) -> Path:
    """A copy of the installed plugin (hooks, the skill's scripts, the manifest), to break its scripts in a test."""
    dest = tmp_path / "plugin-copy"
    for part in ("hooks", ".claude-plugin", "assets/skill/scripts"):
        shutil.copytree(str(PLUGIN / part), str(dest / part), ignore=shutil.ignore_patterns("__pycache__"))
    return dest


MARKER_CODE = """import pathlib as _pl
_pl.Path({path!r}).write_text("ran", encoding="utf-8")
"""


def plant_markers(project: Path, folder: Path) -> List[Path]:
    """Prepend code that writes a marker file to each of the project's copied scripts; returns the marker paths."""
    markers = []
    for name in ("audit.py", "build-prototype.py", "build-tokens.py", "_plumb.py"):
        script = project / SKILL_REL / "scripts" / name
        marker = folder / f"marker-{name}"
        write(script, MARKER_CODE.format(path=str(marker)) + read(script))
        markers.append(marker)
    return markers


def context(r: subprocess.CompletedProcess) -> str:
    """Session start's text: plain stdout for Claude Code, {"additionalContext"} for Copilot CLI."""
    assert r.returncode == 0, r.stderr
    if getattr(r, "copilot", False) and r.stdout.strip():
        out = json.loads(r.stdout)
        assert list(out) == ["additionalContext"]
        return out["additionalContext"] + "\n"
    return r.stdout


def notes(r: subprocess.CompletedProcess) -> List[str]:
    """The hook's own stderr lines (PowerShell may wrap a native command's stderr in extra lines of its own)."""
    return [ln for ln in r.stderr.splitlines() if "plumb: " in ln]


def denied(r: subprocess.CompletedProcess) -> str:
    """The reason of a Copilot-style refusal (exit 0 + JSON deny, flat and in hookSpecificOutput); fails otherwise."""
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse" and hso["permissionDecision"] == "deny"
    assert out["permissionDecision"] == "deny" and out["permissionDecisionReason"] == hso["permissionDecisionReason"]
    return hso["permissionDecisionReason"]


def refused(r: subprocess.CompletedProcess) -> str:
    """The reason of a refusal in the dialect of the CLI that ran the hook: Claude Code exit 2, reason on stderr,
    nothing on stdout; Copilot CLI (r.copilot) the JSON deny. Fails otherwise."""
    if getattr(r, "copilot", False):
        return denied(r)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert r.stdout == ""
    return r.stderr


def allowed(r: subprocess.CompletedProcess) -> None:
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert r.stdout.strip() == "", r.stdout


def actionable(reason: str) -> None:
    """Every refusal says what is wrong and what to do: an error: line, then fix: or ask the user:."""
    lines = reason.strip().splitlines()
    first = next(i for i, ln in enumerate(lines) if ln.startswith("error: "))
    assert any(ln.startswith(("fix: ", "ask the user: ")) for ln in lines[first + 1:]), reason


def patch(*sections: str) -> str:
    return "*** Begin Patch\n" + "".join(sections) + "*** End Patch\n"
