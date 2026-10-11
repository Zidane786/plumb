#!/usr/bin/env python3
"""build-tokens.py: turn the one tokens JSON into the web CSS and the SwiftUI / Jetpack Compose themes.

Usage: build-tokens.py [--check] [--root SKILL_DIR] [--project PATH]

Reads <skill>/assets/tokens/*.tokens.json (exactly one) and the web template, writes
<skill>/assets/platforms/web/tokens.css (+ tailwind.tokens.js for tailwind-v3) and the copies listed in
$extensions.plumb.web.copies (relative to the project root), plus assets/platforms/mobile/ios/<Project>Theme.swift and
mobile/android/<Project>Theme.kt for the platforms listed in $extensions.plumb.platforms. --check writes nothing: it exits 1 naming every stale or
missing file. Exit codes: 0 ok, 1 stale (--check), 2 bad input (error: ... then fix: ...).

Python 3.9+, standard library only. Declarations follow the order of the tokens file
(deterministic, keeps the file's grouping). Imports the shared core _plumb.py from its own directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _plumb as P  # noqa: E402
from _plumb import PlumbError  # noqa: E402

STYLINGS = ("tailwind-v4", "tailwind-v3", "css")
TEMPLATE_NAME = "tokens.css.template"
SCRIPT_REL = "scripts/build-tokens.py"


def _err(what: str, fix: str) -> PlumbError:
    return PlumbError(f"error: {what}\nfix: {fix}")


# ---------------------------------------------------------------- locations


def find_project_root(skill_dir: Path, project: Optional[Path] = None) -> Path:
    """Ruling A: nearest ancestor of the skill dir holding PLUMB.md, else --project, else skill_dir.parents[2]."""
    skill_dir = Path(skill_dir).resolve()
    for parent in skill_dir.parents:
        if (parent / "PLUMB.md").is_file():
            return parent
    if project is not None:
        return Path(project).resolve()
    parents = skill_dir.parents
    return parents[2] if len(parents) > 2 else skill_dir


def rel(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def find_tokens_file(skill_dir: Path) -> Path:
    folder = skill_dir / "assets" / "tokens"
    found = sorted(folder.glob("*.tokens.json")) if folder.is_dir() else []
    if len(found) == 1:
        return found[0]
    if not found:
        raise _err(
            f"no tokens file in {folder} (expected one *.tokens.json)",
            "run the project's create or extract step to make the tokens file, or pass --root with the skill folder",
        )
    names = ", ".join(f.name for f in found)
    raise _err(f"several tokens files in {folder}: {names}", "keep exactly one *.tokens.json there and move the others away")


# ---------------------------------------------------------------- value formatting


def num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else repr(float(x)).rstrip("0").rstrip(".")


def dimension_css(v: object) -> str:
    """A dimension or duration as CSS: '16px' as given, {value, unit} -> '16px', a bare number as is."""
    if isinstance(v, dict) and "value" in v:
        unit = v.get("unit", "")
        return f"{num(v['value'])}{unit}" if isinstance(v["value"], (int, float)) else f"{v['value']}{unit}"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return num(v)
    if isinstance(v, str):
        return v
    raise _err(f"not a dimension: {v!r}", 'write it as "16px" or {"value": 16, "unit": "px"}')


def color_css(v: object) -> str:
    hexv, alpha = P.parse_color(v)
    if alpha >= 1:
        return hexv
    r, g, b = int(hexv[1:3], 16), int(hexv[3:5], 16), int(hexv[5:7], 16)
    return f"rgb({r} {g} {b} / {alpha:.2f})"


def _is_color(v: object) -> bool:
    return isinstance(v, dict) and "colorSpace" in v


def value_css(v: object, ttype: Optional[str]) -> str:
    if ttype == "color" or _is_color(v):
        return color_css(v)
    if ttype == "cubicBezier" and isinstance(v, list):
        return "cubic-bezier(" + ", ".join(num(x) for x in v) + ")"
    if ttype == "fontFamily":
        if isinstance(v, list):
            return ", ".join(f'"{f}"' if " " in str(f) else str(f) for f in v)
        return str(v)
    if ttype == "shadow":
        layers = v if isinstance(v, list) else [v]
        out = []
        for layer in layers:
            if isinstance(layer, str):
                out.append(layer)
                continue
            if not isinstance(layer, dict):
                raise _err(f"not a shadow value: {layer!r}", "use a list of {offsetX, offsetY, blur, spread, color} objects")
            parts = [dimension_css(layer.get(k, "0px")) for k in ("offsetX", "offsetY", "blur")]
            spread = dimension_css(layer.get("spread", "0px"))
            if spread not in ("0", "0px"):
                parts.append(spread)
            parts.append(color_css(layer.get("color", "#000000")))
            out.append(("inset " if layer.get("inset") else "") + " ".join(parts))
        return ", ".join(out)
    if ttype in ("dimension", "duration") or (isinstance(v, dict) and "unit" in v):
        return dimension_css(v)
    if isinstance(v, bool):
        raise _err(f"cannot format {v!r} as CSS", "use a string or a number")
    if isinstance(v, (int, float)):
        return num(v)
    if isinstance(v, str):
        return v
    raise _err(f"cannot format {v!r} as CSS", "check the token's $type and $value")


# ---------------------------------------------------------------- variables from tokens


_ALIAS = re.compile(r"^\{([A-Za-z0-9_.-]+)\}$")
FIELD_TYPES = {"fontSize": "dimension", "lineHeight": "dimension", "letterSpacing": "dimension", "fontFamily": "fontFamily"}
TYPO_FIELDS = (("fontSize", ""), ("lineHeight", "--line-height"), ("letterSpacing", "--letter-spacing"),
               ("fontWeight", "--font-weight"), ("fontFamily", "--font-family"))


def varname(path: str) -> str:
    parts = path.split(".")
    group, rest = parts[0], "-".join(parts[1:])
    if group == "motion" and len(parts) > 2:
        sub = "-".join(parts[2:])
        if parts[1] == "duration":
            return f"--duration-{sub}"
        if parts[1] == "easing":
            return f"--ease-{sub}"
        return f"--motion-{parts[1]}-{sub}"
    if group == "color":
        return f"--color-{rest}"
    if group == "label":
        return f"--color-label-{rest}"
    if group == "typography":
        return f"--text-{rest}"
    return f"--{group}-{rest}" if rest else f"--{group}"


def _token_ext(token: dict) -> dict:
    ext = token.get("$extensions")
    ext = ext.get(P.EXT) if isinstance(ext, dict) else None
    return ext if isinstance(ext, dict) else {}


def _alias_target(raw: object) -> Optional[str]:
    m = _ALIAS.match(raw) if isinstance(raw, str) else None
    return m.group(1) if m else None


def _decls(doc: dict, path: str, token: dict, ttype: Optional[str], mode: str) -> List[Tuple[str, str]]:
    """The (custom property, value) pairs one token contributes in a mode (light | dark | md)."""
    name = varname(path)
    ext = _token_ext(token)
    try:
        value = P.resolve(doc, path, mode)
        if ttype == "typography" and isinstance(value, dict):
            base = P.resolve(doc, path, "light")
            out = []
            for key, suffix in TYPO_FIELDS:
                if key in value and (mode == "light" or value[key] != base.get(key)):
                    out.append((name + suffix, value_css(value[key], FIELD_TYPES.get(key))))
            return out
        raw = ext[mode] if mode in ext else token["$value"]
        target = _alias_target(raw)
        if target is not None and not isinstance(value, dict) and ttype != "typography":
            return [(name, f"var({varname(target)})")]
        return [(name, value_css(value, ttype))]
    except PlumbError as exc:
        text = str(exc)
        if text.startswith(f"error: {path}") or "token reference cycle" in text or "unknown token" in text:
            raise
        first, _, rest = text.partition("\n")
        raise PlumbError(f"error: {path}: {first[len('error: '):]}\n{rest}") from None


def declarations(doc: dict, mode: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for path, token, ttype in P.iter_tokens(doc):
        if mode != "light" and mode not in _token_ext(token):
            continue
        out.extend(_decls(doc, path, token, ttype, mode))
    return out


# ---------------------------------------------------------------- template


PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9._-]+)(@dark|@md)?(?:\|([a-z]+))?\s*\}\}")
DIRECTIVE_LINE = re.compile(r"^([ \t]*)\{\{@([A-Za-z0-9-]+)\}\}[ \t]*$", re.M)
IF_MD = re.compile(r"^[ \t]*\{\{@if-md\}\}[ \t]*\n.*?^[ \t]*\{\{@end\}\}[ \t]*\n\n?", re.M | re.S)
DIRECTIVE_ANY = re.compile(r"\{\{@([A-Za-z0-9-]+)\}\}")


def header_text(skill_dir: Path, tokens_file: Path, root: Path) -> str:
    script = rel(skill_dir / SCRIPT_REL, root)
    src = rel(tokens_file, root)
    return f"GENERATED by {script} from {src}. Do not edit: edit the tokens JSON, then run build-tokens.py."


def read_template(skill_dir: Path, styling: str) -> str:
    folder = skill_dir / "assets" / "platforms" / "web"
    for name in (TEMPLATE_NAME, f"{TEMPLATE_NAME}.{styling}"):
        path = folder / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as exc:
                raise _err(f"{path}: cannot read the template ({exc})", "save it as UTF-8") from None
            return text.replace("\r\n", "\n").replace("\r", "\n")
    raise _err(
        f"missing web template {folder / TEMPLATE_NAME}",
        f"copy {TEMPLATE_NAME}.{styling} from the Plumb plugin's assets/skill/assets/platforms/web/ to {folder / TEMPLATE_NAME}",
    )


def _lines(decls: List[Tuple[str, str]]) -> List[str]:
    return [f"{n}: {v};" for n, v in decls]


def build_css(doc: dict, template: str, header: str) -> str:
    directives: Dict[str, Callable[[], List[str]]] = {
        "header": lambda: [header],
        "vars": lambda: _lines(declarations(doc, "light")),
        "vars-dark": lambda: _lines(declarations(doc, "dark")),
        "vars-md": lambda: _lines(declarations(doc, "md")),
    }

    def run_directive(name: str) -> List[str]:
        if name not in directives:
            raise _err(f"unknown template directive {{{{@{name}}}}}", f"use one of: {', '.join('@' + d for d in directives)}")
        return directives[name]()

    def block(m: "re.Match[str]") -> str:
        lines = run_directive(m.group(2))
        if not lines:
            return "\x00DROP\x00"
        return "\n".join(m.group(1) + line for line in lines)

    if not directives["vars-md"]():  # no md tokens: drop the whole {{@if-md}} ... {{@end}} section
        template = IF_MD.sub("", template)
    template = re.sub(r"^[ \t]*\{\{@(?:if-md|end)\}\}[ \t]*\n", "", template, flags=re.M)
    out = DIRECTIVE_LINE.sub(block, template)
    out = re.sub(r"\x00DROP\x00\n?", "", out)
    out = DIRECTIVE_ANY.sub(lambda m: " ".join(run_directive(m.group(1))), out)

    def sub(m: "re.Match[str]") -> str:
        path, variant, flt = m.group(1), m.group(2), m.group(3)
        mode = {"@dark": "dark", "@md": "md"}.get(variant or "", "light")
        try:
            v = P.resolve(doc, path, mode)
        except PlumbError as exc:
            raise _err(f"template placeholder {m.group(0)}: {str(exc).splitlines()[0][len('error: '):]}",
                       "fix the name in the template or add the token to the tokens file") from None
        if flt == "percent":
            return num(round(float(v) * 100, 4)) + "%"
        if flt == "s":
            text = dimension_css(v)
            mm = re.fullmatch(r"([\d.]+)ms", text)
            if not mm:
                raise _err(f"{m.group(0)}: |s needs a duration in ms, got {text}", "use a duration token written like 150ms")
            return num(float(mm.group(1)) / 1000) + "s"
        if flt:
            raise _err(f"unknown filter |{flt} in {m.group(0)}", "use |percent or |s")
        token_type = _type_of(doc, path)
        return value_css(v, token_type)

    out = PLACEHOLDER.sub(sub, out)
    left = re.search(r"\{\{[^}]*\}\}", out)
    if left:
        raise _err(f"unresolved placeholder in the template: {left.group(0)}", "use {{group.token}}, {{group.token@dark}} or {{@vars}}")
    if "GENERATED by" not in out[:400]:
        out = f"/* {header} */\n" + out
    return out


def _type_of(doc: dict, path: str) -> Optional[str]:
    for p, _tok, ttype in P.iter_tokens(doc):
        if p == path:
            return ttype
    parent = path.rsplit(".", 1)[0]  # a field of a composite, e.g. typography.sm.fontSize
    for p, _tok, ttype in P.iter_tokens(doc):
        if p == parent:
            field = path.rsplit(".", 1)[1]
            return FIELD_TYPES.get(field)
    return None


# ---------------------------------------------------------------- tailwind v3 map


def build_tailwind_js(doc: dict, header: str) -> str:
    sections: Dict[str, Dict[str, object]] = {k: {} for k in ("colors", "borderRadius", "spacing", "boxShadow", "fontFamily",
                                                              "fontSize", "transitionDuration", "transitionTimingFunction")}
    for path, _tok, ttype in P.iter_tokens(doc):
        parts = path.split(".")
        group, key = parts[0], "-".join(parts[1:])
        ref = f"var({varname(path)})"
        if group == "color":
            sections["colors"][key] = ref
        elif group == "label":
            sections["colors"][f"label-{key}"] = ref
        elif group == "radius":
            sections["borderRadius"][key] = ref
        elif group == "spacing":
            sections["spacing"][key] = ref
        elif group == "shadow":
            sections["boxShadow"][key] = ref
        elif group == "font":
            sections["fontFamily"][key] = ref
        elif group == "typography":
            value = P.resolve(doc, path)
            extra = {}
            if isinstance(value, dict):
                for field, suffix in (("lineHeight", "--line-height"), ("letterSpacing", "--letter-spacing"),
                                      ("fontWeight", "--font-weight")):
                    if field in value:
                        extra[field] = f"var({varname(path)}{suffix})"
            sections["fontSize"][key] = [ref, extra]
        elif group == "motion" and len(parts) > 2 and parts[1] == "duration":
            sections["transitionDuration"]["-".join(parts[2:])] = ref
        elif group == "motion" and len(parts) > 2 and parts[1] == "easing":
            sections["transitionTimingFunction"]["-".join(parts[2:])] = ref
    body = {k: v for k, v in sections.items() if v}
    text = json.dumps(body, indent=2, ensure_ascii=False)
    return (
        f"/* {header} */\n"
        "/* Use in tailwind.config.js: theme: { extend: require('./path/to/tailwind.tokens.js') } */\n"
        f"module.exports = {text};\n"
    )


# ---------------------------------------------------------------- mobile themes (SwiftUI, Jetpack Compose)


MOBILE_PLATFORMS = ("ios", "android")
SWIFT_KEYWORDS = frozenset(
    "associatedtype class deinit enum extension fileprivate func import init inout internal let open operator private "
    "protocol public rethrows static struct subscript typealias var break case continue default defer do else fallthrough "
    "for guard if in repeat return switch where while as false is nil self super throw throws true try Any Self".split()
)
KOTLIN_KEYWORDS = frozenset(
    "as break class continue do else false for fun if in interface is null object package return super this throw true "
    "try typealias typeof val var when while".split()
)
GENERIC_FAMILIES = frozenset(
    "system-ui ui-sans-serif ui-serif ui-monospace ui-rounded sans-serif serif monospace cursive fantasy "
    "-apple-system blinkmacsystemfont segoe-ui".split()
)
GENERIC_FAMILIES = GENERIC_FAMILIES | {"segoe ui", "helvetica neue", "arial", "roboto"}
SWIFT_WEIGHTS = {100: ".ultraLight", 200: ".thin", 300: ".light", 400: ".regular", 500: ".medium", 600: ".semibold",
                 700: ".bold", 800: ".heavy", 900: ".black"}
M3_COLORS = (  # Material 3 role -> the token names (in the color group) that can fill it, first found wins
    ("primary", ("primary-fill", "primary")),
    ("onPrimary", ("on-primary-fill", "on-primary")),
    ("primaryContainer", ("primary-container",)),
    ("onPrimaryContainer", ("on-primary-container",)),
    ("secondary", ("secondary",)),
    ("onSecondary", ("on-secondary",)),
    ("tertiary", ("tertiary",)),
    ("onTertiary", ("on-tertiary",)),
    ("background", ("background",)),
    ("onBackground", ("on-background", "on-surface")),
    ("surface", ("surface",)),
    ("onSurface", ("on-surface",)),
    ("surfaceVariant", ("surface-variant",)),
    ("onSurfaceVariant", ("on-surface-variant",)),
    ("surfaceContainerLowest", ("surface-container-lowest",)),
    ("surfaceContainerLow", ("surface-container-low",)),
    ("surfaceContainer", ("surface-container",)),
    ("surfaceContainerHigh", ("surface-container-high",)),
    ("surfaceContainerHighest", ("surface-container-highest",)),
    ("inverseSurface", ("inverse-surface",)),
    ("inverseOnSurface", ("inverse-on-surface",)),
    ("outline", ("outline",)),
    ("outlineVariant", ("outline-variant",)),
    ("error", ("error", "danger")),
    ("onError", ("on-error", "on-danger")),
    ("errorContainer", ("error-container", "danger-container")),
    ("onErrorContainer", ("on-error-container", "on-danger-container")),
    ("scrim", ("scrim",)),
)
M3_TYPE_ROLES = ("displayLarge", "displayMedium", "displaySmall", "headlineLarge", "headlineMedium", "headlineSmall",
                 "titleLarge", "titleMedium", "titleSmall", "bodyLarge", "bodyMedium", "bodySmall", "labelLarge",
                 "labelMedium", "labelSmall")
M3_SHAPES = ("extraSmall", "small", "medium", "large", "extraLarge")
DIMENSION_GROUPS = (("radius", "Radius", ""), ("spacing", "Spacing", "s"), ("size", "Size", ""), ("border", "Border", ""))


def pascal(name: str) -> str:
    """'café-ünïcode' -> 'CafeUnicode': diacritics stripped, non-alphanumerics dropped, words capitalised."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(name)) if not unicodedata.combining(c))
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", plain) if w)


