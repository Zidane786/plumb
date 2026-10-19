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


def raw(root: Path, *extra: str, platforms: str = "web", name: str = "Demo", skill: str = SKILL_REL,
        styling: str = "tailwind-v4") -> "subprocess.CompletedProcess[str]":
    """scaffold.py exactly as given (no confirm token added)."""
    cmd = [sys.executable, str(SCAFFOLD), "--project-root", str(root), "--name", name, "--skill-dir", skill,
           "--platforms", platforms, "--styling", styling, *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


CONFIRM_LINE = re.compile(r"^confirm: .* plus --confirm ([0-9a-f]{12})$", re.M)


def token_of(dry: "subprocess.CompletedProcess[str]") -> Optional[str]:
    m = CONFIRM_LINE.search(dry.stdout)
    return m.group(1) if m else None


def run(root: Path, *extra: str, **kw) -> "subprocess.CompletedProcess[str]":
    """scaffold.py as the skills run it: a real run is the dry run's command plus the token the dry run printed (the
    user's OK on the list is taken as given here). A dry run, or a dry run that fails, is returned as is."""
    if "--dry-run" in extra or "--confirm" in extra:
        return raw(root, *extra, **kw)
    dry = raw(root, *extra, "--dry-run", **kw)
    token = token_of(dry)
    if dry.returncode != 0 or token is None:
        return dry
    return raw(root, *extra, "--confirm", token, **kw)


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
    # no font answer: the system stack once, no repeated head family
    assert doc["font"]["sans"]["$value"] == ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"]
    assert doc["font"]["mono"]["$value"] == ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"]


@pytest.mark.parametrize("sans, stack", [
    ("Inter", ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"]),
    ("segoe ui", ["segoe ui", "system-ui", "-apple-system", "Roboto", "sans-serif"]),
    ("System-UI", ["System-UI", "-apple-system", "Segoe UI", "Roboto", "sans-serif"]),
])
def test_a_font_answer_is_never_repeated_in_its_stack(tmp_path: Path, sans: str, stack: List[str]) -> None:
    path = tmp_path / "answers.json"
    path.write_text(json.dumps({"fonts": {"sans": sans}}), encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    r = run(proj, "--answers", str(path))
    assert r.returncode == 0, r.stderr
    doc = json.loads((proj / SKILL_REL / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))
    assert doc["font"]["sans"]["$value"] == stack


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
    plumb_md = (tmp_path / "PLUMB.md").read_text(encoding="utf-8")
    assert "Main: design-docs/prototype.html · app: design-docs/app.html · screens: design-docs/screens.html" in plumb_md


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


# ---------------------------------------------------------------- one project id for detect.py and scaffold.py


def _detect():
    spec = importlib.util.spec_from_file_location("detect_for_id_test", PLUGIN / "scripts/detect.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_detect_and_scaffold_agree_on_the_project_id(tmp_path: Path) -> None:
    root = tmp_path / "front-desk-app"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"name": "frontdesk", "dependencies": {"next": "15"}}),
                                       encoding="utf-8")
    proposal = _detect().detect(root)["proposal"]
    assert proposal["project"] == "frontdesk"
    assert proposal["skill_dir"] == ".claude/skills/frontdesk-design-system"
    r = run(root, name="Front Desk", skill=proposal["skill_dir"])  # the display name differs from the package name
    assert r.returncode == 0, r.stderr
    skill = root / proposal["skill_dir"]
    tokens = json.loads((skill / "assets/tokens/frontdesk.tokens.json").read_text(encoding="utf-8"))
    assert tokens["$extensions"]["plumb"]["project"] == "frontdesk"
    assert not list((skill / "assets/tokens").glob("front-desk*"))
    assert "Front Desk" in (root / "PLUMB.md").read_text(encoding="utf-8")


def test_a_skill_folder_not_named_after_the_project_falls_back_to_the_same_rule(tmp_path: Path) -> None:
    root = tmp_path / "Some Folder"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"name": "@acme/front-desk"}), encoding="utf-8")
    assert _detect().project_id(root, "design/system") == "front-desk" == _detect().project_name(root)
    assert run(root, name="Front Desk", skill="design/system").returncode == 0
    assert (root / "design/system/assets/tokens/front-desk.tokens.json").is_file()
    bare = tmp_path / "Bare App"
    bare.mkdir()
    assert _detect().project_id(bare) == "bare-app"


