#!/usr/bin/env python3
"""screenshot.py: a headless screenshot of a page with a Chrome, Edge or Chromium already on this machine.

    screenshot.py URL_OR_FILE --out PNG [--width W] [--height H] [--theme light|dark] [--wait MS] [--timeout S]
                  [--browser PATH]

Used by /plumb:audit (prototype screen vs built route) and /plumb:ux (phone and desktop, light and dark) when the agent
has no browser tool of its own. Plumb installs and downloads nothing: it only runs a browser that is already installed.

  URL_OR_FILE   http(s):// or file:// URL, or a local file (relative to the working folder), optionally with a #fragment
                (docs/design/prototype.html#screen-booking/empty opens that screen in that state)
  --out         the PNG to write (folders are created; an existing file is replaced only by a good screenshot)
  --width       viewport width in CSS pixels (default 1280; 390 for a phone)
  --height      viewport height (default 900)
  --theme       light (default) or dark: sets prefers-color-scheme for the page (--force-dark-mode and Blink's
                preferredColorScheme setting)
  --wait        milliseconds of page time before the shot, so scripts can render (default 2000)
  --timeout     seconds before a browser that hangs is stopped (default 60)
  --browser     the browser executable to use instead of searching

The search, first match wins: the PATH names google-chrome, google-chrome-stable, chromium, chromium-browser,
microsoft-edge, microsoft-edge-stable, chrome, msedge (every OS); then on macOS the app bundles Google Chrome, Chromium and
Microsoft Edge in /Applications and ~/Applications; on Windows chrome.exe / msedge.exe under %ProgramFiles%,
%ProgramFiles(x86)%, %ProgramW6432% and %LOCALAPPDATA% (Google/Chrome, Microsoft/Edge, Chromium). The browser runs with a
throwaway profile (deleted afterwards), with background networking, sync, extensions and component updates off.

Exit codes: 0 written (a browser that keeps running after a complete PNG is stopped) · 1 the browser ran but wrote no
screenshot (or hung) · 2 bad input · 3 no browser found:
`note: visual comparison skipped: no browser found` and a `fix:` line; the caller skips the visual part and every other
check still runs. Python 3.9+, standard library only; no shell.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Mapping, Optional

PATH_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
              "microsoft-edge-stable", "chrome", "msedge")
MAC_APP_DIRS: List[Path] = [Path("/Applications"), Path.home() / "Applications"]
MAC_APPS = (("Google Chrome.app", "Google Chrome"), ("Chromium.app", "Chromium"), ("Microsoft Edge.app", "Microsoft Edge"))
WIN_ROOTS = ("PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "LOCALAPPDATA")
WIN_APPS = ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe", "Chromium/Application/chrome.exe")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_END = b"IEND\xaeB`\x82"  # the IEND chunk's type and CRC: the last bytes of every complete PNG
POLL_SECONDS = 0.2
RMTREE_RETRY_SECONDS = 1.0
URL_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://")
NO_BROWSER = ("note: visual comparison skipped: no browser found (looked for Chrome, Edge and Chromium; Plumb installs "
              "nothing)\nfix: use the agent's own browser tool if it has one; otherwise ask the user whether a Chrome, "
              "Edge or Chromium already on this machine can be used and pass its path with --browser PATH. Every other "
              "check still runs.")


class Refusal(Exception):
    def __init__(self, what: str, fix: str, code: int = 2) -> None:
        super().__init__(f"error: {what}\nfix: {fix}")
        self.code = code


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is not None:
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - leave an odd stream as it is
                pass


# ---------------------------------------------------------------- finding a browser


def _runnable(path: Path, platform: str) -> bool:
    if not path.is_file():
        return False
    return platform.startswith("win") or os.access(str(path), os.X_OK)


def _on_path(env: Mapping[str, str]) -> Optional[Path]:
    value = env.get("PATH")
    if value is None:
        value = next((v for k, v in env.items() if k.upper() == "PATH"), "")
    dirs = os.pathsep.join(d for d in str(value).split(os.pathsep) if d.strip())
    if not dirs:
        return None
    for name in PATH_NAMES:
        found = shutil.which(name, path=dirs)
        if found:
            return Path(found)
    return None


def system_candidates(platform: str, env: Mapping[str, str]) -> List[Path]:
    """Where an installed browser lives on this OS, in the order they are tried (Chrome, then Chromium, then Edge)."""
    if platform == "darwin":
        return [d / app / "Contents" / "MacOS" / exe for app, exe in MAC_APPS for d in MAC_APP_DIRS]
    if platform.startswith("win"):
        upper = {k.upper(): v for k, v in env.items()}
        roots = [Path(upper[r]) for r in WIN_ROOTS if upper.get(r)]
        return [root / Path(rel) for rel in WIN_APPS for root in roots]
    return []  # Linux and the rest: browsers live on PATH


def find_browser(platform: Optional[str] = None, env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    platform = platform or sys.platform
    env = os.environ if env is None else env
    found = _on_path(env)
    if found is not None:
        return found
    return next((p for p in system_candidates(platform, env) if _runnable(p, platform)), None)


# ---------------------------------------------------------------- the shot


def target_url(given: str) -> str:
    m = URL_SCHEME.match(given)
    if m:
        if m.group(1).lower() not in ("http", "https", "file"):
            raise Refusal(f"{given}: only http://, https:// and file:// pages can be shot, not {m.group(1)}://",
                          "pass the page's local file or its http(s) URL (e.g. the dev server's address)")
        return given
    path, fragment = Path(given), ""
    if not path.exists() and "#" in given:
        base, fragment = given.split("#", 1)
        path, fragment = Path(base), "#" + fragment
    if not path.is_file():
        raise Refusal(f"{given}: file not found", "pass an existing HTML file (relative to this folder) or a URL")
    return path.resolve().as_uri() + fragment


def command(browser: Path, url: str, shot: Path, profile: Path, width: int, height: int, theme: str,
            wait_ms: int) -> List[str]:
    args = [str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--disable-sync", "--disable-background-networking",
            "--disable-component-update", f"--user-data-dir={profile}", f"--window-size={width},{height}",
            f"--virtual-time-budget={wait_ms}", f"--screenshot={shot}"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")  # Chrome refuses to start as root (containers, CI) without it
    if theme == "dark":
        args += ["--force-dark-mode", "--blink-settings=preferredColorScheme=0"]
    else:
        args.append("--blink-settings=preferredColorScheme=1")
    args.append(url)
    return args


def _last_line(data: bytes) -> str:
    lines = [ln.strip() for ln in data.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    return lines[-1][:300] if lines else ""


def complete_png(data: bytes) -> bool:
    return data.startswith(PNG_SIGNATURE) and data.endswith(PNG_END)


WINDOWS = os.name == "nt"


def _stop(proc: "subprocess.Popen[bytes]") -> None:
    """Stop the browser and the processes it started: its process group on macOS and Linux (it runs in a session of its
    own), its process tree on Windows (taskkill /T, a system tool, no shell)."""
    if WINDOWS:
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if not WINDOWS:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        proc.kill()
        proc.wait()


def run_browser(args: List[str], shot: Path, log: Path, timeout: float) -> Optional[int]:
    """Run the browser until it exits or the screenshot is complete, whichever comes first; None when it hung.

    Some browser builds keep running after writing the screenshot, so a complete PNG (signature to IEND) ends the run.
    Output goes to a file, not a pipe: helper processes (crash handler, updater) can outlive the browser and would hold
    a pipe open until they exit.

    The browser runs in a session of its own, so Ctrl-C in the terminal does not reach it: anything that interrupts the
    wait (KeyboardInterrupt, SystemExit, an error) stops the browser before it goes on, so no headless browser is left
    running and its profile is removed only after it has stopped."""
    try:
        out_log = open(log, "wb")
    except OSError as exc:
        raise Refusal(f"cannot write the browser log in {log.parent} ({exc.strerror or exc})",
                      "check the temporary folder is writable, then run this again", 1) from None
    with out_log:
        try:
            proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=out_log, stderr=subprocess.STDOUT,
                                    start_new_session=not WINDOWS)
        except OSError as exc:
            raise Refusal(f"cannot run {args[0]} ({exc.strerror or exc})",
                          "pass a working browser with --browser PATH, or use the agent's browser tool", 1) from None
        try:
            return _wait(proc, shot, time.monotonic() + timeout)
        except BaseException:
            _stop(proc)
            raise


def _wait(proc: "subprocess.Popen[bytes]", shot: Path, deadline: float) -> Optional[int]:
    while True:
        code = proc.poll()
        if code is not None:
            return code
        try:
            done = shot.is_file() and complete_png(shot.read_bytes())
        except OSError:
            done = False
        if done:
            _stop(proc)
            return 0
        if time.monotonic() > deadline:
            _stop(proc)
            return None
        time.sleep(POLL_SECONDS)


def shoot(browser: Path, url: str, out: Path, width: int, height: int, theme: str, wait_ms: int, timeout: float) -> None:
    fix = ("open the page in a browser to check it loads (a dev server must be running for a URL), then run this again; "
           "or use the agent's browser tool")
    tmp = Path(tempfile.mkdtemp(prefix="plumb-shot-"))
    try:
        profile, shot, log = tmp / "profile", tmp / "shot.png", tmp / "browser.log"
        args = command(browser, url, shot, profile, width, height, theme, wait_ms)
        code = run_browser(args, shot, log, timeout)
        if code is None:
            raise Refusal(f"{browser.name} did not finish within {timeout:g} s", f"{fix}; or pass a longer --timeout", 1)
        data = shot.read_bytes() if shot.is_file() else b""
        if not complete_png(data):
            said = _last_line(log.read_bytes() if log.is_file() else b"")
            raise Refusal(f"{browser.name} wrote no screenshot of {url} (exit {code})"
                          + (f": {said}" if said else ""), fix, 1)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp_out = out.with_name(out.name + ".part")
            tmp_out.write_bytes(data)
            os.replace(str(tmp_out), str(out))
        except OSError as exc:
            raise Refusal(f"cannot write {out} ({exc.strerror or exc})", "pass a writable --out path ending in .png") from None
    finally:
        remove_tree(tmp)


def remove_tree(path: Path) -> None:
    """Delete the throwaway profile. On Windows a browser helper that is still exiting can hold a file open for a moment,
    so try once more after a short wait; never fail the shot over it."""
    shutil.rmtree(str(path), ignore_errors=True)
    if path.exists():
        time.sleep(RMTREE_RETRY_SECONDS)
        shutil.rmtree(str(path), ignore_errors=True)


# ---------------------------------------------------------------- command line


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: python3 screenshot.py URL_OR_FILE --out shot.png [--width 390] "
                     f"[--theme dark]\n")


def main(argv: Optional[List[str]] = None) -> int:
    utf8_stdio()
    parser = _Parser(prog="screenshot.py", description="Headless screenshot with an installed Chrome, Edge or Chromium.")
    parser.add_argument("target", metavar="URL_OR_FILE", help="the page: a URL or a local HTML file (#fragment allowed)")
    parser.add_argument("--out", required=True, metavar="PNG", help="the PNG file to write")
    parser.add_argument("--width", type=int, default=1280, help="viewport width (default 1280)")
    parser.add_argument("--height", type=int, default=900, help="viewport height (default 900)")
    parser.add_argument("--theme", choices=("light", "dark"), default="light", help="prefers-color-scheme (default light)")
    parser.add_argument("--wait", type=int, default=2000, metavar="MS", help="page time before the shot (default 2000)")
    parser.add_argument("--timeout", type=float, default=60.0, metavar="S", help="stop a hung browser (default 60)")
    parser.add_argument("--browser", metavar="PATH", help="the browser executable (default: search this machine)")
    args = parser.parse_args(argv)
    try:
        if not args.out.lower().endswith(".png"):
            raise Refusal(f"--out {args.out!r} must end in .png", "pass --out <name>.png")
        for name, value, low in (("--width", args.width, 100), ("--height", args.height, 100)):
            if not low <= value <= 10000:
                raise Refusal(f"{name} {value} is out of range ({low} to 10000)", f"pass {name} 390 (phone) or 1280 (desktop)")
        if not 0 <= args.wait <= 120000:
            raise Refusal(f"--wait {args.wait} is out of range (0 to 120000 ms)", "pass --wait 2000")
        if not 0 < args.timeout <= 600:
            raise Refusal(f"--timeout {args.timeout:g} is out of range (above 0, at most 600 s)", "pass --timeout 60")
        url = target_url(args.target)
        if args.browser:
            browser = Path(args.browser)
            if not browser.is_file():
                raise Refusal(f"--browser {args.browser}: no such file",
                              "pass the browser's executable (e.g. the path inside Google Chrome.app/Contents/MacOS/)")
        else:
            found = find_browser()
            if found is None:
                print(NO_BROWSER, file=sys.stderr)
                return 3
            browser = found
        out = Path(args.out).resolve()
        shoot(browser, url, out, args.width, args.height, args.theme, args.wait, args.timeout)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    print(f"wrote: {args.out} ({browser.name}, {args.width}x{args.height}, {args.theme})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
