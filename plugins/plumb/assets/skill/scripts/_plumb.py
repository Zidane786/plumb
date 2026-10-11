"""Plumb shared core: token loading and resolution, colour maths, contrast, nearest token, PLUMB.md parsing.

Imported as a sibling module by build-tokens.py, audit.py and build-prototype.py (no package).
Python 3.9+, standard library only. Errors are PlumbError with a message already shaped as
"error: ...\\nfix: ..." (or "ask the user: ..."); entry points print it and exit 2.

Token format: W3C Design Tokens (DTCG). Light values are `$value`; dark and breakpoint values live in
`$extensions["plumb"]` (`dark`, `md`). References use `{group.token}`. Machine settings live at the root in
`$extensions["plumb"]`.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Iterator, Optional, Tuple

PLUMB_VERSION = "1.0.0"
SCHEMA_VERSION = 1
EXT = "plumb"


class PlumbError(Exception):
    """Bad input. The message is already formatted: 'error: ...' then 'fix: ...' (or 'ask the user: ...')."""


def _err(what: str, fix: str) -> PlumbError:
    return PlumbError(f"error: {what}\nfix: {fix}")


def utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 (Windows consoles default to cp1252); tolerate odd streams."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is None:
            continue
        try:
            reconf(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - a stream that cannot be reconfigured is left as it is
            pass


# ---------------------------------------------------------------- reading tokens


def load_tokens(path: Path) -> dict:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise _err(f"{path}: tokens file not found", "run the project's create or extract step, or pass the right path") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{path}: cannot read the tokens file ({exc})", "save it as UTF-8 and check its permissions") from None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _err(
            f"{path.name}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            f"open {path} at line {exc.lineno} and correct the JSON (no trailing commas or comments)",
        ) from None
    if not isinstance(doc, dict):
        raise _err(f"{path.name}: the top level must be a JSON object", f"wrap the tokens in {{ ... }} in {path}")
    return doc


def is_token(node: object) -> bool:
    return isinstance(node, dict) and "$value" in node


def iter_tokens(doc: dict) -> Iterator[Tuple[str, dict, Optional[str]]]:
    """Yield (dotted path, token, $type) for every token, in document order; $type is inherited from groups."""

    def walk(node: dict, prefix: str, inherited: Optional[str]) -> Iterator[Tuple[str, dict, Optional[str]]]:
        gtype = node.get("$type", inherited) if isinstance(node.get("$type"), str) else inherited
        for key, child in node.items():
            if key.startswith("$") or not isinstance(child, dict):
                continue
            path = f"{prefix}.{key}" if prefix else key
            if is_token(child):
                ttype = child.get("$type") if isinstance(child.get("$type"), str) else gtype
                yield path, child, ttype
            else:
                yield from walk(child, path, gtype)

    yield from walk(doc, "", None)


def _find(doc: dict, path: str) -> Tuple[dict, list, Optional[str]]:
    """(token, rest-of-path into its $value, inherited $type) for a dotted path."""
    node: object = doc
    gtype: Optional[str] = None
    parts = path.split(".")
    for i, key in enumerate(parts):
        if not isinstance(node, dict) or key not in node or key.startswith("$"):
            raise _err(f"unknown token: {path}", "check the name against the tokens file (group.token, e.g. color.primary)")
        node = node[key]
        if isinstance(node, dict) and isinstance(node.get("$type"), str):
            gtype = node["$type"]
        if is_token(node):
            return node, parts[i + 1:], gtype  # type: ignore[return-value]
    raise _err(f"{path} is a group, not a token", "name a token inside it, e.g. " + path + ".<token>")


_ALIAS = re.compile(r"^\{([A-Za-z0-9_.-]+)\}$")


def _ext(token: dict) -> dict:
    ext = token.get("$extensions")
    ext = ext.get(EXT) if isinstance(ext, dict) else None
    return ext if isinstance(ext, dict) else {}


def _resolve_path(doc: dict, path: str, mode: str, stack: Tuple[str, ...]) -> object:
    if path in stack:
        chain = " -> ".join(stack + (path,))
        raise _err(f"token reference cycle: {chain}", f"change one of these tokens so it no longer points back at {path}")
    stack = stack + (path,)
    token, rest, _ = _find(doc, path)
    raw = token["$value"]
    ext = _ext(token)
    if mode == "dark" and "dark" in ext:
        raw = ext["dark"]
    elif mode == "md" and "md" in ext:
        # The web from the md breakpoint up: overrides some fields of a composite token, or replaces a simple value.
        override = ext["md"]
        raw = {**raw, **override} if isinstance(override, dict) and isinstance(raw, dict) else override
    for key in rest:
        if not isinstance(raw, dict) or key not in raw:
            raise _err(f"unknown field {key!r} in {path}", f"use one of: {', '.join(raw) if isinstance(raw, dict) else '(none, not composite)'}")
        raw = raw[key]
    return _resolve_value(doc, raw, mode, stack)


def _resolve_value(doc: dict, raw: object, mode: str, stack: Tuple[str, ...]) -> object:
    if isinstance(raw, str):
        m = _ALIAS.match(raw)
        return _resolve_path(doc, m.group(1), mode, stack) if m else raw
    if isinstance(raw, list):
        return [_resolve_value(doc, r, mode, stack) for r in raw]
    if isinstance(raw, dict) and "colorSpace" not in raw:
        return {k: _resolve_value(doc, v, mode, stack) for k, v in raw.items()}
    return raw


def resolve(doc: dict, path: str, mode: str = "light") -> object:
    """The value of a token (or of a field inside a composite: 'typography.sm.fontSize') with references followed.

    mode: light ($value) | dark (extensions.plumb.dark, else $value) | md (extensions.plumb.md merged over $value).
    """
    if mode not in ("light", "dark", "md"):
        raise _err(f"unknown mode {mode!r}", "use light, dark or md")
    return _resolve_path(doc, path, mode, ())


def plumb_settings(doc: dict) -> dict:
    """$extensions.plumb at the root with defaults filled in (unknown keys are kept)."""
    ext = doc.get("$extensions") if isinstance(doc, dict) else None
    given = ext.get(EXT) if isinstance(ext, dict) else None
    given = given if isinstance(given, dict) else {}
    web = given.get("web") if isinstance(given.get("web"), dict) else {}
    contrast_cfg = given.get("contrast") if isinstance(given.get("contrast"), dict) else {}
    out = dict(given)
    out["schema"] = given.get("schema", SCHEMA_VERSION)
    out["project"] = given.get("project", "")
    out["platforms"] = given.get("platforms", ["web"])
    out["web"] = {**web, "styling": web.get("styling", "css"), "copies": web.get("copies", [])}
    out["contrast"] = {**contrast_cfg, "extra_pairs": contrast_cfg.get("extra_pairs", [])}
    out["docs_dir"] = given.get("docs_dir", "docs/design")
    return out


# ---------------------------------------------------------------- colour


_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _bad_color(v: object) -> PlumbError:
    return _err(
        f"not a colour value: {v!r}",
        "use #rgb, #rrggbb, #rrggbbaa or a DTCG colour object with a hex field (named colours are not supported)",
    )


def parse_color(v: object) -> Tuple[str, float]:
    """('#rrggbb', alpha) from #abc, #aabbcc, #aabbccdd or a DTCG object {colorSpace, components, alpha, hex}."""
    if isinstance(v, str):
        m = _HEX.match(v.strip())
        if not m:
            raise _bad_color(v)
        h = m.group(1).lower()
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        alpha = round(int(h[6:8], 16) / 255, 4) if len(h) == 8 else 1.0
        return "#" + h[:6], alpha
    if isinstance(v, dict):
        try:
            alpha = float(v.get("alpha", 1))
        except (TypeError, ValueError):
            raise _bad_color(v) from None
        if isinstance(v.get("hex"), str):
            hexv, _ = parse_color(v["hex"])
            return hexv, alpha
        comps = v.get("components")
        if v.get("colorSpace") == "srgb" and isinstance(comps, list) and len(comps) == 3:
            try:
                return "#" + "".join(f"{round(min(1.0, max(0.0, float(c))) * 255):02x}" for c in comps), alpha
            except (TypeError, ValueError):
                pass
    raise _bad_color(v)


