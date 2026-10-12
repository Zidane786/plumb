"""scaffold.py: lays the design-system skill into a project (fresh, re-run, subsets, dry run, refusals)."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/plumb"
SCAFFOLD = PLUGIN / "scripts/scaffold.py"
SKILL_REL = ".claude/skills/demo-design-system"

SHARED = [
    "SKILL.md", "design.md",
    "assets/tokens/demo.tokens.json", "assets/icons/icon-map.json", "assets/platforms/README.md",
    "assets/platforms/web/tokens.css.template",
    "references/components.md", "references/inventory.md", "references/ux.md", "references/accessibility.md",
    "references/motion.md", "references/vocabulary.md", "references/dark-mode.md", "references/fidelity.md",
]
SKILL_SRC = PLUGIN / "assets/skill"


def plugin_files(sub: str) -> List[str]:
    """[P] files the plugin ships verbatim: derived from the folder so the test can't go stale."""
    base = SKILL_SRC / sub
    return [p.relative_to(SKILL_SRC).as_posix() for p in base.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]


WEB = ["references/web/stack.md", "references/web/components.md",
       "references/web/ux-guidelines.md", "references/web/dark-mode.md"]
MOBILE = ["references/mobile/README.md", "references/mobile/components.md"]
IOS = ["references/mobile/ios/ios.md", "references/mobile/ios/components.md"]
ANDROID = ["references/mobile/android/android.md", "references/mobile/android/components.md"]


