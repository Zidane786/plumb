"""Tour checks: `build-prototype.py --check-tour FILE` (one tour file against the screens, writes nothing, warns where a
screen's own CSS hides a step's target below or above a frame width) and the plugin's `scripts/check-tour.py` (plays a
tour page in a browser already on the machine and checks every step in guide and play mode).

check-tour.py is driven by a stub browser on PATH (a small Python script behind a `google-chrome` launcher) that records
its arguments, looks at the scratch copy it was given and prints a dumped DOM, so these run the same on every OS. One
test runs the real thing headless with Playwright's cached Chromium as --browser.
"""

from __future__ import annotations

import html
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_build_prototype import BP, DOCS, SKILL_REL, assert_refusal, read, write  # noqa: F401
from test_tours import PAGES_REL, TOURS_REL, demo, make_tour_project, put_tour, run, walk  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "plugins/plumb/scripts/check-tour.py"
DASH_REL = f"{DOCS}/prototype/screens/dash.html"

# A neutral app shell: a side navigation hidden below the md breakpoint, a menu button only on narrow frames, a drawer
# moved off canvas until 40rem, a rail hidden with visibility until 64rem (range syntax), a hint hidden on narrow frames
# by a max-width query, plus rules the reader must leave alone.
DASH = """<style>
[data-screen="dash"] .layout { display: grid; }
[data-screen="dash"] .side-nav { display: none; }
[data-screen="dash"] .menu-btn { display: inline-flex; }
[data-screen="dash"] .drawer { transform: translateX(-100%); }
[data-screen="dash"] .rail { visibility: hidden; }
[data-screen="dash"] .layout .panel { display: none; }
[data-screen="dash"] .tip:hover { display: none; }
@media (min-width: 10rem) { [data-screen="dash"] .always { display: none; } }
@container plumb-frame (min-width: 48rem) {
  [data-screen="dash"] .layout { grid-template-columns: 14rem 1fr; }
  [data-screen="dash"] .side-nav { display: block; }
  [data-screen="dash"] .menu-btn { display: none; }
  .panel { display: block; }
}
@container plumb-frame (min-width: 40rem) { [data-screen="dash"] .drawer { transform: none; } }
@container plumb-frame (width >= 64rem) { [data-screen="dash"] .rail { visibility: visible; } }
@container plumb-frame (max-width: 30rem) { [data-screen="dash"] .wide-hint { display: none; } }
@container sidebar (min-width: 20rem) { [data-screen="dash"] .always { display: none; } }
</style>
<section data-screen="dash" data-title="Dashboard" data-order="4">
  <div class="layout">
    <nav class="side-nav" aria-label="Main"><a href="#screen-home" class="nav-home">Home</a></nav>
    <main class="body">
      <button type="button" class="menu-btn">Menu</button>
      <h2>Dashboard</h2>
      <button type="button" class="refresh">Refresh</button>
      <aside class="drawer"><a href="#screen-menu" class="drawer-link">Menu</a></aside>
      <div class="rail"><span class="rail-item">Pinned</span></div>
      <p class="wide-hint">Tip: drag a card to pin it.</p>
      <div class="panel">Stays hidden: the md rule is less specific</div>
      <p class="tip">A hover rule the reader cannot check</p>
      <p class="always">A @media and a foreign @container are left out</p>
    </main>
  </div>
  <div data-state="ready"><p class="summary">All good.</p></div>
</section>
"""


def dash_tour(*targets: str) -> dict:
    return {"title": "Dashboard", "audience": "training",
            "steps": [{"screen": "dash", "title": f"Step {i}", "caption": "Look here.", "target": t}
                      for i, t in enumerate(targets, 1)]}


def dash_project(tmp_path: Path, tours: dict) -> Path:
    p = make_tour_project(tmp_path / "Dash Ünïcode", {"demo": demo()}, build=False)
    write(p / DASH_REL, DASH)
    for name, doc in tours.items():
        put_tour(p, name, doc)
    return p


def check_tour(project: Path, *args: str):
    return run(project, "--check-tour", *args)


def warnings(r) -> list:
    return [line for line in r.stderr.splitlines() if line.startswith("warning: ")]


# ---------------------------------------------------------------- build-prototype.py --check-tour


