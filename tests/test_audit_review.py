"""audit.py --add-review FILE: the agent's review findings (what no rule expresses) merged into the HTML report as a
separate "Agent review" section, marked as such, never changing the rule findings, the summary counts or the exit code.
"""

from __future__ import annotations

import datetime
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL_SRC = REPO / "plugins/plumb/assets/skill"
FIXTURE = REPO / "tests/fixtures/pages"
SKILL_REL = ".claude/skills/demo-design-system"

REVIEW = [
    {"severity": "warn", "file": "app/page.tsx", "line": 3,
     "message": "Two primary buttons compete on the booking screen",
     "fix": "Make \"Cancel\" a secondary button", "why": "One primary action per view keeps the next step obvious."},
    {"severity": "suggest", "file": "app/settings/page.tsx",
     "message": "The empty state says \"No data\" <b>instead</b> of what to do",
     "fix": "Use the vocabulary's empty-state line and a button to add the first item",
     "why": "An empty state should say what to do next."},
    {"severity": "error", "file": "docs/design/prototype/screens/booking.html", "line": 12,
     "message": "Dark mode: the selected day is invisible (same colour as the surface)",
     "fix": "Use the selected token for the fill", "why": "A state nobody can see is a broken control."},
]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "Café Ünïcode"
    shutil.copytree(FIXTURE / "app", dest / "app")
    skill = dest / SKILL_REL
    for name in ("_plumb.py", "audit.py", "build-tokens.py"):
        (skill / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy(SKILL_SRC / "scripts" / name, skill / "scripts" / name)
    (skill / "templates").mkdir(parents=True, exist_ok=True)
    shutil.copy(SKILL_SRC / "templates/audit-report.html.tmpl", skill / "templates/audit-report.html.tmpl")
    write(skill / "assets/tokens/demo.tokens.json", (FIXTURE / "tokens.json").read_text(encoding="utf-8"))
    write(skill / "assets/platforms/web/tokens.css.template",
          (SKILL_SRC / "assets/platforms/web/tokens.css.template.tailwind-v4").read_text(encoding="utf-8"))
    write(dest / "PLUMB.md", "Project: demo\n\n## Checks\nAllowed raw values: components/ui/**\n")
    r = subprocess.run([sys.executable, str(skill / "scripts/build-tokens.py")], cwd=str(dest), capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    return dest


def audit(project: Path, *args: str):
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts/audit.py"), *args], cwd=str(project),
                          capture_output=True, text=True, encoding="utf-8")


def report(project: Path) -> str:
    return (project / f"docs/design/audit-{datetime.date.today().isoformat()}.html").read_text(encoding="utf-8")


def review_file(project: Path, entries, name: str = "review.json") -> Path:
    path = project / "docs/design" / name
    write(path, entries if isinstance(entries, str) else json.dumps(entries, indent=2, ensure_ascii=False) + "\n")
    return path


def section(text: str) -> str:
    start = text.index('<section id="agent-review"')
    return text[start:text.index("</section>", start)]


def assert_refusal(r, *needles: str) -> None:
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "error: " in r.stderr and "\nfix: " in r.stderr, r.stderr
    assert "Traceback" not in r.stderr
    for n in needles:
        assert n in r.stderr, r.stderr


def test_review_is_a_separate_marked_section(project: Path) -> None:
    plain = audit(project, "--html")
    without = report(project)
    assert 'id="agent-review"' not in without
    r = audit(project, "--html", "--add-review", str(review_file(project, REVIEW)))
    assert r.returncode == plain.returncode == 1
    assert r.stdout == plain.stdout  # the terminal shows the rule findings only
    assert "agent review: 3 findings" in r.stderr
    text = report(project)
    part = section(text)
    assert ">Agent review<" in part
    assert "not from a rule" in part
    rows = re.findall(r'<li class="finding[^"]*" data-severity="(\w+)" data-rule="agent-review"', part)
    assert rows == ["error", "warn", "suggest"]  # by severity
    assert part.count('class="agent-mark"') == 3
    for entry in REVIEW:
        assert html.escape(entry["message"], quote=False) in part
        assert html.escape(entry["fix"], quote=False) in part
        assert html.escape(entry["why"], quote=False) in part
    assert "&lt;b&gt;instead&lt;/b&gt;" in part and "<b>instead</b>" not in text
    plain_part = re.sub(r"<[^>]+>", "", part)
    assert "app/page.tsx:3" in plain_part
    assert "app/settings/page.tsx" in plain_part and "app/settings/page.tsx:" not in plain_part  # no line given
    assert '<option value="agent-review">agent review (3)</option>' in text


def test_rule_findings_and_counts_are_unchanged(project: Path) -> None:
    audit(project, "--html")
    before = report(project)
    audit(project, "--html", "--add-review", str(review_file(project, REVIEW)))
    after = report(project)
    for key in ("errors", "warnings", "suggestions", "files"):
        assert re.search(rf'data-count="{key}">(\d+)<', before).group(1) == re.search(rf'data-count="{key}">(\d+)<',
                                                                                      after).group(1)
    stripped = re.sub(r'\n[^\n]*<section id="agent-review".*?</section>', "", after, flags=re.S)
    stripped = re.sub(r'\n[^\n]*<option value="agent-review">[^\n]*', "", stripped)

    def squeeze(text: str) -> str:
        return re.sub(r"\n\s*\n", "\n", text)

    assert squeeze(stripped) == squeeze(before)


def test_review_never_changes_the_exit_code(tmp_path: Path, project: Path) -> None:
    shutil.rmtree(project / "app")
    write(project / "app/ok.tsx", "export const Ok = () => <p className=\"text-sm\">Fine</p>;\n")
    r = audit(project, "--html", "--add-review", str(review_file(project, REVIEW)))
    assert r.returncode == 0, r.stdout + r.stderr  # an agent-review error is for the user, not the gate
    assert 'data-severity="error" data-rule="agent-review"' in report(project)


def test_empty_review_says_so(project: Path) -> None:
    r = audit(project, "--html", "--add-review", str(review_file(project, [])))
    assert r.returncode == 1
    part = section(report(project))
    assert "found nothing beyond the rules" in part


def test_json_output_carries_the_review(project: Path) -> None:
    r = audit(project, "--json", "--html", "out/r.html", "--add-review", str(review_file(project, REVIEW)))
    data = json.loads(r.stdout)
    assert [f["severity"] for f in data["agent_review"]] == ["error", "warn", "suggest"]
    assert data["agent_review"][1]["line"] == 3 and data["agent_review"][2]["line"] is None
    assert all(f["rule"] != "agent-review" for f in data["findings"])
    assert (project / "out/r.html").is_file()


def test_crlf_bom_review_file(project: Path) -> None:
    path = project / "review.json"
    path.write_bytes(("﻿" + json.dumps(REVIEW[:1])).replace("\n", "\r\n").encode("utf-8"))
    r = audit(project, "--html", "--add-review", str(path))
    assert r.returncode == 1, r.stderr
    assert "Two primary buttons" in report(project)


@pytest.mark.parametrize("entries, needles", [
    ("[{\"severity\": \"warn\",}]", ("invalid JSON", "line 1")),
    ({"severity": "warn"}, ("a JSON list",)),
    (["just text"], ("entry 1", "object")),
    ([{"severity": "warn", "file": "a.tsx", "fix": "x"}], ("entry 1", "message")),
    ([{"severity": "major", "file": "a.tsx", "message": "m", "fix": "x"}], ("entry 1", "severity", "major")),
    ([{"severity": "warn", "file": "a.tsx", "line": "3", "message": "m", "fix": "x"}], ("entry 1", "line")),
    ([{"severity": "warn", "file": "a.tsx", "line": 0, "message": "m", "fix": "x"}], ("entry 1", "line")),
    ([{"severity": "warn", "file": "", "message": "m", "fix": "x"}], ("entry 1", "file")),
    ([REVIEW[0], {"severity": "warn", "file": "a.tsx", "message": "m", "fix": "x", "rule": "r"}], ("entry 2", "rule")),
    ([{"severity": "warn", "file": "a.tsx", "message": "m", "fix": "x", "why": 3}], ("entry 1", "why")),
])
def test_bad_review_files_exit_2(project: Path, entries, needles) -> None:
    r = audit(project, "--html", "--add-review", str(review_file(project, entries)))
    assert_refusal(r, "review.json", *needles)
    assert not (project / f"docs/design/audit-{datetime.date.today().isoformat()}.html").exists()


def test_add_review_refusals(project: Path) -> None:
    path = review_file(project, REVIEW)
    assert_refusal(audit(project, "--add-review", str(path)), "--html")
    assert_refusal(audit(project, "--html", "--add-review", str(project / "missing.json")), "missing.json")
    assert_refusal(audit(project, "--quick", "app/page.tsx", "--add-review", str(path)), "--quick")


# ---------------------------------------------------------------- browser (headless; skipped without Playwright)


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_review_section_in_a_browser(project: Path, width: int, scheme: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("requires Playwright")
    long_path = {**REVIEW[1], "file": "app/(marketing)/a-very-long-folder-name-for-wrapping/settings/notifications/page.tsx"}
    r = audit(project, "--html", "--add-review", str(review_file(project, [REVIEW[0], long_path, REVIEW[2]])))
    assert r.returncode == 1, r.stderr
    path = project / f"docs/design/audit-{datetime.date.today().isoformat()}.html"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(path.resolve().as_uri())
            assert page.evaluate("document.documentElement.dataset.theme") == scheme
            assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
            assert page.is_visible("#agent-review") and page.inner_text("#agent-review-h") == "Agent review"
            visible = ("() => [...document.querySelectorAll('li.finding')].filter(e => e.offsetParent !== null)"
                       ".map(e => e.dataset.rule)")
            page.select_option("#rule-filter", "agent-review")
            assert page.evaluate(visible) == ["agent-review"] * 3
            page.click('[data-filter-severity="warn"]')
            assert page.evaluate(visible) == ["agent-review"] * 2
            assert errors == []
        finally:
            browser.close()
