"""The SwiftUI sample app type-checks against its generated theme (macOS with Xcode only).

build-tokens.py writes <Project>Theme.swift for the sample app in tests/fixtures/apps/swiftui/ (with the icon map), and
`swiftc -typecheck` for the iOS simulator checks the theme together with the app's views: as they are (with the
deliberate violations) and after the audit's fixes, which use the theme's colours, text styles, radii and icons.

Collected only on macOS when `xcrun --sdk iphonesimulator --show-sdk-path` answers (conftest.py's
pytest_ignore_collect), so other jobs neither run nor report a skip. Nothing is downloaded or installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List

import pytest

from sample_apps import SWIFTUI, audit, errors, project, read, write

TARGET = "arm64-apple-ios17.0-simulator"


def _sdk() -> str:
    xcrun = shutil.which("xcrun")
    if not xcrun:
        pytest.skip("requires xcrun")
    r = subprocess.run([xcrun, "--sdk", "iphonesimulator", "--show-sdk-path"], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    if r.returncode != 0 or not r.stdout.strip():
        pytest.skip("requires xcrun with the iOS simulator SDK")
    return r.stdout.strip()


def _sources(proj: Path) -> List[Path]:
    theme = proj / SWIFTUI.skill / SWIFTUI.theme
    assert theme.is_file(), theme
    views = sorted((proj / "SampleHabits").glob("*.swift"))
    assert [v.name for v in views] == ["App.swift", "HabitListView.swift", "SettingsView.swift"]
    return [theme, *views]


def _typecheck(proj: Path) -> subprocess.CompletedProcess:
    sdk = _sdk()
    cmd = [str(shutil.which("xcrun")), "swiftc", "-typecheck", "-sdk", sdk, "-target", TARGET,
           *[str(p) for p in _sources(proj)]]
    return subprocess.run(cmd, cwd=str(proj), capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=600)


def test_theme_with_icons_and_the_views_as_written_typecheck(tmp_path):
    proj = project(SWIFTUI, "built", tmp_path)
    theme = read(proj / SWIFTUI.skill / SWIFTUI.theme)
    assert 'case home = "house"' in theme and 'case settings = "gearshape"' in theme
    r = _typecheck(proj)
    assert r.returncode == 0, r.stderr[-6000:]


def test_theme_and_the_fixed_views_typecheck(tmp_path):
    proj = project(SWIFTUI, "ready", tmp_path)
    code, report = audit(proj, SWIFTUI)
    assert code == 0 and errors(report) == []
    views = "\n".join(read(p) for p in sorted((proj / "SampleHabits").glob("*.swift")))
    for name in ("SampleHabitsColor.", "SampleHabitsType.", "SampleHabitsRadius.", "SampleHabitsIcon."):
        assert name in views, name
    r = _typecheck(proj)
    assert r.returncode == 0, r.stderr[-6000:]


def test_a_name_the_theme_does_not_have_fails_the_typecheck(tmp_path):
    proj = project(SWIFTUI, "ready", tmp_path)
    view = proj / "SampleHabits/SettingsView.swift"
    text = read(view)
    assert "SampleHabitsColor.primary" in text
    write(view, text.replace("SampleHabitsColor.primary", "SampleHabitsColor.brand"))
    r = _typecheck(proj)
    assert r.returncode != 0
    assert "brand" in r.stderr, r.stderr[-3000:]
