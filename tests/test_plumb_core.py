"""_plumb.py: the shared token, colour and contrast core every engine script imports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugins/plumb/assets/skill/scripts"))
import _plumb as P  # noqa: E402

FIX = REPO / "tests/fixtures/tokens"


@pytest.fixture()
def doc() -> dict:
    return P.load_tokens(FIX / "basic.tokens.json")


def assert_formatted(err: P.PlumbError) -> None:
    text = str(err)
    assert "error:" in text and ("fix:" in text or "ask the user:" in text), text


def test_versions() -> None:
    assert P.PLUMB_VERSION == "1.0.0" and P.SCHEMA_VERSION == 1


def test_contrast_known_ratios() -> None:
    assert P.contrast("#ffffff", "#14857f") == 4.48
    assert P.contrast("#ffffff", "#13817b") == 4.72  # the brief says 4.7; the exact ratio is 4.72
    assert P.contrast("#1b2230", "#ffffff") >= 15
    assert P.contrast("#14857f", "#ffffff") == P.contrast("#ffffff", "#14857f")
    assert P.contrast("#000", "#fff") == 21.0


def test_delta_e() -> None:
    assert P.delta_e("#14857F", "#13867F") < 1.0
    assert P.delta_e("#000000", "#ffffff") > 99
    assert P.delta_e("#14857f", "#14857f") == 0
    # Sharma et al. reference pair (Lab 50,2.6772,-79.7751 vs 50,0,-82.7485) is ~2.04; check a sRGB pair is sane
    assert 5 < P.delta_e("#ff0000", "#e60000") < 15


def test_resolve_dark_light_and_fallback(doc: dict) -> None:
    assert P.resolve(doc, "color.primary") == "#14857f"
    assert P.resolve(doc, "color.primary", "dark") == "#4fb3c4"
    assert P.resolve(doc, "color.on-primary", "dark") == "#ffffff"  # no dark: falls back to $value


def test_resolve_follows_references(doc: dict) -> None:
    assert P.resolve(doc, "color.link") == "#14857f"
    assert P.resolve(doc, "color.link", "dark") == "#4fb3c4"


def test_resolve_md_and_composite_field(doc: dict) -> None:
    assert P.resolve(doc, "typography.sm", "light")["fontSize"] == "16px"
    assert P.resolve(doc, "typography.sm", "md") == {"fontSize": "14px", "lineHeight": "20px"}
    assert P.resolve(doc, "typography.sm.fontSize", "md") == "14px"


def test_resolve_cycle_and_unknown_raise_formatted_errors() -> None:
    cyc = {"color": {"a": {"$value": "{color.b}", "$type": "color"}, "b": {"$value": "{color.a}", "$type": "color"}}}
    with pytest.raises(P.PlumbError) as e:
        P.resolve(cyc, "color.a")
    assert_formatted(e.value)
    assert "cycle" in str(e.value)
    with pytest.raises(P.PlumbError) as e2:
        P.resolve(cyc, "color.zzz")
    assert_formatted(e2.value)
    with pytest.raises(P.PlumbError) as e3:
        P.resolve(cyc, "color")
    assert_formatted(e3.value)


def test_iter_tokens_paths_and_types(doc: dict) -> None:
    found = {p: t for p, _tok, t in P.iter_tokens(doc)}
    assert found["color.primary"] == "color"
    assert found["typography.sm"] == "typography"
    assert found["spacing.4"] == "dimension"
    assert not any(p.startswith("$") for p in found)


def test_plumb_settings_defaults_and_values(doc: dict) -> None:
    s = P.plumb_settings(doc)
    assert s["project"] == "Café Ünïcode" and s["schema"] == 1
    assert s["web"]["styling"] == "tailwind-v4" and s["docs_dir"] == "docs/design"
    assert s["contrast"]["extra_pairs"] == [["on-primary", "primary", "text"]]
    d = P.plumb_settings({})
    assert d["platforms"] == ["web"] and d["web"]["copies"] == [] and d["contrast"]["extra_pairs"] == []
    assert d["docs_dir"] == "docs/design" and d["schema"] == 1


@pytest.mark.parametrize("raw,expected", [
    ("#abc", ("#aabbcc", 1.0)),
    ("#AABBCC", ("#aabbcc", 1.0)),
    ("#aabbccdd", ("#aabbcc", round(0xDD / 255, 4))),
    ({"colorSpace": "srgb", "components": [1, 0, 0], "alpha": 0.5, "hex": "#FF0000"}, ("#ff0000", 0.5)),
    ({"colorSpace": "srgb", "components": [0, 0, 1]}, ("#0000ff", 1.0)),
])
def test_parse_color_accepts(raw: object, expected: tuple) -> None:
    assert P.parse_color(raw) == expected


@pytest.mark.parametrize("raw", ["blue", "#12", "#ggg", 5, None, {"colorSpace": "display-p3", "components": [1, 0, 0]}])
def test_parse_color_rejects(raw: object) -> None:
    with pytest.raises(P.PlumbError) as e:
        P.parse_color(raw)
    assert_formatted(e.value)


def test_nearest_token_color(doc: dict) -> None:
    path, dist = P.nearest_token(doc, "color", "#13867f")
    assert path == "color.primary" and dist < 1.0


def test_nearest_token_dimension(doc: dict) -> None:
    assert P.nearest_token(doc, "dimension", "15px")[0] == "typography.sm"  # 16px wins over 12px
    assert P.nearest_token(doc, "dimension", "7px")[0] == "spacing.2"
    path, dist = P.nearest_token(doc, "spacing", "17px")
    assert path == "spacing.4" and dist == 1
    assert P.nearest_token(doc, "dimension", "wide") is None
    assert P.nearest_token({}, "color", "#fff") is None


def test_read_plumb_md(tmp_path: Path) -> None:
    text = (
        "<!-- plumb v1.0.0 · written by init -->\n# Plumb: the design system for Café Ünïcode\n\n"
        "Role: home   (home = this repo owns the tokens)\nEdit check: on\nPython: `python3`\n"
        "Mystery key: kept as-is\n<!--\nHidden: yes\n-->\n```\nFenced: ignored\n```\n"
        "UI files: app/**, components/** · *.tsx\nSee https://example.com/x for more\n"
    )
    f = tmp_path / "PLUMB.md"
    f.write_text(text, encoding="utf-8")
    md = P.read_plumb_md(f)
    assert md["Edit check"] == "on" and md["Role"] == "home" and md["Python"] == "python3"
    assert md["Mystery key"] == "kept as-is" and md["UI files"] == "app/**, components/** · *.tsx"
    assert "Hidden" not in md and "Fenced" not in md and "https" not in md
    f.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert P.read_plumb_md(f) == md
    assert P.read_plumb_md(tmp_path / "missing.md") == {}


def test_load_tokens_broken_names_file_and_line() -> None:
    with pytest.raises(P.PlumbError) as e:
        P.load_tokens(FIX / "broken.tokens.json")
    assert_formatted(e.value)
    assert "broken.tokens.json" in str(e.value) and "line 3" in str(e.value)


def test_load_tokens_missing_and_not_an_object(tmp_path: Path) -> None:
    with pytest.raises(P.PlumbError) as e:
        P.load_tokens(tmp_path / "nope.tokens.json")
    assert_formatted(e.value)
    bad = tmp_path / "list.tokens.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(P.PlumbError) as e2:
        P.load_tokens(bad)
    assert_formatted(e2.value)


def test_unicode_round_trip(tmp_path: Path, doc: dict) -> None:
    assert "🎨" in doc["$description"] and "✨" in doc["color"]["primary"]["$description"]
    assert P.plumb_settings(doc)["project"] == "Café Ünïcode"
    out = tmp_path / "ü.tokens.json"
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert P.load_tokens(out) == doc
    # a BOM (Windows editors) is tolerated
    out.write_bytes(b"\xef\xbb\xbf" + out.read_bytes())
    assert P.load_tokens(out) == doc


def test_utf8_stdio_tolerates_streams_without_reconfigure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    class Good:
        def reconfigure(self, **kw: object) -> None:
            calls.append(tuple(sorted(kw.items())))

    class Bare:
        pass

    monkeypatch.setattr(sys, "stdout", Good())
    monkeypatch.setattr(sys, "stderr", Bare())
    P.utf8_stdio()
    assert calls == [(("encoding", "utf-8"), ("errors", "replace"))]


def _nested_and_decimal() -> dict:
    return {"z": {"$type": "dimension", "1.2": {"$value": "1px"}, "1": {"2": {"$value": "2px"}}}}


def test_path_parts_is_a_pure_function_of_the_path() -> None:
    nested = {"z": {"$type": "dimension", "1": {"2": {"$value": "3px"}}}}
    decimal = {"spacing": {"$type": "dimension", "1.2": {"$value": "5px"}}}
    assert P.path_parts("spacing.1.2") == ["spacing", "1.2"]  # a plain string: the decimal reading
    paths = {p: list(P.path_parts(p)) for p, _t, _ty in P.iter_tokens(nested)}
    assert paths == {"z.1.2": ["z", "1", "2"]}  # the path iter_tokens yields carries the names the file has
    assert P.path_parts("z.1.2") == ["z", "1.2"]  # walking a document left nothing behind
    assert [list(P.path_parts(p)) for p, _t, _ty in P.iter_tokens(decimal)] == [["spacing", "1.2"]]
    assert P.resolve(nested, "z.1.2") == "3px" and P.resolve(decimal, "spacing.1.2") == "5px"


def test_a_decimal_name_next_to_the_same_nested_groups_is_refused() -> None:
    with pytest.raises(P.PlumbError) as exc:
        list(P.iter_tokens(_nested_and_decimal()))
    assert_formatted(exc.value)
    assert "z.1.2" in str(exc.value) and '"1.2"' in str(exc.value)
    with pytest.raises(P.PlumbError) as exc:
        P.resolve(_nested_and_decimal(), "z.1.2")
    assert_formatted(exc.value)
