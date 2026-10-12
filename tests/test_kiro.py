"""Kiro support: kiro.py install / uninstall, the Kiro hook files and the Kiro payload adapter in _hooklib.

Kiro (IDE and CLI v3) has no plugin marketplace, so `scripts/kiro.py install` copies Plumb's skills into
`<home>/.kiro/skills/plumb-<name>/` (or, with --project, the project's `.kiro/skills/`) and writes a
`.kiro/hooks/plumb.json` (`{"version": "v1", "hooks": [...]}`) whose commands run the plugin's own hooks through
run.sh (POSIX) or, on Windows, PowerShell -EncodedCommand -> run.cmd, by absolute path, with `--kiro` (and
`--kiro-global` in the home file). Kiro sends snake_case hook input like Claude Code (`hook_event_name`, `cwd`,
`session_id`, `tool_name`, `tool_input`) with its own tool names (`fs_write` with a `command` of create / str_replace /
insert / append, `execute_bash`); with `--kiro` a refusal is exit 2 with the reason on stderr, the end-of-turn block is
`{"decision": "block", "reason": ...}`, session start's plain stdout is the context, and commands are written
/plumb-<name>. Payload samples: tests/fixtures/hooks/kiro/ (from Kiro's docs; the live Kiro run confirms them, see
reference/kiro.md).

Every hook case runs end to end through run.sh (and the installed hook command itself), as Kiro runs it.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import pytest

from hook_support import (HOOKS, MAP, PLUGIN, POWERSHELL, SH, SKILL_REL, WINDOWS, actionable, hook_env, make_project,
                          payload, read, write)

KIRO_PY = PLUGIN / "scripts" / "kiro.py"
SKILL_NAMES = sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md"))
RAW = 'className="bg-[#ff0000]"'
H1 = "<h1>Today&apos;s tables</h1>"
MARK = "installed by Plumb's kiro.py"
LAUNCHER = (PLUGIN / "hooks" / ("run.cmd" if WINDOWS else "run.sh")).resolve()

needs_sh = pytest.mark.skipif(SH is None, reason="requires POSIX shell (sh)")
posix_only = pytest.mark.skipif(WINDOWS or SH is None, reason="requires POSIX shell (sh, symlinks)")
windows_only = pytest.mark.skipif(not WINDOWS, reason="requires Windows (cmd.exe and PowerShell)")
installed_shell = pytest.mark.skipif(not WINDOWS and SH is None, reason="requires POSIX shell (sh)")


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    return make_project(tmp_path)


# ---------------------------------------------------------------- kiro.py


def kiro(*args: str, stdin: str = "", plugin: Path = PLUGIN, home: Path = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_ROOT", "COPILOT_CLI", "PLUMB_PYTHON")}
    if home is not None:  # Path.home() for a run without --home: never the real one
        env.update({"HOME": str(home), "USERPROFILE": str(home)})
    r = subprocess.run([sys.executable, str(plugin / "scripts" / "kiro.py"), *args], input=stdin, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env, timeout=60)
    assert "Traceback" not in r.stderr, r.stderr
    return r


def install(home: Path = None, project: Path = None, plugin: Path = PLUGIN) -> subprocess.CompletedProcess:
    args = ["--project", str(project)] if project is not None else ["--home", str(home)]
    r = kiro("install", *args, "--yes", plugin=plugin, home=home)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def files_under(folder: Path):
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) if folder.exists() else []


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, text[:200]
    out = {}
    for line in m.group(1).splitlines():
        if line[:1].isspace():
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def hooks_file(base: Path) -> dict:
    return json.loads(read(base / ".kiro" / "hooks" / "plumb.json"))


def _load_kiro():
    spec = importlib.util.spec_from_file_location("plumb_kiro_test", KIRO_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_there_are_skills_to_install():
    assert {"init", "create", "extract", "audit", "update", "upgrade", "status"} <= set(SKILL_NAMES)


def test_install_copies_every_skill_with_its_kiro_name(tmp_path):
    home = tmp_path / "home"
    install(home)
    root = PLUGIN.resolve().as_posix()
    for name in SKILL_NAMES:
        text = read(home / ".kiro" / "skills" / f"plumb-{name}" / "SKILL.md")
        source = read(PLUGIN / "skills" / name / "SKILL.md")
        fm = frontmatter(text)
        # Agent Skills front matter only: the Claude-only keys (allowed-tools, argument-hint,
        # disable-model-invocation) are dropped
        assert set(fm) <= {"name", "description", "metadata"}, fm
        assert fm["name"] == f"plumb-{name}"
        assert fm["description"] == frontmatter(source)["description"].replace("/plumb:", "/plumb-")
        assert "${CLAUDE_PLUGIN_ROOT}" not in text
        if "${CLAUDE_PLUGIN_ROOT}" in source:
            assert f"`{root}` (the Plumb plugin's folder, written in by kiro.py install)." in text
        # the fallback for an unfilled plugin root (the skill's folder + /../..) would point into .kiro: it is gone
        assert "reads literally" not in text and "/../.." not in text
        assert MARK in text
        # commands are /plumb-<name> in Kiro; links to reference/ point into the plugin
        assert not re.search(r"/plumb:[a-z]", text)
        assert "](../../" not in text
        for target in re.findall(r"\]\((/[^)]+|[A-Za-z]:/[^)]+)\)", text):
            assert Path(target).is_file(), target
    assert files_under(home / ".kiro" / "skills") == sorted(f"plumb-{n}/SKILL.md" for n in SKILL_NAMES)


def _hooks_by_trigger(doc: dict) -> dict:
    by_trigger = {}
    for h in doc["hooks"]:
        assert set(h) <= {"name", "description", "trigger", "matcher", "action", "timeout", "enabled"}
        assert h["name"].startswith("Plumb ") and MARK in h["description"]
        assert h["action"]["type"] == "command" and isinstance(h["timeout"], int) and h["timeout"] > 0
        assert h["enabled"] is True
        by_trigger.setdefault(h["trigger"], []).append(h)
    return by_trigger


SCRIPTS = (("SessionStart", "session_start.py"), ("PreToolUse", "pre_edit.py"), ("Stop", "stop_check.py"))


def test_install_writes_the_home_hooks_file_and_only_the_home(tmp_path):
    home = tmp_path / "home"
    out = install(home).stdout
    by_trigger = _hooks_by_trigger(hooks_file(home))
    assert set(by_trigger) == {"SessionStart", "PreToolUse", "Stop"}
    assert sorted(h["matcher"] for h in by_trigger["PreToolUse"]) == ["shell", "write"]
    assert "matcher" not in by_trigger["SessionStart"][0] and "matcher" not in by_trigger["Stop"][0]
    for trigger, script in SCRIPTS:
        for h in by_trigger[trigger]:
            command = h["action"]["command"]
            assert f"Runs {LAUNCHER} {script} --kiro --kiro-global." in h["description"]
            if not WINDOWS:
                assert str(LAUNCHER) in command and f" {script} --kiro --kiro-global" in command
    assert str(home / ".kiro" / "hooks" / "plumb.json") in out
    assert str(home / ".kiro" / "skills" / "plumb-init" / "SKILL.md") in out


def test_install_with_a_project_writes_only_the_project(tmp_path):
    home, project = tmp_path / "home", tmp_path / "app"
    project.mkdir()
    r = install(project=project, home=home)
    assert files_under(project / ".kiro" / "skills") == sorted(f"plumb-{n}/SKILL.md" for n in SKILL_NAMES)
    for h in hooks_file(project)["hooks"]:
        assert "--kiro-global" not in h["action"]["command"] + h["description"]
        assert " --kiro." in h["description"]
    assert not (home / ".kiro").exists()
    assert str(project / ".kiro" / "hooks" / "plumb.json") in r.stdout


def test_home_and_project_together_are_refused(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    r = kiro("install", "--home", str(tmp_path / "home"), "--project", str(project), "--yes")
    assert r.returncode == 2
    actionable(r.stderr)
    assert not (project / ".kiro").exists() and not (tmp_path / "home").exists()


def test_parser_errors_give_the_exact_command():
    r = kiro("frobnicate")
    assert r.returncode == 2
    actionable(r.stderr)
    fix = next(ln for ln in r.stderr.splitlines() if ln.startswith("fix: "))
    assert str(KIRO_PY.resolve()) in fix and "--help" in fix


def test_install_twice_updates_in_place(tmp_path):
    home = tmp_path / "home"
    install(home)
    first = {p: read(home / ".kiro" / p) for p in files_under(home / ".kiro")}
    install(home)
    assert {p: read(home / ".kiro" / p) for p in files_under(home / ".kiro")} == first


def test_install_removes_marked_copies_of_skills_the_plugin_no_longer_has(tmp_path):
    home = tmp_path / "home"
    install(home)
    gone = home / ".kiro" / "skills" / "plumb-retired" / "SKILL.md"
    write(gone, f"---\nname: plumb-retired\ndescription: old\n---\n<!-- {MARK} (Plumb 0.9.0) -->\n")
    mine = home / ".kiro" / "skills" / "plumb-mine" / "SKILL.md"
    write(mine, "---\nname: plumb-mine\ndescription: mine\n---\n")
    r = install(home)
    assert f"remove {gone}" in r.stdout
    assert not gone.exists() and not gone.parent.exists()
    assert mine.is_file()


def test_install_without_yes_shows_the_plan_and_asks_the_user(tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    r = kiro("install", "--project", str(project))
    assert r.returncode == 2
    assert str(project / ".kiro" / "hooks" / "plumb.json") in r.stdout
    assert str(project / ".kiro" / "skills" / "plumb-create" / "SKILL.md") in r.stdout
    assert not (project / ".kiro").exists()
    actionable(r.stderr)
    # the agent must not confirm for the user: no fix: line to run, the user is asked
    assert not any(ln.startswith("fix: ") for ln in r.stderr.splitlines()), r.stderr
    ask = next(ln for ln in r.stderr.splitlines() if ln.startswith("ask the user: "))
    assert "kiro.py" in ask and " install " in ask and "--yes" in ask and str(project) in ask and "yourself" in ask


@pytest.mark.parametrize("answer, written", [("y", True), ("yes", True), ("n", False), ("", False)])
def test_install_asks_when_interactive(tmp_path, monkeypatch, capsys, answer, written):
    mod = _load_kiro()
    monkeypatch.setattr(mod, "interactive", lambda: True)
    monkeypatch.setattr(mod, "ask", lambda prompt: answer)
    home = tmp_path / "home"
    code = mod.main(["install", "--home", str(home)])
    assert (home / ".kiro" / "hooks" / "plumb.json").is_file() is written
    assert code == (0 if written else 1)
    if not written:
        assert "nothing was written" in capsys.readouterr().out


def test_install_refuses_to_overwrite_files_that_are_not_plumbs(tmp_path):
    home = tmp_path / "home"
    write(home / ".kiro" / "skills" / "plumb-init" / "SKILL.md", "---\nname: plumb-init\ndescription: mine\n---\n")
    r = kiro("install", "--home", str(home), "--yes")
    assert r.returncode == 2
    assert "plumb-init" in r.stderr and "not Plumb's" in r.stderr
    actionable(r.stderr)
    assert files_under(home / ".kiro") == ["skills/plumb-init/SKILL.md"]  # nothing else written
    home2 = tmp_path / "home2"
    write(home2 / ".kiro" / "hooks" / "plumb.json", '{"version": "v1", "hooks": []}\n')
    r = kiro("install", "--home", str(home2), "--yes")
    assert r.returncode == 2 and "plumb.json" in r.stderr
    actionable(r.stderr)


@posix_only
def test_install_refuses_to_write_through_a_dangling_symlink(tmp_path):
    project = tmp_path / "app"
    target = tmp_path / "outside" / "pwned.txt"
    link = project / ".kiro" / "skills" / "plumb-init" / "SKILL.md"
    link.parent.mkdir(parents=True)
    os.symlink(str(target), str(link))
    r = kiro("install", "--project", str(project), "--yes")
    assert r.returncode == 2 and "symlink" in r.stderr
    actionable(r.stderr)
    assert not target.exists() and not (project / ".kiro" / "hooks").exists()


@posix_only
def test_install_refuses_a_symlinked_kiro_folder_below_kiro(tmp_path):
    project, elsewhere = tmp_path / "app", tmp_path / "elsewhere"
    (project / ".kiro").mkdir(parents=True)
    elsewhere.mkdir()
    os.symlink(str(elsewhere), str(project / ".kiro" / "hooks"))
    r = kiro("install", "--project", str(project), "--yes")
    assert r.returncode == 2 and "symlink" in r.stderr
    assert files_under(elsewhere) == [] and not (project / ".kiro" / "skills").exists()


def test_install_refuses_a_missing_project_folder(tmp_path):
    r = kiro("install", "--project", str(tmp_path / "nope"), "--yes")
    assert r.returncode == 2
    actionable(r.stderr)


def test_uninstall_removes_only_plumbs_files(tmp_path):
    home, project = tmp_path / "home", tmp_path / "app"
    project.mkdir()
    install(home)
    install(project=project, home=home)
    for base in (home, project):
        write(base / ".kiro" / "skills" / "mine" / "SKILL.md", "---\nname: mine\ndescription: mine\n---\n")
        write(base / ".kiro" / "skills" / "plumb-mine" / "SKILL.md", "---\nname: plumb-mine\ndescription: x\n---\n")
        write(base / ".kiro" / "skills" / "plumb-init" / "notes.md", "my notes\n")
        write(base / ".kiro" / "hooks" / "lint.json", '{"version": "v1", "hooks": []}\n')
    r = kiro("uninstall", "--project", str(project))  # no --yes: nothing removed, the user is asked
    assert r.returncode == 2 and (project / ".kiro" / "hooks" / "plumb.json").is_file()
    actionable(r.stderr)
    assert not any(ln.startswith("fix: ") for ln in r.stderr.splitlines())
    r = kiro("uninstall", "--project", str(project), "--yes", home=home)
    assert r.returncode == 0, r.stderr
    left = ["hooks/lint.json", "skills/mine/SKILL.md", "skills/plumb-init/notes.md", "skills/plumb-mine/SKILL.md"]
    assert files_under(project / ".kiro") == left
    assert (home / ".kiro" / "hooks" / "plumb.json").is_file()  # the home is another scope
    r = kiro("uninstall", "--home", str(home), "--yes")
    assert r.returncode == 0 and files_under(home / ".kiro") == left
    r = kiro("uninstall", "--home", str(home), "--yes")
    assert r.returncode == 0 and "nothing to remove" in r.stdout


def test_uninstall_leaves_a_plumb_json_that_is_not_plumbs(tmp_path):
    home = tmp_path / "home"
    write(home / ".kiro" / "hooks" / "plumb.json", '{"version": "v1", "hooks": [{"name": "mine"}]}\n')
    r = kiro("uninstall", "--home", str(home), "--yes")
    assert r.returncode == 0 and (home / ".kiro" / "hooks" / "plumb.json").is_file()
    assert "nothing to remove" in r.stdout


def test_kiro_py_never_downloads_or_runs_anything():
    tree = read(KIRO_PY)
    for banned in ("urllib", "http.client", "socket", "subprocess", "os.system", "pip "):
        assert banned not in tree, banned


def test_hooks_template_and_constants_agree_with_hooklib():
    for text in (read(HOOKS / "_hooklib.py"), read(KIRO_PY)):
        for const in (f'KIRO_MARK = "{MARK}"', 'KIRO_GLOBAL_ARG = "--kiro-global"', 'KIRO_ARG = "--kiro"'):
            assert const in text, const
    tmpl = json.loads(read(PLUGIN / "kiro" / "plumb-hooks.json.tmpl"))
    assert tmpl["version"] == "v1"


# ---------------------------------------------------------------- the Windows command


def _decode(command: str) -> str:
    words = command.split(" ")
    assert words[:6] == ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand"]
    assert len(words) == 7
    return base64.b64decode(words[6]).decode("utf-16-le")


@pytest.mark.parametrize("global_file", [True, False])
def test_windows_command_is_bare_words_and_fails_open(global_file):
    """cmd.exe, Windows PowerShell 5.1, pwsh 7 and Git Bash all read the command the same way: every token is a bare
    word (no quotes, parentheses, %, & or $ for the host shell); the script inside is the fail-open body hooks.json
    ships for Copilot, with the launcher path made literal."""
    mod = _load_kiro()
    command = mod.hook_command("pre_edit.py", global_file=global_file, windows=True)
    assert re.fullmatch(r"[A-Za-z0-9 +/=-]+", command), command
    script = _decode(command)
    run = str(PureWindowsPath(str(PLUGIN.resolve() / "hooks" / "run.cmd")))
    flags = "--kiro --kiro-global" if global_file else "--kiro"
    assert script == (f"$s='{run}'; if (Test-Path -LiteralPath $s) {{ & $s pre_edit.py {flags}; exit $LASTEXITCODE }}; "
                      f"exit 0")


def test_windows_command_quotes_the_path_and_notes_a_missing_launcher_at_session_start(monkeypatch):
    mod = _load_kiro()
    monkeypatch.setattr(mod, "PLUGIN", Path("C:/Users/o'neil/plumb/1.0.0"))
    script = _decode(mod.hook_command("session_start.py", global_file=True, windows=True))
    assert script.startswith("$s='C:\\Users\\o''neil\\plumb\\1.0.0\\hooks\\run.cmd'; "), script
    assert "else { Write-Output 'Plumb: the Kiro hooks point at a Plumb folder that is gone" in script
    assert "kiro.py install again" in script and script.endswith("exit 0")


def run_installed(command: str, stdin: str, cwd: Path, env, shell: str = "default") -> subprocess.CompletedProcess:
    """Run a hook command from a Kiro hooks file as Kiro does: through the system shell (sh -c; on Windows cmd /c or
    PowerShell)."""
    if WINDOWS:
        argv = ([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", command] if shell == "powershell"
                else ["cmd", "/d", "/c", command])
    else:
        argv = [str(SH), "-c", command]
    r = subprocess.run(argv, input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                       cwd=str(cwd), timeout=60)
    if "no Python 3.9+" in r.stderr:
        pytest.skip("requires POSIX shell with python3 on PATH")
    assert "Traceback" not in r.stderr, r.stderr
    return r


def _command(base: Path, trigger: str, matcher=None) -> str:
    (h,) = [h for h in hooks_file(base)["hooks"] if h["trigger"] == trigger and h.get("matcher") == matcher]
    return h["action"]["command"]


def plugin_folder(dest: Path, version: str = None) -> Path:
    shutil.copytree(str(PLUGIN), str(dest), ignore=shutil.ignore_patterns("__pycache__"))
    if version:
        manifest = dest / ".claude-plugin" / "plugin.json"
        doc = json.loads(read(manifest))
        doc["version"] = version
        write(manifest, json.dumps(doc, indent=2) + "\n")
    return dest


@windows_only
@pytest.mark.parametrize("shell", ["cmd", "powershell"])
def test_windows_installed_commands_run_and_fail_open(tmp_path, proj, shell):
    copy = plugin_folder(tmp_path / "plugin-copy")
    install(project=proj, plugin=copy)
    env = kiro_env(tmp_path)
    stdin = payload("kiro", "fs_write_create", CWD=str(proj), FILE="app/globals.css", CONTENT="x")
    write_cmd = _command(proj, "PreToolUse", "write")
    assert kiro_refused(run_installed(write_cmd, stdin, proj, env, shell)).startswith("error: app/globals.css is generated")
    start = _command(proj, "SessionStart")
    r = run_installed(start, payload("kiro", "session_start", CWD=str(proj)), proj, env, shell)
    assert "Plumb: demo-design-system 1.0.0 · " in r.stdout
    shutil.rmtree(str(copy))
    r = run_installed(write_cmd, stdin, proj, env, shell)
    assert r.returncode == 0, (r.stdout, r.stderr)
    r = run_installed(start, payload("kiro", "session_start", CWD=str(proj)), proj, env, shell)
    assert r.returncode == 0 and "kiro.py install" in r.stdout


# ---------------------------------------------------------------- the hooks with Kiro's payloads, through run.sh


def kiro_env(tmp_path: Path, extra=None):
    """Kiro sets no CLAUDE_PLUGIN_ROOT or CLAUDE_PROJECT_DIR: the hooks find the plugin from their own folder and the
    project from the payload's cwd."""
    env = hook_env(tmp_path, copilot=False, extra=extra)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    return env


