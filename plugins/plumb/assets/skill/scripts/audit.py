#!/usr/bin/env python3
"""audit.py: check UI source against the project's design tokens.

Usage:
  audit.py [PATHS...] [--json] [--root SKILL_DIR] [--project PATH]     full audit (default: the whole project)
  audit.py --quick FILE [--before -|PATH] [--root SKILL_DIR]            one file, only what an edit adds (JSON)

Full mode prints every finding as `file:line: <severity> <rule>: <message>` and `  fix: <fix>`, then a summary.
--quick reads the file's text before the edit from stdin (`--before -`) or a file, audits FILE as it is now, and prints
JSON with only the findings the edit adds (compared by rule and matched text, not by line, so moved lines are not new).
--json prints {"version", "checked", "errors", "warnings", "findings": [{"rule","severity","file","line","message","fix"}]}.

Severity: **error** is a hard rule: raw colour, arbitrary design value, Tailwind default palette colour, off-scale type /
radius / spacing, off-token duration or easing, outline-none, design properties in inline styles, a second icon library,
emoji in UI source, and the Swift / Kotlin raw values. Errors fail the audit (exit 1) and the edit check refuses them.
**warn** is softer and only reported: `dark:` outside the primitives, a hand-rolled accessibility primitive, a primitive
restyled from outside.

Every allowed value comes from the project's tokens (assets/tokens/*.tokens.json): durations are the motion.duration
tokens, the type scale is the typography token names, radii the radius tokens, spacing the spacing tokens. Fixes are
token-aware: `bg-[#14857F]` -> `bg-primary (color.primary = #14857f)`; a value with no close token says to add one with
/plumb:update. Without a tokens file only the rules that need no tokens run.

Always allowed: arbitrary values for layout geometry (width, height, top/left, grid templates, z-index); files on
PLUMB.md's `Allowed raw values:` list (e.g. components/ui/**, where the primitives live) are exempt from every rule
except outline-none, icon library and emoji. Exceptions are by path only, never by a comment in the line. Comments are
not checked.

Files: .tsx .jsx .ts .js .vue .svelte .astro .html .css .scss (web), .swift, .kt. Never node_modules or build output
(.next dist build out coverage Pods DerivedData ...), never files over 5 MB. A `GENERATED ... do not edit` header exempts
a file only on the paths Plumb's generators own: <skill>/assets/platforms/** (not starter/), the copies listed in
$extensions.plumb.web.copies, and the generated pages in the docs folder (specimen.html, prototype.html, screens.html,
tours/*.html, audit-*.html); anywhere else the header is just a comment and the file is audited. With no PATHS the project
is walked: PLUMB.md `UI files:` narrows it, the design-system skill's own folder is left out except
assets/platforms/*/starter/, and docs/design is left to the prototype checks. PATHS given are always checked.

Hooks load this file by path (it is not in a package). Register the module in sys.modules before running it, or
its dataclasses fail:
    spec = importlib.util.spec_from_file_location("plumb_audit", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plumb_audit"] = mod      # required before exec_module (dataclasses look the module up)
    spec.loader.exec_module(mod)
Hooks pass make_settings(root, load_doc(skill_dir)) as settings; it adds "_shadcn" when the project has shadcn primitives.

Exit codes: 0 no errors (warnings allowed), 1 errors found, 2 nothing checked or bad input (error: ... then fix: ...).

Python 3.9+, standard library only. Imports the shared core _plumb.py from its own directory. audit_text() and quick()
are pure (no IO) and are what the hooks call.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _plumb as P  # noqa: E402
from _plumb import PlumbError  # noqa: E402

SCRIPT_REL = "scripts/audit.py"
USAGE = f"python3 {SCRIPT_REL} [PATHS...] [--json] [--root SKILL_DIR] | --quick FILE --before -"
WEB_EXT = frozenset((".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".astro", ".html", ".css", ".scss"))
PLATFORM_OF = {**{e: "web" for e in WEB_EXT}, ".swift": "ios", ".kt": "android"}
SKIP_DIRS = frozenset((
    "node_modules", ".next", "dist", "build", "out", ".git", "coverage", "Pods", "DerivedData",
    ".nuxt", ".output", ".svelte-kit", ".turbo", ".vercel", ".parcel-cache", ".cache", ".gradle", ".expo",
    "__pycache__", ".venv", "venv",
))
MAX_BYTES = 5 * 1024 * 1024
FAR_COLOUR = 10.0  # CIEDE2000: at or above this no token is "close"
ADD_TOKEN = "add a token with /plumb:update, then use it"


# ---------------------------------------------------------------- data


@dataclass(frozen=True)
class Hit:
    """One match of a rule: where it starts, the matched text, and (optionally) a specific message and fix."""

    pos: int
    match: str
    message: Optional[str] = None
    fix: Optional[str] = None


@dataclass
class Rule:
    """One row of the rule table. kind: "file" (per file: hooks + full); cross-file rules come later as "cross".

    check(ctx) yields Hits; message is a template with {match}; fix is the default (non token-aware) fix.
    skip_allowed: the rule does not apply to paths on PLUMB.md's `Allowed raw values:` list.
    """

    id: str
    severity: str
    platforms: Tuple[str, ...]
    kind: str
    check: Callable[["Ctx"], Iterable[Hit]]
    message: str
    fix: str
    skip_allowed: bool = True


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    message: str
    fix: str
    match: str = field(default="", repr=False, compare=False)  # normalised in quick(); not in the JSON
    source: str = field(default="", repr=False, compare=False)  # the line's text (empty for very long lines)

    def to_json(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "file": self.file, "line": self.line,
                "message": self.message, "fix": self.fix}


# ---------------------------------------------------------------- token scales


def num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.4f}".rstrip("0").rstrip(".")


def varname(path: str) -> str:
    """The CSS custom property build-tokens.py writes for a token path (kept in step with build-tokens.varname)."""
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


_MS = re.compile(r"^\s*(\d*\.?\d+)\s*(ms|s)?\s*$")


def _to_ms(v: object) -> Optional[float]:
    if isinstance(v, dict) and "value" in v:
        v = f"{v['value']}{v.get('unit', 'ms')}" if isinstance(v["value"], (int, float)) else None
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        return None
    m = _MS.match(str(v))
    if not m:
        return None
    return float(m.group(1)) * (1000 if m.group(2) == "s" else 1)


class Scales:
    """Everything the rules need from one tokens document, computed once."""

    def __init__(self, doc: dict) -> None:
        self.doc = doc
        self.colours: List[Tuple[str, str, str]] = []  # (path, utility name, #rrggbb)
        self.hex_of: Dict[str, str] = {}
        self.type: Dict[str, float] = {}  # name -> font size px
        self.radius: Dict[str, float] = {}
        self.spacing: Dict[str, float] = {}
        self.durations: List[Tuple[str, str, float]] = []  # (path, name, ms)
        self.easings: List[Tuple[str, str, Optional[Tuple[float, ...]]]] = []
        self.shadows: List[str] = []
        self.px_of: Dict[str, float] = {}
        self.base = 4.0
        self._memo: Dict[tuple, object] = {}
        self.aliases = set()
        for path, tok, ttype in P.iter_tokens(doc):
            if isinstance(tok.get("$value"), str) and tok["$value"].startswith("{"):
                self.aliases.add(path)
            parts = path.split(".")
            group, name = parts[0], "-".join(parts[1:])
            try:
                value = P.resolve(doc, path)
            except PlumbError:
                continue
            if ttype == "color":
                try:
                    hexv = P.parse_color(value)[0]
                except PlumbError:
                    continue
                util = varname(path)[len("--color-"):]
                self.colours.append((path, util, hexv))
                self.hex_of[path] = hexv
            elif group == "typography":
                px = P._px(value.get("fontSize")) if isinstance(value, dict) else None
                if px is not None:
                    self.type[name] = px
                    self.px_of[path] = px
            elif group in ("radius", "spacing"):
                px = P._px(value)
                if px is None:
                    continue
                getattr(self, group)[name] = px
                self.px_of[path] = px
                if group == "spacing" and name in ("base", "unit"):
                    self.base = px or 4.0
            elif group == "motion" and len(parts) > 2 and parts[1] == "duration":
                ms = _to_ms(value)
                if ms is not None:
                    self.durations.append((path, "-".join(parts[2:]), ms))
            elif group == "motion" and len(parts) > 2 and parts[1] == "easing":
                curve = None
                if isinstance(value, list) and len(value) == 4 and all(isinstance(x, (int, float)) for x in value):
                    curve = tuple(float(x) for x in value)
                self.easings.append((path, "-".join(parts[2:]), curve))
            elif group == "shadow":
                self.shadows.append(name)
        self.colour_names = {c[1] for c in self.colours}
        self.duration_ms = {d[2] for d in self.durations}
        self.easing_names = {e[1] for e in self.easings}
        self.spacing_px = set(self.spacing.values())

    # ---- nearest tokens (memoised: a minified file repeats the same values thousands of times)

    def nearest_colour(self, hexv: str, role: str) -> Optional[Tuple[str, str, str, float]]:
        key = ("c", hexv, role)
        if key not in self._memo:
            self._memo[key] = self._nearest_colour(hexv, role)
        return self._memo[key]  # type: ignore[return-value]

    def _nearest_colour(self, hexv: str, role: str) -> Optional[Tuple[str, str, str, float]]:
        best = P.nearest_token(self.doc, "color", hexv)
        if best is None or best[0] not in self.hex_of:
            return None
        path, dist = best
        same = [c for c in self.colours if c[2] == self.hex_of[path]]  # tokens with the identical value
        # among tokens with the identical value: the one whose role fits the utility, then a source over an alias
        pick = min(same, key=lambda c: (_role_score(c[1], role), c[0] in self.aliases)) if same else (path, "", self.hex_of[path])
        return pick[0], pick[1], pick[2], dist

    def nearest_dimension(self, group: str, px: float) -> Optional[Tuple[str, float, float]]:
        key = ("d", group, px)
        if key not in self._memo:
            best = P.nearest_token(self.doc, group, f"{num(px)}px")
            self._memo[key] = (best[0], self.px_of.get(best[0], px), best[1]) if best else None
        return self._memo[key]  # type: ignore[return-value]

    def nearest_duration(self, ms: float) -> Optional[Tuple[str, str, float]]:
        return min(self.durations, key=lambda d: abs(d[2] - ms)) if self.durations else None

    def nearest_easing(self, curve: Optional[Tuple[float, ...]]) -> Optional[Tuple[str, str, Optional[tuple]]]:
        if not self.easings:
            return None
        if curve is None:
            return self.easings[0]
        return min(self.easings, key=lambda e: sum((a - b) ** 2 for a, b in zip(e[2], curve)) if e[2] else 99.0)


_SCALES: Dict[int, Tuple[dict, Scales]] = {}


def scales_for(doc: Optional[dict]) -> Optional[Scales]:
    if not isinstance(doc, dict):
        return None
    cached = _SCALES.get(id(doc))
    if cached is None or cached[0] is not doc:
        if len(_SCALES) > 8:
            _SCALES.clear()
        cached = (doc, Scales(doc))
        _SCALES[id(doc)] = cached
    return cached[1]


_TEXTISH = re.compile(r"(?:^|-)(?:on|text|ink|fg|foreground)(?:-|$)")
_LINEISH = re.compile(r"(?:^|-)(?:outline|border|ring|divider|stroke)(?:-|$)")


def _role_score(name: str, role: str) -> int:
    texty = name.startswith("on-") or _TEXTISH.search(name) is not None
    if role == "text":
        return 0 if texty else 1
    if role == "line":
        return 0 if _LINEISH.search(name) else (1 if not texty else 2)
    return 1 if texty else 0


def _role_of_prefix(prefix: str) -> str:
    base = prefix.lstrip("-").split("-")[0]
    if base in ("text", "placeholder", "caret", "decoration", "color"):
        return "text"
    if base in ("border", "ring", "outline", "divide", "stroke"):
        return "line"
    return "fill"


# ---------------------------------------------------------------- per-file context


_STRINGS = r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`"
# Strings come first in each alternation, so "/*" or " //" inside a string never starts a comment.
_STRING_OR_COMMENT = re.compile(_STRINGS + r"|(?<![\w.*/])/\*.*?\*/|<!--.*?-->|(?:^|(?<=[\s;{}]))//[^\n]*", re.S | re.M)
_CSS_STRING_OR_COMMENT = re.compile(_STRINGS + r"|(?<![\w.*/])/\*.*?\*/", re.S)
_NOT_NL = re.compile(r"[^\n]")
_GENERATED = re.compile(r"do not edit", re.I)


def _blank(m: "re.Match[str]") -> str:
    s = m.group(0)
    return s if s[0] in "\"'`" else _NOT_NL.sub(" ", s)


def mask_comments(text: str, ext: str) -> str:
    """The text with comments replaced by spaces (newlines kept, so offsets and line numbers do not move).

    String literals are skipped over, never blanked, so a "/*" or " //" inside one cannot hide the code after it."""
    pattern = _CSS_STRING_OR_COMMENT if ext in (".css",) else _STRING_OR_COMMENT
    return pattern.sub(_blank, text)


def normalise_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_generated(text: str) -> bool:
    head = "\n".join(text[:1500].splitlines()[:5])
    return "GENERATED" in head and _GENERATED.search(head) is not None


_GENERATED_PAGES = ("specimen.html", "prototype.html", "screens.html", "tours/*.html", "audit-*.html")
_PLATFORM_OUTPUT = re.compile(r"(?:^|/)assets/platforms/")
# Folder names that are build output wherever they appear; build, out, dist and coverage only count inside the project
# (a relative path), because a project may itself live under a folder with one of those names.
_ALWAYS_OUTPUT = SKIP_DIRS - {"build", "out", "dist", "coverage"}


def generator_owned(path_name: str, settings: dict) -> bool:
    """A path Plumb's generators write: <skill>/assets/platforms/** (not starter/), web.copies, the docs folder pages."""
    path = path_name.replace("\\", "/")
    if _PLATFORM_OUTPUT.search(path) and "starter" not in path.split("assets/platforms/", 1)[-1].split("/")[:-1]:
        return True
    web = settings.get("web") if isinstance(settings.get("web"), dict) else {}
    copies = [c for c in (web.get("copies") or []) if isinstance(c, str)]
    docs = str(settings.get("docs_dir") or "docs/design").replace("\\", "/").strip("/")
    return path_matches(path, copies) or path_matches(path, [f"{docs}/{page}" for page in _GENERATED_PAGES])


