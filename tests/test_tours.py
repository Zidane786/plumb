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
    APP_REL,
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
WALK_PAGE = f"{PAGES_REL}/walk.html"  # the demo tour again, with "view": "prototype"
HOME_REL = f"{DOCS}/prototype/screens/home.html"
REPO_TEMPLATES = Path(__file__).resolve().parents[1] / "plugins/plumb/assets/skill/templates"
BOOKING_REL = f"{DOCS}/prototype/screens/booking.html"
PURPOSE = "See tonight's bookings at a glance and start a new one."
GUIDE_ITEM = "Start a new booking from the link at the top"


def demo() -> dict:
    return json.loads(read(DEMO_SRC))


def walk() -> dict:
    doc = demo()
    doc["view"] = "prototype"
    return doc


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


def test_say_is_optional_text_for_speech_only(tmp_path: Path) -> None:
    doc = demo()
    _step(doc)["say"] = "  Here are   tonight's tables.\n"
    _step(doc, 1)["say"] = ""
    p = make_tour_project(tmp_path / "p", {"demo": doc})
    steps = tours_json(read(p / PROTO_REL))["tours"][0]["steps"]
    assert steps[0]["say"] == "Here are   tonight's tables.", "trimmed like a caption"
    assert steps[0]["caption"] == "The host lands on tonight's tables, in time order.", "the caption on screen stays"
    assert steps[1]["say"] == "" and steps[2]["say"] == "", "no say: the caption is spoken"
    assert "say" not in json.dumps(demo()), "the fixture itself has no say (the default case above)"


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
    "bad-view": (_set(lambda d: d.update(view="slides")), ['view "slides" is not one of app, prototype', '"view": "app"']),
    "view-not-text": (_set(lambda d: d.update(view=True)), ["view true", '"view": "prototype"']),
    "view-wrong-case": (_set(lambda d: d.update(view="App")), ['view "App"']),
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
    "say-not-text": (_set(lambda d: _step(d).update(say=["Hello"])), ["say must be text", '"say": "..."']),
    "say-a-number": (_set(lambda d: _step(d, 1).update(say=7)), ["chapters[0].steps[1].say must be text"]),
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
                             {"demo": demo(), "training": multi, "lesson": lesson, "walk": walk()})


LOG = """
window.__log = [];
document.addEventListener('plumb:tour', function (e) {
  window.__log.push(Object.assign({t: performance.now()}, e.detail));
});
"""


def _open(browser, path: Path, width: int = 1280, scheme: str = "light", hash_: str = "", reduced: bool = False,
          height: int = 900, init: str = ""):
    ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme,
                              reduced_motion="reduce" if reduced else "no-preference")
    page = ctx.new_page()
    errors: list = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    requests: list = []
    page.on("request", lambda req: requests.append(req.url) if not req.url.startswith(("file:", "data:", "about:")) else None)
    page.add_init_script(LOG)
    if init:
        page.add_init_script(init)
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


def _press_start(page) -> None:
    """A tour that opens in play mode with the page waits on its first card: press its Start (without voice)."""
    page.wait_for_function("window.plumbPlayer.state().waiting")
    assert _state(page)["paused"] is True
    page.click(".pl-card-start [data-pl=start-quiet]")
    assert _state(page)["waiting"] is False and _state(page)["paused"] is False


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


# The prototype, the app-view tour page (the default) and the prototype-view tour page each run the same tour.
ON_EVERY_PAGE = pytest.mark.parametrize("rel, tour", [(PROTO_REL, "demo"), (DEMO_PAGE, "demo"), (WALK_PAGE, "walk")])


@ON_EVERY_PAGE
def test_your_turn_waits_for_the_real_click_and_hints_on_a_wrong_one(browser, built, rel: str, tour: str) -> None:
    ctx, page, errors, _ = _open(browser, built / rel)
    try:
        _start(page, tour, "guide", step=3)
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
    # the app view (the default): no panels; leaving the tour leaves the app where it is, on its #/ID routes
    ctx, page, errors, requests = _open(browser, built / DEMO_PAGE)
    try:
        page.wait_for_function("window.__log.length > 0")
        first = page.evaluate("window.__log[0]")
        assert first["tour"] == "demo" and first["mode"] == "play" and first["pos"] == 0
        assert page.evaluate("window.plumbPrototype.view") == "app"
        assert _shown(page, ".pp-side") == 0 and _shown(page, "#pp-rail") == 0 and _shown(page, "#theme-toggle") == 0
        _press_start(page)
        _wait_pos(page, 1, timeout=3000)
        page.keyboard.press("Escape")
        assert _state(page)["active"] is False
        assert page.evaluate("location.hash") == "#/home", "leaving names the screen in the app's own route"
        page.evaluate("window.plumbPrototype.go('menu')")
        assert _visible_screen(page) == "menu", "viewers can leave the tour and click around"
        assert page.evaluate("location.pathname").endswith("/tours/demo.html")
        assert page.evaluate("location.hash") == "#/menu"
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()
    # the prototype view: today's page, with the screens list
    ctx, page, errors, requests = _open(browser, built / WALK_PAGE)
    try:
        page.wait_for_function("window.__log.length > 0")
        first = page.evaluate("window.__log[0]")
        assert first["tour"] == "walk" and first["mode"] == "play" and first["pos"] == 0
        _press_start(page)
        _wait_pos(page, 1, timeout=3000)
        page.keyboard.press("Escape")
        assert _state(page)["active"] is False
        page.click('.pp-nav [data-nav="menu"]')
        assert _visible_screen(page) == "menu", "viewers can leave the tour and click around"
        assert page.evaluate("location.pathname").endswith("/tours/walk.html")
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
        _press_start(page)
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
@pytest.mark.parametrize("tour", ["demo", "walk"])
def test_tours_render_cleanly_in_both_themes_and_widths(browser, built, width: int, scheme: str, tour: str) -> None:
    ctx, page, errors, requests = _open(browser, built / f"{PAGES_REL}/{tour}.html", width=width, scheme=scheme)
    try:
        page.wait_for_function("window.__log.length > 0")
        assert page.evaluate("document.documentElement.dataset.theme") == scheme
        for pos in (0, 2, 3):
            page.evaluate("([t, p]) => window.plumbPlayer.start(t, {mode: 'guide', pos: p})", [tour, pos])
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            assert overflow <= 0, f"horizontal scroll of {overflow}px at {width}px (pos {pos})"
            box = page.evaluate("JSON.parse(JSON.stringify(document.querySelector('.pl-dock').getBoundingClientRect()))")
            assert box["left"] >= 0 and box["right"] <= width + 0.5, box
        # the dock's own colours follow the theme
        dock_bg = page.evaluate("getComputedStyle(document.querySelector('.pl-dock')).backgroundColor")
        if tour == "walk":
            page.click("#theme-toggle")
        else:  # the app view has no toggle of its own: a screen's toggle calls this
            page.evaluate("window.plumbTheme.toggle()")
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


# ---------------------------------------------------------------- the player stays on top and can get out of the way

LAYERS_REL = f"{DOCS}/prototype/screens/layers.html"
LONG_REL = f"{DOCS}/prototype/screens/long.html"
BOXES_REL = f"{DOCS}/prototype/screens/boxes.html"
# A screen with its own stacking (a fixed scrim at z-index 60, a dialog at 9999); a target selector that matches an
# element hidden by visibility (itself, or through its parent) and one pushed off the frame before the one shown;
# targets an inner scroller has scrolled away (a wide table's far column, the last item of a fixed-height list); a
# display: contents wrapper; a custom text widget (role=textbox); and a state with a fixed toast.
LIST_ITEMS = "".join(f"<li>Item {i}</li>" for i in range(1, 40)) + '<li class="last">The last item</li>'
LAYERS = """<style>
[data-screen="layers"] { position: relative; padding: var(--spacing-6) var(--spacing-4); }
[data-screen="layers"] .scrim { position: fixed; inset: 0; z-index: 60; background: var(--color-scrim); }
[data-screen="layers"] .dialog-box { position: absolute; left: var(--spacing-4); right: var(--spacing-4);
  top: var(--spacing-6); z-index: 9999; padding: var(--spacing-6); background: var(--color-surface); }
[data-screen="layers"] .gone { visibility: hidden; }
[data-screen="layers"] .away { position: absolute; left: 0; top: 0; transform: translateX(-200%); }
[data-screen="layers"] .wide { overflow-x: auto; max-width: 100%; }
[data-screen="layers"] .wide table { width: 3000px; }
[data-screen="layers"] .list { height: 120px; overflow-y: auto; margin: 0; padding: 0; list-style: none; }
[data-screen="layers"] .list li { padding: var(--spacing-2); }
[data-screen="layers"] .contents-wrap { display: contents; }
[data-screen="layers"] .toast { position: fixed; right: var(--spacing-4); bottom: var(--spacing-4);
  padding: var(--spacing-3); background: var(--color-surface); }
</style>
<section data-screen="layers" data-title="Layers" data-order="4">
  <h2>Layers</h2>
  <div data-state="ready">
    <a href="#screen-home" class="go gone" data-test="hidden-go">Hidden</a>
    <div class="gone"><a href="#screen-home" class="go" data-test="hidden-parent-go">Inside hidden</a></div>
    <a href="#screen-home" class="go away" data-test="away-go">Away</a>
    <p><a href="#screen-home" class="go" data-test="shown-go">Shown</a></p>
    <div class="wide"><table><tr><td>First column</td><td>Middle column</td><td class="far">Far column</td></tr></table></div>
    <ul class="list">""" + LIST_ITEMS + """</ul>
    <div class="contents-wrap"><p class="inside">Inside a display: contents wrapper</p></div>
    <div class="rtb" role="textbox" tabindex="0" aria-label="Notes">Notes</div>
  </div>
  <div data-state="dialog">
    <div class="scrim"></div>
    <div class="dialog-box" role="dialog" aria-label="A dialog"><p>The dialog</p></div>
  </div>
  <div data-state="toast">
    <p><span class="zoom-me">Zoom</span></p>
    <div class="toast" role="status">Saved</div>
  </div>
</section>
"""
# A tall screen: a label at its top and one in its middle, a centred fixed dialog in one state, and a dialog that is on
# show in every state.
LONG = """<style>
[data-screen="long"] { padding: var(--spacing-6) var(--spacing-4); }
[data-screen="long"] .long { min-height: 4000px; }
[data-screen="long"] .mid { margin-top: 1800px; }
[data-screen="long"] .modal { position: fixed; left: 50%; top: 50%; transform: translate(-50%, -50%);
  padding: var(--spacing-6); background: var(--color-surface); }
</style>
<section data-screen="long" data-title="Long page" data-order="5">
  <h2>Long page</h2>
  <div data-state="ready">
    <div class="long"><p class="first">The first thing</p><p class="mid">In the middle</p><p>More below</p></div>
  </div>
  <div data-state="dialog">
    <div class="long"><p class="first">Under the dialog</p></div>
    <div class="modal" role="dialog" aria-modal="true" aria-label="Confirm"><p>Are you sure?</p></div>
  </div>
  <div data-state="plain">
    <div class="long"><p class="first">Nothing opens here</p></div>
  </div>
  <aside class="always" role="dialog" aria-label="Always on show"><p>Always here</p></aside>
</section>
"""

# Targets and labels that share a scroller: a wide table, a 120 px list, a tall area inside a scrolling main, and a
# fixed drawer pushed off the frame inside a box that scrolls sideways (the box must never move for it).
BOX_ITEMS = "".join(f'<li class="i{i}">Item {i}</li>' for i in range(1, 41))
BOXES = """<style>
[data-screen="boxes"] { padding: var(--spacing-6) var(--spacing-4); }
[data-screen="boxes"] .wide2 { overflow-x: auto; max-width: 100%; }
[data-screen="boxes"] .wide2 table { width: 3000px; }
[data-screen="boxes"] .list2 { height: 120px; overflow-y: auto; margin: 0; padding: 0; list-style: none; }
[data-screen="boxes"] .list2 li { padding: var(--spacing-2); }
[data-screen="boxes"] .main { height: 500px; overflow-y: auto; }
[data-screen="boxes"] .tallin { min-height: 4000px; }
[data-screen="boxes"] .midin { margin-top: 2000px; }
[data-screen="boxes"] .box { height: 100px; overflow: auto; }
[data-screen="boxes"] .box .roomy { width: 2000px; }
[data-screen="boxes"] .drawer { position: fixed; right: 0; top: 0; transform: translateX(110%); }
[data-screen="boxes"] .drawer100 { position: fixed; right: 0; top: 0; transform: translateX(100%); }
[data-screen="boxes"] .acc { max-height: 0; overflow: hidden; }
[data-screen="boxes"] .track { height: 40px; overflow: hidden; }
[data-screen="boxes"] .track .off { margin-top: 60px; }
</style>
<section data-screen="boxes" data-title="Boxes" data-order="6">
  <h2>Boxes</h2>
  <div data-state="ready">
    <div class="wide2"><table><tr><td class="c1">One</td><td class="c2">Two</td><td class="c3">Far</td></tr></table></div>
    <ul class="list2">""" + BOX_ITEMS + """</ul>
    <div class="main"><div class="tallin"><p class="topin">Top</p><p class="midin">Halfway</p></div></div>
    <div class="box"><nav class="drawer slide">Drawer</nav><p class="roomy">Wide content</p></div>
    <p><span class="slide">The visible one</span></p>
    <div class="acc"><p class="card">In a collapsed accordion</p></div>
    <div class="track"><p class="slide-a">Shown slide</p><p class="card off">The next slide, clipped</p></div>
    <p class="card">The visible card</p>
    <nav class="drawer100 slide3">A drawer moved off by exactly its width</nav>
    <p><span class="slide3">The visible fallback</span></p>
  </div>
</section>
"""