def run_kiro_hook(script: str, stdin: str, cwd: Path, env, flags=("--kiro",), plugin: Path = PLUGIN):
    """A hook through run.sh with the arguments kiro.py puts on its commands."""
    r = subprocess.run([str(SH), str(plugin / "hooks" / "run.sh"), script, *flags], input=stdin, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env, cwd=str(cwd), timeout=60)
    if "no Python 3.9+" in r.stderr:
        pytest.skip("requires POSIX shell with python3 on PATH")
    assert "Traceback" not in r.stderr, r.stderr
    return r


def hook(tmp_path, proj, script: str, name: str, env=None, edit_json=None, flags=("--kiro",), **values):
    values.setdefault("CWD", str(proj))
    text = payload("kiro", name, **values)
    if edit_json:
        doc = json.loads(text)
        edit_json(doc)
        text = json.dumps(doc)
    return run_kiro_hook(script, text, proj, env or kiro_env(tmp_path), flags)


def pre(tmp_path, proj, name, **values):
    return hook(tmp_path, proj, "pre_edit.py", name, **values)


def kiro_refused(r) -> str:
    """Kiro's refusal: exit 2, the reason on stderr, nothing on stdout."""
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert r.stdout == ""
    actionable(r.stderr)
    assert not re.search(r"/plumb:[a-z]", r.stderr), r.stderr  # Kiro's commands are /plumb-<name>
    return r.stderr


