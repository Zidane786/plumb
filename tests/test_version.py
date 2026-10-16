"""version.py: the project's Plumb version (PLUMB.md's first line) against the plugin's (plugin.json), and the
upgrade files in between (upgrades/<version>.md, compared as numbers)."""

from __future__ import annotations

import json
import re
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
    assert out == {"project": "0.9.0", "plugin": "1.2.0", "state": "older", "between": ["1.0.0", "1.1.0", "1.2.0"],
                   "files_differ": []}


def test_numbers_not_strings(tmp_path: Path, plugin: Path) -> None:
    write(plugin / ".claude-plugin/plugin.json", json.dumps({"name": "plumb", "version": "1.10.0"}))
    out = as_json(run("--project", str(project(tmp_path, "1.1.0")), "--plugin", str(plugin), "--json"))
    assert out["state"] == "older"
    assert out["between"] == ["1.2.0", "1.10.0"]  # 1.10.0 > 1.2.0 > 1.1.0


def test_same_and_newer_have_nothing_in_between(tmp_path: Path, plugin: Path) -> None:
    same = as_json(run("--project", str(project(tmp_path, "1.2.0", "a")), "--plugin", str(plugin), "--json"))
    assert same == {"project": "1.2.0", "plugin": "1.2.0", "state": "same", "between": [], "files_differ": []}
    newer = as_json(run("--project", str(project(tmp_path, "1.3.0", "b")), "--plugin", str(plugin), "--json"))
    assert newer == {"project": "1.3.0", "plugin": "1.2.0", "state": "newer", "between": [], "files_differ": []}


def test_the_real_plugin_and_a_fresh_project_are_the_same(tmp_path: Path) -> None:
    version = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    template_line = (PLUGIN / "templates/PLUMB.md").read_text(encoding="utf-8").splitlines()[0]
    p = tmp_path / "fresh"
    write(p / "PLUMB.md", template_line + "\n")
    out = as_json(run("--project", str(p), "--plugin", str(PLUGIN), "--json"))
    assert out == {"project": version, "plugin": version, "state": "same", "between": [], "files_differ": []}


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
    assert r.stdout.index("marketplace update plumb") < r.stdout.index("plugin update plumb@plumb")


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


# ---------------------------------------------------------------- same version, a newer build of Plumb's files

SKILL = ".claude/skills/demo-design-system"


def plugin_files(plugin: Path) -> None:
    """The plugin's own copies of Plumb's [P] files (assets/skill/...), the ones scaffold.py copies into a project."""
    src = plugin / "assets/skill"
    write(src / "scripts/_plumb.py", "core = 1\n")
    write(src / "scripts/audit.py", "audit = 1\n")
    write(src / "templates/player.js", "player();\n")
    write(src / "templates/app-shell.html.tmpl", "<html></html>\n")
    write(src / "assets/platforms/README.md", "# Platforms\n")
    write(src / "SKILL.md.tmpl", "yours, never compared\n")
    write(src / "references/components.md.tmpl", "yours, never compared\n")


def copy_into(plugin: Path, root: Path) -> None:
    src = plugin / "assets/skill"
    for rel in ("scripts/_plumb.py", "scripts/audit.py", "templates/player.js", "templates/app-shell.html.tmpl",
                "assets/platforms/README.md"):
        write(root / SKILL / rel, (src / rel).read_text(encoding="utf-8"))


def test_same_version_lists_plumb_files_that_differ_from_the_plugin(tmp_path: Path, plugin: Path) -> None:
    plugin_files(plugin)
    p = project(tmp_path, "1.2.0")
    copy_into(plugin, p)
    assert as_json(run("--project", str(p), "--plugin", str(plugin), "--json"))["files_differ"] == []
    write(plugin / "assets/skill/scripts/audit.py", "audit = 2\n")          # a newer build of the same version
    write(plugin / "assets/skill/templates/chrome-roles.css", ":root{}\n")  # a file new in that build
    write(p / SKILL / "SKILL.md", "the project's own text\n")              # yours: never compared
    write(p / SKILL / "scripts/local-helper.py", "x = 1\n")                 # not the plugin's: ignored
    out = as_json(run("--project", str(p), "--plugin", str(plugin), "--json"))
    assert out["state"] == "same"
    assert out["files_differ"] == [f"{SKILL}/scripts/audit.py", f"{SKILL}/templates/chrome-roles.css"]
    plain = run("--project", str(p), "--plugin", str(plugin))
    assert plain.returncode == 0
    assert "2 of Plumb's files" in plain.stdout and "/plumb:upgrade" in plain.stdout
    assert "up to date" not in plain.stdout


def test_line_endings_and_bom_are_not_a_difference(tmp_path: Path, plugin: Path) -> None:
    plugin_files(plugin)
    p = project(tmp_path, "1.2.0")
    copy_into(plugin, p)
    write(p / SKILL / "scripts/audit.py", "\ufeffaudit = 1\n", "\r\n")  # a Windows checkout
    assert as_json(run("--project", str(p), "--plugin", str(plugin), "--json"))["files_differ"] == []


