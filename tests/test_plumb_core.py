"""_plumb.py: the shared token, colour and contrast core every engine script imports."""

from __future__ import annotations

import json
import os
import re
import sys
import time
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
    assert P.contrast("#ffffff", "#14857f") == 4.47  # 4.4765: shown floored to 2 decimals, never rounded up
    assert P.contrast("#ffffff", "#13817b") == 4.71  # 4.7151
    assert P.contrast("#1b2230", "#ffffff") >= 15
    assert P.contrast("#14857f", "#ffffff") == P.contrast("#ffffff", "#14857f")
    assert P.contrast("#000", "#fff") == 21.0


def test_contrast_is_compared_unrounded_and_shown_floored() -> None:
    # #008580 on white is 4.49995:1. WCAG does not round: it fails 4.5:1, and it is never shown as 4.50.
    raw = P.contrast_ratio("#008580", "#ffffff")
    assert 4.4999 < raw < 4.5
    assert P.contrast("#008580", "#ffffff") == 4.49
    assert P.ratio_text(raw) == "4.49"
    assert P.ratio_text(4.57) == "4.57" and P.ratio_text(21.0) == "21.00" and P.ratio_text(4.5) == "4.50"
    assert P.contrast_ratio("#ffffff", "#008580") == raw


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


@pytest.mark.parametrize("value, expected", [
    ("oklch(1 0 0)", ("#ffffff", 1.0)),
    ("oklch(0 0 0)", ("#000000", 1.0)),
    # Tailwind v4's neutral and red steps (oklch) and their published sRGB hex
    ("oklch(0.145 0 0)", ("#0a0a0a", 1.0)),
    ("oklch(0.205 0 0)", ("#171717", 1.0)),
    ("oklch(0.556 0 0)", ("#737373", 1.0)),
    ("oklch(0.922 0 0)", ("#e5e5e5", 1.0)),
    ("oklch(0.985 0 0)", ("#fafafa", 1.0)),
    ("oklch(0.577 0.245 27.325)", ("#e7000b", 1.0)),
    # sRGB red in OKLab / OKLCH (Ottosson's reference values), with % lightness and deg hue
    ("oklab(0.62796 0.22486 0.12585)", ("#ff0000", 1.0)),
    ("oklch(62.8% 0.2577 29.23deg)", ("#ff0000", 1.0)),
    ("OKLCH(0.6279 0.2577 29.23)", ("#ff0000", 1.0)),
    # alpha as shadcn writes it
    ("oklch(1 0 0 / 10%)", ("#ffffff", 0.1)),
    ("oklch(1 0 0 / 0.06)", ("#ffffff", 0.06)),
])
def test_parse_color_reads_oklch_and_oklab(value: str, expected: tuple) -> None:
    assert P.parse_color(value) == expected


def test_parse_color_clips_out_of_gamut_and_refuses_bad_oklch() -> None:
    assert P.parse_color("oklch(0.7 0.4 145)")[0].startswith("#")  # far outside sRGB: clipped, not an error
    for bad in ("oklch(1 0)", "oklch(a b c)", "lch(50 30 20)"):
        with pytest.raises(P.PlumbError) as exc:
            P.parse_color(bad)
        assert_formatted(exc.value)


# ---------------------------------------------------------------- reading project files (regular files only, bounded)

_POSIX = os.name == "posix"


def test_read_project_bytes_reads_a_regular_file(tmp_path: Path) -> None:
    f = tmp_path / "a.css"
    f.write_bytes(b"\xef\xbb\xbfa { color: red; }\r\n")
    assert P.read_project_bytes(f) == b"\xef\xbb\xbfa { color: red; }\r\n"
    assert P.read_project_text(f) == "a { color: red; }\r\n"  # utf-8-sig by default
    with pytest.raises(FileNotFoundError):
        P.read_project_bytes(tmp_path / "missing.css")


def test_read_project_bytes_refuses_a_file_over_the_limit(tmp_path: Path) -> None:
    f = tmp_path / "big.css"
    f.write_bytes(b"x" * 101)
    with pytest.raises(OSError):
        P.read_project_bytes(f, limit=100)
    assert P.read_project_bytes(f, limit=101) == b"x" * 101


@pytest.mark.skipif(not _POSIX, reason="requires POSIX: FIFO")
def test_read_project_bytes_refuses_a_fifo_without_waiting(tmp_path: Path) -> None:
    fifo = tmp_path / "hang.css"
    os.mkfifo(fifo)
    start = time.monotonic()
    with pytest.raises(OSError):
        P.read_project_bytes(fifo)
    assert time.monotonic() - start < 2


@pytest.mark.skipif(not _POSIX or not os.path.exists("/dev/zero"), reason="requires POSIX: /dev/zero")
def test_a_tokens_file_linked_to_a_device_is_refused_quickly(tmp_path: Path) -> None:
    link = tmp_path / "demo.tokens.json"
    link.symlink_to("/dev/zero")
    start = time.monotonic()
    with pytest.raises(OSError):
        P.read_project_bytes(link)
    with pytest.raises(P.PlumbError) as err:
        P.load_tokens(link)
    assert time.monotonic() - start < 2
    assert_formatted(err.value)
    assert "not a regular file" in str(err.value)


def test_read_project_head_reads_only_the_start(tmp_path: Path) -> None:
    f = tmp_path / "page.html"
    f.write_bytes(b"a" * 5000)
    assert P.read_project_head(f) == b"a" * P.PAGE_HEAD_BYTES
    assert P.read_project_head(f, 10) == b"a" * 10
    with pytest.raises(OSError):  # a folder (IsADirectoryError on POSIX, PermissionError on Windows)
        P.read_project_bytes(tmp_path)


def test_the_python_pattern_matches_the_hooks() -> None:
    hooklib = (REPO / "plugins/plumb/hooks/_hooklib.py").read_text(encoding="utf-8")
    m = re.search(r'^_SAFE_PYTHON = re\.compile\(r"(.*)"\)$', hooklib, re.M)
    assert m and m.group(1) == P.SAFE_PYTHON.pattern
    for ok in ("python3", "py -3", "py", "python", "python3.12", "/usr/bin/python3", "C:\\Python39\\python.exe"):
        assert P.SAFE_PYTHON.fullmatch(ok), ok
    for bad in ("python3 -c 'x'", "python3; rm -rf ~", "$(evil)", "node", "C:/Program Files/python.exe"):
        assert not P.SAFE_PYTHON.fullmatch(bad), bad