def kiro_allowed(r) -> None:
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert r.stdout.strip() == "", r.stdout


@needs_sh
def test_session_start_prints_the_status_line_as_plain_text(tmp_path, proj):
    r = hook(tmp_path, proj, "session_start.py", "session_start")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("Plumb: demo-design-system 1.0.0 · tokens up to date · "), r.stdout
    assert not r.stdout.lstrip().startswith("{")


@needs_sh
@pytest.mark.parametrize("event", ["SessionStart", "agentSpawn"])
def test_session_start_is_plain_text_even_with_copilot_env(tmp_path, proj, event):
    """--kiro decides the dialect, not a guess from the payload: a PascalCase SessionStart under COPILOT_CLI is still
    Kiro's plain text."""
    r = hook(tmp_path, proj, "session_start.py", "session_start", env=kiro_env(tmp_path, {"COPILOT_CLI": "1"}),
             edit_json=lambda d: d.update(hook_event_name=event))
    assert r.stdout.startswith("Plumb: demo-design-system 1.0.0 · "), r.stdout


@needs_sh
def test_session_start_nudges_with_kiro_commands(tmp_path, proj):
    text = read(proj / "PLUMB.md").replace("<!-- plumb v1.0.0", "<!-- plumb v0.9.0", 1)
    write(proj / "PLUMB.md", text)
    r = hook(tmp_path, proj, "session_start.py", "session_start")
    assert "run /plumb-upgrade" in r.stdout and "/plumb:" not in r.stdout