def staged_tour() -> dict:
    return {"title": "Layers and lengths", "audience": "review",
            "intro": {"title": "Stacking", "text": "A card that stays in view."},
            "steps": [
                {"screen": "layers", "state": "dialog", "title": "Over the dialog",
                 "caption": "The dialog sits under the player.", "target": ".dialog-box", "point": "ring"},
                {"screen": "layers", "state": "ready", "title": "The shown link", "caption": "Only the visible one.",
                 "target": ".go", "point": "ring"},
                {"screen": "long", "title": "A tall area", "caption": "Taller than the window.", "target": ".long",
                 "point": "ring", "labels": [{"target": ".long .first", "text": "First"}]},
                {"screen": "long", "title": "A tall area, no labels", "caption": "Nearest.", "target": ".long",
                 "point": "ring"},
                {"screen": "layers", "state": "ready", "title": "The far column", "caption": "Scrolled sideways.",
                 "target": ".wide .far", "point": "ring"},
                {"screen": "layers", "state": "ready", "title": "The last item", "caption": "Scrolled down the list.",
                 "target": ".list .last", "point": "ring"},
                {"screen": "layers", "state": "ready", "title": "A wrapper", "caption": "It has no box of its own.",
                 "target": ".contents-wrap", "point": "ring"},
                {"screen": "layers", "state": "toast", "title": "The toast", "caption": "A fixed toast.",
                 "target": ".toast", "point": "ring"},
                {"screen": "layers", "state": "toast", "title": "Zoom", "caption": "Closer.", "target": ".zoom-me",
                 "point": "zoom"},
                {"screen": "long", "title": "A label in the middle", "caption": "Halfway down.", "target": ".long",
                 "point": "ring", "labels": [{"target": ".long .mid", "text": "Middle"}]},
                {"screen": "boxes", "title": "Two columns", "caption": "Labels on the first and the far column.",
                 "target": ".wide2", "point": "ring",
                 "labels": [{"target": ".wide2 .c1", "text": "One"}, {"target": ".wide2 .c3", "text": "Far"}]},
                {"screen": "boxes", "title": "A short list", "caption": "The first item and the last.",
                 "target": ".list2 .i1", "point": "ring",
                 "labels": [{"target": ".list2 .i1", "text": "A"}, {"target": ".list2 .i40", "text": "B"}]},
                {"screen": "boxes", "title": "A scrolling main", "caption": "Tall, with a label halfway.",
                 "target": ".tallin", "point": "ring", "labels": [{"target": ".tallin .midin", "text": "Mid"}]},
                {"screen": "boxes", "title": "A drawer", "caption": "The drawer is off the frame.",
                 "target": ".slide", "point": "ring"},
                {"screen": "boxes", "title": "A card", "caption": "Clipped matches come first.",
                 "target": ".card", "point": "ring"},
                {"screen": "boxes", "title": "Another drawer", "caption": "Moved off by 100%.",
                 "target": ".slide3", "point": "ring"},
            ]}


@pytest.fixture(scope="module")
def staged(tmp_path_factory) -> Path:
    p = make_tour_project(tmp_path_factory.mktemp("staged") / "Stage Ünïcode",
                          {"demo": demo(), "staged": staged_tour()}, build=False)
    write(p / LAYERS_REL, LAYERS)
    write(p / LONG_REL, LONG)
    write(p / BOXES_REL, BOXES)
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    return p


# What paints on top at the node's centre (the overlay layer takes no clicks, so it is made hit-testable for the probe).
ON_TOP = """(sel) => { var n = document.querySelector(sel); var r = n.getBoundingClientRect();
  var layer = n.closest('.pl-layer'); if (layer) layer.style.pointerEvents = 'auto';
  var hit = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 6));
  if (layer) layer.style.pointerEvents = '';
  return !!hit && (hit === n || n.contains(hit)); }"""


def test_a_screens_own_layers_never_cover_the_player(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=1)
        page.wait_for_timeout(100)
        assert _shown(page, '#pp-frame [data-screen="layers"] .scrim') == 1
        assert page.evaluate(ON_TOP, ".pl-dock [data-pl=next]"), "the dock is under the screen's z-index 60 layer"
        assert page.evaluate(ON_TOP, ".pl-dock-top [data-pl=hide]")
        _start(page, "staged", "play", step=1)
        page.evaluate("window.plumbPlayer.pause()")
        assert page.evaluate(ON_TOP, ".pl-subtitle"), "the subtitle is under the screen's layer"
        assert page.evaluate(ON_TOP, ".pl-badge")
        assert errors == []
    finally:
        ctx.close()


def test_find_skips_hidden_and_off_frame_targets(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=2)
        page.wait_for_timeout(100)
        rings = page.evaluate("""() => [...document.querySelectorAll('.pl-ring')].map(function (n) {
            var r = n.getBoundingClientRect(); return [r.left + 4, r.top + 4, r.width - 8, r.height - 8]; })""")
        shown = page.evaluate("""() => { var r = document.querySelector('#pp-frame [data-test=shown-go]')
            .getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }""")
        assert len(rings) == 1 and all(abs(a - b) <= 1 for a, b in zip(rings[0], shown)), (rings, shown)
        assert errors == []
    finally:
        ctx.close()


LABEL_IN_VIEW = """() => { var r = document.querySelector('.pl-label').getBoundingClientRect();
    var d = document.querySelector('.pl-dock').getBoundingClientRect();
    return {top: r.top, bottom: r.bottom, dock: d.top}; }"""


@pytest.mark.parametrize("width, smooth", [(1280, False), (390, False), (1280, True)])
def test_a_tall_labelled_target_keeps_its_first_label_in_view(browser, staged, width: int, smooth: bool) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL, width=width)
    try:
        if smooth:  # every scroll the player makes is instant, whatever the page's scroll-behavior
            page.evaluate("document.documentElement.style.scrollBehavior = 'smooth'")
        page.evaluate("window.plumbPrototype.go('long'); window.scrollTo({top: 2500, behavior: 'instant'})")
        _start(page, "staged", "guide", step=3)
        label = page.evaluate(LABEL_IN_VIEW)
        assert label["top"] >= 0 and label["bottom"] <= label["dock"], label
        assert page.evaluate(ON_TOP, ".pl-label"), "the first label is covered"
        # no labels: the nearest edge, so a tall area that already fills the view does not jump
        before = page.evaluate("window.scrollY")
        page.click(".pl-dock [data-pl=next]")
        assert page.evaluate("window.scrollY") == before
        # a label halfway down a tall target comes into view (it cannot share the window with the target's top)
        _start(page, "staged", "guide", step=10)
        label = page.evaluate(LABEL_IN_VIEW)
        assert label["top"] >= 0 and label["bottom"] <= label["dock"], label
        assert page.inner_text(".pl-label") == "Middle"
        assert errors == []
    finally:
        ctx.close()


CARD_IN_VIEW = """() => { var r = document.querySelector('.pl-card-box').getBoundingClientRect();
    var d = document.querySelector('.pl-dock').getBoundingClientRect();
    return r.height > 0 && r.top >= 0 && r.bottom <= d.top; }"""


def test_a_title_card_stays_in_the_viewport_on_a_long_page(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        page.evaluate("window.plumbPrototype.go('long'); window.scrollTo(0, 3000)")
        _start(page, "staged", "guide")
        assert _state(page)["card"] == "intro"
        assert page.evaluate(CARD_IN_VIEW), "the card is off screen when the tour starts scrolled down"
        for y in (0, 2000):
            page.evaluate("(y) => window.scrollTo(0, y)", y)
            page.wait_for_timeout(50)
            assert page.evaluate(CARD_IN_VIEW), f"the card scrolled away with the page (scrolled to {y})"
        assert errors == []
    finally:
        ctx.close()


def _dock_shown(page) -> bool:
    return _shown(page, ".pl-dock") == 1


def _pill(page) -> dict:
    return page.evaluate("""() => { var p = document.querySelector('.pl-pill'); var t = p.querySelector('.pl-pill-title');
        return {shown: !p.hidden && p.getClientRects().length > 0,
                title: t && !t.hidden && t.getClientRects().length ? t.textContent : '',
                button: p.querySelector('[data-pl=show]').textContent}; }""")


@ON_EVERY_PAGE
def test_hide_panel_button_and_pill_in_guide_mode(browser, built, rel: str, tour: str) -> None:
    ctx, page, errors, _ = _open(browser, built / rel)
    try:
        _start(page, tour, "guide", step=1)
        assert _dock_shown(page) and not _pill(page)["shown"]
        assert page.inner_text(".pl-dock-top [data-pl=hide]") == "Hide panel"
        page.click(".pl-dock [data-pl=hide]")
        assert not _dock_shown(page)
        pill = _pill(page)
        assert pill["shown"] and pill["title"] == "Tonight's tables" and pill["button"] == "Show panel", pill
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "show"
        page.keyboard.press("ArrowRight")
        assert _state(page)["step"] == 2 and _pill(page)["title"] == "Start a booking", "the pill follows the step"
        page.click(".pl-pill [data-pl=show]")
        assert _dock_shown(page) and not _pill(page)["shown"]
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "hide"
        page.click(".pl-dock [data-pl=hide]")
        page.keyboard.press("Escape")
        assert not _dock_shown(page) and not _pill(page)["shown"], "leaving takes the pill with it"
        assert errors == []
    finally:
        ctx.close()


def test_hide_panel_in_play_mode_keeps_the_subtitle(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "play", step=1)
        page.evaluate("window.plumbPlayer.pause()")
        page.evaluate("document.activeElement.blur()")
        page.keyboard.press("h")
        assert not _dock_shown(page)
        pill = _pill(page)
        assert pill["shown"] and pill["title"] == "" and pill["button"] == "Show panel", pill
        assert _shown(page, ".pl-subtitle") == 1
        place = page.evaluate("""() => { var s = document.querySelector('.pl-subtitle').getBoundingClientRect();
            var p = document.querySelector('.pl-pill').getBoundingClientRect(); return {sub: s.bottom, pill: p.top}; }""")
        assert place["sub"] <= place["pill"], place
        page.evaluate("window.plumbPlayer.resume()")
        _wait_pos(page, 2)
        assert _shown(page, ".pl-subtitle") == 1 and not _dock_shown(page), "play keeps narrating with the panel hidden"
        page.keyboard.press("h")
        assert _dock_shown(page)
        assert errors == []
    finally:
        ctx.close()


def test_the_h_key_is_ignored_while_typing_or_with_modifiers(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "training", "guide", step=2)
        page.click("#pp-frame [data-test=guest]")
        page.keyboard.press("h")
        assert _dock_shown(page), "typing an h in a field does not hide the panel"
        assert "h" in page.evaluate("document.querySelector('#pp-frame [data-test=guest]').value")
        page.evaluate("document.activeElement.blur()")
        for combo in ("Shift+H", "Alt+h", "Control+h", "Meta+h"):
            page.keyboard.press(combo)
            assert _dock_shown(page), combo
        page.keyboard.press("h")
        assert not _dock_shown(page)
        page.keyboard.press("h")
        assert _dock_shown(page)
        page.keyboard.press("Escape")
        page.keyboard.press("h")
        assert not _dock_shown(page) and not _pill(page)["shown"], "no tour, no panel to hide"
        _start(page, "training", "guide", step=2)
        assert _dock_shown(page), "an h with no tour running changes nothing"
        assert errors == []
    finally:
        ctx.close()


def test_hide_panel_is_remembered_across_reloads(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=1)
        page.click(".pl-dock [data-pl=hide]")
        page.reload()
        page.wait_for_load_state("load")
        _start(page, "demo", "guide", step=1)
        assert not _dock_shown(page) and _pill(page)["shown"], "the hidden panel stays hidden"
        page.click(".pl-pill [data-pl=show]")
        page.reload()
        page.wait_for_load_state("load")
        _start(page, "demo", "guide", step=1)
        assert _dock_shown(page) and not _pill(page)["shown"]
        assert errors == []
    finally:
        ctx.close()


THROWING_STORAGE = """
Object.defineProperty(window, 'localStorage', { configurable: true,
  get: function () { throw new Error('storage is off'); } });
"""


def test_hide_panel_works_when_storage_throws(browser, built) -> None:
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors: list = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(THROWING_STORAGE)
    try:
        page.goto((built / PROTO_REL).resolve().as_uri())
        page.wait_for_load_state("load")
        _start(page, "demo", "guide", step=1)
        assert _dock_shown(page)
        page.click(".pl-dock [data-pl=hide]")
        assert not _dock_shown(page) and _pill(page)["shown"]
        page.click(".pl-pill [data-pl=show]")
        assert _dock_shown(page)
        assert errors == []
    finally:
        ctx.close()


def _frame_width(page) -> float:
    return page.evaluate("document.getElementById('pp-frame').getBoundingClientRect().width")


@pytest.mark.parametrize("width", [1440, 1280])
def test_the_side_columns_collapse_while_a_tour_runs(browser, built, width: int) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, width=width)
    try:
        before = _frame_width(page)
        assert _shown(page, ".pp-side") == 1 and _shown(page, "#pp-rail") == 1
        _start(page, "demo", "guide", step=1)
        page.wait_for_timeout(50)
        assert _shown(page, ".pp-side") == 0 and _shown(page, "#pp-rail") == 0
        assert _frame_width(page) >= 768, _frame_width(page)
        page.keyboard.press("Escape")
        page.wait_for_timeout(50)
        assert _shown(page, ".pp-side") == 1 and _shown(page, "#pp-rail") == 1, "they come back when the tour ends"
        assert abs(_frame_width(page) - before) <= 1
        assert errors == []
    finally:
        ctx.close()