def camel(name: str, keywords: frozenset = frozenset()) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", str(name)) if w]
    out = (words[0][:1].lower() + words[0][1:] if words else "") + "".join(w[:1].upper() + w[1:] for w in words[1:])
    if out[:1].isdigit() or not out:
        out = "n" + out
    return f"`{out}`" if out in keywords else out


def _q(text: object) -> str:
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _one_line(text: object) -> str:
    return " ".join(str(text).split())


def _dim(path: str, v: object) -> float:
    """A dimension in px (rem and em count 16px)."""
    if isinstance(v, dict) and "value" in v:
        number, unit = v["value"], str(v.get("unit", "px"))
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        number, unit = v, "px"
    elif isinstance(v, str):
        m = re.fullmatch(r"\s*(-?[\d.]+)\s*(px|rem|em)?\s*", v)
        if not m:
            raise _err(f"{path}: not a dimension for the mobile themes: {v!r}", 'write it as "16px" or {"value": 16, "unit": "px"}')
        number, unit = m.group(1), m.group(2) or "px"
    else:
        raise _err(f"{path}: not a dimension for the mobile themes: {v!r}", 'write it as "16px" or {"value": 16, "unit": "px"}')
    try:
        n = float(number)
    except (TypeError, ValueError):
        raise _err(f"{path}: not a dimension for the mobile themes: {v!r}", 'write it as "16px"') from None
    if unit in ("rem", "em"):
        return n * 16
    if unit != "px":
        raise _err(f"{path}: unit {unit!r} has no mobile equivalent", "use px (or rem, counted as 16px)")
    return n


