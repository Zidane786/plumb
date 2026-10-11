"""build-prototype.py: the main prototype (prototype.html), the catalogue (screens.html), the screen map (screens.json),
approvals, and the decisions panel, all assembled from one source file per screen.

Static checks run everywhere. The browser checks drive both pages headless and skip only when Playwright is not
importable.
"""

from __future__ import annotations

import datetime
import hashlib
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
FIXTURE = REPO / "tests/fixtures/prototype"
TOKENS_FIXTURE = REPO / "tests/fixtures/pages/tokens.json"
SKILL_REL = ".claude/skills/demo-design-system"
TOKENS_REL = f"{SKILL_REL}/assets/tokens/demo.tokens.json"
DOCS = "docs/design"
PROTO_REL = f"{DOCS}/prototype.html"
CATALOGUE_REL = f"{DOCS}/screens.html"
JSON_REL = f"{DOCS}/prototype/screens.json"
SCREENS_REL = f"{DOCS}/prototype/screens"
SCREENS = {"home": ["ready", "empty", "loading"], "booking": ["ready", "error", "success"], "menu": ["ready", "empty"]}
TITLES = {"home": "Today's tables", "booking": "New booking", "menu": "Menü du jour · Café Ünïcode ☕"}
CONTROL_STATES = ("default", "hover", "focus", "pressed", "disabled", "loading")
CONTROLS = ("button-primary", "button-secondary", "input", "chip", "link")

sys.path.insert(0, str(SCRIPTS))
import _plumb as P  # noqa: E402


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