def test_the_standalone_tour_page_collapses_the_columns_too(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / WALK_PAGE, width=1440)
    try:
        page.wait_for_function("window.__log.length > 0")
        assert _shown(page, ".pp-side") == 0 and _shown(page, "#pp-rail") == 0 and _frame_width(page) >= 768
        assert errors == []
    finally:
        ctx.close()


CHROME = """() => { var probe = document.createElement('span');
  probe.style.color = 'var(--color-primary, rgb(1, 2, 3))'; document.body.appendChild(probe);
  var want = getComputedStyle(probe).color; probe.remove();
  var dock = getComputedStyle(document.querySelector('.pl-dock'));
  return {button: getComputedStyle(document.querySelector('.pl-dock [data-pl=next]')).backgroundColor, primary: want,
          radius: dock.borderTopLeftRadius, font: dock.fontFamily}; }"""


def _chrome(browser, project: Path, scheme: str) -> dict:
    ctx, page, errors, _ = _open(browser, project / PROTO_REL, scheme=scheme)
    try:
        _start(page, "demo", "guide", step=1)
        out = page.evaluate(CHROME)
        assert errors == []
        return out
    finally:
        ctx.close()


def _tour_project(dest: Path, mutate) -> Path:
    p = make_project(dest, build=False, mutate=mutate)
    put_tour(p, "demo", demo())
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    return p


def _with_lg(doc: dict) -> None:
    doc["radius"]["lg"] = {"$value": "20px"}


def _no_accent(doc: dict) -> None:
    for name in ("primary", "on-primary", "link"):
        doc["color"].pop(name, None)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_player_chrome_takes_the_projects_tokens(browser, tmp_path: Path, scheme: str) -> None:
    got = _chrome(browser, _tour_project(tmp_path / "with", _with_lg), scheme)
    assert got["button"] == got["primary"] and got["primary"] != "rgb(1, 2, 3)", got
    assert got["radius"] == "20px", got
    got = _chrome(browser, _tour_project(tmp_path / "without", _no_accent), scheme)
    assert got["primary"] == "rgb(1, 2, 3)", "this project has no primary colour"
    assert got["button"] == ("rgb(47, 93, 138)" if scheme == "light" else "rgb(141, 184, 227)"), got
    assert got["radius"] == "14px", got


def test_the_shell_maps_the_player_roles_to_format_names_with_todays_fallbacks() -> None:
    roles = read(REPO_TEMPLATES / "chrome-roles.css")
    shell = read(REPO_TEMPLATES / "prototype-shell.html.tmpl")
    for line in ("--pl-accent: var(--color-primary, #2f5d8a);", "--pl-accent: var(--color-primary, #8db8e3);",
                 "--pl-on-accent: var(--color-on-primary, #ffffff);", "--pl-surface: var(--color-surface, #ffffff);",
                 "--pl-surface: var(--color-surface, #1a1c1f);", "--pl-border: var(--color-outline, #dcdcd6);",
                 "--pl-font: var(--font-sans, system-ui", "--pl-mono: var(--font-mono, ui-monospace",
                 "--pl-radius: var(--radius-md, 8px);", "--pl-shadow-lg: var(--shadow-popover, "):
        assert line in roles, line
    assert re.search(r"\.pp-frame \{[^}]*isolation: isolate", shell)
    assert re.search(r"\.pp-frame \{[^}]*contain: layout", shell)
    css = read(REPO_TEMPLATES / "player.css")
    assert "isolation: isolate" in css and "var(--radius-lg, 14px)" in css
    # the window is the app view's frame: the player must not make #pp-frame a containing block there
    assert "contain:" not in css


# ---------------------------------------------------------------- review round 1: scrollers, fixed layers, hidden panel

RINGS = """() => [...document.querySelectorAll('.pl-ring')].map(function (n) {
    var r = n.getBoundingClientRect(); return [r.left + 4, r.top + 4, r.width - 8, r.height - 8]; })"""
RECT = """(sel) => { var r = document.querySelector(sel).getBoundingClientRect();
    return [r.left, r.top, r.width, r.height]; }"""
IN_WINDOW = """(sel) => { var r = document.querySelector(sel).getBoundingClientRect();
    var f = document.getElementById('pp-frame').getBoundingClientRect();
    return r.left >= f.left - 1 && r.left < f.right && r.top >= 0 && r.bottom <= window.innerHeight; }"""


def _ringed(page, sel: str) -> None:
    rings, want = page.evaluate(RINGS), page.evaluate(RECT, sel)
    assert len(rings) == 1 and all(abs(a - b) <= 1 for a, b in zip(rings[0], want)), (sel, rings, want)


@pytest.mark.parametrize("step, sel, width, smooth", [
    (5, "#pp-frame .wide .far", 1280, False), (6, "#pp-frame .list .last", 1280, False),
    (5, "#pp-frame .wide .far", 390, True), (6, "#pp-frame .list .last", 390, True)])
def test_a_target_scrolled_away_inside_an_inner_scroller_is_brought_in(browser, staged, step: int, sel: str, width: int,
                                                                        smooth: bool) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL, width=width)
    try:
        if smooth:  # a reset's smooth scrolling on every box: the player's own scrolls stay instant
            page.add_style_tag(content="* { scroll-behavior: smooth !important; }")
        _start(page, "staged", "guide", step=step)
        _ringed(page, sel)
        assert page.evaluate(IN_WINDOW, sel), f"{sel} is not in view"
        _start(page, "staged", "guide", step=2)
        _ringed(page, "#pp-frame [data-test=shown-go]")  # an off-canvas drawer is still skipped
        assert errors == []
    finally:
        ctx.close()


def test_a_display_contents_target_uses_its_first_rendered_child(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=7)
        _ringed(page, "#pp-frame .contents-wrap .inside")
        assert errors == []
    finally:
        ctx.close()


def test_a_fixed_scrim_stays_inside_the_frame(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL, hash_="#screen-layers/dialog")
    try:
        scrim = page.evaluate(RECT, '#pp-frame [data-screen="layers"] .scrim')
        frame = page.evaluate(RECT, "#pp-frame")
        assert all(abs(a - b) <= 2 for a, b in zip(scrim, frame)), (scrim, frame)
        for sel in ("#pp-viewport [data-viewport=phone]", '#pp-toolbar [data-states-for="layers"] [data-set-state="ready"]',
                    ".pp-side [data-nav]"):
            assert page.evaluate(ON_TOP, sel), f"{sel} is covered by the screen's scrim"
        page.click('.pp-side [data-nav="home"]')
        assert _visible_screen(page) == "home"
        assert errors == []
    finally:
        ctx.close()


def test_a_fixed_toast_in_the_phone_frame_is_pointed_at_and_zoom_keeps_it_in_place(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        page.evaluate("window.plumbPrototype.setViewport('phone')")
        _start(page, "staged", "guide", step=8)
        _ringed(page, "#pp-frame .toast")
        inside = """() => { var t = document.querySelector('#pp-frame .toast').getBoundingClientRect();
            var f = document.getElementById('pp-frame').getBoundingClientRect();
            return t.left >= f.left && t.right <= f.right && t.top >= f.top && t.bottom <= f.bottom; }"""
        assert page.evaluate(inside), "the toast sits inside the phone frame"
        _start(page, "staged", "guide", step=9)
        page.wait_for_timeout(500)
        assert page.evaluate("getComputedStyle(document.getElementById('pp-frame')).transform") not in ("none", "")
        assert page.evaluate(inside), "a zoom step's transform does not move a fixed toast out of the frame"
        assert errors == []
    finally:
        ctx.close()


def test_a_state_change_that_opens_a_dialog_scrolls_it_into_view(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL, hash_="#screen-long")
    try:
        switch = '#pp-toolbar [data-states-for="long"] [data-set-state="{}"]'
        assert page.evaluate("window.scrollY") == 0
        page.click(switch.format("dialog"))
        box = page.evaluate(RECT, '#pp-frame [data-screen="long"] .modal')
        assert box[1] >= 0 and box[1] + box[3] <= 900, box
        # a dialog that was already on show (the aside in every state) never moves the page
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        page.click(switch.format("ready"))
        page.click(switch.format("plain"))
        assert page.evaluate("window.scrollY") == 0
        assert errors == []
    finally:
        ctx.close()


def test_with_the_panel_hidden_a_your_turn_hint_brings_it_back_for_that_step(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "lesson", "guide", step=1)
        page.click(".pl-dock [data-pl=hide]")
        assert not _dock_shown(page) and _shown(page, ".pl-pill [data-pl=do]") == 1, "Do it for me stays reachable"
        page.click('#pp-frame [data-screen="booking"] h2')
        assert _dock_shown(page) and _shown(page, ".pl-hint") == 1
        hint = page.inner_text(".pl-hint")
        assert "Book the table" in hint and hint in page.inner_text(".pl-live"), "the hint is shown and announced"
        page.click(".pl-dock [data-pl=do]")
        _wait_pos(page, 1)
        assert not _dock_shown(page) and _pill(page)["shown"], "the next step keeps the viewer's choice"
        assert errors == []
    finally:
        ctx.close()


def test_the_pills_do_it_for_me_advances_a_your_turn_step(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "lesson", "guide", step=1)
        page.keyboard.press("h")
        page.click(".pl-pill [data-pl=do]")
        _wait_pos(page, 1)
        assert _shown(page, ".pl-pill [data-pl=do]") == 0, "only a your-turn step offers it"
        assert errors == []
    finally:
        ctx.close()


def test_the_end_of_play_brings_the_panel_back_for_play_again(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "lesson", "play", speed=2)
        page.click(".pl-dock [data-pl=hide]")
        page.wait_for_function("window.plumbPlayer.state().ended", timeout=15000)
        assert _dock_shown(page) and page.inner_text(".pl-dock [data-pl=play]") == "Play again"
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "play"
        page.click(".pl-dock [data-pl=play]")
        assert not _dock_shown(page) and _pill(page)["shown"], "playing again keeps the viewer's choice"
        assert errors == []
    finally:
        ctx.close()


def test_hide_and_show_say_what_they_control(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "demo", "guide", step=1)
        attrs = """(sel) => { var b = document.querySelector(sel);
            return [b.getAttribute('aria-controls'), b.getAttribute('aria-expanded')]; }"""
        assert page.evaluate(attrs, ".pl-dock [data-pl=hide]") == ["pl-dock", "true"]
        assert page.evaluate(attrs, ".pl-pill [data-pl=show]") == ["pl-dock", "false"]
        assert page.evaluate("document.getElementById('pl-dock') === document.querySelector('.pl-dock')")
        labels = page.evaluate("[document.querySelector('.pl-dock').getAttribute('aria-label'), "
                               "document.querySelector('.pl-pill').getAttribute('aria-label')]")
        assert labels[0] != labels[1] and "hidden" in labels[1], labels
        assert errors == []
    finally:
        ctx.close()


def test_holding_h_toggles_once_and_custom_text_widgets_count_as_typing(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=2)
        page.evaluate("document.activeElement.blur()")
        page.keyboard.down("h")
        page.keyboard.down("h")  # a held key repeats
        page.keyboard.down("h")
        page.keyboard.up("h")
        assert not _dock_shown(page), "holding H hides the panel once"
        page.keyboard.press("h")
        assert _dock_shown(page)
        page.focus("#pp-frame .rtb")
        page.keyboard.press("h")
        page.keyboard.press("ArrowRight")
        assert _dock_shown(page) and _state(page)["step"] == 2, "a role=textbox widget is typing"
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- review round 2: judging never scrolls


def _label_on(page, text: str, sel: str) -> bool:
    """The label sits over the element it names (its left edge between the element's left edge, less the 6 px nudge,
    and its right edge)."""
    return page.evaluate("""([text, sel]) => { var l = [...document.querySelectorAll('.pl-label')]
        .find(function (n) { return n.textContent === text; });
      if (!l) return false;
      var r = l.getBoundingClientRect(), t = document.querySelector(sel).getBoundingClientRect();
      return r.left >= t.left - 8 && r.left <= t.right; }""", [text, sel])


def _labels(page) -> list:
    return page.evaluate("[...document.querySelectorAll('.pl-label')].map(n => n.textContent)")


def test_labels_sharing_a_wide_table_sit_on_their_own_column_or_are_left_out(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=11)
        assert page.evaluate("document.querySelector('#pp-frame .wide2').scrollLeft") == 0
        assert _labels(page) == ["One"], "the far column's label is left out while its column is scrolled away"
        assert _label_on(page, "One", "#pp-frame .wide2 .c1")
        assert errors == []
    finally:
        ctx.close()


def test_a_ring_and_label_in_a_short_list_stay_on_the_first_item(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=12)
        assert page.evaluate("document.querySelector('#pp-frame .list2').scrollTop") == 0
        _ringed(page, "#pp-frame .list2 .i1")
        assert _labels(page) == ["A"] and _label_on(page, "A", "#pp-frame .list2 .i1")
        assert errors == []
    finally:
        ctx.close()


def test_a_tall_target_in_a_scrolling_main_is_ringed_where_it_is(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=13)
        _ringed(page, "#pp-frame .tallin")
        # main brings the target's top edge in (its nearest edge), never on to the label halfway down
        assert page.evaluate("document.querySelector('#pp-frame .main').scrollTop") < 100
        assert _labels(page) == [], "the label is scrolled away inside main, so it is left out"
        assert errors == []
    finally:
        ctx.close()


def test_a_fixed_drawer_off_the_frame_does_not_scroll_the_box_it_sits_in(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=14)
        _ringed(page, '#pp-frame [data-screen="boxes"] p > .slide')
        assert page.evaluate("document.querySelector('#pp-frame .box').scrollLeft") == 0
        assert errors == []
    finally:
        ctx.close()


def test_a_redraw_never_undoes_the_viewers_own_scrolling(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=6)
        assert page.evaluate("document.querySelector('#pp-frame .list').scrollTop") > 0
        page.evaluate("document.querySelector('#pp-frame .list').scrollTop = 0")
        page.set_viewport_size({"width": 1270, "height": 900})
        page.wait_for_timeout(100)
        assert page.evaluate("document.querySelector('#pp-frame .list').scrollTop") == 0
        assert page.evaluate("document.querySelectorAll('.pl-ring').length") == 0, "the scrolled-away item is not ringed"
        assert errors == []
    finally:
        ctx.close()


STORED = "(() => { try { return localStorage.getItem('plumb.player.panel'); } catch (e) { return 'x'; } })()"


def test_at_the_end_of_play_the_panel_stays_with_play_again(browser, built) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL)
    try:
        _start(page, "lesson", "play", speed=2)
        page.wait_for_function("window.plumbPlayer.state().ended", timeout=15000)
        assert _shown(page, ".pl-dock [data-pl=hide]") == 0, "no Hide panel at the end"
        page.evaluate("document.activeElement.blur()")
        page.keyboard.press("h")
        assert _dock_shown(page) and "Panel hidden" not in page.inner_text(".pl-live")
        assert page.evaluate(STORED) is None
        page.click(".pl-dock [data-pl=play]")
        assert _shown(page, ".pl-dock [data-pl=hide]") == 1
        assert errors == []
    finally:
        ctx.close()