def _ms(path: str, v: object) -> float:
    if isinstance(v, dict) and "value" in v:
        number, unit = v["value"], str(v.get("unit", "ms"))
    elif isinstance(v, str):
        m = re.fullmatch(r"\s*([\d.]+)\s*(ms|s)\s*", v)
        if not m:
            raise _err(f"{path}: not a duration: {v!r}", 'write it as "150ms"')
        number, unit = m.group(1), m.group(2)
    else:
        raise _err(f"{path}: not a duration: {v!r}", 'write it as "150ms"')
    try:
        n = float(number)
    except (TypeError, ValueError):
        raise _err(f"{path}: not a duration: {v!r}", 'write it as "150ms"') from None
    return n * 1000 if unit == "s" else n


def _number(path: str, v: object) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise _err(f"{path}: expected a number, got {v!r}", "write it as a plain number")
    return float(v)


def _color_pair(doc: dict, path: str) -> Tuple[str, float, str, float]:
    lh, la = P.parse_color(P.resolve(doc, path, "light"))
    dh, da = P.parse_color(P.resolve(doc, path, "dark"))
    return lh, la, dh, da


def _rgb_int(hexv: str) -> str:
    return "0x" + hexv[1:].upper()


def _check_unique(kind: str, names: List[str]) -> None:
    seen = set()
    for n in names:
        if n in seen:
            raise _err(f"two {kind} tokens produce the same mobile name {n.strip('`')!r}", "rename one of them in the tokens file")
        seen.add(n)