BT = _load("plumb_build_tokens_for_proto", "build-tokens.py")
BP = _load("plumb_build_prototype", "build-prototype.py")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def make_project(dest: Path, screens: bool = True, decisions: bool = True, build: bool = True, mutate=None) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    skill = dest / SKILL_REL
    (skill / "scripts").mkdir(parents=True, exist_ok=True)
    for name in ("_plumb.py", "build-tokens.py", "build-prototype.py"):
        shutil.copy(SCRIPTS / name, skill / "scripts" / name)
    (skill / "templates").mkdir(parents=True, exist_ok=True)
    for tpl in TEMPLATES.glob("*.tmpl"):
        shutil.copy(tpl, skill / "templates" / tpl.name)
    doc = json.loads(read(TOKENS_FIXTURE))
    if mutate:
        mutate(doc)
    write(dest / TOKENS_REL, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    write(skill / "assets/platforms/web/tokens.css.template", read(WEB_TEMPLATES / "tokens.css.template.tailwind-v4"))
    write(dest / "PLUMB.md", "Project: demo\n")
    if screens:
        shutil.copytree(FIXTURE / "screens", dest / SCREENS_REL)
    if decisions:
        write(dest / DOCS / "decisions.md", read(FIXTURE / "decisions.md"))
    if build:
        r = run(dest)
        assert r.returncode == 0, r.stdout + r.stderr
    return dest


def clean_env(tmp: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    empty = tmp / "empty-gitconfig"
    empty.write_text("", encoding="utf-8")
    env.update({"GIT_CONFIG_GLOBAL": str(empty), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CEILING_DIRECTORIES": str(tmp)})
    env.update(extra)
    return env


def run(project: Path, *args: str, env: dict = None):
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts/build-prototype.py"), *args],
                          cwd=str(project), capture_output=True, text=True, encoding="utf-8", env=env)


def build_tokens(project: Path, *args: str):
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts/build-tokens.py"), *args],
                          cwd=str(project), capture_output=True, text=True, encoding="utf-8")


def screens_json(project: Path) -> dict:
    return json.loads(read(project / JSON_REL))


def entry(project: Path, screen: str) -> dict:
    return next(s for s in screens_json(project)["screens"] if s["id"] == screen)


def file_hash(path: Path) -> str:
    return hashlib.sha256(P.normalise_text(read(path)).encode("utf-8")).hexdigest()


def assert_refusal(r, *needles: str) -> None:
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "error: " in r.stderr and "\nfix: " in r.stderr, r.stderr
    assert "Traceback" not in r.stderr
    for n in needles:
        assert n in r.stderr, r.stderr


def block(page: str, attr: str, value: str) -> str:
    """The HTML of the element carrying attr="value" up to the next element with the same attribute (or the end)."""
    start = page.index(f'{attr}="{value}"')
    nxt = page.find(f'{attr}="', start + len(attr) + len(value) + 3)
    return page[start: nxt if nxt != -1 else len(page)]


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "Café Ünïcode")


NETWORK = re.compile(r"""(?:\b(?:src|href|action|poster|data)\s*=\s*["']?\s*https?:|@import\s+(?:url\()?\s*["']?\s*https?:"""
                     r"""|url\(\s*["']?\s*https?:|\bimport\s*\(\s*["']https?:|//fonts\.|cdn\.)""", re.I)


# ---------------------------------------------------------------- assembling the pages


def test_build_writes_both_pages_and_the_map_with_generated_headers(project: Path) -> None:
    for rel in (PROTO_REL, CATALOGUE_REL, JSON_REL):
        text = read(project / rel)
        assert P.is_generated_text(text), rel
        assert "build-prototype.py" in "\n".join(text.splitlines()[:5]), rel
    for rel in (PROTO_REL, CATALOGUE_REL):
        text = read(project / rel)
        assert text.startswith("<!doctype html>")
        assert '<meta charset="utf-8">' in text[:3000].lower()
        assert '<meta name="viewport"' in text[:3000]


def test_prototype_has_nav_routing_states_toggles_and_the_player_mount(project: Path) -> None:
    page = read(project / PROTO_REL)
    nav = page[page.index('class="pp-nav"'):]
    order = [nav.index(f'href="#screen-{sid}"') for sid in SCREENS]
    assert order == sorted(order), "nav follows data-order"
    for sid, states in SCREENS.items():
        assert f'data-screen="{sid}"' in page
        group = block(page, "data-states-for", sid)
        assert [m for m in re.findall(r'data-set-state="([^"]+)"', group)] == states
    assert 'data-viewport="phone"' in page and 'data-viewport="desktop"' in page
    assert 'id="theme-toggle"' in page
    assert 'id="plumb-player"' in page and 'id="plumb-guide"' in page
    assert "window.plumbPrototype" in page
    assert 'href="screens.html"' in page
    assert "#decisions" in page


def test_token_block_is_the_css_vars_export_between_markers(project: Path) -> None:
    css = BT.css_vars(P.load_tokens(project / TOKENS_REL))
    for rel in (PROTO_REL, CATALOGUE_REL):
        page = read(project / rel)
        inner = page.split("/* plumb:tokens */", 1)[1].split("/* plumb:tokens:end */", 1)[0]
        assert inner.strip("\n") == css.strip("\n"), rel


def test_catalogue_has_every_screen_state_in_both_themes(project: Path) -> None:
    page = read(project / CATALOGUE_REL)
    for sid, states in SCREENS.items():
        assert f'id="screen-{sid}"' in page
        for state in states:
            for theme in ("light", "dark"):
                copy = block(page, "data-copy", f"{sid}/{state}/{theme}")
                assert f"pl-{theme}" in page[page.rindex("<", 0, page.index(f'data-copy="{sid}/{state}/{theme}"')):][:200]
                shown = re.findall(r'<div data-state="([^"]+)"', copy)
                hidden = re.findall(r'<div hidden data-state="([^"]+)"', copy)
                assert shown == [state], (sid, state, theme, shown)
                assert sorted(hidden) == sorted(s for s in states if s != state)
    assert page.count('data-copy="') == 2 * sum(len(s) for s in SCREENS.values())


def test_catalogue_control_state_sheet_in_both_themes(project: Path) -> None:
    page = read(project / CATALOGUE_REL)
    sheet = page[page.index('id="controls"'):]
    for theme in ("light", "dark"):
        panel = sheet[sheet.index(f'pl-{theme} '):]
        for comp in CONTROLS:
            for state in CONTROL_STATES:
                assert f'data-component="{comp}" data-state="{state}"' in panel, (theme, comp, state)
    assert "--pl-accent: var(--color-primary);" in page  # the controls are drawn from the project's tokens


def test_catalogue_nav_and_links(project: Path) -> None:
    page = read(project / CATALOGUE_REL)
    nav = page[page.index('class="sc-nav '):]
    for sid in SCREENS:
        assert f'href="#screen-{sid}"' in nav
    assert 'href="#controls"' in nav and 'href="#decisions"' in nav and 'href="prototype.html"' in nav
    # a state has the same address on both pages: #screen-ID/STATE
    assert 'href="#screen-home/empty"' in nav and 'id="screen-home/empty"' in page


def test_screen_styles_and_scripts_are_inlined_and_scoped(project: Path) -> None:
    for rel in (PROTO_REL, CATALOGUE_REL):
        page = read(project / rel)
        assert '[data-screen="booking"] form' in page
        assert page.count('screen.setAttribute("data-script-ran", "yes");') == 1
        define = page[page.index('plumbScreens.define("booking"'):]
        assert define.index("function (screen, plumb)") < define.index('screen.setAttribute("data-script-ran"')
        assert "<script data-screen-script" not in page  # the source tag is replaced by the wrapped function


def test_unicode_titles_are_escaped_and_shown(project: Path) -> None:
    for rel in (PROTO_REL, CATALOGUE_REL):
        page = read(project / rel)
        assert html.escape(TITLES["menu"]) in page or TITLES["menu"] in page
        assert "Today&#x27;s tables" in page or "Today's tables" in page
    assert entry(project, "menu")["title"] == TITLES["menu"]


def test_pages_load_nothing_from_the_network(project: Path) -> None:
    for rel in (PROTO_REL, CATALOGUE_REL):
        page = read(project / rel)
        assert not NETWORK.search(page), (rel, NETWORK.search(page).group(0))
        assert not re.search(r"<link\b", page, re.I), rel
        assert not re.search(r"<script[^>]+\bsrc=", page, re.I), rel


def test_docs_dir_setting_moves_everything(tmp_path: Path) -> None:
    def mutate(doc):
        doc["$extensions"]["plumb"]["docs_dir"] = "design-docs"

    p = make_project(tmp_path / "p", build=False, mutate=mutate)
    shutil.copytree(p / SCREENS_REL, p / "design-docs/prototype/screens")
    shutil.rmtree(p / DOCS)
    r = run(p)
    assert r.returncode == 0, r.stderr
    for name in ("prototype.html", "screens.html", "prototype/screens.json"):
        assert (p / "design-docs" / name).is_file(), name


# ---------------------------------------------------------------- decisions


def test_decisions_panel_shows_the_entries_naming_each_screen(project: Path) -> None:
    page = read(project / PROTO_REL)
    wanted = {
        "home": {"DS-20261001-direction", "DS-20261009-tables-list"},
        "booking": {"DS-20261001-direction", "DS-20261005-booking-form"},
        "menu": {"DS-20261001-direction", "DS-20261009-tables-list"},
    }
    for sid, ids in wanted.items():
        panel = page[page.index(f'data-why-for="{sid}"'):]
        panel = panel[: panel.index("</section>")]
        assert set(re.findall(r'data-decision="([^"]+)"', panel)) == ids, sid
    booking = page[page.index('data-why-for="booking"'):]
    booking = booking[: booking.index("</section>")]
    assert "Łukasz Wójcik" in booking and "2026-10-05" in booking
    assert "one page form, three-step wizard" in booking
    assert 'href="prototype/proposals/booking/index.html"' in booking
    assert "&lt;em&gt;No wizard.&lt;/em&gt;" in booking and "<em>" not in booking
    assert "Why it looks like this" in page


def test_decisions_page_in_both_pages(project: Path) -> None:
    for rel in (PROTO_REL, CATALOGUE_REL):
        page = read(project / rel)
        section = page[page.index('id="decisions"'):]
        ids = re.findall(r'id="decision-(DS-[^"]+)"', section)
        assert ids == ["DS-20261009-tables-list", "DS-20261005-booking-form", "DS-20261001-direction"], rel
        assert "Not a decision heading" not in section
        tables = section[section.index('id="decision-DS-20261009-tables-list"'):]
        assert "2026-10-09" in tables[:4000]  # the date comes from the id when there is no Date line
        assert "山田 花子" in tables[:4000]
        assert 'href="#screen-home"' in tables[:4000]


def test_no_decisions_file_gives_empty_panels(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", decisions=False)
    page = read(p / PROTO_REL)
    assert 'data-decision="' not in page
    assert "No decisions recorded" in page


def test_unreadable_decisions_file_warns_and_still_builds(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", decisions=False, build=False)
    (p / DOCS / "decisions.md").write_bytes(b"## DS-20261001-x \xff\xfe broken\n- Screens: home\n")
    r = run(p)
    assert r.returncode == 0, r.stderr
    assert "decisions.md" in r.stderr and "Traceback" not in r.stderr
    assert 'data-decision="' not in read(p / PROTO_REL)


# ---------------------------------------------------------------- screens.json: map, approve, synced


def test_screens_json_schema_for_new_screens(project: Path) -> None:
    data = screens_json(project)
    assert data["version"] == 1
    assert [s["id"] for s in data["screens"]] == list(SCREENS)
    for s in data["screens"]:
        assert list(s) == ["id", "title", "states", "route", "files", "files_hash", "approved", "synced_from_code", "status"]
        assert s["states"] == SCREENS[s["id"]]
        assert s["title"] == TITLES[s["id"]]
        assert (s["route"], s["files"], s["files_hash"], s["approved"], s["synced_from_code"], s["status"]) == \
            (None, [], None, None, False, "to-build")


def test_map_sets_route_files_hash_and_status(project: Path) -> None:
    r = run(project, "--map", "booking", "--route", "/bookings/new", "--files", "app/bookings/new/**,components/booking-form.tsx")
    assert r.returncode == 0, r.stderr
    e = entry(project, "booking")
    assert e["route"] == "/bookings/new"
    assert e["files"] == ["app/bookings/new/**", "components/booking-form.tsx"]
    assert e["files_hash"] is None and e["status"] == "to-build"
    write(project / "app/bookings/new/page.tsx", "export default function Page() { return null }\n")
    write(project / "components/booking-form.tsx", "export function BookingForm() { return null }\n")
    assert run(project, "--check").returncode == 1  # the files now exist: the map's status is stale
    assert run(project).returncode == 0
    assert entry(project, "booking")["status"] == "built"
    assert run(project, "--map", "booking", "--route", "/bookings/new", "--files", "app/bookings/new/**",
               "components/booking-form.tsx").returncode == 0
    e = entry(project, "booking")
    assert re.fullmatch(r"[0-9a-f]{64}", e["files_hash"])
    # CRLF in a source file does not change the hash
    first = e["files_hash"]
    (project / "components/booking-form.tsx").write_bytes(b"export function BookingForm() { return null }\r\n")
    assert run(project, "--map", "booking", "--route", "/bookings/new", "--files", "app/bookings/new/**,components/booking-form.tsx").returncode == 0
    assert entry(project, "booking")["files_hash"] == first
    assert run(project, "--check").returncode == 0


def test_map_refusals(project: Path) -> None:
    assert_refusal(run(project, "--map", "nope", "--route", "/x", "--files", "app/x/**"), "nope", "booking")
    assert_refusal(run(project, "--map", "home", "--route", "/"), "--files")
    assert_refusal(run(project, "--route", "/"), "--map")
    assert_refusal(run(project, "--map", "home", "--route", " ", "--files", "app/page.tsx"), "--route")
    assert_refusal(run(project, "--map", "home", "--route", "/", "--files", "../outside/**"), "../outside/**")
    assert_refusal(run(project, "--map", "home", "--route", "/", "--files", "/etc/passwd"), "/etc/passwd")


def test_approve_records_git_user_date_and_screen_hash(project: Path, tmp_path: Path) -> None:
    env = clean_env(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True, env=env)
    subprocess.run(["git", "config", "user.name", "Zoë Tester"], cwd=str(project), check=True, env=env)
    r = run(project, "--approve", "booking", env=env)
    assert r.returncode == 0, r.stderr
    approved = entry(project, "booking")["approved"]
    assert approved == {"by": "Zoë Tester", "at": datetime.date.today().isoformat(),
                        "hash": file_hash(project / SCREENS_REL / "booking.html")}
    assert entry(project, "home")["approved"] is None
    page = read(project / PROTO_REL)
    nav = page[page.index('class="pp-nav"'):]
    assert 'data-approval="approved"' in nav[nav.index('data-nav="booking"'):][:600]
    # editing the screen afterwards makes the approval stale: reported, not removed
    path = project / SCREENS_REL / "booking.html"
    write(path, read(path).replace("Book the table", "Book this table"))
    r = run(project, env=env)
    assert r.returncode == 0
    assert "screen booking changed since Zoë Tester approved it" in r.stdout
    assert entry(project, "booking")["approved"] == approved
    nav = read(project / PROTO_REL)
    nav = nav[nav.index('class="pp-nav"'):]
    assert 'data-approval="stale"' in nav[nav.index('data-nav="booking"'):][:600]


def test_approve_falls_back_to_the_user_variable(project: Path, tmp_path: Path) -> None:
    env = clean_env(tmp_path, USER="fallback-user", USERNAME="fallback-user")
    r = run(project, "--approve", "home", env=env)
    assert r.returncode == 0, r.stderr
    assert entry(project, "home")["approved"]["by"] == "fallback-user"


def test_approve_and_synced_refusals(project: Path) -> None:
    assert_refusal(run(project, "--approve", "ghost"), "ghost")
    assert_refusal(run(project, "--synced", "ghost"), "ghost")
    assert_refusal(run(project, "--check", "--approve", "home"), "--check")


def test_synced_marks_and_approve_clears_it(project: Path, tmp_path: Path) -> None:
    env = clean_env(tmp_path, USER="someone")
    assert run(project, "--synced", "menu", env=env).returncode == 0
    assert entry(project, "menu")["synced_from_code"] is True
    page = read(project / PROTO_REL)
    assert 'data-approval="synced"' in page[page.index('data-nav="menu"'):][:600]
    assert run(project, "--approve", "menu", env=env).returncode == 0
    e = entry(project, "menu")
    assert e["synced_from_code"] is False and e["approved"]["by"] == "someone"


def test_map_survives_a_rebuild_and_a_removed_screen_is_dropped(project: Path) -> None:
    assert run(project, "--map", "home", "--route", "/", "--files", "app/page.tsx").returncode == 0
    (project / SCREENS_REL / "menu.html").unlink()
    r = run(project)
    assert r.returncode == 0
    assert "menu" in r.stdout
    data = screens_json(project)
    assert [s["id"] for s in data["screens"]] == ["home", "booking"]
    assert entry(project, "home")["route"] == "/"
    assert 'data-screen="menu"' not in read(project / PROTO_REL)


def test_screens_json_hand_edit_is_reported_by_check(project: Path) -> None:
    path = project / JSON_REL
    data = screens_json(project)
    data["screens"][0]["title"] = "Edited by hand"
    write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    r = run(project, "--check")
    assert r.returncode == 1 and JSON_REL in r.stdout
    write(path, "{ not json")
    assert_refusal(run(project), "screens.json")


# ---------------------------------------------------------------- --check, idempotence


def test_check_is_clean_after_a_build_and_crlf_is_not_stale(project: Path) -> None:
    r = run(project, "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    page = project / PROTO_REL
    page.write_bytes(read(page).replace("\n", "\r\n").encode("utf-8"))
    assert run(project, "--check").returncode == 0


def test_check_names_a_stale_page_and_writes_nothing(project: Path) -> None:
    path = project / SCREENS_REL / "home.html"
    write(path, read(path).replace("No bookings yet today.", "Nothing booked yet."))
    before = read(project / PROTO_REL)
    r = run(project, "--check")
    assert r.returncode == 1
    assert PROTO_REL in r.stdout and CATALOGUE_REL in r.stdout and JSON_REL not in r.stdout
    assert "fix: " in r.stdout and "build-prototype.py" in r.stdout
    assert read(project / PROTO_REL) == before


def test_check_names_a_stale_token_block(project: Path) -> None:
    doc = json.loads(read(project / TOKENS_REL))
    doc["color"]["primary"]["$value"] = "#0b5a56"
    write(project / TOKENS_REL, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    r = run(project, "--check")
    assert r.returncode == 1
    assert "token block" in r.stdout and PROTO_REL in r.stdout and CATALOGUE_REL in r.stdout


def test_check_names_new_states_in_the_map(project: Path) -> None:
    path = project / SCREENS_REL / "menu.html"
    write(path, read(path).replace("</section>", '  <div data-state="offline"><p>Offline.</p></div>\n</section>'))
    r = run(project, "--check")
    assert r.returncode == 1 and JSON_REL in r.stdout
    assert run(project).returncode == 0
    assert entry(project, "menu")["states"] == ["ready", "empty", "offline"]


def test_check_missing_outputs(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    r = run(p, "--check")
    assert r.returncode == 1 and PROTO_REL in r.stdout


def test_idempotent(project: Path) -> None:
    before = {rel: (project / rel).read_bytes() for rel in (PROTO_REL, CATALOGUE_REL, JSON_REL)}
    r = run(project)
    assert r.returncode == 0
    assert "wrote" not in r.stdout
    assert {rel: (project / rel).read_bytes() for rel in before} == before


def test_crlf_screen_files_give_identical_output(project: Path, tmp_path: Path) -> None:
    other = make_project(tmp_path / "crlf", build=False)
    for f in (other / SCREENS_REL).glob("*.html"):
        f.write_bytes(read(f).replace("\n", "\r\n").encode("utf-8"))
    assert run(other).returncode == 0
    for rel in (PROTO_REL, CATALOGUE_REL, JSON_REL):
        assert (other / rel).read_bytes() == (project / rel).read_bytes(), rel


# ---------------------------------------------------------------- refusals


def test_screen_without_states_is_refused_naming_the_file(project: Path) -> None:
    write(project / SCREENS_REL / "empty.html", '<section data-screen="empty" data-title="Empty">\n  <p>Hi</p>\n</section>\n')
    r = run(project)
    assert_refusal(r, f"{SCREENS_REL}/empty.html", "data-state")
    assert re.search(r"empty\.html:1\b", r.stderr), r.stderr


def test_screen_id_must_match_the_file_name(project: Path) -> None:
    write(project / SCREENS_REL / "about.html", '\n<section data-screen="abuot"><div data-state="ready"></div></section>\n')
    r = run(project)
    assert_refusal(r, "about.html:2", "abuot")


def test_duplicate_screen_sections_are_refused(project: Path) -> None:
    write(project / SCREENS_REL / "dup.html", '<section data-screen="dup"><div data-state="a"></div></section>\n'
                                              '<section data-screen="dup"><div data-state="b"></div></section>\n')
    assert_refusal(run(project), "dup.html:2", "duplicate")


def test_file_without_a_screen_section_is_refused(project: Path) -> None:
    write(project / SCREENS_REL / "loose.html", "<div data-state='ready'>no section</div>\n")
    assert_refusal(run(project), "loose.html", "data-screen")


def test_plain_script_is_refused(project: Path) -> None:
    write(project / SCREENS_REL / "js.html", '<section data-screen="js"><div data-state="ready"></div></section>\n'
                                             '<script>alert(1)</script>\n')
    assert_refusal(run(project), "js.html:2", "data-screen-script")


def test_unicode_screen_id_works(project: Path) -> None:
    write(project / SCREENS_REL / "résumé.html", '<section data-screen="résumé" data-title="Résumé">'
                                                 '<div data-state="ready">Ok</div></section>\n')
    assert run(project).returncode == 0
    assert 'href="#screen-résumé"' in read(project / PROTO_REL)
    assert entry(project, "résumé")["states"] == ["ready"]


def test_bad_screen_id_is_refused(project: Path) -> None:
    write(project / SCREENS_REL / "two words.html", '<section data-screen="two words"><div data-state="a"></div></section>\n')
    assert_refusal(run(project), "two words")


def test_no_screens_is_refused_but_check_is_quiet(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", screens=False, build=False)
    assert_refusal(run(p), "prototype/screens")
    r = run(p, "--check")
    assert r.returncode == 0 and "no screen" in r.stdout


def test_missing_template_is_refused(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    (p / SKILL_REL / "templates/screens.html.tmpl").unlink()
    assert_refusal(run(p), "screens.html.tmpl")


def test_bad_arguments_are_shaped(project: Path) -> None:
    assert_refusal(run(project, "--nope"))


# ---------------------------------------------------------------- review fixes (round 1)


def test_screens_link_points_at_the_first_screen(project: Path) -> None:
    page = read(project / PROTO_REL)
    assert 'id="pp-screens-link" href="#screen-home"' in page


def test_build_tokens_refreshes_the_prototype_token_blocks(project: Path) -> None:
    doc = json.loads(read(project / TOKENS_REL))
    doc["color"]["primary"]["$value"] = "#0b5a56"
    doc["typography"]["base"]["$extensions"]["plumb"]["md"]["fontSize"] = "17px"
    write(project / TOKENS_REL, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    r = build_tokens(project, "--check")
    assert r.returncode == 1
    assert f"stale: {PROTO_REL} (prototype token block)" in r.stdout
    assert f"stale: {CATALOGUE_REL} (prototype token block)" in r.stdout
    r = build_tokens(project)
    assert r.returncode == 0, r.stderr
    assert f"wrote {PROTO_REL}" in r.stdout and f"wrote {CATALOGUE_REL}" in r.stdout
    for rel in (PROTO_REL, CATALOGUE_REL):
        page = read(project / rel)
        assert "--color-primary: #0b5a56;" in page
        container = page[page.index("@container plumb-frame (min-width: 48rem)"):]
        assert "--text-base: 17px;" in container[:400]
    # one tokens build leaves nothing for build-prototype to do, and both checks agree
    assert run(project, "--check").returncode == 0, run(project, "--check").stdout
    assert build_tokens(project, "--check").returncode == 0
    before = {rel: (project / rel).read_bytes() for rel in (PROTO_REL, CATALOGUE_REL)}
    assert "wrote" not in run(project).stdout
    assert {rel: (project / rel).read_bytes() for rel in before} == before


def test_build_tokens_leaves_projects_without_a_prototype_alone(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", screens=False, build=False)
    r = build_tokens(p)
    assert r.returncode == 0, r.stderr
    assert not (p / PROTO_REL).exists() and not (p / CATALOGUE_REL).exists()


def test_unsafe_decision_urls_stay_plain_text(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", decisions=False, build=False)
    write(p / DOCS / "decisions.md", "## DS-20261010-urls · Links\n"
          "- Why: [a](javascript:alert(1)) [b](JAVASCRIPT:alert(2)) [c](data:text/html,hi) [d](VbScript:msgbox)\n"
          "- Options: [e]( javascript:alert(3)) and [ok](prototype/proposals/x/index.html)\n- Screens: home\n")
    assert run(p).returncode == 0
    for rel in (PROTO_REL, CATALOGUE_REL):
        page = read(p / rel)
        assert not re.search(r"href\s*=\s*[\"']\s*(?:javascript|data|vbscript):", page, re.I), rel
        assert "[a](javascript:alert(1))" in page and "[d](VbScript:msgbox)" in page
        assert 'href="prototype/proposals/x/index.html"' in page


def test_inline_markup_cuts_code_spans_first() -> None:
    out = BP.inline("see [x](a`b`c) and `**y** [z](u)` then **bold** and [ok](p.html)")
    assert "<code>" not in "".join(re.findall(r'href="[^"]*"', out))
    assert "<code>**y** [z](u)</code>" in out
    assert "<strong>bold</strong>" in out and '<a href="p.html">ok</a>' in out
    assert BP.inline("`<b>`") == "<code>&lt;b&gt;</code>"


def test_globs_read_back_from_the_map_are_checked(project: Path) -> None:
    data = screens_json(project)
    data["screens"][0]["files"] = ["../outside/**"]
    write(project / JSON_REL, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    for args in ((), ("--check",)):
        assert_refusal(run(project, *args), "screens.json", "../outside/**", "--map")


def test_argument_errors_name_the_project_relative_script(project: Path) -> None:
    r = run(project, "--nope")
    assert_refusal(r, f"fix: python3 {SKILL_REL}/scripts/build-prototype.py ")


def test_unscoped_screen_styles_warn_with_file_and_line(project: Path) -> None:
    write(project / SCREENS_REL / "loose.html", '<style>\n[data-screen="loose"] p { margin: 0; }\n.loose, '
          '[data-screen="loose"] h2 { color: red; }\n@media (min-width: 1px) {\n  body { margin: 0; }\n}\n'
          '@keyframes k { from { opacity: 0; } to { opacity: 1; } }\n/* .commented { } */\n</style>\n'
          '<section data-screen="loose"><div data-state="ready">Hi</div></section>\n')
    r = run(project)
    assert r.returncode == 0, r.stderr
    assert f'{SCREENS_REL}/loose.html:3: the style rule ".loose"' in r.stderr
    assert f'{SCREENS_REL}/loose.html:5: the style rule "body"' in r.stderr
    assert r.stderr.count("warning: ") == 2, r.stderr
    assert 'fix: start each selector' in r.stderr
    clean = make_project(project.parent / "clean", build=False)
    assert "warning" not in run(clean).stderr


SIGNUP = ('<section data-screen="signup" data-title="Sign up">\n'
          '  <div data-state="ready"><label for="email">Email</label><input id="email" aria-describedby="email-hint '
          'other"><p id="email-hint">We never share it.</p><a href="#email">Jump</a></div>\n'
          '  <div data-state="error"><label for="email2">Email</label><input id="email2"></div>\n'
          '</section>\n')


def test_catalogue_copies_get_their_own_ids(project: Path) -> None:
    write(project / SCREENS_REL / "signup.html", SIGNUP)
    assert run(project).returncode == 0
    page = read(project / CATALOGUE_REL)
    ids = re.findall(r'\sid="([^"]+)"', page)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert dupes == [], dupes
    for theme in ("light", "dark"):
        copy = block(page, "data-copy", f"signup/ready/{theme}")
        label = re.search(r'<label for="([^"]+)"', copy).group(1)
        assert f'<input id="{label}" aria-describedby="email-hint{label[len("email"):]} other"' in copy
        assert f'href="#{label}"' in copy
    proto = read(project / PROTO_REL)
    assert '<label for="email">' in proto and '<input id="email" aria-describedby="email-hint other">' in proto


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
def built(tmp_path_factory) -> Path:
    return make_project(tmp_path_factory.mktemp("proto") / "Café Ünïcode")


def _open(browser, path: Path, width: int = 1280, scheme: str = "light", hash_: str = ""):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
    page = ctx.new_page()
    errors: list = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    requests: list = []
    page.on("request", lambda req: requests.append(req.url) if not req.url.startswith(("file:", "data:", "about:")) else None)
    page.goto(path.resolve().as_uri() + hash_)
    page.wait_for_load_state("load")
    return ctx, page, errors, requests


def _visible_screen(page) -> str:
    return page.evaluate("""() => [...document.querySelectorAll('#pp-frame > [data-screen]')]
        .filter(s => !s.hidden && s.offsetParent !== null).map(s => s.dataset.screen).join(',')""")


def _visible_states(page, screen: str) -> list:
    return page.evaluate("""(id) => [...document.querySelectorAll('#pp-frame > [data-screen="' + id + '"] [data-state]')]
        .filter(e => e.offsetParent !== null).map(e => e.dataset.state)""", screen)


@pytest.mark.parametrize("name", [PROTO_REL, CATALOGUE_REL])
@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_pages_render_cleanly(browser, built, name: str, width: int, scheme: str) -> None:
    ctx, page, errors, requests = _open(browser, built / name, width, scheme)
    try:
        assert page.evaluate("document.documentElement.dataset.theme") == scheme
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 0, f"horizontal scroll of {overflow}px at {width}px"
        before = page.evaluate("getComputedStyle(document.body).backgroundColor")
        page.click("#theme-toggle")
        assert page.evaluate("document.documentElement.dataset.theme") == ("dark" if scheme == "light" else "light")
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") != before
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 0, f"horizontal scroll of {overflow}px at {width}px after the toggle"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement !== document.body")
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


def test_navigation_by_nav_and_in_screen_links(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        assert _visible_screen(page) == "home"
        page.click('.pp-nav [data-nav="menu"]')
        assert _visible_screen(page) == "menu"
        assert page.evaluate("location.hash") == "#screen-menu"
        page.click('.pp-nav [data-nav="home"]')
        page.click('#pp-frame [data-screen="home"] [data-test="new-booking"]')
        assert _visible_screen(page) == "booking"
        assert page.evaluate("document.title").startswith("New booking")
        page.go_back()
        assert _visible_screen(page) == "home"
        assert errors == [], errors
    finally:
        ctx.close()


def test_opening_a_hash_shows_that_screen_and_state(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, hash_="#screen-menu/empty")
    try:
        assert _visible_screen(page) == "menu"
        assert _visible_states(page, "menu") == ["empty"]
        assert errors == []
    finally:
        ctx.close()


def test_state_switcher(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        assert _visible_states(page, "home") == ["ready"]
        group = '[data-states-for="home"]'
        assert page.locator(f"{group} [data-set-state]").all_inner_texts() == ["Ready", "Empty", "Loading"]
        page.click(f'{group} [data-set-state="empty"]')
        assert _visible_states(page, "home") == ["empty"]
        assert page.get_attribute(f'{group} [data-set-state="empty"]', "aria-pressed") == "true"
        assert page.evaluate("location.hash") == "#screen-home/empty"
        page.click('.pp-nav [data-nav="booking"]')
        assert page.is_visible('[data-states-for="booking"]') and not page.is_visible(group)
        assert errors == []
    finally:
        ctx.close()


def test_viewport_toggle(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        wide = page.evaluate("document.getElementById('pp-frame').getBoundingClientRect().width")
        page.click('[data-viewport="phone"]')
        narrow = page.evaluate("document.getElementById('pp-frame').getBoundingClientRect().width")
        assert narrow <= 390 and narrow < wide
        assert page.get_attribute('[data-viewport="phone"]', "aria-pressed") == "true"
        page.click('[data-viewport="desktop"]')
        assert page.evaluate("document.getElementById('pp-frame').getBoundingClientRect().width") == wide
        assert errors == []
    finally:
        ctx.close()


def test_theme_toggle_switches_the_screen_tokens(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        bg = "getComputedStyle(document.querySelector('#pp-frame > [data-screen=\"home\"]')).backgroundColor"
        assert page.evaluate(bg) == "rgb(255, 255, 255)"
        page.click("#theme-toggle")
        assert page.evaluate(bg) == "rgb(15, 18, 23)"
        page.evaluate("window.plumbPrototype.setTheme('light')")
        assert page.evaluate(bg) == "rgb(255, 255, 255)"
        assert errors == []
    finally:
        ctx.close()


def test_screen_script_runs_and_drives_state(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, hash_="#screen-booking")
    try:
        assert page.get_attribute('#pp-frame [data-screen="booking"]', "data-script-ran") == "yes"
        page.click('#pp-frame [data-test="save"]')
        assert page.is_visible('#pp-frame [data-test="guest-error"]')
        page.fill('#pp-frame [data-test="guest"]', "Zoë")
        page.click('#pp-frame [data-test="save"]')
        assert _visible_states(page, "booking") == ["success"]
        assert page.get_attribute('[data-states-for="booking"] [data-set-state="success"]', "aria-pressed") == "true"
        assert errors == []
    finally:
        ctx.close()


def test_the_api_for_the_player(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        assert page.evaluate("window.plumbPrototype.screens.map(s => s.id)") == list(SCREENS)
        assert page.evaluate("window.plumbPrototype.screens[2].states") == SCREENS["menu"]
        page.evaluate("window.plumbPrototype.go('menu', 'empty')")
        assert _visible_screen(page) == "menu" and _visible_states(page, "menu") == ["empty"]
        page.evaluate("window.plumbPrototype.setViewport('phone')")
        assert page.evaluate("document.getElementById('pp-frame').getBoundingClientRect().width") <= 390
        seen = page.evaluate("""() => { var got = []; window.plumbPrototype.on(e => got.push(e.screen + '/' + e.state));
            window.plumbPrototype.go('home'); return got; }""")
        assert seen == ["home/ready"]
        assert page.evaluate("document.getElementById('plumb-player') !== null")
        assert errors == []
    finally:
        ctx.close()


def test_decisions_panel_and_page_in_the_browser(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, width=390, hash_="#screen-booking")
    try:
        panel = '[data-why-for="booking"]'
        assert page.is_visible(f'{panel} [data-decision="DS-20261005-booking-form"]') or page.is_visible("#pp-why-toggle")
        if not page.is_visible(f'{panel} [data-decision="DS-20261005-booking-form"]'):
            page.click("#pp-why-toggle")
        assert page.is_visible(f'{panel} [data-decision="DS-20261005-booking-form"]')
        assert not page.is_visible('[data-why-for="home"]')
        page.click('.pp-bar a[href="#decisions"]')
        assert page.is_visible("#decisions") and not page.is_visible("#pp-frame")
        page.click('#decisions a[href="#screen-home"] >> nth=0')
        assert _visible_screen(page) == "home"
        assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
        assert errors == []
    finally:
        ctx.close()


def test_catalogue_shows_each_copy_in_its_state_and_theme(browser, built) -> None:
    ctx, page, errors, requests = _open(browser, built / CATALOGUE_REL, width=1280, scheme="light")
    try:
        for sid, states in SCREENS.items():
            for state in states:
                shown = page.evaluate("""(key) => [...document.querySelectorAll('[data-copy="' + key + '"] [data-state]')]
                    .filter(e => e.offsetParent !== null).map(e => e.dataset.state)""", f"{sid}/{state}/light")
                assert shown == [state], (sid, state, shown)
        light = page.evaluate("getComputedStyle(document.querySelector('[data-copy=\"home/ready/light\"] [data-screen]')).backgroundColor")
        dark = page.evaluate("getComputedStyle(document.querySelector('[data-copy=\"home/ready/dark\"] [data-screen]')).backgroundColor")
        assert (light, dark) == ("rgb(255, 255, 255)", "rgb(15, 18, 23)")
        assert page.evaluate("document.querySelectorAll('[data-screen=\"booking\"][data-script-ran=\"yes\"]').length") == \
            2 * len(SCREENS["booking"])
        page.click('.sc-nav a[href="#screen-menu"]')
        assert page.evaluate("location.hash") == "#screen-menu"
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()



def test_screens_link_works_after_a_deep_link_to_decisions(browser, built) -> None:
    for hash_ in ("#decisions", "#decision-DS-20261005-booking-form"):
        ctx, page, errors, _ = _open(browser, built / PROTO_REL, hash_=hash_)
        try:
            assert page.is_visible("#decisions") and not page.is_visible("#pp-frame")
            page.click("#pp-screens-link")
            assert _visible_screen(page) == "home", hash_
            assert page.evaluate("location.hash") == "#screen-home"
            page.click('.pp-nav [data-nav="menu"]')
            page.click("#pp-decisions-link")
            page.evaluate("location.hash = 'screen'")
            page.wait_for_function("!document.getElementById('pp-frame').closest('[hidden]')")
            assert _visible_screen(page) == "menu"  # #screen goes back to the current screen
            assert errors == []
        finally:
            ctx.close()


def test_a_failing_screen_script_does_not_stop_the_others(browser, tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    write(p / SCREENS_REL / "boom.html", '<section data-screen="boom" data-order="0"><div data-state="ready">x</div>'
          '</section>\n<script data-screen-script>throw new Error("boom went the screen");</script>\n')
    write(p / SCREENS_REL / "broken.html", '<section data-screen="broken" data-order="0"><div data-state="ready">x</div>'
          '</section>\n<script data-screen-script>var = ;</script>\n')
    assert run(p).returncode == 0
    for rel, selector in ((PROTO_REL, '#pp-frame [data-screen="booking"]'), (CATALOGUE_REL, '[data-copy] [data-screen="booking"]')):
        ctx, page, errors, _ = _open(browser, p / rel)
        try:
            assert page.get_attribute(selector, "data-script-ran") == "yes", rel
            assert any("boom went the screen" in e for e in errors), errors
            assert any("SyntaxError" in e or "Unexpected" in e for e in errors), errors
            if rel == PROTO_REL:
                page.click('.pp-nav [data-nav="menu"]')
                assert _visible_screen(page) == "menu"
        finally:
            ctx.close()


def test_labels_work_in_every_catalogue_copy(browser, tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    write(p / SCREENS_REL / "signup.html", SIGNUP)
    assert run(p).returncode == 0
    ctx, page, errors, _ = _open(browser, p / CATALOGUE_REL)
    try:
        for theme in ("light", "dark"):
            page.click(f'[data-copy="signup/ready/{theme}"] label')
            assert page.evaluate("document.activeElement.closest('[data-copy]').dataset.copy") == f"signup/ready/{theme}"
        assert errors == []
    finally:
        ctx.close()


def test_narrow_screen_strip_cards_line_up(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, width=390)
    try:
        heights = page.evaluate("[...document.querySelectorAll('.pp-nav a')].map(a => Math.round(a.getBoundingClientRect().height))")
        assert len(set(heights)) == 1, heights
        clamp = page.evaluate("""(() => { const t = document.querySelector('.pp-nav [data-nav="menu"] .nav-title');
            return [t.getBoundingClientRect().height, parseFloat(getComputedStyle(t).lineHeight)]; })()""")
        assert clamp[0] <= clamp[1] * 2 + 1, clamp
        assert page.get_attribute('.pp-nav [data-nav="menu"]', "title") == TITLES["menu"]
        assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
        assert errors == []
    finally:
        ctx.close()