FORM_TRACKS = ("getComputedStyle(document.querySelector('#pp-frame .booking-form'))"
               ".gridTemplateColumns.split(' ').length")


@pytest.mark.parametrize("width", [390, 1280])
def test_the_md_container_query_still_follows_the_frame_with_containment(browser, built, width: int) -> None:
    ctx, page, errors, _ = _open(browser, built / PROTO_REL, width=width, hash_="#screen-booking")
    try:
        assert page.evaluate("getComputedStyle(document.getElementById('pp-frame')).contain").startswith("layout")
        assert page.evaluate(FORM_TRACKS) == 1, "the frame is under 48rem beside the side columns"
        _start(page, "training", "guide", step=1)
        wide = page.evaluate("document.getElementById('pp-frame').getBoundingClientRect().width") >= 768
        assert wide == (width == 1280)
        assert page.evaluate(FORM_TRACKS) == (2 if wide else 1), "the md layout follows the frame's width"
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- review round 3: clip boxes, the frame's edge, scrolling


def test_matches_a_clip_box_hides_are_passed_over_for_a_visible_one(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=15)
        _ringed(page, '#pp-frame [data-screen="boxes"] > [data-state] > p.card')
        assert errors == []
    finally:
        ctx.close()


@pytest.mark.parametrize("width", [1280, 390])
def test_a_drawer_moved_off_by_exactly_its_width_is_skipped(browser, staged, width: int) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL, width=width)
    try:
        _start(page, "staged", "guide", step=16)
        _ringed(page, '#pp-frame [data-screen="boxes"] p > .slide3')
        assert errors == []
    finally:
        ctx.close()


def test_the_marks_follow_the_viewers_scrolling_inside_a_list(browser, staged) -> None:
    ctx, page, errors, _ = _open(browser, staged / PROTO_REL)
    try:
        _start(page, "staged", "guide", step=6)
        _ringed(page, "#pp-frame .list .last")
        top = page.evaluate("document.querySelector('#pp-frame .list').scrollTop")
        page.evaluate("document.querySelector('#pp-frame .list').scrollTop -= 30")
        page.wait_for_timeout(100)
        _ringed(page, "#pp-frame .list .last")
        assert page.evaluate("document.querySelector('#pp-frame .list').scrollTop") == top - 30, "nothing scrolled back"
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- change ids in the Guide panel


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_guide_panel_shows_a_change_id_as_a_chip(browser, tmp_path: Path, scheme: str) -> None:
    """data-guide="F01 · what changed": the Guide lists the text with the id as a chip; text without a leading id
    (or with one that is not a letter and digits) stays plain."""
    p = make_tour_project(tmp_path / "p", build=False)
    home = p / HOME_REL
    write(home, read(home).replace("<h2>", '<h2 data-guide="F01 · The heading says what the page is for">', 1)
          .replace('<ul class="tables">', '<ul class="tables" data-guide="AB1 · not an id">', 1))
    assert run(p).returncode == 0
    ctx, page, errors, _ = _open(browser, p / PROTO_REL, scheme=scheme)
    try:
        items = page.locator("#plumb-guide .pl-gs-do li button")
        texts = items.evaluate_all("bs => bs.map(b => b.textContent)")
        assert "F01The heading says what the page is for" in texts, texts
        assert GUIDE_ITEM in texts and "AB1 · not an id" in texts, texts
        chip = page.locator("#plumb-guide .pl-chip")
        assert chip.count() == 1 and chip.inner_text() == "F01" and chip.get_attribute("data-change") == "F01"
        colors = chip.evaluate("c => [getComputedStyle(c).color, getComputedStyle(c).backgroundColor]")
        assert colors[0] != colors[1]
        page.locator("#plumb-guide .pl-gs-do button", has=page.locator(".pl-chip")).click()  # still flashes its element
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- where a tour plays: "view" (app, the default, or prototype)

def _roles_block() -> str:
    return read(REPO_TEMPLATES / "chrome-roles.css").strip()


