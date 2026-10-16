"""The two fixed-template pages: the audit report (audit.py --html) and the specimen (written by build-tokens.py).

Static checks run everywhere. The browser checks load both pages headless at 1280 and 390 px, in light and dark, and
skip only when Playwright is not importable.
"""

from __future__ import annotations

import datetime
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL_SRC = REPO / "plugins/plumb/assets/skill"
SCRIPTS = SKILL_SRC / "scripts"
TEMPLATES = SKILL_SRC / "templates"
WEB_TEMPLATES = SKILL_SRC / "assets/platforms/web"
FIXTURE = REPO / "tests/fixtures/pages"
SKILL_REL = ".claude/skills/demo-design-system"
TOKENS_REL = f"{SKILL_REL}/assets/tokens/demo.tokens.json"
SPECIMEN_REL = "docs/design/specimen.html"
STATES = ("default", "hover", "focus", "pressed", "disabled", "loading")
COMPONENTS = ("button-primary", "button-secondary", "button-outline", "button-danger", "input", "chip", "card")

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


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def make_project(dest: Path, app: bool = True, templates: bool = True, mutate=None, build: bool = True) -> Path:
    """A project with the pages fixture's tokens (and app files), the skill's scripts and (by default) its templates."""
    dest.mkdir(parents=True, exist_ok=True)
    if app:
        shutil.copytree(FIXTURE / "app", dest / "app")
    skill = dest / SKILL_REL
    (skill / "scripts").mkdir(parents=True, exist_ok=True)
    for name in ("_plumb.py", "audit.py", "build-tokens.py"):
        shutil.copy(SCRIPTS / name, skill / "scripts" / name)
    if templates:
        (skill / "templates").mkdir(parents=True, exist_ok=True)
        for name in ("specimen.html.tmpl", "audit-report.html.tmpl"):
            shutil.copy(TEMPLATES / name, skill / "templates" / name)
    doc = json.loads((FIXTURE / "tokens.json").read_text(encoding="utf-8"))
    if mutate:
        mutate(doc)
    write(dest / TOKENS_REL, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    write(skill / "assets/platforms/web/tokens.css.template",
          (WEB_TEMPLATES / "tokens.css.template.tailwind-v4").read_text(encoding="utf-8"))
    write(dest / "PLUMB.md", "Project: demo\n\n## Checks\nAllowed raw values: components/ui/**\n")
    if build:
        r = build_tokens(dest)
        assert r.returncode == 0, r.stdout + r.stderr
    return dest


def build_tokens(project: Path, *args: str):
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts/build-tokens.py"), *args], cwd=str(project),
                          capture_output=True, text=True, encoding="utf-8")


def audit(project: Path, *args: str):
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts/audit.py"), *args], cwd=str(project),
                          capture_output=True, text=True, encoding="utf-8")


def doc_of(project: Path) -> dict:
    return P.load_tokens(project / TOKENS_REL)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def today_report(project: Path) -> Path:
    return project / f"docs/design/audit-{datetime.date.today().isoformat()}.html"


def plain_text(page: str) -> str:
    """The page with its tags removed (what a reader sees, still HTML-escaped)."""
    return re.sub(r"<[^>]+>", "", page)


def assert_refusal(r, *needles: str) -> None:
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "error: " in r.stderr and "\nfix: " in r.stderr, r.stderr
    assert "Traceback" not in r.stderr
    for n in needles:
        assert n in r.stderr, r.stderr


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "proj")


@pytest.fixture()
def report(project: Path) -> Path:
    r = audit(project, "--html")
    assert r.returncode == 1, r.stdout + r.stderr
    return today_report(project)


NETWORK = re.compile(r"""(?:\b(?:src|href|action|poster|data)\s*=\s*["']?\s*https?:|@import\s+(?:url\()?\s*["']?\s*https?:"""
                     r"""|url\(\s*["']?\s*https?:|\bimport\s*\(\s*["']https?:)""", re.I)


def assert_offline(text: str) -> None:
    assert not NETWORK.search(text), NETWORK.search(text).group(0)
    assert "<link" not in text.lower() or not re.search(r"<link[^>]+href\s*=\s*[\"']?(?:https?:)?//", text, re.I)


def assert_document(text: str) -> None:
    assert text.startswith("<!doctype html>")
    head = text[:3000].lower()
    assert '<meta charset="utf-8">' in head
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in head
    assert "</html>" in text[-200:]


