"""Plumb shared core: token loading and resolution, colour maths, contrast, nearest token, PLUMB.md parsing, the source
file helpers audit.py shares (comment masking, globs, build-output folders), and the inventory scanner:
scan_inventory(roots, exclude) lists every design value used with counts and file:line, cluster(inventory, kind) groups
near-duplicates (CIEDE2000 below 3; sizes within 1px or 6%) with the most-used value as canonical. /plumb:extract and
audit.py's inconsistency-only mode both use them.

Imported as a sibling module by build-tokens.py, audit.py and build-prototype.py (no package).
Python 3.9+, standard library only. Errors are PlumbError with a message already shaped as
"error: ...\\nfix: ..." (or "ask the user: ..."); entry points print it and exit 2.

Token format: W3C Design Tokens (DTCG). Light values are `$value`; dark and breakpoint values live in
`$extensions["plumb"]` (`dark`, `md`). References use `{group.token}`. Machine settings live at the root in
`$extensions["plumb"]`.
"""

from __future__ import annotations

import bisect
import functools
import json
import math
import os
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


# ---------------------------------------------------------------- page templates (specimen, audit report)


def find_template(skill_dir: Optional[Path], name: str) -> Optional[Path]:
    """<skill>/templates/<name>, else the templates folder next to these scripts (the plugin's masters), else None."""
    here = Path(__file__).resolve().parents[1] / "templates" / name
    for path in ([Path(skill_dir) / "templates" / name] if skill_dir is not None else []) + [here]:
        if path.is_file():
            return path
    return None


_SLOT = re.compile(r"\{\{([a-z_]+)\}\}")


def fill_template(text: str, values: dict, name: str = "template") -> str:
    """Every {{slot}} replaced in one pass (inserted text is never scanned again). An unknown slot is an error."""
    text = text.replace("\r\n", "\n").lstrip("\ufeff")

    def sub(m: "re.Match[str]") -> str:
        if m.group(1) not in values:
            raise _err(f"{name}: unknown slot {m.group(0)}", "restore the template from the Plumb plugin (assets/skill/templates/)")
        return str(values[m.group(1)])

    return _SLOT.sub(sub, text)


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
    return delta_e_lab(_lab(a_hex), _lab(b_hex))


def delta_e_lab(lab1: Tuple[float, float, float], lab2: Tuple[float, float, float]) -> float:
    """CIEDE2000 between two CIELAB colours (what delta_e computes after converting; cheaper when Labs are reused)."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
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


_PX = re.compile(r"^\s*(-?\d*\.?\d+)\s*(px|pt|dp|sp|rem)?\s*$")


def _px(v: object) -> Optional[float]:
    """A size in px from '16px', '1rem' (16px), 16, or the DTCG object form {"value": 16, "unit": "px"}."""
    if isinstance(v, dict) and "value" in v:
        v = f"{v['value']}{v.get('unit', '')}" if isinstance(v["value"], (int, float)) else None
    m = _PX.match(str(v)) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else None
    if not m:
        return None
    return float(m.group(1)) * (16 if m.group(2) == "rem" else 1)


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


# ---------------------------------------------------------------- source files (shared by audit.py and the inventory)


SOURCE_EXT = frozenset((".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".astro", ".html", ".css", ".scss", ".swift", ".kt"))
SKIP_DIRS = frozenset((
    "node_modules", ".next", "dist", "build", "out", ".git", "coverage", "Pods", "DerivedData",
    ".nuxt", ".output", ".svelte-kit", ".turbo", ".vercel", ".parcel-cache", ".cache", ".gradle", ".expo",
    "__pycache__", ".venv", "venv",
))
MAX_SOURCE_BYTES = 5 * 1024 * 1024

_STRINGS = r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`"
# Strings come first in each alternation, so "/*" or " //" inside a string never starts a comment.
_STRING_OR_COMMENT = re.compile(_STRINGS + r"|(?<![\w.*/])/\*.*?\*/|<!--.*?-->|(?:^|(?<=[\s;{}]))//[^\n]*", re.S | re.M)
_CSS_STRING_OR_COMMENT = re.compile(_STRINGS + r"|(?<![\w.*/])/\*.*?\*/", re.S)
_NOT_NL = re.compile(r"[^\n]")


def _blank(m: "re.Match[str]") -> str:
    s = m.group(0)
    return s if s[0] in "\"'`" else _NOT_NL.sub(" ", s)


def mask_comments(text: str, ext: str) -> str:
    """The text with comments replaced by spaces (newlines kept, so offsets and line numbers do not move).

    String literals are skipped over, never blanked, so a "/*" or " //" inside one cannot hide the code after it."""
    pattern = _CSS_STRING_OR_COMMENT if ext in (".css",) else _STRING_OR_COMMENT
    return pattern.sub(_blank, text)


def normalise_text(text: str) -> str:
    """No BOM, LF line endings (CRLF and CR files give the same offsets and lines as LF)."""
    if text.startswith("﻿"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def source_ext(name: str) -> Optional[str]:
    """The extension of a UI source file Plumb reads (.tsx ... .kt), or None (.d.ts and anything else)."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if base.endswith(".d.ts"):
        return None
    dot = base.rfind(".")
    ext = base[dot:] if dot > 0 else ""
    return ext if ext in SOURCE_EXT else None