def _entries(doc: dict, group: str) -> List[Tuple[str, str, dict, Optional[str]]]:
    """(name parts joined by '-', path, token, $type) for the tokens under one top-level group."""
    return [("-".join(p.split(".")[1:]), p, t, ty) for p, t, ty in P.iter_tokens(doc) if p.split(".")[0] == group and "." in p]


class MobileData:
    """Everything the two themes are written from, read once from the tokens (only what is present)."""

    def __init__(self, doc: dict, icons: Optional[List[dict]]) -> None:
        self.icons = icons
        self.colors: List[Tuple[str, str, str, float, str, float, str]] = []  # key, name, light, a, dark, a, description
        for path, token, ttype in P.iter_tokens(doc):
            if ttype != "color":
                continue
            parts = path.split(".")
            key = "-".join(parts[1:]) if parts[0] == "color" and len(parts) > 1 else "-".join(parts)
            lh, la, dh, da = _color_pair(doc, path)
            self.colors.append((key, key, lh, la, dh, da, _one_line(token.get("$description", ""))))
        _check_unique("colour", [camel(c[0]) for c in self.colors])
        self.families = self._families(doc)
        self.type_scale = self._type_scale(doc)
        self.dims: List[Tuple[str, str, str, List[Tuple[str, float]]]] = []  # group, swift/kotlin suffix, prefix, entries
        for group, suffix, prefix in DIMENSION_GROUPS:
            ents = [(prefix + name, _dim(path, P.resolve(doc, path))) for name, path, _t, ty in _entries(doc, group)
                    if ty == "dimension"]
            if ents:
                _check_unique(group, [camel(n) for n, _ in ents])
                self.dims.append((group, suffix, prefix, ents))
        self.shadows = self._shadows(doc)
        self.durations: List[Tuple[str, float]] = []
        self.beziers: List[Tuple[str, List[float]]] = []
        self.motion_dims: List[Tuple[str, float]] = []
        self.motion_numbers: List[Tuple[str, float]] = []
        for name, path, _tok, ttype in _entries(doc, "motion"):
            sub = name.split("-", 1)[1] if name.split("-")[0] in ("duration", "easing") and "-" in name else name
            value = P.resolve(doc, path)
            if ttype == "duration":
                self.durations.append((sub, _ms(path, value)))
            elif ttype == "cubicBezier":
                if not (isinstance(value, list) and len(value) == 4):
                    raise _err(f"{path}: a cubic bezier needs four numbers", "write it as [0.2, 0.8, 0.2, 1]")
                self.beziers.append((sub, [_number(path, x) for x in value]))
            elif ttype == "dimension":
                self.motion_dims.append((name, _dim(path, value)))
            elif ttype == "number":
                self.motion_numbers.append((name, _number(path, value)))
        _check_unique("motion", [camel(n) for n, _ in self.durations] + ["ease" + pascal(n) for n, _ in self.beziers]
                      + [camel(n) for n, _ in self.motion_dims + self.motion_numbers])

    @staticmethod
    def _families(doc: dict) -> List[str]:
        for path, _tok, ttype in P.iter_tokens(doc):
            if ttype == "fontFamily":
                value = P.resolve(doc, path)
                names = value if isinstance(value, list) else [value]
                return [str(n) for n in names if isinstance(n, str)]
        return []

    def family(self) -> Optional[str]:
        """The first named (non-generic) family, which the app must bundle; None means the system font."""
        for name in self.families:
            if name.strip().lower() not in GENERIC_FAMILIES:
                return name
        return None

    @staticmethod
    def _type_scale(doc: dict) -> List[Tuple[str, float, int, float, float]]:
        """(name, size px, weight, line height multiplier, letter spacing em), in the file's order."""
        out = []
        for path, _tok, ttype in P.iter_tokens(doc):
            if ttype != "typography":
                continue
            parts = path.split(".")
            name = "-".join(parts[1:]) if parts[0] == "typography" and len(parts) > 1 else "-".join(parts)
            t = P.resolve(doc, path)
            if not isinstance(t, dict) or "fontSize" not in t:
                raise _err(f"{path}: a typography token needs a fontSize", "add fontSize, e.g. \"16px\"")
            size = _dim(f"{path}.fontSize", t["fontSize"])
            try:
                weight = int(t.get("fontWeight", 400))
            except (TypeError, ValueError):
                raise _err(f"{path}.fontWeight must be a number such as 400", "write fontWeight as an integer") from None
            weight = min(900, max(100, int(round(weight / 100.0)) * 100))
            lh = t.get("lineHeight")
            if lh is None or size == 0:
                line = 1.0
            elif isinstance(lh, (int, float)) and not isinstance(lh, bool):
                line = float(lh)
            else:
                line = _dim(f"{path}.lineHeight", lh) / size
            ls = t.get("letterSpacing")
            if ls is None:
                spacing = 0.0
            elif isinstance(ls, str) and ls.strip().endswith("em"):
                spacing = _number(f"{path}.letterSpacing", float(ls.strip()[:-2]))
            else:
                spacing = _dim(f"{path}.letterSpacing", ls) / size if size else 0.0
            out.append((name, size, weight, round(line, 4), round(spacing, 4)))
        _check_unique("typography", [camel(n[0]) for n in out])
        return out

    @staticmethod
    def _shadows(doc: dict) -> List[Tuple[str, float, float, float, str, float, str, float]]:
        """(name, x, y, blur/2, light hex, light alpha, dark hex, dark alpha) from each shadow's largest-blur layer."""
        out = []
        for name, path, _tok, ttype in _entries(doc, "shadow"):
            if ttype != "shadow":
                continue
            picked = []
            for mode in ("light", "dark"):
                value = P.resolve(doc, path, mode)
                layers = value if isinstance(value, list) else [value]
                if not layers or not all(isinstance(layer, dict) for layer in layers):
                    raise _err(f"{path}: the mobile themes need shadow layers written as objects", "use {offsetX, offsetY, blur, spread, color} objects")
                layer = max(layers, key=lambda ly: _dim(path, ly.get("blur", "0px")))
                hexv, alpha = P.parse_color(layer.get("color", "#000000"))
                picked.append((_dim(path, layer.get("offsetX", "0px")), _dim(path, layer.get("offsetY", "0px")),
                               _dim(path, layer.get("blur", "0px")) / 2, hexv, alpha))
            (x, y, r, lh, la), (_x, _y, _r, dh, da) = picked
            out.append((name, x, y, r, lh, la, dh, da))
        _check_unique("shadow", [camel(s[0]) for s in out])
        return out