# ---------------------------------------------------------------- templates


def test_templates_are_complete_offline_documents() -> None:
    for name in ("specimen.html.tmpl", "audit-report.html.tmpl"):
        text = read(TEMPLATES / name)
        assert_document(text)
        assert_offline(text)
        assert 'id="theme-toggle"' in text
        assert "prefers-color-scheme: dark" in text and "prefers-reduced-motion: reduce" in text
        assert ":focus-visible" in text
        assert "data-theme" in text


def test_app_shell_template_is_a_complete_offline_document() -> None:
    """The app view (build-prototype.py's app.html): no chrome, so no theme toggle of its own; both themes, reduced
    motion and focus rings, the frame a tour page's player draws over, and the slots the build fills."""
    text = read(TEMPLATES / "app-shell.html.tmpl")
    assert_document(text)
    assert_offline(text)
    assert 'id="theme-toggle"' not in text
    assert "prefers-color-scheme: dark" in text and "prefers-reduced-motion: reduce" in text
    assert ":focus-visible" in text and "data-theme" in text
    assert 'id="pp-stage"' in text and 'id="pp-frame"' in text and "isolation: isolate;" in text
    for slot in ("header", "base", "title", "theme_key", "theme_css", "screen_styles", "frame", "data", "screen_scripts",
                 "player_css", "player"):
        assert "{{" + slot + "}}" in text, slot
    assert "localStorage" in text and "catch (err)" in text  # storage is a convenience: a throwing one still renders


# ---------------------------------------------------------------- specimen


def test_build_writes_the_specimen_with_a_generated_header(project: Path) -> None:
    path = project / SPECIMEN_REL
    text = read(path)
    assert_document(text)
    head = "\n".join(text.splitlines()[:5])
    assert "GENERATED" in head and "do not edit" in head.lower()
    assert TOKENS_REL in head and "build-tokens.py" in head
    assert "Café Ünïcode" in text
    assert_offline(text)


def test_specimen_is_in_outputs_and_byte_stable(project: Path) -> None:
    path = (project / SPECIMEN_REL).resolve()
    out = BT.outputs(doc_of(project), project / SKILL_REL)
    assert path in out
    first = path.read_bytes()
    assert out[path].encode("utf-8") == first
    r = build_tokens(project)
    assert r.returncode == 0 and "specimen" not in r.stdout, r.stdout
    assert path.read_bytes() == first
    assert not re.search(r"20\d\d-\d\d-\d\d", first.decode("utf-8")), "no date or timestamp in the specimen"


def test_check_covers_the_specimen(project: Path) -> None:
    assert build_tokens(project, "--check").returncode == 0
    path = project / SPECIMEN_REL
    write(path, read(path).replace("</main>", "<p>hand edit</p></main>"))
    r = build_tokens(project, "--check")
    assert r.returncode == 1 and f"stale: {SPECIMEN_REL}" in r.stdout, r.stdout
    path.unlink()
    r = build_tokens(project, "--check")
    assert r.returncode == 1 and f"stale: {SPECIMEN_REL}" in r.stdout, r.stdout


def test_specimen_follows_docs_dir(tmp_path: Path) -> None:
    def mutate(doc: dict) -> None:
        doc["$extensions"]["plumb"]["docs_dir"] = "design/system"

    p = make_project(tmp_path / "proj", mutate=mutate)
    assert (p / "design/system/specimen.html").is_file()
    assert not (p / SPECIMEN_REL).exists()


