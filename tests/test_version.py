"""version.py: the project's Plumb version (PLUMB.md's first line) against the plugin's (plugin.json), and the
upgrade files in between (upgrades/<version>.md, compared as numbers)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/plumb"
SCRIPT = PLUGIN / "scripts/version.py"


def write(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def run(*args: str, cwd: Path | None = None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8",
                          cwd=str(cwd) if cwd else None)


def plumb_md(version: str) -> str:
    return (f"<!-- plumb v{version} · written by /plumb:init, safe to edit values -->\n"
            "# Plumb: the design system for Demo\n\nDesign system: `.claude/skills/demo-design-system/`\n")


@pytest.fixture()
def plugin(tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    write(root / ".claude-plugin/plugin.json", json.dumps({"name": "plumb", "version": "1.2.0"}) + "\n")
    for v in ("0.9.0", "1.0.0", "1.1.0", "1.2.0", "1.10.0", "2.0.0"):
        write(root / f"upgrades/{v}.md", f"# Upgrade to {v}\n\n## What's new\n\nThings.\n")
    write(root / "upgrades/README.md", "# Per-release upgrade steps\n")
    write(root / "upgrades/notes.md", "not a version\n")
    return root


def project(tmp_path: Path, version: str, name: str = "proj", newline: str = "\n") -> Path:
    root = tmp_path / name
    write(root / "PLUMB.md", plumb_md(version), newline)
    return root


def as_json(r) -> dict:
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def assert_refusal(r, *needles: str) -> None:
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert r.stderr.startswith("error: ") and "\nfix: " in r.stderr, r.stderr
    assert "Traceback" not in r.stderr
    for n in needles:
        assert n in r.stderr, r.stderr


def test_older_lists_every_version_in_between_in_numeric_order(tmp_path: Path, plugin: Path) -> None:
    p = project(tmp_path, "0.9.0")
    out = as_json(run("--project", str(p), "--plugin", str(plugin), "--json"))
    assert out == {"project": "0.9.0", "plugin": "1.2.0", "state": "older", "between": ["1.0.0", "1.1.0", "1.2.0"]}


def test_numbers_not_strings(tmp_path: Path, plugin: Path) -> None:
    write(plugin / ".claude-plugin/plugin.json", json.dumps({"name": "plumb", "version": "1.10.0"}))
    out = as_json(run("--project", str(project(tmp_path, "1.1.0")), "--plugin", str(plugin), "--json"))
    assert out["state"] == "older"
    assert out["between"] == ["1.2.0", "1.10.0"]  # 1.10.0 > 1.2.0 > 1.1.0


def test_same_and_newer_have_nothing_in_between(tmp_path: Path, plugin: Path) -> None:
    same = as_json(run("--project", str(project(tmp_path, "1.2.0", "a")), "--plugin", str(plugin), "--json"))
    assert same == {"project": "1.2.0", "plugin": "1.2.0", "state": "same", "between": []}
    newer = as_json(run("--project", str(project(tmp_path, "1.3.0", "b")), "--plugin", str(plugin), "--json"))
    assert newer == {"project": "1.3.0", "plugin": "1.2.0", "state": "newer", "between": []}


def test_the_real_plugin_and_a_fresh_project_are_the_same(tmp_path: Path) -> None:
    version = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    template_line = (PLUGIN / "templates/PLUMB.md").read_text(encoding="utf-8").splitlines()[0]
    p = tmp_path / "fresh"
    write(p / "PLUMB.md", template_line + "\n")
    out = as_json(run("--project", str(p), "--plugin", str(PLUGIN), "--json"))
    assert out == {"project": version, "plugin": version, "state": "same", "between": []}


def test_project_may_be_the_plumb_md_file_crlf_and_bom(tmp_path: Path, plugin: Path) -> None:
    p = tmp_path / "Café Ünïcode"
    write(p / "PLUMB.md", "﻿" + plumb_md("1.0.0"), "\r\n")
    out = as_json(run("--project", str(p / "PLUMB.md"), "--plugin", str(plugin), "--json"))
    assert out["project"] == "1.0.0" and out["between"] == ["1.1.0", "1.2.0"]


def test_plain_output_says_what_to_do(tmp_path: Path, plugin: Path) -> None:
    r = run("--project", str(project(tmp_path, "1.0.0", "a")), "--plugin", str(plugin))
    assert r.returncode == 0, r.stderr
    assert "1.0.0" in r.stdout and "1.2.0" in r.stdout and "/plumb:upgrade" in r.stdout
    assert "1.1.0, 1.2.0" in r.stdout
    r = run("--project", str(project(tmp_path, "1.2.0", "b")), "--plugin", str(plugin))
    assert r.returncode == 0 and "up to date" in r.stdout
    r = run("--project", str(project(tmp_path, "1.3.0", "c")), "--plugin", str(plugin))
    assert r.returncode == 0 and "newer" in r.stdout and "plugin update" in r.stdout


def test_relative_paths_from_the_working_folder(tmp_path: Path, plugin: Path) -> None:
    project(tmp_path, "1.1.0")
    out = as_json(run("--project", "proj", "--plugin", "plugin", "--json", cwd=tmp_path))
    assert out["between"] == ["1.2.0"]


def test_refusals(tmp_path: Path, plugin: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert_refusal(run("--project", str(empty), "--plugin", str(plugin), "--json"), "PLUMB.md", "/plumb:init")
    nover = tmp_path / "nover"
    write(nover / "PLUMB.md", "# Plumb: the design system for Demo\n")
    assert_refusal(run("--project", str(nover), "--plugin", str(plugin)), "version line", "<!-- plumb v")
    p = project(tmp_path, "1.0.0")
    assert_refusal(run("--project", str(p), "--plugin", str(tmp_path / "nowhere")), "plugin.json")
    bad = tmp_path / "bad-plugin"
    write(bad / ".claude-plugin/plugin.json", "{not json")
    assert_refusal(run("--project", str(p), "--plugin", str(bad)), "plugin.json", "line 1")
    nov = tmp_path / "noversion-plugin"
    write(nov / ".claude-plugin/plugin.json", json.dumps({"name": "plumb"}))
    assert_refusal(run("--project", str(p), "--plugin", str(nov)), "version")
    odd = tmp_path / "odd-plugin"
    write(odd / ".claude-plugin/plugin.json", json.dumps({"name": "plumb", "version": "one"}))
    assert_refusal(run("--project", str(p), "--plugin", str(odd)), "'one'")
    assert_refusal(run("--plugin", str(plugin)), "--project")
    assert_refusal(run("--project", str(p)), "--plugin")
