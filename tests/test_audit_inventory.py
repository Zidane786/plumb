"""audit.py --inventory: every design value in use, with counts, file:line and proposed clusters (for /plumb:extract).

The extract skill runs the plugin's own copy (no design system exists yet), so the project root comes from --project, or
the PLUMB.md above the skill folder, or the current folder. Tokens are never read in this mode.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "plugins/plumb/assets/skill/scripts"
AUDIT = SCRIPTS / "audit.py"
KINDS = ["color", "font-family", "font-size", "font-weight", "line-height", "spacing", "radius", "shadow", "duration",
         "easing"]


def write(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def run(args: List[str], cwd: Path, script: Path = AUDIT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], cwd=str(cwd), capture_output=True, encoding="utf-8")


def app(root: Path, newline: str = "\n") -> None:
    write(root / "app/a.css",
          ".a { color: #14857f; padding: 8px; border-radius: 6px; }\n"
          ".b { color: #14857F; padding: 16px; }\n"
          ".c { color: #13867f; padding: 9px; transition: opacity 200ms ease-out; }\n", newline)
    write(root / "app/b.css", ".d { color: #14857f; background: #ffffff; font-size: 14px; }\n", newline)


def test_inventory_json_lists_values_counts_places_and_clusters(tmp_path: Path) -> None:
    app(tmp_path)
    r = run(["--inventory", "--json", "--project", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["version"] == "1.0.0" and out["mode"] == "inventory"
    assert out["root"] == tmp_path.resolve().as_posix() and out["files"] == 2
    assert list(out["kinds"]) == KINDS
    colours = out["kinds"]["color"]
    assert colours["values"][0] == {"value": "#14857f", "count": 3, "where": ["app/a.css:1", "app/a.css:2", "app/b.css:1"]}
    assert [v["value"] for v in colours["values"]] == ["#14857f", "#13867f", "#ffffff"]
    assert colours["clusters"][0] == {"canonical": "#14857f", "members": ["#14857f", "#13867f"], "count": 4}
    spacing = out["kinds"]["spacing"]["clusters"]
    assert {"canonical": "8px", "members": ["8px", "9px"], "count": 2} in spacing
    assert out["kinds"]["duration"]["values"] == [{"value": "200ms", "count": 1, "where": ["app/a.css:3"]}]
    assert out["kinds"]["font-family"] == {"values": [], "clusters": []}


def test_inventory_is_deterministic(tmp_path: Path) -> None:
    app(tmp_path)
    first = run(["--inventory", "--json", "--project", str(tmp_path)], tmp_path)
    second = run(["--inventory", "--json", "--project", str(tmp_path)], tmp_path)
    assert first.returncode == 0 and first.stdout == second.stdout


def test_inventory_terminal_summary_names_clusters_and_places(tmp_path: Path) -> None:
    app(tmp_path)
    r = run(["--inventory", "--project", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "inventory: 2 files" in r.stdout
    assert "color: #14857f x4 (#14857f x3, #13867f x1)" in r.stdout
    assert "app/a.css:1" in r.stdout


def test_inventory_defaults_to_the_current_folder_and_takes_paths(tmp_path: Path) -> None:
    app(tmp_path)
    write(tmp_path / "other/c.css", ".e { color: #222222; }\n")
    r = run(["--inventory", "--json"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["files"] == 3
    r = run(["app", "--inventory", "--json"], tmp_path)
    out = json.loads(r.stdout)
    assert out["files"] == 2 and "#222222" not in [v["value"] for v in out["kinds"]["color"]["values"]]


def test_inventory_skips_the_skill_docs_build_output_and_excludes(tmp_path: Path) -> None:
    app(tmp_path)
    write(tmp_path / "docs/design/prototype/screens/home.html", '<p style="color: #111111">x</p>\n')
    write(tmp_path / ".claude/skills/demo-design-system/assets/platforms/web/x.css", ".x { color: #222222; }\n")
    write(tmp_path / "node_modules/pkg/a.css", ".x { color: #333333; }\n")
    write(tmp_path / "legacy/old.css", ".x { color: #444444; }\n")
    r = run(["--inventory", "--json", "--project", str(tmp_path), "--exclude", "legacy/**"], tmp_path)
    assert r.returncode == 0, r.stderr
    values = [v["value"] for v in json.loads(r.stdout)["kinds"]["color"]["values"]]
    assert values == ["#14857f", "#13867f", "#ffffff"]
    r = run(["--inventory", "--json", "--project", str(tmp_path), "--exclude", "legacy\\**"], tmp_path)
    assert "#444444" not in r.stdout


def test_inventory_from_a_project_copy_uses_plumb_md_and_ignores_broken_tokens(tmp_path: Path) -> None:
    app(tmp_path)
    write(tmp_path / "PLUMB.md", "Design system: `.claude/skills/demo-design-system/`\n")
    skill = tmp_path / ".claude/skills/demo-design-system"
    shutil.copytree(SCRIPTS, skill / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    write(skill / "assets/tokens/demo.tokens.json", "{ broken")
    r = run(["--inventory", "--json"], tmp_path / "app", script=skill / "scripts/audit.py")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["root"] == tmp_path.resolve().as_posix() and out["files"] == 2


def test_inventory_reads_crlf_files_and_unicode_paths(tmp_path: Path) -> None:
    app(tmp_path / "Café Ünïcode", "\r\n")
    r = run(["--inventory", "--json", "--project", str(tmp_path / "Café Ünïcode")], tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["kinds"]["color"]["values"][0]["where"] == ["app/a.css:1", "app/a.css:2", "app/b.css:1"]


def test_inventory_refuses_when_no_ui_files(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "# hi\n")
    r = run(["--inventory", "--project", str(tmp_path)], tmp_path)
    assert r.returncode == 2
    assert r.stderr.startswith("error: no UI files") and "\nfix: " in r.stderr
    assert "Traceback" not in r.stderr


def test_inventory_refuses_missing_paths(tmp_path: Path) -> None:
    app(tmp_path)
    r = run(["nowhere", "--inventory", "--project", str(tmp_path)], tmp_path)
    assert r.returncode == 2
    assert "error:" in r.stderr and "fix:" in r.stderr


def test_inventory_refuses_a_missing_project(tmp_path: Path) -> None:
    r = run(["--inventory", "--project", str(tmp_path / "gone")], tmp_path)
    assert r.returncode == 2
    assert r.stderr.startswith("error: ") and "fix: " in r.stderr


def test_inventory_refuses_other_modes(tmp_path: Path) -> None:
    app(tmp_path)
    for extra in (["--quick", "app/a.css"], ["--html"], ["--no-tokens"]):
        r = run(["--inventory", "--project", str(tmp_path), *extra], tmp_path)
        assert r.returncode == 2, extra
        assert r.stderr.startswith("error: ") and "--inventory" in r.stderr and "fix: " in r.stderr
    r = run(["--exclude", "legacy/**", "--project", str(tmp_path)], tmp_path)
    assert r.returncode == 2 and "--exclude" in r.stderr