def test_specimen_skipped_with_a_note_when_the_template_is_missing(tmp_path: Path) -> None:
    p = make_project(tmp_path / "proj", templates=False, build=False)
    r = build_tokens(p)
    assert r.returncode == 0, r.stderr
    assert "note:" in r.stderr and "specimen.html.tmpl" in r.stderr, r.stderr
    assert not (p / SPECIMEN_REL).exists()
    r = build_tokens(p, "--check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_specimen_shows_every_token(project: Path) -> None:
    text = read(project / SPECIMEN_REL)
    doc = doc_of(project)
    for path, _tok, _type in P.iter_tokens(doc):
        assert f'data-token="{path}"' in text, path
        assert BT.varname(path) in text, path
    for section in ("colour", "type", "spacing", "radius", "shadow", "motion", "components", "other"):
        assert f'id="{section}"' in text, section


def _row(text: str, path: str) -> str:
    start = text.index(f'data-token="{path}"')
    end = text.find('data-token="', start + 10)
    return text[start:end if end != -1 else len(text)]


def test_specimen_colours_in_light_and_dark_with_contrast(project: Path) -> None:
    text = read(project / SPECIMEN_REL)
    doc = doc_of(project)
    for path, _tok, ttype in P.iter_tokens(doc):
        if ttype != "color":
            continue
        row = _row(text, path)
        light = P.parse_color(P.resolve(doc, path, "light"))[0]
        dark = P.parse_color(P.resolve(doc, path, "dark"))[0]
        assert light in row and dark in row, path
        assert 'class="pl-light' in row and 'class="pl-dark' in row, path
    pairs = BT.measure_pairs(doc)
    assert pairs
    for pair in pairs:
        key = f'data-pair="{pair.fg} on {pair.bg}"'
        assert key in text, key
        chunk = text[text.index(key):text.index(key) + 600]
        assert f"light <b>{P.ratio_text(pair.light)}</b>" in chunk and f"dark <b>{P.ratio_text(pair.dark)}</b>" in chunk, chunk


def test_specimen_shows_a_pair_just_under_the_minimum_as_failing(tmp_path: Path) -> None:
    # #008580 on white is 4.49995:1: it fails 4.5:1 and shows 4.49 (floored), as in dark-mode.md and the audit
    def mut(doc: dict) -> None:
        doc["color"]["link"] = {"$value": "#008580", "$extensions": {"plumb": {"dark": "#7fd6d0"}}}
    p = make_project(tmp_path / "proj", mutate=mut)
    text = read(p / SPECIMEN_REL)
    key = 'data-pair="link on background"'
    chunk = text[text.index(key):text.index(key) + 600]
    assert "light <b>4.49</b>" in chunk and "verdict-good" not in chunk.split("</li>")[0], chunk
    found = json.loads(audit(p, "--json").stdout)["findings"]
    assert any(f["rule"] == "contrast" and "link on background is 4.49:1 in light mode" in f["message"] for f in found)


def test_audit_names_a_foreign_specimen_as_a_warning_with_the_move_fix(project: Path) -> None:
    # build-tokens leaves a specimen.html it did not write as it is; the audit must not ask for a build that cannot clear it
    write(project / SPECIMEN_REL, "<!doctype html>\n<html><body><h1>Our own specimen</h1></body></html>\n")
    out = json.loads(audit(project, "--json").stdout)
    drift = [f for f in out["findings"] if f["rule"] == "generated-drift"]
    assert len(drift) == 1, drift
    f = drift[0]
    assert f["severity"] == "warn" and f["file"] == SPECIMEN_REL and "not Plumb's" in f["message"], f
    assert "mv docs/design/specimen.html docs/design/specimen.before-plumb.html" in f["fix"], f
    assert "ask the user" in f["fix"] and "build-tokens.py" in f["fix"]
    assert not any(x["severity"] == "error" and x["file"] == SPECIMEN_REL for x in out["findings"])


def test_specimen_scopes_both_themes_from_the_tokens(project: Path) -> None:
    text = read(project / SPECIMEN_REL)
    doc = doc_of(project)
    assert BT.css_vars(doc) in text  # the project's own export, inlined
    dark_block = re.search(r"\.pl-dark\s*\{([^}]*)\}", text).group(1)
    light_block = re.search(r"\.pl-light\s*\{([^}]*)\}", text).group(1)
    assert "--color-background: #0f1217;" in dark_block
    assert "--color-background: #ffffff;" in light_block and "#0f1217" not in light_block
    assert "--pl-accent: var(--color-primary);" in text


def test_specimen_components_in_every_state_in_both_themes(project: Path) -> None:
    text = read(project / SPECIMEN_REL)
    for comp in COMPONENTS:
        for state in STATES:
            needle = f'data-component="{comp}" data-state="{state}"'
            assert text.count(needle) == 2, (needle, text.count(needle))


def test_specimen_escapes_token_text(project: Path) -> None:
    text = read(project / SPECIMEN_REL)
    assert "&lt;b&gt;&amp;amp; body&lt;/b&gt;" in text
    assert "<b>&amp; body</b>" not in text


def test_specimen_type_motion_and_reduced_motion(project: Path) -> None:
    text = read(project / SPECIMEN_REL)
    assert "var(--text-display--font-weight)" in text and "var(--text-display--letter-spacing)" in text
    assert "var(--duration-fast)" in text and "var(--ease-in-out)" in text
    assert "@media (prefers-reduced-motion: reduce)" in text


def test_specimen_for_a_minimal_token_set(tmp_path: Path) -> None:
    def mutate(doc: dict) -> None:
        for group in ("label", "font", "typography", "radius", "spacing", "size", "border", "shadow", "motion"):
            doc.pop(group)
        doc["color"] = {"$type": "color", "ink": {"$value": "#222222", "$extensions": {"plumb": {"dark": "#eeeeee"}}}}

    p = make_project(tmp_path / "proj", mutate=mutate)
    text = read(p / SPECIMEN_REL)
    assert_document(text)
    assert 'data-token="color.ink"' in text
    for comp in COMPONENTS:
        assert f'data-component="{comp}" data-state="default"' in text


# ---------------------------------------------------------------- audit report


def test_report_written_and_terminal_unchanged(project: Path) -> None:
    plain = audit(project)
    r = audit(project, "--html")
    assert r.returncode == plain.returncode == 1
    assert r.stdout == plain.stdout
    path = today_report(project)
    assert path.is_file()
    assert path.name in r.stderr and "wrote" in r.stderr
    text = read(path)
    assert_document(text)
    assert_offline(text)
    assert "GENERATED" in "\n".join(text.splitlines()[:5])


def test_report_has_every_finding_and_the_summary(project: Path, report: Path) -> None:
    data = json.loads(audit(project, "--json").stdout)
    text = read(report)
    assert data["errors"] and data["warnings"] and data["suggestions"]
    for key, sev in (("errors", "error"), ("warnings", "warn"), ("suggestions", "suggest")):
        assert f'data-count="{key}">{data[key]}<' in text, key
        assert len(re.findall(rf'<li class="finding[^"]*" data-severity="{sev}"', text)) == data[key], sev
    assert f'data-count="files">{data["checked"]}<' in text
    rows = re.findall(r'<li class="finding[^"]*" data-severity="(\w+)" data-rule="([\w-]+)"', text)
    assert len(rows) == len(data["findings"])
    for f in data["findings"]:
        assert html.escape(f["message"], quote=False) in text, f["message"]
        assert html.escape(f["fix"], quote=False) in text, f["fix"]
        assert html.escape(f"{f['file']}:{f['line']}", quote=False) in plain_text(text)
    assert P.PLUMB_VERSION in text and datetime.date.today().isoformat() in text
    for section in ("summary", "issues", "improvements"):
        assert f'id="{section}"' in text
    assert f"python3 {SKILL_REL}/scripts/audit.py --html" in text
    assert "menü.tsx" in text


def test_report_ranks_errors_first_and_improvements_by_impact(report: Path) -> None:
    text = read(report)
    issues = text[text.index('id="issues"'):text.index('id="improvements"')]
    sevs = re.findall(r'<li class="finding[^"]*" data-severity="(\w+)"', issues)
    assert sevs and "suggest" not in sevs
    assert sevs == sorted(sevs, key=lambda s: {"error": 0, "warn": 1}[s])
    improvements = text[text.index('id="improvements"'):]
    groups = re.findall(r'data-rule="([\w-]+)" data-impact="(\d+)"', improvements)
    assert groups
    impacts = [int(i) for _r, i in groups]
    assert impacts == sorted(impacts, reverse=True)
    weights = {r.id: r.weight for r in A.RULES}
    for rule, impact in groups:
        count = len(re.findall(rf'<li class="finding[^"]*" data-severity="suggest" data-rule="{rule}"', improvements))
        assert int(impact) == weights[rule] * count
        assert A.RULES[[r.id for r in A.RULES].index(rule)].why in html.unescape(improvements)
    for sev, word in (("error", "Error"), ("warn", "Warning"), ("suggest", "Suggestion")):
        assert re.search(rf'class="sev sev-{sev}"[^>]*>\s*<span class="sev-shape" aria-hidden="true"></span>\s*{word}', text), sev


def test_report_shows_a_shared_fix_once_per_group(project: Path, report: Path) -> None:
    data = json.loads(audit(project, "--json").stdout)
    text = read(report)
    issues = text[text.index('id="issues"'):text.index('id="improvements"')]
    raw = [f for f in data["findings"] if f["rule"] == "raw-colour"]
    assert len(raw) == 4 and len({f["fix"] for f in raw}) == 1
    assert issues.count(html.escape(raw[0]["fix"], quote=False)) == 1
    assert "(for the 4 below)" in issues
    rows = re.findall(r'<li class="finding([^"]*)" data-severity="error" data-rule="raw-colour"', issues)
    assert rows == [" compact"] * 4
    single = re.findall(r'<li class="finding([^"]*)" data-severity="error" data-rule="palette-colour"', issues)
    assert single == [""]  # a fix of its own stays on its row


def test_report_paths_break_only_after_separators(project: Path, report: Path) -> None:
    text = read(report)
    assert '<span class="seg">.claude</span>/<wbr><span class="seg">skills</span>/<wbr>' in text
    assert '<span class="seg">demo-design-system</span>/<wbr>' in text
    assert '<span class="seg">demo.tokens.json:24</span>' in text or "demo.tokens.json:" in text


def _mutate_muted(doc: dict) -> None:
    doc["color"]["text-muted"] = {"$value": "#b8b8b8", "$extensions": {"plumb": {"dark": "#3a3d42"}}}


def test_chrome_text_keeps_a_contrast_floor(tmp_path: Path) -> None:
    good = make_project(tmp_path / "good")
    assert "--pl-muted: var(--color-text-muted);" in read(good / SPECIMEN_REL)
    p = make_project(tmp_path / "low", mutate=_mutate_muted)
    assert audit(p, "--html").returncode == 1
    for page in (p / SPECIMEN_REL, today_report(p)):
        text = read(page)
        assert "--pl-muted:" not in text.split("Plumb's page roles", 1)[1].split("</style>", 1)[0], page.name
        assert "--pl-text: var(--color-on-surface);" in text, page.name
    row = read(p / SPECIMEN_REL)
    assert "#b8b8b8" in row[row.index('data-token="color.text-muted"'):]  # the token itself is still shown as it is


def test_suggest_rules_have_a_weight_and_a_why() -> None:
    for r in A.RULES:
        assert isinstance(r.weight, int) and r.weight >= 1, r.id
        if r.severity == "suggest":
            assert r.why and r.why.endswith("."), r.id


def test_report_custom_path_and_json_stdout(project: Path) -> None:
    r = audit(project, "--json", "--html", "out/report.html")
    assert r.returncode == 1
    json.loads(r.stdout)
    assert (project / "out/report.html").is_file()
    r = audit(project, "--html=out/second.html")
    assert r.returncode == 1 and (project / "out/second.html").is_file()


def test_report_is_styled_with_the_project_tokens(report: Path, project: Path) -> None:
    text = read(report)
    assert BT.css_vars(doc_of(project)) in text
    assert "--pl-accent: var(--color-primary);" in text
    assert "--pl-bad: var(--color-danger);" in text


def test_report_in_inconsistency_only_mode(tmp_path: Path) -> None:
    p = make_project(tmp_path / "proj")
    r = audit(p, "--no-tokens", "--html")
    assert r.returncode in (0, 1), r.stderr
    text = read(today_report(p))
    assert "inconsistency-only" in text
    assert "--color-primary" not in text  # no tokens: Plumb's neutral page colours only


def test_report_with_nothing_to_report(tmp_path: Path) -> None:
    p = make_project(tmp_path / "proj", app=False)
    write(p / "app/ok.tsx", "export const Ok = () => <p className=\"text-sm\">Fine</p>;\n")
    r = audit(p, "--html")
    assert r.returncode == 0, r.stdout + r.stderr
    text = read(today_report(p))
    assert "No errors or warnings" in text


def test_report_never_replaces_a_page_it_did_not_write(project: Path) -> None:
    # `audit.py --html app/landing.html` (meaning "audit this page") gives the page to --html: refused, bytes kept.
    page = "<!doctype html>\n<html><body><h1>Our landing page</h1></body></html>\r\n"
    write(project / "app/landing.html", page)
    before = (project / "app/landing.html").read_bytes()
    r = audit(project, "--html", "app/landing.html")
    assert_refusal(r, "app/landing.html is not an audit report (not written by audit.py): nothing was written",
                   "fix: put --html after the paths (audit.py <path> --html), or pass a new report path, "
                   "e.g. --html docs/design/audit.html")
    assert (project / "app/landing.html").read_bytes() == before
    # another tool's GENERATED page is not the audit's either
    write(project / "out/other.html", "<!doctype html>\n<!-- GENERATED by some-tool. Do not edit. -->\n<p>x</p>\n")
    assert_refusal(audit(project, "--html", "out/other.html"), "not an audit report")


def test_report_rewrites_its_own_report_and_an_empty_file(project: Path) -> None:
    assert audit(project, "--html", "out/r.html").returncode == 1
    first = read(project / "out/r.html")
    assert P.is_plumb_page(first, A.REPORT_HEADER)
    write(project / "out/r.html", first.replace("</body>", "<p>stale</p></body>"))
    assert audit(project, "--html", "out/r.html").returncode == 1
    assert "<p>stale</p>" not in read(project / "out/r.html")
    write(project / "out/empty.html", "")
    assert audit(project, "--html", "out/empty.html").returncode == 1
    assert P.is_plumb_page(read(project / "out/empty.html"), A.REPORT_HEADER)


_POSIX = os.name == "posix"


@pytest.mark.skipif(not _POSIX, reason="requires POSIX: FIFO")
def test_a_fifo_in_the_project_is_skipped_not_read(project: Path) -> None:
    os.mkfifo(project / "app/hang.css")
    for script, args in (("audit.py", ("--json",)), ("audit.py", ("app",)), ("audit.py", ("--html",)),
                         ("build-tokens.py", ("--check",))):
        try:
            r = subprocess.run([sys.executable, str(project / SKILL_REL / "scripts" / script), *args], cwd=str(project),
                               capture_output=True, text=True, encoding="utf-8", timeout=20)
        except subprocess.TimeoutExpired:
            pytest.fail(f"{script} {args} read the FIFO")
        assert r.returncode in (0, 1), (script, args, r.stdout, r.stderr)
        assert "Traceback" not in r.stderr
        assert "hang.css" not in r.stdout  # never audited


@pytest.mark.skipif(not _POSIX or not os.path.exists("/dev/zero"), reason="requires POSIX: /dev/zero")
def test_a_tokens_file_linked_to_a_device_is_refused_quickly(project: Path) -> None:
    tokens = project / TOKENS_REL
    tokens.unlink()
    tokens.symlink_to("/dev/zero")
    for script, args in (("build-tokens.py", ("--check",)), ("build-tokens.py", ()), ("audit.py", ("--json",))):
        try:
            r = subprocess.run([sys.executable, str(project / SKILL_REL / "scripts" / script), *args], cwd=str(project),
                               capture_output=True, text=True, encoding="utf-8", timeout=20)
        except subprocess.TimeoutExpired:
            pytest.fail(f"{script} {args} read /dev/zero")
        assert_refusal(r, "not a regular file")


@pytest.mark.skipif(not _POSIX, reason="requires POSIX: FIFO")
def test_report_never_writes_into_a_fifo(project: Path) -> None:
    os.mkfifo(project / "out.html")
    try:
        r = audit_t(project, "--html", "out.html")
    except subprocess.TimeoutExpired:
        pytest.fail("--html opened the FIFO")
    assert_refusal(r, "not an audit report")


@pytest.mark.skipif(not _POSIX, reason="requires POSIX: FIFO")
def test_the_tokens_build_never_writes_into_a_fifo(project: Path) -> None:
    (project / SPECIMEN_REL).unlink()
    os.mkfifo(project / SPECIMEN_REL)
    try:
        r = build_tokens_t(project)
    except subprocess.TimeoutExpired:
        pytest.fail("the build opened the FIFO")
    assert_refusal(r, "not a regular file", SPECIMEN_REL)


def build_tokens_t(project: Path, *args: str):
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts/build-tokens.py"), *args],
                          cwd=str(project), capture_output=True, text=True, encoding="utf-8", timeout=20)


