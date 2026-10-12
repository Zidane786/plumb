"""Walkthroughs: tour files (docs/design/prototype/tours/<flow>.json), their validation against the screen files, the
walkthrough player built into every prototype (guide mode and play mode), the per-screen guide panel, and the
standalone tour pages (docs/design/tours/<tour>.html).

Static checks run everywhere. The browser checks drive the pages headless and skip only when Playwright is not
importable.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from test_build_prototype import (  # noqa: F401 - shared helpers of the prototype suite
    BP,
    BT,
    DOCS,
    FIXTURE,
    NETWORK,
    P,
    PROTO_REL,
    SKILL_REL,
    TOKENS_REL,
    assert_refusal,
    build_tokens,
    make_project,
    read,
    run,
    write,
)

TOURS_REL = f"{DOCS}/prototype/tours"
PAGES_REL = f"{DOCS}/tours"
DEMO_SRC = FIXTURE / "tours/demo.json"
DEMO_PAGE = f"{PAGES_REL}/demo.html"
HOME_REL = f"{DOCS}/prototype/screens/home.html"
REPO_TEMPLATES = Path(__file__).resolve().parents[1] / "plugins/plumb/assets/skill/templates"
BOOKING_REL = f"{DOCS}/prototype/screens/booking.html"
PURPOSE = "See tonight's bookings at a glance and start a new one."
GUIDE_ITEM = "Start a new booking from the link at the top"


def demo() -> dict:
    return json.loads(read(DEMO_SRC))


def training() -> dict:
    return {
        "title": "Training: the booking form",
        "audience": "training",
        "steps": [
            {"screen": "booking", "title": "The form", "caption": "Everything the host fills in.", "target": ".booking-form"},
            {"screen": "booking", "title": "The name", "caption": "Type the guest's name here.", "target": "[data-test=guest]",
             "point": "ring", "action": {"type": "Ada"}},
            {"screen": "booking", "title": "Save", "caption": "Press save.", "target": "[data-test=save]", "point": "spotlight"},
        ],
    }


def put_tour(project: Path, name: str, doc) -> Path:
    path = project / TOURS_REL / f"{name}.json"
    write(path, doc if isinstance(doc, str) else json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return path


def make_tour_project(dest: Path, tours: dict = None, build: bool = True) -> Path:
    p = make_project(dest, build=False)
    home = p / HOME_REL
    write(home, read(home).replace('data-order="1">', f'data-order="1" data-purpose="{PURPOSE}">', 1)
          .replace('data-test="new-booking"', f'data-test="new-booking" data-guide="{GUIDE_ITEM}"', 1))
    for name, doc in (tours if tours is not None else {"demo": demo()}).items():
        put_tour(p, name, doc)
    if build:
        r = run(p)
        assert r.returncode == 0, r.stdout + r.stderr
    return p


def build_in_process(project: Path, *args: str, capsys=None):
    """build-prototype.py's main() in this process (fast for the many refusal paths); returns (code, stdout, stderr)."""
    code = BP.main(["--root", str(project / SKILL_REL), *args])
    out, err = capsys.readouterr() if capsys else ("", "")
    return code, out, err


def tours_json(page: str) -> dict:
    m = re.search(r'<script type="application/json" id="plumb-tours">(.*?)</script>', page, re.S)
    assert m, "no plumb-tours data block"
    return json.loads(m.group(1))


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return make_tour_project(tmp_path / "Café Ünïcode")


# ---------------------------------------------------------------- the standalone pages and the embedded player


def test_build_writes_a_generated_self_contained_page_per_tour(project: Path) -> None:
    page = read(project / DEMO_PAGE)
    assert page.startswith("<!doctype html>")
    head = "\n".join(page.splitlines()[:5])
    assert P.is_generated_text(page)
    assert "build-prototype.py" in head and f"{TOURS_REL}/demo.json" in head
    assert '<meta charset="utf-8">' in page[:3000] and '<meta name="viewport"' in page[:3000]
    assert '<base href="../">' in page[:3000], "the page sits one folder down: links and images resolve from the docs folder"
    assert not NETWORK.search(page), NETWORK.search(page)
    assert "<title>Taking a booking at Café Ünïcode · Café Ünïcode walkthrough</title>" in page
    data = tours_json(page)
    assert [t["id"] for t in data["tours"]] == ["demo"], "the page carries its own tour"
    assert data["autostart"] == {"tour": "demo", "mode": "play"}, "a client tour opens in play mode"
    for screen in ("home", "booking", "menu"):
        assert f'data-screen="{screen}"' in page, "the whole prototype is in the page"
    assert "window.plumbPlayer" in page and ".pl-dock" in page