def run(root: Path, *extra: str, platforms: str = "web", name: str = "Demo", skill: str = SKILL_REL,
        styling: str = "tailwind-v4") -> "subprocess.CompletedProcess[str]":
    cmd = [sys.executable, str(SCAFFOLD), "--project-root", str(root), "--name", name, "--skill-dir", skill,
           "--platforms", platforms, "--styling", styling, *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def tree(root: Path) -> List[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def skill_files(root: Path, skill: str = SKILL_REL) -> List[str]:
    base = root / skill
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())


def expected(platforms: List[str]) -> List[str]:
    out = list(SHARED) + plugin_files("scripts") + plugin_files("templates")
    if "web" in platforms:
        out += WEB
    if "ios" in platforms or "android" in platforms:
        out += MOBILE
    if "ios" in platforms:
        out += IOS
    if "android" in platforms:
        out += ANDROID
    return sorted(out)


@pytest.mark.parametrize("platforms", [["web"], ["ios"], ["android"], ["web", "ios"], ["ios", "android"],
                                       ["web", "ios", "android"]])
def test_fresh_scaffold_matches_the_tree_for_each_platform_subset(tmp_path: Path, platforms: List[str]) -> None:
    r = run(tmp_path, platforms=",".join(platforms))
    assert r.returncode == 0, r.stderr
    assert skill_files(tmp_path) == expected(platforms)
    assert (tmp_path / "PLUMB.md").is_file()
    assert (tmp_path / "docs/design/decisions.md").is_file()
    assert (tmp_path / "docs/design/prototype/screens").is_dir()
    for rel in skill_files(tmp_path):
        assert f"wrote: {SKILL_REL}/{rel}" in r.stdout, rel
    assert "wrote: PLUMB.md" in r.stdout


def test_no_unfilled_placeholders_and_no_internal_names(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="web,ios,android").returncode == 0
    for rel in skill_files(tmp_path):
        if rel.startswith("scripts/") or rel.startswith("templates/") or rel.endswith(".template"):
            continue
        text = (tmp_path / SKILL_REL / rel).read_text(encoding="utf-8")
        assert "{{" not in text, rel
        assert "Keel" not in text and "CareDesk" not in text, rel
    assert "{{" not in (tmp_path / "PLUMB.md").read_text(encoding="utf-8")


def test_rerun_keeps_yours_and_refreshes_plugin_files(tmp_path: Path) -> None:
    assert run(tmp_path).returncode == 0
    skill = tmp_path / SKILL_REL
    (skill / "design.md").write_text("MY LOOK\n", encoding="utf-8")
    (skill / "references/ux.md").write_text("MY UX\n", encoding="utf-8")
    (tmp_path / "PLUMB.md").write_text("<!-- plumb v1.0.0 -->\nRole: home\nMine: yes\n", encoding="utf-8")
    (tmp_path / "docs/design/decisions.md").write_text("MY LOG\n", encoding="utf-8")
    (skill / "scripts/audit.py").write_text("# tampered\n", encoding="utf-8")
    (skill / "templates/specimen.html.tmpl").write_text("tampered", encoding="utf-8")
    (skill / "assets/platforms/README.md").write_text("tampered", encoding="utf-8")
    tokens = skill / "assets/tokens/demo.tokens.json"
    tokens_before = tokens.read_bytes()
    r = run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert (skill / "design.md").read_text(encoding="utf-8") == "MY LOOK\n"
    assert (skill / "references/ux.md").read_text(encoding="utf-8") == "MY UX\n"
    assert (tmp_path / "PLUMB.md").read_text(encoding="utf-8").endswith("Mine: yes\n")
    assert (tmp_path / "docs/design/decisions.md").read_text(encoding="utf-8") == "MY LOG\n"
    assert tokens.read_bytes() == tokens_before
    for rel in ("design.md", "references/ux.md"):
        assert f"skip: {SKILL_REL}/{rel} (yours, kept)" in r.stdout
    assert "skip: PLUMB.md (yours, kept)" in r.stdout
    for rel in ("scripts/audit.py", "templates/specimen.html.tmpl", "assets/platforms/README.md"):
        src = (PLUGIN / "assets/skill" / rel).read_bytes()
        assert (skill / rel).read_bytes() == src, rel
        assert f"wrote: {SKILL_REL}/{rel}" in r.stdout


def test_rerun_with_nothing_changed_is_byte_identical(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="web,ios").returncode == 0
    snap = {p: (tmp_path / p).read_bytes() for p in tree(tmp_path)}
    assert run(tmp_path, platforms="web,ios").returncode == 0
    assert {p: (tmp_path / p).read_bytes() for p in tree(tmp_path)} == snap


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    r = run(tmp_path, "--dry-run", platforms="web,ios")
    assert r.returncode == 0, r.stderr
    assert tree(tmp_path) == [] and not list(tmp_path.iterdir())
    assert "would write: PLUMB.md" in r.stdout
    assert f"would write: {SKILL_REL}/SKILL.md" in r.stdout
    assert "wrote:" not in r.stdout


def test_dry_run_on_a_scaffolded_project_changes_nothing(tmp_path: Path) -> None:
    assert run(tmp_path).returncode == 0
    (tmp_path / SKILL_REL / "scripts/audit.py").write_text("# tampered\n", encoding="utf-8")
    before = {p: (tmp_path / p).read_bytes() for p in tree(tmp_path)}
    r = run(tmp_path, "--dry-run")
    assert r.returncode == 0
    assert {p: (tmp_path / p).read_bytes() for p in tree(tmp_path)} == before
    assert f"skip: {SKILL_REL}/design.md (yours, kept)" in r.stdout


def test_plumb_md_has_version_downloads_and_themes(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="web,ios").returncode == 0
    text = (tmp_path / "PLUMB.md").read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("<!-- plumb v1.0.0 ")
    assert re.search(r"^No downloads: .*ask the user and wait", text, re.M)
    assert re.search(r"^Themes: light-and-dark", text, re.M)
    assert re.search(r"^Platforms: web, ios$", text, re.M)
    assert f"Design system: `{SKILL_REL}/`" in text
    template = (PLUGIN / "templates/PLUMB.md").read_text(encoding="utf-8")
    assert template.splitlines()[0].startswith("<!-- plumb v1.0.0 ")
    assert re.search(r"^Themes: ", template, re.M)


def test_plumb_md_is_readable_by_the_shared_parser(tmp_path: Path) -> None:
    assert run(tmp_path).returncode == 0
    sys.path.insert(0, str(PLUGIN / "assets/skill/scripts"))
    try:
        import _plumb as P  # noqa: WPS433
        info = P.read_plumb_md(tmp_path / "PLUMB.md")
    finally:
        sys.path.pop(0)
    assert info["Themes"] == "light-and-dark"
    assert info["Role"] == "home"
    assert info["Python"]
    assert info["Design system"] == f"{SKILL_REL}/"


def test_skill_md_is_lean_and_links_the_references(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="web,ios,android").returncode == 0
    skill = tmp_path / SKILL_REL
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 150
    assert text.startswith("---\nname: demo-design-system\n")
    assert "references/" in text and "design.md" in text
    for needle in ("prototype", "ux.md", "every state", "dark", "download", "ask the user"):
        assert needle.lower() in " ".join(text.split()).lower(), needle
    links = re.findall(r"\]\(([^)#]+)\)", text)
    assert links
    for link in links:
        assert (skill / link).exists(), f"SKILL.md links {link}, which is not scaffolded"


def test_skill_md_only_links_chosen_platform_references(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="ios").returncode == 0
    text = (tmp_path / SKILL_REL / "SKILL.md").read_text(encoding="utf-8")
    assert "references/web/" not in text and "references/mobile/ios/" in text
    assert "references/mobile/android/" not in text
    for link in re.findall(r"\]\(([^)#]+)\)", text):
        assert (tmp_path / SKILL_REL / link).exists(), link


def test_agents_row_text_is_exact() -> None:
    row = (PLUGIN / "templates/agents-row.md").read_text(encoding="utf-8")
    assert "{{SKILL_DIR}}SKILL.md" in row
    one_line = " ".join(row.split())
    for phrase in (
        "Before any UI change, read",
        "UI work is prototype first: update or create the screen with `/plumb:prototype`, "
        "get the user's approval, then build it to match.",
        "Don't install or download anything; if something is missing, ask the user and wait for their decision; "
        "never decide on their behalf",
    ):
        assert phrase in one_line, phrase


def test_decision_entry_and_makefile_snippet() -> None:
    entry = (PLUGIN / "templates/decision-entry.md").read_text(encoding="utf-8")
    assert "DS-YYYYMMDD-" in entry
    for field in ("## DS-", "- Date:", "- Decided by:", "- Options:", "- Chosen:", "- Why:", "- Screens:"):
        assert field in entry, field
    mk = (PLUGIN / "templates/Makefile.snippet").read_text(encoding="utf-8")
    for target in ("tokens:", "tokens-check:", "design-audit:"):
        assert re.search(rf"^{target}", mk, re.M), target
    assert "{{PYTHON}}" in mk and "{{SKILL_DIR}}" in mk
    assert "\t" in mk
    for tool in ("build-tokens.py --check", "audit.py"):
        assert tool in mk


def test_the_copied_build_tokens_runs_on_the_filled_tokens(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="web,ios,android").returncode == 0
    script = tmp_path / SKILL_REL / "scripts/build-tokens.py"
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8",
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    skill = tmp_path / SKILL_REL
    css = (skill / "assets/platforms/web/tokens.css").read_text(encoding="utf-8")
    assert "--color-primary" in css and ".dark" in css
    assert (tmp_path / "docs/design/specimen.html").is_file()
    assert (skill / "assets/platforms/mobile/ios/DemoTheme.swift").is_file()
    assert (skill / "assets/platforms/mobile/android/DemoTheme.kt").is_file()
    check = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True,
                           encoding="utf-8", cwd=str(tmp_path))
    assert check.returncode == 0, check.stdout + check.stderr