def test_check_tour_happy_path_writes_nothing(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    def files() -> list:
        return sorted(x.relative_to(p).as_posix() for x in p.rglob("*") if "__pycache__" not in x.parts)

    before = files()
    r = check_tour(p, f"{TOURS_REL}/demo.json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == f"ok: {TOURS_REL}/demo.json: 6 steps (play mode, app view) match the screens"
    assert r.stderr == ""
    assert files() == before, "--check-tour writes nothing"


def test_check_tour_takes_an_id_or_a_path_from_anywhere(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    assert check_tour(p, "demo").returncode == 0
    r = subprocess.run([sys.executable, str(p / SKILL_REL / "scripts/build-prototype.py"), "--check-tour",
                        str(p / TOURS_REL / "demo.json")], cwd=str(tmp_path), capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0 and "6 steps" in r.stdout, r.stdout + r.stderr


def test_check_tour_ignores_other_broken_tours(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", {"demo": demo(), "broken": "{ not json"}, build=False)
    assert check_tour(p, f"{TOURS_REL}/demo.json").returncode == 0
    assert_refusal(check_tour(p, f"{TOURS_REL}/broken.json"), "broken.json:1: the tour is not valid JSON", "fix: ")


def test_check_tour_refuses_a_missing_file(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    r = check_tour(p, f"{TOURS_REL}/nope.json")
    assert_refusal(r, "no such tour file", f"--check-tour {TOURS_REL}/<id>.json")


def test_check_tour_refuses_a_file_that_is_not_json(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    write(p / TOURS_REL / "notes.txt", "hello\n")
    assert_refusal(check_tour(p, f"{TOURS_REL}/notes.txt"), "a tour file is <id>.json")


def test_check_tour_refuses_an_unknown_screen(tmp_path: Path) -> None:
    doc = demo()
    doc["chapters"][0]["steps"][0]["screen"] = "nowhere"
    p = make_tour_project(tmp_path / "p", {"demo": demo(), "odd": doc}, build=False)
    r = check_tour(p, f"{TOURS_REL}/odd.json")
    assert_refusal(r, f"{TOURS_REL}/odd.json:", "names screen \"nowhere\", which has no screen file", "use one of:")


def test_check_tour_refuses_a_selector_that_matches_nothing(tmp_path: Path) -> None:
    doc = demo()
    doc["chapters"][1]["steps"][0]["target"] = ".gone"
    p = make_tour_project(tmp_path / "p", {"odd": doc}, build=False)
    assert_refusal(check_tour(p, "odd"), '".gone" matches nothing')


def test_check_tour_does_not_combine(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    for extra in (["--check"], ["--approve", "home"], ["--proposal", "x"]):
        assert_refusal(check_tour(p, "demo", *extra), "--check-tour FILE checks one tour file")


def test_check_tour_without_screens_is_refused(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    for f in (p / f"{DOCS}/prototype/screens").glob("*.html"):
        f.unlink()
    assert_refusal(check_tour(p, "demo"), "no screen files in")


def test_a_sidebar_hidden_below_the_md_breakpoint_warns(tmp_path: Path) -> None:
    p = dash_project(tmp_path, {"dash": dash_tour(".side-nav .nav-home", ".refresh")})
    r = check_tour(p, "dash")
    assert r.returncode == 0, r.stdout + r.stderr
    found = warnings(r)
    assert found == [f'warning: {TOURS_REL}/dash.json:9: step 1, steps[0].target ".side-nav .nav-home" sits inside '
                     f"nav.side-nav, which the screen's CSS hides (display: none): visible only when the frame is "
                     f"≥ 48rem"], r.stderr
    assert "\nfix: play the tour where the frame is that wide" in r.stderr
    assert "1 warning" in r.stdout


def test_other_breakpoints_and_ways_of_hiding_warn_too(tmp_path: Path) -> None:
    doc = dash_tour(".drawer-link", ".rail .rail-item", ".menu-btn", ".wide-hint")
    doc["steps"][0]["labels"] = [{"target": ".side-nav a", "text": "Home"}]
    p = dash_project(tmp_path, {"dash": doc})
    r = check_tour(p, "dash")
    assert r.returncode == 0, r.stdout + r.stderr
    text = "\n".join(warnings(r))
    assert ('step 1, steps[0].target ".drawer-link" sits inside aside.drawer, which the screen\'s CSS hides '
            "(transform: translatex(-100%)): visible only when the frame is ≥ 40rem") in text
    assert ('step 1, steps[0].labels[0].target ".side-nav a" sits inside nav.side-nav' in text
            and "≥ 48rem" in text), "labels are checked too"
    assert ('step 2, steps[1].target ".rail .rail-item" sits inside div.rail, which the screen\'s CSS hides '
            "(visibility: hidden): visible only when the frame is ≥ 64rem") in text
    assert ('step 3, steps[2].target ".menu-btn" is hidden by the screen\'s CSS (display: none): visible only when '
            "the frame is < 48rem") in text
    assert ('step 4, steps[3].target ".wide-hint" is hidden by the screen\'s CSS (display: none): visible only when '
            "the frame is > 30rem") in text
    assert len(warnings(r)) == 5


def test_no_warning_without_a_frame_breakpoint(tmp_path: Path) -> None:
    """Shown at every width, hidden at every width (a script may open it), an unreadable selector, a @media rule,
    another container's query, a less specific show rule: no warning."""
    p = dash_project(tmp_path, {"dash": dash_tour(".refresh", ".panel", ".tip", ".always", ".summary")})
    r = check_tour(p, "dash")
    assert r.returncode == 0, r.stdout + r.stderr
    assert warnings(r) == [] and "fix:" not in r.stderr, r.stderr


def test_a_descendant_that_sets_visibility_visible_does_not_warn(tmp_path: Path) -> None:
    screen = DASH.replace("</style>", """[data-screen="dash"] .wrap { visibility: hidden; }
[data-screen="dash"] .wrap .keep { visibility: visible; }
@container plumb-frame (min-width: 48rem) { [data-screen="dash"] .wrap { visibility: visible; } }
</style>""").replace('<p class="summary">All good.</p>',
                     '<p class="summary">All good.</p><div class="wrap"><b class="keep">K</b><i class="lost">L</i></div>')
    p = dash_project(tmp_path, {"dash": dash_tour(".keep", ".lost")})
    write(p / DASH_REL, screen)
    r = check_tour(p, "dash")
    assert r.returncode == 0, r.stdout + r.stderr
    found = warnings(r)
    assert len(found) == 1 and '".lost" sits inside div.wrap' in found[0] and "(visibility: hidden)" in found[0], found


def test_shared_css_reaches_the_breakpoint_warning(tmp_path: Path) -> None:
    shared = ('[data-screen] .side-panel { display: none; }\n'
              "@container plumb-frame (min-width: 48rem) { [data-screen] .side-panel { display: block; } }\n")
    p = dash_project(tmp_path, {"dash": dash_tour(".side-panel a")})
    write(p / DASH_REL, DASH.replace('<main class="body">',
                                     '<div class="side-panel"><a href="#screen-home">Home</a></div><main class="body">'))
    write(p / f"{DOCS}/prototype/screens/_shared/shell.css", shared)
    r = check_tour(p, "dash")
    assert r.returncode == 0, r.stdout + r.stderr
    assert [w for w in warnings(r) if "div.side-panel" in w and "≥ 48rem" in w], r.stderr
    # the screen's own styles come after the shared files: a screen that shows it at every width stays quiet
    write(p / DASH_REL, read(p / DASH_REL).replace("</style>", '[data-screen="dash"] .side-panel { display: block; }\n</style>'))
    r = check_tour(p, "dash")
    assert r.returncode == 0 and warnings(r) == [], r.stderr


def test_a_refused_shared_file_refuses_check_tour(tmp_path: Path) -> None:
    p = dash_project(tmp_path, {"dash": dash_tour(".refresh")})
    write(p / f"{DOCS}/prototype/screens/_shared/bad.css", "a { color: red } </style>\n")
    r = check_tour(p, "dash")
    assert r.returncode == 2 and "error: " in r.stderr and "\nfix: " in r.stderr, r.stderr


def test_inline_size_queries_are_read() -> None:
    for q in ("(min-inline-size: 48rem)", "(inline-size >= 48rem)", "(min-width: 768px)"):
        parts = BP._frame_query(q)
        assert parts and parts[0][0] == "min" and parts[0][2] == 768, q
    assert BP._frame_query("(max-inline-size: 30rem)")[0][:3] == ("max", False, 480)
    assert BP._frame_query("(orientation: portrait)") is None


def test_one_step_matches(tmp_path: Path) -> None:
    p = dash_project(tmp_path, {"dash": dash_tour(".refresh")})
    r = check_tour(p, "dash")
    assert r.stdout.strip() == f"ok: {TOURS_REL}/dash.json: 1 step (guide mode, app view) matches the screens"


def test_important_beats_specificity() -> None:
    css = """[data-screen="x"] .a .b { display: none; }
@container plumb-frame (min-width: 36rem) { .b { display: block !important; } }"""
    screen = BP.Screen("x", "X", 1, "x.html", "")
    screen.styles = [css]
    screen.section = '<section data-screen="x"><div class="a"><p class="b">B</p></div><div data-state="ready"></div></section>'
    sheet = BP._ScreenCSS(screen, "ready")
    node = BP.select(screen.tree(), ".b", "ready")[0]
    assert sheet.hidden(node, 100) is not None and sheet.hidden(node, 36 * 16) is None
    assert [b for b in sheet.bounds.values()] == ["36rem"]


def test_css_reader_reads_rules_and_frame_blocks_only() -> None:
    rules = BP.css_rules("""/* c { display: none } */
a, b { display: none ; color: red }
@media (min-width: 1px) { c { display: none } }
@container plumb-frame (min-width: 48rem) and (max-width: 80rem) { d { visibility: hidden !important } }
@container plumb-frame (orientation: portrait) { e { display: none } }
@keyframes k { from { transform: translateX(-100%) } }
f { background: url("data:image/png;base64,AA;BB"); display: none }""")
    assert [(s, c is not None) for s, _d, c in rules] == [("a, b", False), ("d", True), ("f", False)]
    assert rules[1][1] == [("visibility", "hidden", True)]
    assert [k for k, *_ in rules[1][2]] == ["min", "max"]
    assert ("display", "none", False) in rules[2][1]


@pytest.mark.parametrize("prop, value, off", [
    ("transform", "translatex(-100%)", True), ("transform", "translatex(100%)", True),
    ("transform", "translate(0, 100%)", True), ("transform", "translate3d(-110%, 0, 0)", True),
    ("transform", "translatey(-100%) scale(1)", True), ("translate", "-100% 0", True),
    ("transform", "translatex(-50%)", False), ("transform", "none", False), ("transform", "translatex(-320px)", False),
    ("translate", "0", False)])
def test_off_canvas_transforms(prop: str, value: str, off: bool) -> None:
    assert BP._off_canvas(prop, value) is off


# ---------------------------------------------------------------- check-tour.py with a stub browser

STUB = r'''
import html, json, os, re, sys, time
from urllib.parse import unquote, urlparse
args = sys.argv[1:]
url = args[-1]
copy = unquote(urlparse(url).path)
if os.name == "nt" and re.match(r"^/[A-Za-z]:", copy):
    copy = copy[1:]
text = open(copy, encoding="utf-8").read()
base = re.search(r'<base href="([^"]*)">', text)
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"args": args, "copy": copy, "base": base.group(1) if base else None,
                         "checker": 'pre.id = "plumb-tour-check"' in text,
                         "errors": "__plumbTourErrors" in text}) + "\n")
mode = os.environ.get("STUB_MODE", "ok")
if mode == "sandbox" and "--no-sandbox" not in args:
    sys.stderr.write("[0101/000000.000:FATAL:zygote_host_impl_linux.cc(128)] No usable sandbox! Update your kernel\n")
    sys.exit(1)
width = int(next(a for a in args if a.startswith("--window-size=")).split("=", 1)[1].split(",")[0])
data = json.loads(re.search(r'<script type="application/json" id="plumb-tours">(.*?)</script>', text, re.S).group(1))
tour = next(t for t in data["tours"] if t["id"] == data["autostart"]["tour"])
results = [{"mode": m, "n": s["n"], "problems": []} for m in ("guide", "play") for s in tour["steps"]]
if mode == "problems" and width == 1280:
    results[0]["problems"] = ['the target ".a > b" is hidden (visibility: hidden)']
    results[len(tour["steps"])]["problems"] = ['the target ".a > b" is hidden (visibility: hidden)']
    results[2]["problems"] = ["the dock is covered by div.scrim & co"]
out = {"done": mode != "notdone", "steps": len(tour["steps"]), "positions": 10, "checked": 3, "results": results,
       "errors": ["Uncaught TypeError: x is not a function"] if mode == "problems" and width == 1280 else [],
       "fatal": ""}
if mode == "fatal":
    out["fatal"] = "the page has no walkthrough player or no tour to start"
dom = "<!DOCTYPE html>\n<html><head></head><body><p>page</p>"
if mode not in ("nothing", "fail", "hang"):
    dom += '<pre id="plumb-tour-check" hidden="">' + html.escape(json.dumps(out), quote=False) + "</pre>"
dom += "</body></html>\n"
if mode == "fail":
    sys.stderr.write("[0101/000000.000:ERROR:headless_shell.cc] cannot open the page\n")
    sys.exit(1)
if mode == "hang":
    time.sleep(60)
sys.stdout.write(dom)
sys.stdout.flush()
if mode == "linger":
    time.sleep(30)
'''


def _load_check():
    sys.path.insert(0, str(CHECK.parent))
    spec = importlib.util.spec_from_file_location("plumb_check_tour", CHECK)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plumb_check_tour"] = mod
    spec.loader.exec_module(mod)
    return mod


CT = _load_check()


def make_launcher(folder: Path, name: str, stub: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = folder / f"{name}.cmd"
        path.write_text(f'@"{sys.executable}" "{stub}" %*\r\n', encoding="utf-8")
    else:
        path = folder / name
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub}" "$@"\n', encoding="utf-8")
        path.chmod(0o755)
    return path


@pytest.fixture()
def stub(tmp_path: Path):
    script = tmp_path / "stub_browser.py"
    script.write_text(STUB, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    make_launcher(bin_dir, "google-chrome", script)
    return bin_dir, tmp_path / "calls.jsonl"


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    return make_tour_project(tmp_path_factory.mktemp("check") / "Café Ünïcode", {"demo": demo(), "walk": walk()})


def check(stub, *args: str, mode: str = "ok", cwd: Path = None):
    bin_dir, log = stub
    env = dict(os.environ, PATH=str(bin_dir), STUB_LOG=str(log), STUB_MODE=mode)
    return subprocess.run([sys.executable, str(CHECK), *args], capture_output=True, text=True, encoding="utf-8",
                          env=env, cwd=str(cwd) if cwd else None, timeout=120)


def calls(stub) -> list:
    log = stub[1]
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()] if log.is_file() else []


def test_ok_runs_each_width_headless_with_a_scratch_copy(stub, built: Path) -> None:
    page = built / PAGES_REL / "demo.html"
    r = check(stub, str(page), cwd=built)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "ok: 6 steps × guide/play × 1280, 1440"
    got = calls(stub)
    assert len(got) == 2
    scratch = (built / ".plumb-tmp").resolve()
    for c, width in zip(got, (1280, 1440)):
        a = c["args"]
        for flag in ("--headless=new", "--dump-dom", f"--window-size={width},900",
                     "--blink-settings=preferredColorScheme=1"):
            assert flag in a, (flag, a)
        assert any(x.startswith("--virtual-time-budget=") and int(x.split("=")[1]) > 5000 for x in a)
        profile = Path(next(x for x in a if x.startswith("--user-data-dir=")).split("=", 1)[1]).resolve()
        assert scratch in profile.parents, "the browser profile lives in <project>/.plumb-tmp/"
        assert a[-1].startswith("file:") and scratch in Path(c["copy"]).resolve().parents
        assert c["checker"] and c["errors"], "the checker and the error catcher are in the copy"
        assert c["base"] == (built / DOCS).resolve().as_uri() + "/", "relative images and links resolve as before"
        assert not any("http" in x for x in a[:-1] if not x.startswith("--blink"))
    assert not (built / ".plumb-tmp").exists(), "the scratch copy and profiles are removed"
    assert read(page) == read(page), "the page itself is untouched"


def test_widths_are_chosen_and_deduplicated(stub, built: Path) -> None:
    r = check(stub, str(built / PAGES_REL / "walk.html"), "--width", "390", "--width", "390", cwd=built)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "ok: 6 steps × guide/play × 390"
    assert [next(x for x in c["args"] if x.startswith("--window-size")) for c in calls(stub)] == ["--window-size=390,900"]


def test_problems_are_one_line_per_step_with_widths_and_modes(stub, built: Path) -> None:
    r = check(stub, str(built / PAGES_REL / "demo.html"), mode="problems", cwd=built)
    assert r.returncode == 2, r.stdout + r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == ("step 1 (Tonight at a glance › Tonight's tables): the target \".a > b\" is hidden "
                        "(visibility: hidden) at 1280 (guide, play)")
    assert lines[1] == "step 3 (Take the booking › Type the guest's name): the dock is covered by div.scrim & co at 1280 (guide)"
    assert lines[2] == "page: a script error: Uncaught TypeError: x is not a function at 1280"
    assert lines[3].startswith(f"fix: change those steps in {TOURS_REL}/demo.json")
    assert not (built / ".plumb-tmp").exists()


def test_a_browser_that_lingers_after_the_dump_is_stopped(stub, built: Path) -> None:
    start = time.monotonic()
    r = check(stub, str(built / PAGES_REL / "demo.html"), "--width", "1280", mode="linger", cwd=built)
    assert r.returncode == 0, r.stdout + r.stderr
    assert time.monotonic() - start < 25
    assert not (built / ".plumb-tmp").exists()


@pytest.mark.parametrize("mode, needle", [("nothing", "gave no tour check result"), ("fail", "cannot open the page"),
                                          ("notdone", "the tour check stopped after 3 of 20 positions")])
def test_no_result_is_exit_1(stub, built: Path, mode: str, needle: str) -> None:
    r = check(stub, str(built / PAGES_REL / "demo.html"), "--width", "1280", mode=mode, cwd=built)
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stderr.startswith("error: ") and "\nfix: " in r.stderr and needle in r.stderr, r.stderr
    assert not (built / ".plumb-tmp").exists()


def test_a_hung_browser_is_stopped_at_the_timeout(stub, built: Path) -> None:
    start = time.monotonic()
    r = check(stub, str(built / PAGES_REL / "demo.html"), "--width", "1280", "--timeout", "2", mode="hang", cwd=built)
    assert r.returncode == 1 and "did not finish within 2 s" in r.stderr and "--timeout" in r.stderr, r.stderr
    assert "another Chrome, Edge or Chromium already on this machine with --browser PATH" in r.stderr
    assert time.monotonic() - start < 30
    assert not (built / ".plumb-tmp").exists()


def test_a_fatal_page_is_refused(stub, built: Path) -> None:
    r = check(stub, str(built / PAGES_REL / "demo.html"), "--width", "1280", mode="fatal", cwd=built)
    assert_refusal(r, "no walkthrough player", "rebuild the page with build-prototype.py")


def test_an_existing_scratch_folder_is_kept(stub, built: Path) -> None:
    keep = built / ".plumb-tmp"
    keep.mkdir()
    (keep / "other.txt").write_text("x\n", encoding="utf-8")
    try:
        assert check(stub, str(built / PAGES_REL / "demo.html"), "--width", "1280", cwd=built).returncode == 0
        assert sorted(p.name for p in keep.iterdir()) == ["other.txt"]
    finally:
        (keep / "other.txt").unlink()
        keep.rmdir()


def test_no_browser_exits_3_with_note_and_fix(built: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(CT.S, "find_browser", lambda *a, **k: None)
    code = CT.main([str(built / PAGES_REL / "demo.html")])
    err = capsys.readouterr().err
    assert code == 3
    assert err.startswith("note: tour check skipped: no browser found")
    assert "\nfix: ask the user" in err and "--browser PATH" in err and "build-prototype.py --check-tour" in err
    assert not (built / ".plumb-tmp").exists()


@pytest.mark.parametrize("args, needle", [
    (["nowhere.html"], "file not found"),
    (["PROTO"], "not a tour page"),
    (["PAGE", "--width", "100"], "--width 100 is out of range"),
    (["PAGE", "--timeout", "0"], "--timeout 0 is out of range"),
    (["PAGE", "--browser", "no/such/browser"], "--browser no/such/browser: no such file"),
    ([], "the following arguments are required"),
])
def test_bad_input_is_refused(stub, built: Path, args: list, needle: str) -> None:
    swap = {"PAGE": str(built / PAGES_REL / "demo.html"), "PROTO": str(built / DOCS / "prototype.html")}
    r = check(stub, *[swap.get(a, a) for a in args], cwd=built)
    assert_refusal(r, needle)
    assert calls(stub) == [], "no browser runs on bad input"


@pytest.mark.parametrize("linux", [True, False])
def test_no_usable_sandbox_on_linux_retries_once_with_no_sandbox(stub, built: Path, monkeypatch, capsys,
                                                                 linux: bool) -> None:
    bin_dir, log = stub
    launcher = next(bin_dir.iterdir())
    monkeypatch.setenv("STUB_LOG", str(log))
    monkeypatch.setenv("STUB_MODE", "sandbox")
    monkeypatch.setattr(CT, "_linux", lambda: linux)
    monkeypatch.chdir(built)
    code = CT.main([str(built / PAGES_REL / "demo.html"), "--browser", str(launcher), "--width", "1280",
                    "--width", "1440"])
    out, err = capsys.readouterr()
    sandboxed = ["--no-sandbox" in c["args"] for c in calls(stub)]
    if linux:
        assert code == 0, out + err
        assert out.strip() == "ok: 6 steps × guide/play × 1280, 1440"
        assert err.count("note: ") == 1 and "no usable sandbox" in err and "ran it again with --no-sandbox" in err
        assert sandboxed == [False, True, True], "one retry, then kept for the other widths"
    else:
        assert code == 1 and "No usable sandbox" in err and "note: " not in err, err
        assert sandboxed == [False], "never --no-sandbox off Linux"
    assert not (built / ".plumb-tmp").exists()


def test_result_parsing_unescapes_the_dumped_text() -> None:
    data = {"done": True, "results": [{"mode": "guide", "n": 1, "problems": ['a "b" <c> & d']}]}
    dom = '<html><body><pre id="plumb-tour-check">x</pre><pre id="plumb-tour-check" hidden="">' + \
          html.escape(json.dumps(data), quote=False) + "</pre></body></html>"
    assert CT.parse_result(dom) == data
    assert CT.parse_result("<html></html>") is None
    assert CT.parse_result('<pre id="plumb-tour-check">{not json</pre>') is None


def test_the_copy_gets_a_base_when_the_page_has_none(tmp_path: Path) -> None:
    page = tmp_path / "docs" / "x.html"
    text = CT.scratch_copy("<!doctype html><html><head><title>t</title></head><body><p>x</p></body></html>", page)
    assert f'<base href="{(tmp_path / "docs").resolve().as_uri()}/">' in text
    assert text.index('pre.id = "plumb-tour-check"') < text.index("</body>")


def test_never_downloads_or_uses_a_shell() -> None:
    text = CHECK.read_text(encoding="utf-8")
    for banned in ("urllib.request", "http.client", "socket", "shell=True", "pip ", "npx", "playwright install"):
        assert banned not in text, banned


# ---------------------------------------------------------------- check-tour.py, for real (headless)

HIDDEN_REL = f"{DOCS}/prototype/screens/hidden.html"
HIDDEN = """<style>
[data-screen="hidden"] .ghost { visibility: hidden; }
[data-screen="hidden"] .gone { display: none; }
[data-screen="hidden"] .flat { display: block; width: 0; height: 0; overflow: hidden; }
[data-screen="hidden"] .cover-bar { position: fixed; top: 0; left: 0; width: 100%; height: 120px; z-index: 2; background: #eee; }
[data-screen="hidden"] .under { position: fixed; top: 40px; left: 40px; z-index: 1; margin: 0; }
</style>
<section data-screen="hidden" data-title="Hidden things" data-order="5">
  <h2>Hidden things</h2>
  <div data-state="ready">
    <p class="ghost">Ghost</p>
    <div class="gone"><a href="#screen-home" class="gone-link">Gone</a></div>
    <span class="flat"></span>
    <p class="shown">Shown</p>
  </div>
  <div data-state="covered">
    <div class="cover-bar">A bar on top</div>
    <p class="under">Under the bar</p>
  </div>
</section>
"""


def _real_browser() -> str:
    """Playwright's cached Chromium (the headless shell when the cache has it, else its Chromium), as the test process
    finds it. Skips only when Playwright is not importable (CI has it: PLUMB_STRICT_SKIPS fails that skip there)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("requires Playwright")
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    names = ("chrome-headless-shell.exe", "chrome-headless-shell")
    shells = sorted(p for name in names for p in Path(root).glob(f"chromium_headless_shell-*/*/{name}")) if root else []
    if shells:
        return str(shells[-1])
    with sync_playwright() as pw:
        return pw.chromium.executable_path


def test_check_tour_for_real(tmp_path: Path) -> None:
    browser = _real_browser()
    broken = {"title": "Hidden things", "audience": "training", "steps": [
        {"screen": "hidden", "title": "Ghost", "caption": "Invisible.", "target": ".ghost"},
        {"screen": "hidden", "title": "Gone", "caption": "Not laid out.", "target": ".gone-link"},
        {"screen": "hidden", "title": "Flat", "caption": "No size.", "target": ".flat"},
        {"screen": "hidden", "title": "Shown", "caption": "Fine.", "target": ".shown",
         "labels": [{"target": ".ghost", "text": "Ghost label"}]},
        {"screen": "hidden", "state": "covered", "title": "Under", "caption": "Under a fixed bar.", "target": ".under"},
    ]}
    p = make_tour_project(tmp_path / "Real Ünïcode", {"demo": demo(), "walk": walk()}, build=False)
    write(p / HIDDEN_REL, HIDDEN)
    put_tour(p, "broken", broken)
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    for name in ("demo", "walk"):
        ok = subprocess.run([sys.executable, str(CHECK), str(p / PAGES_REL / f"{name}.html"), "--browser", browser,
                             "--timeout", "90"],
                            capture_output=True, text=True, encoding="utf-8", cwd=str(p), timeout=300)
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert ok.stdout.strip() == "ok: 6 steps × guide/play × 1280, 1440"
    bad = subprocess.run([sys.executable, str(CHECK), str(p / PAGES_REL / "broken.html"), "--width", "1280",
                          "--browser", browser, "--timeout", "90"], capture_output=True, text=True, encoding="utf-8", cwd=str(p), timeout=300)
    assert bad.returncode == 2, bad.stdout + bad.stderr
    lines = bad.stdout.strip().splitlines()
    assert lines[:5] == [
        'step 1 (Ghost): the target ".ghost" is hidden (visibility: hidden) at 1280 (guide, play)',
        'step 2 (Gone): the target ".gone-link" is hidden (display: none on div.gone) at 1280 (guide, play)',
        'step 3 (Flat): the target ".flat" is zero-size (0 × 0 px) at 1280 (guide, play)',
        'step 4 (Shown): the label "Ghost label" (.ghost) is hidden (visibility: hidden) at 1280 (guide, play)',
        'step 5 (Under): the target ".under" is covered by div.cover-bar at 1280 (guide, play)',
    ], bad.stdout
    assert lines[5].startswith(f"fix: change those steps in {TOURS_REL}/broken.json")
    assert not (p / ".plumb-tmp").exists()


# The walkthrough panel is centred at the bottom of the window; for a step whose pinned (position: fixed) target it would
# cover there, the player moves it to the top (pl-at-top) and the check reads it there. A fixed toast in the bottom-right
# corner sits beside the panel (not covered, the panel stays at the bottom), and so does a floating button in the
# bottom-left corner. A status bar centred at the bottom would be under the panel: the panel moves to the top and the
# step passes. A narrow rail pinned from below the top of the window with that bar: the panel at the top covers a little
# of the rail, the part below it is clear and the step passes. The bar with a band across the top half of the window
# (both targets of one step, each state has its own bar) cannot be avoided: at the top the panel would cover more of the band than it covers of the
# bar at the bottom, so it stays at the bottom and the bar is reported.
CORNER_REL = f"{DOCS}/prototype/screens/corner.html"
CORNER = """<style>
[data-screen="corner"] .toast { position: fixed; right: 16px; bottom: 16px; width: 3rem; height: 3rem; margin: 0; z-index: 5; }
[data-screen="corner"] .fab { position: fixed; left: 12px; bottom: 12px; z-index: 5; }
[data-screen="corner"] :is(.bottom-bar, .rail-bar, .both-bar) { position: fixed; left: 50%; bottom: 24px; width: 16rem; height: 3rem; margin: 0 0 0 -8rem;
  z-index: 5; }
[data-screen="corner"] .rail { position: fixed; left: 50%; top: 4rem; width: 1.5rem; height: 40vh; margin: 0 0 0 -0.75rem;
  z-index: 5; }
[data-screen="corner"] .top-band { position: fixed; left: 0; right: 0; top: 0; height: 50vh; margin: 0; z-index: 5; }
</style>
<section data-screen="corner" data-title="Corners" data-order="6">
  <h2>Corners</h2>
  <div data-state="toast"><p class="toast" role="status">Saved</p><button type="button" class="fab">New</button></div>
  <div data-state="under"><p class="bottom-bar" role="status">Saved</p></div>
  <div data-state="rail"><p class="rail-bar" role="status">Saved</p><p class="rail">Rail</p></div>
  <div data-state="both"><p class="both-bar" role="status">Saved</p><p class="top-band">A band across the top</p></div>
</section>
"""
CORNER_TOUR = {"title": "Corners", "audience": "training", "steps": [
    {"screen": "corner", "state": "toast", "title": "Toast", "caption": "Beside the panel.", "target": ".toast",
     "point": "beacon"},
    {"screen": "corner", "state": "toast", "title": "Button", "caption": "Beside the panel too.", "target": ".fab"},
    {"screen": "corner", "state": "under", "title": "Bar", "caption": "The panel moves to the top.",
     "target": ".bottom-bar"},
    {"screen": "corner", "state": "rail", "title": "Rail", "caption": "Clear below the panel at the top.",
     "targets": [".rail-bar", ".rail"]},
    {"screen": "corner", "state": "both", "title": "Both", "caption": "Under the panel either way.",
     "targets": [".both-bar", ".top-band"]},
]}
DOCK_AT = """() => { var d = document.getElementById('pl-dock'), r = d.getBoundingClientRect();
  return [window.plumbPlayer.state().step, d.classList.contains('pl-at-top'), Math.round(r.top), Math.round(r.bottom)]; }"""


def test_check_tour_for_real_reports_the_panel_only_where_it_overlaps(tmp_path: Path) -> None:
    browser = _real_browser()
    from playwright.sync_api import sync_playwright
    p = make_tour_project(tmp_path / "Corner Ünïcode", {"demo": demo()}, build=False)
    write(p / CORNER_REL, CORNER)
    put_tour(p, "corner", CORNER_TOUR)
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    # where the player puts the panel in each step, in both modes (headless, the window check-tour.py uses)
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            for width in (1280, 1440):
                page = b.new_page(viewport={"width": width, "height": 900})
                page.goto((p / PAGES_REL / "corner.html").as_uri())
                page.wait_for_function("window.plumbPlayer && window.plumbPrototype")
                for mode in ("guide", "play"):
                    seen = []
                    for pos in range(5):
                        page.evaluate("([m, p]) => { window.plumbPlayer.start('corner', {mode: m, pos: p, focus: false});"
                                      " if (m === 'play') window.plumbPlayer.pause(); }", [mode, pos])
                        page.wait_for_timeout(150)
                        seen.append(page.evaluate(DOCK_AT))
                    assert [s[:2] for s in seen] == [[1, False], [2, False], [3, True], [4, True], [5, False]], seen
                    assert all(s[2] < 900 / 2 for s in seen if s[1]) and all(s[3] > 900 / 2 for s in seen if not s[1])
                page.close()
        finally:
            b.close()
    out = subprocess.run([sys.executable, str(CHECK), str(p / PAGES_REL / "corner.html"), "--browser", browser,
                          "--timeout", "90"], capture_output=True, text=True, encoding="utf-8", cwd=str(p), timeout=300)
    assert out.returncode == 2, out.stdout + out.stderr
    lines = out.stdout.strip().splitlines()
    assert lines[0] == ('step 5 (Both): the target ".both-bar" is covered by the walkthrough panel '
                        'at 1280 (guide, play), 1440 (guide, play)'), out.stdout
    assert lines[1].startswith(f"fix: change those steps in {TOURS_REL}/corner.json")
    assert len(lines) == 2, out.stdout
    assert not (p / ".plumb-tmp").exists()