def load_icon_map(skill_dir: Path) -> Optional[List[dict]]:
    path = skill_dir / "assets" / "icons" / "icon-map.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _err(f"{path}: cannot read the icon map ({exc})", "fix the JSON or delete the file to leave icons out") from None
    icons = data.get("icons") if isinstance(data, dict) else None
    if not isinstance(icons, list) or not icons:
        raise _err(f"{path}: needs a non-empty 'icons' list", "add entries like {\"concept\": \"home\", \"sfSymbol\": \"house\", \"materialSymbol\": \"home\"}")
    for entry in icons:
        for key in ("concept", "sfSymbol", "materialSymbol"):
            if not isinstance(entry, dict) or not isinstance(entry.get(key), str) or not entry[key]:
                label = entry.get("concept", "?") if isinstance(entry, dict) else "?"
                raise _err(f"{path}: entry {label!r} is missing {key}", f"add {key} to that entry")
    for key in ("concept", "sfSymbol", "materialSymbol"):
        seen: Dict[str, str] = {}
        for entry in icons:
            if entry[key] in seen:
                raise _err(f"{path}: {key} {entry[key]!r} is used by both {seen[entry[key]]!r} and {entry['concept']!r}",
                           "give each concept its own name, SF Symbol and Material symbol")
            seen[entry[key]] = entry["concept"]
    return icons


def _project_name(doc: dict) -> str:
    project = P.plumb_settings(doc).get("project")
    name = pascal(project) if isinstance(project, str) else ""
    if not name:
        raise _err("the tokens file has no project name for the mobile themes", "set $extensions.plumb.project in the tokens file (letters or digits)")
    return name if not name[0].isdigit() else "P" + name


def _swift_relative_to(size: float) -> str:
    for limit, style in ((34, ".largeTitle"), (28, ".title"), (22, ".title2"), (20, ".title3"), (17, ".body"),
                         (15, ".subheadline"), (13, ".footnote")):
        if size >= limit:
            return style
    return ".caption"


