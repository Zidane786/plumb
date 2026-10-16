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
import struct
import subprocess
import sys
import zlib
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
APP_REL = f"{DOCS}/app.html"
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
    for tpl in TEMPLATES.iterdir():
        if tpl.is_file():
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
                assert "<template" not in copy.split("</figure>", 1)[0]  # the copies share the screen's one template
        # one template per screen holds the whole section, every state as written; the page picks each copy's state
        markup = re.findall(f'<template data-screen-markup="{sid}">(.*?)</template>', page, re.S)
        assert len(markup) == 1, sid
        assert re.findall(r'<div data-state="([^"]+)"', markup[0]) == states
        assert "<div hidden data-state=" not in markup[0]
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
    for rel in (PROTO_REL, APP_REL, CATALOGUE_REL):
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
    for name in ("prototype.html", "app.html", "screens.html", "prototype/screens.json"):
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
    synced = run(project, "--synced", "menu", env=env)
    assert synced.returncode == 0
    # never a bare "run --approve": the agent asks the user first
    ask = next(ln for ln in synced.stdout.splitlines() if "--approve menu" in ln)
    assert ask.startswith("ask the user: ") and "Only after their yes to that screen" in ask
    assert "confirm it with --approve" not in synced.stdout
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
    before = {rel: (project / rel).read_bytes() for rel in (PROTO_REL, APP_REL, CATALOGUE_REL, JSON_REL)}
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
    assert f"stale: {APP_REL} (prototype token block)" in r.stdout
    r = build_tokens(project)
    assert r.returncode == 0, r.stderr
    assert f"wrote {PROTO_REL}" in r.stdout and f"wrote {CATALOGUE_REL}" in r.stdout and f"wrote {APP_REL}" in r.stdout
    for rel in (PROTO_REL, APP_REL, CATALOGUE_REL):
        page = read(project / rel)
        assert "--color-primary: #0b5a56;" in page
        container = page[page.index("@container plumb-frame (min-width: 48rem)"):]
        assert "--text-base: 17px;" in container[:400]
    # one tokens build leaves nothing for build-prototype to do, and both checks agree
    assert run(project, "--check").returncode == 0, run(project, "--check").stdout
    assert build_tokens(project, "--check").returncode == 0
    before = {rel: (project / rel).read_bytes() for rel in (PROTO_REL, APP_REL, CATALOGUE_REL)}
    assert "wrote" not in run(project).stdout
    assert {rel: (project / rel).read_bytes() for rel in before} == before


