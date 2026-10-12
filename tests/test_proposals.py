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
    assert sorted(built) == ["a-calm/prototype.html", "a-calm/screens.html", "b-dense/prototype.html",
                             "b-dense/screens.html", "index.html"]
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
    index = read(built["index.html"])
    for text in ("Calm list", "One list of tonight", "Fast for regulars", "Busy on a phone", "B dense"):
        assert text in index, text
    for href in ("a-calm/prototype.html", "a-calm/screens.html", "b-dense/prototype.html", "b-dense/screens.html"):
        assert f'href="{href}"' in index, href
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
    assert "a-calm" not in r.stdout and "--proposal billing" in r.stdout
    assert {k: p.read_bytes() for k, p in pages(proposal).items()} == before  # --check writes nothing


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
    assert_refusal(run(proposal, "--proposal", "../x"), "--proposal")
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
        pytest.skip(f"requires symlinks ({exc})")


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
    assert not any(f.endswith(("index.html", "/prototype.html", "/screens.html")) for f in files), files
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
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


@pytest.mark.parametrize("view", ["prototype.html", "screens.html"])
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
            page.click("#theme-toggle")
            assert page.evaluate("getComputedStyle(document.body).backgroundColor") != before
            assert errors == [] and requests == [], (variant, errors, requests)
        finally:
            ctx.close()
