"""build-prototype.py --proposal NAME: the variants of /plumb:prototype, each built as both views (prototype.html and
screens.html, light and dark, the token block inlined) plus NAME/index.html with the variants side by side. Generated,
byte-stable, offline; token changes refresh them (the default build and build-tokens.py); --check finds them stale.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_build_prototype import (BT, DOCS, FIXTURE, JSON_REL, NETWORK, PROTO_REL, SCRIPTS, SKILL_REL, TOKENS_REL, P,
                                  assert_refusal, build_tokens, make_project, read, run, write)

PROPOSALS = f"{DOCS}/prototype/proposals"
NAME = "billing"
IDEA_A = "# Calm list\n\nOne list of tonight's tables, the booking form in a side sheet.\n\n- Fast for regulars: one screen\n- Busy on a phone\n"


def add_variants(project: Path, name: str = NAME) -> Path:
    base = project / PROPOSALS / name
    for screen in ("home", "booking"):
        write(base / "a-calm/screens" / f"{screen}.html", read(FIXTURE / "screens" / f"{screen}.html"))
    write(base / "a-calm/idea.md", IDEA_A)
    dense = read(FIXTURE / "screens/home.html").replace('data-title="Today\'s tables"', 'data-title="Tables, dense"')
    write(base / "b-dense/screens/home.html", dense)
    return base


@pytest.fixture()
def proposal(tmp_path: Path) -> Path:
    project = make_project(tmp_path / "Café Ünïcode")
    add_variants(project)
    return project


def pages(project: Path, name: str = NAME) -> dict:
    base = project / PROPOSALS / name
    return {p.relative_to(base).as_posix(): p for p in sorted(base.rglob("*.html"))
            if "screens" not in p.relative_to(base).parts[:-1]}


def theme_region(text: str) -> str:
    start = text.index("/* plumb:theme")
    return text[start:text.index("/* plumb:theme:end */", start)]


def test_builds_both_views_per_variant_and_the_index(proposal: Path) -> None:
    main_map, main_proto = read(proposal / JSON_REL), read(proposal / PROTO_REL)
    r = run(proposal, "--proposal", NAME)
    assert r.returncode == 0, r.stdout + r.stderr
    built = pages(proposal)
    assert sorted(built) == ["a-calm/app.html", "a-calm/prototype.html", "a-calm/screens.html", "b-dense/app.html",
                             "b-dense/prototype.html", "b-dense/screens.html", "index.html"]
    doc = json.loads(read(proposal / TOKENS_REL))
    block = BT.token_block(doc)
    for rel, path in built.items():
        text = read(path)
        assert text.startswith("<!doctype html>"), rel
        assert "GENERATED" in "\n".join(text.splitlines()[:3]) and "--proposal billing" in text, rel
        assert block in text, rel
        assert not NETWORK.search(text), (rel, NETWORK.search(text))
        header = "\n".join(text.splitlines()[:3])
        assert str(proposal) not in header and str(proposal.resolve()) not in header, rel  # project-relative only
    a = read(built["a-calm/prototype.html"])
    assert 'data-nav="home"' in a and 'data-nav="booking"' in a
    cat = read(built["a-calm/screens.html"])
    assert 'data-copy="booking/error/dark"' in cat and 'data-copy="booking/error/light"' in cat
    assert 'data-nav="booking"' not in read(built["b-dense/prototype.html"])
    app = read(built["a-calm/app.html"])
    assert '<section data-screen="home"' in app and 'data-screen="booking"' in app and "data-states-for" not in app
    assert P.is_generated_proposal_page(app)
    index = read(built["index.html"])
    for text in ("Calm list", "One list of tonight", "Fast for regulars", "Busy on a phone", "B dense"):
        assert text in index, text
    for href in ("a-calm/prototype.html", "a-calm/app.html", "a-calm/screens.html", "b-dense/prototype.html",
                 "b-dense/app.html", "b-dense/screens.html"):
        assert f'href="{href}"' in index, href
    card = index[index.index('data-variant="a-calm"'):index.index('data-variant="b-dense"')]
    assert card.index("Review: prototype.html") < card.index("Demo: app.html")  # review, then demo
    assert read(proposal / JSON_REL) == main_map and read(proposal / PROTO_REL) == main_proto  # main untouched
    assert "variant" in r.stdout and "billing" in r.stdout


def test_byte_stable_and_check(proposal: Path) -> None:
    assert run(proposal, "--proposal", NAME).returncode == 0
    before = {k: p.read_bytes() for k, p in pages(proposal).items()}
    r = run(proposal, "--proposal", NAME)
    assert r.returncode == 0 and "up to date" in r.stdout, r.stdout
    assert {k: p.read_bytes() for k, p in pages(proposal).items()} == before
    assert run(proposal, "--check", "--proposal", NAME).returncode == 0
    screen = proposal / PROPOSALS / NAME / "b-dense/screens/home.html"
    write(screen, read(screen).replace("Tables, dense", "Tables, denser"))
    r = run(proposal, "--check", "--proposal", NAME)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "b-dense/prototype.html" in r.stdout and "b-dense/screens.html" in r.stdout
    assert "b-dense/app.html" in r.stdout
    assert "a-calm" not in r.stdout and "--proposal billing" in r.stdout
    assert {k: p.read_bytes() for k, p in pages(proposal).items()} == before  # --check writes nothing
    assert run(proposal, "--proposal", NAME).returncode == 0
    app = proposal / PROPOSALS / NAME / "a-calm/app.html"
    app.unlink()
    r = run(proposal, "--check", "--proposal", NAME)
    assert r.returncode == 1 and "a-calm/app.html (missing)" in r.stdout, r.stdout
    assert not app.exists()


def _retoken(project: Path) -> str:
    doc = json.loads(read(project / TOKENS_REL))
    doc["color"]["primary"]["$value"] = "#123456"
    write(project / TOKENS_REL, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return BT.token_block(doc)


def test_token_change_refreshed_by_build_tokens(proposal: Path) -> None:
    assert run(proposal, "--proposal", NAME).returncode == 0
    hand = proposal / PROPOSALS / "old/index.html"
    write(hand, "<!doctype html><style>/* plumb:theme */ x /* plumb:theme:end */</style>\n")  # not generated: left alone
    block = _retoken(proposal)
    r = build_tokens(proposal, "--check")
    assert r.returncode == 1 and "proposals/billing/a-calm/prototype.html" in r.stdout, r.stdout
    assert build_tokens(proposal).returncode == 0
    for rel, path in pages(proposal).items():
        assert block in read(path), rel
    assert build_tokens(proposal, "--check").returncode == 0
    assert run(proposal, "--check", "--proposal", NAME).returncode == 0
    assert read(hand) == "<!doctype html><style>/* plumb:theme */ x /* plumb:theme:end */</style>\n"


def test_token_change_refreshed_by_the_default_build(proposal: Path) -> None:
    assert run(proposal, "--proposal", NAME).returncode == 0
    variant_screen = read(proposal / PROPOSALS / NAME / "a-calm/screens/home.html")
    block = _retoken(proposal)
    r = run(proposal, "--check")
    assert r.returncode == 1 and "proposals/billing/index.html (token block" in r.stdout, r.stdout
    r = run(proposal)
    assert r.returncode == 0, r.stdout + r.stderr
    for rel, path in pages(proposal).items():
        assert block in read(path), rel
    assert run(proposal, "--check").returncode == 0
    assert run(proposal, "--check", "--proposal", NAME).returncode == 0
    assert read(proposal / PROPOSALS / NAME / "a-calm/screens/home.html") == variant_screen


def test_proposals_need_no_main_screens(tmp_path: Path) -> None:
    project = make_project(tmp_path / "fresh", screens=False, build=False)
    add_variants(project)
    r = run(project, "--proposal", NAME)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (project / JSON_REL).exists()


def test_refusals(proposal: Path) -> None:
    assert_refusal(run(proposal, "--proposal", "nothing-here"), "nothing-here", "/plumb:prototype")
    # a name that is not a folder name: one exact command as the fix (the name cleaned up, or an example)
    for given, suggested in (("../x", "x"), ("nav refresh", "nav-refresh"), ("../..", "nav-refresh")):
        r = run(proposal, "--proposal", given)
        assert_refusal(r, "--proposal")
        fix = r.stderr.split("\nfix: ", 1)[1].rstrip("\n")
        assert "\n" not in fix and "[--check]" not in fix, r.stderr
        assert fix.startswith("use a proposal name of letters, digits, _ and -, e.g. python3 "), fix
        assert fix.endswith(f"build-prototype.py --proposal {suggested}"), fix
    (proposal / PROPOSALS / "empty").mkdir(parents=True)
    assert_refusal(run(proposal, "--proposal", "empty"), "no variant")
    write(proposal / PROPOSALS / NAME / "c-broken/screens/x.html", "<p>no section</p>\n")
    assert_refusal(run(proposal, "--proposal", NAME), "c-broken/screens/x.html")
    shutil.rmtree(proposal / PROPOSALS / NAME / "c-broken")
    write(proposal / PROPOSALS / NAME / "c-empty/idea.md", "# Nothing\n")
    assert_refusal(run(proposal, "--proposal", NAME), "c-empty", "screens/")
    shutil.rmtree(proposal / PROPOSALS / NAME / "c-empty")
    assert_refusal(run(proposal, "--proposal", NAME, "--approve", "home"), "--proposal")
    assert run(proposal, "--proposal", NAME).returncode == 0


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"requires POSIX: symlinks ({exc})")


def test_a_variant_or_proposal_linked_outside_is_refused(proposal: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    write(outside / "screens/home.html", read(FIXTURE / "screens/home.html"))
    _symlink_or_skip(proposal / PROPOSALS / NAME / "c-link", outside)
    r = run(proposal, "--proposal", NAME)
    assert_refusal(r, "c-link", "outside")
    assert not (outside / "prototype.html").exists() and not (outside / "screens.html").exists()
    (proposal / PROPOSALS / NAME / "c-link").unlink()
    away = tmp_path / "away-proposal"
    write(away / "a-x/screens/home.html", read(FIXTURE / "screens/home.html"))
    _symlink_or_skip(proposal / PROPOSALS / "linked", away)
    assert_refusal(run(proposal, "--proposal", "linked"), "linked", "outside")
    assert not (away / "index.html").exists()


def test_only_pages_built_by_proposal_are_refreshed(proposal: Path) -> None:
    other = proposal / PROPOSALS / "other/index.html"
    text = ("<!doctype html>\n<!-- GENERATED by another-tool. Do not edit. -->\n"
            "<style>/* plumb:theme */ x /* plumb:theme:end */</style>\n")
    write(other, text)
    assert run(proposal, "--proposal", NAME).returncode == 0
    _retoken(proposal)
    assert build_tokens(proposal).returncode == 0
    assert run(proposal).returncode == 0
    assert read(other) == text
    assert build_tokens(proposal, "--check").returncode == 0
    assert P.is_generated_proposal_page(read(proposal / PROPOSALS / NAME / "index.html"))
    assert P.is_generated_proposal_page(read(proposal / PROPOSALS / NAME / "a-calm/screens.html"))
    assert not P.is_generated_proposal_page(text)
    assert not P.is_generated_proposal_page(read(proposal / PROTO_REL))


def test_audit_skips_the_generated_pages_and_checks_the_screen_files(proposal: Path) -> None:
    skill = proposal / SKILL_REL / "scripts"
    shutil.copy(SCRIPTS / "audit.py", skill / "audit.py")
    assert run(proposal, "--proposal", NAME).returncode == 0
    r = subprocess.run([sys.executable, str(skill / "audit.py"), str(proposal / PROPOSALS / NAME), "--json"],
                       cwd=str(proposal), capture_output=True, text=True, encoding="utf-8")
    data = json.loads(r.stdout)
    files = {f["file"] for f in data["findings"]}
    assert not any(f.endswith(("index.html", "/prototype.html", "/app.html", "/screens.html")) for f in files), files
    assert data["checked"] == 3  # the three variant screen files, not the generated pages


# ---------------------------------------------------------------- browser (headless)


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("requires Playwright")
    return sync_playwright


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    project = make_project(tmp_path_factory.mktemp("prop") / "Café Ünïcode")
    add_variants(project)
    r = run(project, "--proposal", NAME)
    assert r.returncode == 0, r.stdout + r.stderr
    return project / PROPOSALS / NAME


@pytest.fixture(scope="module")
def browser():
    sync_playwright = _playwright()
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


def _open(browser, path: Path, width: int, scheme: str):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
    page = ctx.new_page()
    errors: list = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    requests: list = []
    page.on("request", lambda req: requests.append(req.url) if not req.url.startswith(("file:", "data:", "about:")) else None)
    page.goto(path.resolve().as_uri())
    page.wait_for_load_state("load")
    return ctx, page, errors, requests


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_index_shows_every_variant(browser, built: Path, width: int, scheme: str) -> None:
    ctx, page, errors, requests = _open(browser, built / "index.html", width, scheme)
    try:
        assert page.evaluate("document.documentElement.dataset.theme") == scheme
        assert page.locator("[data-variant]").count() == 2
        assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
        before = page.evaluate("getComputedStyle(document.body).backgroundColor")
        page.click("#theme-toggle")
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") != before
        page.click('[data-variant="a-calm"] a[href="a-calm/prototype.html"]')
        page.wait_for_load_state("load")
        assert page.url.endswith("a-calm/prototype.html")
        page.go_back()
        page.click('[data-variant="a-calm"] a[href="a-calm/app.html"]')
        page.wait_for_load_state("load")
        assert page.url.endswith("a-calm/app.html")
        assert page.locator("#pp-frame > [data-screen]:not([hidden])").count() == 1
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


@pytest.mark.parametrize("view", ["prototype.html", "app.html", "screens.html"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_each_view_renders_in_both_themes(browser, built: Path, view: str, scheme: str) -> None:
    for variant in ("a-calm", "b-dense"):
        ctx, page, errors, requests = _open(browser, built / variant / view, 1280, scheme)
        try:
            assert page.evaluate("document.documentElement.dataset.theme") == scheme
            if view == "screens.html":
                page.wait_for_function(
                    "[...document.querySelectorAll('figure[data-copy] iframe')].every(f => f.dataset.sized)")
                themes = page.evaluate("[...document.querySelectorAll('figure[data-copy]')].map(f => f.dataset.copy.split('/')[2])")
                assert set(themes) == {"light", "dark"}
            else:
                assert page.locator("#pp-frame > [data-screen]").count() >= 1
            before = page.evaluate("getComputedStyle(document.body).backgroundColor")
            if view == "app.html":  # no chrome: the screens' own toggle (none here) or the API switches the theme
                assert page.locator("#theme-toggle").count() == 0
                page.evaluate("window.plumbTheme.toggle()")
            else:
                page.click("#theme-toggle")
            assert page.evaluate("getComputedStyle(document.body).backgroundColor") != before
            assert errors == [] and requests == [], (variant, errors, requests)
        finally:
            ctx.close()


# ---------------------------------------------------------------- change ids (changes.md) and shared files

CHANGES = ("# Changes in this proposal\n\nFree text is fine here.\n\n"
           "- **F01** One list: tonight's tables in one list, the form in a side sheet\n"
           "- **F02** Denser rows: more tables fit on a laptop screen\n")


def mark(project: Path, variant: str, screen: str, text: str, name: str = NAME) -> None:
    path = project / PROPOSALS / name / variant / "screens" / f"{screen}.html"
    write(path, read(path).replace("<h2>", f'<h2 data-guide="{text}">', 1))


def test_change_ids_listed_in_changes_md_build_and_the_index_lists_them(proposal: Path) -> None:
    write(proposal / PROPOSALS / NAME / "changes.md", CHANGES)
    mark(proposal, "a-calm", "home", "F01 · One list of tonight's tables")
    mark(proposal, "a-calm", "booking", "F01 · The form opens in a side sheet")
    mark(proposal, "b-dense", "home", "F02 · Denser rows")
    r = run(proposal, "--proposal", NAME)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "warning" not in r.stderr, r.stderr
    index = read(proposal / PROPOSALS / NAME / "index.html")
    changes = index[index.index('class="changes"'):]
    assert changes.index('id="change-F01"') < changes.index('id="change-F02"')
    assert '<span class="chip">F01</span>' in changes and "<strong>One list</strong>" in changes
    assert "tonight&#x27;s tables in one list" in changes or "tonight's tables in one list" in changes
    assert "In a-calm: Today&#x27;s tables, a-calm: New booking" in changes
    assert "In b-dense: Tables, dense" in changes
    assert run(proposal, "--check", "--proposal", NAME).returncode == 0


def test_an_unknown_change_id_refuses_naming_the_screen_and_the_id(proposal: Path) -> None:
    write(proposal / PROPOSALS / NAME / "changes.md", CHANGES)
    mark(proposal, "b-dense", "home", "F07 · Not listed")
    changes_rel = f"{PROPOSALS}/{NAME}/changes.md"
    for args in (("--proposal", NAME), ("--check", "--proposal", NAME)):
        r = run(proposal, *args)
        assert_refusal(r, f"{PROPOSALS}/{NAME}/b-dense/screens/home.html uses F07", changes_rel,
                       '"- **F07** title: what changed and why"', f"--proposal {NAME}")
    assert not (proposal / PROPOSALS / NAME / "index.html").exists()  # nothing written


def test_ids_without_a_changes_file_refuse(proposal: Path) -> None:
    mark(proposal, "a-calm", "home", "P01 · Moved the list")
    assert_refusal(run(proposal, "--proposal", NAME), f"{PROPOSALS}/{NAME}/changes.md (no such file)",
                   "a-calm/screens/home.html uses P01")


def test_a_listed_id_no_screen_uses_warns(proposal: Path) -> None:
    write(proposal / PROPOSALS / NAME / "changes.md", CHANGES)
    mark(proposal, "a-calm", "home", "F01 · One list")
    r = run(proposal, "--proposal", NAME)
    assert r.returncode == 0, r.stderr
    assert f"warning: {PROPOSALS}/{NAME}/changes.md: F02 is listed but no screen of proposal {NAME} uses it" in r.stderr
    assert 'fix: mark the changed element data-guide="F02 · what changed and why"' in r.stderr
    assert "F01 is listed" not in r.stderr
    assert "No screen uses it yet" in read(proposal / PROPOSALS / NAME / "index.html")
    r = run(proposal, "--check", "--proposal", NAME)
    assert r.returncode == 0 and "F02 is listed" in r.stderr


def test_a_duplicate_id_in_changes_md_refuses(proposal: Path) -> None:
    write(proposal / PROPOSALS / NAME / "changes.md", CHANGES + "- **F01** Again: twice\n")
    assert_refusal(run(proposal, "--proposal", NAME), "changes.md:7: change id F01 is listed twice (also line 5)")


@pytest.mark.parametrize("text", ["Start a new booking here", "Q4 revenue at a glance", "AB12 · two letters",
                                  "F01: a colon, not the id mark", "Step F01 · not at the start"])
def test_guide_text_without_a_leading_id_is_not_checked(proposal: Path, text: str) -> None:
    mark(proposal, "a-calm", "home", text)
    r = run(proposal, "--proposal", NAME)  # no changes.md, and none needed
    assert r.returncode == 0, r.stderr
    assert 'class="changes"' not in read(proposal / PROPOSALS / NAME / "index.html")


def test_main_prototype_ids_are_checked_only_with_a_changes_file(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", build=False)
    home = project / DOCS / "prototype/screens/home.html"
    write(home, read(home).replace("<h2>", '<h2 data-guide="C1 · New heading">', 1))
    assert run(project).returncode == 0  # no <docs>/prototype/changes.md: ids are free text
    write(project / DOCS / "prototype/changes.md", "- **C2** Something else: not C1\n")
    r = run(project)
    assert_refusal(r, f"{DOCS}/prototype/screens/home.html uses C1", f"{DOCS}/prototype/changes.md")
    write(project / DOCS / "prototype/changes.md", "- **C1** New heading: says what the page is for\n- **C2** Other\n")
    r = run(project)
    assert r.returncode == 0 and "C2 is listed but no screen of the prototype uses it" in r.stderr, r.stderr


def test_a_variant_has_its_own_shared_files(proposal: Path) -> None:
    shared = proposal / PROPOSALS / NAME / "a-calm/screens/_shared"
    write(shared / "calm.css", "[data-screen] { outline: 2px solid rgb(9, 8, 7); }\n")
    write(shared / "calm.js", 'screen.setAttribute("data-calm", plumb.screen);\n')
    r = run(proposal, "--proposal", NAME)
    assert r.returncode == 0, r.stderr
    for view in ("prototype.html", "app.html", "screens.html"):
        a = read(proposal / PROPOSALS / NAME / "a-calm" / view)
        b = read(proposal / PROPOSALS / NAME / "b-dense" / view)
        assert a.count("rgb(9, 8, 7)") == 1 and a.count('setAttribute("data-calm"') == 1, view
        assert "rgb(9, 8, 7)" not in b and "data-calm" not in b, view
    assert 'data-variant="a-calm"' in read(proposal / PROPOSALS / NAME / "index.html")
    assert "2 screens" in read(proposal / PROPOSALS / NAME / "index.html")  # _shared is not a screen
    write(shared / "calm.js", 'fetch("/x");\n')
    assert_refusal(run(proposal, "--proposal", NAME), "a-calm/screens/_shared/calm.js:1", "fetch(")


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_index_changes_render_in_both_themes(browser, tmp_path: Path, width: int, scheme: str) -> None:
    project = make_project(tmp_path / "p")
    add_variants(project)
    write(project / PROPOSALS / NAME / "changes.md", CHANGES + "- **F03** " + "A very long title " * 12 + ": why\n")
    mark(project, "a-calm", "home", "F01 · One list")
    mark(project, "b-dense", "home", "F02 · Denser rows")
    mark(project, "a-calm", "booking", "F03 · Long")
    assert run(project, "--proposal", NAME).returncode == 0
    ctx, page, errors, requests = _open(browser, project / PROPOSALS / NAME / "index.html", width, scheme)
    try:
        assert page.locator(".changes .change").count() == 3
        assert page.locator("#change-F01 .chip").inner_text() == "F01"
        assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
        chip = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('.chip')); "
                             "return [s.color, s.backgroundColor]; })()")
        assert chip[0] != chip[1]
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


def test_a_variant_page_plumb_did_not_write_is_never_replaced(proposal: Path) -> None:
    page = proposal / PROPOSALS / NAME / "a-calm/app.html"
    mine = "<!doctype html>\n<!-- GENERATED by another-tool. Do not edit. -->\n<p>mine</p>\n"
    write(page, mine)
    r = run(proposal, "--proposal", NAME)
    assert_refusal(r, "a-calm/app.html", "not Plumb's")
    assert read(page) == mine
    assert not (proposal / PROPOSALS / NAME / "index.html").exists()
    c = run(proposal, "--proposal", NAME, "--check")
    assert c.returncode == 1 and "not Plumb's" in c.stdout
