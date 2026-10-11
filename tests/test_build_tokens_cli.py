"""build-tokens.py --contrast, --migrate, --css-vars, error paths, and the Material role fallbacks."""

from __future__ import annotations

import copy
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
TEMPLATE = REPO / "plugins/plumb/assets/skill/references/dark-mode.md.tmpl"
SKILL_REL = ".claude/skills/demo-design-system"
TOKENS_REL = "assets/tokens/demo.tokens.json"
START, END = "<!-- plumb:contrast:start -->", "<!-- plumb:contrast:end -->"


def write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def make_project(tmp_path: Path, mutate=None, platforms=None, dark_doc: bool = True) -> Path:
    dest = tmp_path / "proj"
    shutil.copytree(FIXTURE, dest)
    scripts = dest / SKILL_REL / "scripts"
    for name in ("_plumb.py", "build-tokens.py"):
        shutil.copy(SCRIPTS / name, scripts / name)
    tokens = dest / SKILL_REL / TOKENS_REL
    doc = json.loads(tokens.read_text(encoding="utf-8"))
    if platforms:
        doc["$extensions"]["plumb"]["platforms"] = platforms
    if mutate:
        mutate(doc)
    write(tokens, json.dumps(doc, indent=2))
    if dark_doc:
        refs = dest / SKILL_REL / "references"
        refs.mkdir(parents=True, exist_ok=True)
        shutil.copy(TEMPLATE, refs / "dark-mode.md")
    return dest


def skill(p: Path) -> Path:
    return p / SKILL_REL


def run(p: Path, *args: str):
    return subprocess.run(
        [sys.executable, str(skill(p) / "scripts/build-tokens.py"), *args],
        cwd=str(p), capture_output=True, text=True, encoding="utf-8",
    )


def dark_md(p: Path) -> str:
    return (skill(p) / "references/dark-mode.md").read_text(encoding="utf-8")


def block(text: str) -> str:
    return text.split(START)[1].split(END)[0]


def assert_refusal(r, *needles: str) -> None:
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert r.stderr.startswith("error: ") and "\nfix: " in r.stderr, r.stderr
    assert "Traceback" not in r.stderr
    for n in needles:
        assert n in r.stderr, r.stderr


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path)


# ---------------------------------------------------------------- --contrast


def test_template_has_markers() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert START in text and END in text and text.index(START) < text.index(END)


def test_contrast_rewrites_only_the_block(project: Path) -> None:
    path = skill(project) / "references/dark-mode.md"
    text = path.read_text(encoding="utf-8")
    write(path, "HEAD KEEP\n" + text + "TAIL KEEP\n")
    r = run(project, "--contrast")
    assert r.returncode == 0, r.stderr
    out = dark_md(project)
    assert out.startswith("HEAD KEEP\n") and out.endswith("TAIL KEEP\n")
    before, after = out.split(START)[0], out.split(END)[1]
    assert before == "HEAD KEEP\n" + text.split(START)[0] and after == text.split(END)[1] + "TAIL KEEP\n"
    table = block(out)
    assert "| Pair | Light | Dark | Need | Result |" in table
    # on-X over X, text over surfaces
    assert re.search(r"\| on-primary on primary \| [\d.]+ \| [\d.]+ \| 4\.5 \| (pass|fail \([a-z, ]+\)) \|", table)
    assert re.search(r"\| on-surface on background \| 15\.\d+ \| 15\.\d+ \| 4\.5 \| pass \|", table)


def test_contrast_values_are_wcag(project: Path) -> None:
    sys.path.insert(0, str(SCRIPTS))
    import _plumb as P
    assert run(project, "--contrast").returncode == 0
    table = block(dark_md(project))
    row = next(l for l in table.splitlines() if l.startswith("| on-surface on background "))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert float(cells[1]) == P.contrast("#1b2230", "#ffffff")
    assert float(cells[2]) == P.contrast("#e7eaef", "#0f1217")


