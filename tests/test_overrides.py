"""build-tokens.py --overrides: the project's own variables in the tokens' namespaces (a stock create-next-app or
shadcn globals.css), listed with the token each maps onto, and moved into the tokens with --apply after the user's OK."""

from __future__ import annotations

import json
import re
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
  --color-glow: var(--glow);
  --radius-2xl: calc(var(--radius) * 1.5);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-lg: var(--radius);
}

:root {
  --radius: 0.625rem;
  --card: oklch(1 0 0);
  --glow: color-mix(in srgb, red 40%, transparent);
}
'''


def test_a_shadcn_stylesheet_moves_what_it_can_and_leaves_nothing_dangling(project: Path) -> None:
    (project / "app/globals.css").write_text(SHADCN, encoding="utf-8")
    found = by_name(plan(project))
    assert found["@custom-variant dark"]["kind"] == "dark-variant"
    assert found["--color-card"]["token_change"] == {"add": "color.card", "$value": "{color.background}"}
    assert found["--color-glow"]["token_change"] is None  # no role, no colour Plumb can read: the user decides
    assert found["--radius-sm"]["token_change"] == {"add": "radius.sm", "$value": "6px"}
    assert found["--radius-lg"]["kind"] == "token"
    assert run(project, "build-tokens.py", "--overrides", "--apply").returncode == 0
    css = (project / "app/globals.css").read_text(encoding="utf-8")
    assert "@custom-variant" not in css and "--color-card" not in css and "--radius: 0.625rem" not in css
    assert "--radius-sm" not in css and "--radius:" not in css  # radius.sm = 6px; --radius fed radius.lg
    # --radius-2xl (a multiple: Plumb cannot tell) stays for the user, and its use points at the token too
    assert "--radius-2xl: calc(var(--radius-lg) * 1.5);" in css
    assert "--color-glow: var(--glow);" in css and "--glow: color-mix(" in css


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


SHADCN_STOCK = REPO / "tests/fixtures/apps/next-tailwind-shadcn/app/globals.css"
ROLES = {"surface": "#fafafa", "sunk": "#f0f0f0", "outline": "#dddddd", "outline-input": "#888888",
         "on-surface-muted": "#555555", "danger": "#c00000", "on-danger": "#ffffff"}


def _scaffold_roles(p: Path) -> None:
    doc = json.loads(tokens_file(p).read_text(encoding="utf-8"))
    for name, value in ROLES.items():
        doc["color"][name] = {"$value": value, "$extensions": {"plumb": {"dark": value}}}
    doc["font"]["sans"]["$value"] = ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"]
    tokens_file(p).write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_a_stock_shadcn_stylesheet_maps_every_variable_onto_a_token(project: Path) -> None:
    shutil.copy(SHADCN_STOCK, project / "app/globals.css")
    _scaffold_roles(project)
    data = plan(project)
    (copy,) = data["copies"]
    assert copy["by_hand"] == []
    found = by_name(data)
    alias = {n: o["token_change"]["$value"] for n, o in found.items()
             if o["token_change"] and isinstance(o["token_change"].get("$value"), str)
             and o["token_change"]["$value"].startswith("{")}
    assert alias == {
        "--color-foreground": "{color.on-surface}",
        "--color-sidebar-ring": "{color.primary}", "--color-sidebar-border": "{color.outline}",
        "--color-sidebar-accent-foreground": "{color.on-surface}", "--color-sidebar-accent": "{color.sunk}",
        "--color-sidebar-primary-foreground": "{color.on-primary}", "--color-sidebar-primary": "{color.primary}",
        "--color-sidebar-foreground": "{color.on-surface}", "--color-sidebar": "{color.surface}",
        "--color-ring": "{color.primary}", "--color-input": "{color.outline-input}", "--color-border": "{color.outline}",
        "--color-destructive": "{color.danger}", "--color-accent-foreground": "{color.on-surface}",
        "--color-accent": "{color.sunk}", "--color-muted-foreground": "{color.on-surface-muted}",
        "--color-muted": "{color.sunk}", "--color-secondary-foreground": "{color.on-surface}",
        "--color-secondary": "{color.sunk}", "--color-primary-foreground": "{color.on-primary}",
        "--color-popover-foreground": "{color.on-surface}", "--color-popover": "{color.surface}",
        "--color-card-foreground": "{color.on-surface}", "--color-card": "{color.surface}"}
    (project / "app/globals.css").write_text(
        '@import "tailwindcss";\n@theme inline {\n  --color-destructive-foreground: var(--df);\n}\n', encoding="utf-8")
    assert by_name(plan(project))["--color-destructive-foreground"]["token_change"]["$value"] == "{color.on-danger}"
    shutil.copy(SHADCN_STOCK, project / "app/globals.css")
    # the chart colours are the app's own: moved as values (oklch read as sRGB), light and dark
    chart = found["--color-chart-1"]["token_change"]
    assert chart == {"add": "color.chart-1", "$value": "#f54900", "$extensions": {"plumb": {"dark": "#1447e6"}}}
    # radius steps from calc(var(--radius) ± Npx) with --radius: 0.625rem (10px)
    assert found["--radius-xl"]["token_change"] == {"add": "radius.xl", "$value": "14px"}
    assert found["--radius-sm"]["token_change"] == {"add": "radius.sm", "$value": "6px"}
    assert found["--radius-md"]["kind"] == found["--radius-lg"]["kind"] == "token"
    # a system font stack in the tokens: the app's own font goes first
    assert found["--font-sans"]["token_change"] == {"prepend": "font.sans", "family": "var(--font-geist-sans)"}
    r = run(project, "build-tokens.py", "--overrides", "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert run(project, "build-tokens.py").returncode == 0
    r = run(project, "audit.py", "--json", "app/globals.css")
    assert [f for f in json.loads(r.stdout)["findings"] if f["file"] == "app/globals.css"] == []
    doc = json.loads(tokens_file(project).read_text(encoding="utf-8"))
    assert doc["color"]["border"] == {"$value": "{color.outline}"}


def test_a_translucent_value_keeps_its_alpha(project: Path) -> None:
    (project / "app/globals.css").write_text(
        '@import "tailwindcss";\n\n@theme inline {\n  --color-glass: var(--glass);\n}\n\n:root {\n'
        '  --glass: oklch(1 0 0 / 10%);\n}\n\n.dark {\n  --glass: #00000080;\n}\n', encoding="utf-8")
    change = by_name(plan(project))["--color-glass"]["token_change"]
    assert change == {"add": "color.glass", "$value": "#ffffff1a", "$extensions": {"plumb": {"dark": "#00000080"}}}


def test_a_colour_the_app_sets_only_in_root_stays_the_same_in_dark(project: Path) -> None:
    (project / "app/globals.css").write_text(
        '@import "tailwindcss";\n\n@theme inline {\n  --color-brand: var(--brand);\n}\n\n:root {\n'
        '  --brand: #7a1fa2;\n}\n', encoding="utf-8")
    (copy,) = plan(project)["copies"]
    change = by_name({"copies": [copy]})["--color-brand"]["token_change"]
    assert change == {"add": "color.brand", "$value": "#7a1fa2", "$extensions": {"plumb": {"same-in-dark": True}}}
    assert any("--color-brand has no dark value in the app; kept the same in dark" in n and "/plumb:update" in n
               for n in copy["notes"])
    out = run(project, "build-tokens.py", "--overrides", "--apply").stdout
    assert "note: app/globals.css line 4: --color-brand has no dark value in the app" in out
    assert run(project, "build-tokens.py").returncode == 0
    r = run(project, "audit.py", "--json")
    assert not [f for f in json.loads(r.stdout)["findings"]
                if f["rule"] == "missing-dark-value" and "color.brand" in f["message"]]


def test_the_plan_lists_other_files_that_use_a_removed_variable(project: Path) -> None:
    (project / "components").mkdir()
    (project / "components/chart.tsx").write_text(
        'export const C = () => <div style={{ width: 4 }} data-c="var(--background)" />;\n', encoding="utf-8")
    (project / "app/extra.css").write_text(".x {\n  color: var(--foreground, red);\n}\n", encoding="utf-8")
    (copy,) = plan(project)["copies"]
    used = {v["name"]: v["used_in"] for v in copy["project_variables"]}
    assert used == {"--background": ["components/chart.tsx:1"], "--foreground": ["app/extra.css:2"]}
    out = run(project, "build-tokens.py", "--overrides", "--apply").stdout
    assert "note: var(--background) is gone from app/globals.css but still read at components/chart.tsx:1" in out and "var(--color-background)" in out


def test_nothing_to_move(project: Path) -> None:
    (project / "app/globals.css").write_text('@import "tailwindcss";\n\nbody {\n  margin: 0;\n}\n', encoding="utf-8")
    assert plan(project)["copies"][0]["overrides"] == []
    r = run(project, "build-tokens.py", "--overrides", "--apply")
    assert r.returncode == 0 and "nothing to move" in r.stdout


def test_apply_needs_overrides(project: Path) -> None:
    r = run(project, "build-tokens.py", "--apply")
    assert r.returncode == 2
    assert r.stderr.startswith("error:") and "\nfix:" in r.stderr and "--overrides --apply" in r.stderr


# ---------------------------------------------------------------- live test 2 (B7): roles checked against the app's colours


def _core():
    import importlib.util
    spec = importlib.util.spec_from_file_location("plumb_core_for_overrides", SCRIPTS / "_plumb.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The tokens extract records from a stock shadcn new-york globals.css: each token holds the app's own colours.
EXTRACTED = {"background": "background", "surface": "card", "sunk": "muted", "on-surface": "foreground",
             "on-surface-muted": "muted-foreground", "on-primary": "primary-foreground", "outline": "border",
             "outline-input": "input", "danger": "destructive"}


def _extracted_tokens(p: Path, extra: dict = None) -> None:
    P = _core()
    css = SHADCN_STOCK.read_text(encoding="utf-8")
    light, dark = css.split(":root {", 1)[1].split("}", 1)[0], css.split(".dark {", 1)[1].split("}", 1)[0]

    def val(block: str, var: str) -> str:
        line = next(ln for ln in block.splitlines() if ln.strip().startswith(f"--{var}:"))
        hexv, alpha = P.parse_color(line.split(":", 1)[1].strip().rstrip(";"))
        return hexv if alpha >= 1 else hexv + f"{round(alpha * 255):02x}"

    doc = json.loads(tokens_file(p).read_text(encoding="utf-8"))
    for token, var in {**EXTRACTED, **(extra or {}), "primary": "primary"}.items():
        doc["color"][token] = {"$value": val(light, var), "$extensions": {"plumb": {"dark": val(dark, var)}}}
    tokens_file(p).write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_a_stock_shadcn_new_york_stylesheet_maps_by_role_and_colour(project: Path) -> None:
    """popover goes to the surface (or a raised surface token), never sunk; sidebar-accent and
    sidebar-accent-foreground follow accent and accent-foreground; a role whose token has other colours than the app
    is still mapped by role but named in the notes (the look would change), so the skill asks."""
    shutil.copy(SHADCN_STOCK, project / "app/globals.css")
    _extracted_tokens(project)
    (copy,) = plan(project)["copies"]
    found = {o["name"][len("--color-"):]: o["token_change"]["$value"] for o in copy["overrides"]
             if o["name"].startswith("--color-") and o["token_change"]
             and str(o["token_change"].get("$value", "")).startswith("{")}
    assert found == {
        "foreground": "{color.on-surface}", "card": "{color.surface}", "card-foreground": "{color.on-surface}",
        "popover": "{color.surface}", "popover-foreground": "{color.on-surface}",
        "primary-foreground": "{color.on-primary}",
        "secondary": "{color.sunk}", "secondary-foreground": "{color.on-surface}",
        "muted": "{color.sunk}", "muted-foreground": "{color.on-surface-muted}",
        "accent": "{color.sunk}", "accent-foreground": "{color.on-surface}",
        "destructive": "{color.danger}", "border": "{color.outline}", "input": "{color.outline-input}",
        "ring": "{color.primary}",
        "sidebar": "{color.surface}", "sidebar-foreground": "{color.on-surface}",
        "sidebar-primary": "{color.primary}", "sidebar-primary-foreground": "{color.on-primary}",
        "sidebar-accent": "{color.sunk}", "sidebar-accent-foreground": "{color.on-surface}",
        "sidebar-border": "{color.outline}", "sidebar-ring": "{color.primary}"}
    looks = sorted(n.split(": --color-", 1)[1].split(" ", 1)[0] for n in copy["notes"] if "the look changes" in n)
    assert looks == ["accent-foreground", "ring", "secondary-foreground", "sidebar", "sidebar-accent-foreground",
                     "sidebar-primary", "sidebar-primary-foreground", "sidebar-ring"]
    # a raised surface token with the popover's colours, and an on-sunk with accent-foreground's: they are used
    _extracted_tokens(project, {"surface-raised": "popover", "on-sunk": "accent-foreground"})
    (copy,) = plan(project)["copies"]
    got = {o["name"]: o["token_change"]["$value"] for o in copy["overrides"] if o["token_change"]}
    assert got["--color-popover"] == "{color.surface-raised}"
    assert got["--color-accent-foreground"] == got["--color-sidebar-accent-foreground"] == "{color.on-sunk}"
    assert got["--color-secondary-foreground"] == "{color.on-sunk}"


def test_a_value_match_never_crosses_roles(project: Path) -> None:
    """Review M3: a background colour is never aliased to a border token just because their colours match (the live
    app's sidebar-accent shared #d8e2ff / #ffffff0f with the outline token)."""
    css = SHADCN_STOCK.read_text(encoding="utf-8")
    css = re.sub(r"(--sidebar-accent:)[^;]*;", r"\1 #d8e2ff;", css, count=1)  # :root
    head, _, tail = css.partition(".dark {")
    tail = re.sub(r"(--sidebar-accent:)[^;]*;", r"\1 #ffffff0f;", tail, count=1)
    (project / "app/globals.css").write_text(head + ".dark {" + tail, encoding="utf-8")
    _extracted_tokens(project)
    doc = json.loads(tokens_file(project).read_text(encoding="utf-8"))
    doc["color"]["outline"] = {"$value": "#d8e2ff", "$extensions": {"plumb": {"dark": "#ffffff0f"}}}
    tokens_file(project).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (copy,) = plan(project)["copies"]
    got = {o["name"]: o["token_change"] for o in copy["overrides"] if o["token_change"]}
    value = got["--color-sidebar-accent"]["$value"]
    assert value != "{color.outline}", got["--color-sidebar-accent"]
    assert value == "{color.sunk}"  # its role, named as a look change for the user to decide
    assert any("--color-sidebar-accent becomes" in n and "the look changes" in n for n in copy["notes"])
    # the same colours on a token of its own family are still found
    doc["color"]["surface-accent"] = {"$value": "#d8e2ff", "$extensions": {"plumb": {"dark": "#ffffff0f"}}}
    tokens_file(project).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (copy,) = plan(project)["copies"]
    got = {o["name"]: o["token_change"] for o in copy["overrides"] if o["token_change"]}
    assert got["--color-sidebar-accent"]["$value"] == "{color.surface-accent}"


def test_used_in_never_lists_plumbs_own_pages(project: Path) -> None:
    (project / "components").mkdir()
    (project / "components/chart.tsx").write_text('export const C = () => <i data-c="var(--background)" />;\n',
                                                 encoding="utf-8")
    (project / "docs/design/prototype/screens").mkdir(parents=True)
    (project / "docs/design/extract.html").write_text("<style>:root { color: var(--background); }</style>\n",
                                                      encoding="utf-8")
    (project / "docs/design/prototype/screens/home.html").write_text('<p style="color: var(--foreground)"></p>\n',
                                                                     encoding="utf-8")
    (copy,) = plan(project)["copies"]
    used = {v["name"]: v["used_in"] for v in copy["project_variables"]}
    assert used == {"--background": ["components/chart.tsx:1"], "--foreground": []}


# ---------------------------------------------------------------- sidebar roles (a sidebar-specific token wins)


def test_a_sidebar_token_wins_over_the_generic_role(project: Path) -> None:
    """sidebar-accent / sidebar-accent-foreground map onto color.sidebar-active / color.on-sidebar-active (accent and
    active are synonyms) before the generic sunk / on-surface; sidebar-primary uses its own token when there is one."""
    shutil.copy(SHADCN_STOCK, project / "app/globals.css")
    _extracted_tokens(project, {"sidebar-active": "sidebar-accent", "on-sidebar-active": "sidebar-accent-foreground",
                                "sidebar-primary": "sidebar-primary", "on-sidebar-primary": "sidebar-primary-foreground"})
    (copy,) = plan(project)["copies"]
    got = {o["name"]: o["token_change"]["$value"] for o in copy["overrides"]
           if o["token_change"] and str(o["token_change"].get("$value", "")).startswith("{")}
    assert got["--color-sidebar-accent"] == "{color.sidebar-active}"
    assert got["--color-sidebar-accent-foreground"] == "{color.on-sidebar-active}"
    assert got["--color-accent"] == "{color.sunk}"  # the non-sidebar names keep the generic role
    assert got["--color-sidebar-ring"] == "{color.primary}"  # no sidebar-ring token: the generic mapping
    # the same names written the other way round: the project says active, the tokens say accent
    (project / "app/globals.css").write_text(
        '@import "tailwindcss";\n@theme inline {\n  --color-sidebar-active: var(--sa);\n}\n', encoding="utf-8")
    doc = json.loads(tokens_file(project).read_text(encoding="utf-8"))
    del doc["color"]["sidebar-active"]
    doc["color"]["sidebar-accent"] = {"$value": "#eeeeee", "$extensions": {"plumb": {"dark": "#222222"}}}
    tokens_file(project).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    assert by_name(plan(project))["--color-sidebar-active"]["token_change"]["$value"] == "{color.sidebar-accent}"


def test_a_sidebar_token_whose_colours_differ_is_a_look_change_note(project: Path) -> None:
    shutil.copy(SHADCN_STOCK, project / "app/globals.css")
    _extracted_tokens(project)
    doc = json.loads(tokens_file(project).read_text(encoding="utf-8"))
    doc["color"]["sidebar-active"] = {"$value": "#123456", "$extensions": {"plumb": {"dark": "#654321"}}}
    tokens_file(project).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (copy,) = plan(project)["copies"]
    got = {o["name"]: o["token_change"]["$value"] for o in copy["overrides"] if o["token_change"]}
    assert got["--color-sidebar-accent"] == "{color.sidebar-active}"
    assert any("--color-sidebar-accent becomes {color.sidebar-active}" in n and "the look changes" in n
               for n in copy["notes"])


def test_no_sidebar_token_keeps_the_generic_mapping(project: Path) -> None:
    shutil.copy(SHADCN_STOCK, project / "app/globals.css")
    _extracted_tokens(project)
    (copy,) = plan(project)["copies"]
    got = {o["name"]: o["token_change"]["$value"] for o in copy["overrides"] if o["token_change"]}
    assert got["--color-sidebar-accent"] == "{color.sunk}"
    assert got["--color-sidebar-accent-foreground"] == "{color.on-surface}"


# ---------------------------------------------------------------- next/font variable applied on <body>

GEIST_GLOBALS = '@import "tailwindcss";\n\n@theme inline {\n  --font-sans: var(--font-geist-sans);\n}\n'
LAYOUT_BODY = '''import { Geist, Geist_Mono } from "next/font/google";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>{children}</body>
    </html>
  );
}
'''


def _font_project(p: Path, routes: str = "app (next-app)", layout: str = LAYOUT_BODY, folder: str = "app",
                  name: str = "layout.tsx") -> None:
    (p / "app/globals.css").write_text(GEIST_GLOBALS, encoding="utf-8")
    doc = json.loads(tokens_file(p).read_text(encoding="utf-8"))
    doc["font"]["sans"]["$value"] = ["Geist", "system-ui", "sans-serif"]
    tokens_file(p).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    if routes:
        md = p / "PLUMB.md"
        md.write_text(md.read_text(encoding="utf-8").rstrip("\n") + f"\nRoutes: {routes}\n", encoding="utf-8")
    (p / folder).mkdir(parents=True, exist_ok=True)
    (p / folder / name).write_text(layout, encoding="utf-8")


def test_a_font_variable_applied_on_body_is_a_by_hand_item(project: Path) -> None:
    _font_project(project)
    (copy,) = plan(project)["copies"]
    assert by_name({"copies": [copy]})["--font-sans"]["token_change"]["prepend"] == "font.sans"
    (item,) = [n for n in copy["by_hand"] if "layout" in n]
    assert "move `geistSans.variable` to the `<html>` className in app/layout.tsx:12" in item
    assert not any("geistMono" in n for n in copy["by_hand"])  # --font-geist-mono is not read by an override here


def test_the_font_variable_check_follows_the_recorded_route_root(project: Path) -> None:
    _font_project(project, routes="web/src/app (next-app)", folder="web/src/app", name="layout.jsx")
    (copy,) = plan(project)["copies"]
    assert any("move `geistSans.variable` to the `<html>` className in web/src/app/layout.jsx:" in n
               for n in copy["by_hand"])


@pytest.mark.parametrize("routes", ["", "none", "app (next-pages)", "elsewhere/app (next-app)", "(not recorded yet)"])
def test_no_next_app_route_means_no_font_check(project: Path, routes: str) -> None:
    _font_project(project, routes=routes)
    (copy,) = plan(project)["copies"]
    assert not any("layout" in n for n in copy["by_hand"])


def test_a_font_variable_already_on_html_is_quiet(project: Path) -> None:
    on_html = LAYOUT_BODY.replace('<html lang="en">', '<html lang="en" className={geistSans.variable}>')
    _font_project(project, layout=on_html)
    (copy,) = plan(project)["copies"]
    assert not any("layout" in n for n in copy["by_hand"])  # on both <html> and <body>: defined at :root
    only_html = on_html.replace("${geistSans.variable} ", "")
    (project / "app/layout.tsx").write_text(only_html, encoding="utf-8")
    (copy,) = plan(project)["copies"]
    assert not any("layout" in n for n in copy["by_hand"])


def test_a_nested_sidebar_token_is_found(project: Path) -> None:
    """color.sidebar.active has the variable name --color-sidebar-active; the alias points at its real path."""
    shutil.copy(SHADCN_STOCK, project / "app/globals.css")
    _extracted_tokens(project)
    doc = json.loads(tokens_file(project).read_text(encoding="utf-8"))
    doc["color"]["sidebar"] = {"active": {"$value": "#eeeeee", "$extensions": {"plumb": {"dark": "#222222"}}},
                               "on-active": {"$value": "#111111", "$extensions": {"plumb": {"dark": "#fefefe"}}}}
    tokens_file(project).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (copy,) = plan(project)["copies"]
    got = {o["name"]: o["token_change"]["$value"] for o in copy["overrides"] if o["token_change"]}
    assert got["--color-sidebar-accent"] == "{color.sidebar.active}"


LOCAL_FONT = '''import localFont from "next/font/local";