def test_theme_switch_and_reduced_motion_answers_reach_the_tokens(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"theme_switch": "class", "reduced_motion": "keep-fades"}), encoding="utf-8")
    proj = tmp_path / "p"
    proj.mkdir()
    assert run(proj, "--answers", str(path)).returncode == 0
    doc = json.loads((proj / SKILL_REL / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))
    assert doc["$extensions"]["plumb"]["web"]["theme_switch"] == "class"
    assert doc["$extensions"]["plumb"]["motion"] == {"reduced": "keep-fades"}
    path.write_text(json.dumps({"reduced_motion": "fades"}), encoding="utf-8")
    other = tmp_path / "q"
    other.mkdir()
    r = run(other, "--answers", str(path))
    assert r.returncode == 2 and r.stderr.startswith("error:") and "keep-fades" in r.stderr


def test_a_data_theme_answer_reaches_the_tokens(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"theme_switch": "data-theme"}), encoding="utf-8")
    proj = tmp_path / "p"
    proj.mkdir()
    assert run(proj, "--answers", str(path)).returncode == 0
    doc = json.loads((proj / SKILL_REL / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))
    assert doc["$extensions"]["plumb"]["web"]["theme_switch"] == "data-theme"


def test_an_existing_stylesheet_copy_gets_a_note_before_the_build(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app/globals.css").write_text('@import "tailwindcss";\nbody { margin: 0; }\n', encoding="utf-8")
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"web_copies": ["app/globals.css"]}), encoding="utf-8")
    r = run(tmp_path, "--answers", str(path), "--dry-run")
    assert r.returncode == 0
    assert "note: app/globals.css already exists with your own CSS" in r.stdout and "would add Plumb's block" in r.stdout
    assert (tmp_path / "app/globals.css").read_text(encoding="utf-8").startswith('@import "tailwindcss";\nbody')


# ---------------------------------------------------------------- token names in the references (live test 2, B15)


TOKEN_PATH = re.compile(r"`((?:color|typography|radius|shadow|spacing|motion|font)\.[\w.-]+)`")


def _named_tokens(root: Path) -> List[str]:
    found = []
    for rel in ("references/components.md", "design.md"):
        found += TOKEN_PATH.findall((root / SKILL_REL / rel).read_text(encoding="utf-8"))
    return found


def _has(doc: dict, path: str) -> bool:
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, dict) and "$value" in node


def test_references_name_only_tokens_the_project_has(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert run(fresh).returncode == 0
    doc = json.loads((fresh / SKILL_REL / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))
    names = _named_tokens(fresh)
    assert "shadow.card" in names and "typography.h3" in names
    assert all(_has(doc, n) for n in names), [n for n in names if not _has(doc, n)]
    # a project whose tokens were recorded from the app (no h3, no shadows, a radius scale of its own)
    kept = tmp_path / "kept"
    tokens = kept / SKILL_REL / "assets/tokens/demo.tokens.json"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(json.dumps({
        "color": {"$type": "color", "primary": {"$value": "#14857f"}},
        "typography": {"$type": "typography", "body": {"$value": {"fontSize": "14px", "lineHeight": "20px"}},
                       "h2": {"$value": {"fontSize": "20px", "lineHeight": "28px"}}},
        "radius": {"$type": "dimension", "sm": {"$value": "4px"}},
    }), encoding="utf-8")
    assert run(kept).returncode == 0
    doc = json.loads(tokens.read_text(encoding="utf-8"))
    names = _named_tokens(kept)
    assert all(_has(doc, n) for n in names), [n for n in names if not _has(doc, n)]
    comps = (kept / SKILL_REL / "references/components.md").read_text(encoding="utf-8")
    assert "Title (`typography.h2`)" in comps and "Radius `radius.sm`. Text `typography.body`." in comps
    assert "`<a card shadow: no such token yet, add one with /plumb:update>` only when it lifts" in comps
    design = (kept / SKILL_REL / "design.md").read_text(encoding="utf-8")
    assert "Elevation: `<the elevation steps: no such token yet, add one with /plumb:update>`" in design


# ---------------------------------------------------------------- the confirm gate (live test 2, B4)


def test_a_real_run_without_the_dry_runs_token_writes_nothing(tmp_path: Path) -> None:
    r = raw(tmp_path)
    assert r.returncode == 2 and tree(tmp_path) == []
    assert r.stderr.startswith("error: the scaffold writes into the project only after the user approved the dry-run list")
    assert "\nask the user: show them the file list from the same command with --dry-run" in r.stderr
    assert "plus --confirm <token> exactly as the dry run printed it" in r.stderr
    assert not re.search(r"[0-9a-f]{12}", r.stderr)  # the refusal never hands out the token


def test_the_dry_run_prints_a_token_that_fits_only_that_list(tmp_path: Path) -> None:
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"direction": "Calm"}), encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    dry = raw(root, "--answers", str(answers), "--dry-run")
    token = token_of(dry)
    assert dry.returncode == 0 and token and tree(root) == []
    assert dry.stdout.rstrip().endswith(f"after their OK run the same command without --dry-run, plus --confirm {token}")
    assert token_of(raw(root, "--answers", str(answers), "--dry-run")) == token  # the same list: the same token
    # another answer, another argument, another project, or a file that appeared since: the token no longer fits
    answers.write_text(json.dumps({"direction": "Bold"}), encoding="utf-8")
    r = raw(root, "--answers", str(answers), "--confirm", token)
    assert r.returncode == 2 and f"error: --confirm {token} does not fit this command" in r.stderr
    assert "ask the user: " in r.stderr and tree(root) == []
    answers.write_text(json.dumps({"direction": "Calm"}), encoding="utf-8")
    assert raw(root, "--answers", str(answers), "--confirm", token, platforms="web,ios").returncode == 2
    other = tmp_path / "other"
    other.mkdir()
    assert raw(other, "--answers", str(answers), "--confirm", token).returncode == 2
    (root / "PLUMB.md").write_text("mine\n", encoding="utf-8")
    assert raw(root, "--answers", str(answers), "--confirm", token).returncode == 2
    (root / "PLUMB.md").unlink()
    r = raw(root, "--answers", str(answers), "--confirm", token)
    assert r.returncode == 0, r.stderr
    assert "wrote: PLUMB.md" in r.stdout