@functools.lru_cache(maxsize=512)
def glob_rx(glob: str) -> "re.Pattern[str]":
    """A path glob (** any folders, * within one folder, ? one character; no wildcard = the path and below) as a regex."""
    g = glob.strip().strip("`").replace("\\", "/")
    if g.startswith("./"):
        g = g[2:]
    out, i = [], 0
    while i < len(g):
        if g.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif g.startswith("**", i):
            out.append(".*")
            i += 2
        elif g[i] == "*":
            out.append("[^/]*")
            i += 1
        elif g[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(g[i]))
            i += 1
    body = "".join(out)
    if "*" not in g and "?" not in g:
        body = body.rstrip("/") + "(?:/.*)?"
    return re.compile(body + r"\Z")


def path_matches(path: str, globs) -> bool:
    """True when the path, or any trailing part of it (so absolute and Windows paths work), matches a glob."""
    if not globs:
        return False
    rxs = [glob_rx(g) for g in globs]
    parts = path.replace("\\", "/").split("/")
    for i in range(len(parts)):
        sub = "/".join(parts[i:])
        if sub and any(rx.match(sub) for rx in rxs):
            return True
    return False


def is_generated_text(text: str) -> bool:
    """A `GENERATED ... do not edit` header in the first five lines."""
    head = "\n".join(text[:1500].splitlines()[:5])
    return "GENERATED" in head and re.search(r"do not edit", head, re.I) is not None


PROPOSAL_PAGE_GLOBS = ("*/index.html", "*/*/prototype.html", "*/*/screens.html")


def is_generated_proposal_page(text: str) -> bool:
    """A proposal page (<docs>/prototype/proposals/...) written by `build-prototype.py --proposal`: a GENERATED header
    that names that command. The one test build-prototype.py and build-tokens.py both use, so a page another tool
    generated there (or a hand-written one) is never refreshed by either."""
    head = "\n".join(text[:2000].splitlines()[:5])
    return is_generated_text(head) and re.search(r"build-prototype\.py --proposal \S", head) is not None


# ---------------------------------------------------------------- Tailwind defaults (the de-facto scale before tokens)

TAILWIND_FAMILIES = ("slate gray zinc neutral stone red orange amber yellow lime green emerald teal cyan sky blue indigo "
                     "violet purple fuchsia pink rose").split()
_SHADES = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")
_PALETTE_HEX = """
slate f8fafc f1f5f9 e2e8f0 cbd5e1 94a3b8 64748b 475569 334155 1e293b 0f172a 020617
gray f9fafb f3f4f6 e5e7eb d1d5db 9ca3af 6b7280 4b5563 374151 1f2937 111827 030712
zinc fafafa f4f4f5 e4e4e7 d4d4d8 a1a1aa 71717a 52525b 3f3f46 27272a 18181b 09090b
neutral fafafa f5f5f5 e5e5e5 d4d4d4 a3a3a3 737373 525252 404040 262626 171717 0a0a0a
stone fafaf9 f5f5f4 e7e5e4 d6d3d1 a8a29e 78716c 57534e 44403c 292524 1c1917 0c0a09
red fef2f2 fee2e2 fecaca fca5a5 f87171 ef4444 dc2626 b91c1c 991b1b 7f1d1d 450a0a
orange fff7ed ffedd5 fed7aa fdba74 fb923c f97316 ea580c c2410c 9a3412 7c2d12 431407
amber fffbeb fef3c7 fde68a fcd34d fbbf24 f59e0b d97706 b45309 92400e 78350f 451a03
yellow fefce8 fef9c3 fef08a fde047 facc15 eab308 ca8a04 a16207 854d0e 713f12 422006
lime f7fee7 ecfccb d9f99d bef264 a3e635 84cc16 65a30d 4d7c0f 3f6212 365314 1a2e05
green f0fdf4 dcfce7 bbf7d0 86efac 4ade80 22c55e 16a34a 15803d 166534 14532d 052e16
emerald ecfdf5 d1fae5 a7f3d0 6ee7b7 34d399 10b981 059669 047857 065f46 064e3b 022c22
teal f0fdfa ccfbf1 99f6e4 5eead4 2dd4bf 14b8a6 0d9488 0f766e 115e59 134e4a 042f2e
cyan ecfeff cffafe a5f3fc 67e8f9 22d3ee 06b6d4 0891b2 0e7490 155e75 164e63 083344
sky f0f9ff e0f2fe bae6fd 7dd3fc 38bdf8 0ea5e9 0284c7 0369a1 075985 0c4a6e 082f49
blue eff6ff dbeafe bfdbfe 93c5fd 60a5fa 3b82f6 2563eb 1d4ed8 1e40af 1e3a8a 172554
indigo eef2ff e0e7ff c7d2fe a5b4fc 818cf8 6366f1 4f46e5 4338ca 3730a3 312e81 1e1b4b
violet f5f3ff ede9fe ddd6fe c4b5fd a78bfa 8b5cf6 7c3aed 6d28d9 5b21b6 4c1d95 2e1065
purple faf5ff f3e8ff e9d5ff d8b4fe c084fc a855f7 9333ea 7e22ce 6b21a8 581c87 3b0764
fuchsia fdf4ff fae8ff f5d0fe f0abfc e879f9 d946ef c026d3 a21caf 86198f 701a75 4a044e
pink fdf2f8 fce7f3 fbcfe8 f9a8d4 f472b6 ec4899 db2777 be185d 9d174d 831843 500724
rose fff1f2 ffe4e6 fecdd3 fda4af fb7185 f43f5e e11d48 be123c 9f1239 881337 4c0519
"""
TAILWIND_PALETTE = {"white": "#ffffff", "black": "#000000"}
for _row in _PALETTE_HEX.strip().splitlines():
    _fam, *_hexes = _row.split()
    TAILWIND_PALETTE.update({f"{_fam}-{s}": f"#{h}" for s, h in zip(_SHADES, _hexes)})