def test_token_block_note_needs_the_generated_region(tmp_path: Path) -> None:
    """A web copy that happens to be called screens.html is a plain stale output, not a prototype token block."""
    def mutate(doc):
        doc["$extensions"]["plumb"]["web"]["copies"] = ["public/screens.html"]

    p = make_project(tmp_path / "p", mutate=mutate)
    assert build_tokens(p).returncode == 0
    assert (p / "public/screens.html").is_file()
    doc = json.loads(read(p / TOKENS_REL))
    doc["color"]["primary"]["$value"] = "#0b5a56"
    write(p / TOKENS_REL, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    r = build_tokens(p, "--check")
    assert r.returncode == 1
    assert "stale: public/screens.html\n" in r.stdout
    assert f"stale: {CATALOGUE_REL} (prototype token block)" in r.stdout


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


def test_inline_markup_tokenises_code_links_and_emphasis() -> None:
    # a code span inside a link label stays inside the link
    assert BP.inline("[`a.md`](p.html)") == '<a href="p.html"><code>a.md</code></a>'
    # bold (and italic) across a code span
    assert BP.inline("**bold `x` y**") == "<strong>bold <code>x</code> y</strong>"
    assert BP.inline("*see `x`*") == "<em>see <code>x</code></em>"
    # code inside an href stays literal text, never markup
    assert BP.inline("[x](a`b`c)") == '<a href="a`b`c">x</a>'
    # markup inside code stays literal; previous cases still hold
    assert BP.inline("`**y** [z](u)`") == "<code>**y** [z](u)</code>"
    assert BP.inline("[**b**](q.html) and a*b*c") == '<a href="q.html"><strong>b</strong></a> and a*b*c'
    assert BP.inline("[a](JavaScript:alert(1)) & <i>") == "[a](JavaScript:alert(1)) &amp; &lt;i&gt;"
    assert BP.inline("[`js`](javascript:x)") == "[<code>js</code>](javascript:x)"


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


def test_catalogue_copies_are_isolated_documents(project: Path) -> None:
    write(project / SCREENS_REL / "signup.html", SIGNUP)
    assert run(project).returncode == 0
    page = read(project / CATALOGUE_REL)
    for theme in ("light", "dark"):
        copy = block(page, "data-copy", f"signup/ready/{theme}")
        assert '<iframe class="sc-iframe" title="Sign up: Ready, ' + theme + ' theme">' in copy
        assert "<template" not in copy.split("</figure>", 1)[0]
    markup = page[page.index('<template data-screen-markup="signup">'):]
    assert markup.startswith('<template data-screen-markup="signup"><section data-screen="signup"')
    assert '<label for="email">' in markup and '<input id="email"' in markup  # markup untouched: ids stay as written
    assert page.count('<template data-screen-markup="signup">') == 1
    assert "sandbox=" not in page  # an opaque origin would block the screens' relative file:// images
    assert '<base href=' in page  # relative paths resolve against the docs folder, as in prototype.html
    assert page.count('<template data-screen-scripts="booking">') == 1 and page.count('<template data-screen-styles="booking">') == 1
    assert "default-src 'none'" in page  # the copies' CSP: nothing from the network
    assert not re.search(r"<style>\s*\[data-screen=", page)  # screen styles live only inside the copies


def test_catalogue_says_it_needs_javascript(project: Path) -> None:
    page = read(project / CATALOGUE_REL)
    notice = page[page.index("<noscript>"): page.index("</noscript>")]
    assert "JavaScript" in notice and 'href="prototype.html"' in notice


# ---------------------------------------------------------------- the app view (app.html)

APP_DOCS = "product/design"  # a variation: another docs folder and screens shaped like an app shell
APP_SCREENS = {
    "overview": """<style>
[data-screen="overview"] { font-family: var(--font-sans); color: var(--color-on-surface); background: var(--color-background); padding: var(--spacing-6) var(--spacing-4); }
[data-screen="overview"] .grid { display: grid; gap: var(--spacing-3); }
@container plumb-frame (min-width: 48rem) {
  [data-screen="overview"] .grid { grid-template-columns: 1fr 1fr; }
}
</style>
<section data-screen="overview" data-title="Overview" data-order="2">
  <h2>Overview</h2>
  <div data-state="ready"><div class="grid"><p>Open items: 12</p><p>Closed this week: 4</p></div>
    <a href="#/people" data-test="to-people">People</a>
    <button type="button" data-test="invite-person">Invite a person</button></div>
  <div data-state="empty"><p>Nothing to show yet.</p></div>
</section>
<script data-screen-script>
screen.querySelector("[data-test=invite-person]").addEventListener("click", function () { plumb.go("people", "invite"); });
</script>
""",
    "people": """<style>
[data-screen="people"] { font-family: var(--font-sans); color: var(--color-on-surface); background: var(--color-background); }
[data-screen="people"] .layout { display: flex; }
[data-screen="people"] .side { flex: none; width: 14rem; padding: var(--spacing-4); background: var(--color-surface); }
[data-screen="people"] .body { flex: 1; min-width: 0; padding: var(--spacing-4); }
[data-screen="people"] .tall { height: 2600px; }
[data-screen="people"] .layer { position: relative; z-index: 60; }
[data-screen="people"] .toast { position: fixed; right: 0; bottom: 0; margin: 0; }
[data-screen="people"] .bar { position: fixed; right: 0; top: 0; margin: 0; }
@container plumb-frame (max-width: 47.99rem) {
  [data-screen="people"] .layout { flex-direction: column; }
  [data-screen="people"] .side { width: auto; }
}
</style>
<section data-screen="people" data-title="People" data-order="1">
  <div class="layout">
    <nav class="side" data-app-sidebar aria-label="Sections"><a href="#/overview" data-test="to-overview">Overview</a></nav>
    <div class="body">
      <h2>People</h2>
      <button type="button" data-test="invite">Invite someone</button>
      <button type="button" data-test="theme">Switch theme</button>
      <button type="button" data-test="go">See the empty overview</button>
      <button type="button" data-test="filter">Only admins</button>
      <div class="tall"></div>
      <div data-state="ready"><p>Three people.</p></div>
      <div data-state="invite"><div class="layer" role="dialog" aria-modal="true" aria-label="Invite" data-test="dialog">
        <p>Invite by email</p></div></div>
      <div data-state="filtered"><p>One admin.</p></div>
      <aside role="dialog" aria-label="Help" data-test="help"><p>Need a hand? Ask the team.</p></aside>
      <p class="toast" role="status" data-test="toast">Saved</p>
      <p class="bar" data-test="bar">Signed in</p>
    </div>
  </div>
</section>
<script data-screen-script>
screen.setAttribute("data-catalogue", String(plumb.catalogue));
screen.querySelector("[data-test=invite]").addEventListener("click", function () { plumb.setState("invite"); });
screen.querySelector("[data-test=theme]").addEventListener("click", function () { window.plumbTheme.toggle(); });
screen.querySelector("[data-test=go]").addEventListener("click", function () { plumb.go("overview", "empty"); });
screen.querySelector("[data-test=filter]").addEventListener("click", function () { plumb.setState("filtered"); });
</script>
""",
}


def make_app_project(dest: Path) -> Path:
    def mutate(doc):
        doc["$extensions"]["plumb"]["docs_dir"] = APP_DOCS

    p = make_project(dest, screens=False, decisions=False, build=False, mutate=mutate)
    for sid, text in APP_SCREENS.items():
        write(p / APP_DOCS / "prototype/screens" / f"{sid}.html", text)
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    return p


def visible_sections(page: str) -> list:
    return re.findall(r'<section data-screen="([^"]+)"', page)  # a hidden one is <section hidden data-screen=...>


def test_app_is_written_with_every_screen_and_no_prototype_panels(project: Path) -> None:
    page = read(project / APP_REL)
    assert page.startswith("<!doctype html>")
    assert P.is_generated_text(page) and "build-prototype.py" in "\n".join(page.splitlines()[:3])
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in page[:3000]
    for sid in SCREENS:
        assert len(re.findall(f'<section(?: hidden)? data-screen="{sid}"', page)) == 1, sid
    for panel in ('class="pp-nav"', "data-states-for", 'id="pp-why"', 'id="decisions"', 'id="theme-toggle"',
                  "data-viewport", 'id="plumb-tours"', 'id="plumb-player"', ".pl-dock", 'class="pp-bar'):
        assert panel not in page, panel
    assert 'id="pp-stage"' in page and 'id="pp-frame"' in page  # where a tour page's player draws
    frame_css = page[page.index(".pa-frame {"):]
    frame_css = frame_css[:frame_css.index("}")]
    assert "container: plumb-frame / inline-size;" in frame_css and "isolation: isolate;" in frame_css
    assert "[data-app-sidebar] { position: sticky; top: 0; height: 100vh; height: 100dvh; }" in page
    assert page.count('screen.setAttribute("data-script-ran", "yes");') == 1
    assert "window.plumbPrototype" in page and "window.plumbTheme" in page and "catalogue: false" in page
    inner = page.split("/* plumb:tokens */", 1)[1].split("/* plumb:tokens:end */", 1)[0]
    assert inner.strip("\n") == BT.css_vars(P.load_tokens(project / TOKENS_REL)).strip("\n")
    assert visible_sections(page) == ["home"]


def test_app_opens_on_the_first_screen_by_data_order(tmp_path: Path) -> None:
    p = make_app_project(tmp_path / "Other App")
    page = read(p / APP_DOCS / "app.html")
    assert visible_sections(page) == ["people"]  # data-order 1, though "overview" sorts first by name
    assert "<title>People · " in page
    data = json.loads(page.split('id="plumb-data">', 1)[1].split("</script>", 1)[0])
    assert [s["id"] for s in data["screens"]] == ["people", "overview"]
    path = p / APP_DOCS / "prototype/screens/overview.html"
    write(path, read(path).replace('data-order="2"', 'data-order="0"'))
    assert run(p).returncode == 0
    assert visible_sections(read(p / APP_DOCS / "app.html")) == ["overview"]


def test_check_names_a_stale_or_missing_app(project: Path) -> None:
    app = project / APP_REL
    write(app, read(app).replace("<title>", "<title>x"))
    r = run(project, "--check")
    assert r.returncode == 1 and f"stale: {APP_REL}\n" in r.stdout and PROTO_REL not in r.stdout, r.stdout
    assert "fix: " in r.stdout
    app.unlink()
    r = run(project, "--check")
    assert r.returncode == 1 and f"stale: {APP_REL} (missing)" in r.stdout, r.stdout
    assert not app.exists()  # --check writes nothing
    r = run(project)
    assert r.returncode == 0 and f"wrote {APP_REL}" in r.stdout
    assert run(project, "--check").returncode == 0


def test_build_tokens_leaves_a_missing_app_to_build_prototype(project: Path) -> None:
    """A project built before the app view has no app.html: the tokens build never writes one; build-prototype.py does."""
    assert build_tokens(project).returncode == 0
    (project / APP_REL).unlink()
    r = build_tokens(project, "--check")
    assert r.returncode == 0 and "app.html" not in r.stdout, r.stdout
    assert build_tokens(project).returncode == 0 and not (project / APP_REL).exists()
    assert run(project).returncode == 0 and (project / APP_REL).is_file()


def test_app_bytes_are_deterministic(project: Path, tmp_path: Path) -> None:
    other = make_project(tmp_path / "second" / "Café Ünïcode")  # another place on disk, the same bytes
    assert (other / APP_REL).read_bytes() == (project / APP_REL).read_bytes()


def test_missing_app_template_is_refused(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    (p / SKILL_REL / "templates/app-shell.html.tmpl").unlink()
    assert_refusal(run(p), "app-shell.html.tmpl", "/plumb:upgrade")
    assert not (p / APP_REL).exists() and not (p / PROTO_REL).exists()


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


def _copy(page, key: str):
    return page.frame_locator(f'[data-copy="{key}"] iframe')


def _copies_ready(page) -> None:
    page.wait_for_function("[...document.querySelectorAll('figure[data-copy] iframe')].every(f => f.dataset.sized)")


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
        _copies_ready(page)
        for sid, states in SCREENS.items():
            for state in states:
                for theme in ("light", "dark"):
                    shown = _copy(page, f"{sid}/{state}/{theme}").locator("[data-state]").evaluate_all(
                        "els => els.filter(e => e.offsetParent !== null).map(e => e.dataset.state)")
                    assert shown == [state], (sid, state, theme, shown)
        bg = "el => getComputedStyle(el).backgroundColor"
        assert _copy(page, "home/ready/light").locator("[data-screen]").evaluate(bg) == "rgb(255, 255, 255)"
        assert _copy(page, "home/ready/dark").locator("[data-screen]").evaluate(bg) == "rgb(15, 18, 23)"
        for state in SCREENS["booking"]:
            for theme in ("light", "dark"):
                _copy(page, f"booking/{state}/{theme}").locator('[data-screen="booking"][data-script-ran="yes"]').wait_for(state="attached")
        heights = page.evaluate("[...document.querySelectorAll('figure[data-copy] iframe')].map(f => f.getBoundingClientRect().height)")
        assert min(heights) >= 48 and max(heights) < 1200, heights  # each copy sized to its content
        content = _copy(page, "home/ready/light").locator("body").evaluate("b => Math.ceil(b.getBoundingClientRect().height)")
        frame_h = page.evaluate("document.querySelector('[data-copy=\"home/ready/light\"] iframe').getBoundingClientRect().height")
        assert abs(frame_h - content) <= 1, (frame_h, content)
        page.click('.sc-nav a[href="#screen-menu"]')
        assert page.evaluate("location.hash") == "#screen-menu"
        _copy(page, "home/ready/light").locator('[data-test="new-booking"]').click()  # a link to another screen
        page.wait_for_function("location.hash === '#screen-booking'")
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
    for rel in (PROTO_REL, CATALOGUE_REL):
        ctx, page, errors, _ = _open(browser, p / rel)
        try:
            if rel == PROTO_REL:
                assert page.get_attribute('#pp-frame [data-screen="booking"]', "data-script-ran") == "yes"
            else:
                _copies_ready(page)
                _copy(page, "booking/ready/light").locator('[data-script-ran="yes"]').wait_for(state="attached")
            assert any("boom went the screen" in e for e in errors), errors
            assert any("SyntaxError" in e or "Unexpected" in e for e in errors), errors
            if rel == PROTO_REL:
                page.click('.pp-nav [data-nav="menu"]')
                assert _visible_screen(page) == "menu"
        finally:
            ctx.close()


ISO = ('<style>\n[data-screen="iso"] #swatch-label { color: rgb(1, 2, 3); }\n</style>\n'
       '<section data-screen="iso" data-title="Isolation">\n'
       '  <svg width="40" height="20" aria-hidden="true"><defs><linearGradient id="grad"><stop offset="0" stop-color="#c00"/>'
       '<stop offset="1" stop-color="#c00"/></linearGradient></defs><rect id="swatch" width="40" height="20" fill="url(#grad)"/></svg>\n'
       '  <p id="swatch-label">Swatch</p><output id="out"></output>\n'
       '  <div data-state="ready"><label for="email">Email</label><input id="email">'
       '<input type="radio" name="size" value="s" id="size-s" checked><label for="size-s">S</label>'
       '<input type="radio" name="size" value="l" id="size-l"><label for="size-l">L</label></div>\n'
       '  <div data-state="empty"><p>Nothing yet.</p></div>\n'
       '</section>\n<script data-screen-script>\ndocument.getElementById("out").textContent = "ran " + plumb.state();\n</script>\n')


@pytest.mark.parametrize("width", [1280, 390])
def test_catalogue_copies_are_isolated(browser, tmp_path: Path, width: int) -> None:
    p = make_project(tmp_path / "p", build=False)
    write(p / SCREENS_REL / "iso.html", ISO)
    assert run(p).returncode == 0
    ctx, page, errors, requests = _open(browser, p / CATALOGUE_REL, width=width)
    try:
        _copies_ready(page)
        keys = [f"iso/{state}/{theme}" for state in ("ready", "empty") for theme in ("light", "dark")]
        for key in keys:
            frame = _copy(page, key)
            # url(#grad) finds its gradient: exactly one #grad in this document, and the rect paints with it
            assert frame.locator("#swatch").evaluate("r => getComputedStyle(r).fill").startswith("url(")
            assert frame.locator("body").evaluate("b => document.querySelectorAll('#grad').length") == 1
            assert frame.locator("#swatch").evaluate("r => r.ownerDocument.getElementById('grad') !== null")
            # an #id rule applies, and getElementById in the screen's script finds this copy's element
            assert frame.locator("#swatch-label").evaluate("el => getComputedStyle(el).color") == "rgb(1, 2, 3)"
            assert frame.locator("#out").inner_text() == "ran " + key.split("/")[1]
        # radio groups are independent between the light and dark copies
        _copy(page, "iso/ready/light").locator('label[for="size-l"]').click()
        assert _copy(page, "iso/ready/light").locator("#size-l").is_checked()
        assert _copy(page, "iso/ready/dark").locator("#size-s").is_checked()
        # labels work in every copy
        for theme in ("light", "dark"):
            frame = _copy(page, f"iso/ready/{theme}")
            frame.locator('label[for="email"]').click()
            assert frame.locator("#email").evaluate("el => el === document.activeElement")
        assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
        assert errors == [] and requests == [], (errors, requests)
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



def _tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    pixels = b"".join(b"\x00" + b"\xcc\x00\x00" * 2 for _ in range(2))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def test_relative_images_load_in_every_copy(browser, tmp_path: Path) -> None:
    p = make_project(tmp_path / "Café Ünïcode", build=False)
    (p / DOCS / "img").mkdir(parents=True, exist_ok=True)
    (p / DOCS / "img/dot.png").write_bytes(_tiny_png())
    write(p / SCREENS_REL / "pic.html", '<section data-screen="pic" data-title="Picture"><div data-state="ready">'
          '<img src="img/dot.png" alt="A dot" width="20" height="20" data-test="dot"></div></section>\n')
    assert run(p).returncode == 0
    ctx, page, errors, requests = _open(browser, p / CATALOGUE_REL)
    try:
        _copies_ready(page)
        for theme in ("light", "dark"):
            img = _copy(page, f"pic/ready/{theme}").locator('[data-test="dot"]')
            img.evaluate("el => el.complete ? null : new Promise(r => { el.onload = el.onerror = r; })")
            assert img.evaluate("el => el.naturalWidth") == 2, theme
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()
    for rel, hash_ in ((PROTO_REL, "#screen-pic"), (APP_REL, "#/pic")):
        ctx, page, errors, _ = _open(browser, p / rel, hash_=hash_)
        try:
            img = page.locator('#pp-frame [data-test="dot"]')
            img.evaluate("el => el.complete ? null : new Promise(r => { el.onload = el.onerror = r; })")
            assert img.evaluate("el => el.naturalWidth") == 2, rel
            assert errors == []
        finally:
            ctx.close()


# ---------------------------------------------------------------- the app view in the browser (headless)


@pytest.fixture(scope="module")
def app_built(tmp_path_factory) -> Path:
    return make_app_project(tmp_path_factory.mktemp("app") / "Other App")


def _state_of(page) -> str:
    return page.evaluate("(() => { var c = window.plumbPrototype.current(); return c.screen + '/' + c.state; })()")


THROWING_STORAGE = """Object.defineProperty(window, 'localStorage', { configurable: true,
    get: function () { throw new DOMException('denied', 'SecurityError'); } });"""


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_app_renders_cleanly_full_window(browser, built, width: int, scheme: str) -> None:
    ctx, page, errors, requests = _open(browser, built / APP_REL, width, scheme)
    try:
        assert page.evaluate("document.documentElement.dataset.theme") == scheme
        assert _visible_screen(page) == "home"
        assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
        frame = page.evaluate("""(() => { var f = document.getElementById('pp-frame'), r = f.getBoundingClientRect();
            return { left: r.left, width: r.width, iso: getComputedStyle(f).isolation,
                     type: getComputedStyle(f).containerType, name: getComputedStyle(f).containerName }; })()""")
        assert frame["left"] == 0 and frame["width"] == page.evaluate("document.documentElement.clientWidth")
        assert frame["iso"] == "isolate" and frame["type"] == "inline-size" and frame["name"] == "plumb-frame"
        assert page.evaluate("document.querySelector('.pp-nav, #pp-rail, [data-states-for], #plumb-player, "
                             "#theme-toggle')") is None
        bg = "getComputedStyle(document.querySelector('#pp-frame > [data-screen=\"home\"]')).backgroundColor"
        before = page.evaluate(bg)
        page.evaluate("window.plumbTheme.toggle()")
        assert page.evaluate("document.documentElement.dataset.theme") == ("dark" if scheme == "light" else "light")
        assert page.evaluate(bg) != before
        assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


@pytest.mark.parametrize("hash_, expected", [
    ("", "home/ready"), ("#/booking", "booking/ready"), ("#/menu/empty", "menu/empty"),
    ("#screen-menu/empty", "menu/empty"), ("#screen-booking", "booking/ready"), ("#/nope", "home/ready"),
    ("#screen-nope", "home/ready"), ("#/menu/nope", "menu/ready"), ("#elsewhere", "home/ready"),
])
def test_app_routes(browser, built, hash_: str, expected: str) -> None:
    ctx, page, errors, _ = _open(browser, built / APP_REL, hash_=hash_)
    try:
        sid, state = expected.split("/")
        assert _visible_screen(page) == sid and _visible_states(page, sid) == [state]
        assert _state_of(page) == expected
        assert page.evaluate("document.title").startswith(TITLES[sid])
        assert errors == []
    finally:
        ctx.close()


def test_app_links_history_and_the_api(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / APP_REL)
    try:
        page.click('#pp-frame [data-screen="home"] [data-test="new-booking"]')  # a prototype link: href="#screen-booking"
        assert _visible_screen(page) == "booking" and page.evaluate("location.hash") == "#/booking"
        assert page.get_attribute('#pp-frame [data-screen="booking"]', "data-script-ran") == "yes"
        page.click('#pp-frame [data-test="save"]')
        assert page.is_visible('#pp-frame [data-test="guest-error"]')
        page.fill('#pp-frame [data-test="guest"]', "Zoë")
        page.click('#pp-frame [data-test="save"]')
        assert _visible_states(page, "booking") == ["success"]
        assert page.evaluate("location.hash") == "#/booking/success"  # plumb.setState replaces the entry
        page.go_back()
        assert _visible_screen(page) == "home" and _state_of(page) == "home/ready"
        api = page.evaluate("Object.keys(window.plumbPrototype).sort()")
        for name in ("go", "setState", "current", "screen", "setTheme", "on", "screens", "project"):
            assert name in api, name
        assert page.evaluate("window.plumbPrototype.screens.map(s => s.id)") == list(SCREENS)
        seen = page.evaluate("""() => { var got = []; window.plumbPrototype.on(e => got.push(e.screen + '/' + e.state));
            window.plumbPrototype.go('menu', 'empty'); window.plumbPrototype.setState('ready'); return got; }""")
        assert seen == ["menu/empty", "menu/ready"]
        assert page.evaluate("location.hash") == "#/menu"
        assert page.evaluate("window.plumbPrototype.screen('menu') === "
                             "document.querySelector('#pp-frame > [data-screen=menu]')")
        length = page.evaluate("history.length")
        page.evaluate("window.plumbPrototype.go('home', null, { history: null })")
        assert _visible_screen(page) == "home" and page.evaluate("history.length") == length
        assert page.evaluate("window.plumbPrototype.setTheme('dark')") == "dark"
        assert page.evaluate("document.documentElement.classList.contains('dark')")
        assert errors == []
    finally:
        ctx.close()


def test_app_screen_scripts_get_the_same_api(browser, app_built) -> None:
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html")
    try:
        assert _visible_screen(page) == "people"
        assert page.get_attribute('#pp-frame [data-screen="people"]', "data-catalogue") == "false"
        assert page.evaluate("window.scrollY") == 0
        page.click('#pp-frame [data-test="invite"]')  # plumb.setState("invite"): the dialog sits below the window
        assert _state_of(page) == "people/invite"
        box = page.evaluate("document.querySelector('[data-test=dialog]').getBoundingClientRect().toJSON()")
        assert page.evaluate("window.scrollY") > 0
        assert box["top"] >= 0 and box["bottom"] <= 900, box  # scrolled into view
        page.click('#pp-frame [data-test="go"]')  # plumb.go("overview", "empty")
        assert _state_of(page) == "overview/empty" and page.evaluate("location.hash") == "#/overview/empty"
        assert page.evaluate("window.scrollY") == 0  # another screen opens at its top
        assert errors == []
    finally:
        ctx.close()


def test_app_theme_follows_the_system_until_chosen_then_remembers(browser, app_built) -> None:
    path = app_built / APP_DOCS / "app.html"
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    try:
        page = ctx.new_page()
        page.goto(path.resolve().as_uri())
        assert page.evaluate("document.documentElement.dataset.theme") == "dark"
        assert page.evaluate("document.documentElement.className") == ""  # the system's, nothing chosen
        page.click('#pp-frame [data-test="theme"]')  # the screen's own toggle
        assert page.evaluate("document.documentElement.dataset.theme") == "light"
        page.reload()
        assert page.evaluate("document.documentElement.dataset.theme") == "light"
        assert page.evaluate("document.documentElement.classList.contains('light')")
        other = ctx.new_page()
        other.goto(path.resolve().as_uri() + "#/overview")
        assert other.evaluate("document.documentElement.dataset.theme") == "light"
    finally:
        ctx.close()
    fresh = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="light")
    try:
        page = fresh.new_page()
        page.goto(path.resolve().as_uri())
        assert page.evaluate("document.documentElement.dataset.theme") == "light"
    finally:
        fresh.close()


def test_app_works_when_storage_throws(browser, app_built) -> None:
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    try:
        ctx.add_init_script(THROWING_STORAGE)
        page = ctx.new_page()
        errors: list = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((app_built / APP_DOCS / "app.html").resolve().as_uri())
        assert _visible_screen(page) == "people"
        assert page.evaluate("document.documentElement.dataset.theme") == "dark"
        page.click('#pp-frame [data-test="theme"]')
        assert page.evaluate("document.documentElement.dataset.theme") == "light"
        page.click('#pp-frame [data-test="to-overview"]')
        assert _visible_screen(page) == "overview"
        assert errors == [], errors
    finally:
        ctx.close()


@pytest.mark.parametrize("width, columns", [(1280, 2), (390, 1)])
def test_app_md_breakpoint_follows_the_window(browser, app_built, width: int, columns: int) -> None:
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", width, hash_="#/overview")
    try:
        cols = page.evaluate("getComputedStyle(document.querySelector('[data-screen=overview] .grid')).gridTemplateColumns")
        assert len(cols.split()) == columns, cols
        assert errors == []
    finally:
        ctx.close()


def test_app_sidebar_hook_is_sticky_from_md(browser, app_built) -> None:
    side = "document.querySelector('[data-screen=people] [data-app-sidebar]')"
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", 1280)
    try:
        assert page.evaluate(f"getComputedStyle({side}).position") == "sticky"
        assert page.evaluate(f"{side}.getBoundingClientRect().height") == 900
        page.evaluate("window.scrollTo(0, 1500)")
        assert page.evaluate("window.scrollY") == 1500
        assert page.evaluate(f"{side}.getBoundingClientRect().top") == 0
        assert errors == []
    finally:
        ctx.close()
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", 390)
    try:
        assert page.evaluate(f"getComputedStyle({side}).position") == "static"  # below md: the screen's own layout
        assert errors == []
    finally:
        ctx.close()


def test_app_frame_keeps_screen_layers_inside(browser, app_built) -> None:
    """A screen's z-index 60 layer stays inside the frame's stacking context: what is drawn over the stage wins."""
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", 1280, hash_="#/people/invite")
    try:
        on_top = page.evaluate("""(() => {
            var d = document.querySelector('[data-test=dialog]'); d.scrollIntoView({ block: 'center' });
            var over = document.createElement('div');
            over.style.cssText = 'position:fixed;inset:0;z-index:1';
            document.getElementById('pp-stage').appendChild(over);
            var r = d.getBoundingClientRect();
            return document.elementFromPoint(r.left + 5, r.top + 5) === over; })()""")
        assert on_top
        assert errors == []
    finally:
        ctx.close()


DIALOG_IN_VIEW = """(() => { var r = document.querySelector('[data-test=dialog]').getBoundingClientRect();
    return r.top >= 0 && r.bottom <= window.innerHeight; })()"""


def test_app_a_dialog_that_was_showing_never_moves_the_page(browser, app_built) -> None:
    """The help panel (role=dialog, always shown, far down) is not opened by a state change: no jump to it."""
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", 1280)
    try:
        assert page.is_visible('[data-test="help"]') and page.evaluate("window.scrollY") == 0  # none at load either
        page.click('#pp-frame [data-test="filter"]')
        assert _state_of(page) == "people/filtered" and page.evaluate("window.scrollY") == 0
        page.evaluate("window.plumbPrototype.setState('ready')")
        assert page.evaluate("window.scrollY") == 0
        page.click('#pp-frame [data-test="to-overview"]')
        page.click('#pp-frame [data-test="to-people"]')  # another screen, its first state: the help panel stays put
        assert _state_of(page) == "people/ready" and page.evaluate("window.scrollY") == 0
        assert errors == []
    finally:
        ctx.close()


def test_app_reveals_a_dialog_opened_from_another_screen(browser, app_built) -> None:
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", 1280, hash_="#/overview")
    try:
        page.click('#pp-frame [data-test="invite-person"]')  # plumb.go("people", "invite")
        assert _state_of(page) == "people/invite"
        assert page.evaluate("window.scrollY") > 0 and page.evaluate(DIALOG_IN_VIEW)
        assert errors == []
    finally:
        ctx.close()


def test_app_reveals_a_dialog_opened_by_a_link(browser, app_built) -> None:
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", 1280, hash_="#/people/invite")
    try:
        assert _state_of(page) == "people/invite"
        assert page.evaluate("window.scrollY") > 0 and page.evaluate(DIALOG_IN_VIEW)
        assert errors == []
    finally:
        ctx.close()


def test_app_fixed_elements_sit_on_the_window(browser, app_built) -> None:
    """The frame is an inline-size container (no containing block for position: fixed): a screen's fixed toast and bar
    stay at the window's edges on a long page, as in the product. Adding transform, filter, contain: layout and the
    like to the frame or the stage would pin them to the page and fail this."""
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", 1280)
    try:
        page.evaluate("window.scrollTo(0, 1500)")
        assert page.evaluate("window.scrollY") == 1500
        assert page.evaluate("document.querySelector('[data-test=toast]').getBoundingClientRect().bottom") == 900
        assert page.evaluate("document.querySelector('[data-test=bar]').getBoundingClientRect().top") == 0
        assert errors == []
    finally:
        ctx.close()


def test_app_announces_each_screen_change(browser, app_built) -> None:
    """The live region is cleared, then set, so the same title twice in a row is announced again."""
    ctx, page, errors, _ = _open(browser, app_built / APP_DOCS / "app.html", 1280)
    try:
        page.evaluate("""() => { window.seen = [];
            new MutationObserver(() => window.seen.push(document.getElementById('pa-announce').textContent))
                .observe(document.getElementById('pa-announce'), { childList: true, characterData: true, subtree: true }); }""")
        page.click('#pp-frame [data-test="to-overview"]')
        page.wait_for_function("window.seen.indexOf('Overview') >= 0")
        page.go_back()
        page.click('#pp-frame [data-test="to-overview"]')
        page.wait_for_function("window.seen.filter(t => t === 'Overview').length === 2")
        assert page.evaluate("window.seen") == ["Overview", "", "Overview"]  # emptied before the repeat
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- catalogue size and the page-size warning

FILLER = "<p>" + "A row of ordinary screen text, long enough to weigh something. " * 20 + "</p>"


def big_screen(sid: str, order: int, states: int, shape: str) -> str:
    """A synthetic screen with `states` state blocks of about 1.3 KB each. Two shapes, so the size rule is not shaped
    to one markup: plain <div> states straight in the section, or <article> states inside a wrapper, each holding an
    inner [data-state] (an inner one belongs to its state block and is never hidden on its own)."""
    if shape == "div":
        blocks = "".join(f'  <div data-state="s{j}"><h3>State {j}</h3>{FILLER}</div>\n' for j in range(states))
        body = f"  <h2>Screen {sid}</h2>\n{blocks}"
    else:
        blocks = "".join(f'    <article data-state="v{j}"><h3>Variant {j}</h3>{FILLER}<span data-state="inner">inner</span>'
                         f"</article>\n" for j in range(states))
        body = f'  <div class="wrap">\n{blocks}  </div>\n'
    return (f'<section data-screen="{sid}" data-title="Screen {sid}" data-order="{order}">\n{body}</section>\n'
            f"<script data-screen-script>\nscreen.setAttribute(\"data-ran\", plumb.state());\n</script>\n")


def big_project(dest: Path, screens: int, states: int, shape: str = "div") -> Path:
    p = make_project(dest, screens=False, decisions=False, build=False)
    for i in range(screens):
        write(p / SCREENS_REL / f"x{i:02d}.html", big_screen(f"x{i:02d}", i + 1, states, shape))
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    return p


@pytest.mark.parametrize("shape", ["div", "nested"])
def test_catalogue_grows_with_screens_not_screens_times_states(tmp_path: Path, shape: str) -> None:
    """20 screens × 10 states: each screen's markup is in the page once (shared by its 20 copies), not once per copy."""
    sizes = {n: (big_project(tmp_path / f"{shape}-{n}", n, 10, shape) / CATALOGUE_REL).stat().st_size for n in (10, 20)}
    screen_bytes = len(big_screen("x00", 1, 10, shape).encode("utf-8"))
    per_screen = (sizes[20] - sizes[10]) / 10
    # one copy of the markup plus the 20 copies' small figures; one template per copy would be 2 × 10 × screen_bytes
    assert per_screen < 2 * screen_bytes, (per_screen, screen_bytes)
    assert sizes[20] < 1_000_000, sizes  # the byte budget (several MB with a full render per copy)
    page = read(tmp_path / f"{shape}-20" / CATALOGUE_REL)
    assert page.count("<template data-screen-markup=") == 20
    assert page.count('data-copy="') == 20 * 10 * 2
    assert page.count("/* plumb:tokens */") == 1  # tokens once in the page; each copy takes them from there
    assert page.count(FILLER) == 20 * 10


def test_large_catalogue_is_deterministic(tmp_path: Path) -> None:
    a = big_project(tmp_path / "a", 20, 10, "nested")
    b = big_project(tmp_path / "elsewhere" / "b", 20, 10, "nested")
    assert (a / CATALOGUE_REL).read_bytes() == (b / CATALOGUE_REL).read_bytes()
    before = (a / CATALOGUE_REL).read_bytes()
    r = run(a)
    assert r.returncode == 0 and f"wrote {CATALOGUE_REL}" not in r.stdout
    assert (a / CATALOGUE_REL).read_bytes() == before


def _size_warnings(err: str) -> list:
    """The pages the size warning names: one `warning:` line for all of them, then a note and one fix."""
    lines = [ln for ln in err.splitlines() if ln.startswith("warning: ") and "a generated page should stay under" in ln]
    assert len(lines) <= 1, err  # never one warning per page
    if not lines:
        return []
    head = lines[0][len("warning: "):].split(": over the ", 1)[0]
    return re.findall(r"(\S+) is [0-9]+\.[0-9] MB", head)


def _size_fix(err: str) -> str:
    return next(ln for ln in err.splitlines() if ln.startswith("fix: make the screen files smaller"))


def test_every_page_over_the_limit_warns(project: Path, monkeypatch, capsys) -> None:
    write(project / DOCS / "prototype/tours/demo.json", read(FIXTURE / "tours/demo.json"))
    write(project / DOCS / "prototype/proposals/pick/a-one/screens/home.html", read(FIXTURE / "screens/home.html"))
    monkeypatch.setattr(BP, "PAGE_WARN_BYTES", 2000)
    code = BP.main(["--root", str(project / SKILL_REL)])
    _out, err = capsys.readouterr()
    assert code == 0, err
    named = _size_warnings(err)
    assert named == sorted([PROTO_REL, APP_REL, CATALOGUE_REL, f"{DOCS}/tours/demo.html"]), err
    assert JSON_REL not in err  # the map is data, not a page
    fix = _size_fix(err)  # what actually shrinks a page, and the honest cost of git-ignoring it
    assert "move inline data: images and large inline SVG into image files" in fix and "split" not in fix
    assert "or git-ignore the pages (they are generated:" in fix and "build-prototype.py rebuilds them" in fix
    assert "a git-ignored page is missing on a fresh clone, so --check then fails: run the build in CI" in fix
    assert "keep the pages committed" in fix
    assert err.count("\nfix: make the screen files smaller") + err.startswith("fix: make") == 1
    note = next(ln for ln in err.splitlines() if ln.startswith("note: every page holds each screen file once"))
    assert f"{SCREENS_REL}/booking.html (" in note  # the heaviest screen files, named so the user knows where to look
    code = BP.main(["--root", str(project / SKILL_REL)])  # nothing rewritten: the pages are still too big
    _out, err = capsys.readouterr()
    assert code == 0 and len(_size_warnings(err)) == 4, err
    code = BP.main(["--root", str(project / SKILL_REL), "--check"])  # --check says it too, exit code unchanged
    out, err = capsys.readouterr()
    assert code == 0 and "up to date" in out and len(_size_warnings(err)) == 4, err
    write(project / SCREENS_REL / "menu.html", read(project / SCREENS_REL / "menu.html").replace("</section>", "<p>more</p></section>"))
    code = BP.main(["--root", str(project / SKILL_REL), "--check"])
    out, err = capsys.readouterr()
    assert code == 1 and "stale: " in out and len(_size_warnings(err)) == 4, (out, err)
    code = BP.main(["--root", str(project / SKILL_REL), "--proposal", "pick"])
    _out, err = capsys.readouterr()
    assert code == 0, err
    base = f"{DOCS}/prototype/proposals/pick"
    assert _size_warnings(err) == sorted([f"{base}/a-one/app.html", f"{base}/a-one/prototype.html",
                                          f"{base}/a-one/screens.html", f"{base}/index.html"]), err
    assert f"{base}/a-one/screens/home.html (" in err  # the variant's own screen files are the ones named
    code = BP.main(["--root", str(project / SKILL_REL), "--check", "--proposal", "pick"])
    _out, err = capsys.readouterr()
    assert code == 0 and len(_size_warnings(err)) == 4, err


def test_size_warning_names_inline_data_uris(project: Path, monkeypatch, capsys) -> None:
    pixel = "data:image/png;base64," + "A" * 40000
    write(project / SCREENS_REL / "photo.html", '<section data-screen="photo" data-title="Photo"><div data-state="ready">'
          f'<img src="{pixel}" alt="A photo"></div></section>\n')
    monkeypatch.setattr(BP, "PAGE_WARN_BYTES", 30000)
    assert BP.main(["--root", str(project / SKILL_REL)]) == 0
    err = capsys.readouterr()[1]
    note = next(ln for ln in err.splitlines() if ln.startswith("note: "))
    assert note.split("the largest: ", 1)[1].startswith(f"{SCREENS_REL}/photo.html (0.1 MB, 0.1 MB of it inline data: URIs)")


def test_size_figures_round_up_and_never_read_as_the_limit(monkeypatch) -> None:
    mib = 1024 * 1024
    assert BP._mb(10 * mib + 1) == "10.1" and BP._mb(10 * mib) == "10.0" and BP._mb(12 * mib + mib // 3) == "12.4"
    assert BP._mb(1) == "0.1"
    assert BP._limit() == "10"
    monkeypatch.setattr(BP, "PAGE_WARN_BYTES", 2000)
    assert BP._limit() == "0.00191"


def test_pages_under_the_limit_do_not_warn(project: Path, monkeypatch, capsys) -> None:
    code = BP.main(["--root", str(project / SKILL_REL)])
    _out, err = capsys.readouterr()
    assert code == 0 and "MB" not in err, err  # the default limit (10 MB) is far above this project's pages
    assert BP.PAGE_WARN_BYTES == 10 * 1024 * 1024
    exact = (project / CATALOGUE_REL).stat().st_size
    monkeypatch.setattr(BP, "PAGE_WARN_BYTES", exact)  # a page exactly at the limit is not over it
    code = BP.main(["--root", str(project / SKILL_REL)])
    _out, err = capsys.readouterr()
    assert code == 0 and CATALOGUE_REL not in err, err


NEST = ('<section data-screen="nest" data-title="Nested states" data-order="0">\n'
        '  <div class="wrap"><article data-state="one"><p data-test="one">One</p>'
        '<span data-state="inner" data-test="inner">inner of one</span></article>\n'
        '  <article data-state="two" data-test="two">Two</article></div>\n'
        '  <p data-state="three" data-test="three">Three</p>\n'
        '  <p data-test="shared">In every state</p>\n'
        '</section>\n<script data-screen-script>\n'
        'screen.setAttribute("data-catalogue", String(plumb.catalogue));\n'
        'screen.setAttribute("data-ran", plumb.state());\n</script>\n')


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_catalogue_copies_pick_their_state_from_the_shared_template(browser, tmp_path: Path, scheme: str) -> None:
    """Each copy shows only its own outer state block (an inner [data-state] stays with its block), runs the screen's
    script with plumb.catalogue === true and its state, takes its own theme and sizes to its content."""
    p = make_project(tmp_path / "p", build=False)
    write(p / SCREENS_REL / "nest.html", NEST)
    assert run(p).returncode == 0
    ctx, page, errors, requests = _open(browser, p / CATALOGUE_REL, scheme=scheme)
    try:
        _copies_ready(page)
        expect = {"one": ["one", "inner", "shared"], "two": ["two", "shared"], "three": ["three", "shared"]}
        for state, shown in expect.items():
            for theme in ("light", "dark"):
                frame = _copy(page, f"nest/{state}/{theme}")
                seen = frame.locator("[data-test]").evaluate_all(
                    "els => els.filter(e => e.offsetParent !== null).map(e => e.dataset.test)")
                assert seen == shown, (state, theme, seen)
                frame.locator(f'[data-screen="nest"][data-ran="{state}"]').wait_for(state="attached")
                assert frame.locator('[data-screen="nest"]').get_attribute("data-catalogue") == "true"
                assert frame.locator("html").get_attribute("data-theme") == theme
                content = frame.locator("body").evaluate("b => Math.ceil(b.getBoundingClientRect().height)")
                height = page.evaluate(f"document.querySelector('[data-copy=\"nest/{state}/{theme}\"] iframe')"
                                       f".getBoundingClientRect().height")
                assert abs(height - content) <= 1, (state, theme, height, content)
        bg = "el => getComputedStyle(el).backgroundColor"
        assert _copy(page, "home/ready/light").locator("[data-screen]").evaluate(bg) == "rgb(255, 255, 255)"
        assert _copy(page, "home/ready/dark").locator("[data-screen]").evaluate(bg) == "rgb(15, 18, 23)"
        # the shared template itself stays as written: picking a copy's state never changes it
        assert page.evaluate("""document.querySelector('template[data-screen-markup="nest"]').content
            .querySelectorAll('[hidden]').length""") == 0
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


PADDED = ('<section data-screen="pad" data-title="Padded" data-order="0">\n'
          '  <div data-state=" ready " data-test="ready">Ready</div>\n'
          '  <div data-state="\n  empty\t" data-test="empty">Empty</div>\n'
          '</section>\n')


def test_padded_state_names_are_read_the_same_everywhere(browser, tmp_path: Path) -> None:
    """data-state=" ready " is the state "ready" in the build (screens.json, the switcher, the copies' keys), in
    prototype.html, in app.html and in every catalogue copy."""
    p = make_project(tmp_path / "p", build=False)
    write(p / SCREENS_REL / "pad.html", PADDED)
    assert run(p).returncode == 0
    assert entry(p, "pad")["states"] == ["ready", "empty"]
    assert 'data-copy="pad/ready/light"' in read(p / CATALOGUE_REL) and 'data-copy="pad/empty/dark"' in read(p / CATALOGUE_REL)
    shown = "els => els.filter(e => e.offsetParent !== null).map(e => e.dataset.test)"
    for rel, hash_, want in ((PROTO_REL, "#screen-pad", "ready"), (PROTO_REL, "#screen-pad/empty", "empty"),
                             (APP_REL, "#/pad", "ready"), (APP_REL, "#/pad/empty", "empty")):
        ctx, page, errors, _ = _open(browser, p / rel, hash_=hash_)
        try:
            assert page.locator('#pp-frame [data-screen="pad"] [data-test]').evaluate_all(shown) == [want], (rel, hash_)
            assert errors == []
        finally:
            ctx.close()
    ctx, page, errors, _ = _open(browser, p / CATALOGUE_REL)
    try:
        _copies_ready(page)
        for state in ("ready", "empty"):
            for theme in ("light", "dark"):
                assert _copy(page, f"pad/{state}/{theme}").locator("[data-test]").evaluate_all(shown) == [state]
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- shared files (<screens>/_shared/*.css, *.js)

SHARED_REL = f"{SCREENS_REL}/_shared"
SHARED_A_JS = ('(window.__order = window.__order || []).push("a:" + plumb.screen);\n'
               'screen.setAttribute("data-shared-catalogue", String(plumb.catalogue));\n')
SHARED_B_JS = '(window.__order = window.__order || []).push("b:" + plumb.screen + ":" + plumb.state());\n'
SHARED_CSS = '[data-screen] { outline: 3px solid rgb(1, 2, 3); }\n'
OWN_HOME_JS = '\n<script data-screen-script>\n(window.__order = window.__order || []).push("own:" + plumb.screen);\n</script>\n'


def add_shared(project: Path, folder: str = SHARED_REL) -> None:
    write(project / folder / "b.js", SHARED_B_JS)
    write(project / folder / "a.js", SHARED_A_JS)
    write(project / folder / "z-layout.css", SHARED_CSS)
    write(project / folder / "a-base.css", '[data-screen] .muted { letter-spacing: 0.01em; }\n')
    write(project / folder / "notes.md", "not a shared file: only .css and .js are read\n")


def test_underscore_screens_stay_screens_and_only_the_shared_folder_is_reserved(tmp_path: Path) -> None:
    """Backwards compatible: a screen file named _x.html (or _shared.html, a file) is a screen as before, its approval
    kept; only the _shared folder is reserved, and nothing in it is a screen. The audit reads the same screens."""
    p = make_project(tmp_path / "p", build=False)
    menu = read(p / SCREENS_REL / "menu.html")
    write(p / SCREENS_REL / "_legacy.html", menu.replace('data-screen="menu"', 'data-screen="_legacy"'))
    write(p / SCREENS_REL / "_shared.html", menu.replace('data-screen="menu"', 'data-screen="_shared"'))
    assert run(p).returncode == 0
    assert run(p, "--approve", "_legacy", env=clean_env(tmp_path, USER="Ana", USERNAME="Ana")).returncode == 0
    approved = entry(p, "_legacy")["approved"]
    write(p / SHARED_REL / "x.html", menu.replace('data-screen="menu"', 'data-screen="x"'))
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    ids = [s["id"] for s in screens_json(p)["screens"]]
    assert sorted(ids) == sorted(["home", "booking", "menu", "_legacy", "_shared"]) and "x" not in ids
    assert entry(p, "_legacy")["approved"] == approved and "has no file any more" not in r.stdout
    assert 'data-screen="x"' not in read(p / PROTO_REL)
    assert [s.id for s in BP.load_screens(p / SCREENS_REL, p, BT.rel)] == ids  # what audit.py's fidelity reads


def test_only_shared_files_is_no_prototype(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", screens=False, build=False)
    add_shared(p)
    assert_refusal(run(p), "no screen files")


def test_shared_css_is_inlined_once_per_page_in_name_order(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    add_shared(p)
    shutil.copytree(FIXTURE / "tours", p / DOCS / "prototype/tours")
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    pages = {rel: read(p / rel) for rel in (PROTO_REL, APP_REL, CATALOGUE_REL, f"{DOCS}/tours/demo.html")}
    for rel, text in pages.items():
        assert text.count("outline: 3px solid rgb(1, 2, 3)") == 1, rel
        assert text.count("letter-spacing: 0.01em") == 1, rel
        assert text.count('(window.__order = window.__order || []).push("a:"') == 1, rel  # each shared JS once
        assert text.index("letter-spacing: 0.01em") < text.index("outline: 3px solid"), rel  # name order
        assert "not a shared file" not in text, rel
        assert not NETWORK.search(text), rel
    proto = pages[PROTO_REL]
    assert proto.index('data-shared-style="_shared/z-layout.css"') < proto.index('data-screen-style="home"')
    assert proto.index('data-shared-script="_shared/a.js"') < proto.index('data-shared-script="_shared/b.js"')
    # screens.html stores them once, in two templates every copy takes
    cat = pages[CATALOGUE_REL]
    assert cat.count("<template data-shared-styles>") == 1 and cat.count("<template data-shared-scripts>") == 1


def test_no_shared_folder_changes_nothing(project: Path) -> None:
    """A project without _shared/ builds the pages it built before: no shared runtime, no extra templates."""
    for rel in (PROTO_REL, APP_REL, CATALOGUE_REL):
        text = read(project / rel)
        assert "useShared" not in text and "data-shared-style=" not in text and "<template data-shared" not in text, rel
    write(project / SHARED_REL / "readme.md", "only notes here\n")
    assert run(project, "--check").returncode == 0  # a _shared folder with no .css or .js holds no shared file


def test_shared_files_feed_the_approval_hash(project: Path, tmp_path: Path) -> None:
    env = clean_env(tmp_path, USER="Ana", USERNAME="Ana")
    assert run(project, "--approve", "home", env=env).returncode == 0
    approved = entry(project, "home")["approved"]
    # recorded before any shared file: the screen file's own hash, exactly as before shared files existed
    assert approved["hash"] == file_hash(project / SCREENS_REL / "home.html") and "shared" not in approved
    write(project / SHARED_REL / "notes.md", "x\n")
    r = run(project, env=env)
    assert r.returncode == 0 and "changed since Ana" not in r.stdout, r.stdout  # no .css/.js: still approved
    assert BP.screen_file_hash(project / SCREENS_REL / "home.html") == approved["hash"]
    write(project / SHARED_REL / "base.css", SHARED_CSS)
    r = run(project, env=env)
    assert r.returncode == 0
    assert "screen home changed since Ana approved it" in r.stdout
    assert f"{SHARED_REL}/base.css was added" in r.stdout and "the screen file changed too" not in r.stdout
    assert "ask the user: approve screen home" in r.stdout
    assert run(project, "--approve", "home", env=env).returncode == 0
    approved = entry(project, "home")["approved"]
    assert set(approved["shared"]) == {"_shared/base.css"}
    assert BP.screen_file_hash(project / SCREENS_REL / "home.html") == approved["hash"]
    assert "changed since Ana" not in run(project, env=env).stdout
    # editing the shared file makes the approval stale, naming the file
    write(project / SHARED_REL / "base.css", SHARED_CSS.replace("3px", "4px"))
    r = run(project, env=env)
    assert (f"note: screen home changed since Ana approved it on {approved['at']} (the shared file: "
            f"{SHARED_REL}/base.css changed; shared files reach every screen)") in r.stdout, r.stdout
    page = read(project / PROTO_REL)
    assert 'data-approval="stale"' in page[page.index('data-nav="home"'):][:600]
    # both changed: said too
    home = project / SCREENS_REL / "home.html"
    write(home, read(home).replace("No bookings yet today.", "Nothing yet."))
    assert "the screen file changed too" in run(project, env=env).stdout
    # both back as they were: approved again
    write(home, read(home).replace("Nothing yet.", "No bookings yet today."))
    write(project / SHARED_REL / "base.css", SHARED_CSS)
    assert "changed since Ana" not in run(project, env=env).stdout
    (project / SHARED_REL / "base.css").unlink()
    assert f"{SHARED_REL}/base.css was removed" in run(project, env=env).stdout


def test_check_covers_shared_files_and_builds_are_byte_stable(project: Path) -> None:
    add_shared(project)
    assert run(project, "--check").returncode == 1
    assert run(project).returncode == 0
    before = {rel: (project / rel).read_bytes() for rel in (PROTO_REL, APP_REL, CATALOGUE_REL, JSON_REL)}
    r = run(project)
    assert r.returncode == 0 and "up to date" in r.stdout
    assert {rel: (project / rel).read_bytes() for rel in before} == before
    assert run(project, "--check").returncode == 0
    write(project / SHARED_REL / "a.js", SHARED_A_JS + "// changed\n")
    r = run(project, "--check")
    assert r.returncode == 1 and PROTO_REL in r.stdout and APP_REL in r.stdout and CATALOGUE_REL in r.stdout
    assert JSON_REL not in r.stdout  # the map holds no page content


@pytest.mark.parametrize("name, text, needle", [
    ("x.js", 'var s = "</script>";\n', "</script"),
    ("x.js", 'fetch("/api/tables").then(function (r) { return r.json(); });\n', "fetch("),
    ("x.js", 'window.fetch("data.json");\n', "fetch("),
    ("x.js", 'var x = new XMLHttpRequest();\n', "XMLHttpRequest"),
    ("x.js", 'import("./more.js");\n', "import("),
    ("x.js", 'import { a } from "./a.js";\n', "import"),
    ("x.js", 'var t = `rows: ${fetch("/rows")}`;\n', "fetch("),  # a template's ${...} is code
    ("x.js", 'var u = "// not a comment"; fetch("/y");\n', "fetch("),  # a string ends before the code
    ("x.js", "var q = /'/; fetch(\"/x\");\n", "fetch("),  # a quote in a regex literal opens no string
    ("x.js", 'var h = s.replace(/[/"]/g, "") / 2; fetch("/z");\n', "fetch("),  # / in a class; then a division
    ("x.js", 'var x = i++ / 2; fetch("/x");\n', "fetch("),  # a postfix ++ then / divides
    ("x.js", 'var y = j-- / 2 / 3; fetch("/y");\n', "fetch("),
    ("x.js", "switch (k) { case /'/.source: fetch(\"/c\"); }\n", "fetch("),  # a regex after case
    ("x.js", "if (k in /'/) fetch(\"/i\");\n", "fetch("),
    ("x.css", '</style><script>alert(1)</script>\n', "</style"),
    ("x.css", '@import url("https://example.com/x.css");\n', "@import"),
    ("x.css", '@import "local.css";\n', "@import"),
    ("x.css", '[data-screen] { background: url(https://example.com/bg.png); }\n', "url(https://"),
    ("x.css", '[data-screen] { background: url( "//cdn.example.com/bg.png" ); }\n', "//"),
])
def test_shared_file_contract_refusals(project: Path, name: str, text: str, needle: str) -> None:
    write(project / SHARED_REL / name, "/* line one */\n" + text)
    assert_refusal(run(project), f"{SHARED_REL}/{name}:2", needle)
    assert_refusal(run(project, "--check"), f"{SHARED_REL}/{name}")


def test_shared_files_that_load_nothing_are_accepted(project: Path) -> None:
    """False positives: a function named prefetch, a method named fetch, a URL in a string, url(#id), relative and
    data: URLs, @import inside a CSS comment."""
    write(project / SHARED_REL / "ok.js", 'function prefetch(x) { return x; }\nvar api = { fetch: function () {} };\n'
                                          'api.fetch(); prefetch(1);\nvar help = "https://example.com/help";\n'
                                          'var important = 1;\n// never fetch() here: the data is inline\n'
                                          '/* new XMLHttpRequest() was the old way;\n   import("x") too */\n'
                                          'var tip = `\nimport your list from a spreadsheet: fetch("it")`;\n'
                                          "var s = 'see https://example.com/api, fetch(later)';\n"
                                          "function f(s) { return /fetch(es)?|import(ed)?/.test(s); }\n"
                                          "function g(s) { switch (s) { case /fetch(es)?/.source: throw /import(s)/; "
                                          "default: return void /fetch(x)/; } }\nvar n = 0; n++ / 2; n-- / 2;\n")
    write(project / SHARED_REL / "ok.css", '/* @import was here */\n[data-screen] .icon { mask: url(#m); '
                                           'background: url(img/bg.png), url("data:image/svg+xml,'
                                           '%3Csvg xmlns=%27http://www.w3.org/2000/svg%27/%3E"); }\n')
    r = run(project)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "warning" not in r.stderr, r.stderr


def test_unscoped_shared_css_warns(project: Path) -> None:
    write(project / SHARED_REL / "loose.css", '.card { padding: 4px; }\n[data-screen="home"] h2, button { margin: 0; }\n'
                                              '@media (min-width: 40rem) { [data-screen] .x { color: red; } }\n')
    r = run(project)
    assert r.returncode == 0
    assert f'warning: {SHARED_REL}/loose.css:1: the style rule ".card"' in r.stderr, r.stderr
    assert f'warning: {SHARED_REL}/loose.css:2: the style rule "button"' in r.stderr
    assert 'rule "[data-screen' not in r.stderr  # scoped rules are fine
    assert f"fix: start each selector in {SHARED_REL}/loose.css with [data-screen]" in r.stderr
    r = run(project, "--check")  # --check says it too
    assert r.returncode == 0 and f'warning: {SHARED_REL}/loose.css:1: the style rule ".card"' in r.stderr, r.stderr


@pytest.mark.parametrize("problem", ["shared", "change-id"])
def test_a_refused_shared_file_or_id_does_not_block_the_map(project: Path, tmp_path: Path, problem: str) -> None:
    """Like a broken tour: --approve (and --map, --synced) still records the map and warns; the build and --check exit
    2 until it is fixed."""
    if problem == "shared":
        write(project / SHARED_REL / "x.js", 'fetch("/x");\n')
        needle = f"{SHARED_REL}/x.js:1"
    else:
        write(project / DOCS / "prototype/changes.md", "- **C1** Heading: clearer\n")
        home = project / SCREENS_REL / "home.html"
        write(home, read(home).replace("<h2>", '<h2 data-guide="C2 · Not listed">', 1))
        needle = "uses C2"
    before = read(project / PROTO_REL)
    r = run(project, "--approve", "booking", env=clean_env(tmp_path, USER="Ana", USERNAME="Ana"))
    assert r.returncode == 0, r.stderr
    assert entry(project, "booking")["approved"]["by"] == "Ana"
    assert "warning: the pages were not rebuilt because a shared file or a change id is refused" in r.stderr
    assert needle in r.stderr and "\nfix: " in r.stderr and r.stderr.count("then run") == 1, r.stderr
    assert read(project / PROTO_REL) == before
    assert_refusal(run(project), needle)
    assert_refusal(run(project, "--check"), needle)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_shared_js_runs_for_each_screen_before_its_own_script(browser, tmp_path: Path, scheme: str) -> None:
    """Every page: each shared JS file runs once per screen (per copy in screens.html), in name order, before the
    screen's own script, with the same API (plumb.screen, plumb.state(), plumb.catalogue); the shared CSS styles every
    screen."""
    p = make_project(tmp_path / "p", build=False)
    add_shared(p)
    home = p / SCREENS_REL / "home.html"
    write(home, read(home) + OWN_HOME_JS)
    tour = json.loads(read(FIXTURE / "tours/demo.json"))
    for view in ("app", "prototype"):  # both views a tour page plays in
        write(p / DOCS / f"prototype/tours/in-{view}.json", json.dumps(dict(tour, view=view), ensure_ascii=False))
    assert run(p).returncode == 0
    order_of = "window.__order || []"
    tour_pages = [f"{DOCS}/tours/in-app.html", f"{DOCS}/tours/in-prototype.html"]
    assert 'id="plumb-guide"' in read(p / tour_pages[1]) and 'id="plumb-guide"' not in read(p / tour_pages[0])
    for rel in [PROTO_REL, APP_REL] + tour_pages:
        ctx, page, errors, requests = _open(browser, p / rel, scheme=scheme)
        try:
            # the shared CSS is in the page once, the shared JS once (it runs per screen, below)
            assert page.evaluate("[...document.querySelectorAll('style')]"
                                 ".filter(s => s.textContent.includes('rgb(1, 2, 3)')).length") == 1, rel
            assert page.evaluate("[...document.querySelectorAll('script')]"
                                 ".filter(s => s.textContent.includes('push(\"a:\"')).length") == 1, rel
            order = page.evaluate(order_of)
            for sid in ("home", "booking", "menu"):
                assert order.count(f"a:{sid}") == 1, (rel, order)
                assert order.index(f"a:{sid}") < next(i for i, x in enumerate(order) if x.startswith(f"b:{sid}:")), order
            assert order.index("b:home:ready") < order.index("own:home"), order
            assert order.index("a:home") < order.index("a:booking") < order.index("a:menu"), order  # screen order
            flags = page.evaluate("[...document.querySelectorAll('#pp-frame > [data-screen]')]"
                                  ".map(s => s.getAttribute('data-shared-catalogue'))")
            assert flags == ["false"] * 3, (rel, flags)
            assert page.evaluate("getComputedStyle(document.querySelector('#pp-frame > [data-screen]')).outlineColor") \
                == "rgb(1, 2, 3)"
            assert page.locator('[data-screen="booking"][data-script-ran="yes"]').count() == 1  # its own script too
            assert errors == [] and requests == [], (rel, errors, requests)
        finally:
            ctx.close()
    ctx, page, errors, requests = _open(browser, p / CATALOGUE_REL, scheme=scheme)
    try:
        _copies_ready(page)
        for state in SCREENS["home"]:
            for theme in ("light", "dark"):
                frame = _copy(page, f"home/{state}/{theme}")
                frame.locator('[data-screen="home"][data-shared-catalogue="true"]').wait_for(state="attached")
                order = frame.locator("body").evaluate(f"() => {order_of}")
                assert order == ["a:home", f"b:home:{state}", "own:home"], (state, theme, order)
                assert frame.locator('[data-screen="home"]').evaluate("s => getComputedStyle(s).outlineColor") \
                    == "rgb(1, 2, 3)"
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


def test_a_failing_shared_script_is_named_and_the_rest_still_runs(browser, tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    add_shared(p)
    write(p / SHARED_REL / "a0-broken.js", 'throw new Error("boom");\n')
    assert run(p).returncode == 0
    ctx, page, errors, _ = _open(browser, p / APP_REL)
    try:
        assert "a:home" in page.evaluate("window.__order || []")
        assert any("the shared script _shared/a0-broken.js failed on screen home" in e for e in errors), errors
    finally:
        ctx.close()


# ---------------------------------------------------------------- a page Plumb did not write is never replaced

OTHER_TOOL = ("<!doctype html>\n<html lang=\"en\">\n<head>\n"
              "<!-- GENERATED by tools/build-app.py from design/screens/. Do not edit: run make app. -->\n"
              "<style>/* plumb:theme */ x /* plumb:theme:end */</style>\n</head><body>the project's own app view</body></html>\n")


@pytest.mark.parametrize("page", [APP_REL, PROTO_REL, CATALOGUE_REL])
@pytest.mark.parametrize("text", [OTHER_TOOL, "<!doctype html>\n<p>written by hand</p>\n"], ids=["other-tool", "by-hand"])
def test_a_page_another_tool_or_a_person_wrote_is_never_replaced(tmp_path: Path, page: str, text: str) -> None:
    p = make_project(tmp_path / "p", build=False)
    write(p / page, text)
    r = run(p)
    assert_refusal(r, page, "not Plumb's", "ask the user", "mv ", ".before-plumb.html")
    assert read(p / page) == text
    others = {PROTO_REL, APP_REL, CATALOGUE_REL, JSON_REL} - {page}
    assert not any((p / o).exists() for o in others), "nothing is written when one page is someone else's"
    c = run(p, "--check")
    assert c.returncode == 1 and f"not Plumb's: {page}" in c.stdout and "ask the user" in c.stdout
    assert read(p / page) == text
    (p / page).rename(p / page.replace(".html", ".before-plumb.html"))
    assert run(p).returncode == 0 and run(p, "--check").returncode == 0


def test_every_page_in_the_way_is_named_at_once(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    write(p / APP_REL, OTHER_TOOL)
    write(p / CATALOGUE_REL, "<p>mine</p>\n")
    r = run(p)
    assert r.returncode == 2 and APP_REL in r.stderr and CATALOGUE_REL in r.stderr


def test_plumb_pages_from_an_older_build_or_another_skill_path_are_replaced(project: Path) -> None:
    for rel in (APP_REL, PROTO_REL):
        old = read(project / rel).replace(SKILL_REL, ".github/skills/demo-design-system").replace("<body", "<body data-old")
        write(project / rel, old)
    assert run(project).returncode == 0 and run(project, "--check").returncode == 0


def test_build_tokens_leaves_a_page_it_did_not_write(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", build=False)
    write(p / APP_REL, OTHER_TOOL)
    assert build_tokens(p).returncode == 0
    assert read(p / APP_REL) == OTHER_TOOL
    assert build_tokens(p, "--check").returncode == 0
