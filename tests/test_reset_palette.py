"""$extensions.plumb.web.reset_palette (live test 2, B2): whether Plumb's block switches off Tailwind's default palette.

true (create, a new app): only the tokens exist. false (extract, an existing app): Tailwind's palette and scales stay
until the app is migrated, and the audit suggests each move instead of reporting errors. When it is true while the
app still uses palette classes, the build warns with their count. scaffold.py takes the `reset_palette` answer and,
unanswered, defaults to false when the app already uses palette classes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "plugins/plumb/assets/skill/scripts"
WEB_TEMPLATES = REPO / "plugins/plumb/assets/skill/assets/platforms/web"
FIXTURE = REPO / "tests/fixtures/projects/web-v4"
SCAFFOLD = REPO / "plugins/plumb/scripts/scaffold.py"
SKILL_REL = ".claude/skills/demo-design-system"
RESETS = [f"--{ns}-*: initial;" for ns in ("color", "radius", "shadow", "text", "font", "ease")]
PAGE = ('export default function Page() {\n  return <div className="bg-emerald-500 text-white">\n'
        '    <p className="text-amber-600">hi</p>\n  </div>;\n}\n')


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    shutil.copytree(FIXTURE, dest)
    for name in ("_plumb.py", "build-tokens.py", "audit.py"):
        shutil.copy(SCRIPTS / name, dest / SKILL_REL / "scripts" / name)
    return dest


def tokens(p: Path) -> Path:
    return p / SKILL_REL / "assets/tokens/demo.tokens.json"


def set_reset(p: Path, value: object) -> None:
    doc = json.loads(tokens(p).read_text(encoding="utf-8"))
    doc["$extensions"]["plumb"]["web"]["reset_palette"] = value
    write(tokens(p), json.dumps(doc, indent=2) + "\n")


def build(p: Path, *args: str) -> "subprocess.CompletedProcess[str]":
    return subprocess.run([sys.executable, str(p / SKILL_REL / "scripts/build-tokens.py"), *args], cwd=str(p),
                          capture_output=True, text=True, encoding="utf-8")


def audit(p: Path) -> dict:
    r = subprocess.run([sys.executable, str(p / SKILL_REL / "scripts/audit.py"), "--json"], cwd=str(p),
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode in (0, 1), r.stderr
    return json.loads(r.stdout)


def css(p: Path) -> str:
    return (p / SKILL_REL / "assets/platforms/web/tokens.css").read_text(encoding="utf-8")


def test_true_and_missing_close_the_scales(project: Path) -> None:
    r = build(project)
    assert r.returncode == 0, r.stderr
    assert all(line in css(project) for line in RESETS)
    assert "Closed scales (web.reset_palette true)" in css(project)
    set_reset(project, True)
    assert build(project).returncode == 0
    assert all(line in css(project) for line in RESETS)


def test_false_keeps_tailwinds_palette_in_the_block_and_the_copy(project: Path) -> None:
    set_reset(project, False)
    r = build(project)
    assert r.returncode == 0, r.stderr
    for text in (css(project), (project / "app/globals.css").read_text(encoding="utf-8")):
        assert not any(line in text for line in RESETS)
        assert "Open scales (web.reset_palette false)" in text
    assert build(project, "--check").returncode == 0


def test_false_with_an_older_template_that_spells_the_resets_out(project: Path) -> None:
    old = ('/* {{@header}} */\n@import "tailwindcss";\n\n{{@dark-variant}}\n\n'
           "/* Closed scales: Tailwind's default colours, radii, shadows, text sizes, fonts and easings do not exist here.\n"
           "   Spacing stays Tailwind's multiplier from the spacing base token; the audit enforces the scale. */\n"
           "@theme static {\n" + "".join(f"  {line}\n" for line in RESETS) + "\n  {{@vars}}\n}\n\n{{@dark}}\n")
    write(project / SKILL_REL / "assets/platforms/web/tokens.css.template", old)
    assert build(project).returncode == 0
    assert all(line in css(project) for line in RESETS)
    set_reset(project, False)
    assert build(project).returncode == 0
    assert not any(line in css(project) for line in RESETS) and "Closed scales" not in css(project)


@pytest.mark.parametrize("value", ["no", 0, None])
def test_a_value_that_is_not_true_or_false_is_refused(project: Path, value: object) -> None:
    set_reset(project, value)
    r = build(project)
    assert r.returncode == 2
    assert r.stderr.startswith("error: $extensions.plumb.web.reset_palette is") and "fix: " in r.stderr


def test_true_warns_with_the_count_of_palette_classes_in_use(project: Path) -> None:
    write(project / "app/page.tsx", PAGE)
    for args in ((), ("--check",)):
        r = build(project, *args)
        assert ("warning: web.reset_palette is true, so Plumb's block switches off Tailwind's default palette"
                in r.stderr), r.stderr
        assert "3 palette classes in 1 UI file would lose their colour (bg-emerald-500, text-white, text-amber-600)" \
            in r.stderr
        assert '"reset_palette": false' in r.stderr and "fix: ask the user:" in r.stderr
    set_reset(project, False)
    assert "warning: web.reset_palette" not in build(project).stderr
    (project / "app/page.tsx").unlink()
    set_reset(project, True)
    assert "warning: web.reset_palette" not in build(project).stderr


def test_audit_suggests_palette_classes_while_the_palette_is_open(project: Path) -> None:
    write(project / "app/page.tsx", PAGE)
    assert build(project).returncode == 0
    closed = [f for f in audit(project)["findings"] if f["rule"] == "palette-colour"]
    assert [f["severity"] for f in closed] == ["error"] * 3
    set_reset(project, False)
    assert build(project).returncode == 0
    opened = [f for f in audit(project)["findings"] if f["rule"] == "palette-colour"]
    assert [f["severity"] for f in opened] == ["suggest"] * 3
    assert "the palette stays open while web.reset_palette is false" in opened[0]["message"]


def test_migrate_records_the_default(project: Path) -> None:
    r = build(project, "--migrate")
    assert r.returncode == 0, r.stderr
    assert "added $extensions.plumb.web.reset_palette = true" in r.stdout
    assert json.loads(tokens(project).read_text(encoding="utf-8"))["$extensions"]["plumb"]["web"]["reset_palette"] is True


# ---------------------------------------------------------------- scaffold.py


def scaffold(root: Path, answers: dict) -> "subprocess.CompletedProcess[str]":
    path = root.parent / f"{root.name}-answers.json"
    write(path, json.dumps(answers))
    dry = subprocess.run([sys.executable, str(SCAFFOLD), "--project-root", str(root), "--name", "Demo", "--skill-dir",
                          SKILL_REL, "--platforms", "web", "--styling", "tailwind-v4", "--answers", str(path),
                          "--dry-run"], capture_output=True, text=True, encoding="utf-8")
    assert dry.returncode == 0, dry.stderr
    token = [ln.split("--confirm ", 1)[1].split()[0] for ln in dry.stdout.splitlines() if "--confirm " in ln]
    return subprocess.run([sys.executable, str(SCAFFOLD), "--project-root", str(root), "--name", "Demo", "--skill-dir",
                           SKILL_REL, "--platforms", "web", "--styling", "tailwind-v4", "--answers", str(path)]
                          + (["--confirm", token[0]] if token else []),
                          capture_output=True, text=True, encoding="utf-8")


def web_settings(root: Path) -> dict:
    return json.loads((root / SKILL_REL / "assets/tokens/demo.tokens.json").read_text(encoding="utf-8"))[
        "$extensions"]["plumb"]["web"]


def test_scaffold_writes_the_answer(tmp_path: Path) -> None:
    for value in (True, False):
        root = tmp_path / str(value)
        root.mkdir()
        r = scaffold(root, {"reset_palette": value})
        assert r.returncode == 0, r.stderr
        assert web_settings(root)["reset_palette"] is value


def test_scaffold_default_keeps_the_palette_of_an_app_that_uses_it(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    write(fresh / "app/page.tsx", "export default function Page() { return <main className=\"p-4\">hi</main>; }\n")
    r = scaffold(fresh, {})
    assert r.returncode == 0, r.stderr
    assert web_settings(fresh)["reset_palette"] is True and "reset_palette false" not in r.stderr
    existing = tmp_path / "existing"
    write(existing / "app/page.tsx", PAGE)
    r = scaffold(existing, {})
    assert r.returncode == 0, r.stderr
    assert web_settings(existing)["reset_palette"] is False
    assert "note: reset_palette false: the app uses 3 Tailwind default palette classes in 1 UI file" in r.stderr


def test_scaffold_refuses_a_reset_palette_that_is_not_a_bool(tmp_path: Path) -> None:
    path = tmp_path / "answers.json"
    write(path, json.dumps({"reset_palette": "yes"}))
    root = tmp_path / "proj"
    root.mkdir()
    r = subprocess.run([sys.executable, str(SCAFFOLD), "--project-root", str(root), "--name", "Demo", "--skill-dir",
                        SKILL_REL, "--platforms", "web", "--styling", "tailwind-v4", "--answers", str(path), "--dry-run"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and r.stderr.startswith("error: answers reset_palette") and "fix: " in r.stderr