TAILWIND_TYPE = {"xs": 12, "sm": 14, "base": 16, "lg": 18, "xl": 20, "2xl": 24, "3xl": 30, "4xl": 36, "5xl": 48, "6xl": 60,
                 "7xl": 72, "8xl": 96, "9xl": 128}
TAILWIND_RADIUS = {"xs": 2, "sm": 4, "": 4, "md": 6, "lg": 8, "xl": 12, "2xl": 16, "3xl": 24, "4xl": 32}  # v4
TAILWIND_WEIGHT = {"thin": 100, "extralight": 200, "light": 300, "normal": 400, "medium": 500, "semibold": 600,
                   "bold": 700, "extrabold": 800, "black": 900}
TAILWIND_LEADING = {"none": "1", "tight": "1.25", "snug": "1.375", "normal": "1.5", "relaxed": "1.625", "loose": "2"}
TAILWIND_EASE = {"linear": "linear", "in": "cubic-bezier(0.4, 0, 1, 1)", "out": "cubic-bezier(0, 0, 0.2, 1)",
                 "in-out": "cubic-bezier(0.4, 0, 0.2, 1)"}
_TAILWIND_MARK = re.compile(r"@tailwind\b|@import\s+[\"']tailwindcss|cdn\.tailwindcss\.com|@tailwindcss/browser|[\"']tailwindcss[\"']")


def tailwind_project(folder: Path) -> bool:
    """The folder has a tailwind.config.* or a package.json that names tailwindcss."""
    folder = Path(folder)
    for marker in ("tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs", "tailwind.config.mjs"):
        if (folder / marker).is_file():
            return True
    pkg = folder / "package.json"
    if pkg.is_file():
        try:
            return uses_tailwind(pkg.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return False
    return False


def is_text_name(key: str) -> bool:
    """A colour token name (without "color.") for text: on-*, link, or text/ink as a whole hyphen word."""
    return key.startswith("on-") or key == "link" or bool({"text", "ink"} & set(key.split("-")))


def uses_tailwind(text: str) -> bool:
    """The text loads Tailwind (@tailwind, @import "tailwindcss", the browser build, or "tailwindcss" in package.json)."""
    return _TAILWIND_MARK.search(text) is not None


# ---------------------------------------------------------------- inventory: every design value actually used


INVENTORY_KINDS = ("color", "font-family", "font-size", "font-weight", "line-height", "spacing", "radius", "shadow",
                   "duration", "easing")


def new_inventory() -> dict:
    return {k: {} for k in INVENTORY_KINDS}


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.4f}".rstrip("0").rstrip(".")


def _hex_value(digits: str) -> str:
    """#rgb/#rgba/#rrggbb/#rrggbbaa digits as lowercase #rrggbb, or #rrggbbaa when translucent."""
    d = digits.lower()
    if len(d) in (3, 4):
        d = "".join(c * 2 for c in d)
    if len(d) == 8 and d[6:] == "ff":
        d = d[:6]
    return "#" + d


def _alpha_byte(alpha: float) -> str:
    return "" if alpha >= 1 else f"{max(0, min(255, round(alpha * 255))):02x}"


def _fn_colour(name: str, args: str) -> Optional[str]:
    """rgb()/rgba()/hsl()/hsla() arguments as a hex value, or None (variables, other colour spaces)."""
    parts = [p for p in re.split(r"[\s,/]+", args.strip()) if p]
    if len(parts) < 3:
        return None
    try:
        if name.startswith("rgb"):
            rgb = [float(p[:-1]) * 2.55 if p.endswith("%") else float(p) for p in parts[:3]]
        else:
            import colorsys
            h = float(re.sub(r"deg$", "", parts[0])) / 360
            sat, light = float(parts[1].rstrip("%")) / 100, float(parts[2].rstrip("%")) / 100
            rgb = [c * 255 for c in colorsys.hls_to_rgb(h % 1, light, sat)]
        alpha = 1.0
        if len(parts) > 3:
            alpha = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
    except ValueError:
        return None
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb) + _alpha_byte(alpha)


def _px_len(num_text: str, unit: str) -> float:
    return float(num_text) * (16 if unit == "rem" else 1)


def _split_top(value: str) -> list:
    """Split a CSS value on commas that are not inside parentheses."""
    out, depth, cur = [], 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


