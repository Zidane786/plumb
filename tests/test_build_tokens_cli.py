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
    r = run(project)
    assert r.returncode == 0
    assert r.stderr.startswith("note: ") and "not refreshed" in r.stderr and "--contrast" in r.stderr
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
    m = re.search(r"on-primary on primary \(light\): .*\(2\) step on-primary to #([0-9a-f]{6}) \(([\d.]+):1\)", table)
    assert m, table
    sys.path.insert(0, str(SCRIPTS))
    import _plumb as P
    assert P.contrast("#" + m.group(1), "#7fd6d0") >= 4.5
    assert float(m.group(2)) >= 4.5
    # light mode darkens the foreground: the suggestion is darker than white (white is the foreground here)
    assert m.group(1) != "ffffff"


def _line(table: str, pair: str, mode: str) -> str:
    return next(l for l in table.splitlines() if l.startswith(f"- {pair} ({mode}):"))


def test_white_on_a_fill_lists_the_fill_option_first_with_both_ratios(tmp_path: Path) -> None:
    """on-X white over X: X stepped (same hue, on-X unchanged) first, then on-X; each with its computed ratio."""
    sys.path.insert(0, str(SCRIPTS))
    import _plumb as P
    p = make_project(tmp_path, fail_mutation)
    assert run(p, "--contrast").returncode == 0
    line = _line(block(dark_md(p)), "on-primary on primary", "light")
    m = re.search(r"two options in light mode: \(1\) step primary to #([0-9a-f]{6}) \(([\d.]+):1, on-primary stays #ffffff\); "
                  r"\(2\) step on-primary to #([0-9a-f]{6}) \(([\d.]+):1\)",
                  line)
    assert m, line
    fill, fill_ratio, text, text_ratio = m.groups()
    assert P.contrast("#ffffff", "#" + fill) == pytest.approx(float(fill_ratio), abs=0.006) and float(fill_ratio) >= 5.0
    assert P.contrast("#" + text, "#7fd6d0") == pytest.approx(float(text_ratio), abs=0.006) and float(text_ratio) >= 5.0
    # same hue, darker: red/green/blue keep their order and every channel went down
    old, new = (int("7fd6d0"[i:i + 2], 16) for i in (0, 2, 4)), [int(fill[i:i + 2], 16) for i in (0, 2, 4)]
    assert all(n < o for n, o in zip(new, old)) and new[0] < new[2] < new[1]
    # the dark theme passes, so it has no line; --check agrees the block is current
    assert "on-primary on primary (dark)" not in block(dark_md(p))
    assert run(p).returncode == 0 and run(p, "--check").returncode == 0


def test_black_on_a_fill_lightens_the_fill_in_dark(tmp_path: Path) -> None:
    sys.path.insert(0, str(SCRIPTS))
    import _plumb as P

    def mut(doc: dict) -> None:
        doc["color"]["primary"]["$extensions"]["plumb"]["dark"] = "#1a3a3c"
        doc["color"]["on-primary"] = {"$value": "#ffffff", "$extensions": {"plumb": {"dark": "#000000"}}}
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    line = _line(block(dark_md(p)), "on-primary on primary", "dark")
    m = re.search(r"\(1\) step primary to #([0-9a-f]{6}) \(([\d.]+):1, on-primary stays #000000\); "
                  r"\(2\) step on-primary to #([0-9a-f]{6})", line)
    assert m, line
    assert P.contrast("#000000", "#" + m.group(1)) >= 4.5 and int(m.group(1)[2:4], 16) > 0x3a  # the fill went lighter


def test_a_foreground_that_is_not_white_or_black_keeps_the_single_suggestion(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["color"]["primary"]["$value"] = "#7fd6d0"
        doc["color"]["on-primary"] = {"$value": "#9a9a9a"}  # grey text on a pale fill: fails, but is neither white nor black
        doc["color"]["on-primary"]["$extensions"] = {"plumb": {"dark": "#9a9a9a"}}
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    line = _line(block(dark_md(p)), "on-primary on primary", "light")
    assert re.fullmatch(r"- on-primary on primary \(light\): nearest passing #[0-9a-f]{6} \([\d.]+:1\)", line), line
    bt = _bt()
    doc = json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))
    pair = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-primary", "primary"))
    assert pair.fix_bg == {} and len(pair.options("light")) == 1