def in_build_output(path_name: str) -> bool:
    path = path_name.replace("\\", "/")
    absolute = path.startswith("/") or re.match(r"^[A-Za-z]:/", path) is not None
    names = _ALWAYS_OUTPUT if absolute else SKIP_DIRS
    return any(part in names for part in path.split("/")[:-1])


def file_ext(path_name: str) -> Optional[str]:
    name = path_name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name.endswith(".d.ts"):
        return None
    dot = name.rfind(".")
    ext = name[dot:] if dot > 0 else ""
    return ext if ext in PLATFORM_OF else None


def _split_list(value: object) -> List[str]:
    return [g for g in re.split(r"[,\s]+", str(value or "")) if g and g not in ("·", "-")]


def _glob_rx(glob: str) -> "re.Pattern[str]":
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


def path_matches(path: str, globs: Sequence[str]) -> bool:
    """True when the path, or any trailing part of it (so absolute and Windows paths work), matches a glob."""
    if not globs:
        return False
    rxs = [_glob_rx(g) for g in globs]
    parts = path.replace("\\", "/").split("/")
    for i in range(len(parts)):
        sub = "/".join(parts[i:])
        if sub and any(rx.match(sub) for rx in rxs):
            return True
    return False


def _is_theme_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return any(p.lower() == "theme" for p in parts[:-1]) or re.search(r"Theme\.(swift|kt)$", parts[-1]) is not None


_APPLY = re.compile(r"@apply\s[^;{}]*")
_STYLE_BLOCK = re.compile(r"<style\b.*?(?:</style\s*>|\Z)", re.S | re.I)


def _in_spans(spans: List[Tuple[int, int]], pos: int) -> bool:
    i = bisect.bisect_right(spans, (pos, float("inf"))) - 1
    return i >= 0 and spans[i][0] <= pos < spans[i][1]


class Ctx:
    """One file being checked: its text (comments blanked in .code), platform, tokens and settings."""

    def __init__(self, path_name: str, text: str, doc: Optional[dict], settings: dict) -> None:
        self.path = path_name.replace("\\", "/")
        self.ext = file_ext(self.path) or ""
        self.platform = PLATFORM_OF.get(self.ext, "web")
        self.text = text
        self.code = mask_comments(text, self.ext)
        self.doc = doc if isinstance(doc, dict) else None
        self.scales = scales_for(self.doc)
        self.settings = settings or {}
        web = self.settings.get("web")
        if not isinstance(web, dict):
            web = P.plumb_settings(self.doc or {})["web"]
        self.web = web
        styling = str(web.get("styling", "css"))
        packages = str(self.settings.get("UI packages", "")).lower()
        if self.doc is None and "tailwind" in packages:
            styling = "tailwind-v3" if re.search(r"tailwind\s*v?3", packages) else "tailwind-v4"
        self.styling = styling
        self.tailwind = styling in ("tailwind-v4", "tailwind-v3")
        self.allowed = path_matches(self.path, _split_list(self.settings.get("Allowed raw values")))
        self.theme_path = _is_theme_path(self.path)
        self.stylesheet = self.ext in (".css", ".scss")  # no markup or imports: the markup-only rules skip it
        self.shadcn = "shadcn" in packages or self.settings.get("_shadcn") is True
        self._apply: Optional[List[Tuple[int, int]]] = None
        self._transitions: Optional[List[Tuple[int, int]]] = None
        self._styles: Optional[List[Tuple[int, int]]] = None
        self._nl = [m.start() for m in re.finditer("\n", text)]

    def class_ok(self, pos: int) -> bool:
        """Tailwind classes count anywhere in markup and scripts; in a stylesheet only after @apply."""
        if not self.stylesheet:
            return True
        if self._apply is None:
            self._apply = [m.span() for m in _APPLY.finditer(self.code)]
        return _in_spans(self._apply, pos)

    def in_transition(self, pos: int) -> bool:
        """Inside the value of a transition declaration (CSS, a style attribute or a JS style object)."""
        if self._transitions is None:
            self._transitions = [m.span(2) for m in _TRANSITION_DECL.finditer(self.code)]
        return _in_spans(self._transitions, pos)

    def in_style_block(self, pos: int) -> bool:
        if self._styles is None:
            self._styles = [m.span() for m in _STYLE_BLOCK.finditer(self.code)]
        return _in_spans(self._styles, pos)

    def line_of(self, pos: int) -> int:
        return bisect.bisect_right(self._nl, pos - 1) + 1 if pos > 0 else 1

    def line_text(self, line: int, limit: int = 1000) -> str:
        start = self._nl[line - 2] + 1 if line >= 2 else 0
        end = self._nl[line - 1] if line - 1 < len(self._nl) else len(self.text)
        return self.text[start:end].strip() if end - start <= limit else ""