def audit_t(project: Path, *args: str):
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts/audit.py"), *args], cwd=str(project),
                          capture_output=True, text=True, encoding="utf-8", timeout=20)


def test_report_refusals(project: Path, tmp_path: Path) -> None:
    assert_refusal(audit(project, "--html", "notes.txt"), "--html")
    assert_refusal(audit(project, "--quick", "app/page.tsx", "--html", "r.html"), "--quick")
    write(project / "blocker", "a file, not a folder\n")
    assert_refusal(audit(project, "--html", "blocker/r.html"), "cannot write")
    bare = make_project(tmp_path / "bare", templates=False)
    r = subprocess.run([sys.executable, str(bare / SKILL_REL / "scripts/audit.py"), "--html"], cwd=str(bare),
                       capture_output=True, text=True, encoding="utf-8")
    assert_refusal(r, "audit-report.html.tmpl")


# ---------------------------------------------------------------- browser (headless)


def _playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        pytest.skip("requires Playwright")
    return sync_playwright


@pytest.fixture(scope="module")
def browser():
    sync_playwright = _playwright()
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> dict:
    p = make_project(tmp_path_factory.mktemp("pages") / "proj")
    r = audit(p, "--html")
    assert r.returncode == 1, r.stderr
    data = json.loads(audit(p, "--json").stdout)
    return {"specimen": p / SPECIMEN_REL, "report": today_report(p), "data": data}