# ---------------------------------------------------------------- Allowed raw values default and --verify


def _app(root: Path, pkg: str, aliases_ui: Optional[str] = "@/components/ui", paths: Optional[dict] = None,
         ui_dir: Optional[str] = "src/components/ui") -> None:
    """A Next.js UI package in `pkg` ('.' = the repo root) with a shadcn components.json and a tsconfig."""
    base = root if pkg == "." else root / pkg
    base.mkdir(parents=True, exist_ok=True)
    (base / "package.json").write_text(json.dumps({"name": "x", "dependencies": {"next": "15", "react": "19"}}),
                                       encoding="utf-8")
    if aliases_ui:
        (base / "components.json").write_text(json.dumps({"aliases": {"ui": aliases_ui}}), encoding="utf-8")
    if paths is not None:  # tsconfig is JSON with comments
        (base / "tsconfig.json").write_text("// comment\n" + json.dumps({"compilerOptions": {"paths": paths}}) + "\n",
                                            encoding="utf-8")
    if ui_dir:
        (base / ui_dir).mkdir(parents=True, exist_ok=True)
        (base / ui_dir / "button.tsx").write_text("export const B = () => null\n", encoding="utf-8")


def allowed_line(root: Path) -> str:
    return re.search(r"^Allowed raw values: (.*)$", (root / "PLUMB.md").read_text(encoding="utf-8"), re.M).group(1).strip()


@pytest.mark.parametrize("pkg", ["web", "client-app"])
def test_allowed_raw_default_follows_the_ui_package_folder(tmp_path: Path, pkg: str) -> None:
    _app(tmp_path, pkg, paths={"@/*": ["./src/*"]})
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == f"{pkg}/src/components/ui/**"


def test_allowed_raw_default_single_package_repo_and_tsconfig_without_src(tmp_path: Path) -> None:
    _app(tmp_path, ".", paths={"@/*": ["./*"]}, ui_dir="components/ui")
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "components/ui/**"
    other = tmp_path / "second"
    _app(other, "ui", aliases_ui="@/lib/primitives", paths={"@/*": ["./app/*"]}, ui_dir="app/lib/primitives")
    assert run(other).returncode == 0
    assert allowed_line(other) == "ui/app/lib/primitives/**"


def test_allowed_raw_default_without_tsconfig_reads_at_as_src(tmp_path: Path) -> None:
    _app(tmp_path, "site")
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "site/src/components/ui/**"


def test_allowed_raw_default_without_components_json_uses_the_folder_that_exists(tmp_path: Path) -> None:
    _app(tmp_path, "web", aliases_ui=None, ui_dir="components/ui")
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "web/components/ui/**"


def test_allowed_raw_default_keeps_the_old_value_with_no_package_and_none_without_web(tmp_path: Path) -> None:
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "components/ui/**"
    ios = tmp_path / "ios-only"
    ios.mkdir()
    assert run(ios, platforms="ios").returncode == 0
    assert allowed_line(ios) == "none"