_I_HEX = re.compile(r"(?<![\w&/#$@])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])")
_I_FN = re.compile(r"(?<![\w-])(rgba?|hsla?)\(\s*([^()]{1,80})\)", re.I)
_I_LEN = re.compile(r"(?<![\w.#-])-?(\d*\.?\d+)(px|rem)(?![\w-])")
_I_TIME = re.compile(r"(?<![\w.#-])(\d*\.?\d+)(ms|s)(?![\w-])")
_I_CURVE = re.compile(r"cubic-bezier\(\s*(-?[\d.]+)[\s,_]+(-?[\d.]+)[\s,_]+(-?[\d.]+)[\s,_]+(-?[\d.]+)\s*\)")
_I_EASE_WORD = re.compile(r"(?<![\w-])(ease-in-out|ease-in|ease-out|ease|linear|step-start|step-end)(?![\w-])")
_I_STEPS = re.compile(r"steps\([^()]{1,40}\)")
_I_DECL = re.compile(r"(?<![\w$@-])([$@]?-{0,2}[A-Za-z][\w-]*)\s*:\s*([^;{}]{1,400})")
_I_STYLE_BLOCK = re.compile(r"(<style\b[^>]*>)(.*?)(?:</style\s*>|\Z)", re.S | re.I)
_I_STYLE_ATTR = re.compile(r"(?<![\w:-])style\s*=\s*([\"'])")
_I_APPLY = re.compile(r"@apply\s[^;{}]*")
_I_SKIP_BEFORE = re.compile(r"(?:(?<![\w-])(?:href|to|xlinkHref|xlink:href|src|action|for|id|anchor|hash)\s*[=:]\s*\{?\s*[\"'`]?"
                            r"|url\(\s*[\"']?)\Z")
_I_SELECTOR_CALLS = ("querySelector(", "querySelectorAll(", "getElementById(", "closest(", "matches(")
_I_SPACING_PROP = re.compile(r"^(?:margin|padding)(?:-[a-z-]+)?$|^(?:row-|column-)?gap$")
_I_RADIUS_PROP = re.compile(r"^border(?:-[a-z]+)*-radius$")
_I_JS_PROP = re.compile(
    r"(?<![\w$.-])[\"']?(fontSize|fontWeight|lineHeight|fontFamily|padding\w*|margin\w*|gap|rowGap|columnGap"
    r"|borderRadius|border\w*Radius|boxShadow|transition\w*|animation\w*)[\"']?\s*:\s*"
    r"(?:\"([^\"\n]*)\"|'([^'\n]*)'|`([^`\n]*)`|(-?\d*\.?\d+)(?![\w.]))")
_CLS = r"(?<![^\s\"'`:{(!,])"
_TW_TEXT = re.compile(_CLS + r"text-(xs|sm|base|lg|xl|[2-9]xl|\[(\d*\.?\d+)(px|rem)\])(?![\w-])")
_TW_WEIGHT = re.compile(_CLS + r"font-(" + "|".join(TAILWIND_WEIGHT) + r")(?![\w-])")
_TW_FAMILY = re.compile(_CLS + r"font-(sans|serif|mono)(?![\w-])")
_TW_LEADING = re.compile(_CLS + r"leading-(none|tight|snug|normal|relaxed|loose|\d+(?:\.\d+)?|\[(\d*\.?\d+)(px|rem)?\])(?![\w-])")
_TW_SPACING = re.compile(_CLS + r"-?(?:p[xytrblse]?|m[xytrblse]?|gap(?:-[xy])?|space-[xy])-(\d+(?:\.\d+)?|px|\[(\d*\.?\d+)(px|rem)\])"
                         r"(?![\w./-])")
_TW_RADIUS = re.compile(_CLS + r"rounded(?:-[trblse]{1,2})?(?:-(none|xs|sm|md|lg|xl|2xl|3xl|4xl|full|\[(\d*\.?\d+)(px|rem)\]))?"
                        r"(?![\w-])")
_TW_SHADOW = re.compile(_CLS + r"(shadow-(?:2xs|xs|sm|md|lg|xl|2xl|inner))(?![\w-])")
_TW_DURATION = re.compile(_CLS + r"duration-(\d+|\[(\d*\.?\d+)(ms|s)\])(?![\w-])")
_TW_EASE = re.compile(_CLS + r"ease-(linear|in-out|in|out|\[([^\]\s]{1,80})\])(?![\w-])")
_TW_PALETTE = re.compile(
    _CLS + r"-?(?:text|bg|border(?:-[trblxyse]{1,2})?|ring(?:-offset)?|outline|fill|stroke|from|to|via|divide|decoration"
    r"|accent|caret|placeholder|shadow)-(white|black|(?:" + "|".join(TAILWIND_FAMILIES) + r")-(?:50|[1-9]00|950))"
    r"(?:/(?:\d{1,3}|\[[^\]\s]{1,20}\]))?(?![\w-])")
_SW_SIZE = re.compile(r"\.system\(\s*size:\s*(\d*\.?\d+)|systemFont\(\s*ofSize:\s*(\d*\.?\d+)"
                      r"|\.custom\(\s*\"([^\"\n]+)\"\s*,\s*(?:fixedSize|size):\s*(\d*\.?\d+)")