def test_only_on_x_on_x_pairs_step_the_fill(tmp_path: Path) -> None:
    """White text over a surface that is not its on-X partner (on-surface-style pairs) keeps the single suggestion:
    stepping a surface would change many pairs, so the fill option is for a control's own on-X only."""
    bt = _bt()
    p = make_project(tmp_path, fail_mutation)
    doc = json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))
    doc["color"]["on-surface"]["$value"] = "#ffffff"
    pairs = bt.measure_pairs(doc)
    pair = next(x for x in pairs if (x.fg, x.bg) == ("on-surface", "background"))
    assert pair.failed and pair.fix_bg == {}


@pytest.mark.parametrize("value,end", [
    ("#ffffff", "white"), ("#fafafa", "white"), ("oklch(0.985 0 0)", "white"), ("#000000", "black"),
    ("#0a0a0a", "black"), ("#0f1217", "black"),
    ("#d0d0d0", None),      # a light grey: neutral but not near white (luminance 0.63)
    ("#9a9a9a", None), ("#4d4d4d", None),
    ("#f7e9ff", None),      # near white but tinted (chroma above the neutral limit)
])
def test_which_text_colours_count_as_white_or_black(value: str, end) -> None:
    bt = _bt()
    sys.path.insert(0, str(SCRIPTS))
    import _plumb as P
    hexv = P.parse_color(value)[0]
    assert bt.neutral_end(hexv) == end


def _fill_doc(tmp_path: Path, fg: str, fill: str, dark_fill: str, bg_name: str = "primary", dark_fg: str = None):
    def mut(doc: dict) -> None:
        on = "on-" + bg_name
        doc["color"][bg_name] = {"$value": fill, "$extensions": {"plumb": {"dark": dark_fill}}}
        doc["color"][on] = {"$value": fg, "$extensions": {"plumb": {"dark": dark_fg or fg}}}
    p = make_project(tmp_path, mut)
    return p, json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))


def test_stock_shadcn_near_white_on_primary_gets_the_fill_option(tmp_path: Path) -> None:
    """oklch(0.985 0 0) text on a mid blue is the stock shadcn pair: the fill option exists and keeps the text value."""
    bt = _bt()
    for fg in ("oklch(0.985 0 0)", "#fafafa"):
        p, doc = _fill_doc(tmp_path / fg[1:4], fg, "#3b82f6", "#60a5fa")
        pair = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-primary", "primary"))
        assert pair.light < 4.5 and pair.fix_bg["light"] and pair.options("light")[0][0] == "primary"
        text = pair.fix_text("light")
        assert text.startswith("two options in light mode: (1) step primary to #") and "on-primary stays #fafafa" in text


def test_a_light_grey_on_a_fill_keeps_the_single_suggestion(tmp_path: Path) -> None:
    bt = _bt()
    _p, doc = _fill_doc(tmp_path, "#d0d0d0", "#8fb8ff", "#8fb8ff")
    pair = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-primary", "primary"))
    assert pair.light < 4.5 and pair.fix_bg == {} and len(pair.options("light")) == 1


def test_the_fill_stays_within_a_degree_of_hue(tmp_path: Path) -> None:
    """Stepping a saturated green (where clipping channels used to rotate the hue by ~7 degrees) keeps its OKLCH hue."""
    bt = _bt()
    sys.path.insert(0, str(SCRIPTS))
    _p, doc = _fill_doc(tmp_path, "#ffffff", "#22c55e", "#22c55e")
    pair = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-primary", "primary"))
    value = pair.fix_bg["light"][0]
    old, new = bt._oklch("#22c55e")[2], bt._oklch(value)[2]
    assert abs((new - old + 180) % 360 - 180) <= 1.0, (old, new, value)
    assert pair.fix_bg["light"][1] >= 4.5


def test_a_surface_lists_the_text_option_first_and_a_control_the_fill_first(tmp_path: Path) -> None:
    bt = _bt()
    for surface in ("surface", "background", "sunk", "raised", "card", "popover"):
        _p, doc = _fill_doc(tmp_path / surface, "#ffffff", "#9ca3af", "#9ca3af", bg_name=surface)
        pair = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-" + surface, surface))
        assert pair.fix_bg["light"] and pair.fix["light"], surface
        assert [o[0] for o in pair.options("light")] == ["on-" + surface, surface], surface
    for control in ("primary", "danger", "success", "accent"):
        _p, doc = _fill_doc(tmp_path / control, "#ffffff", "#9ca3af", "#9ca3af", bg_name=control)
        pair = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-" + control, control))
        assert [o[0] for o in pair.options("light")] == [control, "on-" + control], control