@needs_sh
def test_session_start_without_plumb_md_is_silent(tmp_path):
    empty = tmp_path / "no-plumb"
    empty.mkdir()
    r = hook(tmp_path, empty, "session_start.py", "session_start")
    assert r.returncode == 0 and r.stdout == ""


@needs_sh
@pytest.mark.parametrize("rel", ["app/globals.css", "docs/design/prototype.html", MAP,
                                 f"{SKILL_REL}/assets/platforms/web/tokens.css"])
def test_fs_write_create_of_a_generated_file_is_refused(tmp_path, proj, rel):
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_create", FILE=str(proj / rel), CONTENT="x"))
    assert reason.startswith(f"error: {rel} is generated")


@needs_sh
def test_fs_write_with_a_relative_path_is_refused(tmp_path, proj):
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_str_replace", FILE="app/globals.css", OLD="a", NEW="b"))
    assert reason.startswith("error: app/globals.css is generated")
    assert "/plumb-update" in reason


@needs_sh
@pytest.mark.parametrize("name", ["fs_write_str_replace", "fs_write_append"])
def test_fs_write_to_plumbs_own_files_is_refused(tmp_path, proj, name):
    reason = kiro_refused(pre(tmp_path, proj, name, FILE=str(proj / SKILL_REL / "scripts/audit.py"), OLD="a", NEW="b"))
    assert "is Plumb's file; upgrades replace it" in reason
    assert "fix: use /plumb-update for design changes" in reason