def _open(browser, path: Path, width: int, scheme: str, reduced: str = "no-preference"):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, reduced_motion=reduced)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    requests = []
    page.on("request", lambda req: requests.append(req.url) if not req.url.startswith(("file:", "data:", "about:")) else None)
    page.goto(path.resolve().as_uri())
    page.wait_for_load_state("load")
    return ctx, page, errors, requests


def _app_fonts(doc: dict) -> None:
    """Fonts an app loads through next/font: the variable exists only inside the app (live test 2, B13)."""
    doc["font"]["sans"]["$value"] = ["var(--font-geist-sans)", "Geist", "system-ui", "sans-serif"]
    doc["font"]["mono"]["$value"] = ["var(--font-geist-mono)"]


def test_plumbs_pages_give_app_font_variables_a_fallback(tmp_path: Path) -> None:
    p = make_project(tmp_path / "proj", mutate=_app_fonts)
    specimen = read(p / SPECIMEN_REL)
    assert ("--font-sans: var(--font-geist-sans, Geist, system-ui, sans-serif), Geist, system-ui, sans-serif;"
            in specimen)
    assert "--font-mono: var(--font-geist-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);" in specimen
    # the app's own CSS keeps the tokens as written (next/font defines the variable there)
    css = read(p / SKILL_REL / "assets/platforms/web/tokens.css")
    assert "--font-sans: var(--font-geist-sans), Geist, system-ui, sans-serif;" in css
    assert BT.page_font_value("--font-x", "var(--a, b), c") == "var(--a, b), c"  # a fallback is kept as it is
    assert BT.page_font_value("--font-x", "Inter, sans-serif") == "Inter, sans-serif"
    assert build_tokens(p, "--check").returncode == 0