def test_training_tour_opens_in_guide_mode(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", {"demo": demo(), "training": training()})
    assert tours_json(read(p / f"{PAGES_REL}/training.html"))["autostart"] == {"tour": "training", "mode": "guide"}
    for audience, mode in (("client", "play"), ("whats-new", "play"), ("training", "guide"), ("review", "guide"),
                           ("team", "guide")):
        doc = training()
        doc["audience"] = audience
        put_tour(p, "training", doc)
        assert run(p).returncode == 0
        assert tours_json(read(p / f"{PAGES_REL}/training.html"))["autostart"]["mode"] == mode, audience


def test_prototype_embeds_every_tour_and_the_player(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", {"demo": demo(), "training": training()})
    page = read(p / PROTO_REL)
    data = tours_json(page)
    assert [t["id"] for t in data["tours"]] == ["demo", "training"]
    assert data["autostart"] is None, "prototype.html opens on the screens, not in a tour"
    assert "<base " not in page
    assert "window.plumbPlayer" in page and ".pl-dock" in page
    assert not NETWORK.search(page)


def test_prototype_without_tours_still_has_the_player_and_guide_panel(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p")
    page = read(p / PROTO_REL)
    assert tours_json(page) == {"tours": [], "autostart": None}
    assert "window.plumbPlayer" in page
    assert not (p / PAGES_REL).exists()


def test_tour_data_is_normalised_with_defaults(project: Path) -> None:
    tour = tours_json(read(project / PROTO_REL))["tours"][0]
    assert tour["id"] == "demo" and tour["mode"] == "play" and tour["speed"] == 1
    assert [c["title"] for c in tour["chapters"]] == ["Tonight at a glance", "Take the booking"]
    assert [c["first"] for c in tour["chapters"]] == [0, 2]
    steps = tour["steps"]
    assert len(steps) == 6
    assert steps[1]["state"] == "ready", "a step without a state uses the screen's first state"
    assert steps[1]["point"] == "arrow" and steps[1]["pointLabel"] == "Start here"
    assert steps[0]["targets"] == [".tables"] and steps[5]["targets"] == ["[data-test=new-booking]"]
    assert steps[2]["action"] == {"kind": "type", "target": "[data-test=guest]", "value": "Zoë Brontë", "ms": 0}
    assert steps[3]["action"]["kind"] == "click" and steps[3]["action"]["target"] == "[data-test=save]"
    assert steps[3]["yourTurn"] is True and steps[3]["hint"].startswith("Not that one")
    assert [s["chapter"] for s in steps] == [0, 0, 1, 1, 1, 1]
    t = tours_json(read(project / DEMO_PAGE))["tours"][0]
    assert t == tour


def test_defaults_for_a_minimal_tour(tmp_path: Path) -> None:
    doc = {"title": "Look around", "steps": [{"screen": "menu", "caption": "Tonight's menu."}]}
    p = make_tour_project(tmp_path / "p", {"look": doc})
    tour = tours_json(read(p / PROTO_REL))["tours"][0]
    assert tour["audience"] == "review" and tour["mode"] == "guide" and tour["speed"] == 1
    assert tour["intro"] is None and tour["closing"] is None and tour["chapters"] == []
    step = tour["steps"][0]
    assert step["state"] == "ready" and step["point"] == "none" and step["targets"] == []
    assert step["action"] is None and step["yourTurn"] is False and step["hold"] is None


def test_tour_text_cannot_inject_markup(tmp_path: Path) -> None:
    doc = demo()
    evil = "</script><script>alert(1)</script><img src=x onerror=alert(2)>"
    doc["chapters"][0]["steps"][0]["caption"] = evil
    doc["title"] = "<b>bold</b> & co"
    p = make_tour_project(tmp_path / "p", {"demo": doc})
    for rel in (PROTO_REL, DEMO_PAGE):
        page = read(p / rel)
        assert "</script><script>alert(1)" not in page
        assert "<img src=x onerror" not in page
        assert tours_json(page)["tours"][0]["steps"][0]["caption"] == evil
    assert "<title>&lt;b&gt;bold&lt;/b&gt; &amp; co · Café Ünïcode walkthrough</title>" in read(p / DEMO_PAGE)


# ---------------------------------------------------------------- drift: --check, removal, byte stability


def test_check_is_clean_after_a_build(project: Path) -> None:
    r = run(project, "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 tour" in r.stdout


def test_check_names_a_stale_tour_page_and_writes_nothing(project: Path) -> None:
    doc = demo()
    doc["chapters"][0]["steps"][0]["caption"] = "A new caption."
    put_tour(project, "demo", doc)
    before = (project / DEMO_PAGE).read_bytes()
    r = run(project, "--check")
    assert r.returncode == 1
    assert f"stale: {DEMO_PAGE}" in r.stdout and f"stale: {PROTO_REL}" in r.stdout
    assert "fix: python3 " in r.stdout
    assert (project / DEMO_PAGE).read_bytes() == before


def test_check_names_a_missing_tour_page(project: Path) -> None:
    (project / DEMO_PAGE).unlink()
    r = run(project, "--check")
    assert r.returncode == 1 and f"stale: {DEMO_PAGE} (missing)" in r.stdout


def test_hand_edit_of_a_tour_page_is_stale(project: Path) -> None:
    path = project / DEMO_PAGE
    write(path, read(path).replace("Taking a booking", "Taking a reservation"))
    r = run(project, "--check")
    assert r.returncode == 1 and f"stale: {DEMO_PAGE}" in r.stdout
    assert run(project).returncode == 0 and run(project, "--check").returncode == 0


def test_a_deleted_tour_file_removes_its_page(project: Path) -> None:
    keep = project / PAGES_REL / "notes.html"
    write(keep, "<!doctype html><p>My own notes</p>\n")
    (project / TOURS_REL / "demo.json").unlink()
    r = run(project, "--check")
    assert r.returncode == 1
    assert f"stale: {DEMO_PAGE} (its tour file is gone)" in r.stdout
    assert "notes.html" not in r.stdout, "only generated pages are Plumb's to remove"
    assert (project / DEMO_PAGE).exists(), "--check writes nothing"
    r = run(project)
    assert r.returncode == 0, r.stderr
    assert f"removed {DEMO_PAGE}" in r.stdout
    assert not (project / DEMO_PAGE).exists()
    assert keep.exists()
    assert tours_json(read(project / PROTO_REL))["tours"] == []
    assert run(project, "--check").returncode == 0


def test_the_tours_folder_goes_when_its_last_page_does(project: Path) -> None:
    (project / TOURS_REL / "demo.json").unlink()
    assert run(project).returncode == 0
    assert not (project / PAGES_REL).exists()


def test_rebuild_is_byte_stable(project: Path) -> None:
    before = {rel: (project / rel).read_bytes() for rel in (PROTO_REL, DEMO_PAGE)}
    r = run(project)
    assert r.returncode == 0 and "wrote" not in r.stdout
    assert {rel: (project / rel).read_bytes() for rel in before} == before


def test_crlf_and_bom_tour_files_give_identical_pages(project: Path, tmp_path: Path) -> None:
    other = make_tour_project(tmp_path / "other" / "Café Ünïcode", build=False)
    path = other / TOURS_REL / "demo.json"
    path.write_bytes(b"\xef\xbb\xbf" + read(DEMO_SRC).replace("\n", "\r\n").encode("utf-8"))
    assert run(other).returncode == 0
    for rel in (PROTO_REL, DEMO_PAGE):
        assert (other / rel).read_bytes() == (project / rel).read_bytes(), rel


def test_a_removed_element_breaks_the_tour(project: Path) -> None:
    """A screen edit that drops an element a tour points at fails the build and --check (the tour drifted)."""
    path = project / BOOKING_REL
    write(path, read(path).replace(' data-test="save"', ""))
    for args in ((), ("--check",)):
        r = run(project, *args)
        assert_refusal(r, f"{TOURS_REL}/demo.json:", '"[data-test=save]"', BOOKING_REL, "state ready")


def test_build_tokens_refreshes_the_tour_pages(project: Path) -> None:
    doc = json.loads(read(project / TOKENS_REL))
    doc["color"]["primary"]["$value"] = "#0b5a56"
    write(project / TOKENS_REL, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    r = build_tokens(project, "--check")
    assert r.returncode == 1 and f"stale: {DEMO_PAGE} (prototype token block)" in r.stdout
    assert build_tokens(project).returncode == 0
    assert "--color-primary: #0b5a56;" in read(project / DEMO_PAGE)
    assert run(project, "--check").returncode == 0


def test_tour_pages_follow_the_docs_dir(tmp_path: Path) -> None:
    def mutate(doc):
        doc["$extensions"]["plumb"]["docs_dir"] = "design-docs"

    p = make_project(tmp_path / "p", screens=False, decisions=False, build=False, mutate=mutate)
    shutil.copytree(FIXTURE / "screens", p / "design-docs/prototype/screens")
    write(p / "design-docs/prototype/tours/demo.json", json.dumps(demo(), ensure_ascii=False))
    r = run(p)
    assert r.returncode == 0, r.stderr
    assert (p / "design-docs/tours/demo.html").is_file()
    assert not (p / DOCS).exists()


# ---------------------------------------------------------------- validation: every refusal exits 2 with error and fix


def _step(doc: dict, i: int = 0, chapter: int = 0) -> dict:
    return doc["chapters"][chapter]["steps"][i]


def _set(fn):
    def apply(doc):
        fn(doc)
        return doc
    return apply


REFUSALS = {
    "not-an-object": (lambda d: [], ["demo.json", "JSON object"]),
    "unknown-top-field": (_set(lambda d: d.update(titel="x")), ['unknown field "titel"', "audience"]),
    "no-title": (_set(lambda d: d.pop("title")), ['no "title"']),
    "empty-title": (_set(lambda d: d.update(title="  ")), ['"title"']),
    "bad-audience": (_set(lambda d: d.update(audience="investors")), ['audience "investors"', "client, training, review, team, whats-new"]),
    "bad-speed": (_set(lambda d: d.update(speed=3)), ["speed 3", "0.5, 1, 1.5, 2"]),
    "speed-not-a-number": (_set(lambda d: d.update(speed="fast")), ['speed "fast"']),
    "steps-and-chapters": (_set(lambda d: d.update(steps=[{"screen": "home"}])), ['both "steps" and "chapters"']),
    "no-steps": (_set(lambda d: (d.pop("chapters"), d.update(steps=[]))), ["has no steps"]),
    "chapters-not-a-list": (_set(lambda d: d.update(chapters={"title": "x"})), ['"chapters" must be a list']),
    "chapter-no-title": (_set(lambda d: d["chapters"][1].pop("title")), ['chapters[1] has no "title"']),
    "chapter-no-steps": (_set(lambda d: d["chapters"][1].update(steps=[])), ["chapters[1] has no steps"]),
    "intro-no-title": (_set(lambda d: d["intro"].pop("title")), ['intro has no "title"']),
    "closing-unknown-field": (_set(lambda d: d["closing"].update(body="x")), ['closing has an unknown field "body"']),
    "step-unknown-field": (_set(lambda d: _step(d).update(captoin="x")), ['chapters[0].steps[0] has an unknown field "captoin"']),
    "step-no-screen": (_set(lambda d: _step(d).pop("screen")), ['chapters[0].steps[0] has no "screen"']),
    "unknown-screen": (_set(lambda d: _step(d).update(screen="bookings")), ['screen "bookings"', "home, booking, menu"]),
    "unknown-state": (_set(lambda d: _step(d, 0, 1).update(state="done")), ['state "done"', "ready, error, success"]),
    "missing-target": (_set(lambda d: _step(d, 1, 1).update(target="[data-test=sav]")),
                       ['chapters[1].steps[1].target "[data-test=sav]" matches nothing', BOOKING_REL, "state ready"]),
    "target-in-another-state": (_set(lambda d: _step(d, 2, 1).update(target="[data-test=save]")),
                                ['"[data-test=save]" matches nothing', "state success"]),
    "target-and-targets": (_set(lambda d: _step(d).update(targets=["h2"])), ['both "target" and "targets"']),
    "targets-empty": (_set(lambda d: (_step(d, 1, 1).pop("target"), _step(d, 1, 1).update(targets=[]))),
                      ['"targets" must be a list of selectors']),
    "bad-point": (_set(lambda d: _step(d).update(point="glow")), ['point "glow"', "spotlight, ring, arrow, beacon, zoom, cursor, none"]),
    "bad-point-object": (_set(lambda d: _step(d).update(point={"style": "arrow", "colour": "red"})), ['point has an unknown field "colour"']),
    "point-without-target": (_set(lambda d: (_step(d).pop("target"), _step(d).pop("labels"))), ["point spotlight", "no target"]),
    "callout-bad-side": (_set(lambda d: _step(d, 1).update(callout={"text": "x", "side": "middle"})), ['side "middle"', "top, right, bottom, left"]),
    "callout-without-text": (_set(lambda d: _step(d, 1).update(callout={"side": "top"})), ['callout has no "text"']),
    "label-target-missing": (_set(lambda d: _step(d)["labels"][1].update(target=".nope")), ['labels[1].target ".nope" matches nothing']),
    "label-no-text": (_set(lambda d: _step(d)["labels"][0].pop("text")), ['labels[0] has no "text"']),
    "note-out-of-range": (_set(lambda d: _step(d, 2, 1)["note"].update(x=140)), ["note.x 140", "0 to 100"]),
    "action-two-kinds": (_set(lambda d: _step(d, 1).update(action={"click": True, "wait": 100})),
                         ["exactly one of click, type, choose, wait"]),
    "action-unknown-kind": (_set(lambda d: _step(d, 1).update(action={"press": "x"})), ['action has an unknown field "press"']),
    "action-click-missing": (_set(lambda d: _step(d, 1).update(action={"click": "[data-test=nope]"})),
                             ['action.click "[data-test=nope]" matches nothing']),
    "action-type-no-target": (_set(lambda d: (_step(d, 0, 1).pop("target"), _step(d, 0, 1).update(point="none"))),
                              ["action.type needs a target"]),
    "action-wait-bad": (_set(lambda d: _step(d).update(action={"wait": -1})), ["action.wait -1"]),
    "your-turn-without-action": (_set(lambda d: _step(d).update(your_turn=True)), ["your_turn", "click, type or choose"]),
    "your-turn-with-wait": (_set(lambda d: _step(d).update(your_turn=True, action={"wait": 500})), ["your_turn", "click, type or choose"]),
    "your-turn-not-bool": (_set(lambda d: _step(d, 1, 1).update(your_turn="yes")), ["your_turn must be true or false"]),
    "bad-hold": (_set(lambda d: _step(d).update(hold=-5)), ["hold -5"]),
    "caption-not-text": (_set(lambda d: _step(d).update(caption=42)), ["caption must be text"]),
    "no-title-or-caption": (_set(lambda d: (_step(d).pop("title"), _step(d).pop("caption"))), ['"title" or a "caption"']),
    "unsupported-selector": (_set(lambda d: _step(d).update(target=".tables li:hover")), [":hover", "class or data attribute"]),
    "unparseable-selector": (_set(lambda d: _step(d).update(target="[data-test=")), ['"[data-test="', "not a CSS selector"]),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_refusals(tmp_path: Path, case: str, capsys) -> None:
    mutate, needles = REFUSALS[case]
    p = make_tour_project(tmp_path / "p", build=False)
    put_tour(p, "demo", mutate(demo()))
    for args in ((), ("--check",)):
        code, out, err = build_in_process(p, *args, capsys=capsys)
        assert code == 2, (case, args, out, err)
        assert "error: " in err and "\nfix: " in err, err
        assert "Traceback" not in err
        assert f"{TOURS_REL}/demo.json" in err, err
        for n in needles:
            assert n in err, (case, err)
    assert not (p / DEMO_PAGE).exists()


def test_refusals_run_as_a_script_too(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    doc = demo()
    _step(doc).update(screen="bookings")
    put_tour(p, "demo", doc)
    assert_refusal(run(p), 'screen "bookings"')
    assert_refusal(run(p, "--check"), 'screen "bookings"')


def test_refusals_name_the_line(tmp_path: Path, capsys) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    doc = demo()
    _step(doc, 1, 1).update(target="[data-test=sav]")
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    put_tour(p, "demo", text)
    line = text.splitlines().index('          "target": "[data-test=sav]",') + 1
    code, _out, err = build_in_process(p, capsys=capsys)
    assert code == 2 and f"{TOURS_REL}/demo.json:{line}: " in err, err

    doc = demo()
    _step(doc).update(captoin="x")
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    put_tour(p, "demo", text)
    line = text.splitlines().index('          "captoin": "x"') + 1
    code, _out, err = build_in_process(p, capsys=capsys)
    assert code == 2 and f"{TOURS_REL}/demo.json:{line}: " in err, err


def test_invalid_json_names_the_line(tmp_path: Path, capsys) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    put_tour(p, "demo", '{\n  "title": "x",\n  "steps": [}\n')
    code, _out, err = build_in_process(p, capsys=capsys)
    assert code == 2 and f"{TOURS_REL}/demo.json:3: " in err and "not valid JSON" in err, err


def test_unreadable_tour_file_is_refused(tmp_path: Path, capsys) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    (p / TOURS_REL / "demo.json").write_bytes(b'{"title": "caf\xe9"}')
    code, _out, err = build_in_process(p, capsys=capsys)
    assert code == 2 and "UTF-8" in err and "fix: " in err, err


def test_bad_tour_file_name_is_refused(tmp_path: Path, capsys) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    put_tour(p, "my tour", training())
    code, _out, err = build_in_process(p, capsys=capsys)
    assert code == 2 and 'tour id "my tour"' in err and "fix: " in err, err


def test_duplicate_tour_ids_are_refused() -> None:
    """Demo.json and demo.json are one tour on Windows and macOS: refused everywhere, so the pages never collide."""
    with pytest.raises(P.PlumbError) as exc:
        BP.check_tour_ids([("Demo", "x/Demo.json"), ("demo", "x/demo.json")])
    assert 'duplicate tour id "demo"' in str(exc.value) and "\nfix: " in str(exc.value)


def test_tour_ids_that_collide_in_links_are_refused(tmp_path: Path, capsys) -> None:
    p = make_tour_project(tmp_path / "p", {"demo": demo(), "demo-2": training()}, build=False)
    code, _out, err = build_in_process(p, capsys=capsys)
    assert code == 2, err
    assert '"demo-2"' in err and "#tour-demo-2" in err and "fix: " in err, err


def test_tours_without_screens_are_refused_and_check_stays_quiet(tmp_path: Path) -> None:
    p = make_project(tmp_path / "p", screens=False, build=False)
    put_tour(p, "demo", demo())
    r = run(p, "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert_refusal(run(p), "no screen files")


# ---------------------------------------------------------------- the selector check (stdlib only)


MARKUP = """<section data-screen="s" data-title="S">
  <header class="top bar" id="head"><h2 lang="en-GB">Title</h2><a href="#screen-x" data-test="go">Go</a></header>
  <div data-state="ready">
    <ul class="list"><li class="row">One</li><li class="row hot">Two</li><li class="row">Three</li></ul>
    <form><label>Name <input name="guest" type="text" required></label><select name="t"><option value="a">A</option></select>
    <button type="submit" disabled>Save</button></form>
    <p>First</p><p class="muted">Second</p>
  </div>
  <div data-state="empty"><p class="only-empty">Nothing</p><div data-state="nested"><b>inner</b></div></div>
</section>"""


@pytest.mark.parametrize("selector, ready, empty", [
    ("h2", 1, 1), ("#head", 1, 1), (".row", 3, 0), (".row.hot", 1, 0), ("li.hot", 1, 0), ("*", 16, 7),
    ("[data-test=go]", 1, 1), ('[data-test="go"]', 1, 1), ("[data-test='go']", 1, 1), ("[href^='#screen']", 1, 1),
    ("[href$=x]", 1, 1), ("[href*=een]", 1, 1), (".top", 1, 1), ("[class~=bar]", 1, 1), ("[lang|=en]", 1, 1),
    ("[data-test=GO i]", 1, 1), ("header > h2", 1, 1), ("header h2", 1, 1), ("section h2", 1, 1), ("[data-screen=s] > header > h2", 1, 1),
    ("h2 + a", 1, 1), ("h2 ~ a", 1, 1), ("ul > li:first-child", 1, 0), ("li:last-child", 1, 0),
    ("li:nth-child(2)", 1, 0), ("li:nth-child(odd)", 2, 0), ("li:nth-child(2n+1)", 2, 0), ("p:nth-of-type(2)", 1, 0),
    ("li:not(.hot)", 2, 0), ("input[required]", 1, 0), ("button:disabled", 1, 0), (".only-empty", 0, 1),
    ("b", 0, 1), (".list, .only-empty", 1, 1), ("[data-state] p", 2, 1), ("b:only-child", 0, 1), ("p:only-child", 0, 0),
    ("select > option:first-of-type", 1, 0), ("li:is(.hot, .nope)", 1, 0),
])
def test_selector_matching(selector: str, ready: int, empty: int) -> None:
    tree = BP.parse_markup(MARKUP)
    assert len(BP.select(tree, selector, "ready")) == ready, selector
    assert len(BP.select(tree, selector, "empty")) == empty, selector


@pytest.mark.parametrize("selector", ["li:hover", "a::before", "li:nth-child(foo)", "[data-x", "a >", ",", ""])
def test_selectors_the_check_cannot_read_are_errors(selector: str) -> None:
    tree = BP.parse_markup(MARKUP)
    with pytest.raises(BP.SelectorError):
        BP.select(tree, selector, "ready")


def test_json_lines_maps_paths_to_lines() -> None:
    text = '{\n  "a": 1,\n  "b": [\n    {"c": "x"},\n    {\n      "d": [1, 2]\n    }\n  ]\n}\n'
    lines = BP.json_lines(text)
    assert lines[("a",)] == 2 and lines[("b",)] == 3 and lines[("b", 0)] == 4 and lines[("b", 0, "c")] == 4
    assert lines[("b", 1)] == 5 and lines[("b", 1, "d")] == 6 and lines[("b", 1, "d", 1)] == 6


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
    multi = training()
    multi["steps"].append({"screen": "home", "title": "Several rings", "caption": "Two things at once.",
                           "targets": ["h2", "[data-test=new-booking]"], "point": "ring"})
    lesson = {"title": "Lesson: booking a table", "audience": "training", "steps": [
        {"screen": "booking", "title": "Book", "caption": "Your turn: book the table.", "target": "[data-test=save]",
         "point": "cursor", "action": {"click": True}, "your_turn": True},
        {"screen": "home", "title": "All of tonight", "caption": "The whole list.", "target": ".tables", "point": "zoom"},
    ]}
    return make_tour_project(tmp_path_factory.mktemp("tours") / "Café Ünïcode",
                             {"demo": demo(), "training": multi, "lesson": lesson})


LOG = """
window.__log = [];
document.addEventListener('plumb:tour', function (e) {
  window.__log.push(Object.assign({t: performance.now()}, e.detail));
});
"""


def _open(browser, path: Path, width: int = 1280, scheme: str = "light", hash_: str = "", reduced: bool = False):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                              reduced_motion="reduce" if reduced else "no-preference")
    page = ctx.new_page()
    errors: list = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    requests: list = []
    page.on("request", lambda req: requests.append(req.url) if not req.url.startswith(("file:", "data:", "about:")) else None)
    page.add_init_script(LOG)
    page.goto(path.resolve().as_uri() + hash_)
    page.wait_for_load_state("load")
    return ctx, page, errors, requests


def _state(page) -> dict:
    return page.evaluate("window.plumbPlayer.state()")


def _start(page, tour: str = "demo", mode: str = "guide", step=None, speed=None) -> None:
    opts = {"mode": mode}
    if step is not None:
        opts["step"] = step
    if speed is not None:
        opts["speed"] = speed
    page.evaluate("([t, o]) => window.plumbPlayer.start(t, o)", [tour, opts])


def _wait_pos(page, pos: int, timeout: int = 8000) -> None:
    page.wait_for_function("(p) => window.plumbPlayer.state().pos === p", arg=pos, timeout=timeout)


def _visible_screen(page) -> str:
    return page.evaluate("""() => [...document.querySelectorAll('#pp-frame > [data-screen]')]
        .filter(s => !s.hidden).map(s => s.dataset.screen).join(',')""")


def _shown(page, selector: str) -> int:
    return page.evaluate("""(sel) => [...document.querySelectorAll(sel)].filter(e => !e.hidden &&
        e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden').length""", selector)


def test_guide_mode_waits_and_moves_with_next_back_arrows_and_esc(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        page.click('#plumb-guide [data-tour-start="demo"][data-mode="guide"]')
        s = _state(page)
        assert s["active"] and s["mode"] == "guide" and s["pos"] == 0 and s["card"] == "intro"
        assert _shown(page, ".pl-card") == 1 and "Taking a booking" in page.inner_text(".pl-card")
        page.wait_for_timeout(1500)
        assert _state(page)["pos"] == 0, "guide mode waits"
        page.click(".pl-dock [data-pl=next]")
        assert _state(page)["pos"] == 1 and _state(page)["card"] == "chapter"
        page.keyboard.press("ArrowRight")
        s = _state(page)
        assert s["pos"] == 2 and s["step"] == 1 and _visible_screen(page) == "home"
        assert page.inner_text(".pl-dock .pl-title") == "Tonight's tables"
        assert "Step 1 of 6" in page.inner_text(".pl-dock")
        page.keyboard.press("ArrowLeft")
        assert _state(page)["pos"] == 1
        page.keyboard.press("ArrowRight")
        page.click(".pl-dock [data-pl=back]")
        assert _state(page)["pos"] == 1
        page.keyboard.press("Escape")
        assert _state(page)["active"] is False
        assert _shown(page, ".pl-dock") == 0 and _shown(page, ".pl-card") == 0
        assert page.evaluate("document.activeElement.getAttribute('data-tour-start')") == "demo", "focus goes back"
        assert errors == []
    finally:
        ctx.close()


def test_guide_next_on_a_click_step_performs_the_click(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=2)
        assert _visible_screen(page) == "home"
        page.click(".pl-dock [data-pl=next]")
        assert _state(page)["step"] is None and _state(page)["card"] == "chapter"
        assert _visible_screen(page) == "booking", "the real link was clicked"
        assert errors == []
    finally:
        ctx.close()


def test_play_mode_advances_by_itself_at_1x_and_2x(browser, built) -> None:
    timings = {}
    for speed in (1, 2):
        ctx, page, errors, _ = _open(browser, built / PROTO_REL)
        try:
            _start(page, "demo", "play", step=1, speed=speed)
            _wait_pos(page, 3)
            log = page.evaluate("window.__log")
            t2 = next(e["t"] for e in log if e["pos"] == 2)
            t3 = next(e["t"] for e in log if e["pos"] == 3)
            timings[speed] = t3 - t2
            s = _state(page)
            assert s["mode"] == "play" and s["speed"] == speed and not s["paused"]
            assert page.inner_text(".pl-badge") == f"▶ Playing · {speed}×"
            assert errors == []
        finally:
            ctx.close()
    assert 600 <= timings[1] <= 1300, timings
    assert 280 <= timings[2] <= 800, timings
    assert timings[2] < timings[1] * 0.75, timings


def test_speed_buttons_apply_live(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "play", step=1)
        page.click('.pl-dock [data-speed="2"]')
        assert _state(page)["speed"] == 2
        assert page.get_attribute('.pl-dock [data-speed="2"]', "aria-pressed") == "true"
        assert page.inner_text(".pl-badge") == "▶ Playing · 2×"
        page.click('.pl-dock [data-speed="0.5"]')
        assert _state(page)["speed"] == 0.5
        assert errors == []
    finally:
        ctx.close()


def test_space_pauses_and_resumes_play(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "play", step=1)
        page.evaluate("document.activeElement && document.activeElement.blur()")
        page.keyboard.press(" ")
        assert _state(page)["paused"] is True
        assert page.inner_text(".pl-badge") == "❚❚ Paused · 1×"
        page.wait_for_timeout(1400)
        assert _state(page)["pos"] == 2, "paused play does not move"
        page.keyboard.press(" ")
        assert _state(page)["paused"] is False
        _wait_pos(page, 3, timeout=3000)
        page.click(".pl-dock [data-pl=play]")
        assert _state(page)["paused"] is True
        page.click(".pl-dock [data-pl=play]")
        assert _state(page)["paused"] is False
        assert errors == []
    finally:
        ctx.close()


def test_scene_markers_are_the_chapters_and_jump(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "play")
        marks = page.locator(".pl-dock .pl-marks button")
        assert marks.count() == 2
        assert "Tonight at a glance" in marks.nth(0).get_attribute("aria-label")
        assert "Take the booking" in marks.nth(1).get_attribute("aria-label")
        marks.nth(1).click()
        s = _state(page)
        assert s["pos"] == 4 and s["card"] == "chapter" and s["mode"] == "play"
        assert "Take the booking" in page.inner_text(".pl-card")
        _wait_pos(page, 5, timeout=3000)
        page.click(".pl-dock [data-pl=restart]")
        assert _state(page)["pos"] == 0
        assert errors == []
    finally:
        ctx.close()


def test_steps_are_markers_without_chapters(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "training", "guide")
        assert page.locator(".pl-dock .pl-marks button").count() == 4
        page.locator(".pl-dock .pl-marks button").nth(2).click()
        assert _state(page)["step"] == 3
        assert errors == []
    finally:
        ctx.close()


def test_the_cursor_clicks_the_real_control_in_play(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        page.evaluate("""() => { window.__screens = []; window.__taps = 0;
            window.plumbPrototype.on(e => window.__screens.push([e.screen, window.plumbPlayer.state().pos]));
            new MutationObserver(() => { var c = document.querySelector('.pl-cursor');
              if (c && c.classList.contains('pl-tap')) window.__taps++; })
              .observe(document.body, {subtree: true, attributes: true, attributeFilter: ['class']}); }""")
        _start(page, "demo", "play", step=2)
        _wait_pos(page, 4)
        screens = page.evaluate("window.__screens")
        assert ["booking", 3] in screens, f"the click on step 2 changed the screen: {screens}"
        assert page.evaluate("window.__taps") >= 1
        assert _visible_screen(page) == "booking"
        assert errors == []
    finally:
        ctx.close()


def test_typed_text_is_letter_by_letter_in_play_and_instant_in_guide(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        page.evaluate("""() => { window.__values = []; setInterval(() => {
            var f = document.querySelector('#pp-frame [data-test=guest]'); window.__values.push(f.value); }, 15); }""")
        _start(page, "demo", "play", step=3)
        _wait_pos(page, 6)
        values = page.evaluate("window.__values")
        partial = [v for v in values if 0 < len(v) < len("Zoë Brontë")]
        assert partial and all("Zoë Brontë".startswith(v) for v in partial), values
        assert page.input_value("#pp-frame [data-test=guest]") == "Zoë Brontë"
        page.evaluate("window.plumbPlayer.leave()")
        page.fill("#pp-frame [data-test=guest]", "")
        _start(page, "demo", "guide", step=3)
        assert page.input_value("#pp-frame [data-test=guest]") == "Zoë Brontë"
        assert errors == []
    finally:
        ctx.close()


def test_your_turn_waits_for_the_real_click_and_hints_on_a_wrong_one(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=3)
        page.click(".pl-dock [data-pl=next]")
        s = _state(page)
        assert s["step"] == 4 and s["yourTurn"] is True
        assert _shown(page, ".pl-dock [data-pl=next]") == 0, "no Next on a your-turn step"
        assert _shown(page, ".pl-dock [data-pl=do]") == 1, "but the player can do it for you"
        page.wait_for_timeout(1200)
        assert _state(page)["step"] == 4
        assert _shown(page, ".pl-hint") == 0
        page.click('#pp-frame [data-screen="booking"] h2')
        assert _shown(page, ".pl-hint") == 1
        assert "Book the table" in page.inner_text(".pl-hint")
        assert _state(page)["step"] == 4
        page.click("#pp-frame [data-test=save]")
        page.wait_for_function("window.plumbPlayer.state().step === 5")
        assert page.evaluate("window.plumbPrototype.current().state") == "success"
        assert _shown(page, ".pl-hint") == 0
        assert errors == []
    finally:
        ctx.close()


def test_a_wrong_click_does_not_leave_the_screen(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=4)
        page.click('#pp-frame [data-screen="booking"] h2')
        assert _shown(page, ".pl-hint") == 1
        page.click(".pl-dock [data-pl=do]")
        page.wait_for_function("window.plumbPlayer.state().step === 5")
        assert errors == []
    finally:
        ctx.close()


def test_your_turn_is_played_by_itself_in_play_mode(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "play", step=4, speed=2)
        page.wait_for_function("window.plumbPlayer.state().step === 5", timeout=6000)
        assert errors == []
    finally:
        ctx.close()


@pytest.mark.parametrize("step, selector, count", [
    (1, ".pl-dim", 1), (1, ".pl-label", 2), (2, ".pl-arrow", 1), (2, ".pl-callout", 1), (3, ".pl-ring", 1),
    (4, ".pl-cursor", 1), (5, ".pl-beacon", 1), (5, ".pl-note", 1),
])
def test_each_way_of_pointing_renders(browser, built, step: int, selector: str, count: int) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=step)
        assert _shown(page, selector) == count, selector
        assert errors == []
    finally:
        ctx.close()


def test_pointing_text_and_positions(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=1)
        labels = page.locator(".pl-label").all_inner_texts()
        assert labels == ["1 Today", "2 New booking"]
        _start(page, "demo", "guide", step=2)
        assert "Start here" in page.inner_text(".pl-arrow")
        assert page.inner_text(".pl-callout") == "Every booking starts here"
        callout = page.evaluate("document.querySelector('.pl-callout').getBoundingClientRect().top")
        target = page.evaluate("document.querySelector('#pp-frame [data-test=new-booking]').getBoundingClientRect().bottom")
        assert callout >= target, "side bottom puts the callout under the element"
        _start(page, "demo", "guide", step=5)
        assert page.inner_text(".pl-note") == "Saved in one step"
        assert errors == []
    finally:
        ctx.close()


def test_zoom_enlarges_the_area(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=6)
        page.wait_for_timeout(500)
        assert page.evaluate("getComputedStyle(document.getElementById('pp-frame')).transform") not in ("none", "")
        page.click(".pl-dock [data-pl=back]")
        assert page.evaluate("getComputedStyle(document.getElementById('pp-frame')).transform") in ("none", "")
        assert errors == []
    finally:
        ctx.close()


def test_several_rings_in_one_step(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "training", "guide", step=4)
        assert _shown(page, ".pl-ring") == 2
        assert errors == []
    finally:
        ctx.close()


def test_intro_and_closing_cards(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide")
        assert "Taking a booking" in page.inner_text(".pl-card")
        assert "What you'll see" in page.inner_text(".pl-card")
        _start(page, "demo", "guide", step=6)
        page.click(".pl-dock [data-pl=next]")
        s = _state(page)
        assert s["card"] == "closing"
        assert "What to try next" in page.inner_text(".pl-card")
        assert page.inner_text(".pl-dock [data-pl=next]") == "Finish"
        page.click(".pl-dock [data-pl=next]")
        assert _state(page)["active"] is False
        assert errors == []
    finally:
        ctx.close()


def test_play_runs_to_the_end_at_2x(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "play", speed=2)
        page.wait_for_function("window.__log.some(e => e.card === 'closing')", timeout=15000)
        page.wait_for_function("!window.plumbPlayer.state().active || window.plumbPlayer.state().ended", timeout=5000)
        steps = [e["step"] for e in page.evaluate("window.__log") if e.get("step")]
        assert steps == [1, 2, 3, 4, 5, 6]
        assert errors == []
    finally:
        ctx.close()


def test_deep_link_opens_a_step(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, hash_="#tour-training-2")
    try:
        page.wait_for_function("window.__log.length > 0")
        first = page.evaluate("window.__log[0]")
        assert first["tour"] == "training" and first["step"] == 2 and first["mode"] == "guide"
        assert _visible_screen(page) == "booking"
        page.click(".pl-dock [data-pl=next]")
        assert page.evaluate("location.hash") == "#tour-training-3"
        assert errors == []
    finally:
        ctx.close()
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, hash_="#tour-demo-3")
    try:
        page.wait_for_function("window.__log.length > 0")
        first = page.evaluate("window.__log[0]")
        assert first["tour"] == "demo" and first["step"] == 3 and first["mode"] == "play"
        assert errors == []
    finally:
        ctx.close()
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, hash_="#tour-demo")
    try:
        page.wait_for_function("window.__log.length > 0")
        assert page.evaluate("window.__log[0]")["pos"] == 0
        assert errors == []
    finally:
        ctx.close()


def test_tour_links_inside_the_page_start_the_tour(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        page.evaluate("""() => { var a = document.createElement('a'); a.href = '#tour-training-3'; a.id = 'tl';
            a.textContent = 'go'; document.querySelector('.pp-foot').appendChild(a); }""")
        page.click("#tl")
        s = _state(page)
        assert s["tour"] == "training" and s["step"] == 3
        assert errors == []
    finally:
        ctx.close()


def test_standalone_pages_open_straight_into_the_tour(browser, built) -> None:
    ctx, page, errors, requests = _open(browser, built / DEMO_PAGE)
    try:
        page.wait_for_function("window.__log.length > 0")
        first = page.evaluate("window.__log[0]")
        assert first["tour"] == "demo" and first["mode"] == "play" and first["pos"] == 0
        _wait_pos(page, 1, timeout=3000)
        page.keyboard.press("Escape")
        assert _state(page)["active"] is False
        page.click('.pp-nav [data-nav="menu"]')
        assert _visible_screen(page) == "menu", "viewers can leave the tour and click around"
        assert page.evaluate("location.pathname").endswith("/tours/demo.html")
        assert page.evaluate("location.hash") == "#screen-menu"
        href = page.evaluate("document.querySelector('a[href=\"screens.html\"]').href")
        assert href.endswith("/docs/design/screens.html"), href
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()
    ctx, page, errors, _ = _open(browser, built / f"{PAGES_REL}/training.html")
    try:
        page.wait_for_function("window.__log.length > 0")
        assert page.evaluate("window.__log[0]")["mode"] == "guide"
        page.wait_for_timeout(800)
        assert _state(page)["pos"] == 0
        assert errors == []
    finally:
        ctx.close()


def test_reduced_motion_still_plays_without_the_glide(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, reduced=True)
    try:
        _start(page, "demo", "play", step=2)
        page.wait_for_function("document.querySelector('.pl-cursor') && !document.querySelector('.pl-cursor').hidden",
                               timeout=4000)
        assert page.evaluate("getComputedStyle(document.querySelector('.pl-cursor')).transitionDuration") == "0s"
        _wait_pos(page, 4)
        s = _state(page)
        assert s["mode"] == "play" and s["active"], "an OS setting never turns Play into Guide"
        assert page.evaluate("document.querySelector('.pl-badge').textContent").startswith("▶ Playing")
        assert errors == []
    finally:
        ctx.close()
    ctx, page, errors, _ = _open(browser, built / DEMO_PAGE, reduced=True)
    try:
        page.wait_for_function("window.__log.length > 0")
        assert page.evaluate("window.__log[0]")["mode"] == "play"
        _wait_pos(page, 1, timeout=3000)
        assert errors == []
    finally:
        ctx.close()


def test_captions_are_announced(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "play", step=1)
        live = page.evaluate("""() => [...document.querySelectorAll('[aria-live]')].map(e => e.textContent).join(' | ')""")
        assert "The host lands on tonight's tables, in time order." in live
        assert page.inner_text(".pl-subtitle") == "The host lands on tonight's tables, in time order."
        _start(page, "demo", "guide", step=2)
        live = page.evaluate("""() => [...document.querySelectorAll('[aria-live]')].map(e => e.textContent).join(' | ')""")
        assert "One link starts a new booking." in live and "Every booking starts here" in live
        assert _shown(page, ".pl-subtitle") == 0, "subtitles are for play mode"
        assert errors == []
    finally:
        ctx.close()


def test_every_player_control_works_by_keyboard(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        page.focus('#plumb-guide [data-tour-start="training"][data-mode="guide"]')
        page.keyboard.press("Enter")
        assert _state(page)["active"] and _state(page)["mode"] == "guide"
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "next"
        page.keyboard.press("Enter")
        assert _state(page)["step"] == 2
        focusable = page.evaluate("""() => [...document.querySelectorAll('.pl-dock button')]
            .filter(b => !b.hidden && b.getClientRects().length).every(b => b.tabIndex >= 0)""")
        assert focusable
        assert errors == []
    finally:
        ctx.close()


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_tours_render_cleanly_in_both_themes_and_widths(browser, built, width: int, scheme: str) -> None:
    ctx, page, errors, requests = _open(browser, built / DEMO_PAGE, width=width, scheme=scheme)
    try:
        page.wait_for_function("window.__log.length > 0")
        assert page.evaluate("document.documentElement.dataset.theme") == scheme
        for pos in (0, 2, 3):
            page.evaluate("(p) => window.plumbPlayer.start('demo', {mode: 'guide', pos: p})", pos)
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            assert overflow <= 0, f"horizontal scroll of {overflow}px at {width}px (pos {pos})"
            box = page.evaluate("JSON.parse(JSON.stringify(document.querySelector('.pl-dock').getBoundingClientRect()))")
            assert box["left"] >= 0 and box["right"] <= width + 0.5, box
        # the dock's own colours follow the theme
        dock_bg = page.evaluate("getComputedStyle(document.querySelector('.pl-dock')).backgroundColor")
        page.click("#theme-toggle")
        assert page.evaluate("getComputedStyle(document.querySelector('.pl-dock')).backgroundColor") != dock_bg
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


def test_guide_panel_shows_the_screen_what_to_do_try_it_and_a_feed(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        panel = page.locator("#plumb-guide")
        assert panel.is_visible()
        text = panel.text_content()
        assert "This screen" in text and "Today's tables" in text and PURPOSE in text
        assert "What you can do" in text and GUIDE_ITEM in text and "Tonight's tables" in text
        page.click('#plumb-guide [data-try="demo"]')
        s = _state(page)
        assert s["tour"] == "demo" and s["mode"] == "guide" and s["step"] == 1
        page.keyboard.press("Escape")
        page.click('.pp-nav [data-nav="menu"]')
        assert "Menü du jour" in page.inner_text("#plumb-guide .pl-feed li:first-child")
        page.click('#pp-toolbar [data-states-for="menu"] [data-set-state="empty"]')
        assert "Empty" in page.inner_text("#plumb-guide .pl-feed li:first-child")
        text = panel.text_content()
        assert "Menü du jour" in text
        page.click('.pp-nav [data-nav="booking"]')
        assert page.locator('#plumb-guide [data-try="demo"]').count() == 1
        assert page.locator('#plumb-guide [data-try="training"]').count() == 1
        page.click('#plumb-guide [data-try="training"]')
        assert _state(page)["tour"] == "training" and _state(page)["step"] == 1
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- review round 1: navigating clicks, focus, polish


OVERLAYS = """() => {
  var s = document.getElementById('pp-stage').getBoundingClientRect();
  return [...document.querySelectorAll('.pl-layer > [data-pl-step]')].map(function (n) {
    var r = n.getBoundingClientRect();
    return {cls: n.getAttribute('class'), left: r.left - s.left, top: r.top - s.top, right: r.right - s.left,
            bottom: r.bottom - s.top, w: s.width, h: s.height};
  });
}"""


@pytest.mark.parametrize("width", [1280, 390])
def test_a_navigating_click_takes_the_steps_marks_with_it(browser, built, width: int) -> None:
    """After step 2's played click opens New booking, nothing of step 2 (callout, arrow) is left at a stale or 0x0 spot
    during the pause after the click."""
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, width=width)
    try:
        page.evaluate("""(js) => { window.__after = []; var get = eval(js);
            setInterval(function () { var s = window.plumbPlayer.state();
              if (s.pos === 3 && window.plumbPrototype.current().screen === 'booking') window.__after.push(get()); }, 20); }""",
                      OVERLAYS)
        _start(page, "demo", "play", step=2)
        _wait_pos(page, 4)
        after = page.evaluate("window.__after")
        assert after, "the pause after the click was sampled"
        for sample in after:
            assert not [o for o in sample if "pl-callout" in o["cls"] or "pl-arrow" in o["cls"]], sample
            for o in sample:
                assert o["left"] >= -1 and o["top"] >= -1 and o["right"] <= o["w"] + 1 and o["bottom"] <= o["h"] + 1, o
        assert errors == []
    finally:
        ctx.close()


def test_overlays_stay_on_the_stage_and_off_hidden_elements(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, width=390)
    try:
        for step in range(1, 7):
            _start(page, "demo", "guide", step=step)
            page.wait_for_timeout(450 if step == 6 else 50)
            for o in page.evaluate(OVERLAYS):
                assert o["left"] >= -1 and o["right"] <= o["w"] + 1 and o["top"] >= -1 and o["bottom"] <= o["h"] + 1, (step, o)
                if "pl-callout" in o["cls"] or "pl-arrow" in o["cls"]:
                    assert o["left"] > 1 or o["top"] > 1, (step, o)
        assert errors == []
    finally:
        ctx.close()


def test_enter_on_next_at_a_navigating_step_keeps_focus_in_the_dock(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=2)
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "next"
        page.keyboard.press("Enter")
        assert _visible_screen(page) == "booking" and _state(page)["pos"] == 4
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "next"
        page.keyboard.press("Enter")
        assert _state(page)["pos"] == 5, "a second Enter still drives the tour"
        assert errors == []
    finally:
        ctx.close()


def test_a_played_navigating_click_keeps_focus_on_pause(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "play", step=2)
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "play"
        _wait_pos(page, 4)
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "play"
        page.keyboard.press(" ")
        assert _state(page)["paused"] is True
        assert errors == []
    finally:
        ctx.close()


def test_autostart_does_not_move_focus_and_the_skip_link_reaches_the_dock(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / DEMO_PAGE)
    try:
        page.wait_for_function("window.__log.length > 0")
        assert page.evaluate("document.activeElement === document.body"), "no focus ring on load"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.textContent") == "Skip to the walkthrough"
        page.keyboard.press("Enter")
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "play"
        assert page.evaluate("location.hash").startswith("#tour-demo")
        page.keyboard.press("Escape")
        assert _shown(page, ".pl-skip") == 0 and page.evaluate("document.querySelector('.pl-skip').hidden")
        assert errors == []
    finally:
        ctx.close()


def test_zoom_never_crops_its_area(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "lesson", "guide", step=2)
        page.wait_for_timeout(450)
        assert page.evaluate("getComputedStyle(document.getElementById('pp-frame')).transform") in ("none", ""), \
            "an area that already fills the screen is not zoomed"
        for width in (1280, 390):
            page.set_viewport_size({"width": width, "height": 900})
            _start(page, "demo", "guide", step=6)
            page.wait_for_timeout(450)
            assert page.evaluate("getComputedStyle(document.getElementById('pp-frame')).transform") not in ("none", "")
            inside = page.evaluate("""() => { var s = document.getElementById('pp-stage').getBoundingClientRect();
                var r = document.querySelector('#pp-frame [data-test=new-booking]').getBoundingClientRect();
                return r.left >= s.left && r.right <= s.right && r.top >= s.top && r.bottom <= s.bottom; }""")
            assert inside, f"the zoomed element stays whole on the stage at {width}px"
        assert errors == []
    finally:
        ctx.close()


def test_default_hint_follows_the_pointing_style_and_blinks_the_target(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "lesson", "guide", step=1)
        page.click('#pp-frame [data-screen="booking"] h2')
        text = page.inner_text(".pl-hint")
        assert "highlighted" not in text and "where the cursor points" in text and "Book the table" in text, text
        assert page.evaluate("document.querySelector('#pp-frame [data-test=save]').classList.contains('pl-attn')")
        assert errors == []
    finally:
        ctx.close()


def test_labels_keep_clear_of_the_badge(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, width=390)
    try:
        _start(page, "demo", "play", step=1)
        page.evaluate("window.plumbPlayer.pause()")
        boxes = page.evaluate("""() => { var b = document.querySelector('.pl-badge').getBoundingClientRect();
            return [...document.querySelectorAll('.pl-label')].map(function (n) { var r = n.getBoundingClientRect();
              return !(r.right <= b.left || r.left >= b.right || r.bottom <= b.top || r.top >= b.bottom); }); }""")
        assert len(boxes) == 2 and not any(boxes), boxes
        assert errors == []
    finally:
        ctx.close()


def test_the_side_rail_ends_above_the_dock(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, width=1280)
    try:
        _start(page, "demo", "guide", step=1)
        page.wait_for_timeout(100)
        rail = page.evaluate("document.getElementById('pp-rail').getBoundingClientRect().bottom")
        dock = page.evaluate("document.querySelector('.pl-dock').getBoundingClientRect().top")
        assert rail <= dock + 1, (rail, dock)
        assert errors == []
    finally:
        ctx.close()


def test_a_broken_tour_does_not_block_map_approve_or_synced(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p")
    page_before = (p / PROTO_REL).read_bytes()
    doc = demo()
    _step(doc).update(screen="bookings")
    put_tour(p, "demo", doc)
    r = run(p, "--approve", "home")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "approved home" in r.stdout
    assert "warning: the pages were not rebuilt" in r.stderr and 'screen "bookings"' in r.stderr and "\nfix: " in r.stderr
    entry = next(s for s in json.loads(read(p / f"{DOCS}/prototype/screens.json"))["screens"] if s["id"] == "home")
    assert entry["approved"] is not None
    assert (p / PROTO_REL).read_bytes() == page_before, "the pages wait for the tour to be fixed"
    for args in (("--synced", "menu"), ("--map", "menu", "--route", "/menu", "--files", "app/menu/**")):
        r = run(p, *args)
        assert r.returncode == 0 and "warning: the pages were not rebuilt" in r.stderr, r.stdout + r.stderr
    assert_refusal(run(p), 'screen "bookings"')
    assert_refusal(run(p, "--check"), 'screen "bookings"')


def test_player_colours_are_tokens_or_named_video_colours() -> None:
    css = read(REPO_TEMPLATES / "player.css")
    head, _sep, rest = css.partition("--pl-video-shadow-strong:")
    assert _sep, "the video colours are defined once, by name"
    body = rest.split("}", 1)[1]
    raw = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|(?<![\w-])(?:white|black)(?![\w-])", body)
    assert raw == [], raw
    assert "--pl-video-ink" in head and "--pl-video-scrim" in head and "--pl-video-dim" in head