@needs_sh
def test_fs_write_under_the_plugin_root_is_refused_without_claude_plugin_root(tmp_path, proj):
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_str_replace", FILE=str(PLUGIN / "hooks" / "pre_edit.py"),
                              OLD="a", NEW="b"))
    assert "is Plumb's file; upgrades replace it" in reason


@needs_sh
def test_fs_write_create_of_a_new_route_is_refused_prototype_first(tmp_path, proj):
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_create", FILE="app/billing/page.tsx",
                              CONTENT="export default function Billing() {\n  return <h1>Billing</h1>;\n}\n"))
    assert "error: app/billing/page.tsx is a new screen with no approved prototype" in reason
    assert "fix: /plumb-prototype billing" in reason


@needs_sh
def test_fs_write_str_replace_adding_a_raw_colour_is_refused(tmp_path, proj):
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_str_replace", FILE=str(proj / "app/page.tsx"), OLD=H1,
                              NEW=f"<h1 {RAW}>Today&apos;s tables</h1>"))
    assert reason.startswith("Plumb edit check: this edit adds 1 design-system error to app/page.tsx")
    assert "#ff0000" in reason
    kiro_allowed(pre(tmp_path, proj, "fs_write_str_replace", FILE=str(proj / "app/page.tsx"), OLD=H1,
                     NEW="<h1>Tables</h1>"))


@needs_sh
@pytest.mark.parametrize("line", [12, "12"])
def test_fs_write_insert_is_checked(tmp_path, proj, line):
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_insert", FILE=str(proj / "app/page.tsx"), LINE=line,
                              NEW=f"      <p {RAW}>note</p>"))
    assert "#ff0000" in reason
    kiro_allowed(pre(tmp_path, proj, "fs_write_insert", FILE=str(proj / "app/page.tsx"), LINE=line,
                     NEW="      <p>note</p>"))


@needs_sh
def test_fs_write_append_is_checked(tmp_path, proj):
    write(proj / "components/widget.tsx", "export const W = () => <p>w</p>;\n")
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_append", FILE=str(proj / "components/widget.tsx"),
                              NEW=f"export const X = () => <p {RAW}>x</p>;\n"))
    assert "#ff0000" in reason
    kiro_allowed(pre(tmp_path, proj, "fs_write_append", FILE=str(proj / "components/widget.tsx"),
                     NEW="export const X = () => <p>x</p>;\n"))


@needs_sh
def test_fs_write_append_with_file_text_is_checked_as_an_append(tmp_path, proj):
    write(proj / "components/legacy.tsx", f"export const L = () => <p {RAW}>l</p>;\n")

    def as_file_text(doc):
        doc["tool_input"]["file_text"] = doc["tool_input"].pop("new_str")

    # appending clean code to a file that already has a raw value adds no error
    kiro_allowed(pre(tmp_path, proj, "fs_write_append", FILE=str(proj / "components/legacy.tsx"),
                     NEW="export const M = () => <p>m</p>;\n", edit_json=as_file_text))
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_append", FILE=str(proj / "components/legacy.tsx"),
                              NEW='export const N = () => <p className="text-[#00ff00]">n</p>;\n',
                              edit_json=as_file_text))
    assert "#00ff00" in reason


