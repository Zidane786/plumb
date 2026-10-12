"""Shared pytest hooks.

Strict skips: with PLUMB_STRICT_SKIPS=1 (set in CI only) any skipped test whose reason is not a
platform / tool-availability reason fails the session. Browser tests skip locally when Playwright is
missing ("requires Playwright"); on CI that must never happen silently.
"""

import os

import pytest

ALLOWED_SKIP_REASONS = (
    "requires macOS",
    "requires Windows",
    "requires POSIX shell",
    "requires xcrun",
)

_unexpected_skips: list = []


def _strict() -> bool:
    return os.environ.get("PLUMB_STRICT_SKIPS") == "1"


def pytest_runtest_logreport(report) -> None:
    if not _strict() or not report.skipped:
        return
    lr = report.longrepr
    reason = lr[2] if isinstance(lr, tuple) and len(lr) == 3 else str(lr)
    if reason.startswith("Skipped: "):
        reason = reason[len("Skipped: "):]
    if not any(a in reason for a in ALLOWED_SKIP_REASONS):
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