def build_swift(doc: dict, data: MobileData, project: str, header: str) -> str:
    sw = lambda n: camel(n, SWIFT_KEYWORDS)  # noqa: E731
    low = project[:1].lower() + project[1:]
    init_light, init_dark = f"{low}Light", "dark"
    L = [
        f"// {header}",
        f"// {project} design system for SwiftUI (iOS 17+).",
        "",
        "import SwiftUI",
        "#if canImport(UIKit)",
        "import UIKit",
        "#endif",
        "",
        "// MARK: - Colours (light and dark resolve automatically through the trait collection)",
        "",
        "public extension Color {",
        "    /// A colour that follows the system appearance: `light` in light mode, `dark` in dark mode.",
        f"    init({init_light} light: UInt32, lightAlpha: Double = 1, {init_dark}: UInt32, darkAlpha: Double = 1) {{",
        "        #if canImport(UIKit)",
        "        self.init(uiColor: UIColor { traits in",
        "            let (hex, alpha) = traits.userInterfaceStyle == .dark ? (dark, darkAlpha) : (light, lightAlpha)",
        "            return UIColor(red: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,",
        "                           blue: CGFloat(hex & 0xFF) / 255, alpha: CGFloat(alpha))",
        "        })",
        "        #else",
        "        self.init(.sRGB, red: Double((light >> 16) & 0xFF) / 255, green: Double((light >> 8) & 0xFF) / 255,",
        "                  blue: Double(light & 0xFF) / 255, opacity: lightAlpha)",
        "        #endif",
        "    }",
        "}",
        "",
    ]
    if data.colors:
        L.append(f"public enum {project}Color {{")
        for key, _n, lh, la, dh, da, desc in data.colors:
            if desc:
                L.append(f"    /// {desc}")
            args = f"{init_light}: {_rgb_int(lh)}" + (f", lightAlpha: {num(round(la, 4))}" if la != 1 else "")
            args += f", {init_dark}: {_rgb_int(dh)}" + (f", darkAlpha: {num(round(da, 4))}" if da != 1 else "")
            L.append(f"    public static let {sw(key)} = Color({args})")
        L += ["}", ""]
    if data.type_scale:
        family = data.family()
        font = (f"{{ .custom({_q(family)}, size: size, relativeTo: relativeTo).weight(weight) }}" if family
                else "{ .system(size: size, weight: weight) }")
        note = (f"/// The font. Bundle {family} and register it in the app's Info.plist (UIAppFonts)." if family
                else "/// The font: the system font, scaled with Dynamic Type where the system supports it.")
        L += [
            "// MARK: - Type scale",
            "",
            f"public struct {project}TextStyle: Sendable {{",
            "    public let size: CGFloat",
            "    public let weight: Font.Weight",
            "    public let lineHeight: CGFloat   // multiplier of size",
            "    public let tracking: CGFloat     // em",
            "    public let relativeTo: Font.TextStyle",
            f"    {note}",
            f"    public var font: Font {font}",
            "    /// Extra space between lines, for `.lineSpacing(...)`.",
            "    public var lineSpacing: CGFloat { size * (lineHeight - 1) }",
            "    /// Letter spacing in points, for `.tracking(...)`.",
            "    public var trackingPoints: CGFloat { size * tracking }",
            "}",
            "",
            f"public enum {project}Type {{",
        ]
        for name, size, weight, lh, ls in data.type_scale:
            L.append(f"    public static let {sw(name)} = {project}TextStyle(size: {num(size)}, weight: {SWIFT_WEIGHTS[weight]}, "
                     f"lineHeight: {num(lh)}, tracking: {num(ls)}, relativeTo: {_swift_relative_to(size)})")
        L += [
            "}",
            "",
            "public extension View {",
            f"    /// Apply a {project} text style: font, line spacing and tracking.",
            f"    func {low}Text(_ style: {project}TextStyle) -> some View {{",
            "        font(style.font).lineSpacing(style.lineSpacing).tracking(style.trackingPoints)",
            "    }",
            "}",
            "",
        ]
    for group, suffix, _prefix, ents in data.dims:
        L += [f"// MARK: - {suffix} (points)", "", f"public enum {project}{suffix} {{"]
        L += [f"    public static let {sw(n)}: CGFloat = {num(v)}" for n, v in ents]
        L += ["}", ""]
    if data.shadows:
        L += [
            "// MARK: - Elevation (each shadow's largest layer)",
            "",
            f"public struct {project}Shadow: Sendable {{",
            "    public let x: CGFloat, y: CGFloat, radius: CGFloat",
            "    public let lightColor: UInt32, lightAlpha: Double, darkColor: UInt32, darkAlpha: Double",
            f"    public var color: Color {{ Color({init_light}: lightColor, lightAlpha: lightAlpha, {init_dark}: darkColor, darkAlpha: darkAlpha) }}",
            "}",
            "",
            f"public enum {project}Elevation {{",
        ]
        for name, x, y, r, lh, la, dh, da in data.shadows:
            L.append(f"    public static let {sw(name)} = {project}Shadow(x: {num(x)}, y: {num(y)}, radius: {num(r)}, "
                     f"lightColor: {_rgb_int(lh)}, lightAlpha: {num(round(la, 4))}, darkColor: {_rgb_int(dh)}, "
                     f"darkAlpha: {num(round(da, 4))})")
        L += [
            "}",
            "",
            "public extension View {",
            f"    func {low}Shadow(_ s: {project}Shadow) -> some View {{ shadow(color: s.color, radius: s.radius, x: s.x, y: s.y) }}",
            "}",
            "",
        ]
    if data.durations or data.beziers or data.motion_dims or data.motion_numbers:
        L += ["// MARK: - Motion (use `nil` animations when @Environment(\\.accessibilityReduceMotion) is on)", "",
              f"public enum {project}Motion {{"]
        L += [f"    public static let {sw(n)}: Double = {num(v / 1000)}  // seconds" for n, v in data.durations]
        for n, pts in data.beziers:
            L.append(f"    public static func ease{pascal(n)}(_ duration: Double) -> Animation "
                     f"{{ .timingCurve({', '.join(num(x) for x in pts)}, duration: duration) }}")
        L += [f"    public static let {sw(n)}: CGFloat = {num(v)}" for n, v in data.motion_dims + data.motion_numbers]
        L += [
            "    /// The animation to use, or nil (instant) when Reduce Motion is on.",
            "    public static func animation(_ animation: Animation, reduceMotion: Bool) -> Animation? "
            "{ reduceMotion ? nil : animation }",
            "}",
            "",
        ]
    if data.icons:
        L += ["// MARK: - Icons (SF Symbols mapped from assets/icons/icon-map.json)", "",
              f"public enum {project}Icon: String, CaseIterable, Sendable {{"]
        L += [f"    case {sw(i['concept'])} = {_q(i['sfSymbol'])}" for i in data.icons]
        L += ["    public var image: Image { Image(systemName: rawValue) }", "}", ""]
    return "\n".join(L)


def _kt_color(hexv: str, alpha: float) -> str:
    return f"Color(0x{round(alpha * 255):02X}{hexv[1:].upper()})"


