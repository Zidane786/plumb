"""scaffold.py --relocate and --verify: move the skill, keep every reference in step, find it again."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def test_verify_reports_make_targets_plumb_md_names_but_the_makefile_lacks(tmp_path: Path) -> None:
    root = project_with_everything(tmp_path)
    make = root / "Makefile"
    make.write_text(make.read_text(encoding="utf-8").replace("design-audit:", "audit:"), encoding="utf-8")
    r = cli(root, "--verify")
    assert r.returncode == 1
    assert "problem: PLUMB.md names `make design-audit`, but the Makefile has no such target" in r.stdout
    assert "make tokens`" not in r.stdout and "templates/Makefile.snippet" in r.stdout
    make.unlink()
    r = cli(root, "--verify")
    assert r.returncode == 1
    for target in ("tokens", "tokens-check", "design-audit"):
        assert f"problem: PLUMB.md names `make {target}`, but there is no Makefile" in r.stdout


def test_verify_without_plumb_md(tmp_path: Path) -> None:
    r = cli(tmp_path, "--verify")
    assert r.returncode == 1 and "problem: no PLUMB.md" in r.stdout and "fix: " in r.stdout
