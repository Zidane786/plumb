"""Shared pytest hooks.

Strict skips: with PLUMB_STRICT_SKIPS=1 (set in CI only) any skipped test whose reason does not start
with one of ALLOWED_SKIP_REASONS (a platform or platform-tool reason, e.g. "requires POSIX: FIFO",
"requires Windows: real PowerShell/cmd launcher") fails the session. Browser tests skip locally when Playwright is
missing ("requires Playwright"); on CI that must never happen silently.
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


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus) -> None:
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