@pytest.mark.parametrize("styling,extra", [("tailwind-v4", None), ("tailwind-v3", "tailwind.tokens.js"), ("css", None)])
def test_every_styling_mode_builds(tmp_path: Path, styling: str, extra: Optional[str]) -> None:
    assert run(tmp_path, styling=styling).returncode == 0
    template = tmp_path / SKILL_REL / "assets/platforms/web/tokens.css.template"
    master = PLUGIN / f"assets/skill/assets/platforms/web/tokens.css.template.{styling}"
    assert template.read_bytes() == master.read_bytes()
    script = tmp_path / SKILL_REL / "scripts/build-tokens.py"
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    settings = json.loads((tmp_path / SKILL_REL / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))
    assert settings["$extensions"]["plumb"]["web"]["styling"] == styling
    if extra:
        assert (tmp_path / SKILL_REL / "assets/platforms/web" / extra).is_file()


def test_tokens_file_shape(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="web,ios").returncode == 0
    doc = json.loads((tmp_path / SKILL_REL / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))
    plumb = doc["$extensions"]["plumb"]
    assert plumb["schema"] == 1 and plumb["project"] == "demo" and plumb["platforms"] == ["web", "ios"]
    assert plumb["web"]["styling"] == "tailwind-v4"
    colours = {k: v for k, v in doc["color"].items() if not k.startswith("$")}
    assert colours
    for name, tok in colours.items():
        if name == "link":
            continue
        assert "dark" in tok.get("$extensions", {}).get("plumb", {}), f"{name} has no dark value"
    assert doc["spacing"]["2"]["$value"] == "8px"
    assert doc["spacing"]["4"]["$value"] == "16px"