def _spread(count: int, slots: int) -> List[int]:
    """slots indexes into a list of `count`, spread from the first to the last entry."""
    if count == 0:
        return []
    return [int(round(i * (count - 1) / float(slots - 1))) for i in range(slots)]


def build_kotlin(doc: dict, data: MobileData, project: str, header: str) -> str:
    kt = lambda n: camel(n, KOTLIN_KEYWORDS)  # noqa: E731
    low = project[:1].lower() + project[1:]
    package = "app." + (re.sub(r"[^a-z0-9]", "", project.lower()) if not project[0].isdigit() else "p" + project.lower()) + ".designsystem"
    imports = [
        "androidx.compose.animation.core.CubicBezierEasing", "androidx.compose.foundation.isSystemInDarkTheme",
        "androidx.compose.foundation.shape.RoundedCornerShape", "androidx.compose.material3.ColorScheme",
        "androidx.compose.material3.MaterialTheme", "androidx.compose.material3.Shapes",
        "androidx.compose.material3.Typography", "androidx.compose.material3.darkColorScheme",
        "androidx.compose.material3.lightColorScheme", "androidx.compose.runtime.Composable",
        "androidx.compose.runtime.CompositionLocalProvider", "androidx.compose.runtime.Immutable",
        "androidx.compose.runtime.staticCompositionLocalOf", "androidx.compose.ui.graphics.Color",
        "androidx.compose.ui.text.TextStyle", "androidx.compose.ui.text.font.FontFamily",
        "androidx.compose.ui.text.font.FontWeight", "androidx.compose.ui.unit.dp", "androidx.compose.ui.unit.em",
        "androidx.compose.ui.unit.sp",
    ]
    L = [f"// {header}", f"// {project} design system for Jetpack Compose (Material 3).", f"package {package}", ""]
    L += [f"import {i}" for i in imports]
    L += [""]
    names = {c[0]: c for c in data.colors}
    L += [f"/** Every {project} colour for one appearance (the Material roles cover only part of them). */", "@Immutable",
          f"data class {project}Colors("]
    L += [f"    val {kt(c[0])}: Color," for c in data.colors]
    L += [")", ""]
    for mode, lidx in (("Light", 2), ("Dark", 4)):
        L.append(f"val {project}{mode}Colors = {project}Colors(")
        L += [f"    {kt(c[0])} = {_kt_color(c[lidx], c[lidx + 1])}," for c in data.colors]
        L += [")", ""]
    roles = []
    for role, candidates in M3_COLORS:
        found = next((c for c in candidates if c in names), None)
        if found:
            roles.append((role, found))
    for mode, fn in (("Light", "lightColorScheme"), ("Dark", "darkColorScheme")):
        if roles:
            L.append(f"val {project}{mode}ColorScheme: ColorScheme = {fn}(")
            L += [f"    {role} = {project}{mode}Colors.{kt(name)}," for role, name in roles]
            L += [")", ""]
        else:
            L += [f"val {project}{mode}ColorScheme: ColorScheme = {fn}()", ""]
    family = data.family()
    L += [(f"/** {family}, bundled in the app: pass its FontFamily in; the default falls back to the system sans. */" if family
           else "/** The system sans by default; pass a FontFamily to use another. */"),
          f"fun {low}Typography(fontFamily: FontFamily = FontFamily.Default): Typography {{"]
    styles = {}
    for name, size, weight, lh, ls in data.type_scale:
        styles[name] = (size, weight, lh, ls)
    for name, (size, weight, lh, ls) in styles.items():
        L.append(f"    val {kt(name)} = TextStyle(fontFamily = fontFamily, fontSize = {num(size)}.sp, fontWeight = "
                 f"FontWeight.W{weight}, lineHeight = {num(round(size * lh, 2))}.sp, letterSpacing = {num(ls)}.em)")
    if styles:
        by_size = sorted(styles, key=lambda n: -styles[n][0])
        L.append("    return Typography(")
        L += [f"        {role} = {kt(by_size[idx])}," for role, idx in zip(M3_TYPE_ROLES, _spread(len(by_size), len(M3_TYPE_ROLES)))]
        L += ["    )", "}", "",
              f"/** The {project} type scale by its own names, for when a Material role does not fit. */",
              f"object {project}Type {{"]
        for name, (size, weight, lh, ls) in styles.items():
            L.append(f"    val {kt(name)} = TextStyle(fontSize = {num(size)}.sp, fontWeight = FontWeight.W{weight}, "
                     f"lineHeight = {num(round(size * lh, 2))}.sp, letterSpacing = {num(ls)}.em)")
        L += ["}", ""]
    else:
        L += ["    return Typography()", "}", ""]
    radii = next((ents for group, _s, _p, ents in data.dims if group == "radius"), [])
    ordered = sorted(radii, key=lambda e: e[1])
    L += [f"val {project}Shapes = Shapes("]
    L += [f"    {slot} = RoundedCornerShape({num(ordered[idx][1])}.dp)," for slot, idx in zip(M3_SHAPES, _spread(len(ordered), 5))]
    L += [")", ""]
    for group, suffix, _prefix, ents in data.dims:
        L.append(f"object {project}{suffix} {{")
        L += [f"    val {kt(n)} = {num(v)}.dp" for n, v in ents]
        L += ["}", ""]
    if data.shadows:
        L += ["/** Shadow elevation approximating each shadow (the largest layer's blur / 2). */",
              f"object {project}Elevation {{"]
        L += [f"    val {kt(s[0])} = {num(s[3])}.dp" for s in data.shadows]
        L += ["}", ""]
    if data.durations or data.beziers or data.motion_dims or data.motion_numbers:
        L += ["/** Motion. Skip animations when the system animation scale is 0 (reduced motion). */",
              f"object {project}Motion {{"]
        L += [f"    const val {camel(n, KOTLIN_KEYWORDS).strip('`')}Millis = {num(v)}" for n, v in data.durations]
        L += [f"    val Ease{pascal(n)} = CubicBezierEasing({', '.join(num(x) + 'f' for x in pts)})" for n, pts in data.beziers]
        L += [f"    val {kt(n)} = {num(v)}.dp" for n, v in data.motion_dims]
        L += [f"    const val {kt(n)} = {num(v)}f" for n, v in data.motion_numbers]
        L += ["}", ""]
    if data.icons:
        L += ["/** Material Symbols names mapped from assets/icons/icon-map.json. */", f"enum class {project}Icon(val symbol: String) {{"]
        L += [f"    {kt(i['concept'])}({_q(i['materialSymbol'])})," for i in data.icons]
        L += ["}", ""]
    L += [
        f"val Local{project}Colors = staticCompositionLocalOf {{ {project}LightColors }}",
        "",
        f"/** Wrap the app: Material 3 with {project} colours, type and shapes, plus every {project} colour through {project}Theme.colors. */",
        "@Composable",
        f"fun {project}Theme(",
        "    darkTheme: Boolean = isSystemInDarkTheme(),",
        "    fontFamily: FontFamily = FontFamily.Default,",
        "    content: @Composable () -> Unit,",
        ") {",
        f"    val {low} = if (darkTheme) {project}DarkColors else {project}LightColors",
        f"    CompositionLocalProvider(Local{project}Colors provides {low}) {{",
        "        MaterialTheme(",
        f"            colorScheme = if (darkTheme) {project}DarkColorScheme else {project}LightColorScheme,",
        f"            typography = {low}Typography(fontFamily),",
        f"            shapes = {project}Shapes,",
        "            content = content,",
        "        )",
        "    }",
        "}",
        "",
        f"object {project}Theme {{",
        f"    val colors: {project}Colors",
        f"        @Composable get() = Local{project}Colors.current",
        "}",
        "",
    ]
    return "\n".join(L)