def test_files_are_compared_only_when_the_version_is_the_same(tmp_path: Path, plugin: Path) -> None:
    plugin_files(plugin)
    older = project(tmp_path, "1.1.0", "older")   # the upgrade refreshes them anyway
    newer = project(tmp_path, "1.3.0", "newer")   # the project's files are the newer ones: never offered back
    for p in (older, newer):
        write(p / SKILL / "scripts/audit.py", "something else\n")
        assert as_json(run("--project", str(p), "--plugin", str(plugin), "--json"))["files_differ"] == []


def test_no_design_system_yet_linked_or_odd_paths_compare_nothing(tmp_path: Path, plugin: Path) -> None:
    plugin_files(plugin)
    fresh = project(tmp_path, "1.2.0", "fresh")  # PLUMB.md names a skill that isn't there yet
    assert as_json(run("--project", str(fresh), "--plugin", str(plugin), "--json"))["files_differ"] == []
    linked = tmp_path / "linked"
    write(linked / "PLUMB.md", plumb_md("1.2.0") + "Role: linked\n")
    write(linked / SKILL / "scripts/audit.py", "other\n")
    assert as_json(run("--project", str(linked), "--plugin", str(plugin), "--json"))["files_differ"] == []
    outside = tmp_path / "elsewhere"  # a real skill outside the project, with a file that differs
    write(outside / "scripts/audit.py", "other\n")
    lines = ("Design system: `../elsewhere/`", f"Design system: `{outside.as_posix()}/`", "Design system: ``")
    for i, line in enumerate(lines):
        odd = tmp_path / f"odd{i}"
        write(odd / "PLUMB.md", plumb_md("1.2.0").replace(f"Design system: `{SKILL}/`", line))
        assert as_json(run("--project", str(odd), "--plugin", str(plugin), "--json"))["files_differ"] == []
    nodesign = tmp_path / "nodesign"
    write(nodesign / "PLUMB.md", "<!-- plumb v1.2.0 · written by /plumb:init, safe to edit values -->\n# Plumb\n")
    assert as_json(run("--project", str(nodesign), "--plugin", str(plugin), "--json"))["files_differ"] == []


def _scaffold(root: Path, *extra: str):
    cmd = [sys.executable, str(PLUGIN / "scripts/scaffold.py"), "--project-root", str(root), "--name", "Demo",
           "--skill-dir", SKILL, "--platforms", "web", "--styling", "tailwind-v4", *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def test_what_scaffold_copies_is_what_version_compares(tmp_path: Path) -> None:
    """A real scaffold, then its dry run again: every file still `would write:` is one of Plumb's (the project's own are
    `skip: … (yours, kept)`). version.py compares exactly those: none differ after the scaffold, each one changed is
    listed, and nothing else is."""
    version = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    p = tmp_path / "real"
    p.mkdir()
    dry = _scaffold(p, "--dry-run")
    token = re.search(r"--confirm ([0-9a-f]{12})", dry.stdout).group(1)
    assert _scaffold(p, "--confirm", token).returncode == 0
    again = _scaffold(p, "--dry-run").stdout
    plumbs = sorted(line[len("would write: "):] for line in again.splitlines() if line.startswith("would write: "))
    assert plumbs and all(f"{SKILL}/scripts/" in x or f"{SKILL}/templates/" in x or x.endswith("platforms/README.md")
                          for x in plumbs)
    write(p / "PLUMB.md", plumb_md(version))
    assert as_json(run("--project", str(p), "--plugin", str(PLUGIN), "--json"))["files_differ"] == []
    for x in plumbs:
        (p / x).write_bytes((p / x).read_bytes() + b"\n// another build\n")
    (p / SKILL / "SKILL.md").write_text("the project's own\n", encoding="utf-8")
    assert sorted(as_json(run("--project", str(p), "--plugin", str(PLUGIN), "--json"))["files_differ"]) == plumbs


def test_plumb_md_is_read_the_way_the_hooks_read_it(tmp_path: Path, plugin: Path) -> None:
    plugin_files(plugin)
    head = "<!-- plumb v1.2.0 · written by /plumb:init, safe to edit values -->\n# Plumb\n\n"
    cases = {
        "note": (f"Design system: `{SKILL}/`   (home)\n", True),
        "plain": (f"Design system: {SKILL}\n", True),
        "indented": (f"  Design system: `{SKILL}/`\n", True),
        "last-wins": (f"Design system: `elsewhere/`\nDesign system: `{SKILL}/`\n", True),
        "fenced": (f"```\nDesign system: `{SKILL}/`\n```\n", False),
        "bullet": (f"- Design system: `{SKILL}/`\n", False),
        "linked-capital": (f"Design system: `{SKILL}/`\nRole: Linked\n", False),
    }
    for name, (body, listed) in cases.items():
        p = tmp_path / name
        write(p / "PLUMB.md", head + body, "\r\n" if name == "plain" else "\n")
        copy_into(plugin, p)
        write(p / SKILL / "scripts/audit.py", "audit = 0\n")  # another build
        out = as_json(run("--project", str(p / "PLUMB.md"), "--plugin", str(plugin), "--json"))["files_differ"]
        assert out == ([f"{SKILL}/scripts/audit.py"] if listed else []), name