def test_answers_fill_the_templates(tmp_path: Path) -> None:
    answers = {
        "description": "A planner for busy clinics",
        "audience": "front-desk staff",
        "direction": "Calm clinic",
        "colors": {"light": {"primary": "#1f7a8c"}, "dark": {"primary": "#4fb3c4"}},
        "radius": {"md": "8px"},
        "motion": {"fast": "120ms"},
        "fonts": {"sans": "Inter"},
        "voice": "plain and warm",
        "icons": [{"concept": "home", "lucide": "house", "sfSymbol": "house", "materialSymbol": "home"}],
    }
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(answers), encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    r = run(proj, "--answers", str(path), platforms="web,ios")
    assert r.returncode == 0, r.stderr
    skill = proj / SKILL_REL
    tokens = json.loads((skill / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))
    assert tokens["color"]["primary"]["$value"] == "#1f7a8c"
    assert tokens["color"]["primary"]["$extensions"]["plumb"]["dark"] == "#4fb3c4"
    assert tokens["radius"]["md"]["$value"] == "8px"
    assert tokens["motion"]["duration"]["fast"]["$value"] == "120ms"
    assert tokens["font"]["sans"]["$value"][0] == "Inter"
    design = (skill / "design.md").read_text(encoding="utf-8")
    assert "A planner for busy clinics" in design and "Calm clinic" in design and "#1f7a8c" in design
    assert "front-desk staff" in (skill / "references/ux.md").read_text(encoding="utf-8")
    assert "plain and warm" in (skill / "references/vocabulary.md").read_text(encoding="utf-8")
    icons = json.loads((skill / "assets/icons/icon-map.json").read_text(encoding="utf-8"))
    assert icons["icons"][0]["concept"] == "home"
    assert "Calm clinic" in (proj / "PLUMB.md").read_text(encoding="utf-8")
    build = subprocess.run([sys.executable, str(skill / "scripts/build-tokens.py")], capture_output=True,
                           text=True, encoding="utf-8")
    assert build.returncode == 0, build.stdout + build.stderr


def test_light_only_answer_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"themes": "light-only"}), encoding="utf-8")
    proj = tmp_path / "p"
    proj.mkdir()
    assert run(proj, "--answers", str(path)).returncode == 0
    assert re.search(r"^Themes: light-only", (proj / "PLUMB.md").read_text(encoding="utf-8"), re.M)