# ---------------------------------------------------------------- fixes


def _colour_fix(ctx: Ctx, hexv: str, alpha: float, prefix: Optional[str], role: str) -> Optional[str]:
    s = ctx.scales
    if s is None:
        return None
    if not s.colours:
        return f"no colour tokens yet: {ADD_TOKEN}"
    near = s.nearest_colour(hexv, role)
    if near is None:
        return None
    path, util, tokhex, dist = near
    if dist >= FAR_COLOUR:
        return f"no colour token is close (nearest {path} = {tokhex}, ΔE {dist:.1f}): {ADD_TOKEN}"
    if prefix:
        use = f"{prefix}-{util}" + (f"/{round(alpha * 100)}" if alpha < 1 else "")
    else:
        use = f"var({varname(path)})"
    return f"{use} ({path} = {tokhex})"


def _mobile_colour_fix(ctx: Ctx, hexv: Optional[str]) -> Optional[str]:
    s = ctx.scales
    if s is None or hexv is None:
        return None
    if not s.colours:
        return f"no colour tokens yet: {ADD_TOKEN}"
    near = s.nearest_colour(hexv, "fill")
    if near is None:
        return None
    path, _util, tokhex, dist = near
    if dist >= FAR_COLOUR:
        return f"no colour token is close (nearest {path} = {tokhex}, ΔE {dist:.1f}): {ADD_TOKEN}"
    return f"use the {path} token ({tokhex}) from the generated theme"


def _dimension_fix(ctx: Ctx, group: str, px: float, utility: Optional[str]) -> Optional[str]:
    """utility: 'text', 'rounded-t', 'p', '-mt' ... (Tailwind); None for CSS (var(--...)); 'theme' for mobile."""
    s = ctx.scales
    if s is None:
        return None
    near = s.nearest_dimension(group, px)
    if near is None:
        return f"no {group} tokens yet: {ADD_TOKEN}"
    path, tokpx, dist = near
    name = "-".join(path.split(".")[1:])
    if group == "spacing" and utility not in (None, "theme") and s.base:
        step = tokpx / s.base  # Tailwind spacing utilities are steps of the base, whatever the token is called
        name = num(step) if (step * 2).is_integer() else name
    if utility == "theme":
        text = f"use the {path} token ({num(tokpx)}px) from the generated theme"
    elif utility:
        text = f"{utility}-{name} ({path} = {num(tokpx)}px)"
    else:
        text = f"var({varname(path)}) ({path} = {num(tokpx)}px)"
    if dist:
        text += f"; if the design needs {num(px)}px, {ADD_TOKEN}"
    return text


def _duration_fix(ctx: Ctx, ms: float, utility: Optional[str]) -> Optional[str]:
    s = ctx.scales
    near = s.nearest_duration(ms) if s else None
    if near is None:
        return None
    path, _name, tok = near
    use = f"{utility}-{num(tok)}" if utility else f"var({varname(path)})"
    return f"{use} ({path} = {num(tok)}ms)"


_KEYWORD_CURVES = {"ease": (0.25, 0.1, 0.25, 1.0), "ease-in": (0.42, 0.0, 1.0, 1.0), "ease-out": (0.0, 0.0, 0.58, 1.0),
                   "ease-in-out": (0.42, 0.0, 0.58, 1.0), "linear": (0.0, 0.0, 1.0, 1.0)}


def _easing_fix(ctx: Ctx, curve: Optional[Tuple[float, ...]], tailwind: bool) -> Optional[str]:
    s = ctx.scales
    near = s.nearest_easing(curve) if s else None
    if near is None:
        return None
    path, name, _c = near
    use = f"ease-{name}" if tailwind else f"var({varname(path)})"
    return f"{use} ({path})"


# ---------------------------------------------------------------- web rules

# A class starts the text or follows whitespace, a quote, a colon (variants), {, (, ! or a comma.
CLS = r"(?<![^\s\"'`:{(!,])"
_CFUNC = re.compile(r"(?<![\w-])(?:rgba?|hsla?|oklch|oklab|lch|hwb)\(")
_HEX = re.compile(r"(?<![\w&/#$@])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])")
_ATTR_BEFORE = re.compile(r"(?<![\w-])(?:href|to|xlinkHref|xlink:href|src|action|for|id|anchor|hash)\s*[=:]\s*\{?\s*[\"'`]?\Z")
_URL_BEFORE = re.compile(r"url\(\s*[\"']?\Z")
_SELECTOR_CALLS = ("querySelector(", "querySelectorAll(", "getElementById(", "closest(", "matches(")
_TO_STOP = re.compile(r"[^{};\n'\"`]*")
_SELECTOR_CHARS = re.compile(r"[\w\s,.#>+~*:()\[\]=^$|-]*\Z")
_UTIL_BEFORE_BRACKET = re.compile(r"(?<![^\s\"'`:{(!,])(-?[a-z][a-z0-9-]*?)-\Z")
_PROP_START = re.compile(r"\s*[\"']?([a-zA-Z-]+)")


def _selector_follows(code: str, end: int) -> bool:
    """True when the colour-looking #name is a CSS id selector (`#add {`, `#add,` at the end of a selector line)."""
    window = code[end:end + 300]
    m = _TO_STOP.match(window)
    between, stop = window[:m.end()], window[m.end():m.end() + 1]
    if stop == "{":
        return _SELECTOR_CHARS.match(between) is not None
    return stop in ("\n", "") and between.strip() == ","


def _class_prefix(code: str, pos: int) -> Optional[str]:
    """The Tailwind utility a colour sits in: `bg` for bg-[#fff], `border-t` for hover:border-t-[#fff]."""
    lb = code.rfind("[", max(0, pos - 80), pos)
    if lb < 0 or any(c in code[lb + 1:pos] for c in " \t\n\"'`]"):
        return None
    m = _UTIL_BEFORE_BRACKET.search(code[max(0, lb - 40):lb])
    return m.group(1) if m else None


def _skip_hex_context(code: str, pos: int) -> bool:
    """A #name that is a link target, a url(#id) reference or a selector passed to querySelector(...)."""
    if _ATTR_BEFORE.search(code, max(0, pos - 40), pos) or _URL_BEFORE.search(code, max(0, pos - 12), pos):
        return True
    start = max(0, pos - 150)
    for call in _SELECTOR_CALLS:
        at = code.rfind(call, start, pos)
        if at >= 0:
            between = code[at + len(call):pos].lstrip()
            if between[:1] in ("'", '"', "`") and not any(q in between[1:] for q in "'\"`"):
                return True
    return False


def _css_role(code: str, pos: int) -> str:
    """The colour's role from the property it is the value of: color -> text, border/outline/stroke -> line."""
    start = max(0, pos - 120)
    cut = max(code.rfind(";", start, pos), code.rfind("{", start, pos), code.rfind("}", start, pos), code.rfind(",", start, pos))
    m = _PROP_START.match(code, cut + 1 if cut >= 0 else start, pos)
    prop = m.group(1).lower() if m else ""
    if prop == "color":
        return "text"
    if prop.startswith(("border", "outline", "stroke")):
        return "line"
    return "fill"


_WORD_BEFORE = re.compile(r"[A-Za-z]{2,}\.?\s+\Z")
_CSS_VALUE_HINT = re.compile(r"\d(?:px|rem|em|%)|\b(?:solid|dashed|dotted|double|groove|ridge|inset|outset)\b")


def _is_copy(ctx: Ctx, code: str, pos: int, end: int) -> bool:
    """True for #123 in a JSX/HTML text node (between > and <) or in a string that reads as words ("Issue #456").

    Class names, style values and stylesheets (including <style> blocks) are never copy."""
    if ctx.stylesheet or ctx.in_style_block(pos):
        return False
    start = max(0, pos - 300)
    gt, lt = code.rfind(">", start, pos), code.rfind("<", start, pos)
    if gt > lt and code[gt - 1:gt] not in ("=", "-"):
        nxt = code.find("<", end, end + 300)
        around = code[gt + 1:pos] + code[end:nxt] if nxt >= 0 else ""
        # apostrophes are normal in copy; quotes, ; = ? && || mean the > was code (a comparison), not a tag
        if nxt >= 0 and not any(c in around for c in "\"`;=?") and "&&" not in around and "||" not in around:
            return True
    line_start = code.rfind("\n", 0, pos) + 1
    before = code[line_start:pos]
    q = max(before.rfind(c) for c in "\"'`")
    if q < 0:
        return False
    inner = before[q + 1:]
    eol = code.find("\n", end)
    closes = code.find(before[q], end, eol if eol >= 0 else len(code)) >= 0
    return closes and _WORD_BEFORE.search(inner) is not None and _CSS_VALUE_HINT.search(inner) is None


def _parse_hex(digits: str) -> Tuple[str, float]:
    """('#rrggbb', alpha) from the digits of #rgb, #rgba, #rrggbb or #rrggbbaa."""
    d = digits.lower()
    if len(d) in (3, 4):
        d = "".join(c * 2 for c in d)
    alpha = round(int(d[6:8], 16) / 255, 4) if len(d) == 8 else 1.0
    return "#" + d[:6], alpha


