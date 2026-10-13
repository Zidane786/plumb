"""scaffold.py --relocate and --verify: move the skill, keep every reference in step, find it again."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import pytest

from test_scaffold import PLUGIN, SCAFFOLD, SKILL_REL, run, tree

NEW = ".github/skills/demo-design-system"


def cli(root: Path, *args: str) -> "subprocess.CompletedProcess[str]":
    return subprocess.run([sys.executable, str(SCAFFOLD), "--project-root", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8")


def project_with_everything(tmp_path: Path, skill: str = SKILL_REL) -> Path:
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"web_copies": ["app/globals.css"]}), encoding="utf-8")
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    assert run(root, "--answers", str(answers), skill=skill).returncode == 0
    row = (PLUGIN / "templates/agents-row.md").read_text(encoding="utf-8").replace("{{SKILL_DIR}}", skill + "/")
    (root / "AGENTS.md").write_text(
        "# Agents\n\n| Task | File | Rule |\n|---|---|---|\n| Backend | `api/README.md` | "
        f"mentions {skill}/ only in prose |\n{row}", encoding="utf-8")
    snippet = (PLUGIN / "templates/Makefile.snippet").read_text(encoding="utf-8")
    (root / "Makefile").write_text(snippet.replace("{{PYTHON}}", "python3").replace("{{SKILL_DIR}}", skill + "/"),
                                   encoding="utf-8")
    script = root / skill / "scripts/build-tokens.py"
    built = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    return root


def test_relocate_moves_the_skill_and_updates_every_reference(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    r = cli(root, "--relocate", SKILL_REL, NEW)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (root / SKILL_REL).exists() and (root / NEW / "SKILL.md").is_file()
    plumb = (root / "PLUMB.md").read_text(encoding="utf-8")
    assert f"Design system: `{NEW}/`" in plumb and SKILL_REL not in plumb
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert f"`{NEW}/SKILL.md`" in agents
    assert f"mentions {SKILL_REL}/ only in prose" in agents  # only the Plumb row changes
    make = (root / "Makefile").read_text(encoding="utf-8")
    assert NEW in make and SKILL_REL not in make
    assert "moved: " in r.stdout and "updated: PLUMB.md" in r.stdout and "updated: AGENTS.md" in r.stdout
    assert "updated: Makefile" in r.stdout and "check: ok" in r.stdout
    check = subprocess.run([sys.executable, str(root / NEW / "scripts/build-tokens.py"), "--check"],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(root))
    assert check.returncode == 0, check.stdout + check.stderr
    assert cli(root, "--verify").returncode == 0


def test_relocate_dry_run_lists_changes_and_writes_nothing(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    before = {p: (root / p).read_bytes() for p in tree(root)}
    r = cli(root, "--relocate", SKILL_REL, NEW, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert {p: (root / p).read_bytes() for p in tree(root)} == before
    assert not (root / NEW).exists()
    for line in (f"would move: {SKILL_REL} -> {NEW}", "would update: PLUMB.md", "would update: AGENTS.md",
                 "would update: Makefile", "would run: "):
        assert line in r.stdout, line


def test_relocate_accepts_windows_style_paths(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    r = cli(root, "--relocate", SKILL_REL.replace("/", "\\"), NEW.replace("/", "\\"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (root / NEW / "SKILL.md").is_file()


def test_relocate_refuses_a_non_empty_target(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    (root / NEW).mkdir(parents=True)
    (root / NEW / "x.txt").write_text("x", encoding="utf-8")
    r = cli(root, "--relocate", SKILL_REL, NEW)
    assert r.returncode == 2 and r.stderr.startswith("error: ") and "fix: " in r.stderr and "not empty" in r.stderr
    assert (root / SKILL_REL / "SKILL.md").is_file()


def test_relocate_allows_an_empty_existing_target(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    (root / NEW).mkdir(parents=True)
    assert cli(root, "--relocate", SKILL_REL, NEW).returncode == 0
    assert (root / NEW / "SKILL.md").is_file()


def test_relocate_refuses_a_folder_that_is_not_a_plumb_skill(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain/SKILL.md").write_text("x", encoding="utf-8")
    r = cli(tmp_path, "--relocate", "plain", "other")
    assert r.returncode == 2 and "not a Plumb design-system skill" in r.stderr and "fix: " in r.stderr
    r = cli(tmp_path, "--relocate", "missing", "other")
    assert r.returncode == 2 and "fix: " in r.stderr


def test_relocate_refuses_a_target_outside_the_project(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    for bad in ("../elsewhere/x-design-system", "/abs/elsewhere", "C:\\Users\\me\\x"):
        r = cli(root, "--relocate", SKILL_REL, bad)
        assert r.returncode == 2, bad
        assert "error: " in r.stderr and "fix: " in r.stderr and "Traceback" not in r.stderr
    assert (root / SKILL_REL / "SKILL.md").is_file()


def test_relocate_refuses_same_and_nested_targets(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    assert cli(root, "--relocate", SKILL_REL, SKILL_REL).returncode == 2
    assert cli(root, "--relocate", SKILL_REL, SKILL_REL + "/inner").returncode == 2


def test_relocate_cannot_be_combined_with_verify(tmp_path: Path) -> None:
    r = cli(tmp_path, "--relocate", "a", "b", "--verify")
    assert r.returncode == 2 and "fix: " in r.stderr


def test_verify_passes_on_a_healthy_project(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    r = cli(root, "--verify")
    assert r.returncode == 0, r.stdout
    for line in ("ok: PLUMB.md names", "ok: AGENTS.md row points at", "ok: Makefile line points at",
                 "ok: web copy app/globals.css resolves", "verify: ok"):
        assert line in r.stdout, line


def test_verify_finds_a_skill_elsewhere_and_suggests_relocate(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    (root / ".github/skills").mkdir(parents=True)
    (root / SKILL_REL).rename(root / NEW)
    r = cli(root, "--verify")
    assert r.returncode == 1
    assert f"problem: PLUMB.md names {SKILL_REL}/ but no design-system skill is there" in r.stdout
    assert f"found: a design-system skill at {NEW}" in r.stdout
    assert f"--relocate {NEW} {SKILL_REL}" in r.stdout


def test_verify_reports_stale_agents_makefile_and_copies(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    agents = root / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace(SKILL_REL + "/SKILL.md", "old/SKILL.md"), encoding="utf-8")
    make = root / "Makefile"
    make.write_text(make.read_text(encoding="utf-8").replace(SKILL_REL, "old"), encoding="utf-8")
    (root / "app/globals.css").unlink()
    (root / "app").rmdir()
    r = cli(root, "--verify")
    assert r.returncode == 1
    assert "problem: the Plumb row in AGENTS.md does not name" in r.stdout
    assert "problem: Makefile line" in r.stdout
    assert "problem: web copy app/globals.css: its folder does not exist" in r.stdout


def test_verify_without_plumb_md(tmp_path: Path) -> None:
    r = cli(tmp_path, "--verify")
    assert r.returncode == 1 and "problem: no PLUMB.md" in r.stdout and "fix: " in r.stdout



MAKE_TARGET = re.compile(r"\bmake (tokens|tokens-check|design-audit)\b")
COMMANDS = re.compile(r"^## Commands\n(.*?)(?=^## )", re.M | re.S)


def add_make_hints(root: Path) -> None:
    """What /plumb:init's wire-in does when the user says yes to the Makefile: name the targets in PLUMB.md."""
    plumb = root / "PLUMB.md"
    text = plumb.read_text(encoding="utf-8")
    text = re.sub(r"(scripts/build-tokens\.py`)\n", r"\1 (make tokens)\n", text, count=1)
    text = text.replace("--check` ·", "--check` (make tokens-check) ·", 1)
    text = re.sub(r"(scripts/audit\.py`)\n", r"\1 (make design-audit)\n", text, count=1)
    plumb.write_text(text, encoding="utf-8")