def test_view_defaults_to_app_and_the_tour_page_is_the_app_with_the_player(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", {"demo": demo(), "walk": walk()})
    tours = tours_json(read(p / PROTO_REL))["tours"]
    assert tours[0]["id"] == "demo" and tours[0]["view"] == "app", "a tour without view plays in the app view"
    assert tours[1]["id"] == "walk" and tours[1]["view"] == "prototype"
    app_page, proto_page = read(p / DEMO_PAGE), read(p / WALK_PAGE)
    for page in (app_page, proto_page):
        assert P.is_generated_text(page) and "build-prototype.py" in "\n".join(page.splitlines()[:5])
        assert '<base href="../">' in page[:3000] and not NETWORK.search(page)
        assert "window.plumbPlayer" in page and 'id="pp-stage"' in page and 'id="pp-frame"' in page
        for screen in ("home", "booking", "menu"):
            assert f'data-screen="{screen}"' in page
    assert 'class="pa-stage"' in app_page and 'class="pp-side' not in app_page and 'id="theme-toggle"' not in app_page
    assert 'view: "app"' in app_page, "the page is the app view (its window.plumbPrototype)"
    assert tours_json(app_page) == {"tours": [tours[0]], "autostart": {"tour": "demo", "mode": "play"}}
    assert "<title>Taking a booking at Café Ünïcode · Café Ünïcode walkthrough</title>" in app_page
    assert 'class="pp-side pp-ui"' in proto_page and 'id="theme-toggle"' in proto_page
    assert tours_json(proto_page)["autostart"] == {"tour": "walk", "mode": "play"}
    assert "window.plumbPlayer" not in read(p / APP_REL), "app.html itself is a clean demo: no player"


def test_view_change_makes_the_page_stale_and_a_rebuild_follows_it(project: Path) -> None:
    before = read(project / DEMO_PAGE)
    doc = demo()
    doc["view"] = "prototype"
    put_tour(project, "demo", doc)
    r = run(project, "--check")
    assert r.returncode == 1 and f"stale: {DEMO_PAGE}" in r.stdout, r.stdout
    assert read(project / DEMO_PAGE) == before, "--check writes nothing"
    assert run(project).returncode == 0
    assert 'class="pp-side pp-ui"' in read(project / DEMO_PAGE)
    doc["view"] = "app"  # written out, the default gives the same bytes as no view at all
    put_tour(project, "demo", doc)
    assert run(project).returncode == 0 and read(project / DEMO_PAGE) == before


def test_a_bad_view_names_the_line(tmp_path: Path, capsys) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    doc = {"title": "Look around", "view": "fullscreen", "steps": [{"screen": "menu", "caption": "Tonight's menu."}]}
    text = json.dumps(doc, indent=2) + "\n"
    put_tour(p, "look", text)
    line = text.splitlines().index('  "view": "fullscreen",') + 1
    code, _out, err = build_in_process(p, capsys=capsys)
    assert code == 2 and f"{TOURS_REL}/look.json:{line}: " in err and "\nfix: " in err, err
    assert not (p / f"{PAGES_REL}/look.html").exists()


def test_both_shells_carry_the_one_shared_role_block(tmp_path: Path) -> None:
    """The --pl-* roles live once, in templates/chrome-roles.css: both shells take it through one slot, so the app view
    (and its tour pages) give the player the same colours as prototype.html, and the two can never drift."""
    for name in ("prototype-shell.html.tmpl", "app-shell.html.tmpl"):
        shell = read(REPO_TEMPLATES / name)
        assert shell.count("{{chrome_roles}}") == 1, name
        assert "--pl-accent:" not in shell and "--pl-bg:" not in shell, f"{name} defines its own roles"
    roles = _roles_block()
    for selector in (":where(:root), :where(.pl-light)", ':where(:root[data-theme="dark"]), :where(.pl-dark)',
                     ':where(:root:not([data-theme="light"]))'):
        assert selector in roles, selector
    p = make_tour_project(tmp_path / "p", {"demo": demo(), "walk": walk()})
    for rel in (PROTO_REL, APP_REL, DEMO_PAGE, WALK_PAGE):
        assert read(p / rel).count(roles) == 1, rel


def test_a_missing_role_block_template_is_refused(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", build=False)
    (p / SKILL_REL / "templates/chrome-roles.css").unlink()
    assert_refusal(run(p), "chrome-roles.css", "/plumb:upgrade")
    assert not (p / PROTO_REL).exists()


def test_the_prototype_links_to_the_app_on_the_first_screen(tmp_path: Path) -> None:
    p = make_tour_project(tmp_path / "p", {"walk": walk()})
    for rel in (PROTO_REL, WALK_PAGE):
        assert '<a id="pp-app-link" href="app.html#/home"' in read(p / rel), rel


# A screen that keeps a fixed bar at the top of the window, with targets far down the page (one taller than the
# window, labelled at its top); and one with two stacked sticky bars (other class names) next to a sticky full-height
# sidebar (data-app-sidebar), which must not count as a header.
BARS_REL = f"{DOCS}/prototype/screens/bars.html"
STUCK_REL = f"{DOCS}/prototype/screens/stuck.html"
PLAIN_REL = f"{DOCS}/prototype/screens/plain.html"
# No bar at the top of the window: a sticky head inside a scrolling box sticks to that box, not the window; a sticky
# group head whose group ends above the target has scrolled away; and a sticky panel taller than half the window is no
# header: none of them may push a target down.
PLAIN = """<style>
[data-screen="plain"] { padding: var(--spacing-4); }
[data-screen="plain"] .box { height: 200px; overflow: auto; }
[data-screen="plain"] .box .head { position: sticky; top: 0; height: 40px; background: var(--color-surface); }
[data-screen="plain"] .box .rows { height: 600px; }
[data-screen="plain"] .panel { position: sticky; top: 0; height: 80vh; background: var(--color-sunk); }
[data-screen="plain"] .gap { height: 1600px; }
[data-screen="plain"] .spot { height: 80px; }
[data-screen="plain"] .ghead { position: sticky; top: 0; height: 40px; margin: 0; background: var(--color-surface); }
[data-screen="plain"] .group .rows { height: 300px; }
</style>
<section data-screen="plain" data-title="Plain" data-order="9">
  <div data-state="ready">
    <div class="box"><div class="head">Head</div><div class="rows"></div></div>
    <div class="group"><h3 class="ghead">An earlier group</h3><div class="rows"></div></div>
    <div class="gap"></div>
    <div class="spot">Here</div>
    <div class="gap"></div>
    <div class="panel">A tall sticky panel</div>
    <div class="gap"></div>
  </div>
</section>
"""
BARS = """<style>
[data-screen="bars"] { padding: 0 var(--spacing-4) var(--spacing-6); }
[data-screen="bars"] .bar { position: fixed; top: 0; left: 0; right: 0; height: 64px; margin: 0; z-index: 60;
  background: var(--color-surface); }
[data-screen="bars"] .gap { height: 1600px; }
[data-screen="bars"] .mid-target { height: 80px; background: var(--color-sunk); }
[data-screen="bars"] .tall { min-height: 1400px; }
</style>
<section data-screen="bars" data-title="Bars" data-order="7">
  <header class="bar"><p>Bars</p></header>
  <div data-state="ready">
    <div class="gap"></div>
    <div class="mid-target">In the middle</div>
    <div class="gap"></div>
    <div class="tall"><p class="first">The top of a tall area</p></div>
    <div class="gap"></div>
    <p><span class="zoom-me">Zoom here</span></p>
    <div class="gap"></div>
  </div>
</section>
"""
STUCK = """<style>
[data-screen="stuck"] .shell { display: block; }
[data-screen="stuck"] .side { height: 2000px; }
[data-screen="stuck"] .topnav { position: sticky; top: 0; height: 48px; z-index: 30; background: var(--color-surface); }
[data-screen="stuck"] .subnav { position: sticky; top: 48px; height: 40px; z-index: 30; background: var(--color-sunk); }
[data-screen="stuck"] .room { height: 1800px; }
@container plumb-frame (min-width: 48rem) {
  [data-screen="stuck"] .shell { display: grid; grid-template-columns: 14rem minmax(0, 1fr); align-items: start; }
}
</style>
<section data-screen="stuck" data-title="Stuck" data-order="8">
  <div class="shell">
    <nav class="side" data-app-sidebar aria-label="Sections"><p>Sections</p></nav>
    <main>
      <div class="topnav">Top</div>
      <div class="subnav">Sub</div>
      <div data-state="ready">
        <div class="room"></div>
        <p class="deep">Deep down</p>
        <div class="room"></div>
        <p><span class="zoom-me2">Zoom here too</span></p>
        <div class="room"></div>
      </div>
    </main>
  </div>
</section>
"""


def bars_tour() -> dict:
    return {"title": "Bars and zoom", "audience": "review", "steps": [
        {"screen": "bars", "title": "Under the bar", "caption": "Clear of the fixed bar.", "target": ".mid-target",
         "point": "ring"},
        {"screen": "bars", "title": "A tall area", "caption": "Its label clear of the bar.", "target": ".tall",
         "point": "ring", "labels": [{"target": ".tall .first", "text": "Top"}]},
        {"screen": "bars", "title": "Zoom", "caption": "A fixed bar stays put.", "target": ".zoom-me", "point": "zoom"},
        {"screen": "stuck", "title": "Two sticky bars", "caption": "Clear of both.", "target": ".deep", "point": "ring"},
        {"screen": "stuck", "title": "Zoom", "caption": "Nothing fixed here.", "target": ".zoom-me2", "point": "zoom"},
        {"screen": "home", "title": "Back home", "caption": "Tonight's tables.", "target": ".tables", "point": "ring"},
        {"screen": "plain", "title": "Nothing on top", "caption": "Centred.", "target": ".spot", "point": "ring"},
    ], "closing": {"title": "That was it", "text": "Over to you."}}


@pytest.fixture(scope="module")
def apptour(tmp_path_factory) -> Path:
    p = make_tour_project(tmp_path_factory.mktemp("apptour") / "App Ünïcode",
                          {"demo": demo(), "bars": bars_tour(), "walk": walk()}, build=False)
    write(p / BARS_REL, BARS)
    write(p / STUCK_REL, STUCK)
    write(p / PLAIN_REL, PLAIN)
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    return p


def _history(page) -> int:
    return page.evaluate("history.length")


def test_the_app_view_tour_page_plays_guide_mode_without_adding_history(browser, apptour) -> None:
    ctx, page, errors, requests = _open(browser, apptour / DEMO_PAGE)
    try:
        page.wait_for_function("window.__log.length > 0")
        page.evaluate("window.plumbPlayer.start('demo', {mode: 'guide'})")
        start, seen = _history(page), set()
        for _ in range(40):
            # the state and the hash in one read: "Do it for me" moves on from a timer, never between two reads
            s, hash_ = page.evaluate("[window.plumbPlayer.state(), location.hash]")
            if not s["active"]:
                break
            seen.add(_visible_screen(page))
            if s["step"] is not None:
                assert hash_ == f"#tour-demo-{s['step']}"
            page.click(".pl-dock [data-pl=do]" if s["yourTurn"] else ".pl-dock [data-pl=next]")
            page.wait_for_function("(pos) => { const t = window.plumbPlayer.state(); return !t.active || t.pos !== pos; }",
                                   arg=s["pos"])
        assert not _state(page)["active"], "Finish leaves the walkthrough"
        assert {"home", "booking"} <= seen, seen
        assert _history(page) == start, "the player (and the clicks it makes) moved between screens with no history entry"
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


def test_the_app_view_tour_page_plays_by_itself_in_play_mode(browser, apptour) -> None:
    ctx, page, errors, requests = _open(browser, apptour / DEMO_PAGE)
    try:
        page.wait_for_function("window.__log.length > 0")
        start = _history(page)
        _press_start(page)
        page.evaluate("window.plumbPlayer.setSpeed(2)")
        page.wait_for_function("window.plumbPlayer.state().ended", timeout=30000)
        steps = page.evaluate("[...new Set(window.__log.map(e => e.step).filter(n => n !== null))].length")
        assert steps == 6, "every step played"
        assert {e["mode"] for e in page.evaluate("window.__log")} == {"play"}
        assert _history(page) == start
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


def test_tour_links_work_on_the_app_view_tour_page(browser, apptour) -> None:
    ctx, page, errors, _ = _open(browser, apptour / f"{PAGES_REL}/bars.html", hash_="#tour-bars-4")
    try:
        page.wait_for_function("window.__log.length > 0")
        first = page.evaluate("window.__log[0]")
        assert first["tour"] == "bars" and first["step"] == 4 and first["mode"] == "guide"
        assert _visible_screen(page) == "stuck"
        page.evaluate("""() => { var a = document.createElement('a'); a.href = '#tour-bars-6'; a.id = 'tl';
            a.textContent = 'go'; document.querySelector('.pl-dock-top').appendChild(a); }""")
        page.click("#tl")
        s = _state(page)
        assert s["tour"] == "bars" and s["step"] == 6 and _visible_screen(page) == "home"
        assert page.evaluate("location.hash") == "#tour-bars-6"
        page.evaluate("location.hash = '#tour-bars'")
        page.wait_for_function("window.plumbPlayer.state().pos === 0")
        assert _visible_screen(page) == "bars"
        assert errors == []
    finally:
        ctx.close()


def test_the_closing_card_of_an_app_view_tour_opens_the_prototype(browser, apptour) -> None:
    ctx, page, errors, _ = _open(browser, apptour / f"{PAGES_REL}/bars.html")
    try:
        page.wait_for_function("window.__log.length > 0")
        page.evaluate("window.plumbPlayer.jump(window.plumbPlayer.state().total - 1)")
        assert _state(page)["card"] == "closing"
        assert _shown(page, ".pl-card-link") == 1
        href = page.evaluate("document.querySelector('.pl-card-link').href")
        # the screen the tour is on (jumping from step 1 to the end leaves it on that step's screen)
        assert href.endswith("/docs/design/prototype.html#screen-bars"), href
        page.click(".pl-card-link")
        page.wait_for_load_state("load")
        assert page.evaluate("location.pathname").endswith("/docs/design/prototype.html")
        assert _visible_screen(page) == "bars"
        assert errors == []
    finally:
        ctx.close()
    ctx, page, errors, _ = _open(browser, apptour / WALK_PAGE)
    try:
        page.wait_for_function("window.__log.length > 0")
        page.evaluate("window.plumbPlayer.jump(window.plumbPlayer.state().total - 1)")
        assert _state(page)["card"] == "closing" and _shown(page, ".pl-card-link") == 0, "the prototype view has its panels"
        assert errors == []
    finally:
        ctx.close()


COVER = """(sel) => { var r = document.querySelector(sel).getBoundingClientRect();
  var dock = document.querySelector('.pl-dock').getBoundingClientRect();
  var bars = [...document.querySelectorAll('#pp-frame .bar, #pp-frame .topnav, #pp-frame .subnav')]
    .filter(b => b.getClientRects().length && b.closest('[data-screen]').hidden === false)
    .map(b => b.getBoundingClientRect().bottom);
  return {top: r.top, bottom: r.bottom, below: Math.max(0, ...bars), dock: dock.top}; }"""


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("step, sel, below", [
    (1, '#pp-frame [data-screen="bars"] .mid-target', 64),
    (2, '#pp-frame [data-screen="bars"] .tall .first', 64),
    (4, '#pp-frame [data-screen="stuck"] .deep', 88),
])
def test_app_view_targets_clear_the_screens_own_fixed_and_sticky_bars(browser, apptour, width: int, step: int,
                                                                      sel: str, below: int) -> None:
    ctx, page, errors, _ = _open(browser, apptour / f"{PAGES_REL}/bars.html", width=width)
    try:
        page.wait_for_function("window.__log.length > 0")
        _start(page, "bars", "guide", step=step)
        page.wait_for_timeout(100)
        for again in (False, True):
            if again:  # the viewer scrolled the target up under the bar: opening the step again brings it out
                page.evaluate("(sel) => window.scrollBy(0, document.querySelector(sel).getBoundingClientRect().top - 20)", sel)
                page.evaluate("window.plumbPlayer.jump(window.plumbPlayer.state().pos)")
                page.wait_for_timeout(100)
            got = page.evaluate(COVER, sel)
            assert abs(got["below"] - below) <= 0.5, f"the screen's bars are on show at the top: {got}"
            assert got["top"] >= got["below"] - 0.5, f"a bar covers the target: {got} ({again})"
            assert got["bottom"] <= got["dock"] + 0.5, f"the dock covers the target: {got} ({again})"
        assert page.evaluate(ON_TOP, ".pl-dock [data-pl=next]"), "the screen's z-index 60 bar covers the dock"
        assert errors == []
    finally:
        ctx.close()


def test_app_view_sticky_boxes_that_are_no_header_never_push_a_target_down(browser, apptour) -> None:
    ctx, page, errors, _ = _open(browser, apptour / f"{PAGES_REL}/bars.html")
    try:
        page.wait_for_function("window.__log.length > 0")
        _start(page, "bars", "guide", step=7)
        page.wait_for_timeout(100)
        spot = page.evaluate(RECT, '#pp-frame [data-screen="plain"] .spot')
        dock = page.evaluate(RECT, ".pl-dock")
        assert abs(spot[1] + spot[3] / 2 - (dock[1] - 8) / 2) <= 2, (spot, dock)
        assert errors == []
    finally:
        ctx.close()


def test_the_prototype_view_ignores_bars_held_inside_its_frame(browser, apptour) -> None:
    """In prototype.html the frame holds the screen's fixed bar (contain: layout) and its sticky bars (overflow hidden):
    neither is at the top of the window, so they never push a target down."""
    ctx, page, errors, _ = _open(browser, apptour / PROTO_REL)
    try:
        _start(page, "bars", "guide", step=1)
        page.wait_for_timeout(100)
        assert page.evaluate(IN_WINDOW, '#pp-frame [data-screen="bars"] .mid-target')
        mid = page.evaluate(RECT, '#pp-frame [data-screen="bars"] .mid-target')
        dock = page.evaluate(RECT, ".pl-dock")
        bar = page.evaluate("document.querySelector('.pp-bar').getBoundingClientRect().bottom")
        room = (max(bar, 0) + dock[1] - 8) / 2  # centred between the sticky bar and the dock's room
        assert abs(mid[1] + mid[3] / 2 - room) <= 2, (mid, dock, bar)
        assert errors == []
    finally:
        ctx.close()


FRAME_T = "getComputedStyle(document.getElementById('pp-frame')).transform"


def test_app_view_zoom_never_moves_the_screens_fixed_layers(browser, apptour) -> None:
    ctx, page, errors, _ = _open(browser, apptour / f"{PAGES_REL}/bars.html")
    try:
        page.wait_for_function("window.__log.length > 0")
        _start(page, "bars", "guide", step=3)
        page.wait_for_timeout(500)
        assert page.evaluate(FRAME_T) == "none", "a zoom would pull the fixed bar to the top of the page"
        bar = page.evaluate(RECT, '#pp-frame [data-screen="bars"] .bar')
        assert bar[1] == 0 and bar[3] == 64, bar
        assert _shown(page, ".pl-dim") == 1, "the step points with a spotlight instead"
        assert page.evaluate(IN_WINDOW, '#pp-frame [data-screen="bars"] .zoom-me')
        # a screen with nothing fixed zooms as before (its sticky bars and sidebar are not fixed layers)
        _start(page, "bars", "guide", step=5)
        page.wait_for_timeout(500)
        assert page.evaluate(FRAME_T).startswith("matrix("), page.evaluate(FRAME_T)
        assert page.evaluate("getComputedStyle(document.getElementById('pp-stage')).overflowY") in ("clip", "hidden")
        page.keyboard.press("Escape")
        assert page.evaluate(FRAME_T) == "none"
        assert errors == []
    finally:
        ctx.close()


def test_the_prototype_page_links_to_the_app_and_keeps_screen_and_state(browser, apptour) -> None:
    ctx, page, errors, _ = _open(browser, apptour / PROTO_REL)
    try:
        assert page.evaluate("document.getElementById('pp-app-link').getAttribute('href')") == "app.html#/home"
        page.click('.pp-nav [data-nav="booking"]')
        page.click('[data-states-for="booking"] [data-set-state="error"]')
        assert page.evaluate("document.getElementById('pp-app-link').getAttribute('href')") == "app.html#/booking/error"
        page.click("#pp-app-link")
        page.wait_for_load_state("load")
        assert page.evaluate("location.pathname").endswith("/docs/design/app.html")
        assert page.evaluate("window.plumbPrototype.current()") == {"page": "screen", "screen": "booking", "state": "error"}
        assert errors == []
    finally:
        ctx.close()
    ctx, page, errors, _ = _open(browser, apptour / WALK_PAGE)
    try:  # one folder down, the link still reaches the docs folder's app.html
        href = page.evaluate("document.getElementById('pp-app-link').href")
        assert href.split("#")[0].endswith("/docs/design/app.html"), href
        assert errors == []
    finally:
        ctx.close()


@pytest.mark.parametrize("rel", [DEMO_PAGE, WALK_PAGE])
def test_the_skip_link_stays_off_the_window_until_it_has_focus(browser, built, rel: str) -> None:
    """The player's "Skip to the walkthrough" takes no room on any page with the player (the app view included): the
    screen does not move when the tour starts or ends, and the link shows only while focused."""
    ctx, page, errors, _ = _open(browser, built / rel)
    try:
        page.wait_for_function("window.__log.length > 0")
        page.evaluate("window.plumbPlayer.pause()")
        skip = page.evaluate(RECT, ".pl-skip")
        assert skip[1] + skip[3] <= 0, f"the skip link is in the window: {skip}"
        stage = page.evaluate(RECT, "#pp-stage")
        if rel == DEMO_PAGE:
            assert stage[1] == 0, "the app view's window is the frame: nothing above it"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.textContent") == "Skip to the walkthrough"
        shown = page.evaluate(RECT, ".pl-skip")
        assert shown[1] >= 0 and shown[1] + shown[3] <= 900, shown
        assert page.evaluate(RECT, "#pp-stage")[1] == stage[1], "focusing it moves nothing"
        page.keyboard.press("Escape")
        assert page.evaluate(RECT, "#pp-stage")[1] == stage[1], "the screen does not shift when the tour ends"
        assert errors == []
    finally:
        ctx.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_a_zoom_step_is_outlined_whether_or_not_it_can_zoom(browser, apptour, width: int) -> None:
    ctx, page, errors, _ = _open(browser, apptour / f"{PAGES_REL}/bars.html", width=width)
    try:
        page.wait_for_function("window.__log.length > 0")
        _start(page, "bars", "guide", step=5)
        page.wait_for_timeout(500)
        assert _shown(page, ".pl-edge") == 1, page.evaluate(FRAME_T)
        assert errors == []
    finally:
        ctx.close()


def test_leaving_an_app_view_tour_keeps_focus_on_the_screen(browser, apptour) -> None:
    ctx, page, errors, _ = _open(browser, apptour / DEMO_PAGE)
    try:
        page.wait_for_function("window.__log.length > 0")
        page.keyboard.press("Escape")
        assert not _state(page)["active"]
        assert page.evaluate("document.getElementById('pp-frame').contains(document.activeElement)"), \
            page.evaluate("document.activeElement.outerHTML.slice(0, 80)")
        assert page.evaluate("document.activeElement.getAttribute('data-screen')") == "home"
        assert "The app is yours to click around" in page.inner_text(".pl-live")
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- pinned targets and labels away from their target

BOARD_REL = f"{DOCS}/prototype/screens/board.html"
# An app shell: a sticky sidebar (data-app-sidebar) with a link, a page header with two labelled things, a long list, a
# footer far below, and a state with a toast fixed to the bottom-right corner of the window.
BOARD_ROWS = "".join(f'<p class="row r{i}">Row {i}</p>' for i in range(1, 61))
BOARD = """<style>
[data-screen="board"] .shell { display: block; }
[data-screen="board"] .side { padding: var(--spacing-4); background: var(--color-sunk); }
[data-screen="board"] .head { display: flex; gap: var(--spacing-4); padding: var(--spacing-4); }
[data-screen="board"] .row { margin: 0; padding: var(--spacing-4); }
[data-screen="board"] .foot { margin-top: 1200px; padding: var(--spacing-4); }
[data-screen="board"] .toast { position: fixed; right: var(--spacing-6); bottom: var(--spacing-6); z-index: 70;
  width: 280px; padding: var(--spacing-3); background: var(--color-surface); }
@container plumb-frame (min-width: 48rem) {
  [data-screen="board"] .shell { display: grid; grid-template-columns: 14rem minmax(0, 1fr); align-items: start; }
}
</style>
<section data-screen="board" data-title="Board" data-order="11">
  <div class="shell">
    <nav class="side" data-app-sidebar aria-label="Sections"><a href="#screen-board" class="week">Week</a></nav>
    <main>
      <header class="head"><p class="kpi">This week: 12</p><button type="button" class="primary">New item</button></header>
      <div data-state="ready">""" + BOARD_ROWS + """<footer class="foot">The end</footer></div>
      <div data-state="saved">""" + BOARD_ROWS + """<footer class="foot">The end</footer>
        <div class="toast" role="status">Saved</div></div>
    </main>
  </div>
</section>
"""


def pins_tour() -> dict:
    labels = [{"target": ".head .kpi", "text": "This week"}, {"target": ".head .primary", "text": "New"}]
    return {"title": "Pinned and labelled", "audience": "review", "steps": [
        {"screen": "board", "title": "The last row", "caption": "Down the list.", "target": ".r60", "point": "ring"},
        {"screen": "board", "title": "The sidebar", "caption": "Labels on the header.", "target": ".side .week",
         "point": "ring", "labels": labels},
        {"screen": "board", "title": "Too far apart", "caption": "The header and the footer.", "target": ".side .week",
         "point": "ring", "labels": [{"target": ".head .kpi", "text": "This week"}, {"target": ".foot", "text": "End"}]},
        {"screen": "board", "state": "saved", "title": "Saved", "caption": "The toast says so.", "target": ".toast",
         "point": "beacon"},
        {"screen": "board", "state": "ready", "title": "A row", "caption": "In the middle.", "target": ".r30",
         "point": "ring"},
    ]}


@pytest.fixture(scope="module")
def pins(tmp_path_factory) -> Path:
    p = make_tour_project(tmp_path_factory.mktemp("pins") / "Pins Ünïcode", {"demo": demo(), "pins": pins_tour()},
                          build=False)
    write(p / BOARD_REL, BOARD)
    r = run(p)
    assert r.returncode == 0, r.stdout + r.stderr
    return p


PINS_PAGE = f"{PAGES_REL}/pins.html"
OVERLAP = """([a, b]) => { var r = document.querySelector(a).getBoundingClientRect();
  var s = document.querySelector(b).getBoundingClientRect();
  return Math.max(0, Math.min(r.right, s.right) - Math.max(r.left, s.left)) *
         Math.max(0, Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top)); }"""
TOAST = '#pp-frame [data-screen="board"] .toast'


@pytest.mark.parametrize("width", [1280, 390])
def test_a_toast_fixed_to_the_window_is_not_scrolled_to_and_the_dock_moves_clear(browser, pins, width: int) -> None:
    ctx, page, errors, _ = _open(browser, pins / PINS_PAGE, width=width, height=800)
    try:
        page.wait_for_function("window.__log.length > 0")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        _start(page, "pins", "guide", step=4)
        page.wait_for_timeout(100)
        assert page.evaluate("window.scrollY") == 0, "scrolling cannot move a toast fixed to the window"
        assert page.evaluate(OVERLAP, [".pl-dock", TOAST]) == 0, page.evaluate(RECT, ".pl-dock")
        assert page.evaluate(IN_WINDOW, TOAST)
        assert _shown(page, ".pl-beacon") == 1
        assert page.evaluate(ON_TOP, ".pl-dock [data-pl=next]")
        # reached from a step that scrolled down: the page stays where it is, the dock still keeps clear
        _start(page, "pins", "guide", step=1)
        down = page.evaluate("window.scrollY")
        assert down > 0
        page.evaluate("window.plumbPlayer.jump(window.plumbPlayer.state().pos + 3)")
        assert _state(page)["step"] == 4
        assert page.evaluate("window.scrollY") == down, "the step did not scroll the page"
        assert page.evaluate(OVERLAP, [".pl-dock", TOAST]) == 0
        # play mode: the subtitle follows the dock and keeps clear of the toast too
        _start(page, "pins", "play", step=4)
        page.evaluate("window.plumbPlayer.pause()")
        assert page.evaluate(OVERLAP, [".pl-dock", TOAST]) == 0
        assert page.evaluate(OVERLAP, [".pl-subtitle", TOAST]) == 0
        assert page.evaluate(OVERLAP, [".pl-subtitle", ".pl-dock"]) == 0
        sub = page.evaluate(RECT, ".pl-subtitle")
        assert sub[1] >= 0 and sub[1] + sub[3] <= 800, sub
        # a target that scrolls keeps today's dock at the bottom of the window
        _start(page, "pins", "guide", step=5)
        dock = page.evaluate(RECT, ".pl-dock")
        assert abs(dock[1] + dock[3] - (800 - 8)) <= 1, dock
        assert page.evaluate(IN_WINDOW, '#pp-frame [data-screen="board"] .r30')
        assert errors == []
    finally:
        ctx.close()


def test_the_pill_keeps_clear_of_a_pinned_toast_too(browser, pins) -> None:
    ctx, page, errors, _ = _open(browser, pins / PINS_PAGE, width=390, height=800)
    try:
        page.wait_for_function("window.__log.length > 0")
        _start(page, "pins", "guide", step=4)
        page.keyboard.press("h")
        assert _shown(page, ".pl-pill") == 1
        assert page.evaluate(OVERLAP, [".pl-pill", TOAST]) == 0, page.evaluate(RECT, ".pl-pill")
        page.keyboard.press("h")
        assert page.evaluate(OVERLAP, [".pl-dock", TOAST]) == 0
        assert errors == []
    finally:
        ctx.close()


def test_in_the_prototype_page_the_dock_keeps_clear_of_a_toast_too(browser, pins) -> None:
    ctx, page, errors, _ = _open(browser, pins / PROTO_REL, height=800)
    try:
        _start(page, "pins", "guide", step=4)
        page.wait_for_timeout(100)
        assert page.evaluate(OVERLAP, [".pl-dock", TOAST]) == 0
        assert page.evaluate(IN_WINDOW, TOAST)
        assert errors == []
    finally:
        ctx.close()


LABELS_SHOWN = """() => { var d = document.querySelector('.pl-dock').getBoundingClientRect();
  return [...document.querySelectorAll('.pl-label')].map(function (n) { var r = n.getBoundingClientRect();
    return {text: n.textContent, ok: r.top >= 0 && r.bottom <= d.top}; }); }"""
WEEK = '#pp-frame [data-screen="board"] .side .week'


@pytest.mark.parametrize("via", ["next", "jump"])
def test_labels_away_from_a_target_in_view_are_brought_in_with_it(browser, pins, via: str) -> None:
    ctx, page, errors, _ = _open(browser, pins / PINS_PAGE, height=800)
    try:
        page.wait_for_function("window.__log.length > 0")
        _start(page, "pins", "guide", step=1)
        assert page.evaluate("window.scrollY") > 0
        if via == "next":
            page.click(".pl-dock [data-pl=next]")
        else:
            page.evaluate("window.plumbPlayer.jump(window.plumbPlayer.state().pos + 1)")
        assert _state(page)["step"] == 2
        assert page.evaluate(IN_WINDOW, WEEK), "the target stays in view"
        labels = page.evaluate(LABELS_SHOWN)
        assert [x["text"] for x in labels] == ["This week", "New"], labels
        assert all(x["ok"] for x in labels), labels
        # they cannot all fit (the footer is far below): the target and the first label come first
        page.click(".pl-dock [data-pl=next]")
        assert _state(page)["step"] == 3
        assert page.evaluate(IN_WINDOW, WEEK)
        first = [x for x in page.evaluate(LABELS_SHOWN) if x["text"] == "This week"]
        assert first and first[0]["ok"], page.evaluate(LABELS_SHOWN)
        assert errors == []
    finally:
        ctx.close()


# ---------------------------------------------------------------- voice and subtitles (play mode)
# Headless browsers have no voices: a fake speechSynthesis, injected before the page loads, records every utterance
# (text, rate, lang, voice) and every cancel, and lets a test end an utterance (__speech.end()), fail it
# (__speech.fail(code)) or have each one end by itself after a few ms (window.__speechAuto = ms).

FAKE_SPEECH = """
(() => {
  const S = window.__speech = { spoken: [], cancels: 0, current: null,
    voices: window.__voices !== undefined ? window.__voices : [
      { name: "Other", lang: "fr-FR", default: true, localService: true, voiceURI: "fr" },
      { name: "Test English", lang: "en-US", default: false, localService: true, voiceURI: "en" }] };
  const synth = {
    speaking: false, pending: false, paused: false, onvoiceschanged: null,
    getVoices() { return S.voices.slice(); },
    speak(u) {
      S.spoken.push({ text: u.text, rate: u.rate, lang: u.lang, voice: u.voice ? u.voice.name : null, t: performance.now() });
      S.current = u; this.speaking = true;
      if (window.__speechAuto) setTimeout(() => { if (S.current === u) S.end(); }, window.__speechAuto);
    },
    cancel() {
      S.cancels += 1; const u = S.current; S.current = null; this.speaking = false;
      if (u && u.onerror) u.onerror({ error: "interrupted" });
    },
    pause() {}, resume() {}, addEventListener() {}, removeEventListener() {},
  };
  S.end = () => { const u = S.current; S.current = null; synth.speaking = false; if (u && u.onend) u.onend({}); return !!u; };
  S.fail = (code) => { const u = S.current; S.current = null; synth.speaking = false;
    if (u && u.onerror) u.onerror({ error: code }); return !!u; };
  Object.defineProperty(window, "speechSynthesis", { configurable: true, value: synth });
  window.SpeechSynthesisUtterance = function (text) {
    this.text = text; this.rate = 1; this.lang = ""; this.voice = null; this.onend = null; this.onerror = null; };
})();
"""
NO_VOICES = "window.__voices = [];" + FAKE_SPEECH
NO_SPEECH = """Object.defineProperty(window, "speechSynthesis", { configurable: true, value: undefined });
window.SpeechSynthesisUtterance = undefined;"""
AUTO_END = "window.__speechAuto = 60;"
REMEMBER_VOICE = "try { localStorage.setItem('plumb.player.voice', 'on'); } catch (e) {}"
STORAGE_WRITES = """
window.__writes = [];
['setItem', 'removeItem', 'clear'].forEach(function (name) {
  var orig = Storage.prototype[name];
  Storage.prototype[name] = function (key) {
    window.__writes.push([this === window.localStorage ? 'local' : 'session', name, key === undefined ? null : key]);
    return orig.apply(this, arguments);
  };
});
"""
VOICE_BTN = ".pl-dock [data-pl=voice]"
SAY_1 = "Here are tonight's tables. All of them, in time order."
ODD_CAPTION = "Back on the list: tables & times <b>now</b> --> next."


def voiced_tour() -> dict:
    doc = demo()
    _step(doc, 0, 0)["say"] = SAY_1
    _step(doc, 1, 0)["say"] = "Look."
    _step(doc, 3, 1)["caption"] = ODD_CAPTION
    return doc


@pytest.fixture(scope="module")
def voiced(tmp_path_factory) -> Path:
    return make_tour_project(tmp_path_factory.mktemp("voice") / "Voice Ünïcode", {"demo": voiced_tour()})


def _spoken(page) -> list:
    return page.evaluate("window.__speech.spoken.map(s => s.text)")


def _cancels(page) -> int:
    return page.evaluate("window.__speech.cancels")


def _voice_note(page) -> str:
    return page.evaluate("(() => { var n = document.querySelector('.pl-voice-note'); return n.hidden ? '' : n.textContent; })()")


def _live(page) -> str:
    return page.evaluate("[...document.querySelectorAll('[aria-live]')].map(e => e.textContent).join(' | ')")


def _visible_start_buttons(page) -> list:
    return page.evaluate("""[...document.querySelectorAll('.pl-card-start button')].filter(b => !b.hidden &&
        b.getClientRects().length).map(b => [b.textContent, b.classList.contains('pl-primary'), b.type])""")


def test_voice_is_off_by_default_a_toggle_and_remembered(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        _start(page, "demo", "play", step=1)
        page.wait_for_timeout(300)
        assert _spoken(page) == [] and _state(page)["voice"] is False, "off by default: captions are not read twice"
        assert page.evaluate(f"document.querySelector('{VOICE_BTN}').tagName") == "BUTTON"
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "false"
        assert page.get_attribute(VOICE_BTN, "aria-keyshortcuts") == "V"
        page.click(VOICE_BTN)
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "true" and _state(page)["voice"] is True
        said = page.evaluate("window.__speech.spoken")
        assert [s["text"] for s in said] == ["Here are tonight's tables."], "the step again, from its start"
        assert said[0]["rate"] == 0.9 and said[0]["lang"] == "en", said
        assert said[0]["voice"] == "Test English", "the page's lang picks the voice"
        assert _state(page)["step"] == 1
        assert "Voice on." in _live(page)
        assert page.inner_text(".pl-subtitle") == "The host lands on tonight's tables, in time order.", \
            "say is for speech only: the subtitle on screen stays the caption"
        assert page.evaluate("localStorage.getItem('plumb.player.voice')") == "on"
        before = _cancels(page)
        page.keyboard.press("v")
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "false" and _cancels(page) == before + 1
        assert page.evaluate("localStorage.getItem('plumb.player.voice')") is None
        page.keyboard.press("v")
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "true"
        page.reload()
        page.wait_for_load_state("load")
        _start(page, "demo", "play", step=2)
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "true", "remembered across reloads"
        assert _spoken(page) == ["Look."], "a step's say replaces its caption for speech"
        assert errors == []
    finally:
        ctx.close()


def test_the_v_key_is_ignored_while_typing_with_modifiers_held_or_repeated(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        _start(page, "demo", "play", step=3)
        page.evaluate("window.plumbPlayer.pause()")
        page.focus("#pp-frame [data-test=guest]")
        page.keyboard.press("v")
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "false", "typing a v is not the V key"
        page.evaluate("document.activeElement.blur()")
        for combo in ("Control+v", "Alt+v", "Meta+v"):
            page.keyboard.press(combo)
            assert page.get_attribute(VOICE_BTN, "aria-pressed") == "false", combo
        page.evaluate("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'v', repeat: true, bubbles: true}))")
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "false", "a held key toggles once"
        _start(page, "demo", "guide", step=1)
        page.keyboard.press("v")
        assert page.evaluate("localStorage.getItem('plumb.player.voice')") is None, "voice is for play mode"
        assert errors == []
    finally:
        ctx.close()


def test_the_pace_follows_the_speed_control(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        page.evaluate("window.plumbPlayer.setVoice(true)")
        rates = []
        for speed in (0.5, 1, 1.5, 2):
            _start(page, "demo", "play", step=1, speed=speed)
            rates.append(page.evaluate("window.__speech.spoken.at(-1).rate"))
        assert rates == [0.7, 0.9, 1.15, 1.3], "calm at 1x, slower at 0.5x, capped at 1.5x and 2x"
        # a speed change restarts the sentence at the new pace
        before, n = _cancels(page), len(_spoken(page))
        page.click(".pl-dock [data-speed='1.5']")
        said = page.evaluate("window.__speech.spoken")
        assert _cancels(page) == before + 1 and len(said) == n + 1
        assert said[-1]["text"] == said[-2]["text"] and said[-1]["rate"] == 1.15
        assert errors == []
    finally:
        ctx.close()


def test_a_step_waits_for_its_speech_then_a_pause_then_its_hold(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        page.evaluate("window.plumbPlayer.setVoice(true)")
        _start(page, "demo", "play", step=1)  # hold 700 ms
        page.wait_for_timeout(1500)
        assert _state(page)["pos"] == 2 and _spoken(page) == ["Here are tonight's tables."], "still speaking: it waits"
        ended = page.evaluate("(() => { window.__speech.end(); return performance.now(); })()")
        page.wait_for_function("window.__speech.spoken.length === 2")
        said = page.evaluate("window.__speech.spoken")
        assert said[1]["text"] == "All of them, in time order."
        assert said[1]["t"] - ended >= 300, "a short pause after each sentence"
        page.wait_for_timeout(1200)
        assert _state(page)["pos"] == 2, "the second sentence is still being spoken"
        ended = page.evaluate("(() => { window.__speech.end(); return performance.now(); })()")
        _wait_pos(page, 3, timeout=4000)
        moved = page.evaluate("window.__log.filter(e => e.pos === 3).at(-1).t")
        assert moved - ended >= 350 + 700 - 50, "then the pause and the step's hold, as today"
        # a card speaks its title, then its text
        n = len(_spoken(page))
        _start(page, "demo", "play")
        assert _spoken(page)[n:] == ["Taking a booking"]
        page.evaluate("window.__speech.end()")
        page.wait_for_function("(n) => window.__speech.spoken.length === n + 2", arg=n)
        assert _spoken(page)[-1] == "What you'll see: tonight's tables, a new booking typed in, and the confirmation."
        assert errors == []
    finally:
        ctx.close()


def test_pause_and_resume_stop_and_speak_the_sentence_again(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        page.evaluate("window.plumbPlayer.setVoice(true)")
        _start(page, "demo", "play", step=1)
        before = _cancels(page)
        page.click(".pl-dock [data-pl=play]")
        assert _state(page)["paused"] is True and _cancels(page) == before + 1
        page.wait_for_timeout(1200)
        assert _spoken(page) == ["Here are tonight's tables."] and _state(page)["pos"] == 2
        page.keyboard.press("Space")
        assert _state(page)["paused"] is False
        assert _spoken(page) == ["Here are tonight's tables."] * 2, "Play speaks that sentence again"
        assert errors == []
    finally:
        ctx.close()


@pytest.mark.parametrize("how", ["next", "back", "jump", "restart", "hide", "mode", "leave"])
def test_every_move_cancels_the_sentence_so_voice_and_screen_stay_in_step(browser, voiced, how: str) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        page.evaluate("window.plumbPlayer.setVoice(true)")
        _start(page, "demo", "play", step=1)
        before = _cancels(page)
        if how == "next":
            page.keyboard.press("ArrowRight")
            want = "Look."
        elif how == "back":
            page.keyboard.press("ArrowLeft")
            want = "Tonight at a glance"
        elif how == "jump":
            page.click(".pl-marks button >> nth=1")
            want = "Take the booking"
        elif how == "restart":
            page.click(".pl-dock [data-pl=restart]")
            want = "Taking a booking"
        elif how == "hide":
            page.keyboard.press("h")
            want = "Here are tonight's tables."
        elif how == "mode":
            page.click(".pl-dock [data-pl=mode]")
            want = None
        else:
            page.keyboard.press("Escape")
            want = None
        assert _cancels(page) == before + 1, how
        said = _spoken(page)
        if want:
            assert said[-1] == want and len(said) == 2, (how, said)
        else:
            page.wait_for_timeout(500)
            assert len(said) == 1 and _spoken(page) == said, "guide mode and leaving are silent"
        assert errors == []
    finally:
        ctx.close()


def test_reduced_motion_still_speaks(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH, reduced=True)
    try:
        page.evaluate("window.plumbPlayer.setVoice(true)")
        _start(page, "demo", "play", step=1)
        assert _spoken(page) == ["Here are tonight's tables."], "a voice is not motion"
        assert errors == []
    finally:
        ctx.close()


def test_a_tour_that_opens_in_play_mode_waits_on_its_first_card_for_start(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / DEMO_PAGE, init=FAKE_SPEECH)
    try:
        page.wait_for_function("window.plumbPlayer.state().waiting")
        assert _visible_start_buttons(page) == [["Start with voice", False, "button"], ["Start without voice", True, "button"]]
        assert _state(page)["pos"] == 0 and _state(page)["card"] == "intro"
        assert page.evaluate("document.activeElement === document.body"), "no focus move on load"
        assert "Choose Start with voice or Start without voice." in _live(page)
        page.wait_for_timeout(1200)
        assert _state(page)["pos"] == 0 and _spoken(page) == [], "nothing plays or speaks before the click"
        page.click("[data-pl=start-voice]")
        assert _state(page)["waiting"] is False and _state(page)["paused"] is False
        assert _visible_start_buttons(page) == []
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "true"
        assert _spoken(page) == ["Taking a booking"]
        assert page.evaluate("localStorage.getItem('plumb.player.voice')") == "on"
        assert page.evaluate("document.activeElement.getAttribute('data-pl')") == "play"
        # the remembered choice is the default; Space (or Play) starts with it
        page.reload()
        page.wait_for_function("window.plumbPlayer.state().waiting")
        assert _visible_start_buttons(page) == [["Start with voice", True, "button"], ["Start without voice", False, "button"]]
        page.keyboard.press("Space")
        assert _state(page)["waiting"] is False and _spoken(page) == ["Taking a booking"]
        # without voice: no speech, and the choice is remembered
        page.reload()
        page.wait_for_function("window.plumbPlayer.state().waiting")
        page.click("[data-pl=start-quiet]")
        page.wait_for_timeout(300)
        assert _spoken(page) == [] and page.get_attribute(VOICE_BTN, "aria-pressed") == "false"
        assert page.evaluate("localStorage.getItem('plumb.player.voice')") is None
        _wait_pos(page, 1, timeout=3000)
        assert errors == []
    finally:
        ctx.close()
    # a deep link that opens a step in play mode waits too, on a card of its own
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH, hash_="#tour-demo-3")
    try:
        page.wait_for_function("window.plumbPlayer.state().waiting")
        assert _state(page)["step"] == 3 and page.inner_text(".pl-card-box h2") == "Taking a booking at Café Ünïcode"
        page.click("[data-pl=start-quiet]")
        assert _state(page)["waiting"] is False and _shown(page, ".pl-card") == 0
        assert errors == []
    finally:
        ctx.close()


@pytest.mark.parametrize("init", [NO_SPEECH, NO_VOICES], ids=["no-api", "no-voices"])
def test_without_speech_the_voice_is_disabled_and_captions_keep_todays_timing(browser, voiced, init: str) -> None:
    ctx, page, errors, _ = _open(browser, voiced / DEMO_PAGE, init=REMEMBER_VOICE + init)
    try:
        page.wait_for_function(f"document.querySelector('{VOICE_BTN}').disabled", timeout=3000)
        assert _voice_note(page) == "Voice isn't available in this browser"
        assert page.get_attribute(VOICE_BTN, "title") == "Voice isn't available in this browser"
        assert page.get_attribute(VOICE_BTN, "aria-describedby") == "pl-voice-note"
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "false"
        assert _visible_start_buttons(page) == [["Start", True, "button"]], "only Start"
        page.keyboard.press("v")
        page.click("[data-pl=start-quiet]")
        assert _state(page)["voice"] is False
        _wait_pos(page, 1, timeout=3000)  # the intro's 600 ms hold, as today
        assert errors == []
    finally:
        ctx.close()


def test_an_error_mid_run_says_so_once_and_continues_with_captions(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        page.evaluate("window.plumbPlayer.setVoice(true)")
        _start(page, "demo", "play", step=1)
        page.evaluate("window.__speech.fail('synthesis-failed')")
        assert _voice_note(page) == "Voice stopped: continuing with captions"
        assert "Voice stopped: continuing with captions" in _live(page)
        assert page.get_attribute(VOICE_BTN, "aria-pressed") == "false"
        assert not page.evaluate(f"document.querySelector('{VOICE_BTN}').disabled")
        _wait_pos(page, 3, timeout=4000)  # the step's own timing
        page.wait_for_timeout(300)
        assert _spoken(page) == ["Here are tonight's tables."], "voice off for the rest of the run"
        assert page.evaluate("localStorage.getItem('plumb.player.voice')") == "on", "the viewer's choice stays"
        _start(page, "demo", "play", step=2)
        assert _spoken(page)[-1] == "Look.", "a new run speaks again"
        assert _voice_note(page) == ""
        assert errors == []
    finally:
        ctx.close()


def test_speech_that_never_ends_falls_back_after_a_safety_timer(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        page.evaluate("window.plumbPlayer.setVoice(true)")
        started = page.evaluate("performance.now()")
        _start(page, "demo", "play", step=2)  # say "Look.": one word
        assert _spoken(page) == ["Look."]
        page.wait_for_function("document.querySelector('.pl-voice-note').textContent === "
                               "'Voice stopped: continuing with captions'", timeout=6000)
        noted = page.evaluate("performance.now()")
        assert noted - started >= 1500, "the safety timer allows the expected time and a margin first"
        _wait_pos(page, 4, timeout=6000)
        assert errors == []
    finally:
        ctx.close()


VTT_CUE = re.compile(r"(\d+)\n(\d\d):(\d\d):(\d\d)\.(\d{3}) --> (\d\d):(\d\d):(\d\d)\.(\d{3})\n((?:.+\n)+)")


def _cues(vtt: str) -> list:
    assert vtt.startswith("WEBVTT\n\n1\n"), vtt[:40]
    body = vtt[len("WEBVTT\n\n"):]
    out, at = [], 0
    for m in VTT_CUE.finditer(body):
        assert m.start() == at, ("a stray line in the file", body[at:m.start()])
        g = m.groups()
        out.append({"n": int(g[0]), "start": ((int(g[1]) * 60 + int(g[2])) * 60 + int(g[3])) * 1000 + int(g[4]),
                    "end": ((int(g[5]) * 60 + int(g[6])) * 60 + int(g[7])) * 1000 + int(g[8]), "text": g[9][:-1]})
        at = m.end() + 1
    assert at >= len(body), ("unparsed", body[at:])
    return out


@pytest.mark.parametrize("voice", [True, False], ids=["voice", "captions"])
def test_subtitles_are_exact_from_a_play_through(browser, voiced, voice: bool) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=AUTO_END + FAKE_SPEECH)
    try:
        page.evaluate("(v) => window.plumbPlayer.setVoice(v)", voice)
        _start(page, "demo", "play", speed=2)
        page.wait_for_function("window.plumbPlayer.state().ended", timeout=30000)
        vtt = page.evaluate("window.plumbPlayer.subtitles()")
        cues = _cues(vtt)
        doc = voiced_tour()
        steps = [s for c in doc["chapters"] for s in c["steps"]]
        odd = ODD_CAPTION.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        want = ([f"{doc['intro']['title']}\n{doc['intro']['text']}", doc["chapters"][0]["title"]] +
                [s["caption"] for s in steps[:2]] + [doc["chapters"][1]["title"]] +
                [s["caption"] if s["caption"] != ODD_CAPTION else odd for s in steps[2:]] +
                [f"{doc['closing']['title']}\n{doc['closing']['text']}"])
        assert [c["text"] for c in cues] == want, "the captions on screen, in order (say is never shown)"
        assert [c["n"] for c in cues] == list(range(1, len(want) + 1))
        assert "tables &amp; times &lt;b&gt;now&lt;/b&gt; --&gt; next." in vtt
        log = page.evaluate("window.__log")
        first = {}
        for e in log:
            if e["active"] and not e["ended"] and e["pos"] not in first:
                first[e["pos"]] = e["t"]
        t0 = first[0]
        for i, c in enumerate(cues):
            assert abs(c["start"] - (first[i] - t0)) <= 25, (i, c, first[i] - t0)
            assert c["end"] > c["start"]
            if i + 1 < len(cues):
                assert abs(cues[i + 1]["start"] - c["end"]) <= 2, "back to back: one caption ends as the next shows"
        ended = next(e["t"] for e in log if e["ended"])
        assert abs(cues[-1]["end"] - (ended - t0)) <= 25
        if voice:
            assert len(_spoken(page)) > len(cues), "every card and step was spoken (cards say two sentences)"
        with page.expect_download() as dl:
            page.click(".pl-dock [data-pl=vtt]")
        assert dl.value.suggested_filename == "demo.vtt"
        assert Path(dl.value.path()).read_text(encoding="utf-8") == vtt
        assert "Saved the subtitles as demo.vtt." in _live(page)
        assert errors == []
    finally:
        ctx.close()


def test_save_subtitles_is_in_the_panel_while_playing(browser, voiced) -> None:
    ctx, page, errors, _ = _open(browser, voiced / PROTO_REL, init=FAKE_SPEECH)
    try:
        _start(page, "demo", "guide", step=1)
        assert _shown(page, ".pl-dock [data-pl=vtt]") == 0, "subtitles come from play mode"
        _start(page, "demo", "play", step=1)
        assert _shown(page, ".pl-dock [data-pl=vtt]") == 1
        page.wait_for_timeout(400)
        with page.expect_download() as dl:
            page.click(".pl-dock [data-pl=vtt]")
        cues = _cues(Path(dl.value.path()).read_text(encoding="utf-8"))
        assert [c["text"] for c in cues] == ["The host lands on tonight's tables, in time order."]
        assert cues[0]["start"] == 0 and cues[0]["end"] >= 350, "the caption on screen, up to now"
        assert errors == []
    finally:
        ctx.close()


def test_only_the_voice_choice_is_written_to_storage(browser, voiced) -> None:
    ctx, page, errors, requests = _open(browser, voiced / DEMO_PAGE, init=STORAGE_WRITES + AUTO_END + FAKE_SPEECH)
    try:
        page.wait_for_function("window.plumbPlayer.state().waiting")
        page.click("[data-pl=start-voice]")
        page.evaluate("window.plumbPlayer.setSpeed(2)")
        page.wait_for_function("window.plumbPlayer.state().ended", timeout=30000)
        with page.expect_download():
            page.click(".pl-dock [data-pl=vtt]")
        writes = page.evaluate("window.__writes")
        assert writes and all(w[0] == "local" and w[2] == "plumb.player.voice" for w in writes), writes
        assert page.evaluate("Object.keys(localStorage)") == ["plumb.player.voice"]
        assert page.evaluate("sessionStorage.length") == 0
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()


def _rgb(text: str) -> tuple:
    m = re.match(r"rgba?\((\d+), (\d+), (\d+)", text)
    assert m, text
    return tuple(int(x) for x in m.groups())


def _contrast(a: tuple, b: tuple) -> float:
    def lum(c):
        def ch(v):
            v = v / 255
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b_ = (ch(x) for x in c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b_
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_voice_controls_render_in_both_themes(browser, voiced, scheme: str, width: int) -> None:
    ctx, page, errors, requests = _open(browser, voiced / DEMO_PAGE, init=REMEMBER_VOICE + FAKE_SPEECH,
                                        scheme=scheme, width=width)
    try:
        page.wait_for_function("window.plumbPlayer.state().waiting")
        for sel in ("[data-pl=start-voice]", "[data-pl=start-quiet]"):
            box = page.evaluate(f"JSON.parse(JSON.stringify(document.querySelector('{sel}').getBoundingClientRect()))")
            assert box["left"] >= 0 and box["right"] <= width and box["bottom"] <= 900, (sel, box)
            fg, bg = page.evaluate(f"(() => {{ var s = getComputedStyle(document.querySelector('{sel}')); "
                                   f"return [s.color, s.backgroundColor]; }})()")
            assert _contrast(_rgb(fg), _rgb(bg)) >= 4.5, (sel, fg, bg)
        page.click("[data-pl=start-voice]")
        assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
        fg, bg = page.evaluate(f"(() => {{ var s = getComputedStyle(document.querySelector('{VOICE_BTN}')); "
                               "return [s.color, s.backgroundColor]; })()")
        accent = page.evaluate("""(() => { var p = document.createElement('span'); p.style.background = 'var(--pl-accent)';
            document.querySelector('.pl-dock').appendChild(p); var c = getComputedStyle(p).backgroundColor; p.remove();
            return c; })()""")
        assert bg == accent and _contrast(_rgb(fg), _rgb(bg)) >= 4.5, "pressed: the accent, readable"
        assert _shown(page, ".pl-dock [data-pl=vtt]") == 1
        assert errors == [] and requests == [], (errors, requests)
    finally:
        ctx.close()