def test_contrast_is_idempotent_and_default_build_refreshes_block(project: Path) -> None:
    assert run(project, "--contrast").returncode == 0
    first = dark_md(project)
    assert run(project, "--contrast").returncode == 0
    assert dark_md(project) == first
    assert run(project).returncode == 0
    assert run(project, "--check").returncode == 0
    # a token change makes the block stale for --check, and a build refreshes it
    tokens = skill(project) / TOKENS_REL
    doc = json.loads(tokens.read_text(encoding="utf-8"))
    doc["color"]["on-surface"]["$extensions"]["plumb"]["dark"] = "#cccccc"
    write(tokens, json.dumps(doc, indent=2))
    r = run(project, "--check")
    assert r.returncode == 1 and "references/dark-mode.md" in r.stdout
    assert run(project).returncode == 0
    assert "CCCCCC".lower() not in block(dark_md(project))  # ratios, not hex, in the table
    assert run(project, "--check").returncode == 0


def test_default_build_skips_a_dark_mode_file_without_markers(project: Path) -> None:
    path = skill(project) / "references/dark-mode.md"
    write(path, "# my own notes\n")
    assert run(project).returncode == 0
    assert path.read_text(encoding="utf-8") == "# my own notes\n"


def test_contrast_keeps_crlf(project: Path) -> None:
    path = skill(project) / "references/dark-mode.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert run(project, "--contrast").returncode == 0
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def fail_mutation(doc: dict) -> None:
    doc["color"]["primary"]["$value"] = "#7fd6d0"  # pale teal: on-primary (white) fails in light
    doc["color"]["primary"]["$extensions"]["plumb"]["dark"] = "#1a3a3c"  # white on it passes in dark


def test_failures_list_nearest_passing_value(tmp_path: Path) -> None:
    p = make_project(tmp_path, fail_mutation)
    r = run(p, "--contrast")
    assert r.returncode == 0, r.stderr
    table = block(dark_md(p))
    row = next(l for l in table.splitlines() if l.startswith("| on-primary on primary "))
    assert "fail" in row
    m = re.search(r"on-primary on primary \(light\): nearest passing #([0-9a-f]{6}) \(([\d.]+):1\)", table)
    assert m, table
    sys.path.insert(0, str(SCRIPTS))
    import _plumb as P
    assert P.contrast("#" + m.group(1), "#7fd6d0") >= 4.5
    assert float(m.group(2)) >= 4.5
    # light mode darkens the foreground: the suggestion is darker than white (white is the foreground here)
    assert m.group(1) != "ffffff"