const brand = localFont({
  src: [{ path: "./a.woff2", weight: "400" }, { path: "./b.woff2", weight: "700" }],
  variable: "--font-geist-sans",
});

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={brand.variable}>{children}</body>
    </html>
  );
}
'''


def test_a_font_with_a_nested_src_array_is_found(project: Path) -> None:
    _font_project(project, layout=LOCAL_FONT)
    (copy,) = plan(project)["copies"]
    assert any("move `brand.variable` to the `<html>` className in app/layout.tsx:11" in n for n in copy["by_hand"])


def test_a_body_in_a_comment_does_not_hide_the_real_tag(project: Path) -> None:
    layout = "// the fonts go on <body> here, <html> there\n/* <body> */\n" + LAYOUT_BODY
    _font_project(project, layout=layout)
    (copy,) = plan(project)["copies"]
    assert any("move `geistSans.variable` to the `<html>` className in app/layout.tsx:" in n for n in copy["by_hand"])


FONTS_MODULE = 'import { Geist } from "next/font/google";\nexport const sans = Geist({ variable: "--font-geist-sans" });\n'
LAYOUT_IMPORT = '''import { sans as geistSans } from "./fonts";

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={geistSans.variable}>{children}</body>
    </html>
  );
}
'''


def test_a_font_defined_in_a_local_module_is_followed_one_hop(project: Path) -> None:
    _font_project(project, layout=LAYOUT_IMPORT)
    (project / "app/fonts.ts").write_text(FONTS_MODULE, encoding="utf-8")
    (copy,) = plan(project)["copies"]
    assert any("move `geistSans.variable` to the `<html>` className in app/layout.tsx:6" in n for n in copy["by_hand"])
    (project / "app/fonts.ts").write_text(FONTS_MODULE.replace("--font-geist-sans", "--font-other"), encoding="utf-8")
    (copy,) = plan(project)["copies"]
    assert not any("layout" in n for n in copy["by_hand"])  # a different font: not the one the tokens read


def test_a_font_from_somewhere_unreadable_says_it_could_not_be_checked(project: Path) -> None:
    _font_project(project, layout=LAYOUT_IMPORT.replace('"./fonts"', '"@/lib/fonts"'))
    (copy,) = plan(project)["copies"]
    (item,) = [n for n in copy["by_hand"] if "layout" in n]
    assert "could not see where geistSans is defined" in item and "var(--font-geist-sans)" in item
    (project / "app/layout.tsx").write_text(LAYOUT_IMPORT, encoding="utf-8")  # a relative import with no file behind it
    (copy,) = plan(project)["copies"]
    assert any("could not see where geistSans is defined" in n for n in copy["by_hand"])


def test_duplicate_next_app_routes_give_one_note(project: Path) -> None:
    _font_project(project, routes="app (next-app), ./app/ (next-app)")
    (copy,) = plan(project)["copies"]
    assert len([n for n in copy["by_hand"] if "layout" in n]) == 1
