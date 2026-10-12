"""Tests for plugins/plumb/hooks/run.sh, the POSIX sh launcher every hook runs through.

The launcher picks the first of python3, python, "py -3" that is Python 3.9+, runs the script relative to the hooks
folder with stdin and arguments passed through, tells the script which Python it picked (PLUMB_PYTHON) and exits 0
quietly (one stderr line) when no Python is found: a missing Python never blocks a tool call. Fake interpreters are
small sh scripts, so those tests run only where a POSIX sh can execute them (not native Windows). The last section runs
the real hooks through run.sh, as hooks.json does.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import pytest

from hook_support import HOOKS, PLUGIN, SH, hook_env, make_project, payload, read, run_hook

RUN_SH = HOOKS / "run.sh"

pytestmark = pytest.mark.skipif(SH is None, reason="requires POSIX: a POSIX sh")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="requires POSIX: fake sh interpreters")


def _hooks_dir(tmp_path: Path) -> Path:
    hooks = tmp_path / "plugin" / "hooks"
    hooks.mkdir(parents=True)
    shutil.copy(str(RUN_SH), str(hooks / "run.sh"))
    return hooks


def _run(hooks: Path, args: List[str], env_path: str, stdin: str = "") -> subprocess.CompletedProcess:
    env: Dict[str, str] = {k: v for k, v in os.environ.items() if k not in ("PATH", "PLUMB_PYTHON")}
    env["PATH"] = env_path
    return subprocess.run([str(SH), str(hooks / "run.sh"), *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, cwd=str(hooks.parent.parent), timeout=60)


def _fake(bin_dir: Path, name: str, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    p = bin_dir / name
    p.write_bytes(("#!/bin/sh\n" + body).encode("utf-8"))  # LF endings on every OS
    p.chmod(0o755)


def test_runs_script_with_real_python_passing_args_and_stdin(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    (hooks / "echo_hook.py").write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        "print('ok', sys.version_info >= (3, 9), sys.argv[1:], data.strip())\n",
        encoding="utf-8",
    )
    r = _run(hooks, ["echo_hook.py", "--x", "two words"], os.environ.get("PATH", ""), stdin='{"tool": "Edit"}\n')
    if "no Python 3.9+" in r.stderr:
        pytest.skip("no python3/python/py -3 on PATH for sh")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok True ['--x', 'two words'] {\"tool\": \"Edit\"}"


def test_exit_code_of_script_passes_through(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    (hooks / "block.py").write_text("import sys\nprint('blocked', file=sys.stderr)\nsys.exit(2)\n", encoding="utf-8")
    r = _run(hooks, ["block.py"], os.environ.get("PATH", ""))
    if "no Python 3.9+" in r.stderr:
        pytest.skip("no python3/python/py -3 on PATH for sh")
    assert r.returncode == 2
    assert "blocked" in r.stderr


@posix_only
def test_no_python_prints_one_stderr_line_and_exits_0(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    r = _run(hooks, ["pre_edit.py"], str(empty), stdin="{}")
    assert r.returncode == 0
    assert r.stdout == ""
    lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
    assert len(lines) == 1 and "no Python 3.9+" in lines[0] and lines[0].startswith("plumb: ")


@posix_only
def test_missing_script_argument_is_quiet_exit_0(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    r = _run(hooks, [], str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == ""


@posix_only
def test_skips_too_old_python3_and_uses_python(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "python3", 'if [ "$1" = "-c" ]; then exit 1; fi\necho "python3 $*"\n')
    _fake(fake_bin, "python", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "python $*"\n')
    r = _run(hooks, ["pre_edit.py", "--x"], str(fake_bin))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"python {hooks}/pre_edit.py --x"


@posix_only
def test_prefers_python3_when_it_is_new_enough(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "python3", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "python3 $*"\n')
    _fake(fake_bin, "python", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "python $*"\n')
    r = _run(hooks, ["pre_edit.py"], str(fake_bin))
    assert r.stdout.strip() == f"python3 {hooks}/pre_edit.py"


@posix_only
def test_falls_back_to_py_launcher(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "py", 'if [ "$1" = "-3" ] && [ "$2" = "-c" ]; then exit 0; fi\necho "py $*"\n')
    r = _run(hooks, ["pre_edit.py", "a b"], str(fake_bin))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"py -3 {hooks}/pre_edit.py a b"


@posix_only
def test_absolute_script_path_is_kept(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "python3", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "python3 $*"\n')
    target = tmp_path / "elsewhere" / "x.py"
    r = _run(hooks, [str(target)], str(fake_bin))
    assert r.stdout.strip() == f"python3 {target}"


@posix_only
def test_version_probe_does_not_eat_hook_stdin(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "python3", 'if [ "$1" = "-c" ]; then while IFS= read -r x; do :; done; exit 0; fi\n'
                               'IFS= read -r l; echo "got: $l"\n')
    r = _run(hooks, ["pre_edit.py"], str(fake_bin), stdin="HOOK-JSON")
    assert r.stdout.strip() == "got: HOOK-JSON"


@posix_only
def test_run_sh_tells_the_script_which_python_it_picked(tmp_path: Path) -> None:
    hooks = _hooks_dir(tmp_path)
    fake_bin = tmp_path / "bin"
    _fake(fake_bin, "py", 'if [ "$1" = "-3" ] && [ "$2" = "-c" ]; then exit 0; fi\necho "PLUMB_PYTHON=$PLUMB_PYTHON"\n')
    r = _run(hooks, ["session_start.py"], str(fake_bin))
    assert r.stdout.strip() == "PLUMB_PYTHON=py -3"


def test_run_sh_names_plumb_not_slate() -> None:
    text = read(RUN_SH)
    assert "slate" not in text.lower() and "PLUMB_PYTHON" in text


# ---------------------------------------------------------------- the real hooks through run.sh


def test_hooks_json_runs_every_hook_through_run_sh() -> None:
    hooks = json.loads(read(HOOKS / "hooks.json"))["hooks"]
    cmds = {event: [h["command"] for entry in entries for h in entry["hooks"]] for event, entries in hooks.items()}
    prefix = 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" '
    assert cmds == {"SessionStart": [prefix + "session_start.py"], "PreToolUse": [prefix + "pre_edit.py"],
                    "Stop": [prefix + "stop_check.py"]}
    assert "python3 " not in read(HOOKS / "hooks.json")


def test_real_hooks_through_run_sh(tmp_path: Path) -> None:
    proj = make_project(tmp_path)
    env = hook_env(tmp_path)
    r = run_hook("sh", "session_start.py", payload("claude", "session_start", CWD=str(proj)), proj, env)
    assert r.returncode == 0 and r.stdout.startswith("Plumb: demo-design-system 1.0.0 · "), r.stdout + r.stderr
    r = run_hook("sh", "pre_edit.py", payload("claude", "write", CWD=str(proj), FILE=str(proj / "app/globals.css"),
                                              CONTENT="x"), proj, env)
    assert r.returncode == 2 and r.stderr.startswith("error: app/globals.css is generated")
    r = run_hook("sh", "pre_edit.py", payload("claude", "edit", CWD=str(proj), FILE=str(proj / "README.md"),
                                              OLD="Notes.", NEW="More."), proj, env)
    assert r.returncode == 0 and r.stdout == ""
    r = run_hook("sh", "stop_check.py", payload("claude", "stop", CWD=str(proj), ACTIVE=False), proj, env)
    assert r.returncode == 0 and r.stdout == ""


def test_hooks_without_a_project_dir_use_the_current_directory(tmp_path: Path) -> None:
    proj = make_project(tmp_path)
    stdin = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                        "tool_input": {"file_path": "app/globals.css", "content": "x"}})
    r = run_hook("sh", "pre_edit.py", stdin, proj, hook_env(tmp_path))
    assert r.returncode == 2 and "app/globals.css is generated" in r.stderr
    # CLAUDE_PROJECT_DIR wins over the current directory
    r = run_hook("sh", "pre_edit.py", stdin, tmp_path, hook_env(tmp_path, extra={"CLAUDE_PROJECT_DIR": str(proj)}))
    assert r.returncode == 2
