"""Skip reasons: with PLUMB_STRICT_SKIPS=1 (CI) only platform and tool skips are allowed, by these prefixes.

Docs quote the list from here; every skip reason in tests/ that depends on the OS or a platform tool starts with one.
"""

from __future__ import annotations

import re
from pathlib import Path

import conftest

TESTS = Path(__file__).resolve().parent
PREFIXES = ("requires macOS", "requires Windows", "requires POSIX", "requires xcrun")
# reasons that are not about the platform: they must never happen on CI, so they are not allowed there
NOT_PLATFORM = ("requires Playwright", "requires git", "no python3/python/py -3 on PATH", "no hook launcher")


def test_conftest_allows_exactly_these_prefixes():
    assert conftest.ALLOWED_SKIP_REASONS == PREFIXES


def test_allowed_means_starts_with_a_prefix():
    assert conftest.allowed_skip("requires POSIX: FIFO")
    assert conftest.allowed_skip("requires macOS or Windows: case-insensitive file system")
    assert not conftest.allowed_skip("needs a FIFO (POSIX)")
    assert not conftest.allowed_skip("this requires POSIX")
    assert not conftest.allowed_skip("requires Playwright")


def test_every_skip_reason_in_tests_starts_with_a_prefix_or_is_a_tool_that_ci_has():
    rx = re.compile(r"""(?:reason=|pytest\.skip\()\s*f?(["'])(.*?)\1""")
    bad = []
    for path in sorted(TESTS.glob("*.py")):
        for m in rx.finditer(path.read_text(encoding="utf-8")):
            reason = m.group(2)
            if not reason.startswith(PREFIXES) and not reason.startswith(NOT_PLATFORM):
                bad.append(f"{path.name}: {reason}")
    assert not bad, bad