def mobile_outputs(doc: dict, skill_dir: Path, header: str) -> Dict[Path, str]:
    platforms = P.plumb_settings(doc)["platforms"]
    if not isinstance(platforms, list):
        raise _err("platforms must be a list in the tokens file", 'write it as ["web", "ios", "android"]')
    wanted = [p for p in MOBILE_PLATFORMS if p in platforms]
    if not wanted:
        return {}
    project = _project_name(doc)
    data = MobileData(doc, load_icon_map(skill_dir))
    mobile = skill_dir / "assets" / "platforms" / "mobile"
    out: Dict[Path, str] = {}
    if "ios" in wanted:
        out[mobile / "ios" / f"{project}Theme.swift"] = build_swift(doc, data, project, header)
    if "android" in wanted:
        out[mobile / "android" / f"{project}Theme.kt"] = build_kotlin(doc, data, project, header)
    return out


# ---------------------------------------------------------------- outputs


def safe_copy_path(root: Path, copy: object) -> Path:
    text = str(copy).replace("\\", "/") if isinstance(copy, str) else ""
    bad = (not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text) is not None
           or ".." in text.split("/"))
    if bad:
        raise _err(
            f"$extensions.plumb.web.copies has {copy!r}, which is not a path inside the project",
            "write copies relative to the project root, e.g. \"app/globals.css\"",
        )
    return (root / text).resolve()


def outputs(doc: dict, skill_dir: Path, project: Optional[Path] = None, tokens_file: Optional[Path] = None) -> Dict[Path, str]:
    """Every generated file as {absolute path: content}: web CSS, copies, and the mobile themes for the listed platforms."""
    skill_dir = Path(skill_dir).resolve()
    root = find_project_root(skill_dir, project)
    tokens_file = tokens_file or find_tokens_file(skill_dir)
    settings = P.plumb_settings(doc)
    web = settings["web"]
    styling = web["styling"]
    if styling not in STYLINGS:
        raise _err(f"web.styling is {styling!r} in {tokens_file.name}", f"set $extensions.plumb.web.styling to one of: {', '.join(STYLINGS)}")
    header = header_text(skill_dir, tokens_file, root)
    css = build_css(doc, read_template(skill_dir, styling), header)
    folder = skill_dir / "assets" / "platforms" / "web"
    out: Dict[Path, str] = {folder / "tokens.css": css}
    if styling == "tailwind-v3":
        out[folder / "tailwind.tokens.js"] = build_tailwind_js(doc, header)
    copies = web.get("copies") or []
    if not isinstance(copies, list):
        raise _err("web.copies must be a list of paths", "write it as [\"app/globals.css\"]")
    for copy in copies:
        out[safe_copy_path(root, copy)] = css
    out.update(mobile_outputs(doc, skill_dir, header))
    return dict(sorted(out.items(), key=lambda kv: str(kv[0])))


# ---------------------------------------------------------------- cli


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: python3 {SCRIPT_REL} [--check] [--root SKILL_DIR] [--project PATH]\n")


def main(argv: Optional[List[str]] = None) -> int:
    P.utf8_stdio()
    parser = _Parser(prog="build-tokens.py", description="Build the web token outputs from the tokens JSON.")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 when any output is stale or missing")
    parser.add_argument("--root", metavar="SKILL_DIR", help="the design-system skill folder (default: this script's skill)")
    parser.add_argument("--project", metavar="PATH", help="project root when no PLUMB.md is found above the skill")
    args = parser.parse_args(argv)
    skill_dir = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    project = Path(args.project) if args.project else None
    try:
        root = find_project_root(skill_dir, project)
        tokens_file = find_tokens_file(skill_dir)
        files = outputs(P.load_tokens(tokens_file), skill_dir, project, tokens_file)
    except PlumbError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        print(
            f"error: unexpected token structure ({type(exc).__name__}: {exc})\n"
            f"fix: open the tokens file and compare it with reference/tokens-format.md",
            file=sys.stderr,
        )
        return 2
    command = f"python3 {rel(skill_dir / SCRIPT_REL, root)}"
    stale = []
    for path, text in files.items():
        try:
            current = path.read_bytes() if path.exists() else None
        except OSError:
            current = None
        if current == text.encode("utf-8"):
            continue
        if args.check:
            stale.append(path)
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"error: cannot write {rel(path, root)} ({exc})\nfix: check the folder exists and is writable", file=sys.stderr)
            return 2
        print(f"wrote {rel(path, root)}")
    if args.check:
        if stale:
            for path in stale:
                print(f"stale: {rel(path, root)}")
            print(f"fix: {command}")
            return 1
        print(f"ok: {len(files)} generated files are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