def test_dark_failure_lightens(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["color"]["on-surface"]["$extensions"]["plumb"]["dark"] = "#2a3040"  # dim text on #0f1217
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    table = block(dark_md(p))
    m = re.search(r"on-surface on background \(dark\): nearest passing #([0-9a-f]{6})", table)
    assert m, table
    sys.path.insert(0, str(SCRIPTS))
    import _plumb as P
    assert P.contrast("#" + m.group(1), "#0f1217") >= 4.5
    assert int(m.group(1)[:2], 16) > 0x2a  # lightened


def test_ui_boundary_uses_three_to_one(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["color"]["outline-input"] = {"$value": "#838b98", "$extensions": {"plumb": {"dark": "#6e7785"}}}
        doc["color"]["surface"] = {"$value": "#ffffff", "$extensions": {"plumb": {"dark": "#1c2129"}}}
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    row = next(l for l in block(dark_md(p)).splitlines() if l.startswith("| outline-input on surface "))
    assert "| 3 |" in row


def test_contrast_ui_setting_and_surfaces_setting(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["color"]["edge"] = {"$value": "#8a8a8a"}
        doc["color"]["card-x"] = {"$value": "#ffffff", "$extensions": {"plumb": {"dark": "#1c2129"}}}
        doc["$extensions"]["plumb"]["contrast"] = {"ui": ["edge"], "surfaces": ["card-x"]}
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    table = block(dark_md(p))
    assert "| edge on card-x |" in table
    assert "| on-surface on card-x |" in table
    assert "on-surface on background" not in table  # surfaces were replaced by the listed ones


def test_extra_pairs(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"]["plumb"]["contrast"] = {"extra_pairs": [{"fg": "primary", "bg": "background", "need": 3, "note": "icon"}]}
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    assert re.search(r"\| primary on background \| [\d.]+ \| [\d.]+ \| 3 \|", block(dark_md(p)))


@pytest.mark.parametrize("pairs", [
    [{"fg": "nope", "bg": "background"}],
    [{"fg": "primary"}],
    ["primary"],
    [{"fg": "primary", "bg": "background", "need": "high"}],
    "primary",
])
def test_bad_extra_pairs_are_refused(tmp_path: Path, pairs) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"]["plumb"]["contrast"] = {"extra_pairs": pairs}
    p = make_project(tmp_path, mut)
    assert_refusal(run(p, "--contrast"), "extra_pairs")
    assert_refusal(run(p), "extra_pairs")


def test_contrast_without_file_or_markers_is_refused(tmp_path: Path) -> None:
    p = make_project(tmp_path, dark_doc=False)
    assert_refusal(run(p, "--contrast"), "dark-mode.md")
    assert "fix:" in run(p, "--contrast").stderr
    refs = skill(p) / "references"
    refs.mkdir(parents=True, exist_ok=True)
    write(refs / "dark-mode.md", "# no markers\n")
    assert_refusal(run(p, "--contrast"), "plumb:contrast:start")
    assert (refs / "dark-mode.md").read_text(encoding="utf-8") == "# no markers\n"


# ---------------------------------------------------------------- --migrate


def strip_schema(doc: dict) -> None:
    doc["$extensions"] = {"plumb": {"project": "demo", "platforms": ["web"]}}


def contains(old, new) -> bool:
    """Every value of `old` is present, unchanged, in `new`."""
    if isinstance(old, dict):
        return isinstance(new, dict) and all(k in new and contains(v, new[k]) for k, v in old.items())
    return old == new


def test_migrate_schema0_adds_and_never_changes(tmp_path: Path) -> None:
    p = make_project(tmp_path, strip_schema)
    tokens = skill(p) / TOKENS_REL
    old = json.loads(tokens.read_text(encoding="utf-8"))
    r = run(p, "--migrate")
    assert r.returncode == 0, r.stderr
    new = json.loads(tokens.read_text(encoding="utf-8"))
    assert contains(old, new)
    ext = new["$extensions"]["plumb"]
    assert ext["schema"] == 1 and ext["docs_dir"] == "docs/design"
    assert ext["web"]["styling"] == "css" and ext["web"]["copies"] == []
    assert ext["contrast"]["extra_pairs"] == []
    assert ext["project"] == "demo" and ext["platforms"] == ["web"]  # existing values kept
    assert "schema" in r.stdout and "added" in r.stdout
    assert tokens.read_bytes().endswith(b"\n") and b"\r" not in tokens.read_bytes()


def test_migrate_without_any_extensions(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        del doc["$extensions"]
    p = make_project(tmp_path, mut)
    old = json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))
    assert run(p, "--migrate").returncode == 0
    new = json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))
    assert contains(old, new) and new["$extensions"]["plumb"]["schema"] == 1


def test_migrate_keeps_existing_web_settings(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"] = {"plumb": {"web": {"styling": "tailwind-v4"}, "contrast": {"extra_pairs": [{"fg": "primary", "bg": "background"}]}}}
    p = make_project(tmp_path, mut)
    old = json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))
    assert run(p, "--migrate").returncode == 0
    new = json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))
    assert contains(old, new)
    assert new["$extensions"]["plumb"]["web"]["styling"] == "tailwind-v4"
    assert new["$extensions"]["plumb"]["web"]["copies"] == []


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    p = make_project(tmp_path, strip_schema)
    assert run(p, "--migrate").returncode == 0
    first = (skill(p) / TOKENS_REL).read_bytes()
    r = run(p, "--migrate")
    assert r.returncode == 0 and "nothing to add" in r.stdout
    assert (skill(p) / TOKENS_REL).read_bytes() == first