_SW_RADIUS = re.compile(r"(?<![\w.])cornerRadius\s*:\s*(\d*\.?\d+)|\.cornerRadius\(\s*(\d*\.?\d+)")
_SW_PADDING = re.compile(r"\.padding\(\s*(?:\.\w+\s*,\s*|\[[^\]]*\]\s*,\s*)?(\d*\.?\d+)\s*\)|(?<![\w.])spacing:\s*(\d*\.?\d+)")
_SW_RGB = re.compile(r"(?<![\w.])(?:UI|NS)?Color\(\s*(?:\.\w+\s*,\s*)?red:\s*([\d./]+)\s*,\s*green:\s*([\d./]+)\s*,\s*blue:\s*([\d./]+)")
_SW_ANIM = re.compile(r"\.(easeInOut|easeIn|easeOut|linear)\(\s*duration:\s*(\d*\.?\d+)")
_KT_SIZE = re.compile(r"fontSize\s*=\s*(\d*\.?\d+)\.sp")
_KT_RADIUS = re.compile(r"(?:RoundedCornerShape|CornerSize)\(\s*(\d*\.?\d+)\.dp")
_KT_PADDING = re.compile(r"(?:\.padding|spacedBy|PaddingValues)\(([^()]{0,160})\)")
_KT_DP = re.compile(r"(\d*\.?\d+)\.dp")
_KT_HEX = re.compile(r"(?<![\w.])Color\(\s*0[xX]([0-9A-Fa-f]{8}|[0-9A-Fa-f]{6})")
_KT_WEIGHT = re.compile(r"FontWeight\.(W[1-9]00|Thin|ExtraLight|Light|Normal|Medium|SemiBold|Bold|ExtraBold|Black)\b")
_KT_TWEEN = re.compile(r"tween\(\s*(?:durationMillis\s*=\s*)?(\d+)")
_KT_WEIGHTS = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Normal": 400, "Medium": 500, "SemiBold": 600, "Bold": 700,
               "ExtraBold": 800, "Black": 900}
_SW_EASE = {"easeInOut": "ease-in-out", "easeIn": "ease-in", "easeOut": "ease-out", "linear": "linear"}


def _easing_value(text: str) -> Optional[str]:
    m = _I_CURVE.search(text)
    if m:
        return "cubic-bezier(" + ", ".join(_fmt(float(x)) for x in m.groups()) + ")"
    m = _I_STEPS.search(text)
    if m:
        return " ".join(m.group(0).split())
    m = _I_EASE_WORD.search(text)
    return m.group(1) if m else None


def _family_value(text: str) -> Optional[str]:
    names = [n.strip().strip("\"'").strip().lower() for n in text.split(",")]
    names = [" ".join(n.split()) for n in names if n]
    if not names or names[0] in ("inherit", "initial", "unset") or names[0].startswith("var("):
        return None
    return ", ".join(names)