def test_unicode_project_name(tmp_path: Path) -> None:
    name = "Café Ünïcode ☕"
    r = run(tmp_path, name=name, skill=".claude/skills/cafe-unicode-design-system", platforms="web,ios")
    assert r.returncode == 0, r.stderr
    skill = tmp_path / ".claude/skills/cafe-unicode-design-system"
    assert "Café Ünïcode ☕" in (skill / "design.md").read_text(encoding="utf-8")
    assert "Café Ünïcode ☕" in (tmp_path / "PLUMB.md").read_text(encoding="utf-8")
    assert "name: cafe-unicode-design-system" in (skill / "SKILL.md").read_text(encoding="utf-8")
    doc = json.loads((skill / "assets/tokens/cafe-unicode.tokens.json").read_text(encoding="utf-8"))
    assert doc["$extensions"]["plumb"]["project"] == "cafe-unicode"
    build = subprocess.run([sys.executable, str(skill / "scripts/build-tokens.py")], capture_output=True,
                           text=True, encoding="utf-8")
    assert build.returncode == 0, build.stdout + build.stderr
    assert (skill / "assets/platforms/mobile/ios/CafeUnicodeTheme.swift").is_file()


def test_unicode_path_in_the_project_root(tmp_path: Path) -> None:
    root = tmp_path / "Ünï proj"
    root.mkdir()
    r = run(root)
    assert r.returncode == 0, r.stderr
    assert (root / SKILL_REL / "SKILL.md").is_file()


def test_windows_style_paths(tmp_path: Path) -> None:
    r = run(tmp_path, "--docs-dir", "docs\\design", skill=".claude\\skills\\demo-design-system")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / SKILL_REL / "SKILL.md").is_file()
    assert (tmp_path / "docs/design/decisions.md").is_file()
    assert "wrote: " + SKILL_REL + "/SKILL.md" in r.stdout
    assert "\\" not in r.stdout
    assert f"Design system: `{SKILL_REL}/`" in (tmp_path / "PLUMB.md").read_text(encoding="utf-8")


def test_custom_docs_dir(tmp_path: Path) -> None:
    assert run(tmp_path, "--docs-dir", "design-docs").returncode == 0
    assert (tmp_path / "design-docs/decisions.md").is_file()
    assert (tmp_path / "design-docs/prototype/screens").is_dir()
    doc = json.loads((tmp_path / SKILL_REL / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))
    assert doc["$extensions"]["plumb"]["docs_dir"] == "design-docs"
    assert "design-docs/prototype.html" in (tmp_path / "PLUMB.md").read_text(encoding="utf-8")


def test_files_are_utf8_with_lf(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="web,ios,android", name="Café").returncode == 0
    for rel in tree(tmp_path):
        data = (tmp_path / rel).read_bytes()
        assert b"\r" not in data, rel
        data.decode("utf-8")


@pytest.mark.parametrize("args,needle", [
    (["--platforms", "web,windows"], "platform"),
    (["--platforms", ""], "platform"),
    (["--styling", "sass"], "styling"),
])
def test_bad_choices_are_refused_with_a_fix(tmp_path: Path, args: List[str], needle: str) -> None:
    cmd = [sys.executable, str(SCAFFOLD), "--project-root", str(tmp_path), "--name", "Demo", "--skill-dir", SKILL_REL,
           "--platforms", "web", "--styling", "tailwind-v4"]
    for i in range(0, len(args), 2):
        cmd[cmd.index(args[i]) + 1] = args[i + 1]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2
    assert r.stderr.startswith("error: ") and "fix: " in r.stderr and needle in r.stderr
    assert "Traceback" not in r.stderr
    assert tree(tmp_path) == []


def test_missing_project_root_is_refused(tmp_path: Path) -> None:
    r = run(tmp_path / "nope")
    assert r.returncode == 2 and "error: " in r.stderr and "fix: " in r.stderr


