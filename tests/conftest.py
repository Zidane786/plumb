"""Shared pytest hooks.

Strict skips: with PLUMB_STRICT_SKIPS=1 (set in CI only) any skipped test whose reason does not start
with one of ALLOWED_SKIP_REASONS (a platform or platform-tool reason, e.g. "requires POSIX: FIFO",
"requires Windows: real PowerShell/cmd launcher") fails the session. Browser tests skip locally when Playwright is
missing ("requires Playwright"); on CI that must never happen silently.

Slow runners: with PLUMB_CPU_SLOW=N every browser test's page runs with Chromium's CPU slowed N times (DevTools
Emulation.setCPUThrottlingRate), the way a busy CI runner behaves. Browser tests must pass at PLUMB_CPU_SLOW=10.
"""

import os
import shutil
import subprocess
import sys

import pytest

# Collected only where they can run, so other OSes neither run them nor report a skip.
_MACOS_XCODE_ONLY = {"test_swift_typecheck.py"}
_xcode: list = []


def _has_ios_sdk() -> bool:
    """macOS with xcrun and the iOS simulator SDK (Xcode, not only the command line tools)."""
    if not _xcode:
        ok = False
        xcrun = shutil.which("xcrun") if sys.platform == "darwin" else None
        if xcrun:
            try:
                r = subprocess.run([xcrun, "--sdk", "iphonesimulator", "--show-sdk-path"], capture_output=True,
                                   text=True, encoding="utf-8", timeout=60)
                ok = r.returncode == 0 and bool(r.stdout.strip())
            except (OSError, subprocess.SubprocessError):
                ok = False
        _xcode.append(ok)
    return _xcode[0]


def pytest_ignore_collect(collection_path, config):
    if collection_path.name in _MACOS_XCODE_ONLY and not _has_ios_sdk():
        return True
    return None

ALLOWED_SKIP_REASONS = (
    "requires macOS",
    "requires Windows",
    "requires POSIX",
    "requires xcrun",
)

_unexpected_skips: list = []


def allowed_skip(reason: str) -> bool:
    """A skip reason CI accepts: it starts with one of ALLOWED_SKIP_REASONS."""
    return reason.startswith(ALLOWED_SKIP_REASONS)


def _strict() -> bool:
    return os.environ.get("PLUMB_STRICT_SKIPS") == "1"


def pytest_runtest_logreport(report) -> None:
    if not _strict() or not report.skipped:
        return
    lr = report.longrepr
    reason = lr[2] if isinstance(lr, tuple) and len(lr) == 3 else str(lr)
    if reason.startswith("Skipped: "):
        reason = reason[len("Skipped: "):]
    if not allowed_skip(reason):
        _unexpected_skips.append((report.nodeid, reason))


# ---------------------------------------------------------------- the real home is never written (~/.plumb)

_REAL_HOME: list = []


def _real_plumb_state(home: str) -> list:
    """Every path under <real home>/.plumb with its size and modification time ([] when it does not exist)."""
    root = os.path.join(home, ".plumb")
    if not os.path.lexists(root):
        return []
    out = [(".", os.lstat(root).st_mtime_ns)]
    for folder, dirs, files in os.walk(root):
        for name in sorted(dirs + files):
            path = os.path.join(folder, name)
            st = os.lstat(path)
            out.append((os.path.relpath(path, root), st.st_size, st.st_mtime_ns))
    return sorted(out)


def _browsers_path(home: str) -> str:
    """Where Playwright keeps its browsers for the real user (its own default), so the browser tests still find
    Chromium after HOME moves."""
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local")), "ms-playwright")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Caches", "ms-playwright")
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"), "ms-playwright")


def pytest_configure(config) -> None:
    """Every test, and every hook or script a test starts, sees a throwaway home (HOME and USERPROFILE), so nothing
    can reach the real ~/.plumb/feedback/; PLAYWRIGHT_BROWSERS_PATH keeps pointing at the real browser cache. The
    session fails if the real ~/.plumb changed anyway (pytest_sessionfinish)."""
    import tempfile
    real = os.path.expanduser("~")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _browsers_path(real))
    fake = tempfile.mkdtemp(prefix="plumb-test-home-")
    os.environ["HOME"] = fake
    os.environ["USERPROFILE"] = fake
    _REAL_HOME[:] = [real, _real_plumb_state(real), fake]
    if os.environ.get("PLUMB_CPU_SLOW"):
        _slow_pages(float(os.environ["PLUMB_CPU_SLOW"]))


def _slow_pages(rate: float) -> None:
    """PLUMB_CPU_SLOW: every new page runs with the CPU slowed `rate` times (Chromium only)."""
    try:
        from playwright.sync_api._generated import BrowserContext
    except ImportError:
        return  # no Playwright: the browser tests skip anyway
    new_page = BrowserContext.new_page

    def slow_page(self, *args, **kwargs):
        page = new_page(self, *args, **kwargs)
        self.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": rate})
        return page

    BrowserContext.new_page = slow_page


def _real_home_problem() -> str:
    if not _REAL_HOME:
        return ""
    real, before, fake = _REAL_HOME
    import shutil
    shutil.rmtree(fake, ignore_errors=True)
    if _real_plumb_state(real) != before:
        return (f"a test wrote the real {os.path.join(real, '.plumb')} (tests must use their own HOME/USERPROFILE; "
                f"see conftest.py and hook_support.hook_env)")
    return ""


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus) -> None:
    problem = _real_home_problem()
    if problem:
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        if tr is not None:
            tr.write_line("\n" + problem, red=True)
        else:
            print(problem)
        session.exitstatus = 1
    if not _strict() or not _unexpected_skips:
        return
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    lines = ["", "PLUMB_STRICT_SKIPS=1: unexpected skips (only platform/tool skips are allowed):"]
    lines += [f"  {nodeid}: {reason}" for nodeid, reason in _unexpected_skips]
    text = "\n".join(lines)
    if tr is not None:
        tr.write_line(text, red=True)
    else:
        print(text)
    session.exitstatus = 1