def test_migrate_refuses_newer_schema(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"]["plumb"]["schema"] = 7
    p = make_project(tmp_path, mut)
    before = (skill(p) / TOKENS_REL).read_bytes()
    assert_refusal(run(p, "--migrate"), "schema")
    assert (skill(p) / TOKENS_REL).read_bytes() == before


def test_migrate_refuses_bad_schema_value(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"]["plumb"]["schema"] = "one"
    p = make_project(tmp_path, mut)
    assert_refusal(run(p, "--migrate"), "schema")


def test_migrate_refuses_non_object_extensions(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"] = {"plumb": "oops"}
    p = make_project(tmp_path, mut)
    assert_refusal(run(p, "--migrate"), "$extensions")


# ---------------------------------------------------------------- --css-vars


def test_css_vars(project: Path) -> None:
    r = run(project, "--css-vars")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert ":root{" in out.replace(" ", "").replace("\n", "") or ":root {" in out
    assert "--color-background: #ffffff;" in out
    assert "--color-primary: #14857f;" in out
    assert "--color-link: var(--color-primary);" in out
    assert "--radius-md: 6px;" in out
    root_part, rest = out.split(".dark", 1)
    assert "--color-background: #ffffff;" in root_part and "#0f1217" not in root_part
    dark_part = rest
    assert "--color-background: #0f1217;" in dark_part
    assert "@media (prefers-color-scheme: dark)" in out and ":root:not(.light)" in out
    assert out.count("--color-background: #0f1217;") == 2
    assert "--color-on-primary" not in dark_part  # only tokens with a dark value
    for banned in ("@theme", "@apply", "@import", "@custom-variant", "@utility", "{{"):
        assert banned not in out
    assert "\r" not in out


def test_css_vars_is_deterministic_and_writes_nothing(project: Path) -> None:
    a, b = run(project, "--css-vars"), run(project, "--css-vars")
    assert a.stdout == b.stdout
    assert not (skill(project) / "assets/platforms/web/tokens.css").exists()


def test_css_vars_without_dark_has_no_dark_block(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        for _k, tok in doc["color"].items():
            if isinstance(tok, dict):
                tok.pop("$extensions", None)
        doc["shadow"]["card"].pop("$extensions")
    p = make_project(tmp_path, mut)
    out = run(p, "--css-vars").stdout
    assert ".dark" not in out and "prefers-color-scheme" not in out and "--shadow-card" in out


# ---------------------------------------------------------------- error paths


@pytest.mark.parametrize("flag", ["--contrast", "--migrate", "--css-vars", "--check", None])
def test_missing_tokens_file(tmp_path: Path, flag) -> None:
    p = make_project(tmp_path)
    (skill(p) / TOKENS_REL).unlink()
    assert_refusal(run(p, *([flag] if flag else [])), "tokens")


def test_unknown_reference(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["color"]["link"]["$value"] = "{color.nope}"
    p = make_project(tmp_path, mut)
    for flag in ("--contrast", "--css-vars", None):
        assert_refusal(run(p, *([flag] if flag else [])), "unknown token: color.nope")


def test_unsupported_colour(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["color"]["primary"]["$value"] = "rebeccapurple"
    p = make_project(tmp_path, mut)
    for flag in ("--contrast", "--css-vars", None):
        assert_refusal(run(p, *([flag] if flag else [])), "not a colour value")


def test_broken_json_names_file_and_line(tmp_path: Path) -> None:
    p = make_project(tmp_path)
    write(skill(p) / TOKENS_REL, '{\n  "color": {,\n}\n')
    for flag in ("--contrast", "--migrate", "--css-vars"):
        assert_refusal(run(p, flag), "demo.tokens.json", "line 2")


def test_conflicting_modes_are_refused(project: Path) -> None:
    assert_refusal(run(project, "--migrate", "--contrast"), "one of")
    assert_refusal(run(project, "--css-vars", "--check"), "one of")


def test_non_object_token_group_is_refused_without_traceback(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"]["plumb"]["contrast"] = ["x"]
    p = make_project(tmp_path, mut)
    r = run(p, "--contrast")
    assert "Traceback" not in r.stderr


# ---------------------------------------------------------------- Kotlin carried fixes


def kotlin(p: Path) -> str:
    return (skill(p) / "assets/platforms/mobile/android/DemoTheme.kt").read_text(encoding="utf-8")


def role_block(text: str, fn: str) -> str:
    return text.split(f"{fn}(", 1)[1].split("\n)\n", 1)[0]


ALL_ROLES = [
    "primary", "onPrimary", "primaryContainer", "onPrimaryContainer", "secondary", "onSecondary", "secondaryContainer",
    "onSecondaryContainer", "tertiary", "onTertiary", "tertiaryContainer", "onTertiaryContainer", "background",
    "onBackground", "surface", "onSurface", "surfaceVariant", "onSurfaceVariant", "outline", "outlineVariant", "error",
    "onError", "errorContainer", "onErrorContainer", "inverseSurface", "inverseOnSurface", "inversePrimary", "scrim",
    "surfaceTint", "surfaceContainerLowest", "surfaceContainerLow", "surfaceContainer", "surfaceContainerHigh",
    "surfaceContainerHighest",
]


def test_no_material_default_purple_role_remains(tmp_path: Path) -> None:
    p = make_project(tmp_path, platforms=["web", "android"])
    assert run(p).returncode == 0
    text = kotlin(p)
    for fn in ("lightColorScheme", "darkColorScheme"):
        scheme = role_block(text, fn)
        for role in ALL_ROLES:
            assert re.search(rf"^    {role} = Demo(Light|Dark)Colors\.\w+,$", scheme, re.M), f"{role} missing in {fn}"
    assert "= lightColorScheme()" not in text and "= darkColorScheme()" not in text
    scheme = role_block(text, "lightColorScheme")
    assert "secondary = DemoLightColors.primary," in scheme
    assert "surfaceVariant = DemoLightColors.background," in scheme  # nothing sunk/column/surface in the fixture
    assert "outline = DemoLightColors.onSurface," in scheme


def test_roles_prefer_matching_tokens(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["color"]["sunk"] = {"$value": "#f2f4f6", "$extensions": {"plumb": {"dark": "#12151b"}}}
        doc["color"]["outline"] = {"$value": "#e6e8ec", "$extensions": {"plumb": {"dark": "#2a303a"}}}
        doc["color"]["bad"] = {"$value": "#d6453d"}
    p = make_project(tmp_path, mut, platforms=["web", "android"])
    assert run(p).returncode == 0
    scheme = role_block(kotlin(p), "lightColorScheme")
    assert "surfaceVariant = DemoLightColors.sunk," in scheme
    assert "outline = DemoLightColors.outline," in scheme
    assert "error = DemoLightColors.bad," in scheme


def test_kotlin_without_colours_has_no_empty_class(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        del doc["color"]
    p = make_project(tmp_path, mut, platforms=["web", "android"])
    r = run(p)
    assert r.returncode == 0, r.stderr
    text = kotlin(p)
    assert "data class DemoColors()" not in text and "DemoColors(" not in text
    assert "LocalDemoColors" not in text and "val colors: DemoColors" not in text
    assert "fun DemoTheme(" in text and "colorScheme = " in text
