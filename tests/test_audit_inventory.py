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
    assert colours["values"][0] == {"value": "#14857f", "count": 3, "where": ["app/a.css:1", "app/a.css:2", "app/b.css:1"],
                                  "sources": {"literal": 3}}
    assert [v["value"] for v in colours["values"]] == ["#14857f", "#13867f", "#ffffff"]
    assert colours["clusters"][0] == {"canonical": "#14857f", "members": ["#14857f", "#13867f"], "count": 4,
                                 "source": "literal"}
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
    assert "color: #14857f x4 [literal] (#14857f x3, #13867f x1)" in r.stdout
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


def radius_counts(tmp: Path) -> dict:
    r = run(["--inventory", "--json", "--project", str(tmp)], tmp)
    assert r.returncode == 0, r.stderr
    return {v["value"]: v["count"] for v in json.loads(r.stdout)["kinds"]["radius"]["values"]}


def tw_project(root: Path, css: str, base_name: str = "app") -> None:
    write(root / "package.json", '{"dependencies": {"tailwindcss": "^4.0.0"}}\n')
    write(root / f"{base_name}/globals.css", '@import "tailwindcss";\n' + css)
    write(root / f"{base_name}/page.tsx", '<div className="rounded-sm rounded-md rounded-lg rounded-xl rounded-t-lg" />\n')


STOCK = (":root { --radius: %s; }\n@theme inline {\n  --radius-sm: calc(var(--radius) - 4px);\n"
         "  --radius-md: calc(var(--radius) - 2px);\n  --radius-lg: var(--radius);\n"
         "  --radius-xl: calc(var(--radius) + 4px);\n}\n")


def test_inventory_radius_resolves_against_the_projects_theme_variables(tmp_path: Path) -> None:
    tw_project(tmp_path, STOCK % "0.625rem")
    assert radius_counts(tmp_path) == {"6px": 1, "8px": 1, "10px": 2, "14px": 1}


def test_inventory_radius_follows_another_base_radius_and_folder(tmp_path: Path) -> None:
    tw_project(tmp_path, STOCK % "8px", base_name="src/styles")
    assert radius_counts(tmp_path) == {"4px": 1, "6px": 1, "8px": 2, "12px": 1}


def test_inventory_radius_reads_plain_lengths_in_a_plain_theme_block(tmp_path: Path) -> None:
    tw_project(tmp_path, "@theme {\n  --radius-lg: 1rem;\n  --radius-xl: 20px; /* wide */\n}\n")
    # sm and md are not defined by the project: Tailwind's defaults (4px, 6px)
    assert radius_counts(tmp_path) == {"4px": 1, "6px": 1, "16px": 2, "20px": 1}


def test_inventory_radius_unresolvable_steps_fall_back_to_the_default(tmp_path: Path) -> None:
    # --radius is never defined, so the calc steps cannot resolve
    tw_project(tmp_path, "@theme inline { --radius-lg: calc(var(--radius) + 2px); }\n")
    assert radius_counts(tmp_path) == {"4px": 1, "6px": 1, "8px": 2, "12px": 1}


def test_inventory_radius_without_a_theme_keeps_tailwinds_defaults(tmp_path: Path) -> None:
    tw_project(tmp_path, ":root { --radius: 0.625rem; }\n")  # a base alone is not a theme radius
    assert radius_counts(tmp_path) == {"4px": 1, "6px": 1, "8px": 2, "12px": 1}
    other = tmp_path / "second"
    tw_project(other, ".x { color: #111111; }\n")
    assert radius_counts(other) == {"4px": 1, "6px": 1, "8px": 2, "12px": 1}


def colour_project(root: Path) -> None:
    write(root / "package.json", '{"dependencies": {"tailwindcss": "^4.0.0"}}\n')
    write(root / "app/globals.css", '@import "tailwindcss";\n:root { --chart-3: #10b981; --chart-4: #11b77f; }\n')
    write(root / "app/page.tsx", '<i className="bg-emerald-500 text-emerald-500" style={{ color: "#10b982" }} />\n')


def test_inventory_colour_clusters_stay_within_one_source_kind(tmp_path: Path) -> None:
    colour_project(tmp_path)
    r = run(["--inventory", "--json", "--project", str(tmp_path)], tmp_path)
    assert r.returncode == 0, r.stderr
    colours = json.loads(r.stdout)["kinds"]["color"]
    groups = {(g["source"], g["canonical"]): g["members"] for g in colours["clusters"]}
    # the two chart variables merge with each other; the palette class and the literal stay in their own groups
    assert groups[("variable", "#10b981")] == ["#10b981", "#11b77f"]
    assert groups[("palette", "#10b981")] == ["#10b981"]
    assert groups[("literal", "#10b982")] == ["#10b982"]
    assert len(colours["clusters"]) == 3
    emerald = next(v for v in colours["values"] if v["value"] == "#10b981")
    assert emerald["count"] == 3 and emerald["sources"] == {"variable": 1, "palette": 2}
    r = run(["--inventory", "--project", str(tmp_path)], tmp_path)
    assert "[variable]" in r.stdout and "[palette]" in r.stdout and "[literal]" in r.stdout
    assert "app/globals.css:2" in r.stdout


def test_inventory_colour_clusters_still_merge_inside_one_kind(tmp_path: Path) -> None:
    write(tmp_path / "app/a.css", ":root { --a: #14857f; --b: #13867f; }\n.x { color: #14857f; }\n")
    r = run(["--inventory", "--json", "--project", str(tmp_path)], tmp_path)
    groups = [(g["source"], g["members"]) for g in json.loads(r.stdout)["kinds"]["color"]["clusters"]]
    assert ("variable", ["#13867f", "#14857f"]) in groups and ("literal", ["#14857f"]) in groups