@needs_sh
def test_fs_write_of_other_files_is_allowed_silently(tmp_path, proj):
    r = pre(tmp_path, proj, "fs_write_create", FILE=str(proj / "notes.txt"), CONTENT="hi")
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


@needs_sh
@pytest.mark.parametrize("command", ["sed -i 's/a/b/' app/globals.css", "echo x > docs/design/screens.html",
                                     f"sed -i 's/x/y/' {SKILL_REL}/scripts/audit.py"])
def test_execute_bash_writes_are_refused(tmp_path, proj, command):
    reason = kiro_refused(pre(tmp_path, proj, "execute_bash", COMMAND=command))
    assert " is generated" in reason or "is Plumb's file" in reason


@needs_sh
@pytest.mark.parametrize("command", [f"python3 {SKILL_REL}/scripts/build-tokens.py", "cat app/globals.css",
                                     "echo hello > notes.txt"])
def test_execute_bash_reads_and_builds_are_allowed(tmp_path, proj, command):
    kiro_allowed(pre(tmp_path, proj, "execute_bash", COMMAND=command))


@needs_sh
def test_execute_cmd_on_windows_is_a_shell_too(tmp_path, proj):
    reason = kiro_refused(pre(tmp_path, proj, "execute_bash", COMMAND="echo x > docs/design/screens.html",
                              edit_json=lambda d: d.update(tool_name="execute_cmd")))
    assert " is generated" in reason


@needs_sh
def test_camel_case_event_name_is_read(tmp_path, proj):
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_create", FILE="app/globals.css", CONTENT="x",
                              edit_json=lambda d: d.update(hook_event_name="preToolUse")))
    assert reason.startswith("error: app/globals.css is generated")


@needs_sh
def test_kiro_payload_is_answered_in_kiros_dialect_even_with_copilot_env(tmp_path, proj):
    env = kiro_env(tmp_path, {"COPILOT_CLI": "1"})
    r = hook(tmp_path, proj, "pre_edit.py", "fs_write_create", env=env, FILE="app/globals.css", CONTENT="x")
    assert kiro_refused(r).startswith("error: app/globals.css is generated")


@needs_sh
def test_without_plumb_md_kiro_is_never_blocked(tmp_path, proj):
    (proj / "PLUMB.md").unlink()
    kiro_allowed(pre(tmp_path, proj, "fs_write_create", FILE="app/globals.css", CONTENT="x"))


@needs_sh
@pytest.mark.parametrize("stdin", ["", "not json", "[]", '{"tool_name": "fs_write", "tool_input": 7}'])
def test_garbage_input_is_allowed(tmp_path, proj, stdin):
    r = run_kiro_hook("pre_edit.py", stdin, proj, kiro_env(tmp_path))
    assert r.returncode == 0 and r.stdout == ""


@needs_sh
def test_unknown_fs_write_command_is_allowed_for_other_files(tmp_path, proj):
    r = pre(tmp_path, proj, "fs_write_append", FILE=str(proj / "components/new.tsx"), NEW="x",
            edit_json=lambda d: d["tool_input"].update(command="rewrite"))
    kiro_allowed(r)


@needs_sh
def test_stop_blocks_once_with_the_decision_json(tmp_path, proj):
    env = kiro_env(tmp_path)
    hook(tmp_path, proj, "session_start.py", "session_start", env=env)
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    r = hook(tmp_path, proj, "stop_check.py", "stop", env=env)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["decision"] == "block" and "#ff0000" in out["reason"]
    actionable(out["reason"])
    # Kiro sends no stop_hook_active: the next stop only reports, so it can never loop
    r = hook(tmp_path, proj, "stop_check.py", "stop", env=env)
    assert "decision" not in json.loads(r.stdout)


@needs_sh
def test_stop_without_ui_changes_is_silent(tmp_path, proj):
    env = kiro_env(tmp_path)
    hook(tmp_path, proj, "session_start.py", "session_start", env=env)
    r = hook(tmp_path, proj, "stop_check.py", "stop", env=env)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


# ---------------------------------------------------------------- Kiro's own Plumb files are guarded


@needs_sh
@pytest.mark.parametrize("rel", [".kiro/hooks/plumb.json", ".kiro/skills/plumb-init/SKILL.md"])
def test_fs_write_to_kiros_plumb_files_is_refused(tmp_path, proj, rel):
    install(project=proj, home=tmp_path / "home")
    reason = kiro_refused(pre(tmp_path, proj, "fs_write_str_replace", FILE=str(proj / rel), OLD="true", NEW="false"))
    assert reason.startswith(f"error: {rel} is Plumb's Kiro file")
    assert "kiro.py" in reason and " install --project " in reason


@needs_sh
@pytest.mark.parametrize("command", ["sed -i 's/true/false/' .kiro/hooks/plumb.json",
                                     "echo x > .kiro/skills/plumb-init/SKILL.md"])
def test_shell_writes_to_kiros_plumb_files_are_refused(tmp_path, proj, command):
    install(project=proj, home=tmp_path / "home")
    reason = kiro_refused(pre(tmp_path, proj, "execute_bash", COMMAND=command))
    assert "is Plumb's Kiro file" in reason


