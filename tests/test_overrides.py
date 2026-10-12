"""build-tokens.py --overrides: the project's own variables in the tokens' namespaces (a stock create-next-app or
shadcn globals.css), listed with the token each maps onto, and moved into the tokens with --apply after the user's OK."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "plugins/plumb/assets/skill/scripts"
FIXTURE = REPO / "tests/fixtures/projects/web-v4"
STOCK = REPO / "tests/fixtures/apps/next-tailwind-stock/app/globals.css"
SKILL_REL = ".claude/skills/demo-design-system"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    shutil.copytree(FIXTURE, dest)
    for name in ("_plumb.py", "build-tokens.py", "audit.py"):
        shutil.copy(SCRIPTS / name, dest / SKILL_REL / "scripts" / name)
    (dest / "app").mkdir(exist_ok=True)
    shutil.copy(STOCK, dest / "app/globals.css")
    return dest


def run(p: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(p / SKILL_REL / "scripts" / script), *args], cwd=str(p),
                          capture_output=True, text=True, encoding="utf-8")


def tokens_file(p: Path) -> Path:
    return p / SKILL_REL / "assets/tokens/demo.tokens.json"


def plan(p: Path) -> dict:
    r = run(p, "build-tokens.py", "--overrides")
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def by_name(data: dict) -> dict:
    (copy,) = data["copies"]
    return {o["name"]: o for o in copy["overrides"]}


def test_overrides_lists_each_variable_with_the_token_it_maps_onto(project: Path) -> None:
    before = (project / "app/globals.css").read_bytes(), tokens_file(project).read_bytes()
    data = plan(project)
    (copy,) = data["copies"]
    assert copy["file"] == "app/globals.css"
    found = by_name(data)
    assert list(found) == ["--color-background", "--color-foreground", "--font-sans", "--font-mono"]
    bg = found["--color-background"]
    assert (bg["line"], bg["kind"], bg["token"], bg["value"]) == (9, "token", "color.background", "var(--background)")
    assert bg["project_values"] == {"light": "#ffffff", "dark": "#0a0a0a"}
    fg = found["--color-foreground"]
    assert (fg["kind"], fg["token"]) == ("new-name", "color.foreground")
    assert fg["token_change"] == {"add": "color.foreground", "$value": "{color.on-surface}"}
    sans = found["--font-sans"]
    assert (sans["kind"], sans["token"], sans["token_change"]) == ("token", "font.sans", None)
    assert any("var(--font-geist-sans)" in n and "Inter" in n for n in copy["by_hand"])  # the tokens' font differs
    mono = found["--font-mono"]
    assert mono["kind"] == "new-name" and mono["token_change"]["add"] == "font.mono"
    assert mono["token_change"]["$value"][0] == "var(--font-geist-mono)" and "monospace" in mono["token_change"]["$value"]
    assert [(r["line"], r["old"], r["new"]) for r in copy["replace"]] == [
        (23, "var(--background)", "var(--color-background)"), (24, "var(--foreground)", "var(--color-foreground)"),
        (25, "Arial, Helvetica, sans-serif", "var(--font-sans)")]
    assert all(r["why"] for r in copy["replace"])
    # the :root and dark variables that only fed the overrides, the @theme block, and the blocks left empty
    assert copy["remove_lines"] == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
    assert ((project / "app/globals.css").read_bytes(), tokens_file(project).read_bytes()) == before  # read only


def test_apply_moves_them_into_the_tokens_and_the_audit_passes(project: Path) -> None:
    assert run(project, "build-tokens.py").returncode == 0
    r = run(project, "audit.py", "--json", "app/globals.css")
    assert {f["rule"] for f in json.loads(r.stdout)["findings"]} >= {"block-override", "raw-colour"}
    r = run(project, "build-tokens.py", "--overrides", "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "wrote app/globals.css" in r.stdout and "added color.foreground" in r.stdout
    css = (project / "app/globals.css").read_text(encoding="utf-8")
    assert "--background:" not in css and "@theme inline" not in css and "prefers-color-scheme" not in css.split(
        "/* plumb:end */")[1]
    assert css.split("/* plumb:end */")[1].strip() == (
        "body {\n  background: var(--color-background);\n  color: var(--color-foreground);\n"
        "  font-family: var(--font-sans);\n}")
    doc = json.loads(tokens_file(project).read_text(encoding="utf-8"))
    assert doc["color"]["foreground"] == {"$value": "{color.on-surface}"}
    assert doc["font"]["mono"]["$value"][0] == "var(--font-geist-mono)"
    assert run(project, "build-tokens.py").returncode == 0
    r = run(project, "audit.py", "--json", "app/globals.css")
    assert [f for f in json.loads(r.stdout)["findings"] if f["file"] == "app/globals.css"] == []
    assert plan(project)["copies"][0]["overrides"] == []


def test_a_font_variable_the_tokens_name_goes_first_in_the_token(project: Path) -> None:
    doc = json.loads(tokens_file(project).read_text(encoding="utf-8"))
    doc["font"]["sans"]["$value"] = ["Geist", "system-ui", "sans-serif"]
    tokens_file(project).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    sans = by_name(plan(project))["--font-sans"]
    assert sans["token_change"] == {"prepend": "font.sans", "family": "var(--font-geist-sans)"}
    assert run(project, "build-tokens.py", "--overrides", "--apply").returncode == 0
    doc = json.loads(tokens_file(project).read_text(encoding="utf-8"))
    assert doc["font"]["sans"]["$value"] == ["var(--font-geist-sans)", "Geist", "system-ui", "sans-serif"]


def test_a_declaration_sharing_its_line_is_left_for_the_user(project: Path) -> None:
    (project / "app/globals.css").write_text(
        '@import "tailwindcss";\n@theme inline { --color-brand: var(--brand); --radius-sm: 2px; }\n', encoding="utf-8")
    data = plan(project)
    (copy,) = data["copies"]
    assert copy["remove_lines"] == [] and len(copy["by_hand"]) >= 1
    assert any("line 2" in n for n in copy["by_hand"])
    r = run(project, "build-tokens.py", "--overrides", "--apply")
    assert r.returncode == 0 and "by hand" in r.stdout
    assert "--color-brand" in (project / "app/globals.css").read_text(encoding="utf-8")


SHADCN = '''@import "tailwindcss";

@custom-variant dark (&:is(.dark *));

@theme inline {
  --color-card: var(--card);
  --color-sidebar-ring: var(--sidebar-ring);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-lg: var(--radius);
}

:root {
  --radius: 0.625rem;
  --card: oklch(1 0 0);
  --sidebar-ring: oklch(0.708 0 0);
}
'''


def test_a_shadcn_stylesheet_moves_what_it_can_and_leaves_nothing_dangling(project: Path) -> None:
    (project / "app/globals.css").write_text(SHADCN, encoding="utf-8")
    found = by_name(plan(project))
    assert found["@custom-variant dark"]["kind"] == "dark-variant"
    assert found["--color-card"]["token_change"] == {"add": "color.card", "$value": "{color.background}"}
    assert found["--color-sidebar-ring"]["token_change"] is None  # no role, no colour Plumb can read: the user decides
    assert found["--radius-lg"]["kind"] == "token"
    assert run(project, "build-tokens.py", "--overrides", "--apply").returncode == 0
    css = (project / "app/globals.css").read_text(encoding="utf-8")
    assert "@custom-variant" not in css and "--color-card" not in css and "--radius: 0.625rem" not in css
    # --radius fed --radius-lg (moved); --radius-sm stays for the user, so its use points at the token too
    assert "--radius-sm: calc(var(--radius-lg) - 4px);" in css and "var(--radius)" not in css
    assert "--color-sidebar-ring: var(--sidebar-ring);" in css and "--sidebar-ring: oklch(0.708 0 0);" in css


def test_a_crlf_stylesheet_keeps_its_line_endings(project: Path) -> None:
    css = project / "app/globals.css"
    css.write_bytes(css.read_bytes().replace(b"\n", b"\r\n"))
    assert plan(project)["copies"][0]["remove_lines"] == list(range(3, 22))
    assert run(project, "build-tokens.py", "--overrides", "--apply").returncode == 0
    raw = css.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b"") and b"--background:" not in raw
    assert raw.startswith(b'@import "tailwindcss";\r\n\r\nbody {\r\n  background: var(--color-background);\r\n')


def test_an_override_directly_above_plumbs_block_never_touches_the_block(project: Path) -> None:
    css = project / "app/globals.css"
    css.write_text('@import "tailwindcss";\n\n@theme inline {\n  --color-background: var(--bg);\n}\n',
                   encoding="utf-8")
    assert run(project, "build-tokens.py").returncode == 0
    text = css.read_text(encoding="utf-8")
    # move the project's lines above the block: the @theme block now sits directly over the start marker
    start = text.index("/* plumb:start")
    block = text[start:text.index("/* plumb:end */") + len("/* plumb:end */")]
    css.write_text('@import "tailwindcss";\n\n@theme inline {\n  --color-background: var(--bg);\n}\n' + block + "\n",
                   encoding="utf-8")
    data = plan(project)
    lines = css.read_text(encoding="utf-8").split("\n")
    assert all(not lines[n - 1].startswith("/* plumb:") for n in data["copies"][0]["remove_lines"])
    r = run(project, "build-tokens.py", "--overrides", "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    after = css.read_text(encoding="utf-8")
    assert block in after and "--color-background: var(--bg)" not in after
    assert run(project, "build-tokens.py", "--check").returncode == 0


def test_nothing_to_move(project: Path) -> None:
    (project / "app/globals.css").write_text('@import "tailwindcss";\n\nbody {\n  margin: 0;\n}\n', encoding="utf-8")
    assert plan(project)["copies"][0]["overrides"] == []
    r = run(project, "build-tokens.py", "--overrides", "--apply")
    assert r.returncode == 0 and "nothing to move" in r.stdout


def test_apply_needs_overrides(project: Path) -> None:
    r = run(project, "build-tokens.py", "--apply")
    assert r.returncode == 2
    assert r.stderr.startswith("error:") and "\nfix:" in r.stderr and "--overrides --apply" in r.stderr