def test_plumbs_pages_never_fall_back_to_serif(browser, tmp_path: Path) -> None:
    p = make_project(tmp_path / "proj", mutate=_app_fonts)
    assert audit(p, "--html").returncode == 1
    for path in (p / SPECIMEN_REL, today_report(p)):
        ctx, page, errors, _ = _open(browser, path, 1280, "light")
        try:
            family = page.evaluate("getComputedStyle(document.body).fontFamily")
            assert "system-ui" in family or "Geist" in family, (path.name, family)
            assert "serif" not in family.replace("sans-serif", ""), (path.name, family)
            mono = page.evaluate("getComputedStyle(document.querySelector('code') || document.body).fontFamily")
            assert "Times" not in mono, mono
        finally:
            ctx.close()


@pytest.mark.parametrize("name", ["specimen", "report"])
@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_page_renders_cleanly(browser, pages, name: str, width: int, scheme: str) -> None:
    ctx, page, errors, requests = _open(browser, pages[name], width, scheme)
    try:
        assert page.evaluate("document.documentElement.dataset.theme") == scheme
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 0, f"horizontal scroll of {overflow}px at {width}px"
        before = page.evaluate("getComputedStyle(document.body).backgroundColor")
        page.click("#theme-toggle")
        other = "dark" if scheme == "light" else "light"
        assert page.evaluate("document.documentElement.dataset.theme") == other
        after = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert after != before
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 0, f"horizontal scroll of {overflow}px at {width}px after the toggle"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement !== document.body")
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