def _rgb(hexv: str) -> Tuple[int, int, int]:
    h = parse_color(hexv)[0]
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _linear(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _luminance(hexv: str) -> float:
    r, g, b = (_linear(c) for c in _rgb(hexv))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg_hex: str, bg_hex: str) -> float:
    """WCAG 2.x contrast ratio, rounded to 2 decimals; argument order does not matter."""
    a, b = _luminance(fg_hex), _luminance(bg_hex)
    hi, lo = max(a, b), min(a, b)
    return round((hi + 0.05) / (lo + 0.05), 2)


def _lab(hexv: str) -> Tuple[float, float, float]:
    r, g, b = (_linear(c) for c in _rgb(hexv))
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    xn, yn, zn = 0.95047, 1.0, 1.08883  # D65

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a_hex: str, b_hex: str) -> float:
    """CIEDE2000 colour difference (sRGB, D65)."""
    l1, a1, b1 = _lab(a_hex)
    l2, a2, b2 = _lab(b_hex)
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    cbar7 = ((c1 + c2) / 2) ** 7
    g = 0.5 * (1 - math.sqrt(cbar7 / (cbar7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (b1 or a1p) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (b2 or a2p) else 0.0
    dl, dc = l2 - l1, c2p - c1p
    if c1p * c2p == 0:
        dh = 0.0
    else:
        dh = h2p - h1p
        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360
    dhp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    lbar, cbarp = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbar = (h1p + h2p) / 2
    else:
        hbar = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hbar - 30)) + 0.24 * math.cos(math.radians(2 * hbar))
         + 0.32 * math.cos(math.radians(3 * hbar + 6)) - 0.20 * math.cos(math.radians(4 * hbar - 63)))
    dtheta = 30 * math.exp(-(((hbar - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cbarp ** 7 / (cbarp ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (lbar - 50) ** 2 / math.sqrt(20 + (lbar - 50) ** 2)
    sc = 1 + 0.045 * cbarp
    sh = 1 + 0.015 * cbarp * t
    rt = -math.sin(math.radians(2 * dtheta)) * rc
    return math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dhp / sh) ** 2 + rt * (dc / sc) * (dhp / sh))


# ---------------------------------------------------------------- nearest token


_PX = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(px|pt|dp|sp)?\s*$")


def _px(v: object) -> Optional[float]:
    m = _PX.match(str(v)) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else None
    return float(m.group(1)) if m else None


def nearest_token(doc: dict, kind: str, value: str) -> Optional[Tuple[str, float]]:
    """The closest token to a raw value: (token path, distance), or None when nothing comparable exists.

    kind 'color': CIEDE2000 over colour tokens (light values). kind 'dimension': absolute px difference over every
    dimension token and the fontSize of typography tokens. Any other kind is a top-level group name ('typography',
    'spacing', 'radius', ...) and limits the dimension search to that group. Ties go to the first token in the file.
    """
    best: Optional[Tuple[str, float]] = None
    if kind == "color":
        try:
            target = parse_color(value)[0]
        except PlumbError:
            return None
        for path, _tok, ttype in iter_tokens(doc):
            if ttype != "color":
                continue
            try:
                cand = parse_color(resolve(doc, path))[0]
            except PlumbError:
                continue
            d = delta_e(target, cand)
            if best is None or d < best[1]:
                best = (path, d)
        return best
    want = _px(value)
    if want is None:
        return None
    for path, _tok, ttype in iter_tokens(doc):
        if kind != "dimension" and path.split(".")[0] != kind:
            continue
        try:
            raw = resolve(doc, path)
        except PlumbError:
            continue
        if ttype == "typography" and isinstance(raw, dict):
            got = _px(raw.get("fontSize"))
        elif ttype == "dimension":
            got = _px(raw)
        else:
            got = None
        if got is None:
            continue
        d = abs(got - want)
        if best is None or d < best[1]:
            best = (path, d)
    return best


# ---------------------------------------------------------------- PLUMB.md


_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9 _/-]*?):(?:\s+(.*)|\s*)$")
_NOTE = re.compile(r"\s{2,}\([^)]*\)\s*$")


def read_plumb_md(path: Path) -> dict:
    """'Key: value' lines of PLUMB.md as a dict. Unknown keys are kept; comments, code fences, headings, bullets
    and tables are ignored; CRLF is fine; a missing file gives {}. A trailing '   (note)' is dropped from a value
    and a value wrapped in backticks is unwrapped."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, IsADirectoryError):
        return {}
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{path}: cannot read PLUMB.md ({exc})", "save it as UTF-8") from None
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out: dict = {}
    in_fence = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence or not s or s[0] in "#-*>|":
            continue
        m = _KEY.match(s)
        if not m:
            continue
        val = _NOTE.sub("", (m.group(2) or "").strip()).strip()
        if len(val) >= 2 and val[0] == val[-1] == "`":
            val = val[1:-1].strip()
        out[m.group(1).strip()] = val
    return out