def test_the_answer_wins_over_the_derived_default(tmp_path: Path) -> None:
    _app(tmp_path, "web", paths={"@/*": ["./src/*"]})
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"allowed_raw": "lib/primitives/**"}), encoding="utf-8")
    assert run(tmp_path, "--answers", str(path)).returncode == 0
    assert allowed_line(tmp_path) == "lib/primitives/**"


def _verify(root: Path) -> "subprocess.CompletedProcess[str]":
    return subprocess.run([sys.executable, str(SCAFFOLD), "--verify", "--project-root", str(root)],
                          capture_output=True, text=True, encoding="utf-8")


def test_verify_is_quiet_when_the_allowed_pattern_matches(tmp_path: Path) -> None:
    _app(tmp_path, "web", paths={"@/*": ["./src/*"]})
    assert run(tmp_path).returncode == 0
    r = _verify(tmp_path)
    assert "Allowed raw values" not in r.stdout and "warning:" not in r.stdout, r.stdout


def test_verify_warns_when_the_allowed_pattern_matches_nothing(tmp_path: Path) -> None:
    _app(tmp_path, "web", paths={"@/*": ["./src/*"]})
    assert run(tmp_path).returncode == 0
    plumb = tmp_path / "PLUMB.md"
    plumb.write_text(plumb.read_text(encoding="utf-8").replace("web/src/components/ui/**", "frontend/src/ui/**"),
                     encoding="utf-8")
    r = _verify(tmp_path)
    assert "warning: PLUMB.md Allowed raw values: frontend/src/ui/** matches 0 files" in r.stdout, r.stdout
    assert "fix: ask the user: correct Allowed raw values:" in r.stdout
    assert "problem: PLUMB.md Allowed raw values" not in r.stdout


def test_verify_accepts_none_for_allowed_raw_values(tmp_path: Path) -> None:
    _app(tmp_path, "web", paths={"@/*": ["./src/*"]})
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"allowed_raw": "none"}), encoding="utf-8")
    assert run(tmp_path, "--answers", str(path)).returncode == 0
    assert "Allowed raw values" not in _verify(tmp_path).stdout


def test_allowed_raw_default_follows_a_tsconfig_extends(tmp_path: Path) -> None:
    _app(tmp_path, "web", ui_dir="components/ui")  # the alias would guess src/ without the base config
    base = tmp_path / "web"
    (base / "tsconfig.base.json").write_text(json.dumps({"compilerOptions": {"paths": {"@/*": ["./*"]}}}),
                                             encoding="utf-8")
    (base / "tsconfig.json").write_text('{"extends": "./tsconfig.base", "compilerOptions": {}}', encoding="utf-8")
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "web/components/ui/**"


def test_allowed_raw_default_survives_an_extends_cycle_and_a_missing_base(tmp_path: Path) -> None:
    _app(tmp_path, "web")
    (tmp_path / "web/tsconfig.json").write_text('{"extends": "./tsconfig.json"}', encoding="utf-8")
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "web/src/components/ui/**"
    other = tmp_path / "b"
    _app(other, "web")
    (other / "web/tsconfig.json").write_text('{"extends": "./nope.json"}', encoding="utf-8")
    assert run(other).returncode == 0
    assert allowed_line(other) == "web/src/components/ui/**"


def test_allowed_raw_default_reads_jsconfig_with_comments_and_trailing_commas(tmp_path: Path) -> None:
    _app(tmp_path, "site", ui_dir="components/ui")
    (tmp_path / "site/jsconfig.json").write_text(
        '{\n  // aliases\n  "compilerOptions": {\n    /* root */\n    "paths": { "@/*": ["./*",], },\n  },\n}\n',
        encoding="utf-8")
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "site/components/ui/**"


def test_allowed_raw_default_prefers_an_existing_folder_over_a_wrong_alias_guess(tmp_path: Path) -> None:
    _app(tmp_path, "web", ui_dir="components/ui")  # no tsconfig: "@/" would mean src/, which does not exist
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "web/components/ui/**"


def test_allowed_raw_default_lists_every_web_package(tmp_path: Path) -> None:
    _app(tmp_path, "admin", paths={"@/*": ["./src/*"]})
    _app(tmp_path, "portal", paths={"@/*": ["./*"]}, ui_dir="components/ui")
    assert run(tmp_path).returncode == 0
    assert allowed_line(tmp_path) == "admin/src/components/ui/**, portal/components/ui/**"
