"""screenshot.py: a headless screenshot with a Chrome, Edge or Chromium already on the machine, never a download.

The browser is a stub on PATH (a small Python script behind a `google-chrome` launcher) that records its arguments and
writes a PNG, so these tests run the same on every OS, with or without a real browser installed. The search itself
(PATH names, macOS app bundles, Windows Program Files / LocalAppData) is tested in-process on fake folders.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/plumb/scripts/screenshot.py"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32 + b"IEND\xaeB`\x82"

STUB = '''
import json, os, sys, time
log = os.environ.get("STUB_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(sys.argv[1:]) + "\\n")
mode = os.environ.get("STUB_MODE", "ok")
shot = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--screenshot="))
if mode == "ok":
    with open(shot, "wb") as fh:
        fh.write(%r)
elif mode == "linger":  # some browser builds keep running after writing the shot
    with open(os.environ["STUB_PID"], "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    with open(shot, "wb") as fh:
        fh.write(%r)
    time.sleep(8)
elif mode == "partial":  # a PNG that never gets its end
    with open(shot, "wb") as fh:
        fh.write(%r[:12])
elif mode == "notpng":
    with open(shot, "wb") as fh:
        fh.write(b"hello")
elif mode == "fail":
    sys.stderr.write("[0101/000000.000:ERROR:headless_shell.cc] cannot open the page\\n")
    sys.exit(1)
elif mode == "hang":  # writes nothing and never exits
    with open(os.environ["STUB_PID"], "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    time.sleep(60)
elif mode == "slow":
    time.sleep(4)
''' % (PNG, PNG, PNG)


def _load():
    spec = importlib.util.spec_from_file_location("plumb_screenshot", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plumb_screenshot"] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load()


def make_launcher(folder: Path, name: str, stub: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = folder / f"{name}.cmd"
        path.write_text(f'@"{sys.executable}" "{stub}" %*\r\n', encoding="utf-8")
    else:
        path = folder / name
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub}" "$@"\n', encoding="utf-8")
        path.chmod(0o755)
    return path


@pytest.fixture()
def stub(tmp_path: Path):
    """(bin folder holding a google-chrome launcher, log file of the argument lists it was called with)."""
    script = tmp_path / "stub_browser.py"
    script.write_text(STUB, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    make_launcher(bin_dir, "google-chrome", script)
    return bin_dir, tmp_path / "calls.jsonl"


def run(stub, *args: str, mode: str = "ok", cwd: Path | None = None, path: str | None = None):
    bin_dir, log = stub
    env = dict(os.environ, PATH=str(bin_dir) if path is None else path, STUB_LOG=str(log), STUB_MODE=mode,
               STUB_PID=str(log.parent / "stub.pid"))
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=str(cwd) if cwd else None, timeout=60)


def calls(stub) -> list:
    log = stub[1]
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def page(tmp_path: Path, name: str = "page.html") -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<!doctype html><title>x</title><p>Hi</p>\n", encoding="utf-8")
    return p


def assert_refusal(r, *needles: str) -> None:
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "error: " in r.stderr and "\nfix: " in r.stderr, r.stderr
    assert "Traceback" not in r.stderr
    for n in needles:
        assert n in r.stderr, r.stderr


def flag(args: list, name: str) -> str | None:
    return next((a.split("=", 1)[1] for a in args if a.startswith(name + "=")), None)


# ---------------------------------------------------------------- running the browser


def test_file_screenshot_light_by_default(tmp_path: Path, stub) -> None:
    src = page(tmp_path)
    out = tmp_path / "shots/page.png"
    r = run(stub, str(src), "--out", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.read_bytes() == PNG
    assert "wrote" in r.stdout and "page.png" in r.stdout and "light" in r.stdout
    (args,) = calls(stub)
    assert args[-1] == src.resolve().as_uri()
    assert "--headless=new" in args
    assert flag(args, "--window-size") == "1280,900"
    assert flag(args, "--user-data-dir")  # a throwaway profile, never the user's own
    assert "--force-dark-mode" not in args
    assert flag(args, "--blink-settings") == "preferredColorScheme=1"
    assert not Path(flag(args, "--user-data-dir")).exists()  # removed afterwards


def test_inside_a_plumb_project_the_profile_stays_in_the_project(tmp_path: Path, stub) -> None:
    """Live test 2 (B10): nothing is written outside the project. With a PLUMB.md in the working folder or above, the
    throwaway profile lives in <project>/.plumb-tmp/, which this run removes again when it made it."""
    project = tmp_path / "proj"
    (project / "app").mkdir(parents=True)
    (project / "PLUMB.md").write_text("Project: demo\n", encoding="utf-8")
    src = page(project)
    r = run(stub, str(src), "--out", str(project / "shot.png"), cwd=project / "app")
    assert r.returncode == 0, r.stdout + r.stderr
    (args,) = calls(stub)
    profile = Path(flag(args, "--user-data-dir"))
    assert project.resolve() / ".plumb-tmp" in profile.resolve().parents
    assert not (project / ".plumb-tmp").exists()
    (project / ".plumb-tmp").mkdir()  # a setup's folder is kept, only the profile goes
    (project / ".plumb-tmp" / "answers.json").write_text("{}", encoding="utf-8")
    assert run(stub, str(src), "--out", str(project / "shot.png"), cwd=project).returncode == 0
    assert sorted(p.name for p in (project / ".plumb-tmp").iterdir()) == ["answers.json"]


def test_run_from_elsewhere_the_profile_follows_the_out_path(tmp_path: Path, stub) -> None:
    """Review M5: run from a folder outside the project, the --out path (inside it) still finds its PLUMB.md."""
    project = tmp_path / "proj"
    (project / "docs/design").mkdir(parents=True)
    (project / "PLUMB.md").write_text("Project: demo\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    src = page(project)
    r = run(stub, str(src), "--out", str(project / "docs/design/shots/home.png"), cwd=elsewhere)
    assert r.returncode == 0, r.stdout + r.stderr
    (args,) = calls(stub)
    assert project.resolve() / ".plumb-tmp" in Path(flag(args, "--user-data-dir")).resolve().parents
    assert not (project / ".plumb-tmp").exists() and list(elsewhere.iterdir()) == []


def test_dark_theme_width_and_height(tmp_path: Path, stub) -> None:
    src = page(tmp_path)
    out = tmp_path / "dark.png"
    r = run(stub, str(src), "--out", str(out), "--width", "390", "--height", "844", "--theme", "dark")
    assert r.returncode == 0, r.stderr
    (args,) = calls(stub)
    assert flag(args, "--window-size") == "390,844"
    assert "--force-dark-mode" in args
    assert flag(args, "--blink-settings") == "preferredColorScheme=0"
    assert "dark" in r.stdout


def test_urls_and_fragments(tmp_path: Path, stub) -> None:
    r = run(stub, "http://localhost:3000/booking?x=1", "--out", str(tmp_path / "a.png"))
    assert r.returncode == 0, r.stderr
    src = page(tmp_path, "docs/design/prototype.html")
    r = run(stub, f"{src}#screen-booking/empty", "--out", str(tmp_path / "b.png"))
    assert r.returncode == 0, r.stderr
    first, second = calls(stub)
    assert first[-1] == "http://localhost:3000/booking?x=1"
    assert second[-1] == src.resolve().as_uri() + "#screen-booking/empty"


def test_relative_and_unicode_paths(tmp_path: Path, stub) -> None:
    home = tmp_path / "Café Ünïcode"
    page(home, "docs/design/screens.html")
    r = run(stub, "docs/design/screens.html", "--out", "shots/screens.png", cwd=home)
    assert r.returncode == 0, r.stderr
    assert (home / "shots/screens.png").read_bytes() == PNG
    (args,) = calls(stub)
    assert args[-1] == (home / "docs/design/screens.html").resolve().as_uri()


def test_explicit_browser_path(tmp_path: Path, stub) -> None:
    other = make_launcher(tmp_path / "elsewhere", "my-browser", tmp_path / "stub_browser.py")
    r = run(stub, str(page(tmp_path)), "--out", str(tmp_path / "x.png"), "--browser", str(other), path="")
    assert r.returncode == 0, r.stderr
    assert len(calls(stub)) == 1


def test_browser_failures_exit_1_and_keep_the_old_file(tmp_path: Path, stub) -> None:
    src = page(tmp_path)
    out = tmp_path / "keep.png"
    out.write_bytes(b"old")
    for mode in ("fail", "notpng", "partial"):
        r = run(stub, str(src), "--out", str(out), mode=mode)
        assert r.returncode == 1, (mode, r.stdout, r.stderr)
        assert "error: " in r.stderr and "\nfix: " in r.stderr and "Traceback" not in r.stderr
        assert out.read_bytes() == b"old"
    r = run(stub, str(src), "--out", str(out), mode="fail")
    assert "cannot open the page" in r.stderr  # the browser's own last line is shown


@pytest.mark.speed
def test_a_browser_that_lingers_after_a_complete_shot_is_stopped(tmp_path: Path, stub) -> None:
    out = tmp_path / "x.png"
    start = time.monotonic()
    r = run(stub, str(page(tmp_path)), "--out", str(out), mode="linger")
    assert r.returncode == 0, r.stderr
    assert out.read_bytes() == PNG
    assert time.monotonic() - start < 7
    pid = int((tmp_path / "stub.pid").read_text(encoding="utf-8"))
    assert not alive(pid), "the browser was left running"


def alive(pid: int) -> bool:
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_an_interrupted_shot_stops_the_browser_before_removing_its_profile(tmp_path: Path, stub, monkeypatch) -> None:
    bin_dir, _log = stub
    launcher = next(p for p in bin_dir.iterdir() if p.name.startswith("google-chrome"))
    pid_file = tmp_path / "hang.pid"
    monkeypatch.setenv("STUB_MODE", "hang")
    monkeypatch.setenv("STUB_PID", str(pid_file))
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(S.tempfile, "tempdir", str(temp_root))
    real_sleep = time.sleep
    seen = {}

    def interrupt(seconds: float) -> None:  # Ctrl-C arrives once the browser is up
        if "profiles" not in seen and pid_file.is_file() and pid_file.read_text(encoding="utf-8").strip():
            seen["profiles"] = [p.name for p in temp_root.iterdir()]
            raise KeyboardInterrupt
        real_sleep(seconds)

    monkeypatch.setattr(S.time, "sleep", interrupt)
    with pytest.raises(KeyboardInterrupt):
        S.shoot(launcher, page(tmp_path).resolve().as_uri(), tmp_path / "x.png", 390, 844, "light", 0, 30)
    pid = int(pid_file.read_text(encoding="utf-8"))
    assert not alive(pid), "an interrupted shot left the browser running"
    assert seen["profiles"] and list(temp_root.iterdir()) == []  # the profile existed, and is gone after the stop


def test_a_browser_that_hangs_is_stopped(tmp_path: Path, stub) -> None:
    r = run(stub, str(page(tmp_path)), "--out", str(tmp_path / "x.png"), "--timeout", "1", mode="slow")
    assert r.returncode == 1, r.stderr
    assert "did not finish" in r.stderr and "\nfix: " in r.stderr


def test_bad_input_exits_2(tmp_path: Path, stub) -> None:
    src = page(tmp_path)
    assert_refusal(run(stub, str(tmp_path / "missing.html"), "--out", str(tmp_path / "x.png")), "missing.html")
    assert_refusal(run(stub, str(src), "--out", str(tmp_path / "x.jpg")), ".png")
    assert_refusal(run(stub, str(src), "--out", str(tmp_path / "x.png"), "--width", "0"), "--width")
    assert_refusal(run(stub, str(src), "--out", str(tmp_path / "x.png"), "--theme", "sepia"), "--theme")
    assert_refusal(run(stub, "ftp://example.com/x", "--out", str(tmp_path / "x.png")), "ftp")
    assert_refusal(run(stub, str(src), "--out", str(tmp_path / "x.png"), "--browser", str(tmp_path / "nope")), "nope")
    assert_refusal(run(stub, str(src)), "--out")
    assert calls(stub) == []


# ---------------------------------------------------------------- no browser: skip with a note, never a download


def test_no_browser_exits_3_with_note_and_fix(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(S, "find_browser", lambda *a, **k: None)
    out = tmp_path / "x.png"
    code = S.main([str(page(tmp_path)), "--out", str(out)])
    err = capsys.readouterr().err
    assert code == 3
    assert err.startswith("note: visual comparison skipped: no browser found")
    assert "\nfix: " in err and "browser tool" in err and "--browser" in err
    assert not out.exists()


def test_search_finds_nothing_on_an_empty_machine(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(S, "MAC_APP_DIRS", [tmp_path / "Applications"])
    empty = str(tmp_path / "empty-bin")
    for platform in ("darwin", "win32", "linux"):
        assert S.find_browser(platform, {"PATH": empty}) is None


def test_search_path_names_first(tmp_path: Path, stub, monkeypatch) -> None:
    bin_dir, _log = stub
    monkeypatch.setattr(S, "MAC_APP_DIRS", [tmp_path / "Applications"])
    for platform in ("darwin", "linux", "win32"):
        found = S.find_browser(platform, {"PATH": str(bin_dir)})
        assert found is not None and found.parent == bin_dir, platform
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        assert name in S.PATH_NAMES


def test_search_macos_app_bundles(tmp_path: Path, monkeypatch) -> None:
    apps = tmp_path / "Applications"
    exe = apps / "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setattr(S, "MAC_APP_DIRS", [apps])
    assert S.find_browser("darwin", {"PATH": ""}) == exe
    chrome = apps / "Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome.parent.mkdir(parents=True)
    chrome.write_text("#!/bin/sh\n", encoding="utf-8")
    chrome.chmod(0o755)
    assert S.find_browser("darwin", {"PATH": ""}) == chrome  # Chrome before Edge
    assert S.find_browser("linux", {"PATH": ""}) is None  # app bundles are a macOS place only


def test_search_windows_program_files_and_local_app_data(tmp_path: Path) -> None:
    local = tmp_path / "Local"
    edge = tmp_path / "PF86/Microsoft/Edge/Application/msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_bytes(b"")
    env = {"PATH": "", "ProgramFiles": str(tmp_path / "PF"), "ProgramFiles(x86)": str(tmp_path / "PF86"),
           "LOCALAPPDATA": str(local)}
    assert S.find_browser("win32", env) == edge
    chrome = local / "Google/Chrome/Application/chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"")
    assert S.find_browser("win32", {k.upper(): v for k, v in env.items()}) == chrome  # env names in any case


def test_never_downloads_or_uses_a_shell() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for banned in ("urllib", "http.client", "socket", "shell=True", "pip ", "npx", "playwright install"):
        assert banned not in text, banned