def check_raw_colour(ctx: Ctx) -> Iterator[Hit]:
    code = ctx.code
    for m in _HEX.finditer(code):
        pos = m.start()
        digits = m.group(1)
        if len(digits) in (3, 4) and digits.isdigit() and _is_copy(ctx, code, pos, m.end()):
            continue  # "Order #123" in a text node or a sentence-like string is a number, not a colour
        if _skip_hex_context(code, pos) or _selector_follows(code, m.end()):
            continue
        hexv, alpha = _parse_hex(digits)
        prefix = _class_prefix(code, pos)
        role = _role_of_prefix(prefix) if prefix else _css_role(code, pos)
        yield Hit(pos, m.group(0), fix=_colour_fix(ctx, hexv, alpha, prefix, role))
    for m in _CFUNC.finditer(code):
        close = code.find(")", m.end(), m.end() + 200)
        args = code[m.end():close if close >= 0 else m.end() + 200]
        if "var(" in args or "$" in args or "{" in args:
            continue
        text = code[m.start():close + 1] if close >= 0 else m.group(0)
        yield Hit(m.start(), text, fix=_colour_fn_fix(ctx, code, m.start(), text))


_RGB_ARGS = re.compile(r"^rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})")


def _colour_fn_fix(ctx: Ctx, code: str, pos: int, text: str) -> Optional[str]:
    m = _RGB_ARGS.match(text)
    if not m:
        return None
    rgb = [min(255, int(x)) for x in m.groups()]
    prefix = _class_prefix(code, pos)
    role = _role_of_prefix(prefix) if prefix else _css_role(code, pos)
    return _colour_fix(ctx, "#" + "".join(f"{c:02x}" for c in rgb), 1.0, prefix, role)


_ARB_PREFIX = (
    r"text|tracking|leading|shadow|inset-shadow|drop-shadow|bg|rounded(?:-[trblse]{1,2})?|border(?:-[trblxyse]{1,2})?"
    r"|divide(?:-[xy])?|ring(?:-offset)?|outline(?:-offset)?|font|duration|delay|ease|animate|blur|backdrop-blur|opacity"
    r"|fill|stroke|decoration|accent|caret|placeholder|from|via|to|p[xytrblse]?|m[xytrblse]?|gap(?:-[xy])?|space-[xy]"
)
_ARB = re.compile(CLS + r"(-?(?:" + _ARB_PREFIX + r"))-(\[[^\]\s\"'`]{1,300}\]|\(--[\w-]{1,100}\))")
_DESIGN_PROPS = (
    r"color|background(?:-color|-image)?|font-(?:size|weight|family)|line-height|letter-spacing|border(?:-[a-z]+)?-radius"
    r"|border(?:-[a-z]+)?-color|box-shadow|text-shadow|transition(?:-[a-z]+)?|animation(?:-[a-z]+)?|opacity|fill|stroke"
    r"|outline(?:-color)?|filter|backdrop-filter"
)
_ARB_PROP = re.compile(CLS + r"\[(" + _DESIGN_PROPS + r"):([^\]\s\"'`]{1,300})\]")
_VAR_ONLY = re.compile(r"^\[(?:[a-z-]+:)?(?:var\(--[\w-]+\)|--[\w-]+)\]$|^\(--[\w-]+\)$|^(?:[a-z-]+:)?var\(--[\w-]+\)$")
_BG_LAYOUT = re.compile(r"^\[(?:url\(|position:|size:|length:|image:url\()")
_PX_VALUE = re.compile(r"^\[?(-?\d*\.?\d+)(px|rem)\]?$")
_MS_VALUE = re.compile(r"^\[(\d*\.?\d+)(ms|s)\]$")
_CURVE = re.compile(r"cubic-bezier\(\s*(-?[\d.]+)[\s,_]+(-?[\d.]+)[\s,_]+(-?[\d.]+)[\s,_]+(-?[\d.]+)\s*\)")


def _has_colour(text: str) -> bool:
    return _HEX.search(text) is not None or _CFUNC.search(text) is not None


def _px_of(value: str) -> Optional[float]:
    m = _PX_VALUE.match(value)
    return float(m.group(1)) * (16 if m.group(2) == "rem" else 1) if m else None


def _names(names: Iterable[str], prefix: str) -> str:
    listed = [f"{prefix}-{n}" for n in names][:8]
    return ", ".join(listed) if listed else "(none yet)"


def _arbitrary_fix(ctx: Ctx, utility: str, value: str) -> Optional[str]:
    s = ctx.scales
    if s is None:
        return None
    base = utility.lstrip("-")
    px = _px_of(value)
    if base == "text":
        if px is not None:
            return _dimension_fix(ctx, "typography", px, "text")
        return f"use a type scale utility: {_names(s.type, 'text')}"
    if base in ("leading", "tracking"):
        return f"use a type scale utility (each sets its line height and tracking): {_names(s.type, 'text')}"
    if base.startswith("rounded"):
        return _dimension_fix(ctx, "radius", px, utility) if px is not None else f"use {_names(s.radius, 'rounded')}"
    if re.match(r"^(?:p[xytrblse]?|m[xytrblse]?|gap(?:-[xy])?|space-[xy])$", base):
        return _dimension_fix(ctx, "spacing", px, utility) if px is not None else f"use {_names(s.spacing, base)}"
    if base in ("duration", "delay"):
        m = _MS_VALUE.match(value)
        if m:
            return _duration_fix(ctx, float(m.group(1)) * (1000 if m.group(2) == "s" else 1), base)
        return f"use {_names(sorted({num(d[2]) for d in s.durations}), base)}"
    if base == "ease":
        c = _CURVE.search(value)
        return _easing_fix(ctx, tuple(float(x) for x in c.groups()) if c else None, True)
    if base == "shadow":
        return f"use {_names(s.shadows, 'shadow')}"
    return None


def check_arbitrary_value(ctx: Ctx) -> Iterator[Hit]:
    if not ctx.tailwind:
        return
    code = ctx.code
    for m in _ARB.finditer(code):
        if not ctx.class_ok(m.start()):
            continue
        utility, value = m.group(1), m.group(2)
        if _VAR_ONLY.match(value) or _has_colour(value):
            continue
        if utility.lstrip("-") == "bg" and _BG_LAYOUT.match(value):
            continue
        yield Hit(m.start(), m.group(0), fix=_arbitrary_fix(ctx, utility, value))
    for m in _ARB_PROP.finditer(code):
        if not ctx.class_ok(m.start()):
            continue
        value = m.group(2)
        if _VAR_ONLY.match(value) or _has_colour(value):
            continue
        yield Hit(m.start(), m.group(0))


_FAMILIES = ("slate gray zinc neutral stone red orange amber yellow lime green emerald teal cyan sky blue indigo violet "
             "purple fuchsia pink rose").split()
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
PALETTE: Dict[str, str] = {"white": "#ffffff", "black": "#000000"}
for _row in _PALETTE_HEX.strip().splitlines():
    _fam, *_hexes = _row.split()
    PALETTE.update({f"{_fam}-{s}": f"#{h}" for s, h in zip(_SHADES, _hexes)})
_PALETTE = re.compile(
    CLS + r"(-?(?:text|bg|border(?:-[trblxyse]{1,2})?|ring(?:-offset)?|outline|fill|stroke|from|to|via|divide|decoration"
    r"|accent|caret|placeholder|shadow|inset-shadow|drop-shadow))-(white|black|(?:" + "|".join(_FAMILIES) + r")-(?:50|[1-9]00|950))"
    r"(?:/(?:\d{1,3}|\[[^\]\s]{1,20}\]))?(?![\w-])"
)


def check_palette_colour(ctx: Ctx) -> Iterator[Hit]:
    if not ctx.tailwind:
        return
    names = ctx.scales.colour_names if ctx.scales else set()
    for m in _PALETTE.finditer(ctx.code):
        if not ctx.class_ok(m.start()):
            continue
        name = m.group(2)
        if name in names:
            continue
        prefix = m.group(1)
        yield Hit(m.start(), m.group(0), fix=_colour_fix(ctx, PALETTE[name], 1.0, prefix, _role_of_prefix(prefix)))


_TW_TYPE = {"xs": 12, "sm": 14, "base": 16, "lg": 18, "xl": 20, "2xl": 24, "3xl": 30, "4xl": 36, "5xl": 48, "6xl": 60,
            "7xl": 72, "8xl": 96, "9xl": 128}
_TYPE_CLASS = re.compile(CLS + r"text-(xs|sm|base|lg|xl|[2-9]xl)(?![\w-])")
_FONT_SIZE = re.compile(r"(?<![\w-])font-size\s*:\s*([^;{}\n]{1,120})")
_CSS_LEN = re.compile(r"(?<![\w.-])(\d*\.?\d+)(px|rem)(?![\w-])")


def check_off_scale_type(ctx: Ctx) -> Iterator[Hit]:
    s = ctx.scales
    if s is None or not s.type:
        return
    if ctx.tailwind:
        for m in _TYPE_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()):
                continue
            if m.group(1) not in s.type:
                yield Hit(m.start(), m.group(0), fix=_dimension_fix(ctx, "typography", _TW_TYPE[m.group(1)], "text"))
    for m in _FONT_SIZE.finditer(ctx.code):
        for v in _CSS_LEN.finditer(m.group(1)):
            px = float(v.group(1)) * (16 if v.group(2) == "rem" else 1)
            if px:
                yield Hit(m.start(1) + v.start(), v.group(0), message=f"literal font-size {v.group(0)}",
                          fix=_dimension_fix(ctx, "typography", px, None))


_TW_RADIUS = {"xs": 2, "sm": 4, "md": 6, "lg": 8, "xl": 12, "2xl": 16, "3xl": 24, "4xl": 32}
_RADIUS_CLASS = re.compile(CLS + r"(rounded(?:-[trblse]{1,2})?)-(xs|sm|md|lg|xl|2xl|3xl|4xl)(?![\w-])")
_RADIUS_DECL = re.compile(r"(?<![\w-])border(?:-[a-z]+)*-radius\s*:\s*([^;{}\n]{1,120})")