def load_scaffold():
    import importlib.util
    spec = importlib.util.spec_from_file_location("plumb_scaffold", SCAFFOLD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_a_fresh_scaffold_names_the_direct_commands_and_passes_verify(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    assert run(root).returncode == 0
    commands = COMMANDS.search((root / "PLUMB.md").read_text(encoding="utf-8")).group(1)
    py = "python" if os.name == "nt" else "python3"  # scaffold's default when init names no interpreter
    assert f"{py} {SKILL_REL}/scripts/build-tokens.py`" in commands
    assert f"{py} {SKILL_REL}/scripts/build-tokens.py --check`" in commands
    assert f"{py} {SKILL_REL}/scripts/audit.py`" in commands
    assert "make" not in commands
    r = cli(root, "--verify")
    assert r.returncode == 0, r.stdout
    assert "note: no Plumb targets in a Makefile (/plumb:init step 4 asks the user whether to add them)" in r.stdout


def test_generated_skill_files_name_no_make_targets(tmp_path: Path) -> None:
    # A project that declined the Makefile must not be told to run `make tokens` by its own design-system skill.
    root = tmp_path / "proj"
    root.mkdir()
    assert run(root, platforms="web,ios,android").returncode == 0
    built = subprocess.run([sys.executable, str(root / SKILL_REL / "scripts/build-tokens.py")], capture_output=True,
                           text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    hits = []
    for path in sorted((root / SKILL_REL).rglob("*")) + [root / "PLUMB.md"]:
        if path.is_file() and path.suffix in (".md", ".css", ".json", ".swift", ".kt", ".html", ".template"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if MAKE_TARGET.search(line):
                    hits.append(f"{path.relative_to(root)}:{n}: {line.strip()[:90]}")
    assert not hits, "make targets named without a Makefile:\n" + "\n".join(hits)


def test_verify_passes_in_a_linked_repo(tmp_path: Path) -> None:
    home = project_with_everything(tmp_path)
    api = tmp_path / "api"
    api.mkdir()
    linked = (PLUGIN / "templates/PLUMB.md").read_text(encoding="utf-8")
    skill = f"../proj/{SKILL_REL}/"
    for slot, value in {"SKILL_DIR": skill, "ROLE": "linked", "PYTHON": "python3", "PROJECT": "api",
                        "ROUTES": "none"}.items():
        linked = linked.replace("{{" + slot + "}}", value)
    (api / "PLUMB.md").write_text(linked, encoding="utf-8")
    r = cli(api, "--verify")
    assert r.returncode == 0, r.stdout
    assert f"ok: PLUMB.md names {skill.rstrip('/')}/ and it is a design-system skill" in r.stdout
    assert "problem: web copy" not in r.stdout  # the home repo owns its copies
    assert home.is_dir()


def test_verify_reports_make_targets_that_do_not_exist(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    add_make_hints(root)
    (root / "Makefile").unlink()
    r = cli(root, "--verify")
    assert r.returncode == 1, r.stdout
    assert "problem: PLUMB.md names `make tokens`, `make tokens-check`, `make design-audit` but there is no Makefile" in r.stdout
    assert "fix: " in r.stdout and "Makefile.snippet" in r.stdout and "direct commands" in r.stdout


def test_verify_reports_a_make_target_missing_from_the_makefile(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    add_make_hints(root)
    make = root / "Makefile"
    text = make.read_text(encoding="utf-8")
    make.write_text(text.split("# Check the UI code")[0].replace(" design-audit", ""), encoding="utf-8")
    r = cli(root, "--verify")
    assert r.returncode == 1, r.stdout
    assert "problem: PLUMB.md names `make design-audit` but the Makefile has no design-audit target" in r.stdout
    assert "ok: PLUMB.md's make targets" not in r.stdout


def test_verify_notes_a_target_that_may_come_from_an_included_makefile(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    add_make_hints(root)
    make = root / "Makefile"
    text = make.read_text(encoding="utf-8")
    make.write_text("include design.mk\n" + text.split("# Check the UI code")[0].replace(" design-audit", ""),
                    encoding="utf-8")
    r = cli(root, "--verify")
    assert r.returncode == 0, r.stdout
    assert "note: PLUMB.md names `make design-audit`; the Makefile does not define it but includes design.mk" in r.stdout


def test_verify_accepts_make_targets_that_exist(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    add_make_hints(root)
    r = cli(root, "--verify")
    assert r.returncode == 0 and "ok: PLUMB.md's make targets exist in the Makefile" in r.stdout


def test_makefile_parsing(tmp_path: Path) -> None:
    mod = load_scaffold()
    (tmp_path / "Makefile").write_text(
        ".PHONY: tokens design-audit\nVAR := x\nOTHER = y\nX ?= z\ntokens::\n\techo\n"
        "design-audit tokens-check: deps\n\techo a:b\n-include local.mk\nsinclude more.mk\n", encoding="utf-8")
    targets, includes = mod.makefile_targets(tmp_path)
    assert {"tokens", "design-audit", "tokens-check"} <= targets
    assert not {"VAR", "OTHER", "X", "echo", "a"} & targets
    assert includes == ["local.mk", "more.mk"]
    assert mod.makefile_targets(tmp_path / "missing") == (None, [])


def test_check_make_targets_returns_its_lines_and_prints_nothing(tmp_path: Path, capsys) -> None:
    mod = load_scaffold()
    (tmp_path / "Makefile").write_text("tokens:\n\techo\n", encoding="utf-8")
    ok, note, problem = mod.check_make_targets("tokens `x` (make tokens)", tmp_path)
    assert ok == "PLUMB.md's make targets exist in the Makefile" and note is None and problem is None
    assert mod.check_make_targets("no make hints here", tmp_path) == (None, None, None)
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------- a git-ignored skill folder (live test 2, B5)


@pytest.fixture
def hermetic_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No global or system git config from the machine running the tests (a global excludes file that ignores .claude
    would change every result). Returns the empty global config file a test may fill."""
    home = tmp_path / "home"
    home.mkdir()
    config = home / "gitconfig"
    config.write_text("", encoding="utf-8")
    for key, value in (("HOME", str(home)), ("USERPROFILE", str(home)), ("XDG_CONFIG_HOME", str(home / "xdg")),
                       ("GIT_CONFIG_GLOBAL", str(config)), ("GIT_CONFIG_NOSYSTEM", "1"),
                       ("GIT_CEILING_DIRECTORIES", str(tmp_path))):
        monkeypatch.setenv(key, value)
    return config


def _git_repo(root: Path, ignore: Optional[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True, encoding="utf-8")
    if ignore is not None:
        (root / ".gitignore").write_text(ignore, encoding="utf-8")


def _skill_ignored(root: Path) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", "--", f"{SKILL_REL}/SKILL.md"], cwd=str(root),
                       capture_output=True, encoding="utf-8")
    return r.returncode == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="requires git")
def test_a_git_ignored_skill_folder_is_reported_by_the_dry_run_the_scaffold_and_verify(tmp_path: Path,
                                                                                       hermetic_git: Path) -> None:
    """The live test's repo ignored .claude/, so the design-system skill would never have been committed."""
    root = tmp_path / "proj"
    _git_repo(root, "node_modules\n.claude/\n")
    want = (f"{SKILL_REL}/ is git-ignored by .claude/ (.gitignore line 2) — the design system would never be "
            f"committed")
    hint = ('fix: ask the user: un-ignore it (in .gitignore replace the line ".claude/" with ".claude/*" and add '
            '"!.claude/skills/" after it), or choose another location for it')
    dry = run(root, "--dry-run")
    assert dry.returncode == 0 and f"warning: {want}" in dry.stdout and hint in dry.stdout
    real = run(root)
    assert real.returncode == 0 and f"warning: {want}" in real.stdout
    v = cli(root, "--verify")
    assert v.returncode == 1 and f"problem: {want}" in v.stdout and hint in v.stdout
    # the fix the hint names: the skill is committed, verify is quiet about it
    (root / ".gitignore").write_text("node_modules\n.claude/*\n!.claude/skills/\n", encoding="utf-8")
    v = cli(root, "--verify")
    assert "git-ignored" not in v.stdout and v.returncode == 0, v.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="requires git")
def test_an_ignored_plumb_md_or_docs_folder_is_reported_too(tmp_path: Path, hermetic_git: Path) -> None:
    root = tmp_path / "proj"
    _git_repo(root, "PLUMB.md\ndocs/\n")
    out = run(root, "--dry-run").stdout
    assert "warning: PLUMB.md is git-ignored by PLUMB.md (.gitignore line 1)" in out
    assert 'in .gitignore add "!PLUMB.md" after the line "PLUMB.md" (or remove that line)' in out
    assert "warning: docs/design/ is git-ignored by docs/ (.gitignore line 2)" in out
    assert 'replace the line "docs/" with "docs/*" and add "!docs/design/" after it' in out


def test_outside_git_nothing_is_said_about_ignores(tmp_path: Path, hermetic_git: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    (root / ".gitignore").write_text(".claude/\n", encoding="utf-8")
    assert "git-ignored" not in run(root, "--dry-run").stdout


def _apply(root: Path, fix, source_file: Path, use_override: bool = False) -> None:
    """Make exactly the edit the fix describes: replace its line with its lines, or add its lines after it; or, for a
    global excludes file, add the override lines to the repo's .gitignore."""
    if use_override:
        path = root / ".gitignore"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(old + "".join(f"{line}\n" for line in fix.override), encoding="utf-8")
        return
    lines = source_file.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    for line in lines:
        if line == fix.pattern:
            out += fix.lines if fix.replace else [line, *fix.lines]
        else:
            out.append(line)
    source_file.write_text("\n".join(out) + "\n", encoding="utf-8")


# (name, .gitignore, .git/info/exclude, global excludes, the words of the fix)
IGNORE_CASES = [
    ("gitignore-dir", ".claude/\n", None, None,
     'in .gitignore replace the line ".claude/" with ".claude/*" and add "!.claude/skills/" after it'),
    ("gitignore-starstar", ".claude/**\n", None, None,
     'in .gitignore add "!.claude/skills/" and "!.claude/skills/**" after the line ".claude/**"'),
    ("gitignore-star", ".claude/*\n", None, None, 'in .gitignore add "!.claude/skills/" after the line ".claude/*"'),
    ("info-exclude", None, ".claude/\n", None,
     'in .git/info/exclude replace the line ".claude/" with ".claude/*" and add "!.claude/skills/" after it'),
    ("global", None, None, ".claude\n", "in your global git excludes file"),
]


@pytest.mark.skipif(shutil.which("git") is None, reason="requires git")
@pytest.mark.parametrize("name,gitignore,exclude,global_,words", IGNORE_CASES, ids=[c[0] for c in IGNORE_CASES])
def test_the_unignore_fix_names_the_real_source_and_works(tmp_path: Path, hermetic_git: Path, name: str,
                                                         gitignore: Optional[str], exclude: Optional[str],
                                                         global_: Optional[str], words: str) -> None:
    """Review I1: the fix must work for where the pattern really is (a .gitignore, .git/info/exclude or the global
    excludes file) and for the pattern's shape (.claude/, .claude/*, .claude/**): applied as printed, git keeps the
    skill and --verify is quiet."""
    root = tmp_path / "proj"
    _git_repo(root, gitignore)
    source = root / ".gitignore"
    if exclude is not None:
        source = root / ".git" / "info" / "exclude"
        source.write_text(exclude, encoding="utf-8")
    if global_ is not None:
        source = tmp_path / "global-ignore"
        source.write_text(global_, encoding="utf-8")
        hermetic_git.write_text(f"[core]\n\texcludesFile = {source.as_posix()}\n", encoding="utf-8")
    assert run(root).returncode == 0
    assert _skill_ignored(root)
    v = cli(root, "--verify")
    assert v.returncode == 1 and words in v.stdout, v.stdout
    if global_ is not None:
        assert source.as_posix() in v.stdout and "line 1" in v.stdout
        assert "replace the line" not in v.stdout.split("in your global git excludes file", 1)[0]
        assert ('or keep that file and add "!.claude/", ".claude/*" and "!.claude/skills/" to this repo\'s .gitignore'
                in v.stdout)
    mod = load_scaffold()
    found = mod.ignored_by_git(root, SKILL_REL, "docs/design")
    skill = [f for f in found if f.shown == f"{SKILL_REL}/"]
    assert len(skill) == 1
    fix = mod.unignore_fix(skill[0].shown, skill[0].pattern, skill[0].source)
    _apply(root, fix, source)
    assert not _skill_ignored(root), f"{name}: the fix did not un-ignore the skill"
    if global_ is not None:  # the other way: leave the global file alone and override it in the repo
        source.write_text(global_, encoding="utf-8")
        assert _skill_ignored(root)
        _apply(root, fix, source, use_override=True)
        assert not _skill_ignored(root), f"{name}: the repo override did not un-ignore the skill"
    v = cli(root, "--verify")
    assert "git-ignored" not in v.stdout, v.stdout


@pytest.mark.parametrize("line,want", [
    (".gitignore:2:.claude/\t.claude/skills/x/SKILL.md", (".gitignore", "2", ".claude/", ".claude/skills/x/SKILL.md")),
    ("C:/Users/me/.config/git/ignore:1:.claude\t.claude/skills/x/SKILL.md",
     ("C:/Users/me/.config/git/ignore", "1", ".claude", ".claude/skills/x/SKILL.md")),
    (".gitignore:3:a:b\tx", (".gitignore", "3", "a:b", "x")),
    ('.gitignore:1:*.md\t"PLUMB.md"', (".gitignore", "1", "*.md", "PLUMB.md")),
    ("no tab here", None),
])
def test_check_ignore_lines_parse_on_every_platform(line: str, want) -> None:
    assert load_scaffold().parse_check_ignore(line) == want


# ---------------------------------------------------------------- Routes: and UI files: (recorded, checked by --verify)


def _scaffold_with(tmp_path: Path, answers: dict, platforms: str = "web") -> "tuple[Path, subprocess.CompletedProcess]":
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(answers), encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    return root, run(root, "--answers", str(path), platforms=platforms)


def test_routes_answer_is_written_to_plumb_md_and_verified(tmp_path: Path) -> None:
    root, r = _scaffold_with(tmp_path, {"routes": "frontend/src/app (next-app)", "ui_files": "frontend/src/** · *.tsx"})
    assert r.returncode == 0, r.stderr
    text = (root / "PLUMB.md").read_text(encoding="utf-8")
    assert "Routes: frontend/src/app (next-app)   " in text
    v = cli(root, "--verify")
    assert "problem: Routes: frontend/src/app (next-app) does not exist in the project" in v.stdout
    assert "fix: ask the user: correct Routes:" in v.stdout and v.returncode == 1
    (root / "frontend/src/app/keys").mkdir(parents=True)
    (root / "frontend/src/app/keys/page.tsx").write_text("export default () => null;\n", encoding="utf-8")
    v = cli(root, "--verify")
    assert "ok: Routes: frontend/src/app (next-app) exists" in v.stdout
    assert "ok: PLUMB.md UI files: matches 1 file" in v.stdout
    assert v.returncode == 0, v.stdout


def test_routes_unanswered_is_not_recorded_for_web_and_none_for_mobile(tmp_path: Path) -> None:
    root, r = _scaffold_with(tmp_path / "web", {})
    assert r.returncode == 0, r.stderr
    assert "Routes: (not recorded yet: /plumb:init records the app's page roots)" in (root / "PLUMB.md").read_text(
        encoding="utf-8")
    v = cli(root, "--verify")
    assert "note: Routes not recorded: run /plumb:init to record them" in v.stdout and v.returncode == 0, v.stdout
    root, r = _scaffold_with(tmp_path / "ios", {}, platforms="ios")
    assert "Routes: none   " in (root / "PLUMB.md").read_text(encoding="utf-8")
    assert "ok: Routes: none" in cli(root, "--verify").stdout


@pytest.mark.parametrize("routes", ["../app (next-app)", "frontend/views", "frontend/src/app", "app (remix)", 7,
                                    "a\nb"])
def test_a_bad_routes_answer_is_refused(tmp_path: Path, routes: object) -> None:
    root, r = _scaffold_with(tmp_path, {"routes": routes})
    assert r.returncode == 2 and r.stderr.startswith("error: answers.routes") and "fix: " in r.stderr
    assert not (root / "PLUMB.md").exists()


def test_verify_reports_ui_files_that_match_no_file(tmp_path: Path) -> None:
    """Live test 2: `UI files: app/**, src/**, components/**` in a monorepo whose UI is in frontend/ covered 0 files,
    which silently switched the audit and the checks off."""
    root, r = _scaffold_with(tmp_path, {"routes": "frontend/src/app (next-app)"})
    assert r.returncode == 0, r.stderr
    for name in ("frontend/src/app/page.tsx", "frontend/src/components/ui/button.tsx"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("export default () => null;\n", encoding="utf-8")
    plumb = root / "PLUMB.md"
    text = plumb.read_text(encoding="utf-8")
    plumb.write_text(re.sub(r"UI files: [^\n]*", "UI files: app/**, src/**, components/** · *.tsx *.css", text),
                     encoding="utf-8")
    v = cli(root, "--verify")
    assert v.returncode == 1
    assert "problem: PLUMB.md UI files: app/**, src/**, components/** · *.tsx *.css matches 0 files" in v.stdout
    assert "fix: ask the user: correct UI files:" in v.stdout
    plumb.write_text(re.sub(r"UI files: [^\n]*", "UI files: frontend/src/**, frontend/lib/** · *.tsx *.css", text),
                     encoding="utf-8")
    v = cli(root, "--verify")
    assert "ok: PLUMB.md UI files: matches 2 files" in v.stdout and v.returncode == 0, v.stdout
    assert "note: UI files: frontend/lib/** matches 0 files" in v.stdout