def test_skill_dir_outside_the_project_is_refused(tmp_path: Path) -> None:
    for bad in ("../elsewhere/x-design-system", "/abs/elsewhere", "C:\\Users\\me\\x-design-system", ""):
        r = run(tmp_path, skill=bad)
        assert r.returncode == 2, bad
        assert "error: " in r.stderr and "fix: " in r.stderr
        assert "Traceback" not in r.stderr
    assert tree(tmp_path) == []


def test_empty_name_is_refused(tmp_path: Path) -> None:
    r = run(tmp_path, name="   ")
    assert r.returncode == 2 and "error: " in r.stderr and "fix: " in r.stderr


def test_name_without_letters_or_digits_is_refused(tmp_path: Path) -> None:
    r = run(tmp_path, name="☕☕")
    assert r.returncode == 2 and "fix: " in r.stderr


@pytest.mark.parametrize("content,needle", [
    ("{not json", "answers"),
    ("[1, 2]", "answers"),
    ('{"colors": {"light": {"primary": "teal"}}}', "primary"),
    ('{"colors": "blue"}', "colors"),
    ('{"themes": "sepia"}', "themes"),
    ('{"icons": [{"concept": "home"}]}', "icons"),
])
def test_bad_answers_are_refused_before_anything_is_written(tmp_path: Path, content: str, needle: str) -> None:
    path = tmp_path / "a.json"
    path.write_text(content, encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    r = run(proj, "--answers", str(path))
    assert r.returncode == 2, r.stdout
    assert r.stderr.startswith("error: ") and "fix: " in r.stderr and needle in r.stderr
    assert tree(proj) == []


def test_missing_answers_file_is_refused(tmp_path: Path) -> None:
    r = run(tmp_path, "--answers", str(tmp_path / "missing.json"))
    assert r.returncode == 2 and "error: " in r.stderr and "fix: " in r.stderr


def test_a_blocking_file_is_reported_not_a_traceback(tmp_path: Path) -> None:
    (tmp_path / ".claude").write_text("not a folder", encoding="utf-8")
    r = run(tmp_path)
    assert r.returncode == 2 and "error: " in r.stderr and "fix: " in r.stderr
    assert "Traceback" not in r.stderr


def test_default_palette_passes_contrast_in_both_themes(tmp_path: Path) -> None:
    assert run(tmp_path).returncode == 0
    script = tmp_path / SKILL_REL / "scripts/build-tokens.py"
    r = subprocess.run([sys.executable, str(script), "--contrast"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    text = (tmp_path / SKILL_REL / "references/dark-mode.md").read_text(encoding="utf-8")
    block = text.split("<!-- plumb:contrast:start -->")[1].split("<!-- plumb:contrast:end -->")[0]
    assert block.strip()
    assert not [l for l in block.splitlines() if l.startswith("|") and l.rstrip().endswith("| fail |")], block


def test_an_existing_tokens_file_under_another_name_is_kept_and_not_duplicated(tmp_path: Path) -> None:
    tokens = tmp_path / SKILL_REL / "assets/tokens"
    tokens.mkdir(parents=True)
    (tokens / "other.tokens.json").write_text("{}\n", encoding="utf-8")
    r = run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in tokens.iterdir()) == ["other.tokens.json"]
    assert f"skip: {SKILL_REL}/assets/tokens/other.tokens.json (yours, kept)" in r.stdout


# ---------------------------------------------------------------- UI files: stack-aware default

WEB_DEFAULT = "app/**, src/**, components/** · *.tsx *.jsx *.vue *.svelte *.css"
ANGULAR = ("src/** · *.component.ts *.component.html *.component.scss *.component.css *.routes.ts *routing.module.ts "
           "styles.scss styles.css")


def ui_files_line(root: Path) -> str:
    m = re.search(r"^UI files: (.*)$", (root / "PLUMB.md").read_text(encoding="utf-8"), re.M)
    assert m
    return m.group(1).strip()


def angular_app(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(json.dumps({"name": "notes", "dependencies": {"@angular/core": "18"}}),
                                       encoding="utf-8")
    comp = root / "src/app/notes"
    comp.mkdir(parents=True)
    for name in ("notes.component.ts", "notes.component.html", "notes.component.scss"):
        (comp / name).write_text("x\n", encoding="utf-8")


def test_angular_project_gets_component_ui_files_by_default(tmp_path: Path) -> None:
    angular_app(tmp_path)
    r = run(tmp_path, styling="css")
    assert r.returncode == 0, r.stderr
    assert ui_files_line(tmp_path) == ANGULAR
    assert f"note: UI files from the detected stack: {ANGULAR}" in r.stderr
    assert "ui_files" in r.stderr  # how to change it


def test_angular_with_ios_chosen_but_no_ios_folder_keeps_swift(tmp_path: Path) -> None:
    angular_app(tmp_path)
    assert run(tmp_path, platforms="web,ios", styling="css").returncode == 0
    assert ui_files_line(tmp_path) == ANGULAR + " *.swift"


def test_web_and_ios_side_by_side_get_the_ios_folder(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}),
                                           encoding="utf-8")
    (tmp_path / "ios/App.xcodeproj").mkdir(parents=True)
    (tmp_path / "ios/App.xcodeproj/project.pbxproj").write_text("", encoding="utf-8")
    (tmp_path / "ios/App").mkdir()
    (tmp_path / "ios/App/ContentView.swift").write_text("import SwiftUI\n", encoding="utf-8")
    assert run(tmp_path, platforms="web,ios").returncode == 0
    assert ui_files_line(tmp_path) == "app/**, src/**, components/**, ios/** · *.tsx *.jsx *.vue *.svelte *.css *.swift"
    # web chosen alone: the iOS package is left out, so the platform default fits again
    other = tmp_path / "web-only"
    shutil.copytree(str(tmp_path / "ios"), str(other / "ios"))
    shutil.copy(str(tmp_path / "package.json"), str(other / "package.json"))
    assert run(other).returncode == 0
    assert ui_files_line(other) == WEB_DEFAULT


def test_failed_detection_falls_back_with_a_note(tmp_path: Path, monkeypatch, capsys) -> None:
    spec = importlib.util.spec_from_file_location("plumb_scaffold_for_test", SCAFFOLD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    broken = tmp_path / "detect.py"
    broken.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    monkeypatch.setattr(mod, "DETECT", broken)
    assert mod.detected_ui_files(tmp_path, ["web"]) is None
    err = capsys.readouterr().err
    assert "note: UI files: the platform default (detecting the stack failed: " in err and "boom" in err


def test_ui_files_answer_wins_over_the_detected_stack(tmp_path: Path) -> None:
    angular_app(tmp_path / "p")
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"ui_files": "src/** · *.ts *.html *.scss"}), encoding="utf-8")
    assert run(tmp_path / "p", "--answers", str(path), styling="css").returncode == 0
    assert ui_files_line(tmp_path / "p") == "src/** · *.ts *.html *.scss"


@pytest.mark.parametrize("deps", [{"next": "15", "react": "19"}, {"react": "18"}, {"vue": "3"}, {"svelte": "5"}, None])
def test_other_stacks_keep_the_platform_default(tmp_path: Path, deps: Optional[dict]) -> None:
    if deps is not None:
        (tmp_path / "package.json").write_text(json.dumps({"dependencies": deps}), encoding="utf-8")
    assert run(tmp_path).returncode == 0
    assert ui_files_line(tmp_path) == WEB_DEFAULT


def test_mobile_defaults_are_unchanged(tmp_path: Path) -> None:
    assert run(tmp_path, platforms="ios").returncode == 0
    assert ui_files_line(tmp_path) == "*.swift"
    other = tmp_path / "droid"
    other.mkdir()
    assert run(other, platforms="web,android").returncode == 0
    assert ui_files_line(other) == WEB_DEFAULT + " · *.kt"