def check_off_scale_radius(ctx: Ctx) -> Iterator[Hit]:
    s = ctx.scales
    if s is None or not s.radius:
        return
    if ctx.tailwind:
        for m in _RADIUS_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()):
                continue
            if m.group(2) not in s.radius:
                yield Hit(m.start(), m.group(0), fix=_dimension_fix(ctx, "radius", _TW_RADIUS[m.group(2)], m.group(1)))
    for m in _RADIUS_DECL.finditer(ctx.code):
        for v in _CSS_LEN.finditer(m.group(1)):
            px = float(v.group(1)) * (16 if v.group(2) == "rem" else 1)
            if px and px < 999:  # 9999px is the pill idiom
                yield Hit(m.start(1) + v.start(), v.group(0), message=f"literal border-radius {v.group(0)}",
                          fix=_dimension_fix(ctx, "radius", px, None))


_SPACING_CLASS = re.compile(CLS + r"(-?(?:p[xytrblse]?|m[xytrblse]?|gap(?:-[xy])?|space-[xy]))-(\d+(?:\.\d+)?)(?![\w./-])")


def check_off_scale_spacing(ctx: Ctx) -> Iterator[Hit]:
    s = ctx.scales
    if not ctx.tailwind or s is None or not s.spacing:
        return
    for m in _SPACING_CLASS.finditer(ctx.code):
        if not ctx.class_ok(m.start()):
            continue
        step = m.group(2)
        px = float(step) * s.base
        if px == 0 or px in s.spacing_px:  # the utility's px (step x base), never its name
            continue
        yield Hit(m.start(), m.group(0), fix=_dimension_fix(ctx, "spacing", px, m.group(1)))


_DURATION_CLASS = re.compile(CLS + r"(duration|delay)-(\d+)(?![\w.-])")
_TRANSITION_DECL = re.compile(r"(?<![\w-])(transition(?:-[a-z]+)*|transition[A-Z][A-Za-z]*)\s*:\s*[\"'`]?([^;{}\n\"'`]{1,300})")
_TIME = re.compile(r"(?<![\w.-])(\d*\.?\d+)(ms|s)(?![\w-])")
_DURATION_PROPS = ("transition", "transition-duration", "transition-delay", "transitionDuration", "transitionDelay")
_EASING_PROPS = ("transition", "transition-timing-function", "transitionTimingFunction")


def check_off_token_duration(ctx: Ctx) -> Iterator[Hit]:
    s = ctx.scales
    if s is None or not s.durations:
        return
    if ctx.tailwind:
        for m in _DURATION_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()):
                continue
            ms = float(m.group(2))
            if ms and ms not in s.duration_ms:
                yield Hit(m.start(), m.group(0), fix=_duration_fix(ctx, ms, m.group(1)))
    for m in _TRANSITION_DECL.finditer(ctx.code):
        if m.group(1) not in _DURATION_PROPS:
            continue
        for t in _TIME.finditer(m.group(2)):
            ms = float(t.group(1)) * (1000 if t.group(2) == "s" else 1)
            if ms and ms not in s.duration_ms:
                yield Hit(m.start(2) + t.start(), t.group(0), fix=_duration_fix(ctx, ms, None))


_EASE_CLASS = re.compile(CLS + r"ease-(in-out|in|out|linear)(?![\w-])")
_EASE_KEYWORD = re.compile(r"(?<![\w-])(ease-in-out|ease-in|ease-out|ease|linear|step-start|step-end)(?![\w(-])")


def check_off_token_easing(ctx: Ctx) -> Iterator[Hit]:
    s = ctx.scales
    if s is None or not s.easings:
        return
    if ctx.tailwind:
        for m in _EASE_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()) or ctx.in_transition(m.start()):
                continue  # inside a transition value the CSS check below reports it, with the CSS fix
            if m.group(1) not in s.easing_names:
                curve = _KEYWORD_CURVES.get("linear" if m.group(1) == "linear" else f"ease-{m.group(1)}")
                yield Hit(m.start(), m.group(0), fix=_easing_fix(ctx, curve, True))
    for m in _TRANSITION_DECL.finditer(ctx.code):
        if m.group(1) not in _EASING_PROPS:
            continue
        value, base = m.group(2), m.start(2)
        for c in _CURVE.finditer(value):
            yield Hit(base + c.start(), c.group(0), fix=_easing_fix(ctx, tuple(float(x) for x in c.groups()), False))
        for k in _EASE_KEYWORD.finditer(value):
            yield Hit(base + k.start(), k.group(0), fix=_easing_fix(ctx, _KEYWORD_CURVES.get(k.group(1)), False))


_OUTLINE_CLASS = re.compile(CLS + r"outline-none(?![\w-])")
_OUTLINE_DECL = re.compile(r"(?<![\w-])outline\s*:\s*[\"']?(?:none|0)(?![\w.%-])")


def check_outline_none(ctx: Ctx) -> Iterator[Hit]:
    if ctx.styling == "tailwind-v4":  # in v3 outline-none is a transparent outline, which forced-colors still shows
        for m in _OUTLINE_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()):
                continue
            yield Hit(m.start(), m.group(0), fix="use outline-hidden (keeps an outline in forced-colors mode) with the focus ring token")
    for m in _OUTLINE_DECL.finditer(ctx.code):
        yield Hit(m.start(), m.group(0), fix="use outline: 2px solid transparent (forced-colors still shows it) plus the focus ring token")


_STYLE_PROPS = (
    r"color|background(?:Color|Image|-color|-image)?|font(?:Size|Weight|Family|-size|-weight|-family)?|lineHeight|line-height"
    r"|letterSpacing|letter-spacing|transition|animation|backdropFilter|backdrop-filter|filter|boxShadow|box-shadow"
    r"|border(?:Color|Radius|-color|-radius)?|outline"
)
_JSX_STYLE = re.compile(r"(?<![\w-])style\s*=\s*\{\{")
_ATTR_STYLE = re.compile(r"(?<![\w-])style\s*=\s*([\"'])")
_SVELTE_STYLE = re.compile(r"(?<![\w-])style:(" + _STYLE_PROPS + r")(?![\w-])")
_STYLE_PROP = re.compile(r"(?<=[\s{,;\"'])[\"']?(" + _STYLE_PROPS + r")(?![\w-])[\"']?\s*:\s*([^,;}\n]{0,80})")


def check_inline_style(ctx: Ctx) -> Iterator[Hit]:
    if ctx.stylesheet:
        return
    code = ctx.code
    for m in _JSX_STYLE.finditer(code):
        start = m.end() - 2  # the outer {
        value = _attr_value(code, start, min(len(code), start + 5000))
        end = start + len(value) if value else code.find("}", m.end(), m.end() + 2000)
        yield from _style_props(code, m.end(), end if end >= 0 else min(len(code), m.end() + 2000))
    for m in _ATTR_STYLE.finditer(code):
        end = code.find(m.group(1), m.end(), m.end() + 2000)
        if end >= 0:
            yield from _style_props(code, m.end(), end)
    for m in _SVELTE_STYLE.finditer(code):
        yield Hit(m.start(), m.group(0))


def _style_props(code: str, start: int, end: int) -> Iterator[Hit]:
    for p in _STYLE_PROP.finditer(code, start, end):
        yield Hit(p.start(1), f"{p.group(1)}: {p.group(2).strip()}".strip())


_ICON_LIBS = (r"lucide[\w-]*|@lucide/[\w-]+|@heroicons/[\w-]+|@tabler/icons[\w-]*|react-icons|@fortawesome/[\w-]+"
              r"|@radix-ui/react-icons|@phosphor-icons/[\w-]+|phosphor-react|@mui/icons-material|iconoir[\w-]*"
              r"|feather-icons|react-feather|@ant-design/icons[\w-]*|@iconify/[\w-]+|bootstrap-icons|ionicons"
              r"|@expo/vector-icons|react-native-vector-icons|@material-design-icons/[\w-]+|remixicon[\w-]*")
_ICON_IMPORT = re.compile(r"(?:\bfrom\s+|\bimport\s+|\brequire\s*\(\s*|\bimport\s*\(\s*)[\"'](" + _ICON_LIBS + r")(?:/[^\"']*)?[\"']")


def _icon_family(package: str) -> str:
    if package.startswith(("lucide", "@lucide/")):
        return "lucide"
    if package.startswith("@"):
        scope, _, name = package.partition("/")
        return scope if scope in ("@heroicons", "@fortawesome", "@phosphor-icons", "@iconify", "@material-design-icons") else package
    return re.sub(r"-(?:react|vue|svelte|vue-next|static|preact|solid|angular)$", "", package)


def check_icon_library(ctx: Ctx) -> Iterator[Hit]:
    if ctx.stylesheet:
        return
    wanted = str(ctx.web.get("icons") or ctx.settings.get("Icons") or "lucide").strip().lower()
    wanted = "lucide" if wanted.startswith("lucide") else wanted
    for m in _ICON_IMPORT.finditer(ctx.code):
        if _icon_family(m.group(1)) != wanted:
            yield Hit(m.start(1), m.group(1), fix=f"use {wanted} only, through the icon map (assets/icons/icon-map.json)")