class _Scan:
    """One file's text being added to an inventory."""

    def __init__(self, inv: dict, name: str, code: str) -> None:
        self.inv, self.name, self.code = inv, name, code
        self._nl = [m.start() for m in re.finditer("\n", code)]

    def add(self, kind: str, value: str, pos: int) -> None:
        line = bisect.bisect_right(self._nl, pos - 1) + 1 if pos > 0 else 1
        slot = self.inv[kind].get(value)
        if slot is None:
            slot = self.inv[kind][value] = {"count": 0, "where": []}
        slot["count"] += 1
        slot["where"].append(f"{self.name}:{line}")

    def colours(self, start: int, end: int, css: bool) -> None:
        code = self.code
        for m in _I_HEX.finditer(code, start, end):
            pos, digits = m.start(), m.group(1)
            if _I_SKIP_BEFORE.search(code, max(0, pos - 40), pos):
                continue
            if not css:
                if len(digits) in (3, 4) and digits.isdigit() and code[pos - 1:pos] != "[":
                    continue  # "Order #123" is copy, not a colour
                line_start = code.rfind("\n", 0, pos) + 1
                before = code[max(line_start, pos - 150):pos]
                if any(call in before for call in _I_SELECTOR_CALLS):
                    continue
            self.add("color", _hex_value(digits), pos)
        for m in _I_FN.finditer(code, start, end):
            value = _fn_colour(m.group(1).lower(), m.group(2))
            if value:
                self.add("color", value, m.start())

    def declaration(self, prop: str, value: str, pos: int, colours: bool) -> None:
        """One CSS declaration (or a JS style property already turned into kebab-case)."""
        if colours:
            self.colours(pos, pos + len(value), True)
        prop = prop.lower()
        v = value.strip()
        if not v or v.startswith("var(") and ")" == v[-1:] and v.count("(") == 1:
            return
        if prop == "font-size":
            for m in _I_LEN.finditer(value):
                self.add("font-size", _fmt(_px_len(m.group(1), m.group(2))) + "px", pos + m.start())
        elif prop == "font-weight":
            m = re.search(r"(?<![\w-])([1-9]00|bold|normal)(?![\w-])", value)
            if m:
                self.add("font-weight", {"bold": "700", "normal": "400"}.get(m.group(1), m.group(1)), pos + m.start())
        elif prop == "line-height":
            self._line_height(v, pos + value.find(v))
        elif prop == "font-family":
            fam = _family_value(v)
            if fam:
                self.add("font-family", fam, pos + value.find(v))
        elif prop == "font":
            self._font(value, pos)
        elif _I_SPACING_PROP.match(prop):
            for m in _I_LEN.finditer(value):
                px = _px_len(m.group(1), m.group(2))
                if px:
                    self.add("spacing", _fmt(px) + "px", pos + m.start())
        elif _I_RADIUS_PROP.match(prop):
            for m in _I_LEN.finditer(value):
                px = _px_len(m.group(1), m.group(2))
                if px and px < 999:
                    self.add("radius", _fmt(px) + "px", pos + m.start())
        elif prop == "box-shadow":
            if v.lower() not in ("none", "inherit", "initial", "unset") and not v.startswith("var("):
                self.add("shadow", self._shadow(v), pos + value.find(v))
        elif prop in ("transition", "animation"):
            offset = 0
            for part in _split_top(value):
                times = list(_I_TIME.finditer(part))
                if times:
                    ms = float(times[0].group(1)) * (1000 if times[0].group(2) == "s" else 1)
                    if ms:
                        self.add("duration", _fmt(ms) + "ms", pos + offset + times[0].start())
                ease = _easing_value(part)
                if ease:
                    self.add("easing", ease, pos + offset)
                offset += len(part) + 1
        elif prop in ("transition-duration", "animation-duration"):
            for m in _I_TIME.finditer(value):
                ms = float(m.group(1)) * (1000 if m.group(2) == "s" else 1)
                if ms:
                    self.add("duration", _fmt(ms) + "ms", pos + m.start())
        elif prop in ("transition-timing-function", "animation-timing-function"):
            offset = 0
            for part in _split_top(value):
                ease = _easing_value(part)
                if ease:
                    self.add("easing", ease, pos + offset)
                offset += len(part) + 1

    def _line_height(self, v: str, pos: int) -> None:
        m = re.match(r"(\d*\.?\d+)(px|rem)?(?![\w%-])", v)
        if m:
            self.add("line-height", _fmt(_px_len(m.group(1), m.group(2))) + "px" if m.group(2) else _fmt(float(m.group(1))), pos)

    def _font(self, value: str, pos: int) -> None:
        m = re.search(r"(?<![\w.-])(\d*\.?\d+)(px|rem)(?:\s*/\s*(\d*\.?\d+(?:px|rem)?))?\s+(.+)$", value.strip())
        if not m:
            return
        base = pos + value.find(value.strip())
        self.add("font-size", _fmt(_px_len(m.group(1), m.group(2))) + "px", base + m.start())
        if m.group(3):
            self._line_height(m.group(3), base + m.start(3))
        w = re.search(r"(?<![\w-])([1-9]00|bold)(?![\w-])", value.strip()[:m.start()])
        if w:
            self.add("font-weight", "700" if w.group(1) == "bold" else w.group(1), base + w.start())
        fam = _family_value(m.group(4))
        if fam:
            self.add("font-family", fam, base + m.start(4))

    @staticmethod
    def _shadow(v: str) -> str:
        v = _I_FN.sub(lambda m: _fn_colour(m.group(1).lower(), m.group(2)) or m.group(0), v)
        v = _I_HEX.sub(lambda m: _hex_value(m.group(1)), v)
        parts = [" ".join(p.split()) for p in _split_top(v.lower())]
        return ", ".join(p for p in parts if p)

    def css(self, start: int, end: int) -> None:
        for m in _I_DECL.finditer(self.code, start, end):
            self.declaration(m.group(1), m.group(2), m.start(2), True)

    def js(self, start: int, end: int) -> None:
        for m in _I_JS_PROP.finditer(self.code, start, end):
            prop = re.sub(r"([A-Z])", lambda c: "-" + c.group(1).lower(), m.group(1))
            quoted = next((i for i in (2, 3, 4) if m.group(i) is not None), None)
            if quoted is not None:
                self.declaration(prop, m.group(quoted), m.start(quoted), False)
                continue
            pos, number = m.start(5), float(m.group(5))
            if not number:
                continue
            if prop == "font-weight":
                self.add("font-weight", _fmt(number), pos)
            elif prop == "line-height":
                self.add("line-height", _fmt(number), pos)
            elif prop == "font-size":
                self.add("font-size", _fmt(number) + "px", pos)
            elif _I_SPACING_PROP.match(prop):
                self.add("spacing", _fmt(abs(number)) + "px", pos)
            elif "radius" in prop:
                self.add("radius", _fmt(number) + "px", pos)

    def tailwind(self, start: int, end: int) -> None:
        code = self.code
        for m in _TW_TEXT.finditer(code, start, end):
            px = _px_len(m.group(2), m.group(3)) if m.group(2) else TAILWIND_TYPE[m.group(1)]
            self.add("font-size", _fmt(px) + "px", m.start())
        for m in _TW_WEIGHT.finditer(code, start, end):
            self.add("font-weight", str(TAILWIND_WEIGHT[m.group(1)]), m.start())
        for m in _TW_FAMILY.finditer(code, start, end):
            self.add("font-family", m.group(0).lstrip("\"'`:{(!, \t\n"), m.start())
        for m in _TW_LEADING.finditer(code, start, end):
            key = m.group(1)
            if key in TAILWIND_LEADING:
                value = TAILWIND_LEADING[key]
            elif m.group(2):
                value = _fmt(_px_len(m.group(2), m.group(3))) + "px" if m.group(3) else _fmt(float(m.group(2)))
            else:
                value = _fmt(float(key) * 4) + "px"
            self.add("line-height", value, m.start())
        for m in _TW_SPACING.finditer(code, start, end):
            step = m.group(1)
            px = _px_len(m.group(2), m.group(3)) if m.group(2) else 1.0 if step == "px" else float(step) * 4
            if px:
                self.add("spacing", _fmt(px) + "px", m.start())
        for m in _TW_RADIUS.finditer(code, start, end):
            size = m.group(1) or ""
            if size in ("none", "full"):
                continue
            px = _px_len(m.group(2), m.group(3)) if m.group(2) else TAILWIND_RADIUS[size]
            if px:
                self.add("radius", _fmt(px) + "px", m.start())
        for m in _TW_SHADOW.finditer(code, start, end):
            self.add("shadow", m.group(1), m.start())
        for m in _TW_DURATION.finditer(code, start, end):
            ms = float(m.group(2)) * (1000 if m.group(3) == "s" else 1) if m.group(2) else float(m.group(1))
            if ms:
                self.add("duration", _fmt(ms) + "ms", m.start())
        for m in _TW_EASE.finditer(code, start, end):
            value = TAILWIND_EASE.get(m.group(1)) or _easing_value(m.group(2).replace("_", " ") if m.group(2) else "")
            if value:
                self.add("easing", value, m.start())
        for m in _TW_PALETTE.finditer(code, start, end):
            self.add("color", TAILWIND_PALETTE[m.group(1)], m.start())

    def swift(self) -> None:
        code = self.code
        for m in _SW_SIZE.finditer(code):
            size = m.group(1) or m.group(2) or m.group(4)
            self.add("font-size", _fmt(float(size)) + "px", m.start())
            if m.group(3):
                self.add("font-family", m.group(3).strip().lower(), m.start())
        for m in _SW_RADIUS.finditer(code):
            px = float(m.group(1) or m.group(2))
            if px:
                self.add("radius", _fmt(px) + "px", m.start())
        for m in _SW_PADDING.finditer(code):
            px = float(m.group(1) or m.group(2))
            if px:
                self.add("spacing", _fmt(px) + "px", m.start())
        for m in _SW_RGB.finditer(code):
            comps = []
            for g in m.groups():
                num, _, den = g.partition("/")
                try:
                    v = float(num) / float(den) if den else float(num)
                except (ValueError, ZeroDivisionError):
                    break
                comps.append(v / 255 if v > 1 and not den else v)
            if len(comps) == 3:
                self.add("color", "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in comps), m.start())
        for m in _SW_ANIM.finditer(code):
            self.add("duration", _fmt(float(m.group(2)) * 1000) + "ms", m.start())
            self.add("easing", _SW_EASE[m.group(1)], m.start())

    def kotlin(self) -> None:
        code = self.code
        for m in _KT_SIZE.finditer(code):
            self.add("font-size", _fmt(float(m.group(1))) + "px", m.start())
        for m in _KT_RADIUS.finditer(code):
            if float(m.group(1)):
                self.add("radius", _fmt(float(m.group(1))) + "px", m.start())
        for m in _KT_PADDING.finditer(code):
            for d in _KT_DP.finditer(m.group(1)):
                if float(d.group(1)):
                    self.add("spacing", _fmt(float(d.group(1))) + "px", m.start(1) + d.start())
        for m in _KT_HEX.finditer(code):
            d = m.group(1).lower()
            argb = d if len(d) == 8 else "ff" + d
            self.add("color", _hex_value(argb[2:] + argb[:2]), m.start())
        for m in _KT_WEIGHT.finditer(code):
            w = m.group(1)
            self.add("font-weight", w[1:] if w.startswith("W") else str(_KT_WEIGHTS[w]), m.start())
        for m in _KT_TWEEN.finditer(code):
            if int(m.group(1)):
                self.add("duration", m.group(1) + "ms", m.start())


def inventory_add(inv: dict, name: str, text: str, tailwind: bool = False, code: Optional[str] = None) -> None:
    """Add every design value in one file's text to inv (see scan_inventory). name is how the file appears in "where".

    code: the text with comments masked, when the caller has it already. Call finish_inventory(inv) when done."""
    ext = source_ext(name)
    if ext is None:
        return
    if code is None:
        code = mask_comments(normalise_text(text), ext)
    scan = _Scan(inv, name, code)
    if ext == ".swift":
        scan.colours(0, len(code), False)
        scan.swift()
        return
    if ext == ".kt":
        scan.colours(0, len(code), False)
        scan.kotlin()
        return
    if ext in (".css", ".scss"):
        scan.css(0, len(code))
        if tailwind:
            for m in _I_APPLY.finditer(code):
                scan.tailwind(m.start(), m.end())
                scan.colours(m.start(), m.end(), False)
        return
    css_spans = []
    for m in _I_STYLE_BLOCK.finditer(code):
        css_spans.append(m.span(2))
    for m in _I_STYLE_ATTR.finditer(code):
        end = code.find(m.group(1), m.end(), m.end() + 2000)
        if end >= 0:
            css_spans.append((m.end(), end))
    css_spans.sort()
    pos = 0
    for start, end in css_spans:
        if start < pos:
            continue
        scan.colours(pos, start, False)
        scan.js(pos, start)
        if tailwind:
            scan.tailwind(pos, start)
        scan.css(start, end)
        pos = end
    scan.colours(pos, len(code), False)
    scan.js(pos, len(code))
    if tailwind:
        scan.tailwind(pos, len(code))


def _where_key(w: str) -> Tuple[str, int]:
    file, _, line = w.rpartition(":")
    return file, int(line) if line.isdigit() else 0


def finish_inventory(inv: dict) -> dict:
    """Sort each value's places (file, then line) and list each line once; the count keeps every occurrence."""
    for values in inv.values():
        for slot in values.values():
            slot["where"] = sorted(set(slot["where"]), key=_where_key)
    return inv


def scan_inventory(roots, exclude, base: Optional[Path] = None, tailwind: Optional[bool] = None) -> dict:
    """Every design value used under roots: {kind: {value: {"count": n, "where": ["file:line", ...]}}}.

    kinds: color (lowercase #rrggbb, #rrggbbaa when translucent), font-family (lowercase stack), font-size, spacing,
    radius (px; rem x16), font-weight (100-900), line-height (unitless or px), shadow (normalised CSS or the Tailwind
    class), duration (ms), easing (keyword or cubic-bezier(a, b, c, d)). Reads CSS/SCSS (and @apply), <style> blocks
    and style attributes, JS style objects, Tailwind classes (only when the project uses Tailwind; tailwind=None
    detects it), Swift and Kotlin. Comments, node_modules and build output, generated files, files over 5 MB and
    paths matching an exclude glob are skipped. "where" paths are relative to base (default: the folder the roots share)."""
    roots = [Path(r) for r in roots]
    if base is None:
        dirs = [str((r if r.is_dir() else r.parent).resolve()) for r in roots]
        base = Path(os.path.commonpath(dirs)) if dirs else Path.cwd()
    base = Path(base).resolve()
    found = []
    detected = False
    for root in roots:
        detected = detected or tailwind_project(root if root.is_dir() else root.parent)
        if root.is_file():
            paths = [root]
        elif root.is_dir():
            paths = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
                paths.extend(Path(dirpath) / f for f in sorted(filenames))
        else:
            continue
        for path in paths:
            if source_ext(path.name) is None:
                continue
            resolved = path.resolve()
            try:
                name = resolved.relative_to(base).as_posix()
            except ValueError:
                name = resolved.as_posix()
            if exclude and path_matches(name, exclude):
                continue
            try:
                if path.stat().st_size > MAX_SOURCE_BYTES:
                    continue
                text = normalise_text(path.read_bytes().decode("utf-8-sig", errors="replace"))
            except OSError:
                continue
            if is_generated_text(text):
                continue
            detected = detected or uses_tailwind(text)
            found.append((name, text))
    inv = new_inventory()
    use_tw = detected if tailwind is None else tailwind
    for name, text in found:
        inventory_add(inv, name, text, use_tw)
    return finish_inventory(inv)


# ---------------------------------------------------------------- clustering near-duplicates


SIZE_KINDS = ("font-size", "line-height", "spacing", "radius", "duration")
COLOUR_DELTA = 3.0  # CIEDE2000 below this: the same colour to the eye
SIZE_PX, SIZE_RATIO = 1.0, 0.06  # sizes within 1px (1ms) or 6% are the same step


def _size_of(value: str) -> Optional[Tuple[float, str]]:
    m = re.match(r"^(-?\d*\.?\d+)(px|ms)?$", value)
    return (float(m.group(1)), m.group(2) or "") if m else None


def sizes_close(a: float, b: float, unit: str = "px") -> bool:
    """Two sizes on the same step: within 1px (1ms) or 6% of the larger. Unitless values (line height) use 6% only."""
    diff = abs(a - b)
    return (bool(unit) and diff <= SIZE_PX) or diff <= SIZE_RATIO * max(abs(a), abs(b))


def cluster(inventory: dict, kind: str) -> list:
    """Near-duplicate groups of one kind: [{"canonical", "members", "count"}], most used first.

    Colours group below CIEDE2000 3 (same alpha); sizes and durations within 1px/1ms or 6%. Greedy: the most-used value
    not yet grouped is the canonical (the value to propose as a token) and takes every ungrouped value close to it.
    Other kinds (font-family, font-weight, shadow, easing) are never merged: each value is its own group."""
    values = inventory.get(kind) or {}
    items = sorted(values.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    count = {v: s["count"] for v, s in items}
    order = [v for v, _ in items]
    assigned = set()
    groups = []
    if kind == "color":
        keyed = {}
        for v in order:
            try:
                hexv, alpha = parse_color(v)
            except PlumbError:
                continue
            keyed[v] = (_lab(hexv), alpha)
        by_l = sorted(keyed, key=lambda v: keyed[v][0][0])
        ls = [keyed[v][0][0] for v in by_l]
        max_dl = COLOUR_DELTA * 1.75  # CIEDE2000 >= |dL| / SL and SL <= 1.75: no closer colour lies outside this window

        def near(v: str) -> list:
            lab, alpha = keyed[v]
            lo, hi = bisect.bisect_left(ls, lab[0] - max_dl), bisect.bisect_right(ls, lab[0] + max_dl)
            return [w for w in by_l[lo:hi] if w not in assigned and abs(keyed[w][1] - alpha) < 0.02
                    and delta_e_lab(lab, keyed[w][0]) < COLOUR_DELTA]
    elif kind in SIZE_KINDS:
        keyed = {v: s for v in order for s in [_size_of(v)] if s is not None}
        by_n = sorted(keyed, key=lambda v: keyed[v][0])
        ns = [keyed[v][0] for v in by_n]

        def near(v: str) -> list:
            n, unit = keyed[v]
            span = max(SIZE_PX if unit else 0.0, abs(n) * SIZE_RATIO / (1 - SIZE_RATIO))
            lo, hi = bisect.bisect_left(ns, n - span), bisect.bisect_right(ns, n + span)
            return [w for w in by_n[lo:hi] if w not in assigned and keyed[w][1] == unit and sizes_close(n, keyed[w][0], unit)]
    else:
        keyed = {}

        def near(v: str) -> list:
            return []
    for v in order:
        if v in assigned:
            continue
        assigned.add(v)
        members = [v]
        if v in keyed:
            close = near(v)
            assigned.update(close)
            members += sorted(close, key=lambda w: (-count[w], w))
        groups.append({"canonical": v, "members": members, "count": sum(count[m] for m in members)})
    groups.sort(key=lambda g: -g["count"])
    return groups