@needs_sh
def test_home_kiro_plumb_files_are_refused_too(tmp_path, proj):
    home = tmp_path / "home"
    install(home)
    env = kiro_env(tmp_path, {"HOME": str(home), "USERPROFILE": str(home)})
    for rel in (".kiro/hooks/plumb.json", ".kiro/skills/plumb-audit/SKILL.md"):
        reason = kiro_refused(pre(tmp_path, proj, "fs_write_str_replace", env=env, FILE=str(home / rel), OLD="a",
                                  NEW="b"))
        assert "is Plumb's Kiro file" in reason and "kiro.py" in reason and "--project" not in reason


@needs_sh
def test_users_own_kiro_files_are_not_guarded(tmp_path, proj):
    write(proj / ".kiro" / "hooks" / "plumb.json", '{"version": "v1", "hooks": []}\n')
    write(proj / ".kiro" / "skills" / "plumb-mine" / "SKILL.md", "---\nname: plumb-mine\ndescription: x\n---\n")
    for rel in (".kiro/hooks/plumb.json", ".kiro/skills/plumb-mine/SKILL.md", ".kiro/hooks/lint.json"):
        kiro_allowed(pre(tmp_path, proj, "fs_write_create", FILE=str(proj / rel), CONTENT="{}"))


# ---------------------------------------------------------------- the installed hook commands


@installed_shell
def test_installed_commands_run_the_hooks(tmp_path, proj):
    install(project=proj, home=tmp_path / "home")
    env = kiro_env(tmp_path)
    write_cmd = _command(proj, "PreToolUse", "write")
    r = run_installed(write_cmd, payload("kiro", "fs_write_create", CWD=str(proj), FILE="app/globals.css", CONTENT="x"),
                      proj, env)
    assert kiro_refused(r).startswith("error: app/globals.css is generated")
    shell_cmd = _command(proj, "PreToolUse", "shell")
    r = run_installed(shell_cmd, payload("kiro", "execute_bash", CWD=str(proj), COMMAND="cat app/globals.css"), proj, env)
    kiro_allowed(r)
    r = run_installed(_command(proj, "SessionStart"), payload("kiro", "session_start", CWD=str(proj)), proj, env)
    assert r.stdout.startswith("Plumb: demo-design-system 1.0.0 · ")


def _stdin(proj: Path, cwd: Path = None) -> str:
    return payload("kiro", "fs_write_create", CWD=str(cwd or proj), FILE=str(proj / "app/globals.css"), CONTENT="x")


@installed_shell
def test_home_hooks_defer_to_a_healthy_workspace_file_of_the_same_plugin(tmp_path, proj):
    """Kiro CLI runs global and workspace hooks side by side: the home copy stays quiet where the project has its own
    working one, so nothing runs twice."""
    home = tmp_path / "home"
    install(home)
    env = kiro_env(tmp_path)
    home_write = _command(home, "PreToolUse", "write")
    assert kiro_refused(run_installed(home_write, _stdin(proj), proj, env)).startswith("error: app/globals.css is generated")
    r = run_installed(_command(home, "SessionStart"), payload("kiro", "session_start", CWD=str(proj)), proj, env)
    assert r.stdout.startswith("Plumb: ")
    install(project=proj, home=home)
    kiro_allowed(run_installed(home_write, _stdin(proj), proj, env))
    r = run_installed(_command(home, "SessionStart"), payload("kiro", "session_start", CWD=str(proj)), proj, env)
    assert r.returncode == 0 and r.stdout == ""
    # the walk is not widened: from a subfolder (no .kiro there) the home hook runs
    sub = proj / "app"
    assert kiro_refused(run_installed(home_write, _stdin(proj, sub), sub, env)).startswith("error: ")


@installed_shell
def test_home_hooks_do_not_defer_to_a_stale_workspace_file(tmp_path, proj):
    """The reported repro: the project file from an old plugin folder that is then removed, the home file from the live
    plugin. The workspace hook fails open, so the home hook must not stand down."""
    old = plugin_folder(tmp_path / "plugin-old")
    install(project=proj, plugin=old, home=tmp_path / "h0")
    home = tmp_path / "home"
    install(home)
    shutil.rmtree(str(old))
    env = kiro_env(tmp_path)
    kiro_allowed(run_installed(_command(proj, "PreToolUse", "write"), _stdin(proj), proj, env))  # fails open
    reason = kiro_refused(run_installed(_command(home, "PreToolUse", "write"), _stdin(proj), proj, env))
    assert reason.startswith("error: app/globals.css is generated")


@installed_shell
def test_home_hooks_do_not_defer_to_a_disabled_or_foreign_workspace_hook(tmp_path, proj):
    home = tmp_path / "home"
    install(home)
    install(project=proj, home=home)
    env = kiro_env(tmp_path)
    home_write = _command(home, "PreToolUse", "write")
    path = proj / ".kiro" / "hooks" / "plumb.json"
    doc = json.loads(read(path))
    for h in doc["hooks"]:
        if h.get("matcher") == "write":
            h["enabled"] = False
    write(path, json.dumps(doc, indent=2) + "\n")
    assert kiro_refused(run_installed(home_write, _stdin(proj), proj, env)).startswith("error: app/globals.css is generated")
    # a plumb.json that is not Plumb's does not make the home hooks stand down
    write(path, '{"version": "v1", "hooks": []}\n')
    assert kiro_refused(run_installed(home_write, _stdin(proj), proj, env)).startswith("error: app/globals.css is generated")