# U+1F000+ are emoji. In U+2600-27BF (and the few in 2Bxx) only characters with emoji presentation count, or any
# character followed by U+FE0F: plain text glyphs such as ✓ ✕ ★ ☰ ⚠ are fine in copy.
_EMOJI_PRESENTATION = ("\u2614\u2615\u2648-\u2653\u267f\u2693\u26a1\u26aa\u26ab\u26bd\u26be\u26c4\u26c5\u26ce\u26d4"
                       "\u26ea\u26f2\u26f3\u26f5\u26fa\u26fd\u2705\u270a\u270b\u2728\u274c\u274e\u2753-\u2755\u2757"
                       "\u2795-\u2797\u27b0\u27bf\u2b1b\u2b1c\u2b50\u2b55")
_EMOJI = re.compile("(?:(?:[\U0001F000-\U0001FAFF" + _EMOJI_PRESENTATION + "]|[\u2190-\u2bff]\ufe0f)[\ufe0f\u200d]*)+")


def check_emoji(ctx: Ctx) -> Iterator[Hit]:
    for m in _EMOJI.finditer(ctx.code):
        yield Hit(m.start(), m.group(0))


_DARK = re.compile(CLS + r"dark:([^\s\"'`{},;)]{1,120})")
_STANDALONE = frozenset("hidden block inline flex grid contents invisible visible underline italic uppercase lowercase "
                        "capitalize truncate static fixed absolute relative sticky".split())


def check_dark_variant(ctx: Ctx) -> Iterator[Hit]:
    if not ctx.tailwind:
        return
    for m in _DARK.finditer(ctx.code):
        if not ctx.class_ok(m.start()):
            continue
        util = m.group(1).split(":")[-1].lstrip("!")
        if "-" in util.lstrip("-") or util in _STANDALONE:
            yield Hit(m.start(), m.group(0))


_ROLES = (r"alertdialog|dialog|menubar|menuitemcheckbox|menuitemradio|menuitem|menu|tooltip|tablist|tabpanel|tab|checkbox"
          r"|switch|radiogroup|radio|combobox|listbox|option|button")
_HANDROLLED = re.compile(r"(?<![\w-])role\s*=\s*\{?\s*[\"'`]?(?:" + _ROLES + r")(?![\w-])[\"'`]?\}?"
                         r"|(?<![\w-])aria-modal(?![\w-])|\bcreatePortal\s*\(")
_CLICK_TAG = re.compile(r"<(div|span)(?![\w-])")
_CLICK_ATTR = re.compile(r"(?<![\w-])(?:onClick|@click|v-on:click|on:click)\s*=")
_ROLE_OR_TAB = re.compile(r"(?<![\w-])(?:role|tabIndex|tabindex)\s*=")
_NATIVE = re.compile(r"<select(?![\w-])|<input\b[^>]{0,300}?\btype\s*=\s*\{?\s*[\"']?(checkbox|radio)(?![\w-])")
_PRIMITIVE_FOR = {"select": "Select", "checkbox": "Checkbox", "radio": "RadioGroup"}


def check_hand_rolled(ctx: Ctx) -> Iterator[Hit]:
    if ctx.stylesheet:
        return
    code = ctx.code
    for m in _HANDROLLED.finditer(code):
        yield Hit(m.start(), m.group(0).rstrip("( "))
    for m in _CLICK_TAG.finditer(code):
        end = _tag_end(code, m.end(), min(len(code), m.end() + 3000))
        if end < 0:
            continue
        if _CLICK_ATTR.search(code, m.end(), end) and not _ROLE_OR_TAB.search(code, m.end(), end):
            yield Hit(m.start(), f"<{m.group(1)}> with a click handler",
                      fix="use a <button> (or the Button primitive): it is focusable and works with Enter and Space")
    if ctx.shadcn:
        for m in _NATIVE.finditer(code):
            kind = m.group(1) or "select"
            text = "<select>" if kind == "select" else f'<input type="{kind}">'
            yield Hit(m.start(), text, fix=f"use the {_PRIMITIVE_FOR[kind]} primitive from components/ui (shadcn)")


PRIMITIVES = ("Button", "Badge", "Card")
_PRIM_OPEN = re.compile(r"<(" + "|".join(PRIMITIVES) + r")(?![\w-])")
_CLASS_ATTR = re.compile(r"(?<![\w-])(?:v-bind:|:)?(?:className|class)\s*=\s*")
_DESIGN_CLASS = re.compile(r"(?<![\w-])((?:[a-z-]+:)*(?:text-[a-z][\w-]*|bg-[\w-]+|border(?:-[\w-]+)?|shadow-[\w-]+"
                           r"|rounded(?:-[\w-]+)?|ring(?:-[\w-]+)?))(?![\w-])")
_TEXT_LAYOUT = re.compile(r"(?:^|:)text-(?:left|center|right|justify|start|end|wrap|nowrap|balance|pretty|ellipsis|clip)$")
_STR_LIT = re.compile(r"\"([^\"]*)\"|'([^']*)'|`([^`]*)`")


def _skip_quote(code: str, i: int, limit: int) -> int:
    j = code.find(code[i], i + 1, limit)
    return j + 1 if j >= 0 else -1


def _tag_end(code: str, i: int, limit: int) -> int:
    """Index of the > closing a tag opened before i (braces balanced, quotes skipped), or -1."""
    depth = 0
    while i < limit:
        c = code[i]
        if c in "\"'`":
            i = _skip_quote(code, i, limit)
            if i < 0:
                return -1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return -1
        elif c == ">" and depth == 0:
            return i
        elif c == "<" and depth == 0:
            return -1
        i += 1
    return -1


def _attr_value(code: str, i: int, limit: int) -> Optional[str]:
    if i >= limit:
        return None
    if code[i] in "\"'":
        j = code.find(code[i], i + 1, limit)
        return code[i:j + 1] if j >= 0 else None
    if code[i] != "{":
        return None
    depth, k = 0, i
    while k < limit:
        c = code[k]
        if c in "\"'`":
            k = _skip_quote(code, k, limit)
            if k < 0:
                return None
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return code[i:k + 1]
        k += 1
    return None


def check_restyled_primitive(ctx: Ctx) -> Iterator[Hit]:
    if ctx.stylesheet:
        return
    code = ctx.code
    for m in _PRIM_OPEN.finditer(code):
        limit = min(len(code), m.end() + 5000)
        end = _tag_end(code, m.end(), limit)
        if end < 0:
            continue
        for a in _CLASS_ATTR.finditer(code, m.end(), end):
            value = _attr_value(code, a.end(), end)
            if not value:
                continue
            strings = " ".join(g for t in _STR_LIT.findall(value) for g in t if g)
            bad = [c for c in _DESIGN_CLASS.findall(strings) if not _TEXT_LAYOUT.search(c)]
            if bad:
                yield Hit(m.start(), f"<{m.group(1)}> {' '.join(bad)}")


# ---------------------------------------------------------------- Swift and Kotlin rules


_SW_COMPONENTS = re.compile(r"(?<![\w.])(?:(?:UI|NS)?Color\s*\(\s*(?:\.\w+\s*,\s*)?|#colorLiteral\s*\(\s*)(red|white|hue)\s*:")
_SW_HEX = re.compile(r"(?<![\w.])(?:UI|NS)?Color\s*\(\s*(hex|rgb|rgba|argb|hexString)\s*:\s*\"?(?:#|0x)?([0-9A-Fa-f]{6,8})\b\"?"
                     r"(?:[^()\n]{0,60}\))?")
_COMPONENT = {k: re.compile(k + r"\s*[:=]\s*(\d*\.?\d+)[fF]?(?:\s*/\s*(\d*\.?\d+))?") for k in ("red", "green", "blue")}


def _components_hex(args: str) -> Optional[str]:
    out = []
    for k in ("red", "green", "blue"):
        m = _COMPONENT[k].search(args)
        if not m:
            return None
        v = float(m.group(1)) / float(m.group(2)) if m.group(2) else float(m.group(1))
        v = v / 255 if v > 1 and not m.group(2) else v
        out.append(max(0, min(255, round(v * 255))))
    return "#" + "".join(f"{c:02x}" for c in out)


def _hex6(digits: str, argb: bool) -> str:
    d = digits.lower()
    return "#" + (d[-6:] if argb and len(d) == 8 else d[:6])


def check_swift_colour(ctx: Ctx) -> Iterator[Hit]:
    if ctx.theme_path:
        return
    code = ctx.code
    for m in _SW_COMPONENTS.finditer(code):
        close = code.find(")", m.end(), m.end() + 200)
        args = code[m.start():close + 1] if close >= 0 else code[m.start():m.end()]
        hexv = _components_hex(args) if m.group(1) == "red" else None
        yield Hit(m.start(), " ".join(args.split()), fix=_mobile_colour_fix(ctx, hexv))
    for m in _SW_HEX.finditer(code):
        yield Hit(m.start(), m.group(0), fix=_mobile_colour_fix(ctx, _hex6(m.group(2), m.group(1) == "argb")))


_SW_FONT = re.compile(r"(?:\.system\s*\(\s*size\s*:\s*(\d*\.?\d+)|\.custom\s*\(\s*\"[^\"\n]*\"\s*,\s*(?:fixedSize|size)\s*:\s*(\d*\.?\d+)"
                      r"|systemFont\s*\(\s*ofSize\s*:\s*(\d*\.?\d+)|UIFont\s*\(\s*name\s*:[^,\n]*,\s*size\s*:\s*(\d*\.?\d+))"
                      r"(?:[^()\n]{0,60}\))?")
_SW_RADIUS = re.compile(r"(?<![\w.])cornerRadius\s*:\s*(\d*\.?\d+)(?![\w.])|\.cornerRadius\s*\(\s*(\d*\.?\d+)\s*(?=[,)])[^()\n]{0,60}\)")