def test_report_filters_and_every_finding(browser, pages) -> None:
    data = pages["data"]
    ctx, page, errors, _ = _open(browser, pages["report"], 1280, "light")
    try:
        visible = "() => [...document.querySelectorAll('li.finding')].filter(e => e.offsetParent !== null)"
        count = lambda sev=None: page.evaluate(  # noqa: E731
            f"({visible})().filter(e => !{json.dumps(sev)} || e.dataset.severity === {json.dumps(sev)}).length")
        assert count() == len(data["findings"])
        page.click('[data-filter-severity="error"]')
        assert count("error") == 0 and count("warn") == data["warnings"]
        page.click('[data-filter-severity="error"]')
        assert count("error") == data["errors"]
        page.select_option("#rule-filter", "hover-only")
        assert count() == sum(1 for f in data["findings"] if f["rule"] == "hover-only") >= 1
        page.select_option("#rule-filter", "")
        assert count() == len(data["findings"])
        page.click('[data-filter-severity="suggest"]')
        assert count("suggest") == 0
        assert errors == []
    finally:
        ctx.close()


def test_report_says_when_no_finding_matches_and_resets(browser, pages) -> None:
    data = pages["data"]
    ctx, page, errors, _ = _open(browser, pages["report"], 390, "dark")
    try:
        assert not page.is_visible("#none-match")
        for sev in ("error", "warn", "suggest"):
            page.click(f'[data-filter-severity="{sev}"]')
        assert page.is_visible("#none-match")
        assert "No findings match these filters" in page.inner_text("#none-match")
        page.click("#reset-filters")
        assert not page.is_visible("#none-match")
        visible = page.evaluate("[...document.querySelectorAll('li.finding')].filter(e => e.offsetParent !== null).length")
        assert visible == len(data["findings"])
        assert page.evaluate("document.getElementById('rule-filter').value") == ""
        assert errors == []
    finally:
        ctx.close()


