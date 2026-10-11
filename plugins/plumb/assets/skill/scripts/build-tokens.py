#!/usr/bin/env python3
"""build-tokens.py: turn the one tokens JSON into the web CSS, the SwiftUI / Jetpack Compose themes and the contrast evidence.

Usage: build-tokens.py [--check | --contrast | --migrate | --css-vars] [--root SKILL_DIR] [--project PATH]

Reads <skill>/assets/tokens/*.tokens.json (exactly one) and the web template, writes
<skill>/assets/platforms/web/tokens.css (+ tailwind.tokens.js for tailwind-v3) and the copies listed in
$extensions.plumb.web.copies (relative to the project root), plus assets/platforms/mobile/ios/<Project>Theme.swift and
mobile/android/<Project>Theme.kt for the platforms listed in $extensions.plumb.platforms, and refreshes the block between
<!-- plumb:contrast:start --> and <!-- plumb:contrast:end --> in <skill>/references/dark-mode.md when that file has the markers.

  --check      write nothing; exit 1 naming every stale or missing file.
  --contrast   rewrite only the contrast block of references/dark-mode.md (exit 2 if the file or the markers are missing).
  --migrate    bring the tokens JSON up to the current schema (1) by adding missing settings; never removes or changes a value.
  --css-vars   print the tokens as plain CSS custom properties (:root, the md breakpoint, .dark and prefers-color-scheme).

The default build prints one `note:` line to stderr when dark-mode.md exists without the markers.
Exit codes: 0 ok, 1 stale (--check), 2 bad input (error: ... then fix: ...).

Contrast pairs (WCAG 2.x, light and dark):
  * every on-X token over X (4.5:1);
  * every text token over every surface (4.5:1). Text tokens are colour tokens whose name starts with `on-`, is exactly
    `link`, or has `text` or `ink` as a whole hyphen-separated word (text-muted, primary-ink; not pink or context-menu).
    Surfaces are background, page, sidebar, sunk, column, surface*, and *-container, or exactly the tokens listed in
    $extensions.plumb.contrast.surfaces. An `on-X` token where X is itself a surface (on-surface, on-surface-variant,
    on-background) is checked over every surface; any other on-X (on-primary) is checked over its own X only;
  * UI boundaries (3:1): the token `outline-input` and tokens listed in contrast.ui, over every non-container surface;
  * contrast.extra_pairs, either form per entry:
      ["on-primary-fill", "primary-fill", "text"]            [fg, bg, kind], kind text (4.5) | large (3) | ui (3)
      {"fg": token, "bg": token, "need": 4.5, "note": "..."}  "need" defaults to 4.5 (3 for large text)
--contrast exits 0 even when pairs fail: it writes the evidence, the audit is the gate.
A failing pair lists the nearest passing foreground: its L* is stepped darker (light mode) or lighter (dark mode) until it passes.

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
_ON = ("on-surface", "on-background", "text", "ink")  # neutral text, the last resort for a foreground role
_BG = ("surface", "background", "page")  # neutral surfaces, the last resort for a background role
M3_COLORS = (  # Material 3 role -> the token names (in the color group) that can fill it, first found wins.
    # Roles with no token of their own come from the closest present tokens, then from neutral surface / on-surface
    # values, so Material's default purple never shows through.
    ("primary", ("primary-fill", "primary", "link") + _ON),
    ("onPrimary", ("on-primary-fill", "on-primary") + _BG),
    ("primaryContainer", ("primary-container", "surface-variant", "sunk", "column") + _BG),
    ("onPrimaryContainer", ("on-primary-container",) + _ON),
    ("inversePrimary", ("primary", "primary-fill", "link") + _ON),
    ("secondary", ("secondary", "primary-fill", "primary", "link") + _ON),
    ("onSecondary", ("on-secondary", "on-primary-fill", "on-primary") + _BG),
    ("secondaryContainer", ("secondary-container", "primary-container", "surface-variant", "sunk", "column") + _BG),
    ("onSecondaryContainer", ("on-secondary-container", "on-primary-container") + _ON),
    ("tertiary", ("tertiary", "primary-fill", "primary", "link") + _ON),
    ("onTertiary", ("on-tertiary", "on-primary-fill", "on-primary") + _BG),
    ("tertiaryContainer", ("tertiary-container", "primary-container", "surface-variant", "sunk", "column") + _BG),
    ("onTertiaryContainer", ("on-tertiary-container", "on-primary-container") + _ON),
    ("background", ("background", "page", "surface")),
    ("onBackground", ("on-background", "on-surface", "text", "ink")),
    ("surface", ("surface", "background", "page")),
    ("onSurface", ("on-surface", "on-background", "text", "ink")),
    ("surfaceVariant", ("surface-variant", "sunk", "column") + _BG),
    ("onSurfaceVariant", ("on-surface-variant", "on-surface-soft") + _ON),
    ("surfaceTint", ("primary-fill", "primary", "link") + _ON),
    ("surfaceContainerLowest", ("surface-container-lowest", "surface-raised") + _BG),
    ("surfaceContainerLow", ("surface-container-low", "column", "sunk") + _BG),
    ("surfaceContainer", ("surface-container", "column", "sunk") + _BG),
    ("surfaceContainerHigh", ("surface-container-high", "surface-raised", "sunk", "column") + _BG),
    ("surfaceContainerHighest", ("surface-container-highest", "surface-raised", "sunk", "column") + _BG),
    ("inverseSurface", ("inverse-surface",) + _ON),
    ("inverseOnSurface", ("inverse-on-surface",) + _BG),
    ("outline", ("outline", "outline-strong", "outline-input") + _ON),
    ("outlineVariant", ("outline-variant", "outline", "outline-strong", "outline-input") + _ON),
    ("error", ("error", "danger", "bad-fill", "bad") + _ON),
    ("onError", ("on-error", "on-danger", "on-bad-fill") + _BG),
    ("errorContainer", ("error-container", "danger-container", "bad-container") + _BG),
    ("onErrorContainer", ("on-error-container", "on-danger-container", "on-bad-container", "error", "danger", "bad") + _ON),
    ("scrim", ("scrim",) + _ON),
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
    has_colors = bool(data.colors)
    if has_colors:
        L += [f"/** Every {project} colour for one appearance (the Material roles cover only part of them). */", "@Immutable",
              f"data class {project}Colors("]
        L += [f"    val {kt(c[0])}: Color," for c in data.colors]
        L += [")", ""]
        for mode, lidx in (("Light", 2), ("Dark", 4)):
            L.append(f"val {project}{mode}Colors = {project}Colors(")
            L += [f"    {kt(c[0])} = {_kt_color(c[lidx], c[lidx + 1])}," for c in data.colors]
            L += [")", ""]
    for mode, fn, lidx in (("Light", "lightColorScheme", 2), ("Dark", "darkColorScheme", 4)):
        L.append(f"val {project}{mode}ColorScheme: ColorScheme = {fn}(")
        if has_colors:
            for role, candidates in M3_COLORS:
                found = next((c for c in candidates if c in names), data.colors[0][0])
                L.append(f"    {role} = {project}{mode}Colors.{kt(found)},")
        else:  # no colour tokens: neutral roles, never Material's default purple
            bg, fg = ("Color.White", "Color.Black") if mode == "Light" else ("Color.Black", "Color.White")
            for role, value in (("primary", fg), ("onPrimary", bg), ("background", bg), ("onBackground", fg), ("surface", bg), ("onSurface", fg)):
                L.append(f"    {role} = {value},")
        L += [")", ""]
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
    material = [
        "MaterialTheme(",
        f"    colorScheme = if (darkTheme) {project}DarkColorScheme else {project}LightColorScheme,",
        f"    typography = {low}Typography(fontFamily),",
        f"    shapes = {project}Shapes,",
        "    content = content,",
        ")",
    ]
    if has_colors:
        L += [f"val Local{project}Colors = staticCompositionLocalOf {{ {project}LightColors }}", "",
              f"/** Wrap the app: Material 3 with {project} colours, type and shapes, plus every {project} colour through {project}Theme.colors. */"]
    else:
        L += [f"/** Wrap the app: Material 3 with {project} type and shapes (this project has no colour tokens yet). */"]
    L += ["@Composable", f"fun {project}Theme(", "    darkTheme: Boolean = isSystemInDarkTheme(),",
          "    fontFamily: FontFamily = FontFamily.Default,", "    content: @Composable () -> Unit,", ") {"]
    if has_colors:
        L += [f"    val {low} = if (darkTheme) {project}DarkColors else {project}LightColors",
              f"    CompositionLocalProvider(Local{project}Colors provides {low}) {{"]
        L += ["        " + m for m in material] + ["    }", "}", "",
              f"object {project}Theme {{", f"    val colors: {project}Colors", f"        @Composable get() = Local{project}Colors.current", "}", ""]
    else:
        L += ["    " + m for m in material] + ["}", ""]
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
    dark = contrast_output(doc, skill_dir, required=False)
    if dark:
        out[dark[0]] = dark[1]
    return dict(sorted(out.items(), key=lambda kv: str(kv[0])))


# ---------------------------------------------------------------- contrast evidence


CONTRAST_START = "<!-- plumb:contrast:start -->"
CONTRAST_END = "<!-- plumb:contrast:end -->"
DARK_DOC_REL = "references/dark-mode.md"
SURFACE_NAMES = frozenset(("background", "page", "sidebar", "sunk", "column"))
NEED_TEXT, NEED_UI = 4.5, 3.0


def _is_surface_name(key: str) -> bool:
    return key in SURFACE_NAMES or key.startswith("surface") or key.endswith("-container")


_is_text_name = P.is_text_name


class Pair:
    def __init__(self, fg: str, bg: str, need: float) -> None:
        self.fg, self.bg, self.need = fg, bg, need
        self.light = 0.0
        self.dark = 0.0
        self.fix: Dict[str, Optional[Tuple[str, float]]] = {}
        self.fg_path = self.bg_path = ""
        self.hex: Dict[str, Tuple[str, str]] = {}

    @property
    def failed(self) -> List[str]:
        return [m for m, v in (("light", self.light), ("dark", self.dark)) if v < self.need]


def _contrast_settings(doc: dict) -> dict:
    cfg = P.plumb_settings(doc)["contrast"]
    where = "$extensions.plumb.contrast"
    for key in ("surfaces", "ui", "extra_pairs"):
        if key in cfg and not isinstance(cfg[key], list):
            raise _err(f"{where}.{key} must be a list", f"write it as a list, e.g. {where}.{key}: []")
    for key in ("surfaces", "ui"):
        if not all(isinstance(x, str) for x in cfg.get(key, [])):
            raise _err(f"{where}.{key} must list token names as strings", 'write it like ["surface", "sunk"]')
    return cfg


def _blend(fg: str, alpha: float, bg: str) -> str:
    if alpha >= 1:
        return fg
    mix = [round(int(fg[i:i + 2], 16) * alpha + int(bg[i:i + 2], 16) * (1 - alpha)) for i in (1, 3, 5)]
    return "#" + "".join(f"{c:02x}" for c in mix)


def _lab_to_hex(lightness: float, a: float, b: float) -> str:
    fy = (lightness + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def inv(t: float) -> float:
        return t ** 3 if t > 6 / 29 else 3 * (6 / 29) ** 2 * (t - 4 / 29)

    x, y, z = 0.95047 * inv(fx), 1.0 * inv(fy), 1.08883 * inv(fz)
    lin = (3.2404542 * x - 1.5371385 * y - 0.4985314 * z,
           -0.9692660 * x + 1.8760108 * y + 0.0415560 * z,
           0.0556434 * x - 0.2040259 * y + 1.0572252 * z)

    def enc(c: float) -> int:
        c = min(1.0, max(0.0, c))
        return round(255 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055))

    return "#" + "".join(f"{enc(c):02x}" for c in lin)


def _walk_lightness(fg: str, bg: str, need: float, lighten: bool) -> Optional[Tuple[str, float]]:
    lightness, a, b = P._lab(fg)
    lightness = min(100.0, max(0.0, lightness))
    step = 0.5 if lighten else -0.5
    while (lightness < 100) if lighten else (lightness > 0):
        lightness = min(100.0, max(0.0, lightness + step))
        cand = _lab_to_hex(lightness, a, b)
        ratio = P.contrast(cand, bg)
        if ratio >= need:
            return cand, ratio
    return None


def nearest_passing(fg: str, bg: str, need: float, lighten: bool) -> Optional[Tuple[str, float]]:
    """The fg colour moved in small L* steps (hue kept) until it reaches `need` on bg: lighter when `lighten`, else
    darker; when that direction cannot reach it (white text on a light fill), the other direction is tried."""
    return _walk_lightness(fg, bg, need, lighten) or _walk_lightness(fg, bg, need, not lighten)


def contrast_pairs(doc: dict) -> List[Pair]:
    cfg = _contrast_settings(doc)
    keys: Dict[str, str] = {}  # name -> token path, colour tokens in file order
    for path, _tok, ttype in P.iter_tokens(doc):
        if ttype == "color":
            parts = path.split(".")
            keys["-".join(parts[1:]) if parts[0] == "color" and len(parts) > 1 else "-".join(parts)] = path

    def known(name: object, where: str) -> str:
        text = str(name)
        if text in keys:
            return text
        if text.startswith("color."):
            return known(text[6:].replace(".", "-"), where)
        raise _err(f"{where}: unknown colour token {text!r}", "name a colour token from the tokens file, e.g. on-surface")

    listed = cfg.get("surfaces") or []
    surfaces = [known(n, "$extensions.plumb.contrast.surfaces") for n in listed]
    if not listed:
        surfaces = [k for k in keys if not _is_text_name(k) and _is_surface_name(k)]
    plain_surfaces = [k for k in surfaces if listed or not k.endswith("-container")]
    ui_names = [k for k in keys if k == "outline-input"] + [known(n, "$extensions.plumb.contrast.ui") for n in cfg.get("ui", [])]

    pairs: List[Pair] = []
    seen = set()

    def add(fg: str, bg: str, need: float) -> None:
        if fg != bg and (fg, bg) not in seen:
            seen.add((fg, bg))
            pairs.append(Pair(fg, bg, need))

    for k in keys:
        if k.startswith("on-") and k[3:] in keys:
            add(k, k[3:], NEED_TEXT)
    for k in keys:
        if k in ui_names:
            continue
        if k.startswith("on-"):
            base = k[3:]
            if _is_surface_name(base) and not base.endswith("-container"):
                for s_ in surfaces:
                    add(k, s_, NEED_TEXT)
        elif _is_text_name(k):
            for s_ in surfaces:
                add(k, s_, NEED_TEXT)
    for k in dict.fromkeys(ui_names):
        for s_ in plain_surfaces:
            add(k, s_, NEED_UI)

    extra = cfg.get("extra_pairs", [])
    kinds = {"text": NEED_TEXT, "large": NEED_UI, "ui": NEED_UI}
    for i, entry in enumerate(extra):
        where = f"$extensions.plumb.contrast.extra_pairs[{i}]"
        if isinstance(entry, list):
            if len(entry) != 3 or not all(isinstance(x, str) for x in entry) or entry[2] not in kinds:
                raise _err(f"{where} must be [fg, bg, kind] with kind text, large or ui",
                           'write it like ["on-primary-fill", "primary-fill", "text"]')
            add(known(entry[0], where), known(entry[1], where), kinds[entry[2]])
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get("fg"), str) or not isinstance(entry.get("bg"), str):
            raise _err(f"{where} must be [fg, bg, kind] or an object with \"fg\" and \"bg\" token names",
                       'write it like ["primary", "background", "ui"] or {"fg": "primary", "bg": "background", "need": 3}')
        need = entry.get("need", NEED_TEXT)
        if isinstance(need, bool) or not isinstance(need, (int, float)) or not 1 <= need <= 21:
            raise _err(f"{where}.need must be a number from 1 to 21 (4.5 text, 3 large text or UI)", "write \"need\": 4.5 or \"need\": 3")
        add(known(entry["fg"], where), known(entry["bg"], where), float(need))
    return pairs


def _hex_in(doc: dict, path: str, mode: str) -> Tuple[str, float]:
    try:
        return P.parse_color(P.resolve(doc, path, mode))
    except PlumbError as exc:
        first, _, rest = str(exc).partition("\n")
        if first.startswith(f"error: {path}"):
            raise
        raise PlumbError(f"error: {path}: {first[len('error: '):]}\n{rest}") from None


def measure_pairs(doc: dict) -> List[Pair]:
    """contrast_pairs(doc) measured in light and dark: each Pair gets .light, .dark, .fix (nearest passing fg per
    failing mode), .fg_path / .bg_path (token paths) and .hex[mode] = (fg blended over bg, bg). audit.py uses this too."""
    pairs = contrast_pairs(doc)
    paths: Dict[str, str] = {}
    for path, _tok, ttype in P.iter_tokens(doc):
        if ttype == "color":
            parts = path.split(".")
            paths["-".join(parts[1:]) if parts[0] == "color" and len(parts) > 1 else "-".join(parts)] = path
    for pair in pairs:
        pair.fg_path, pair.bg_path = paths[pair.fg], paths[pair.bg]
        for mode in ("light", "dark"):
            fg, fa = _hex_in(doc, paths[pair.fg], mode)
            bg, ba = _hex_in(doc, paths[pair.bg], mode)
            if ba < 1:
                raise _err(f"{pair.bg} is transparent, so {pair.fg} on {pair.bg} cannot be measured",
                           "use an opaque colour for the background in $extensions.plumb.contrast")
            fg = _blend(fg, fa, bg)
            pair.hex[mode] = (fg, bg)
            ratio = P.contrast(fg, bg)
            if mode == "light":
                pair.light = ratio
            else:
                pair.dark = ratio
            if ratio < pair.need:
                pair.fix[mode] = nearest_passing(fg, bg, pair.need, lighten=(mode == "dark"))
    return pairs


def contrast_block(doc: dict) -> str:
    """The generated text between the contrast markers (no trailing newline)."""
    pairs = measure_pairs(doc)
    failing = [p for p in pairs if p.failed]
    L = [
        "Generated by `build-tokens.py --contrast` from the tokens file (WCAG 2.x relative luminance). Do not edit this block:",
        "change the tokens, then run the command again. Text needs 4.5:1; large text and UI boundaries need 3:1.",
        "",
        f"{len(pairs)} pairs checked, {len(failing)} failing.",
        "",
        "| Pair | Light | Dark | Need | Result |",
        "|---|---:|---:|---:|---|",
    ]
    for p in pairs:
        result = "pass" if not p.failed else "fail (" + ", ".join(p.failed) + ")"
        L.append(f"| {p.fg} on {p.bg} | {p.light:.2f} | {p.dark:.2f} | {num(p.need)} | {result} |")
    if failing:
        L += ["", "Nearest passing values (the foreground nudged in L*, lighter in dark mode, darker in light mode):", ""]
        for p in failing:
            for mode in p.failed:
                fix = p.fix.get(mode)
                if fix:
                    L.append(f"- {p.fg} on {p.bg} ({mode}): nearest passing {fix[0]} ({fix[1]:.2f}:1)")
                else:
                    L.append(f"- {p.fg} on {p.bg} ({mode}): no value of this hue passes; change the background")
    return "\n".join(L)


def apply_contrast_block(text: str, block: str) -> Optional[str]:
    """`text` with the marked block replaced (its own line endings kept), or None when the markers are missing."""
    if text.count(CONTRAST_START) != 1 or text.count(CONTRAST_END) != 1:
        return None
    start = text.index(CONTRAST_START) + len(CONTRAST_START)
    end = text.index(CONTRAST_END)
    if end < start:
        return None
    nl = "\r\n" if "\r\n" in text else "\n"
    return text[:start] + nl + block.replace("\n", nl) + nl + text[end:]


def read_dark_doc(skill_dir: Path) -> Optional[str]:
    path = skill_dir / DARK_DOC_REL
    if not path.is_file():
        return None
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{path}: cannot read ({exc})", "save it as UTF-8") from None


def contrast_output(doc: dict, skill_dir: Path, required: bool) -> Optional[Tuple[Path, str]]:
    """(path, new text) for references/dark-mode.md; None when it is absent or unmarked and not required."""
    path = skill_dir / DARK_DOC_REL
    text = read_dark_doc(skill_dir)
    if text is None:
        if required:
            raise _err(f"{path} not found", f"copy references/dark-mode.md.tmpl from the Plumb plugin's assets/skill/ to {path}, then run --contrast again")
        return None
    new = apply_contrast_block(text, contrast_block(doc))
    if new is None:
        if required:
            raise _err(f"{path} has no {CONTRAST_START} ... {CONTRAST_END} markers",
                       f"add the two marker lines on their own lines where the table should go in {path}")
        print(f"note: the contrast block in {path.name} was not refreshed (no {CONTRAST_START} / {CONTRAST_END} markers); "
              f"add those two lines where the table should go, then run build-tokens.py --contrast", file=sys.stderr)
        return None
    return path, new


# ---------------------------------------------------------------- migrate and css-vars


def migrate(doc: dict, defaults_project: str = "") -> List[str]:
    """Add the missing schema-1 settings to `doc` in place; returns what was added. Never removes or changes a value."""
    added: List[str] = []
    ext = doc.get("$extensions")
    if ext is None:
        ext = {}
        doc_items = list(doc.items())
        doc.clear()
        doc["$extensions"] = ext
        doc.update(doc_items)
    elif not isinstance(ext, dict):
        raise _err("$extensions must be an object", "write it as \"$extensions\": { \"plumb\": { ... } }")
    plumb = ext.get(P.EXT)
    if plumb is None:
        plumb = ext[P.EXT] = {}
    elif not isinstance(plumb, dict):
        raise _err("$extensions.plumb must be an object", "write it as \"plumb\": { \"schema\": 1, ... }")
    schema = plumb.get("schema")
    if schema is not None and (isinstance(schema, bool) or not isinstance(schema, int) or schema < 0):
        raise _err(f"$extensions.plumb.schema is {schema!r}", "write the schema as a whole number, e.g. 1")
    if isinstance(schema, int) and schema > P.SCHEMA_VERSION:
        raise _err(f"the tokens file uses schema {schema}, newer than this build-tokens.py supports ({P.SCHEMA_VERSION})",
                   "update the Plumb plugin and the project's scripts first, then run --migrate again")
    if schema is None or schema == 0:
        plumb["schema"] = P.SCHEMA_VERSION
        added.append("$extensions.plumb.schema = 1")
    defaults = {"platforms": ["web"], "docs_dir": "docs/design"}
    if defaults_project:
        defaults["project"] = defaults_project
    for key, value in defaults.items():
        if key not in plumb:
            plumb[key] = value
            added.append(f"$extensions.plumb.{key} = {json.dumps(value)}")
    for key, subdefaults in (("web", {"styling": "css", "copies": []}), ("contrast", {"extra_pairs": []})):
        sub = plumb.get(key)
        if sub is None:
            sub = plumb[key] = {}
        elif not isinstance(sub, dict):
            raise _err(f"$extensions.plumb.{key} must be an object", f"write it as \"{key}\": {json.dumps(subdefaults)}")
        for k, v in subdefaults.items():
            if k not in sub:
                sub[k] = v
                added.append(f"$extensions.plumb.{key}.{k} = {json.dumps(v)}")
    return added


def css_vars(doc: dict) -> str:
    """Plain custom properties: :root (light), the md breakpoint, .dark and the prefers-color-scheme dark block."""

    def rule(selector: str, decls: List[Tuple[str, str]], indent: str = "", extra: Tuple[str, ...] = ()) -> List[str]:
        lines = [f"{indent}{selector} {{"] + [f"{indent}  {n}: {v};" for n, v in decls] + [f"{indent}  {e}" for e in extra]
        return lines + [f"{indent}}}"]

    out = rule(":root", declarations(doc, "light"))
    md = declarations(doc, "md")
    if md:
        out += ["@media (min-width: 48rem) {"] + rule(":root", md, "  ") + ["}"]
    dark = declarations(doc, "dark")
    if dark:
        out += rule(".dark", dark, extra=("color-scheme: dark;",))
        out += ["@media (prefers-color-scheme: dark) {"] + rule(":root:not(.light)", dark, "  ", ("color-scheme: dark;",)) + ["}"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- cli


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: python3 {SCRIPT_REL} [--check | --contrast | --migrate | --css-vars] [--root SKILL_DIR] [--project PATH]\n")


def _write(path: Path, text: str, root: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as exc:
        print(f"error: cannot write {rel(path, root)} ({exc})\nfix: check the folder exists and is writable", file=sys.stderr)
        return False
    return True


def main(argv: Optional[List[str]] = None) -> int:
    P.utf8_stdio()
    parser = _Parser(prog="build-tokens.py", description="Build the token outputs from the tokens JSON.")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 when any output is stale or missing")
    parser.add_argument("--contrast", action="store_true", help="rewrite the contrast block of references/dark-mode.md")
    parser.add_argument("--migrate", action="store_true", help="add the missing settings to the tokens JSON (additive)")
    parser.add_argument("--css-vars", action="store_true", help="print the tokens as plain CSS custom properties")
    parser.add_argument("--root", metavar="SKILL_DIR", help="the design-system skill folder (default: this script's skill)")
    parser.add_argument("--project", metavar="PATH", help="project root when no PLUMB.md is found above the skill")
    args = parser.parse_args(argv)
    if sum(bool(x) for x in (args.check, args.contrast, args.migrate, args.css_vars)) > 1:
        parser.error("pass only one of --check, --contrast, --migrate, --css-vars")
    skill_dir = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    project = Path(args.project) if args.project else None
    try:
        return _run(args, skill_dir, project)
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


def _run(args: argparse.Namespace, skill_dir: Path, project: Optional[Path]) -> int:
    root = find_project_root(skill_dir, project)
    tokens_file = find_tokens_file(skill_dir)
    doc = P.load_tokens(tokens_file)
    if args.css_vars:
        sys.stdout.write(css_vars(doc))
        return 0
    if args.migrate:
        added = migrate(doc, P.read_plumb_md(root / "PLUMB.md").get("Project", ""))
        if not added:
            print(f"ok: {rel(tokens_file, root)} is at schema {P.SCHEMA_VERSION}, nothing to add")
            return 0
        text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        if not _write(tokens_file, text, root):
            return 2
        for line in added:
            print(f"added {line}")
        print(f"wrote {rel(tokens_file, root)}")
        return 0
    if args.contrast:
        found = contrast_output(doc, skill_dir, required=True)
        assert found is not None
        path, text = found
        if read_dark_doc(skill_dir) == text:
            print(f"ok: the contrast block in {rel(path, root)} is up to date")
        else:
            if not _write(path, text, root):
                return 2
            print(f"wrote {rel(path, root)}")
        fails = text.count("| fail (")
        if fails:
            print(f"{fails} pair(s) fail: see the nearest passing values in {rel(path, root)}")
        return 0
    files = outputs(doc, skill_dir, project, tokens_file)
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
            # a checkout with CRLF line endings or a BOM (git autocrlf) is not stale; a plain build still rewrites it
            if current is None or P.normalise_text(current.decode("utf-8", errors="replace")) != text:
                stale.append(path)
            continue
        if not _write(path, text, root):
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