def _mobile_sizes(ctx: Ctx, rx: "re.Pattern[str]", group: str) -> Iterator[Hit]:
    if ctx.theme_path or ctx.scales is None:
        return
    for m in rx.finditer(ctx.code):
        value = next(g for g in m.groups() if g is not None)
        px = float(value)
        if px:
            yield Hit(m.start(), m.group(0).strip(), fix=_dimension_fix(ctx, group, px, "theme"))


def check_swift_font(ctx: Ctx) -> Iterator[Hit]:
    if ctx.scales is not None and ctx.scales.type:
        yield from _mobile_sizes(ctx, _SW_FONT, "typography")


def check_swift_radius(ctx: Ctx) -> Iterator[Hit]:
    if ctx.scales is not None and ctx.scales.radius:
        yield from _mobile_sizes(ctx, _SW_RADIUS, "radius")


_KT_HEX = re.compile(r"(?<![\w.])Color\s*\(\s*0[xX]([0-9A-Fa-f]{6,8})[uUlL]*\s*\)")
_KT_COMPONENTS = re.compile(r"(?<![\w.])Color\s*\(\s*(?:red\s*=\s*)?(\d*\.?\d+)[fF]?\s*,\s*(?:green\s*=\s*)?(\d*\.?\d+)[fF]?\s*,"
                            r"\s*(?:blue\s*=\s*)?(\d*\.?\d+)[fF]?(?:[^()\n]{0,40}\))?")
_KT_PARSE = re.compile(r"\bparseColor\s*\(\s*\"#([0-9A-Fa-f]{6,8})\"\s*\)")


def check_kotlin_colour(ctx: Ctx) -> Iterator[Hit]:
    if ctx.theme_path:
        return
    code = ctx.code
    for m in _KT_HEX.finditer(code):
        yield Hit(m.start(), m.group(0), fix=_mobile_colour_fix(ctx, _hex6(m.group(1), True)))
    for m in _KT_COMPONENTS.finditer(code):
        vals = [float(x) for x in m.groups()]
        scale = 255 if all(v <= 1 for v in vals) else 1  # 0..1 floats, else 0..255 ints
        hexv = "#" + "".join(f"{max(0, min(255, round(v * scale))):02x}" for v in vals)
        yield Hit(m.start(), m.group(0), fix=_mobile_colour_fix(ctx, hexv))
    for m in _KT_PARSE.finditer(code):
        yield Hit(m.start(), m.group(0), fix=_mobile_colour_fix(ctx, _hex6(m.group(1), False)))


_KT_SP = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\.sp(?!\w)")
_KT_FONT_CONTEXT = re.compile(r"fontSize\s*=\s*\Z")
_KT_SHAPE = re.compile(r"(?<![\w.])(?:RoundedCornerShape|CutCornerShape|CornerSize)\s*\(")
_KT_DP = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\.dp(?!\w)")


def check_kotlin_font(ctx: Ctx) -> Iterator[Hit]:
    s = ctx.scales
    if ctx.theme_path or s is None or not s.type:
        return
    for m in _KT_SP.finditer(ctx.code):
        px = float(m.group(1))
        if not px:
            continue
        if _KT_FONT_CONTEXT.search(ctx.code, max(0, m.start() - 40), m.start()):
            fix = _dimension_fix(ctx, "typography", px, "theme")
        else:
            fix = f"use a typography token's text style from the generated theme: {', '.join(list(s.type)[:8])}"
        yield Hit(m.start(), m.group(0), fix=fix)


def check_kotlin_radius(ctx: Ctx) -> Iterator[Hit]:
    s = ctx.scales
    if ctx.theme_path or s is None or not s.radius:
        return
    code = ctx.code
    for m in _KT_SHAPE.finditer(code):
        close = code.find(")", m.end(), m.end() + 300)
        for d in _KT_DP.finditer(code, m.end(), close if close >= 0 else m.end()):
            px = float(d.group(1))
            if px:
                yield Hit(d.start(), d.group(0), fix=_dimension_fix(ctx, "radius", px, "theme"))


# ---------------------------------------------------------------- the rule table

WEB, ALL = ("web",), ("web", "ios", "android")
RULES: List[Rule] = [
    Rule("raw-colour", "error", WEB, "file", check_raw_colour, "raw colour {match}",
         "reference a colour token; if one is genuinely missing, add it with /plumb:update"),
    Rule("arbitrary-value", "error", WEB, "file", check_arbitrary_value, "arbitrary design value {match}",
         "use a token utility (see assets/platforms/web/tokens.css); if one is genuinely missing, add it with /plumb:update"),
    Rule("palette-colour", "error", WEB, "file", check_palette_colour, "Tailwind default palette colour {match}",
         "use a colour token utility (bg-<token>, text-<token>, border-<token>)"),
    Rule("off-scale-type", "error", WEB, "file", check_off_scale_type, "{match} is not on the type scale",
         "use a typography token (text-<name> or var(--text-<name>))"),
    Rule("off-scale-radius", "error", WEB, "file", check_off_scale_radius, "{match} is not on the radius scale",
         "use a radius token (rounded-<name> or var(--radius-<name>)); rounded-full and rounded-none are always fine"),
    Rule("off-scale-spacing", "error", WEB, "file", check_off_scale_spacing, "{match} is not on the spacing scale",
         "use a step of the spacing tokens"),
    Rule("off-token-duration", "error", WEB, "file", check_off_token_duration, "duration {match} is not a motion token",
         "use a motion.duration token; to turn a transition off use transition-none"),
    Rule("off-token-easing", "error", WEB, "file", check_off_token_easing, "easing {match} is not a motion token",
         "use a motion.easing token"),
    Rule("outline-none", "error", WEB, "file", check_outline_none, "{match} removes the focus outline",
         "keep a forced-colors outline (outline-hidden / outline: 2px solid transparent) with the focus ring token",
         skip_allowed=False),
    Rule("inline-style", "error", WEB, "file", check_inline_style, "design property in an inline style: {match}",
         "style with token utilities or classes; inline style is only for layout geometry (top, left, width, height, grid)"),
    Rule("icon-library", "error", WEB, "file", check_icon_library, "second icon library: {match}",
         "use the project's icon library only, through the icon map (assets/icons/icon-map.json)", skip_allowed=False),
    Rule("emoji", "error", ALL, "file", check_emoji, "emoji in UI source: {match}",
         "use an icon from the icon map (assets/icons/icon-map.json) or plain text", skip_allowed=False),
    Rule("dark-variant", "warn", WEB, "file", check_dark_variant, "{match} outside the primitives",
         "tokens switch by themselves under .dark: fix the token (its dark value) or the primitive instead"),
    Rule("hand-rolled-primitive", "warn", WEB, "file", check_hand_rolled, "hand-rolled accessibility primitive: {match}",
         "use the accessible primitive from the components folder (Dialog, Menu, Tabs, Tooltip, Checkbox, Select ...); "
         "a clickable thing is a <button> or a link"),
    Rule("restyled-primitive", "warn", WEB, "file", check_restyled_primitive, "primitive restyled from outside: {match}",
         "add a named variant or size inside the primitive instead, and flag it for sign-off"),
    Rule("swift-raw-colour", "error", ("ios",), "file", check_swift_colour, "raw colour {match}",
         "use a colour from the generated theme (assets/platforms/mobile/ios/)"),
    Rule("swift-font-size", "error", ("ios",), "file", check_swift_font, "literal type size {match}",
         "use a text style from the generated theme"),
    Rule("swift-corner-radius", "error", ("ios",), "file", check_swift_radius, "literal corner radius {match}",
         "use a radius from the generated theme"),
    Rule("kotlin-raw-colour", "error", ("android",), "file", check_kotlin_colour, "raw colour {match}",
         "use a colour from the generated theme (MaterialTheme.colorScheme or the project's colours)"),
    Rule("kotlin-font-size", "error", ("android",), "file", check_kotlin_font, "literal type size {match}",
         "use a text style from the generated theme (MaterialTheme.typography)"),
    Rule("kotlin-corner-radius", "error", ("android",), "file", check_kotlin_radius, "literal corner radius {match}",
         "use a shape from the generated theme (MaterialTheme.shapes)"),
]
_ORDER = {r.id: i for i, r in enumerate(RULES)}


# ---------------------------------------------------------------- the pure API (hooks call these)


def audit_text(path_name: str, text: str, doc: Optional[dict], settings: dict) -> List[Finding]:
    """Every per-file finding for one file's text. Pure: no IO. doc None runs only the rules that need no tokens.

    Unsupported extensions and generated files give []. CRLF and Windows paths give the same result as LF and /.
    """
    if file_ext(path_name) is None or in_build_output(path_name):
        return []
    text = normalise_text(text or "")
    if is_generated(text) and generator_owned(path_name, settings or {}):
        return []
    ctx = Ctx(path_name, text, doc, settings)
    out: List[Finding] = []
    for rule in RULES:
        if rule.kind != "file" or ctx.platform not in rule.platforms or (rule.skip_allowed and ctx.allowed):
            continue
        for hit in rule.check(ctx):
            line = ctx.line_of(hit.pos)
            out.append(Finding(
                rule.id, rule.severity, ctx.path, line, hit.message or rule.message.format(match=hit.match),
                hit.fix or rule.fix, match=hit.match, source=ctx.line_text(line),
            ))
    out.sort(key=lambda f: (f.line, _ORDER[f.rule]))
    return out


def _key(f: Finding) -> Tuple[str, str]:
    return f.rule, " ".join(f.match.lower().split())