def test_report_paths_wrap_only_at_separators(browser, pages) -> None:
    ctx, page, errors, _ = _open(browser, pages["report"], 390, "light")
    try:
        breaks = page.evaluate("""() => {
            const out = [];
            for (const loc of document.querySelectorAll('code.loc')) {
                const walker = document.createTreeWalker(loc, NodeFilter.SHOW_TEXT);
                let prevTop = null, prevChar = '';
                for (let n = walker.nextNode(); n; n = walker.nextNode()) {
                    for (let i = 0; i < n.length; i++) {
                        const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1);
                        const rect = r.getClientRects()[0];
                        if (!rect) continue;
                        if (prevTop !== null && rect.top > prevTop + 2) out.push(prevChar);
                        prevTop = rect.top; prevChar = n.data[i];
                    }
                }
            }
            return out;
        }""")
        assert breaks, "the long tokens path should wrap at 390px"
        assert set(breaks) == {"/"}, breaks
        assert errors == []
    finally:
        ctx.close()


def test_specimen_side_by_side_themes_use_the_token_values(browser, pages) -> None:
    ctx, page, errors, _ = _open(browser, pages["specimen"], 1280, "light")
    try:
        swatch = "document.querySelector('[data-token=\"color.background\"] .pl-{0} .swatch-chip')"
        light = page.evaluate(f"getComputedStyle({swatch.format('light')}).backgroundColor")
        dark = page.evaluate(f"getComputedStyle({swatch.format('dark')}).backgroundColor")
        assert light == "rgb(255, 255, 255)" and dark == "rgb(15, 18, 23)"
        page.click("#theme-toggle")
        assert page.evaluate(f"getComputedStyle({swatch.format('light')}).backgroundColor") == light
        n = page.evaluate("document.querySelectorAll('[data-component][data-state]').length")
        assert n == len(COMPONENTS) * len(STATES) * 2
        assert errors == []
    finally:
        ctx.close()


def test_specimen_motion_is_static_with_reduced_motion(browser, pages) -> None:
    ctx, page, errors, _ = _open(browser, pages["specimen"], 1280, "light", reduced="reduce")
    try:
        durations = page.evaluate("[...document.querySelectorAll('.motion-dot')].map(e => getComputedStyle(e).transitionDuration)")
        assert durations and all(d == "0s" for d in durations), durations
        assert errors == []
    finally:
        ctx.close()
    ctx, page, errors, _ = _open(browser, pages["specimen"], 1280, "light")
    try:
        durations = page.evaluate("[...document.querySelectorAll('.motion-dot')].map(e => getComputedStyle(e).transitionDuration)")
        assert "0.15s" in durations and "0.32s" in durations, durations
    finally:
        ctx.close()
