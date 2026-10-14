"""audit.py full mode: cross-file rules, inconsistency-only mode, and the inventory scanner in _plumb.py.

Every folder in tests/fixtures/audit/cross/<rule>/ is a cross-file rule id; each case folder (bad*, good*) is a small
project. case.json says what the rule must report: "expect": [[file, line], ...] (a line may be a token name, meaning the
line of that token in the tokens file), "tokens": "none" for a project with no tokens yet, "build": false to leave the
generated files unbuilt. A tokens.json in the case is the project's tokens; otherwise clean.tokens.json is used.
Every case also runs with CRLF line endings.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "plugins/plumb/assets/skill/scripts"
TEMPLATES = REPO / "plugins/plumb/assets/skill/assets/platforms/web"
CROSS = REPO / "tests/fixtures/audit/cross"
SKILL_REL = ".claude/skills/demo-design-system"
TOKENS_REL = f"{SKILL_REL}/assets/tokens/demo.tokens.json"
GEN_REL = f"{SKILL_REL}/assets/platforms/web/tokens.css"

sys.path.insert(0, str(SCRIPTS))
import _plumb as P  # noqa: E402


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A = _load("plumb_audit", "audit.py")
BT = _load("plumb_build_tokens", "build-tokens.py")
CROSS_IDS = {"near-duplicate-colour", "near-duplicate-size", "outlier-value", "duplicate-component", "contrast",
             "missing-dark-value", "focus-state", "hover-only", "touch-target", "reduced-motion", "generated-drift",
             "missing-token", "unused-token", "duplicate-tokens", "consolidate-components", "contrast-headroom",
             "consistency", "unknown-token-reference"}
ERROR_IDS = {"contrast", "generated-drift", "missing-dark-value"}
SUGGEST_IDS = {"missing-token", "unused-token", "duplicate-tokens", "consolidate-components", "contrast-headroom",
               "consistency"}


def severity_of(rule_id: str) -> str:
    return "error" if rule_id in ERROR_IDS else "suggest" if rule_id in SUGGEST_IDS else "warn"


def write(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def make_project(dest: Path, case: Path = None, tokens: object = "clean", build: bool = True, crlf: bool = False) -> Path:
    """A project in dest: the case's files, the skill's scripts, tokens (clean, the case's tokens.json, or none)."""
    dest.mkdir(parents=True, exist_ok=True)
    if case is not None:
        for src in sorted(case.rglob("*")):
            if src.is_file() and src.name not in ("case.json", "tokens.json"):
                text = src.read_text(encoding="utf-8")
                write(dest / src.relative_to(case), text, "\r\n" if crlf else "\n")
    skill = dest / SKILL_REL
    (skill / "scripts").mkdir(parents=True, exist_ok=True)
    for name in ("_plumb.py", "audit.py", "build-tokens.py"):
        shutil.copy(SCRIPTS / name, skill / "scripts" / name)
    if not (dest / "PLUMB.md").exists():
        write(dest / "PLUMB.md", "Project: demo\n\n## Checks\nAllowed raw values: components/ui/**\n")
    src_tokens = (case / "tokens.json") if case is not None and (case / "tokens.json").is_file() else None
    if tokens != "none":
        text = (src_tokens or CROSS / "clean.tokens.json").read_text(encoding="utf-8")
        write(dest / TOKENS_REL, text, "\r\n" if crlf else "\n")
        styling = json.loads(text)["$extensions"]["plumb"]["web"]["styling"]
        write(skill / "assets/platforms/web/tokens.css.template",
              (TEMPLATES / f"tokens.css.template.{styling}").read_text(encoding="utf-8"))
        if build:
            r = subprocess.run([sys.executable, str(skill / "scripts/build-tokens.py")], cwd=str(dest),
                               capture_output=True, text=True, encoding="utf-8")
            assert r.returncode == 0, r.stdout + r.stderr
    return dest


def run(project: Path, *args: str, script: Path = None):
    script = script or project / SKILL_REL / "scripts/audit.py"
    return subprocess.run([sys.executable, str(script), *args], cwd=str(project), capture_output=True, text=True,
                          encoding="utf-8")


def audit_json(project: Path, *args: str) -> dict:
    r = run(project, "--json", *args)
    assert r.returncode in (0, 1), r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    out = json.loads(r.stdout)
    out["_code"] = r.returncode
    out["_stderr"] = r.stderr
    return out


def token_line(project: Path, name: str) -> int:
    lines = (project / TOKENS_REL).read_text(encoding="utf-8").splitlines()
    return next(i for i, line in enumerate(lines, 1) if line.strip().startswith(f'"{name}":'))


# ---------------------------------------------------------------- the rule table


FIDELITY_IDS = {"route-not-prototyped", "screen-drift", "screen-unapproved", "screen-not-built", "state-missing-in-code",
                "no-prototype", "component-missing-in-code",
                "synced-from-code", "copy-missing-in-code", "missing-state"}  # tests/test_audit_fidelity.py


def test_cross_rules_are_in_the_one_rule_table() -> None:
    cross = {r.id: r for r in A.RULES if r.kind == "cross"}
    assert set(cross) == CROSS_IDS | FIDELITY_IDS
    for rule_id, r in cross.items():
        if rule_id in FIDELITY_IDS:
            continue
        assert r.severity == severity_of(rule_id), rule_id
        assert callable(r.check) and r.message and r.fix, rule_id
    assert {r.kind for r in A.RULES} == {"file", "cross"}


def test_every_cross_rule_has_a_failing_and_a_passing_case() -> None:
    dirs = {p.name for p in CROSS.iterdir() if p.is_dir()}
    assert dirs == CROSS_IDS, sorted(dirs ^ CROSS_IDS)
    for rule_id in CROSS_IDS:
        names = [p.name for p in (CROSS / rule_id).iterdir() if p.is_dir()]
        assert any(n.startswith("bad") for n in names), rule_id
        assert any(n.startswith("good") for n in names), rule_id


def cases():
    return sorted(p for p in CROSS.glob("*/*") if p.is_dir())


@pytest.mark.parametrize("variant", ["lf", "crlf"])
@pytest.mark.parametrize("case", cases(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_cross_fixture(case: Path, variant: str, tmp_path: Path) -> None:
    spec = json.loads((case / "case.json").read_text(encoding="utf-8"))
    rule = case.parent.name
    project = make_project(tmp_path / "Café Ünïcode", case, spec.get("tokens", "clean"), spec.get("build", True),
                           crlf=variant == "crlf")
    out = audit_json(project)
    got = sorted((f["file"], f["line"]) for f in out["findings"] if f["rule"] == rule)
    want = sorted((file, line if isinstance(line, int) else token_line(project, line)) for file, line in spec["expect"])
    detail = [(f["rule"], f["file"], f["line"], f["message"]) for f in out["findings"]]
    assert got == want, detail
    for f in out["findings"]:
        if f["rule"] == rule:
            assert f["severity"] == severity_of(rule)
            assert f["message"] and f["fix"]
    if spec.get("tokens") == "none":
        assert out["mode"] == "inconsistency-only"
    else:
        assert out["mode"] == "full"


# ---------------------------------------------------------------- specific messages and fixes


def test_drift_names_the_stale_file_and_the_build_command(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "generated-drift/bad-stale", build=False)
    r = run(project)
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"{GEN_REL}:1: error generated-drift" in r.stdout
    assert f"fix: python3 {SKILL_REL}/scripts/build-tokens.py" in r.stdout


def test_drift_ignores_line_endings_of_the_generated_file(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "generated-drift/good")
    path = project / GEN_REL
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert [f for f in audit_json(project)["findings"] if f["rule"] == "generated-drift"] == []


def test_drift_without_the_template_is_one_error_finding_not_a_crash(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "generated-drift/good")
    (project / SKILL_REL / "assets/platforms/web/tokens.css.template").unlink()
    out = audit_json(project)
    drift = [f for f in out["findings"] if f["rule"] == "generated-drift"]
    assert len(drift) == 1 and "template" in drift[0]["message"] and drift[0]["fix"]
    assert out["_code"] == 1


def test_contrast_reports_mode_ratio_and_nearest_passing_value(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "contrast/bad")
    found = [f for f in audit_json(project)["findings"] if f["rule"] == "contrast"]
    light = next(f for f in found if "on-primary on primary" in f["message"] and "light" in f["message"])
    assert "4.48:1" in light["message"] and "4.5:1" in light["message"]
    assert "#070707" in light["fix"] and "build-tokens.py" in light["fix"]
    assert any("text-muted on background" in f["message"] and "dark" in f["message"] for f in found)


def test_contrast_fix_for_white_on_a_fill_lists_the_fill_option_first(tmp_path: Path) -> None:
    """on-X is white over X: the fix names both options with their ratios, X stepped first (the text stays white)."""
    project = make_project(tmp_path / "p", CROSS / "contrast/bad")
    found = [f for f in audit_json(project)["findings"] if f["rule"] == "contrast"]
    light = next(f for f in found if "on-primary on primary" in f["message"] and "light" in f["message"])
    fix = light["fix"]
    assert fix.startswith("two options in light mode") and "keeps on-primary as it is (#ffffff)" in fix
    assert fix.index("(1) step primary to #") < fix.index("(2) step on-primary to #070707")
    first = fix.split("(1) step primary to ")[1][:7]
    assert P.contrast("#ffffff", first) >= 4.5 + BT.FIX_SPARE - 0.05  # the pale-teal fill darkened enough
    # dark mode: on-primary is #0f1217 (not black): only the on-primary option, worded as before
    dark = next(f for f in found if "on-primary on primary" in f["message"] and "dark" in f["message"])
    assert dark["fix"].startswith("nearest passing on-primary in dark mode:") and "two options" not in dark["fix"]


def test_contrast_uses_the_build_tokens_pair_logic() -> None:
    doc = P.load_tokens(CROSS / "contrast/bad/tokens.json")
    pairs = BT.measure_pairs(doc)
    failing = {(p.fg, p.bg, m) for p in pairs for m in p.failed}
    assert failing == {("on-primary", "primary", "light"), ("on-primary", "primary", "dark"),
                       ("text-muted", "background", "dark"), ("text-muted", "surface", "dark")}
    assert all(p.fg_path.startswith("color.") and p.bg_path.startswith("color.") for p in pairs)


def test_bad_contrast_settings_are_one_error_finding_not_a_crash(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "contrast/good")
    doc = json.loads((project / TOKENS_REL).read_text(encoding="utf-8"))
    doc["$extensions"]["plumb"]["contrast"] = {"extra_pairs": [["nope", "background", "text"]]}
    write(project / TOKENS_REL, json.dumps(doc, indent=2))
    out = audit_json(project)
    found = [f for f in out["findings"] if f["rule"] == "contrast"]
    assert len(found) == 1 and "nope" in found[0]["message"] and found[0]["fix"] and out["_code"] == 1


def test_type_tokens_of_one_size_but_different_styles_are_not_duplicates(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "duplicate-tokens/good")
    doc = json.loads((project / TOKENS_REL).read_text(encoding="utf-8"))
    doc["typography"]["label"] = {"$value": {"fontSize": "14px", "lineHeight": "16px", "fontWeight": 600}}
    write(project / TOKENS_REL, json.dumps(doc, indent=2))
    assert not [f for f in audit_json(project)["findings"] if f["rule"] == "duplicate-tokens"]
    doc["typography"]["body-sm"] = {"$value": {"fontSize": "14.5px", "lineHeight": "20px"}}
    write(project / TOKENS_REL, json.dumps(doc, indent=2))
    found = [f for f in audit_json(project)["findings"] if f["rule"] == "duplicate-tokens"]
    assert [f["line"] for f in found] == [token_line(project, "body-sm")]


def test_missing_dark_value_is_an_error_naming_the_token(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "missing-dark-value/bad")
    out = audit_json(project)
    found = [f for f in out["findings"] if f["rule"] == "missing-dark-value"]
    assert found[0]["severity"] == "error" and out["_code"] == 1
    assert "color.on-primary" in found[0]["message"] and "same-in-dark" in found[0]["fix"]


def test_same_in_dark_marks_a_deliberate_constant(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "missing-dark-value/good-same-in-dark")
    out = audit_json(project)
    assert not [f for f in out["findings"] if f["rule"] == "missing-dark-value"]


def test_themes_light_only_turns_the_dark_rules_off(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "missing-dark-value/bad")
    assert "missing-dark-value" in {f["rule"] for f in audit_json(project)["findings"]}
    write(project / "PLUMB.md", "Project: demo\nThemes: light-only\n")
    assert "missing-dark-value" not in {f["rule"] for f in audit_json(project)["findings"]}
    project = make_project(tmp_path / "q", CROSS / "contrast/bad")
    assert any("dark mode" in f["message"] for f in audit_json(project)["findings"] if f["rule"] == "contrast")
    write(project / "PLUMB.md", "Project: demo\nThemes: light-only\n")
    contrast = [f["message"] for f in audit_json(project)["findings"] if f["rule"] == "contrast"]
    assert contrast and all("light mode" in m and "dark" not in m for m in contrast), contrast


def test_suggestions_never_change_the_exit_code_and_are_counted_apart(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "unused-token/bad")
    out = audit_json(project)
    sugg = [f for f in out["findings"] if f["severity"] == "suggest"]
    assert sugg and out["suggestions"] == len(sugg) and out["errors"] == 0 and out["_code"] == 0
    assert all(f["message"] and f["fix"] for f in sugg)
    r = run(project)
    assert r.returncode == 0 and f"{len(sugg)} suggestion" in r.stdout and "suggest unused-token" in r.stdout
    assert "radius.md" in r.stdout


def test_unused_tokens_are_one_suggestion_per_group(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "unused-token/bad")
    found = [f for f in audit_json(project)["findings"] if f["rule"] == "unused-token"]
    colour = next(f for f in found if "colour" in f["message"])
    assert colour["message"].startswith("2 colour tokens are never used")
    assert "color.surface" in colour["message"] and "color.text-muted" in colour["message"]
    assert next(f for f in found if "radius" in f["message"])["message"].startswith("1 radius token is never used")


def test_unused_tokens_are_not_reported_for_an_early_project(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "unused-token/bad")
    for i in range(1, 5):
        (project / f"app/part{i}.tsx").unlink()
    assert not [f for f in audit_json(project)["findings"] if f["rule"] == "unused-token"]


def _created(project: Path, days_ago: int) -> None:
    import datetime
    day = (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()
    text = (project / "PLUMB.md").read_text(encoding="utf-8")
    write(project / "PLUMB.md", text + f"\n## Plumb updates\n- {day} created with Plumb 1.0.0 (web; direction \"x\")\n")


def test_a_just_created_system_gets_no_housekeeping_suggestions_about_its_own_tokens(tmp_path: Path) -> None:
    for days, quiet in ((0, True), (A.FRESH_DAYS - 1, True), (A.FRESH_DAYS, False), (90, False)):
        project = make_project(tmp_path / f"p{days}", CROSS / "unused-token/bad")
        doc = json.loads((project / TOKENS_REL).read_text(encoding="utf-8"))
        doc["color"]["surface-copy"] = dict(doc["color"]["surface"])  # a duplicate token
        write(project / TOKENS_REL, json.dumps(doc, indent=2))
        _created(project, days)
        rules = {f["rule"] for f in audit_json(project)["findings"]}
        assert ("unused-token" in rules) is not quiet and ("duplicate-tokens" in rules) is not quiet, (days, rules)


def _named_steps_case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    doc = json.loads((CROSS / "clean.tokens.json").read_text(encoding="utf-8"))
    doc["radius"] = {"$type": "dimension", "sm": {"$value": "4px"}, "lg": {"$value": "10px"}}
    doc["spacing"]["4"] = {"$value": "20px"}  # gap-4 is 20px in this project, not Tailwind's 16px
    write(case / "tokens.json", json.dumps(doc, indent=2))
    for i in range(3):
        write(case / f"app/card{i}.tsx",
              f'export const C{i} = () => <div className="rounded-lg gap-4 p-4 text-sm">x</div>;\n')
    return case


def test_named_tailwind_steps_count_at_the_projects_token_values(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", _named_steps_case(tmp_path))
    found = audit_json(project)["findings"]
    assert not [f for f in found if f["rule"] == "missing-token"], found  # rounded-lg is radius.lg = 10px here
    assert not [f for f in found if f["rule"] in ("off-scale-spacing", "off-scale-radius")], found
    inv = A.Project(project, project / SKILL_REL, json.loads((project / TOKENS_REL).read_text(encoding="utf-8")), {},
                    [A.make_ctx("app/card0.tsx", (project / "app/card0.tsx").read_text(encoding="utf-8"),
                                json.loads((project / TOKENS_REL).read_text(encoding="utf-8")), {})],
                    False, None).inventory
    assert set(inv["radius"]) == {"10px"} and set(inv["spacing"]) == {"20px"} and set(inv["font-size"]) == {"14px"}


def test_the_audit_skips_only_plumbs_block_in_a_web_copy(tmp_path: Path) -> None:
    case = tmp_path / "case"
    doc = json.loads((CROSS / "clean.tokens.json").read_text(encoding="utf-8"))
    doc["$extensions"]["plumb"]["web"]["copies"] = ["app/globals.css"]
    write(case / "tokens.json", json.dumps(doc, indent=2))
    write(case / "app/globals.css", '@import "tailwindcss";\n\nbody {\n  color: #123456;\n}\n')
    write(case / "app/page.tsx", 'export default () => <p className="text-sm">x</p>;\n')
    project = make_project(tmp_path / "p", case)  # the build adds the block to app/globals.css
    text = (project / "app/globals.css").read_text(encoding="utf-8")
    assert "/* plumb:start" in text
    line = text.splitlines().index("  color: #123456;") + 1
    found = [f for f in audit_json(project, "app")["findings"] if f["file"] == "app/globals.css"]
    assert [(f["rule"], f["line"]) for f in found] == [("raw-colour", line)], found  # the project's line, not the block's
    assert not [f for f in audit_json(project)["findings"] if f["rule"] == "generated-drift"]


def test_focus_inconsistency_names_the_majority(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "focus-state/bad-inconsistent")
    found = [f for f in audit_json(project)["findings"] if f["rule"] == "focus-state"]
    assert "outline" in found[0]["message"] and "ring" in found[0]["message"] and "inconsistent" in found[0]["message"]


def test_mobile_touch_targets_name_points_and_dp(tmp_path: Path) -> None:
    for case, unit in (("bad-ios", "44pt"), ("bad-android", "48dp")):
        project = make_project(tmp_path / case, CROSS / f"touch-target/{case}")
        found = [f for f in audit_json(project)["findings"] if f["rule"] == "touch-target"]
        assert found and all(unit in f["message"] and f["severity"] == "warn" for f in found), found


def test_review_duplications_are_gone() -> None:
    for name in ("_px_len", "_fmt_need", "_is_text_role"):
        assert not hasattr(A, name), name
    assert BT._is_text_name is P.is_text_name and callable(P.tailwind_project) and callable(P._px_len)


def test_missing_token_proposes_a_name(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "missing-token/bad")
    found = [f for f in audit_json(project)["findings"] if f["rule"] == "missing-token"]
    assert "#b45309" in found[0]["message"] and "3 times" in found[0]["message"]
    assert "color." in found[0]["fix"] and "/plumb:update" in found[0]["fix"]


def test_contrast_headroom_proposes_a_value_with_half_a_point_to_spare(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "contrast-headroom/bad")
    found = [f for f in audit_json(project)["findings"] if f["rule"] == "contrast-headroom"]
    assert "4.51:1" in found[0]["message"] and "surface" in found[0]["message"]
    proposed = found[0]["fix"].split("#", 1)[1][:6]
    assert P.contrast("#" + proposed, "#f6f7f9") >= 5.0


def test_duplicate_component_points_at_the_primitive(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "duplicate-component/bad")
    found = [f for f in audit_json(project)["findings"] if f["rule"] == "duplicate-component"]
    assert len(found) == 3
    assert all("3 button-like components" in f["message"] for f in found), found
    assert all("Button primitive" in f["fix"] for f in found)


def test_cross_rules_never_run_in_quick_mode() -> None:
    text = '<button className="opacity-0 group-hover:opacity-100 h-6 w-6 transition">x</button>\n'
    rules = {f.rule for f in A.quick("app/x.tsx", "", text, None, {})}
    assert not rules & CROSS_IDS
    rules = {f.rule for f in A.audit_text("app/x.tsx", text, None, {})}
    assert not rules & CROSS_IDS


def test_explicit_paths_still_find_the_reduced_motion_block_elsewhere(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "reduced-motion/good", tokens="none")
    write(project / "app/page.tsx", 'export const P = () => <div className="transition-opacity">x</div>;\n')
    out = audit_json(project, "app/page.tsx")
    assert [f for f in out["findings"] if f["rule"] == "reduced-motion"] == []


# ---------------------------------------------------------------- inconsistency-only mode


def test_no_tokens_runs_inconsistency_only_and_exits_0_on_warnings(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "outlier-value/bad", tokens="none")
    write(project / "app/page.tsx", 'export const P = () => <p className="bg-[#13867f]" style={{ color: "#14857f" }}>x</p>;\n')
    r = run(project)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "inconsistency-only" in r.stdout and "raw-colour" not in r.stdout and "inline-style" not in r.stdout
    assert "warn outlier-value" in r.stdout or "warn near-duplicate-colour" in r.stdout
    out = audit_json(project)
    assert out["mode"] == "inconsistency-only" and out["errors"] == 0
    colours = out["scales"]["color"]
    assert colours[0]["value"] == "#14857f" and colours[0]["count"] >= 6 and "#13867f" in colours[0]["members"]


def test_no_tokens_still_fails_on_error_rules(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", tokens="none")
    write(project / "app/x.tsx", '<p className="text-lg">Saved 🎉</p>\n')
    r = run(project)
    assert r.returncode == 1 and "error emoji" in r.stdout, r.stdout + r.stderr


def test_no_tokens_flag_ignores_the_tokens_file(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", CROSS / "contrast/bad")
    write(project / "app/x.tsx", '<p className="bg-[#14857F]">x</p>\n')
    out = audit_json(project, "--no-tokens")
    assert out["mode"] == "inconsistency-only" and out["_code"] == 0
    assert not {f["rule"] for f in out["findings"]} & {"contrast", "generated-drift", "missing-dark-value", "raw-colour"}
    assert audit_json(project)["_code"] == 1


def test_single_html_prototype(tmp_path: Path) -> None:
    proto = tmp_path / "Prötotype" / "checkout.html"
    write(proto, (CROSS / "prototype.html").read_text(encoding="utf-8"))
    args = ["--json", "--root", str(tmp_path / "no-skill"), "--project", str(proto.parent), str(proto)]
    r = run(proto.parent, *args, script=SCRIPTS / "audit.py")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["mode"] == "inconsistency-only" and out["checked"] == 1
    got = sorted((f["rule"], f["line"]) for f in out["findings"])
    assert got == [("near-duplicate-size", 13), ("outlier-value", 22)], out["findings"]
    outlier = next(f for f in out["findings"] if f["rule"] == "outlier-value")
    assert "#2463eb" in outlier["message"] and "#2563eb" in outlier["fix"]
    scales = out["scales"]
    assert scales["font-size"][0]["value"] == "16px" and scales["color"][0]["value"] == "#2563eb"


# ---------------------------------------------------------------- the inventory


KINDS = ("color", "font-family", "font-size", "font-weight", "line-height", "spacing", "radius", "shadow", "duration",
         "easing")


def test_inventory_shape_and_normalisation(tmp_path: Path) -> None:
    write(tmp_path / "app/a.css",
          ":root { --brand: #14857F; }\n"
          ".a { color: #FFF; background: rgb(20, 133, 127); font: 600 1rem/1.5 \"Inter\", sans-serif; }\n"
          ".b { padding: 8px 1rem; margin: 0 auto; border-radius: 6px; box-shadow: 0 1px 2px #0000001A; }\n"
          ".c { transition: opacity 0.2s cubic-bezier(0.2, 0.8, 0.2, 1); font-weight: bold; line-height: 24px; }\n"
          "/* .x { color: #123456; } */\n")
    inv = P.scan_inventory([tmp_path], [])
    assert set(inv) == set(KINDS)
    assert inv["color"]["#14857f"] == {"count": 2, "where": ["app/a.css:1", "app/a.css:2"]}
    assert inv["color"]["#ffffff"]["count"] == 1 and "#123456" not in inv["color"]
    assert inv["font-size"]["16px"]["where"] == ["app/a.css:2"]
    assert inv["font-weight"]["600"]["count"] == 1 and inv["font-weight"]["700"]["count"] == 1
    assert inv["line-height"]["1.5"]["count"] == 1 and inv["line-height"]["24px"]["count"] == 1
    assert inv["font-family"]["inter, sans-serif"]["count"] == 1
    assert inv["spacing"]["8px"]["count"] == 1 and inv["spacing"]["16px"]["count"] == 1 and "0px" not in inv["spacing"]
    assert inv["radius"]["6px"]["count"] == 1
    assert inv["shadow"]["0 1px 2px #0000001a"]["count"] == 1
    assert inv["duration"]["200ms"]["count"] == 1
    assert inv["easing"]["cubic-bezier(0.2, 0.8, 0.2, 1)"]["count"] == 1


def test_inventory_counts_tailwind_classes_only_in_tailwind_projects(tmp_path: Path) -> None:
    page = '<div className="p-4 text-lg rounded-lg bg-teal-700 duration-200 ease-out font-semibold leading-6 hover:p-4" />\n'
    write(tmp_path / "tw/app/globals.css", '@import "tailwindcss";\n')
    write(tmp_path / "tw/app/page.tsx", page)
    inv = P.scan_inventory([tmp_path / "tw"], [])
    assert inv["spacing"]["16px"] == {"count": 2, "where": ["app/page.tsx:1"]}
    assert inv["font-size"]["18px"]["count"] == 1 and inv["radius"]["8px"]["count"] == 1
    assert inv["color"]["#0f766e"]["count"] == 1 and inv["duration"]["200ms"]["count"] == 1
    assert inv["easing"]["cubic-bezier(0, 0, 0.2, 1)"]["count"] == 1
    assert inv["font-weight"]["600"]["count"] == 1 and inv["line-height"]["24px"]["count"] == 1
    write(tmp_path / "plain/index.html", '<div class="p-4 text-lg">Bootstrap-style classes are not Tailwind</div>\n')
    inv = P.scan_inventory([tmp_path / "plain"], [])
    assert inv["spacing"] == {} and inv["font-size"] == {}


def test_inventory_skips_build_output_excludes_and_reads_crlf_and_unicode_paths(tmp_path: Path) -> None:
    write(tmp_path / "app/ünï/a.css", ".a {\n  color: #14857f;\n}\n", "\r\n")
    write(tmp_path / "node_modules/x/a.css", ".a { color: #111111; }\n")
    write(tmp_path / "dist/a.css", ".a { color: #222222; }\n")
    write(tmp_path / "legacy/a.css", ".a { color: #333333; }\n")
    write(tmp_path / "app/notes.md", "#444444\n")
    inv = P.scan_inventory([tmp_path], ["legacy/**"])
    assert inv["color"] == {"#14857f": {"count": 1, "where": ["app/ünï/a.css:2"]}}


def test_inventory_html_prototype_style_blocks_and_attributes() -> None:
    inv = P.scan_inventory([CROSS / "prototype.html"], [])
    assert inv["color"]["#2563eb"]["count"] == 5
    assert inv["color"]["#2463eb"]["where"] == ["prototype.html:22"]
    assert "#2462ea" not in inv["color"] and "#123" not in " ".join(inv["color"])
    assert inv["font-size"]["16px"]["count"] == 3 and inv["font-size"]["24px"]["count"] == 1
    assert inv["font-family"]["system-ui, sans-serif"]["count"] == 1
    assert inv["duration"]["150ms"]["count"] == 1 and inv["easing"]["ease-out"]["count"] == 1


def test_inventory_js_style_objects_swift_and_kotlin(tmp_path: Path) -> None:
    write(tmp_path / "app/x.tsx", 'const s = { fontSize: 14, padding: "12px", color: "#14857f", borderRadius: 6 };\n'
                                  'type P = { padding: number; color: string };\n')
    write(tmp_path / "ios/V.swift", 'Text("x").font(.system(size: 15)).padding(12).cornerRadius(8)\n'
                                    'let c = Color(red: 0.078, green: 0.522, blue: 0.498)\n')
    write(tmp_path / "android/V.kt", 'Text("x", fontSize = 15.sp, modifier = Modifier.padding(12.dp))\n'
                                     'val c = Color(0xFF14857F)\nval s = RoundedCornerShape(8.dp)\n')
    inv = P.scan_inventory([tmp_path], [])
    assert inv["font-size"]["14px"]["count"] == 1 and inv["font-size"]["15px"]["count"] == 2
    assert inv["spacing"]["12px"]["count"] == 3
    assert inv["radius"]["6px"]["count"] == 1 and inv["radius"]["8px"]["count"] == 2
    assert inv["color"]["#14857f"]["count"] == 3


def test_inventory_ignores_link_targets_ids_and_issue_numbers(tmp_path: Path) -> None:
    write(tmp_path / "app/x.tsx", '<a href="#add">Add</a>\n<p>Order #123</p>\n<use href="#fade" />\n'
                                  'document.querySelector("#face");\n<div id="cafe" />\n')
    write(tmp_path / "app/x.css", "#add { color: #abcdef; }\n.a { fill: url(#bead); }\n")
    inv = P.scan_inventory([tmp_path], [])
    assert inv["color"] == {"#abcdef": {"count": 1, "where": ["app/x.css:1"]}}


def test_cluster_colours_by_delta_e_and_proposes_the_most_used() -> None:
    inv = {k: {} for k in KINDS}
    for value, n in (("#14857f", 9), ("#13867f", 2), ("#15847e", 1), ("#1b2230", 4), ("#ffffff", 7)):
        inv["color"][value] = {"count": n, "where": [f"a.css:{i}" for i in range(n)]}
    clusters = P.cluster(inv, "color")
    assert clusters[0] == {"canonical": "#14857f", "members": ["#14857f", "#13867f", "#15847e"], "count": 12}
    assert [c["canonical"] for c in clusters] == ["#14857f", "#ffffff", "#1b2230"]


def test_cluster_sizes_within_1px_or_6_percent() -> None:
    inv = {k: {} for k in KINDS}
    for value, n in (("16px", 8), ("15px", 2), ("18px", 3), ("100px", 2), ("105px", 1), ("112px", 1)):
        inv["font-size"][value] = {"count": n, "where": []}
    groups = {c["canonical"]: c["members"] for c in P.cluster(inv, "font-size")}
    assert groups == {"16px": ["16px", "15px"], "18px": ["18px"], "100px": ["100px", "105px"], "112px": ["112px"]}
    assert P.cluster(inv, "shadow") == []
    inv["line-height"] = {"1.5": {"count": 3, "where": []}, "1.45": {"count": 1, "where": []}, "24px": {"count": 1, "where": []}}
    assert {c["canonical"]: c["members"] for c in P.cluster(inv, "line-height")} == {"1.5": ["1.5", "1.45"], "24px": ["24px"]}


# ---------------------------------------------------------------- speed


def _big_project(dest: Path, files: int) -> Path:
    project = make_project(dest)
    for i in range(files):
        folder = project / "app" / f"area{i % 40}"
        if i % 4 == 0:
            write(folder / f"s{i}.css", f".c{i} {{ color: #{i % 4096:03x}fff; padding: {i % 7 * 4}px; "
                                        f"transition: opacity 150ms ease-out; border-radius: {i % 5}px; }}\n" * 20)
        else:
            write(folder / f"C{i}.tsx", (
                f"export function C{i}() {{\n  return (\n    <div className=\"group p-4 bg-surface rounded-md\">\n"
                f"      <button className=\"h-8 w-8 opacity-0 group-hover:opacity-100 bg-primary rounded-md px-2 text-sm\">x</button>\n"
                f"      <p className=\"text-sm text-on-surface\">Item {i}</p>\n    </div>\n  );\n}}\n") * 5)
    return project


BASELINE_MIN = 0.2  # seconds: the smallest baseline worth a ratio (below it, timer and scheduler noise dominate)
BASELINE_FILES = (1000, 2000, 4000)  # doubled until the baseline takes BASELINE_MIN
RATIO_LIMIT = 8.0  # between linear (4) and quadratic (16), with room for machine load


def _audit_time(project: Path, files: int) -> float:
    start = time.perf_counter()
    r = run(project, "--json")
    elapsed = time.perf_counter() - start
    assert r.returncode == 1, r.stderr
    assert json.loads(r.stdout)["checked"] == files
    return elapsed


def test_full_audit_scales_linearly_and_stays_fast(tmp_path: Path) -> None:
    """4x the files take no worse than linear time (ratio under RATIO_LIMIT: 4 is linear, n log n about 4.8, quadratic
    16) and the big run stays under a generous 30 s cap (CI runners are slower than a laptop).

    The baseline sizes itself: from 1,000 files it doubles until its best of 3 takes at least BASELINE_MIN, so the
    ratio always applies and never rests on a run too short to time. Then the baseline and 4x its files are timed in
    turn (three times each, the fastest kept), so both see the same machine load, after one warm-up run each: the
    first run on freshly written files pays the OS's first-open cost (and an on-access virus scanner's). Robust to
    machine speed and load, still catches quadratic work."""
    for n in BASELINE_FILES:
        small_project = _big_project(tmp_path / f"small-{n}", n)
        if min(_audit_time(small_project, n) for _ in range(3)) >= BASELINE_MIN:
            break
    big_n = 4 * n
    big_project = _big_project(tmp_path / f"big-{big_n}", big_n)
    _audit_time(big_project, big_n)  # warm-up: first opens of freshly written files (and any on-access scanner)
    _audit_time(small_project, n)
    smalls, bigs = [], []
    for _ in range(3):
        smalls.append(_audit_time(small_project, n))
        bigs.append(_audit_time(big_project, big_n))
    small, big = min(smalls), min(bigs)
    print(f"audit timing: {n} files {small:.2f}s, {big_n} files {big:.2f}s, ratio {big / small:.1f}")
    assert big < 30.0, f"{big:.1f}s for {big_n} files"
    assert big / small < RATIO_LIMIT, f"{big_n} files took {big:.2f}s, {n} took {small:.2f}s: ratio {big / small:.1f}"