def test_an_alias_fill_names_the_source_token(tmp_path: Path) -> None:
    bt = _bt()

    def mut(doc: dict) -> None:
        doc["color"]["brand"] = {"$value": "#7fd6d0", "$extensions": {"plumb": {"dark": "#7fd6d0"}}}
        doc["color"]["primary"] = {"$value": "{color.brand}"}
        doc["color"]["on-primary"] = {"$value": "#ffffff"}
    p = make_project(tmp_path, mut)
    doc = json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))
    pair = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-primary", "primary"))
    assert pair.options("light")[0][1] == "color.brand"
    assert "(it is an alias: change it at the source token color.brand)" in pair.fix_text("light")
    assert run(p, "--contrast").returncode == 0
    assert "source token color.brand" in block(dark_md(p))


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


def _bt():
    import importlib.util
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("bt_headroom_test", SCRIPTS / "build-tokens.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_proposed_value_clears_the_audits_headroom_rule(tmp_path: Path) -> None:
    """A value Plumb proposes for a failing pair passes with 0.5 to spare, so the same audit's contrast-headroom
    suggestion (a pair under 0.3 above the minimum) never flags it once applied."""
    bt = _bt()
    p = make_project(tmp_path, fail_mutation)
    doc = json.loads((skill(p) / TOKENS_REL).read_text(encoding="utf-8"))
    pair = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-primary", "primary"))
    value, ratio = pair.fix["light"]
    assert ratio >= pair.need + bt.FIX_SPARE and bt.FIX_SPARE >= bt.HEADROOM
    doc["color"]["on-primary"]["$value"] = value
    again = next(x for x in bt.measure_pairs(doc) if (x.fg, x.bg) == ("on-primary", "primary"))
    assert again.light >= again.need + bt.HEADROOM  # out of contrast-headroom's range (need <= ratio < need + 0.3)
    audit = (SCRIPTS / "audit.py").read_text(encoding="utf-8")
    assert 'getattr(bt, "HEADROOM", 0.3)' in audit  # the audit reads the same threshold


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


@pytest.mark.parametrize("name,expected", [
    ("pink", False), ("label-pink", False), ("blink", False), ("context-menu", False), ("textarea-border", False),
    ("subtext", False), ("outline-input", False),
    ("text", True), ("text-muted", True), ("ink", True), ("primary-ink", True), ("link", True), ("on-primary", True),
])
def test_text_names_are_whole_words(name: str, expected: bool) -> None:
    sys.path.insert(0, str(SCRIPTS))
    import importlib.util
    spec = importlib.util.spec_from_file_location("bt_names", SCRIPTS / "build-tokens.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._is_text_name(name) is expected


def test_pink_label_is_not_checked_as_text(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["color"]["label-pink"] = {"$value": "#ffc0cb"}
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    assert "pink" not in block(dark_md(p))


def test_on_surface_family_is_checked_over_every_surface(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        for n, (l, d) in {"sunk": ("#f2f4f6", "#12151b"), "column": ("#f6f7f9", "#161a21"),
                          "on-surface-variant": ("#5e6675", "#a7afbb")}.items():
            doc["color"][n] = {"$value": l, "$extensions": {"plumb": {"dark": d}}}
        doc["color"]["primary-container"] = {"$value": "#e3f3f1", "$extensions": {"plumb": {"dark": "#12403d"}}}
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    table = block(dark_md(p))
    for pair in ("on-surface-variant on sunk", "on-surface-variant on column", "on-surface-variant on background",
                 "on-surface on sunk", "on-surface on column", "on-surface on primary-container"):
        assert f"| {pair} |" in table, pair
    assert "| on-primary on background |" not in table


def test_extra_pairs_list_form(tmp_path: Path) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"]["plumb"]["contrast"] = {"extra_pairs": [
            ["on-primary", "primary", "text"], ["primary", "background", "large"], ["primary", "on-surface", "ui"]]}
    p = make_project(tmp_path, mut)
    assert run(p, "--contrast").returncode == 0
    table = block(dark_md(p))
    assert re.search(r"\| on-primary on primary \| [\d.]+ \| [\d.]+ \| 4\.5 \|", table)
    assert re.search(r"\| primary on background \| [\d.]+ \| [\d.]+ \| 3 \|", table)
    assert re.search(r"\| primary on on-surface \| [\d.]+ \| [\d.]+ \| 3 \|", table)


@pytest.mark.parametrize("entry", [["primary", "background"], ["primary", "background", "huge"], ["primary", "nope", "text"],
                                   ["primary", "background", "text", "x"], [1, 2, 3]])
def test_bad_list_form_extra_pairs(tmp_path: Path, entry) -> None:
    def mut(doc: dict) -> None:
        doc["$extensions"]["plumb"]["contrast"] = {"extra_pairs": [entry]}
    p = make_project(tmp_path, mut)
    assert_refusal(run(p, "--contrast"), "extra_pairs")


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