def quick(path_name: str, before_text: Optional[str], after_text: str, doc: Optional[dict], settings: dict) -> List[Finding]:
    """Only the findings the edit adds: after minus before, compared by rule + matched text (a multiset), not by line.

    When a value occurs more often after than before, the extra occurrences reported are the ones on lines whose text
    did not exist before (so a moved line is never new). before_text None means a new file: everything is new.
    """
    after = audit_text(path_name, after_text, doc, settings)
    if before_text is None:
        return after
    before = audit_text(path_name, before_text, doc, settings)
    have = Counter(_key(f) for f in before)
    old_lines = Counter(" ".join(line.split()) for line in normalise_text(before_text).split("\n"))
    groups: Dict[Tuple[str, str], List[Finding]] = {}
    for f in after:
        groups.setdefault(_key(f), []).append(f)
    new: List[Finding] = []
    for key, found in groups.items():
        extra = len(found) - have.get(key, 0)
        if extra <= 0:
            continue
        ranked = sorted(found, key=lambda f: (old_lines.get(" ".join(f.source.split()), 0) > 0 if f.source else True))
        new.extend(ranked[:extra])
    new.sort(key=lambda f: (f.line, _ORDER[f.rule]))
    return new


# ---------------------------------------------------------------- project, files


def find_project_root(skill_dir: Path, project: Optional[Path] = None) -> Path:
    """Nearest ancestor of the skill dir holding PLUMB.md, else --project, else skill_dir.parents[2] (as build-tokens)."""
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


def load_doc(skill_dir: Path) -> Optional[dict]:
    """The tokens document, or None when there is no tokens file yet. Several files or broken JSON raise PlumbError."""
    folder = skill_dir / "assets" / "tokens"
    found = sorted(folder.glob("*.tokens.json")) if folder.is_dir() else []
    if not found:
        return None
    if len(found) > 1:
        names = ", ".join(f.name for f in found)
        raise PlumbError(f"error: several tokens files in {folder}: {names}\nfix: keep exactly one *.tokens.json there")
    return P.load_tokens(found[0])


def make_settings(root: Path, doc: Optional[dict]) -> dict:
    """PLUMB.md's Key: value lines merged over the tokens file's $extensions.plumb settings.

    Adds "_shadcn": True when the project has shadcn primitives (components/ui/select or checkbox, at the root or in
    src/), so native <select> and checkbox/radio inputs are reported as hand-rolled."""
    settings = {**P.plumb_settings(doc or {}), **P.read_plumb_md(root / "PLUMB.md")}
    for base in (root, root / "src"):
        for name in ("select", "checkbox"):
            if any((base / "components" / "ui" / f"{name}{ext}").is_file() for ext in (".tsx", ".jsx")):
                settings["_shadcn"] = True
    return settings


def _ui_filter(settings: dict) -> Tuple[List[str], List[str]]:
    value = str(settings.get("UI files", "") or "")
    if not value.strip():
        return [], []
    left, _, right = value.partition("·")
    items = _split_list(left) + _split_list(right)
    dirs = [g for g in items if "/" in g]
    names = [g for g in items if "/" not in g]
    return dirs, names


def collect_files(targets: List[Path], root: Path, skill_dir: Path, settings: dict, explicit: bool) -> List[Path]:
    skill_root = Path(skill_dir).resolve()
    dirs, names = _ui_filter(settings) if not explicit else ([], [])
    docs_dir = (root / str(settings.get("docs_dir") or "docs/design")).resolve()
    out = set()

    def wanted(path: Path) -> bool:
        if file_ext(path.name) is None:
            return False
        resolved = path.resolve()
        try:  # the design-system skill's own files are not the app; only its starter components are audited
            inside = resolved.relative_to(skill_root).parts
            if inside[:2] != ("assets", "platforms") or "starter" not in inside[2:-1]:
                return False
        except ValueError:
            pass
        if explicit:
            return True
        try:
            resolved.relative_to(docs_dir)
            return False
        except ValueError:
            pass
        r = rel(path, root)
        if dirs and not any(_glob_rx(d).match(r) for d in dirs):  # UI files: globs from the project root
            return False
        if names and not any(_glob_rx(n).match(path.name) for n in names):
            return False
        return True

    for target in targets:
        if target.is_file():
            if file_ext(target.name) is not None:
                out.add(target)
            continue
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in filenames:
                path = Path(dirpath) / name
                if wanted(path):
                    out.add(path)
    return sorted(out, key=lambda p: rel(p, root))


def read_source(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig", errors="replace")


# ---------------------------------------------------------------- CLI


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: {USAGE}\n")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _report(findings: List[Finding], checked: int, as_json: bool) -> int:
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = len(findings) - errors
    if as_json:
        out = {"version": P.PLUMB_VERSION, "checked": checked, "errors": errors, "warnings": warnings,
               "findings": [f.to_json() for f in findings]}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    else:
        for f in findings:
            print(f"{f.file}:{f.line}: {f.severity} {f.rule}: {f.message}")
            print(f"  fix: {f.fix}")
        if findings:
            print(f"audit: {_plural(errors, 'error')}, {_plural(warnings, 'warning')} in {_plural(checked, 'file')} checked")
        else:
            print(f"audit: no design-system issues in {_plural(checked, 'file')}")
    return 1 if errors else 0


def _read_stdin() -> str:
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        return sys.stdin.read() if sys.stdin else ""
    return stream.read().decode("utf-8-sig", errors="replace")


def run_quick(args: argparse.Namespace, root: Path, doc: Optional[dict], settings: dict) -> int:
    path = Path(args.quick)
    if not path.is_file():
        print(f"error: {args.quick}: file not found\nfix: pass the path of the file being edited to --quick", file=sys.stderr)
        return 2
    bpath = Path(args.before) if args.before and args.before != "-" else None
    if bpath is not None and not bpath.is_file():
        print(f"error: {args.before}: file not found\nfix: pass --before - and send the old text on stdin", file=sys.stderr)
        return 2
    try:
        before = _read_stdin() if args.before == "-" else read_source(bpath) if bpath is not None else None
        after = read_source(path)
    except OSError as exc:
        print(f"error: cannot read {exc.filename or args.quick} ({exc.strerror or exc})\n"
              f"fix: check the file exists and is readable, then run the check again", file=sys.stderr)
        return 2
    name = rel(path, root)
    checked = 1 if file_ext(name) is not None and not in_build_output(name) else 0
    findings = quick(name, before, after, doc, settings)
    return _report(findings, checked, True)


def run_full(args: argparse.Namespace, root: Path, skill_dir: Path, doc: Optional[dict], settings: dict) -> int:
    explicit = bool(args.paths)
    targets = [Path(p) for p in args.paths] if explicit else [root]
    existing = [t for t in targets if t.exists()]
    for t in targets:
        if not t.exists():
            print(f"note: {t} does not exist, skipped", file=sys.stderr)
    if not existing:
        print(f"error: none of {', '.join(str(t) for t in targets)} exist, nothing was checked\n"
              f"fix: pass the folders that hold your UI code, e.g. python3 {rel(skill_dir / SCRIPT_REL, root)} app components",
              file=sys.stderr)
        return 2
    findings: List[Finding] = []
    checked = 0
    for path in collect_files(existing, root, skill_dir, settings, explicit):
        name = rel(path, root)
        try:
            size = path.stat().st_size
            if size > MAX_BYTES:
                print(f"note: skipped {name} ({size / 1024 / 1024:.1f} MB, over the 5 MB limit)", file=sys.stderr)
                continue
            text = read_source(path)
        except OSError as exc:
            print(f"note: cannot read {name} ({exc}), skipped", file=sys.stderr)
            continue
        if is_generated(normalise_text(text[:1500])) and generator_owned(name, settings):
            continue  # a header counts only on the paths the generators own
        checked += 1
        findings.extend(audit_text(name, text, doc, settings))
    if not checked:
        print(f"error: no UI files in {', '.join(str(t) for t in existing)}, nothing was checked\n"
              f"fix: pass the folders that hold your UI code, e.g. python3 {rel(skill_dir / SCRIPT_REL, root)} app components",
              file=sys.stderr)
        return 2
    return _report(findings, checked, args.json)


def main(argv: Optional[List[str]] = None) -> int:
    P.utf8_stdio()
    parser = _Parser(prog="audit.py", description="Check UI source against the design tokens.")
    parser.add_argument("paths", nargs="*", metavar="PATHS", help="files or folders to check (default: the project)")
    parser.add_argument("--quick", metavar="FILE", help="check one file and report only what the edit adds (JSON)")
    parser.add_argument("--before", metavar="-|PATH", help="with --quick: the file's text before the edit (- reads stdin)")
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    parser.add_argument("--root", metavar="SKILL_DIR", help="the design-system skill folder (default: this script's skill)")
    parser.add_argument("--project", metavar="PATH", help="project root when no PLUMB.md is found above the skill")
    args = parser.parse_args(argv)
    if args.before and not args.quick:
        parser.error("--before works only with --quick FILE")
    if args.quick and args.paths:
        parser.error("--quick checks one file: pass no other paths")
    skill_dir = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        root = find_project_root(skill_dir, Path(args.project) if args.project else None)
        doc = load_doc(skill_dir)
        settings = make_settings(root, doc)
        if doc is None:
            print(f"note: no tokens file in {rel(skill_dir / 'assets' / 'tokens', root)}: only the checks that need no "
                  f"tokens ran", file=sys.stderr)
        if args.quick:
            return run_quick(args, root, doc, settings)
        return run_full(args, root, skill_dir, doc, settings)
    except PlumbError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        print(f"error: unexpected token structure ({type(exc).__name__}: {exc})\n"
              f"fix: open the tokens file and compare it with reference/tokens-format.md", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