@installed_shell
def test_installed_command_fails_open_when_the_plugin_moved_and_session_start_says_so(tmp_path, proj):
    """After a plugin update the old path may be gone: a hook that cannot start must never block Kiro's tools (any
    non-zero exit blocks a PreToolUse), and session start tells the agent the checks are off."""
    copy = plugin_folder(tmp_path / "plugin-copy")
    install(project=proj, plugin=copy, home=tmp_path / "home")
    write_cmd, start_cmd = _command(proj, "PreToolUse", "write"), _command(proj, "SessionStart")
    shutil.rmtree(str(copy))
    env = kiro_env(tmp_path)
    r = run_installed(write_cmd, _stdin(proj), proj, env)
    assert r.returncode == 0 and r.stdout == ""
    r = run_installed(start_cmd, payload("kiro", "session_start", CWD=str(proj)), proj, env)
    assert r.returncode == 0
    (line,) = r.stdout.splitlines()
    assert line.startswith(f"Plumb: the Kiro hooks point at a Plumb folder that is gone ({copy.resolve()})")
    assert "ask the user to run python3" in line and "kiro.py install" in line and "again" in line
    assert f'--project "{proj}"' in line or f"--project {proj}" in line


@needs_sh
@pytest.mark.parametrize("flags, scope", [(("--kiro", "--kiro-global"), ""), (("--kiro",), "--project")])
def test_session_start_says_when_a_newer_plumb_is_installed(tmp_path, proj, flags, scope):
    cache = tmp_path / "cache" / "plumb"
    old = plugin_folder(cache / "1.0.0")
    write(cache / "1.2.0" / ".claude-plugin" / "plugin.json", '{"name": "plumb", "version": "1.2.0"}\n')
    write(cache / "1.10.0" / ".claude-plugin" / "plugin.json", '{"name": "other", "version": "9.0.0"}\n')
    r = run_kiro_hook("session_start.py", payload("kiro", "session_start", CWD=str(proj)), proj, kiro_env(tmp_path),
                      flags, plugin=old)
    assert r.returncode == 0, r.stderr
    line = next(ln for ln in r.stdout.splitlines() if "Kiro still uses" in ln)
    assert line.startswith("Plumb 1.2.0 is installed but Kiro still uses 1.0.0: ask the user to run python3 ")
    assert str((cache / "1.2.0" / "scripts" / "kiro.py").resolve()) in line
    assert ("--project" in line) is bool(scope)
    # without a newer one: no such line
    shutil.rmtree(str(cache / "1.2.0"))
    r = run_kiro_hook("session_start.py", payload("kiro", "session_start", CWD=str(proj)), proj, kiro_env(tmp_path),
                      flags, plugin=old)
    assert "Kiro still uses" not in r.stdout


# ---------------------------------------------------------------- in-process: the adapter


@pytest.fixture(scope="module")
def H():
    spec = importlib.util.spec_from_file_location("plumb_hooklib_kiro_test", HOOKS / "_hooklib.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plumb_hooklib_kiro_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_payload_reads_kiro_tools(H, monkeypatch):
    monkeypatch.delenv("COPILOT_CLI", raising=False)
    monkeypatch.setattr(sys, "argv", ["pre_edit.py", "--kiro"])
    p = H.Payload({"hook_event_name": "preToolUse", "cwd": "/w", "session_id": "s", "tool_name": "fs_write",
                   "tool_input": {"command": "str_replace", "path": "a.tsx", "old_str": "x", "new_str": "y"}})
    assert (p.event, p.tool, p.kiro, p.copilot, p.file_path, p.cwd, p.session_id) == \
        ("PreToolUse", "write", True, False, "a.tsx", "/w", "s")
    assert p.changes[0].kind == "edit" and p.changes[0].after("x x") == "y x"
    p = H.Payload({"hook_event_name": "PreToolUse", "tool_name": "execute_bash", "tool_input": {"command": "ls"}})
    assert (p.tool, p.command, p.changes, p.kiro) == ("shell", "ls", [], True)
    assert H.Payload({"hook_event_name": "agentSpawn"}).event == "SessionStart"
    assert H.Payload({"hook_event_name": "stop"}).event == "Stop"
    assert H.Payload({"hook_event_name": "Stop"}).kiro is True  # from --kiro, not from the payload
    assert H.tool_text("fix: /plumb:prototype x, /plumb:update") == "fix: /plumb-prototype x, /plumb-update"


def test_without_kiro_flag_nothing_is_guessed(H, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pre_edit.py"])
    monkeypatch.delenv("COPILOT_CLI", raising=False)
    p = H.Payload({"hook_event_name": "PreToolUse", "tool_name": "fs_write",
                   "tool_input": {"command": "create", "path": "a", "file_text": "x"}})
    assert p.kiro is False and p.copilot is False and p.tool == "write"
    assert H.tool_text("fix: /plumb:prototype x") == "fix: /plumb:prototype x"


@pytest.mark.parametrize("tool_input, kind, before, after", [
    ({"command": "create", "path": "a", "file_text": "new\n"}, "write", "old\n", "new\n"),
    ({"command": "insert", "path": "a", "insert_line": 1, "new_str": "mid"}, "insert", "one\ntwo\n", "one\nmid\ntwo\n"),
    ({"command": "insert", "path": "a", "insert_line": "1", "new_str": "mid"}, "insert", "one\ntwo\n", "one\nmid\ntwo\n"),
    ({"command": "append", "path": "a", "new_str": "end\n"}, "append", "one\n", "one\nend\n"),
    ({"command": "append", "path": "a", "new_str": "end\n"}, "append", "one", "one\nend\n"),
    ({"command": "append", "path": "a", "new_str": "end\n"}, "append", "", "end\n"),
    ({"command": "append", "path": "a", "file_text": "end\n"}, "append", "one\n", "one\nend\n"),
])
def test_fs_write_commands_become_changes(H, tool_input, kind, before, after):
    p = H.Payload({"hook_event_name": "PreToolUse", "tool_name": "fs_write", "tool_input": tool_input})
    (c,) = p.changes
    assert c.kind == kind and c.after(before) == after
