#!/usr/bin/env python3
"""audit.py: check UI source against the project's design tokens.

Usage:
  audit.py [PATHS...] [--json] [--no-tokens] [--root SKILL_DIR] [--project PATH]   full audit (default: the whole project)
  audit.py --quick FILE [--before -|PATH] [--root SKILL_DIR]                        one file, only what an edit adds (JSON)
  audit.py [PATHS...] --html [OUT.html]                                            also write the HTML report

Full mode prints every finding as `file:line: <severity> <rule>: <message>` and `  fix: <fix>`, then a summary
("N errors, N warnings" and, on its own line, "N suggestions"). It runs the per-file rules and then the cross-file
rules. --quick reads the file's text before the edit from stdin (`--before -`) or a file, audits FILE as it is now, and
prints JSON with only the findings the edit adds (compared by rule and matched text, not by line, so moved lines are not
new); --quick never runs the cross-file rules.
--html writes the report page (default <docs_dir>/audit-YYYY-MM-DD.html) from templates/audit-report.html.tmpl, styled
with the project's tokens: the summary, Issues (errors then warnings, grouped by rule, each with file:line, message and
fix, filterable by severity and rule), Improvements (the suggestions ranked by impact = the rule's weight x occurrences,
each with why and fix) and how to re-run. The terminal output and the exit code are the same with or without it.
--json prints {"version", "mode", "checked", "errors", "warnings", "suggestions",
"findings": [{"rule","severity","file","line","message","fix"}]} (+ "scales" in inconsistency-only mode).

Severity: **error** is a hard rule: raw colour, arbitrary design value, Tailwind default palette colour, off-scale type /
radius / spacing, off-token duration or easing, outline-none, design properties in inline styles, a second icon library,
emoji in UI source, the Swift / Kotlin raw values, and (cross-file) contrast failures, missing dark values and stale
generated files. Errors fail the audit (exit 1) and the edit check refuses them.
**warn** is softer and only reported: `dark:` outside the primitives, a hand-rolled accessibility primitive, a primitive
restyled from outside, and the cross-file warnings below.
**suggest** is an improvement, never a failure (it does not change the exit code); each says why and gives a concrete fix.

Cross-file rules (full mode only; one table with the per-file rules, kind "cross"):
  generated-drift (error)   build-tokens.py's outputs() differ from the files on disk (line endings ignored); the fix is
                            `python3 <skill>/scripts/build-tokens.py`.
  contrast (error)          build-tokens.py's contrast pairs (measure_pairs) below 4.5:1 text / 3:1 large and UI, checked
                            in light AND dark, with the nearest passing value.
  missing-dark-value (error) every colour token needs $extensions.plumb.dark, except one marked
                            "$extensions": {"plumb": {"same-in-dark": true}} (a deliberate constant, e.g. a brand fill);
                            an alias takes its target's dark value. `Themes: light-only` in PLUMB.md (a recorded decision)
                            turns the dark rules off: no missing-dark-value, and contrast in light mode only.
  duplicate-component, focus-state (a primitive with no focus style, or primitives showing focus differently: ring
  vs outline vs shadow), hover-only, touch-target (web < 44px without pointer-coarse:, SwiftUI .frame < 44pt on a
  Button or tap gesture, Compose size < 48dp on a clickable or IconButton), reduced-motion (warn).
  near-duplicate-colour, near-duplicate-size, outlier-value (warn): inconsistency-only mode (below).
  Suggestions: missing-token (a raw value used 3+ times with no close token: add one, name proposed), unused-token (one per
  token group, never referenced in the code walked; not run for explicit PATHS or fewer than 5 UI files), duplicate-tokens (two tokens of one kind within ΔE 3 in
  every theme, or within 1px: merge?), consolidate-components (components differing only in padding/radius: a variant),
  contrast-headroom (a pair passing by less than 0.3: a value with 0.5 to spare), consistency (the same component or
  control with different padding or radius across files: pick the majority).

Inconsistency-only mode: when there is no tokens file (a prototype, code before /plumb:extract) or with --no-tokens. The
de-facto scales are inferred from the inventory (_plumb.scan_inventory's scanner, the one /plumb:extract uses) and
printed; near-duplicate groups (CIEDE2000 below 3, sizes within 1px or 6%) and one-off values (used once while a
near-duplicate is used 5+ times) are warnings. Raw values are not errors in this mode (there are no tokens to point to),
so it exits 1 only for the rules that need no tokens (emoji, outline-none, ...). audit_text() and --quick with no
tokens skip the same raw-value rules (RAW_VALUE_RULES). A single HTML prototype works: inline <style> blocks and style
attributes are read.

Every allowed value comes from the project's tokens (assets/tokens/*.tokens.json): durations are the motion.duration
tokens, the type scale is the typography token names, radii the radius tokens, spacing the spacing tokens. Fixes are
token-aware: `bg-[#14857F]` -> `bg-primary (color.primary = #14857f)`; a value with no close token says to add one with
/plumb:update.

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
import datetime
import html
import importlib.util
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
USAGE = (f"python3 {SCRIPT_REL} [PATHS...] [--json] [--html [OUT.html]] [--no-tokens] [--root SKILL_DIR] [--project PATH]"
         " | --quick FILE --before -")
WEB_EXT = frozenset((".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".astro", ".html", ".css", ".scss"))
PLATFORM_OF = {**{e: "web" for e in WEB_EXT}, ".swift": "ios", ".kt": "android"}
SKIP_DIRS = P.SKIP_DIRS
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
    """One row of the rule table. kind "file": per file (hooks + full), check(Ctx) yields Hits; kind "cross": full mode
    only, check(Project) yields XHits. severity: error | warn | suggest. message is a template with {match}; fix is the
    default (non token-aware) fix.
    skip_allowed: the rule does not apply to paths on PLUMB.md's `Allowed raw values:` list.
    weight: how much one occurrence matters; the HTML report ranks Improvements by weight x occurrences.
    why: one sentence on why it matters (shown with each suggestion in the HTML report).
    """

    id: str
    severity: str
    platforms: Tuple[str, ...]
    kind: str
    check: Callable[..., Iterable]
    message: str
    fix: str
    skip_allowed: bool = True
    weight: int = 1
    why: str = ""


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




mask_comments = P.mask_comments
normalise_text = P.normalise_text


def is_generated(text: str) -> bool:
    return P.is_generated_text(text)


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


_glob_rx = P.glob_rx
path_matches = P.path_matches


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
    for m in (_HEX.finditer(code) if "#" in code else ()):  # literal pre-checks: the scan only runs when it can match
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
    for m in (_CFUNC.finditer(code) if "(" in code else ()):
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
    if not ctx.tailwind or ("[" not in ctx.code and "(--" not in ctx.code):
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


_FAMILIES = P.TAILWIND_FAMILIES
PALETTE: Dict[str, str] = P.TAILWIND_PALETTE
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


_TW_TYPE = P.TAILWIND_TYPE
_TYPE_CLASS = re.compile(CLS + r"text-(xs|sm|base|lg|xl|[2-9]xl)(?![\w-])")
_FONT_SIZE = re.compile(r"(?<![\w-])font-size\s*:\s*([^;{}\n]{1,120})")
_CSS_LEN = re.compile(r"(?<![\w.-])(\d*\.?\d+)(px|rem)(?![\w-])")


def check_off_scale_type(ctx: Ctx) -> Iterator[Hit]:
    s = ctx.scales
    if s is None or not s.type:
        return
    if ctx.tailwind and "text-" in ctx.code:
        for m in _TYPE_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()):
                continue
            if m.group(1) not in s.type:
                yield Hit(m.start(), m.group(0), fix=_dimension_fix(ctx, "typography", _TW_TYPE[m.group(1)], "text"))
    for m in (_FONT_SIZE.finditer(ctx.code) if "font-size" in ctx.code else ()):
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
    if ctx.tailwind and "rounded" in ctx.code:
        for m in _RADIUS_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()):
                continue
            if m.group(2) not in s.radius:
                yield Hit(m.start(), m.group(0), fix=_dimension_fix(ctx, "radius", _TW_RADIUS[m.group(2)], m.group(1)))
    for m in (_RADIUS_DECL.finditer(ctx.code) if "radius" in ctx.code else ()):
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
    if ctx.tailwind and ("duration-" in ctx.code or "delay-" in ctx.code):
        for m in _DURATION_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()):
                continue
            ms = float(m.group(2))
            if ms and ms not in s.duration_ms:
                yield Hit(m.start(), m.group(0), fix=_duration_fix(ctx, ms, m.group(1)))
    for m in (_TRANSITION_DECL.finditer(ctx.code) if "transition" in ctx.code else ()):
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
    if ctx.tailwind and "ease-" in ctx.code:
        for m in _EASE_CLASS.finditer(ctx.code):
            if not ctx.class_ok(m.start()) or ctx.in_transition(m.start()):
                continue  # inside a transition value the CSS check below reports it, with the CSS fix
            if m.group(1) not in s.easing_names:
                curve = _KEYWORD_CURVES.get("linear" if m.group(1) == "linear" else f"ease-{m.group(1)}")
                yield Hit(m.start(), m.group(0), fix=_easing_fix(ctx, curve, True))
    for m in (_TRANSITION_DECL.finditer(ctx.code) if "transition" in ctx.code else ()):
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
    if "outline" not in ctx.code:
        return
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
    if ctx.stylesheet or "style" not in ctx.code:
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
    if ctx.code.isascii():  # every emoji is outside ASCII
        return
    for m in _EMOJI.finditer(ctx.code):
        yield Hit(m.start(), m.group(0))


_DARK = re.compile(CLS + r"dark:([^\s\"'`{},;)]{1,120})")
_STANDALONE = frozenset("hidden block inline flex grid contents invisible visible underline italic uppercase lowercase "
                        "capitalize truncate static fixed absolute relative sticky".split())


def check_dark_variant(ctx: Ctx) -> Iterator[Hit]:
    if not ctx.tailwind or "dark:" not in ctx.code:
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
    if "role" in code or "aria-modal" in code or "createPortal" in code:
        for m in _HANDROLLED.finditer(code):
            yield Hit(m.start(), m.group(0).rstrip("( "))
    for m in (_CLICK_TAG.finditer(code) if "<div" in code or "<span" in code else ()):
        end = _tag_end(code, m.end(), min(len(code), m.end() + 3000))
        if end < 0:
            continue
        if _CLICK_ATTR.search(code, m.end(), end) and not _ROLE_OR_TAB.search(code, m.end(), end):
            yield Hit(m.start(), f"<{m.group(1)}> with a click handler",
                      fix="use a <button> (or the Button primitive): it is focusable and works with Enter and Space")
    if ctx.shadcn and ("<select" in code or "<input" in code):
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


# ---------------------------------------------------------------- cross-file rules (full mode only)


@dataclass(frozen=True)
class XHit:
    """One finding of a cross-file rule: where it is, the matched text, and (optionally) a specific message and fix."""

    file: str
    line: int
    match: str
    message: Optional[str] = None
    fix: Optional[str] = None


_BUILD_TOKENS = "build-tokens.py"
RAW_VALUE_RULES = frozenset(("raw-colour", "arbitrary-value", "palette-colour", "inline-style", "swift-raw-colour",
                              "kotlin-raw-colour"))  # not errors when there are no tokens to point to
_FINDING_SIZE_KINDS = ("font-size", "line-height", "spacing", "radius")
_LIGHT_ONLY = re.compile(r"^\s*light[\s-]*only\b", re.I)


def load_build_tokens():
    """build-tokens.py from this script's folder (the same version as this audit), or None when it is not there."""
    path = Path(__file__).resolve().parent / _BUILD_TOKENS
    name = "plumb_build_tokens"
    mod = sys.modules.get(name)
    if mod is not None and Path(getattr(mod, "__file__", "") or "").resolve() == path:
        return mod
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _plumb_error_parts(exc: PlumbError) -> Tuple[str, str]:
    first, _, rest = str(exc).partition("\n")
    fix = rest[len("fix: "):] if rest.startswith("fix: ") else rest or "correct the tokens file"
    return first[len("error: "):] if first.startswith("error: ") else first, fix


class Project:
    """Everything the cross-file rules look at: the audited files (as Ctx), the tokens, the settings, the inventory.

    A later --changed mode passes a subset of files in ctxs; the token-level rules (contrast, drift, dark values)
    do not depend on which files were passed."""

    def __init__(self, root: Path, skill_dir: Path, doc: Optional[dict], settings: dict, ctxs: List["Ctx"],
                 explicit: bool, tokens_file: Optional[Path], generated_texts: Optional[List[str]] = None) -> None:
        self.root, self.skill_dir, self.doc, self.settings = root, skill_dir, doc, settings
        self.ctxs, self.explicit, self.tokens_file = ctxs, explicit, tokens_file
        self.generated_texts = generated_texts or []
        self.inconsistency = doc is None
        self.scales = scales_for(doc)
        self.tokens_name = rel(tokens_file, root) if tokens_file is not None else ""
        self.light_only = _LIGHT_ONLY.match(str(settings.get("Themes", "") or "")) is not None
        self.build_command = f"python3 {rel(skill_dir / 'scripts' / _BUILD_TOKENS, root)}"
        globs = _split_list(settings.get("Allowed raw values"))
        self.primitive_globs = globs or ["components/ui/**"]
        self.markup = [c for c in ctxs if c.platform == "web" and not c.stylesheet]
        self._tokens_text: Optional[str] = None
        self._pairs: Optional[object] = None
        self._inventory: Optional[dict] = None
        self._inv_findings: Optional[List[Tuple[str, XHit]]] = None

    # ---- tokens

    def is_primitive(self, ctx: "Ctx") -> bool:
        return path_matches(ctx.path, self.primitive_globs)

    def token_line(self, path: str) -> int:
        """The line of a token ("color.primary") in the tokens file; 1 when it cannot be found."""
        if self._tokens_text is None:
            try:
                self._tokens_text = normalise_text(read_source(self.tokens_file)) if self.tokens_file else ""
            except OSError:
                self._tokens_text = ""
        text, pos, found = self._tokens_text, 0, None
        for part in path.split("."):
            found = re.compile(r"\"" + re.escape(part) + r"\"\s*:").search(text, pos)
            if found is None:
                return 1
            pos = found.end()
        return text.count("\n", 0, found.start()) + 1 if found else 1

    def pairs(self):
        """build-tokens' measured contrast pairs, a PlumbError (bad contrast settings), or None (no generator)."""
        if self._pairs is None:
            bt = load_build_tokens()
            if bt is None or self.doc is None:
                self._pairs = False
            else:
                try:
                    self._pairs = bt.measure_pairs(self.doc)
                except PlumbError as exc:
                    self._pairs = exc
        return self._pairs or None

    def modes(self) -> Tuple[str, ...]:
        return ("light",) if self.light_only else ("light", "dark")

    def colour_tokens(self) -> List[Tuple[str, dict]]:
        return [(path, tok) for path, tok, ttype in P.iter_tokens(self.doc or {}) if ttype == "color"]

    # ---- the inventory of values used in code

    @property
    def inventory(self) -> dict:
        if self._inventory is None:
            tailwind = (any(c.tailwind for c in self.ctxs) or any(P.uses_tailwind(c.text) for c in self.ctxs)
                        or P.tailwind_project(self.root))
            inv = P.new_inventory()
            for c in self.ctxs:
                P.inventory_add(inv, c.path, c.text, tailwind, code=c.code)
            self._inventory = P.finish_inventory(inv)
        return self._inventory

    def scales_inferred(self) -> Dict[str, List[dict]]:
        return {kind: [{"value": g["canonical"], "count": g["count"], "members": g["members"]}
                       for g in P.cluster(self.inventory, kind)] for kind in P.INVENTORY_KINDS}


def _at(where: str) -> Tuple[str, int]:
    file, _, line = where.rpartition(":")
    return file, int(line) if line.isdigit() else 1


def _times(n: int) -> str:
    return "once" if n == 1 else f"{n} times"


# ---- near-duplicates and outliers in code (inconsistency-only mode: no tokens yet)


def _inventory_findings(proj: Project) -> List[Tuple[str, XHit]]:
    if proj._inv_findings is not None:
        return proj._inv_findings
    out: List[Tuple[str, XHit]] = []
    inv = proj.inventory
    for kind in ("color",) + _FINDING_SIZE_KINDS:
        for group in P.cluster(inv, kind):
            canon = group["canonical"]
            canon_n = inv[kind][canon]["count"]
            for member in group["members"][1:]:
                slot = inv[kind][member]
                file, line = _at(slot["where"][0])
                if kind == "color":
                    gap = f"ΔE {P.delta_e(P.parse_color(member)[0], P.parse_color(canon)[0]):.1f}"
                    what = member
                else:
                    gap = "within 1px or 6%"
                    what = f"{kind} {member}"
                if slot["count"] == 1 and canon_n >= 5:
                    out.append(("outlier-value", XHit(
                        file, line, member,
                        f"{what} is used once while the near-identical {canon} is used {canon_n} times ({gap}): "
                        f"a one-off value is usually a slip",
                        f"use {canon} here; /plumb:extract turns the de-facto scale into tokens")))
                else:
                    rule = "near-duplicate-colour" if kind == "color" else "near-duplicate-size"
                    out.append((rule, XHit(
                        file, line, member,
                        f"{what} ({_times(slot['count'])}) is a near-duplicate of {canon} ({canon_n} times, {gap}): "
                        f"two values nobody can tell apart split the scale",
                        f"use {canon}, the most-used value of this group, where {member} appears "
                        f"({', '.join(slot['where'][:3])}{' ...' if len(slot['where']) > 3 else ''}); "
                        f"/plumb:extract turns the groups into tokens")))
    proj._inv_findings = out
    return out


def check_near_duplicate_colour(proj: Project) -> Iterator[XHit]:
    if proj.inconsistency:
        yield from (h for r, h in _inventory_findings(proj) if r == "near-duplicate-colour")


def check_near_duplicate_size(proj: Project) -> Iterator[XHit]:
    if proj.inconsistency:
        yield from (h for r, h in _inventory_findings(proj) if r == "near-duplicate-size")


def check_outlier_value(proj: Project) -> Iterator[XHit]:
    if proj.inconsistency:
        yield from (h for r, h in _inventory_findings(proj) if r == "outlier-value")


# ---- several components doing one job


_COMP_DEF = re.compile(r"(?:\bfunction\s+([A-Z]\w*)\s*[(<]|\b(?:const|let)\s+([A-Z]\w*)\s*(?::[^=\n]{1,80})?=\s*"
                       r"(?:React\.)?(?:forwardRef|memo)?\s*\(?\s*(?:\([^()]{0,200}\)|[A-Za-z_]\w*)\s*(?::[^=\n]{1,80})?=>)")
_BUTTONISH = re.compile(r"button|btn", re.I)
_BUTTON_TAG = re.compile(r"<button(?![\w.-])")
_TEST_FILE = re.compile(r"\.(?:test|spec|stories|story)$", re.I)


def _classes_in(code: str, start: int, end: int) -> Tuple[List[str], int]:
    """The class names given in a tag's class/className attributes (string literals only) and where the first starts."""
    out, first = [], -1
    for a in _CLASS_ATTR.finditer(code, start, end):
        value = _attr_value(code, a.end(), end)
        if not value:
            continue
        first = a.start() if first < 0 else first
        for t in _STR_LIT.findall(value):
            out.extend(" ".join(g for g in t if g).split())
    return out, first


def _base(cls: str) -> str:
    return cls.rsplit(":", 1)[-1].lstrip("!")


def _stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0]


def check_duplicate_component(proj: Project) -> Iterator[XHit]:
    items: List[Tuple[str, int, str]] = []
    seen_sigs = set()
    for ctx in proj.markup:
        if proj.is_primitive(ctx):
            continue
        stem = _stem(ctx.path)
        defs = list(_COMP_DEF.finditer(ctx.code))
        if _BUTTONISH.search(stem) and not _TEST_FILE.search(stem):
            named = next((d for d in defs if _BUTTONISH.search(d.group(1) or d.group(2))), defs[0] if defs else None)
            items.append((ctx.path, ctx.line_of(named.start()) if named else 1, stem))
            continue
        for d in defs:
            name = d.group(1) or d.group(2)
            if _BUTTONISH.search(name):
                items.append((ctx.path, ctx.line_of(d.start()), name))
        for m in _BUTTON_TAG.finditer(ctx.code):
            end = _tag_end(ctx.code, m.end(), min(len(ctx.code), m.end() + 3000))
            if end < 0:
                continue
            classes, _first = _classes_in(ctx.code, m.end(), end)
            bases = [_base(c) for c in classes]
            has = (any(b.startswith("bg-") for b in bases), any(b.startswith("rounded") for b in bases),
                   any(re.match(r"^p[xytrblse]?-", b) for b in bases), any(b.startswith("text-") for b in bases))
            if not all(has):
                continue
            sig = tuple(sorted(classes))
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            items.append((ctx.path, ctx.line_of(m.start()), f'<button class="{" ".join(classes)}">'))
    if len(items) < 3:
        return
    names = ", ".join(i[2] for i in items[:6]) + (" ..." if len(items) > 6 else "")
    where = proj.primitive_globs[0].replace("**", "").rstrip("/*") or "the primitives folder"
    for file, line, name in items:
        yield XHit(file, line, name,
                   f"{name} is one of {len(items)} button-like components outside the primitives ({names}): several "
                   f"components doing one job drift apart in size, colour and focus",
                   f"use the Button primitive ({where}/button) and add a variant there if none fits; then remove the copy")


# ---- tokens: contrast, dark values, drift


def check_contrast(proj: Project) -> Iterator[XHit]:
    pairs = proj.pairs()
    if pairs is None:
        return
    if isinstance(pairs, PlumbError):
        what, fix = _plumb_error_parts(pairs)
        yield XHit(proj.tokens_name, 1, what, f"contrast cannot be measured: {what}", fix)
        return
    for pair in pairs:
        for mode in proj.modes():
            ratio = pair.light if mode == "light" else pair.dark
            if ratio >= pair.need:
                continue
            near = pair.fix.get(mode)
            if near:
                fix = (f"nearest passing {pair.fg} in {mode} mode: {near[0]} ({near[1]:.2f}:1); change {pair.fg_path} "
                       f"with /plumb:update, then run {proj.build_command}")
            else:
                fix = (f"no {pair.fg} of this hue reaches {num(pair.need)}:1 on {pair.bg} in {mode} mode: change "
                       f"{pair.bg_path} with /plumb:update, then run {proj.build_command}")
            yield XHit(proj.tokens_name, proj.token_line(pair.fg_path), f"{pair.fg} on {pair.bg}",
                       f"{pair.fg} on {pair.bg} is {ratio:.2f}:1 in {mode} mode (needs {num(pair.need)}:1): text "
                       f"this faint is hard to read", fix)


def check_contrast_headroom(proj: Project) -> Iterator[XHit]:
    pairs = proj.pairs()
    bt = load_build_tokens()
    if not pairs or isinstance(pairs, PlumbError) or bt is None:
        return
    for pair in pairs:
        for mode in proj.modes():
            ratio = pair.light if mode == "light" else pair.dark
            if not pair.need <= ratio < pair.need + 0.3:
                continue
            fg, bg = pair.hex[mode]
            better = bt.nearest_passing(fg, bg, pair.need + 0.5, lighten=(mode == "dark"))
            fix = (f"nudge {pair.fg_path} ({mode}) to {better[0]} ({better[1]:.2f}:1, 0.5 to spare) with /plumb:update, "
                   f"then run {proj.build_command}") if better else f"give {pair.bg_path} more contrast in {mode} mode"
            yield XHit(proj.tokens_name, proj.token_line(pair.fg_path), f"{pair.fg} on {pair.bg}",
                       f"{pair.fg} on {pair.bg} passes at {ratio:.2f}:1 in {mode} mode, only {ratio - pair.need:.2f} "
                       f"above the {num(pair.need)}:1 minimum: thin fonts and dim screens push it under", fix)


def _dark_ext(token: dict) -> dict:
    ext = token.get("$extensions")
    ext = ext.get("plumb") if isinstance(ext, dict) else None
    return ext if isinstance(ext, dict) else {}


def check_missing_dark_value(proj: Project) -> Iterator[XHit]:
    if proj.doc is None or proj.light_only:
        return
    for path, tok in proj.colour_tokens():
        raw = tok.get("$value")
        if isinstance(raw, str) and raw.strip().startswith("{"):
            continue  # an alias takes its dark value from the token it points at (checked there)
        ext = _dark_ext(tok)
        if "dark" in ext or ext.get("same-in-dark") is True:
            continue
        try:
            light = P.parse_color(P.resolve(proj.doc, path))[0]
        except PlumbError:
            light = str(raw)
        yield XHit(proj.tokens_name, proj.token_line(path), path,
                   f"{path} has no dark value: in dark mode it stays {light}, a value chosen for light surfaces",
                   f'add "$extensions": {{"plumb": {{"dark": "#..."}}}} to {path} with /plumb:update; if it is '
                   f'deliberately the same in both themes mark it "same-in-dark": true; a light-only product records '
                   f"Themes: light-only in PLUMB.md")


def check_generated_drift(proj: Project) -> Iterator[XHit]:
    if proj.doc is None or proj.tokens_file is None:
        return
    bt = load_build_tokens()
    if bt is None:
        return
    try:
        files = bt.outputs(proj.doc, proj.skill_dir, proj.root, proj.tokens_file)
    except PlumbError as exc:
        what, fix = _plumb_error_parts(exc)
        yield XHit(proj.tokens_name, 1, what, f"the generated files cannot be checked: {what}", fix)
        return
    for path, text in files.items():
        try:
            current = normalise_text(path.read_bytes().decode("utf-8", errors="replace")) if path.is_file() else None
        except OSError:
            current = None
        if current == text:
            continue
        state = "missing" if current is None else "stale: it does not match the tokens (edited by hand, or tokens changed since)"
        yield XHit(rel(path, proj.root), 1, rel(path, proj.root), f"generated file is {state}", proj.build_command)


# ---- focus, hover, touch, motion


_FOCUS = re.compile(r"(?:^|[\s\"'`:{(\[,])(?:[\w-]+:)*(?:group-|peer-)?focus(?:-visible|-within)?:"
                    r"|:focus(?:-visible|-within)?(?![\w-])|data-\[?focus|focus-ring|focusRing|isFocusVisible|useFocusRing")
_INTERACTIVE = re.compile(r"<(?:button|a|input|select|textarea|summary)(?![\w.-])"
                          r"|role\s*=\s*\{?\s*[\"'`](?:button|link|checkbox|switch|tab|menuitem|option|radio)[\"'`]")
_INTERACTIVE_NAMES = frozenset("button input select checkbox switch tabs toggle toggle-group slider radio radio-group "
                               "textarea link combobox dropdown-menu menu menubar".split())


_FOCUS_CLASS = re.compile(r"(?:^|[\s\"'`{(\[,])((?:[\w-]+:)*(?:group-|peer-)?focus(?:-visible|-within)?:(?:[\w-]+:)*!?"
                          r"([a-z][\w-]*))")
_FOCUS_RULE = re.compile(r":focus(?:-visible|-within)?[^{}]*\{([^{}]*)\}")
_TREATMENTS = (("ring", "ring"), ("outline", "outline"), ("shadow", "shadow"), ("border", "border"), ("bg", "background"),
               ("box-shadow", "shadow"), ("background", "background"))


def _focus_treatment(code: str) -> Optional[Tuple[str, int]]:
    """How a file shows focus (ring, outline, shadow, border, background) and where, from its focus classes or its
    :focus rules; None when it has no focus style this can classify."""
    seen: Counter = Counter()
    first: Dict[str, int] = {}
    for m in _FOCUS_CLASS.finditer(code):
        base = m.group(2)
        if base in ("outline-none", "outline-hidden", "outline-0"):
            continue
        kind = next((name for prefix, name in _TREATMENTS if base == prefix or base.startswith(prefix + "-")), None)
        if kind:
            seen[kind] += 1
            first.setdefault(kind, m.start(1))
    for m in _FOCUS_RULE.finditer(code):
        for decl in m.group(1).split(";"):
            prop, _, value = decl.partition(":")
            prop, value = prop.strip().lower(), value.strip().lower()
            if not value or value in ("none", "0") or prop.startswith("outline-offset"):
                continue
            kind = next((name for prefix, name in _TREATMENTS if prop == prefix or prop.startswith(prefix + "-")), None)
            if kind:
                seen[kind] += 1
                first.setdefault(kind, m.start())
    if not seen:
        return None
    kind = max(seen, key=lambda k: (seen[k], -first[k]))
    return kind, first[kind]


def _sibling_css(proj: Project, ctx: "Ctx") -> str:
    """The comment-masked text of the stylesheets next to a component with its name (button.module.css ...)."""
    folder = (proj.root / ctx.path).parent
    stem = _stem(ctx.path).lower()
    try:
        siblings = sorted(p for p in folder.iterdir() if p.suffix in (".css", ".scss") and p.name.lower().startswith(stem + "."))
    except OSError:
        return ""
    out = []
    for p in siblings:
        try:
            out.append(mask_comments(normalise_text(read_source(p)), p.suffix))
        except OSError:
            continue
    return "\n".join(out)


def check_focus_state(proj: Project) -> Iterator[XHit]:
    prims = [c for c in proj.markup if proj.is_primitive(c)]
    if prims:
        styled: List[Tuple["Ctx", str, int]] = []
        for ctx in prims:
            m = _INTERACTIVE.search(ctx.code)
            if m is None and _stem(ctx.path).lower() not in _INTERACTIVE_NAMES:
                continue
            sibling = None
            if not _FOCUS.search(ctx.code):
                sibling = _sibling_css(proj, ctx)
                if not _FOCUS.search(sibling):
                    yield XHit(ctx.path, ctx.line_of(m.start()) if m else 1, _stem(ctx.path),
                               f"the {_stem(ctx.path)} primitive has no focus style: keyboard users cannot see where they "
                               f"are, and every screen built on it inherits the gap",
                               "add a visible focus style with the focus ring token (focus-visible:ring-2 "
                               "focus-visible:ring-<token>, or :focus-visible { outline: 2px solid var(--color-<token>) })")
                    continue
            found = _focus_treatment(ctx.code if sibling is None else sibling)
            if found:
                styled.append((ctx, found[0], ctx.line_of(found[1]) if sibling is None else 1))
        ranked = Counter(kind for _c, kind, _l in styled).most_common()
        if len(ranked) < 2 or ranked[0][1] == ranked[1][1]:
            return  # one treatment everywhere, or no majority to point to
        major, n = ranked[0]
        for ctx, kind, line in styled:
            if kind != major:
                yield XHit(ctx.path, line, f"{_stem(ctx.path)} focus {kind}",
                           f"inconsistent focus states: the {_stem(ctx.path)} primitive shows focus with {kind}, {n} other "
                           f"primitives with {major}: keyboard users should meet one focus style everywhere",
                           f"use the same {major} focus style here as the other primitives (the focus ring token)")
        return
    if any(_FOCUS.search(c.code) for c in proj.ctxs):
        return
    for ctx in proj.markup:
        m = _INTERACTIVE.search(ctx.code)
        if m:
            yield XHit(ctx.path, ctx.line_of(m.start()), m.group(0),
                       "interactive elements but no focus style anywhere: keyboard users cannot see where they are",
                       "add one shared focus style (:focus-visible { outline: 2px solid <focus colour> } or "
                       "focus-visible:ring-2) and use it on every control")
            return


_HOVER_STRING = re.compile(r"\"[^\"\n]*hover:[^\"\n]*\"|'[^'\n]*hover:[^'\n]*'|`[^`]*hover:[^`]*`")
_REVEAL = re.compile(r"^(?:opacity-(?!0$)\d+|visible)$")


def check_hover_only(proj: Project) -> Iterator[XHit]:
    for ctx in proj.markup:
        if "hover:" not in ctx.code:
            continue
        for m in _HOVER_STRING.finditer(ctx.code):
            classes = m.group(0)[1:-1].split()
            hidden = [c for c in classes if ":" not in c and c.lstrip("!") in ("opacity-0", "invisible")]
            reveal = any("hover:" in c and _REVEAL.match(_base(c)) for c in classes)
            focus = any("focus" in c.rsplit(":", 1)[0] and _REVEAL.match(_base(c)) for c in classes if ":" in c)
            if hidden and reveal and not focus:
                pos = m.start() + m.group(0).find(hidden[0])
                yield XHit(ctx.path, ctx.line_of(pos), " ".join(c for c in classes if "hover" in c or c in hidden),
                           f"{hidden[0]} revealed only on hover: keyboard and touch users never see this action",
                           "reveal it on focus too: add group-focus-within:opacity-100 (or focus-visible:opacity-100 / "
                           "group-focus-within:visible), or keep it visible on touch (pointer-coarse:opacity-100)")


_TOUCH_TAG = re.compile(r"<(button|a)(?![\w.-])")
_ROLE_BUTTON = re.compile(r"role\s*=\s*\{?\s*[\"'`]button[\"'`]")
_TAG_NAME = re.compile(r"<([\w.-]+)")
_SIZE_CLASS = re.compile(r"^(min-)?(h|w|size)-(\d+(?:\.\d+)?|px|\[(\d*\.?\d+)(px|rem)\])$")
TOUCH_PX = 44.0  # web px and iOS pt
TOUCH_DP = 48.0  # Android
_SW_FRAME = re.compile(r"\.frame\(([^()]{0,200})\)")
_SW_DIM = re.compile(r"\b(width|height|minWidth|minHeight)\s*:\s*(\d+(?:\.\d+)?)")
_SW_TAP_VIEWS = frozenset(("Button", "Link", "Toggle", "Menu", "NavigationLink", "Stepper"))
_KT_SIZE_MOD = re.compile(r"\.(size|height|width|requiredSize|requiredHeight|requiredWidth|defaultMinSize|sizeIn|heightIn"
                          r"|widthIn)\(([^()]{0,160})\)")
_KT_TAP_MOD = re.compile(r"\.(?:clickable|combinedClickable|toggleable|selectable)\b")
_KT_TAP_CALLS = frozenset(("IconButton", "Button", "TextButton", "OutlinedButton", "FilledIconButton",
                           "FilledTonalButton", "ElevatedButton", "IconToggleButton", "FloatingActionButton"))
_KT_DP_ARG = re.compile(r"(?:\b(\w+)\s*=\s*)?(\d+(?:\.\d+)?)\.dp")
_IDENT_BEFORE = re.compile(r"([A-Za-z_]\w*)\s*\Z")


def _match_back(code: str, i: int) -> int:
    """Index of the bracket opening the one closed at code[i] (")" or "}"), or -1."""
    pairs = {")": "(", "}": "{", "]": "["}
    stack = [code[i]]
    j = i - 1
    while j >= 0 and stack:
        c = code[j]
        if c in pairs:
            stack.append(c)
        elif c in "({[":
            if pairs[stack[-1]] != c:
                return -1
            stack.pop()
        j -= 1
    return j + 1 if not stack else -1


def _swift_view_of(code: str, pos: int) -> str:
    """The view a SwiftUI modifier at pos applies to: walk back over modifiers and closures to the view's name."""
    i = pos
    for _ in range(40):
        j = i - 1
        while j >= 0 and code[j] in " \t\n":
            j -= 1
        if j < 0:
            return ""
        if code[j] in ")}":
            j = _match_back(code, j)
            if j < 0:
                return ""
            i = j
            continue
        m = _IDENT_BEFORE.search(code, 0, j + 1)
        if not m:
            return ""
        start = m.start(1)
        k = start - 1
        while k >= 0 and code[k] in " \t\n":
            k -= 1
        if k >= 0 and code[k] == ".":
            i = k  # another modifier (.padding ...): keep walking back
            continue
        return m.group(1)
    return ""


def _kotlin_call_of(code: str, pos: int) -> str:
    """The function whose argument list contains pos (IconButton for `IconButton(modifier = Modifier...)`)."""
    depth, j = 0, pos - 1
    lo = max(0, pos - 2000)
    while j >= lo:
        c = code[j]
        if c in ")}]":
            depth += 1
        elif c in "({[":
            if depth == 0:
                if c != "(":
                    return ""
                m = _IDENT_BEFORE.search(code, max(0, j - 80), j)
                return m.group(1) if m else ""
            depth -= 1
        j -= 1
    return ""


def _mobile_touch(ctx: "Ctx") -> Iterator[XHit]:
    code = ctx.code
    if ctx.platform == "ios":
        for m in _SW_FRAME.finditer(code):
            dims = {k: float(v) for k, v in _SW_DIM.findall(m.group(1))}
            small = [f"{k}: {num(v)}" for k, v in dims.items() if k in ("width", "height") and v < TOUCH_PX
                     and dims.get("min" + k.capitalize(), 0) < TOUCH_PX]
            small += [f"{k}: {num(v)}" for k, v in dims.items() if k.startswith("min") and v < TOUCH_PX]
            if not small:
                continue
            after = code[m.end():m.end() + 200]
            tap = _swift_view_of(code, m.start()) in _SW_TAP_VIEWS or re.match(r"(?:\s*\.\w+\([^()]*\))*\s*\.onTapGesture\b", after)
            if tap:
                yield XHit(ctx.path, ctx.line_of(m.start()), f".frame({m.group(1).strip()})",
                           f"touch target under {num(TOUCH_PX)}pt: a tappable view framed at {', '.join(small)}: hard to "
                           f"hit with a finger",
                           f"give it at least {num(TOUCH_PX)}x{num(TOUCH_PX)}pt: .frame(minWidth: 44, minHeight: 44) and "
                           f".contentShape(Rectangle()), keeping the icon small inside")
        return
    if ctx.platform == "android":
        done = set()
        for m in _KT_SIZE_MOD.finditer(code):
            start = code.rfind("Modifier", max(0, m.start() - 300), m.start())
            if start < 0 or start in done:
                continue
            end = code.find("\n", m.end())
            chain_end = end if end >= 0 else len(code)
            chain = code[start:chain_end]
            tap = _KT_TAP_MOD.search(chain) is not None or _kotlin_call_of(code, start) in _KT_TAP_CALLS
            if not tap or "minimumInteractiveComponentSize" in chain:
                continue
            small, covered = [], False
            for mod in _KT_SIZE_MOD.finditer(chain):
                minimum = mod.group(1) in ("defaultMinSize", "sizeIn", "heightIn", "widthIn")
                for name, value in _KT_DP_ARG.findall(mod.group(2)):
                    v = float(value)
                    if minimum and (not name or name.startswith("min")):
                        covered = covered or v >= TOUCH_DP
                    elif not minimum and v < TOUCH_DP:
                        small.append(f".{mod.group(1)}({mod.group(2).strip()})")
            done.add(start)
            if small and not covered:
                yield XHit(ctx.path, ctx.line_of(start), small[0],
                           f"touch target under {num(TOUCH_DP)}dp: a clickable element sized {', '.join(dict.fromkeys(small))}: "
                           f"hard to hit with a finger",
                           f"give it at least {num(TOUCH_DP)}dp: Modifier.minimumInteractiveComponentSize() or "
                           f".defaultMinSize(minWidth = 48.dp, minHeight = 48.dp), keeping the icon small inside")


def check_touch_target(proj: Project) -> Iterator[XHit]:
    for ctx in proj.ctxs:
        if ctx.platform in ("ios", "android"):
            yield from _mobile_touch(ctx)
    base = proj.scales.base if proj.scales else 4.0
    for ctx in proj.markup:
        code = ctx.code
        starts = {m.start(): m.group(1) for m in _TOUCH_TAG.finditer(code)}
        for m in _ROLE_BUTTON.finditer(code):
            lt = code.rfind("<", 0, m.start())
            t = _TAG_NAME.match(code, lt) if lt >= 0 else None
            if t:
                starts.setdefault(lt, t.group(1))
        for start in sorted(starts):
            tag = starts[start]
            end = _tag_end(code, start + 1 + len(tag), min(len(code), start + 3000))
            if end < 0:
                continue
            classes, _first = _classes_in(code, start, end)
            if not classes or any("pointer-coarse:" in c for c in classes):
                continue
            small, mins = [], set()
            for c in classes:
                s = _SIZE_CLASS.match(c.lstrip("!"))
                if not s:
                    continue
                step = s.group(3)
                px = P._px_len(s.group(4), s.group(5)) if s.group(4) else 1.0 if step == "px" else float(step) * base
                dims = ("h", "w") if s.group(2) == "size" else (s.group(2),)
                if s.group(1):
                    if px >= TOUCH_PX:
                        mins.update(dims)
                elif px < TOUCH_PX:
                    small.append((dims, c))
            small = [c for dims, c in small if not set(dims) <= mins]
            if small:
                yield XHit(ctx.path, ctx.line_of(start), f"<{tag}> {' '.join(small)}",
                           f"touch target under {num(TOUCH_PX)}px: <{tag}> {' '.join(small)}: hard to hit on a phone",
                           f"make it at least {num(TOUCH_PX)}px on touch: add pointer-coarse:size-11 (or min-h-11 min-w-11), "
                           f"or give it a larger padded hit area")


_ANIM_CLASS = re.compile(r"(?<![^\s\"'`:])(?:transition(?:-(?!none)[a-z]+)?|animate-(?!none)[a-z][\w-]*)(?![\w-])")
_ANIM_DECL = re.compile(r"(?<![\w-])(?:transition|animation)(?:-[a-z]+)?\s*:\s*[\"'`]?(?!none\b)[\w.]"
                        r"|@keyframes\b|(?<![\w-])(?:transition|animation)[A-Z]\w*\s*:")
_ANIM_JS = re.compile(r"(?<![\w-])(?:transition|animation)(?:[A-Z]\w*)?\s*:\s*(?:[\"'`](?!none\b)|\d|\{)")
_CLASS_CALL = re.compile(r"(?<![\w.$])(?:cn|clsx|classnames|classNames|cva|twMerge|twJoin|cx|tw)\s*\(")
_REDUCED = re.compile(r"prefers-reduced-motion|motion-reduce:|motion-safe:|useReducedMotion|reducedMotion")


def _balanced(code: str, i: int) -> int:
    """Index just past the bracket matching the one at code[i] (quotes skipped), or -1."""
    close = {"(": ")", "{": "}", "[": "]"}
    stack, j, limit = [], i, min(len(code), i + 5000)
    while j < limit:
        c = code[j]
        if c in "\"'`":
            j = _skip_quote(code, j, limit)
            if j < 0:
                return -1
            continue
        if c in close:
            stack.append(close[c])
        elif stack and c == stack[-1]:
            stack.pop()
            if not stack:
                return j + 1
        j += 1
    return -1


def class_strings(code: str) -> Iterator[Tuple[int, str]]:
    """(position, text) of every string literal that holds classes: class/className attribute values and the
    arguments of cn() / clsx() / cva() / twMerge() ... (prose strings and JSX text are not classes)."""
    for a in _CLASS_ATTR.finditer(code):
        value = _attr_value(code, a.end(), min(len(code), a.end() + 5000))
        if value:
            for s in _STR_LIT.finditer(value):
                yield a.end() + s.start(), s.group(0)
    for c in _CLASS_CALL.finditer(code):
        end = _balanced(code, c.end() - 1)
        if end > 0:
            for s in _STR_LIT.finditer(code, c.end(), end):
                yield s.start(), s.group(0)


def _style_attr_spans(code: str) -> List[Tuple[int, int]]:
    spans = []
    for m in _ATTR_STYLE.finditer(code):
        end = code.find(m.group(1), m.end(), m.end() + 2000)
        if end >= 0:
            spans.append((m.end(), end))
    return spans


def _first_animation(ctx: "Ctx") -> Optional[int]:
    """Where the file first animates: a transition/animation declaration (stylesheets, <style> blocks, style
    attributes, JS style objects) or a transition/animate-* class (class attributes and cn()/clsx() arguments)."""
    code = ctx.code
    found: List[int] = []
    if ctx.stylesheet:
        m = _ANIM_DECL.search(code)
        return m.start() if m else None
    spans = _style_attr_spans(code)
    for m in _ANIM_DECL.finditer(code):
        if ctx.in_style_block(m.start()) or _in_spans(spans, m.start()):
            found.append(m.start())
            break
    m = _ANIM_JS.search(code)
    if m:
        found.append(m.start())
    for pos, text in class_strings(code):
        a = _ANIM_CLASS.search(text)
        if a:
            found.append(pos + a.start())
    return min(found) if found else None


def _reduced_motion_anywhere(proj: Project) -> bool:
    if any(_REDUCED.search(c.code) for c in proj.ctxs) or any(_REDUCED.search(t) for t in proj.generated_texts):
        return True
    seen = {c.path for c in proj.ctxs}
    for dirpath, dirnames, filenames in os.walk(proj.root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in filenames:
            ext = file_ext(name)
            if ext not in (".css", ".scss", ".html"):
                continue
            path = Path(dirpath) / name
            if rel(path, proj.root) in seen:
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
                if _REDUCED.search(mask_comments(normalise_text(read_source(path)), ext)):
                    return True
            except OSError:
                continue
    return False


def check_reduced_motion(proj: Project) -> Iterator[XHit]:
    for ctx in proj.ctxs:
        if ctx.platform != "web":
            continue
        pos = _first_animation(ctx)
        if pos is None:
            continue
        if not _reduced_motion_anywhere(proj):
            yield XHit(ctx.path, ctx.line_of(pos), "animation",
                       "animations or transitions but no prefers-reduced-motion handling anywhere: motion can make "
                       "people with vestibular disorders sick",
                       "add @media (prefers-reduced-motion: reduce) { *, ::before, ::after { animation-duration: 0s "
                       "!important; transition-duration: 0s !important; } } to the global stylesheet (Plumb's tokens.css "
                       "has it), or use motion-safe: / motion-reduce: variants")
        return


# ---- suggestions: improvements, never failures


def _colour_name(hexv: str) -> str:
    import colorsys
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.12 or light > 0.97 or light < 0.03:
        family = "gray"
    else:
        deg = h * 360
        bounds = ((15, "red"), (40, "orange"), (55, "amber"), (70, "yellow"), (90, "lime"), (150, "green"),
                  (175, "teal"), (195, "cyan"), (215, "sky"), (240, "blue"), (260, "indigo"), (280, "violet"),
                  (300, "purple"), (330, "pink"), (345, "rose"), (361, "red"))
        family = next(name for limit, name in bounds if deg < limit)
    step = min(950, max(50, int(round((1 - light) * 10)) * 100))
    return f"{family}-{step}"


def _token_values(proj: Project) -> Dict[str, List[float]]:
    s = proj.scales
    out: Dict[str, List[float]] = {"font-size": list(s.type.values()), "spacing": list(s.spacing.values()),
                                   "radius": list(s.radius.values()), "duration": [d[2] for d in s.durations]}
    return out


def check_missing_token(proj: Project) -> Iterator[XHit]:
    s = proj.scales
    if s is None:
        return
    inv = proj.inventory
    colours = set()
    for path, _tok in proj.colour_tokens():
        for mode in ("light", "dark"):
            try:
                colours.add(P.parse_color(P.resolve(proj.doc, path, mode))[0])
            except PlumbError:
                pass
    labs = [P._lab(c) for c in colours]
    sizes = _token_values(proj)
    taken = {path for path, _t, _ty in P.iter_tokens(proj.doc)}
    for kind in ("color", "font-size", "spacing", "radius", "shadow", "duration"):
        for value, slot in sorted(inv[kind].items(), key=lambda kv: (-kv[1]["count"], kv[0])):
            n = slot["count"]
            if n < 3:
                continue
            if kind == "color":
                hexv = value[:7]
                lab = P._lab(hexv)
                if any(P.delta_e_lab(lab, t) < P.COLOUR_DELTA for t in labs):
                    continue  # a token is close: the per-file fix already names it
                name = f"color.{_colour_name(hexv)}"
            elif kind == "shadow":
                if s.shadows and (not value.startswith("shadow-") or value[len("shadow-"):] in s.shadows):
                    continue
                name = f"shadow.{value[len('shadow-'):] if value.startswith('shadow-') else 'raised'}"
            else:
                size = P._size_of(value)
                if size is None or any(P.sizes_close(size[0], t, size[1]) for t in sizes[kind]):
                    continue
                n_txt = num(size[0])
                name = {"font-size": f"typography.size-{n_txt}", "spacing": f"spacing.{num(size[0] / s.base)}",
                        "radius": f"radius.r{n_txt}", "duration": f"motion.duration.d{n_txt}"}[kind]
            base_name, i = name, 2
            while name in taken:
                name, i = f"{base_name}-{i}", i + 1
            taken.add(name)
            file, line = _at(slot["where"][0])
            places = ", ".join(slot["where"][:3]) + (" ..." if len(slot["where"]) > 3 else "")
            yield XHit(file, line, value,
                       f"{value} ({kind}) is used {n} times with no token: a value used this often belongs in the scale, "
                       f"where it can change in one place",
                       f"add {name} = {value} with /plumb:update, then use it at {places}")


_UTIL = re.compile(
    r"^-?(bg|text|border(?:-[trblxyse]{1,2})?|ring(?:-offset)?|outline|fill|stroke|from|via|to|decoration|divide(?:-[xy])?"
    r"|accent|caret|placeholder|shadow|inset-shadow|drop-shadow|rounded(?:-[trblse]{1,2})?|font|leading|tracking|ease"
    r"|duration|delay|animate|p[xytrblse]?|m[xytrblse]?|gap(?:-[xy])?|space-[xy]|[wh]|size|min-[wh]|max-[wh]|inset(?:-[xy])?"
    r"|top|left|right|bottom|translate-[xy]|scroll-[mp][xytrblse]?)-(.+)$")
_WORD = re.compile(r"-{0,2}[A-Za-z][\w-]*")
_FAMILY_OF_PREFIX = (("rounded", "radius"), ("shadow", "shadow"), ("inset-shadow", "shadow"), ("drop-shadow", "shadow"),
                     ("duration", "duration"), ("delay", "duration"), ("ease", "easing"), ("font", "font"))
_COLOUR_PREFIXES = re.compile(r"^(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|divide|accent|caret|placeholder|shadow)")
_SPACING_PREFIXES = re.compile(r"^(?:p[xytrblse]?|m[xytrblse]?|gap|space|[wh]|size|min|max|inset|top|left|right|bottom|translate|scroll)")


UNUSED_MIN_FILES = 5
_GROUP_LABEL = {"color": "colour", "typography": "type", "radius": "radius", "spacing": "spacing", "shadow": "shadow",
                "motion": "motion", "font": "font"}


def check_unused_token(proj: Project) -> Iterator[XHit]:
    if proj.doc is None or proj.explicit or len(proj.ctxs) < UNUSED_MIN_FILES:
        return  # partial scans and early projects use few tokens yet: not worth a suggestion
    words, mobile = set(), set()
    for c in proj.ctxs:
        found = set(_WORD.findall(c.code))
        (mobile if c.platform != "web" else words).update(found)
    used: Dict[str, set] = {k: set() for k in ("colour", "text", "radius", "shadow", "duration", "easing", "font", "spacing")}
    for w in words:
        m = _UTIL.match(w)
        if not m:
            continue
        prefix, rest = m.group(1), m.group(2)
        if _COLOUR_PREFIXES.match(prefix):
            used["colour"].add(rest)
        if prefix == "text":
            used["text"].add(rest)
        for p, fam in _FAMILY_OF_PREFIX:
            if prefix == p or prefix.startswith(p + "-") and p == "rounded":
                used[fam].add(rest)
        if _SPACING_PREFIXES.match(prefix):
            used["spacing"].add(rest)
    s = proj.scales
    referenced = set()
    aliases: Dict[str, str] = {}
    candidates = []
    for path, tok, ttype in P.iter_tokens(proj.doc):
        raw = tok.get("$value")
        if isinstance(raw, str) and raw.strip().startswith("{") and raw.strip().endswith("}"):
            aliases[path] = raw.strip()[1:-1]
        group = path.split(".")[0]
        var = varname(path)
        if group not in ("color", "typography", "radius", "spacing", "shadow", "motion", "font"):
            continue
        candidates.append(path)
        camel = re.sub(r"[-_.]+([a-zA-Z0-9])", lambda x: x.group(1).upper(), "-".join(path.split(".")[1:]))
        hit = var in words or (camel and camel in mobile)
        if not hit:
            if ttype == "color":
                hit = var[len("--color-"):] in used["colour"]
            elif group == "typography":
                hit = var[len("--text-"):] in used["text"]
            elif group == "radius":
                hit = var[len("--radius-"):] in used["radius"]
            elif group == "shadow":
                hit = var[len("--shadow-"):] in used["shadow"]
            elif group == "font":
                hit = var[len("--font-"):] in used["font"]
            elif group == "spacing":
                px = s.px_of.get(path) if s else None
                hit = "-".join(path.split(".")[1:]) in used["spacing"] or (
                    px is not None and s.base and num(px / s.base) in used["spacing"])
            elif group == "motion" and var.startswith("--duration-"):
                ms = next((d[2] for d in s.durations if d[0] == path), None) if s else None
                hit = var[len("--duration-"):] in used["duration"] or (ms is not None and num(ms) in used["duration"])
            elif group == "motion" and var.startswith("--ease-"):
                hit = var[len("--ease-"):] in used["easing"]
            else:
                hit = True  # other motion tokens: no utility to look for
        if hit:
            referenced.add(path)
    changed = True
    while changed:
        changed = False
        for src, target in aliases.items():
            if src in referenced and target not in referenced:
                referenced.add(target)
                changed = True
    unused: Dict[str, List[str]] = {}
    for path in candidates:
        if path not in referenced:
            unused.setdefault(path.split(".")[0], []).append(path)
    for group, paths in unused.items():
        n = len(paths)
        label = _GROUP_LABEL.get(group, group)
        listed = ", ".join(paths[:12]) + (" ..." if n > 12 else "")
        yield XHit(proj.tokens_name, proj.token_line(paths[0]), f"{n} {label}",
                   f"{n} {label} token{'s are' if n > 1 else ' is'} never used in the {_plural(len(proj.ctxs), 'file')} "
                   f"checked: {listed}; unused tokens are noise in the scale and invite near-duplicates",
                   f"remove {'them' if n > 1 else 'it'} with /plumb:update, or use {'them' if n > 1 else 'it'} where "
                   f"{'they belong' if n > 1 else 'it belongs'} (e.g. var({varname(paths[0])}))")


def check_duplicate_tokens(proj: Project) -> Iterator[XHit]:
    if proj.doc is None:
        return
    doc = proj.doc
    colours = []
    for path, tok in proj.colour_tokens():
        raw = tok.get("$value")
        if isinstance(raw, str) and raw.strip().startswith("{"):
            continue
        try:
            light = P.parse_color(P.resolve(doc, path))
            dark = P.parse_color(P.resolve(doc, path, "dark"))
        except PlumbError:
            continue
        colours.append((path, light, dark, P.is_text_name("-".join(path.split(".")[1:]))))
    for i, (path, light, dark, texty) in enumerate(colours):
        for other, olight, odark, otexty in colours[:i]:
            if texty != otexty or abs(light[1] - olight[1]) > 0.02:
                continue
            dl = P.delta_e(light[0], olight[0])
            dd = P.delta_e(dark[0], odark[0])
            if dl < P.COLOUR_DELTA and (proj.light_only or dd < P.COLOUR_DELTA):
                both = f"ΔE {dl:.1f} in light" + ("" if proj.light_only else f", {dd:.1f} in dark")
                yield XHit(proj.tokens_name, proj.token_line(path), path,
                           f"{path} ({light[0]}) looks the same as {other} ({olight[0]}): {both}; two tokens nobody can "
                           f"tell apart get used interchangeably",
                           f"merge? keep {other} and point {path} at {{{other}}} (or remove it) with /plumb:update")
                break
    s = proj.scales
    if s is None:
        return
    groups: Dict[str, List[Tuple[str, float]]] = {}
    for path, px in s.px_of.items():
        if px and not (path in s.aliases):
            groups.setdefault(path.split(".")[0], []).append((path, px))
    def style(path: str) -> object:
        """A type token's other fields: the same size with another line height or weight is a different style (label
        vs body); sizes 1px apart are near-duplicate steps whatever the other fields say."""
        try:
            value = P.resolve(doc, path)
        except PlumbError:
            return None
        return sorted((k, str(v)) for k, v in value.items() if k != "fontSize") if isinstance(value, dict) else None

    for group, items in groups.items():
        for i, (path, px) in enumerate(items):
            for other, opx in items[:i]:
                if group == "typography" and px == opx and style(path) != style(other):
                    continue
                if abs(px - opx) <= P.SIZE_PX:
                    yield XHit(proj.tokens_name, proj.token_line(path), path,
                               f"{path} ({num(px)}px) is within 1px of {other} ({num(opx)}px): steps this close are not "
                               f"a scale, they are a choice left open",
                               f"merge? keep {other} and point {path} at {{{other}}} (or remove it) with /plumb:update")
                    break


_PAD_RADIUS = re.compile(r"^(?:[\w-]+:)*(?:-?p[xytrblse]?-|rounded(?:-|$))")


def check_consolidate_components(proj: Project) -> Iterator[XHit]:
    groups: Dict[tuple, List[Tuple[str, str, int, frozenset]]] = {}
    for ctx in proj.markup:
        if proj.is_primitive(ctx):
            continue
        code = ctx.code
        defs = list(_COMP_DEF.finditer(code))
        for k, d in enumerate(defs):
            limit = min(defs[k + 1].start() if k + 1 < len(defs) else len(code), d.end() + 1500)
            a = _CLASS_ATTR.search(code, d.end(), limit)
            if a is None:
                continue
            lt = code.rfind("<", d.end(), a.start())
            t = _TAG_NAME.match(code, lt) if lt >= 0 else None
            value = _attr_value(code, a.end(), limit)
            if t is None or not value or "${" in value:
                continue
            classes = " ".join(g for tup in _STR_LIT.findall(value) for g in tup if g).split()
            pr = frozenset(c for c in classes if _PAD_RADIUS.match(c))
            rest = frozenset(c for c in classes if c not in pr)
            if len(rest) < 2 or not pr:
                continue
            groups.setdefault((t.group(1), rest), []).append((d.group(1) or d.group(2), ctx.path, ctx.line_of(a.start()), pr))
    for (_tag, _rest), comps in groups.items():
        if len(comps) < 2 or len({c[3] for c in comps}) < 2:
            continue
        names = [c[0] for c in comps]
        for name, file, line, pr in comps:
            others = ", ".join(n for n in names if n != name)
            yield XHit(file, line, name,
                       f"{name} differs from {others} only in padding/radius ({' '.join(sorted(pr))}): several components "
                       f"doing one job with small differences drift further apart",
                       f"make one component with a size or shape variant (e.g. size=\"sm\" | \"lg\") and use it for "
                       f"{', '.join(names)}")


_USE_TAG = re.compile(r"<([A-Z][\w.]*|button|input|select|textarea)(?![\w.-])")
_PAD_CLASS = re.compile(r"^-?p[xytrblse]?-")
_RADIUS_CLASS_ANY = re.compile(r"^rounded(?:-|$)")


def check_consistency(proj: Project) -> Iterator[XHit]:
    seen: Dict[Tuple[str, str], Dict[str, List[Tuple[str, int]]]] = {}
    for ctx in proj.markup:
        if proj.is_primitive(ctx):
            continue
        code = ctx.code
        for m in _USE_TAG.finditer(code):
            end = _tag_end(code, m.end(), min(len(code), m.end() + 3000))
            if end < 0:
                continue
            classes, first = _classes_in(code, m.end(), end)
            plain = [c for c in classes if ":" not in c]
            for aspect, rx in (("padding", _PAD_CLASS), ("radius", _RADIUS_CLASS_ANY)):
                vals = sorted(c for c in plain if rx.match(c))
                if vals:
                    seen.setdefault((m.group(1), aspect), {}).setdefault(" ".join(vals), []).append(
                        (ctx.path, ctx.line_of(m.start())))
    for (tag, aspect), values in seen.items():
        if len(values) < 2 or len({f for uses in values.values() for f, _l in uses}) < 2:
            continue
        ranked = sorted(values.items(), key=lambda kv: -len(kv[1]))
        if len(ranked[0][1]) == len(ranked[1][1]):
            continue  # no majority to pick
        major, uses = ranked[0]
        for value, places in ranked[1:]:
            for file, line in places:
                yield XHit(file, line, f"<{tag}> {value}",
                           f"<{tag}> uses {value} here but {major} in {len(uses)} other places: the same element should "
                           f"have the same {aspect} everywhere",
                           f"pick one: use {major} (the majority) here, or if this one is deliberately different make it a "
                           f"named variant of {tag}")


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
    # cross file (full mode only)
    Rule("generated-drift", "error", ALL, "cross", check_generated_drift, "generated file is stale",
         "run build-tokens.py"),
    Rule("contrast", "error", ALL, "cross", check_contrast, "contrast failure: {match}",
         "change the token, then run build-tokens.py"),
    Rule("missing-dark-value", "error", ALL, "cross", check_missing_dark_value, "{match} has no dark value",
         'add $extensions.plumb.dark, or mark it "same-in-dark": true'),
    Rule("near-duplicate-colour", "warn", ALL, "cross", check_near_duplicate_colour, "near-duplicate colour {match}",
         "use the most-used value of the group"),
    Rule("near-duplicate-size", "warn", ALL, "cross", check_near_duplicate_size, "near-duplicate size {match}",
         "use the most-used value of the group"),
    Rule("outlier-value", "warn", ALL, "cross", check_outlier_value, "one-off value {match}",
         "use the common value"),
    Rule("duplicate-component", "warn", WEB, "cross", check_duplicate_component, "duplicate component {match}",
         "use the Button primitive with a variant"),
    Rule("focus-state", "warn", WEB, "cross", check_focus_state, "no focus style: {match}",
         "add a visible focus style with the focus ring token"),
    Rule("hover-only", "warn", WEB, "cross", check_hover_only, "hover-only action: {match}",
         "reveal it on focus too (group-focus-within:)"),
    Rule("touch-target", "warn", ALL, "cross", check_touch_target, "touch target too small: {match}",
         "make it at least 44px / 44pt / 48dp on touch"),
    Rule("reduced-motion", "warn", WEB, "cross", check_reduced_motion, "no reduced-motion handling",
         "add a prefers-reduced-motion block"),
    Rule("missing-token", "suggest", ALL, "cross", check_missing_token, "{match} has no token",
         "add a token with /plumb:update", weight=3,
         why="A raw value repeated across files drifts the moment one copy changes; a token keeps every use in step "
             "and lets dark mode and a rebrand reach it."),
    Rule("unused-token", "suggest", ALL, "cross", check_unused_token, "{match} is unused",
         "remove it with /plumb:update, or use it", weight=1,
         why="A token nothing uses still has to be named, documented and kept in contrast; removing it (or using it) "
             "keeps the scale honest."),
    Rule("duplicate-tokens", "suggest", ALL, "cross", check_duplicate_tokens, "{match} duplicates another token",
         "merge the two tokens with /plumb:update", weight=2,
         why="Two tokens nobody can tell apart get used interchangeably, so changing one leaves half the product "
             "behind."),
    Rule("consolidate-components", "suggest", WEB, "cross", check_consolidate_components,
         "{match} differs from another component only in padding/radius", "make one component with a variant", weight=2,
         why="Components that differ only in padding or radius drift apart over time; one component with a variant is "
             "one place to fix and to test."),
    Rule("contrast-headroom", "suggest", ALL, "cross", check_contrast_headroom, "{match} barely passes",
         "nudge the token for 0.5 to spare", weight=3,
         why="A pair that only just passes fails after the smallest tweak, on a dim screen or in the other theme; a "
             "little headroom keeps the text readable."),
    Rule("consistency", "suggest", WEB, "cross", check_consistency, "{match} differs from the majority",
         "pick one value", weight=2,
         why="The same control with a different padding or radius on different screens makes the product feel "
             "unfinished, and it can no longer be changed in one place."),
]
_ORDER = {r.id: i for i, r in enumerate(RULES)}


# ---------------------------------------------------------------- the pure API (hooks call these)


def audit_text(path_name: str, text: str, doc: Optional[dict], settings: dict) -> List[Finding]:
    """Every per-file finding for one file's text. Pure: no IO. doc None (no tokens yet) runs only the rules that need
    no tokens and skips RAW_VALUE_RULES (a raw value is not an error when there is no token to point to), exactly like
    the full audit's inconsistency-only mode; quick() inherits this.

    Unsupported extensions and generated files give []. CRLF and Windows paths give the same result as LF and /.
    """
    ctx = make_ctx(path_name, text, doc, settings)
    return file_findings(ctx, RAW_VALUE_RULES if doc is None else frozenset()) if ctx is not None else []


def make_ctx(path_name: str, text: str, doc: Optional[dict], settings: dict) -> Optional[Ctx]:
    """The Ctx for one file, or None when the file is not audited (other extension, build output, generated)."""
    if file_ext(path_name) is None or in_build_output(path_name):
        return None
    text = normalise_text(text or "")
    if is_generated(text) and generator_owned(path_name, settings or {}):
        return None
    return Ctx(path_name, text, doc, settings)


def file_findings(ctx: Ctx, skip: frozenset = frozenset()) -> List[Finding]:
    out: List[Finding] = []
    for rule in RULES:
        if rule.kind != "file" or rule.id in skip or ctx.platform not in rule.platforms or (rule.skip_allowed and ctx.allowed):
            continue
        for hit in rule.check(ctx):
            line = ctx.line_of(hit.pos)
            out.append(Finding(
                rule.id, rule.severity, ctx.path, line, hit.message or rule.message.format(match=hit.match),
                hit.fix or rule.fix, match=hit.match, source=ctx.line_text(line),
            ))
    out.sort(key=lambda f: (f.line, _ORDER[f.rule]))
    return out


_SEVERITY_RANK = {"error": 0, "warn": 1, "suggest": 2}


def cross_findings(proj: Project) -> List[Finding]:
    """Every cross-file finding (full mode only): errors, then warnings, then suggestions."""
    out: List[Finding] = []
    for rule in RULES:
        if rule.kind != "cross":
            continue
        for hit in rule.check(proj):
            out.append(Finding(rule.id, rule.severity, hit.file, hit.line, hit.message or rule.message.format(match=hit.match),
                               hit.fix or rule.fix, match=hit.match))
    out.sort(key=lambda f: (_SEVERITY_RANK[f.severity], _ORDER[f.rule], f.file, f.line))
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
    """path relative to root (posix); the path as given when it is outside. Tries the plain absolute path first
    (no filesystem calls: walked files are already under the resolved root), then resolves symlinks."""
    try:
        return Path(os.path.abspath(path)).relative_to(os.path.abspath(root)).as_posix()
    except ValueError:
        pass
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def find_tokens(skill_dir: Path) -> Optional[Path]:
    """The one *.tokens.json in <skill>/assets/tokens, or None. Several files raise PlumbError."""
    folder = skill_dir / "assets" / "tokens"
    found = sorted(folder.glob("*.tokens.json")) if folder.is_dir() else []
    if not found:
        return None
    if len(found) > 1:
        names = ", ".join(f.name for f in found)
        raise PlumbError(f"error: several tokens files in {folder}: {names}\nfix: keep exactly one *.tokens.json there")
    return found[0]


def load_doc(skill_dir: Path) -> Optional[dict]:
    """The tokens document, or None when there is no tokens file yet. Several files or broken JSON raise PlumbError."""
    path = find_tokens(skill_dir)
    return P.load_tokens(path) if path is not None else None


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
        resolved = Path(os.path.abspath(path))
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


# ---------------------------------------------------------------- the HTML report (--html)


REPORT_TEMPLATE = "audit-report.html.tmpl"
_SEV_WORD = {"error": ("Error", "Errors"), "warn": ("Warning", "Warnings"), "suggest": ("Suggestion", "Suggestions")}


def _t(text: object) -> str:
    """Text content, escaped (quotes kept as they are, so messages read and search the same as in the terminal)."""
    return html.escape(str(text), quote=False)


def _a(text: object) -> str:
    return html.escape(str(text), quote=True)


def _sev(severity: str, plural: bool = False) -> str:
    word = _SEV_WORD[severity][1 if plural else 0]
    return f'<span class="sev sev-{severity}"><span class="sev-shape" aria-hidden="true"></span> {word}</span>'


SEGMENT_NOWRAP = 32  # path parts up to this long never break inside; longer ones may (rare: a very long file name)


def _loc(path: str, line: int) -> str:
    """file:line that wraps only after a /: each part is unbreakable (hyphens included), with a break chance after
    every separator."""
    parts = f"{path}:{line}".replace("\\", "/").split("/")
    shown = [f'<span class="seg">{_t(s)}</span>' if len(s) <= SEGMENT_NOWRAP else _t(s) for s in parts]
    return f'<code class="loc">{"/<wbr>".join(shown)}</code>'


def _finding_item(f: Finding, with_fix: bool = True) -> str:
    fix = f'<p class="fix"><span class="fix-label">Fix</span>{_t(f.fix)}</p>' if with_fix else ""
    return (f'<li class="finding{"" if with_fix else " compact"}" data-severity="{_a(f.severity)}" data-rule="{_a(f.rule)}">'
            f'<div class="f-where">{_sev(f.severity)}{_loc(f.file, f.line)}</div>'
            f'<div class="f-what"><p class="msg">{_t(f.message)}</p>{fix}</div></li>')


def _findings_list(items: List[Finding], indent: str = "") -> List[str]:
    """The rows of one rule group. A fix shared by several rows is shown once above them (the rows stay compact);
    a fix of its own stays on its row."""
    by_fix: Dict[str, List[Finding]] = {}
    for f in items:
        by_fix.setdefault(f.fix, []).append(f)
    out, single = [], []
    for fix, group in by_fix.items():
        if len(group) < 2:
            single += group
            continue
        out.append(f'{indent}<div class="fix-group" data-group><p class="fix shared-fix"><span class="fix-label">Fix</span>'
                   f'{_t(fix)} <span class="count">(for the {len(group)} below)</span></p>')
        out.append(f'{indent}  <ul class="findings" role="list">' + "".join(_finding_item(f, False) for f in group) + "</ul></div>")
    if single:
        out.append(f'{indent}<ul class="findings" role="list">' + "".join(_finding_item(f) for f in single) + "</ul>")
    return out


def _rules_by_id() -> Dict[str, Rule]:
    return {r.id: r for r in RULES}


def report_issues(findings: List[Finding]) -> str:
    issues = sorted((f for f in findings if f.severity in ("error", "warn")),
                    key=lambda f: (_SEVERITY_RANK[f.severity], _ORDER.get(f.rule, 999), f.file, f.line))
    if not issues:
        return '    <p class="empty">No errors or warnings.</p>'
    rules = _rules_by_id()
    out = []
    for severity in ("error", "warn"):
        mine = [f for f in issues if f.severity == severity]
        if not mine:
            continue
        out.append(f'    <div class="sev-group" data-group>')
        out.append(f'      <h3 class="sev-h">{_sev(severity, True)} <span class="count">{len(mine)}</span></h3>')
        for rule_id in dict.fromkeys(f.rule for f in mine):
            group = [f for f in mine if f.rule == rule_id]
            what = rules[rule_id].message.replace("{match}", "…").strip(" :…") if rule_id in rules else ""
            out.append(f'      <div class="rule-group" data-group><h4><code>{_t(rule_id)}</code>'
                       f'<span class="rule-msg">{_t(what)}</span><span class="count">{len(group)}</span></h4>')
            out += _findings_list(group, "        ")
            out.append("      </div>")
        out.append("    </div>")
    return "\n".join(out)


def improvement_groups(findings: List[Finding]) -> List[Tuple[str, int, int, List[Finding]]]:
    """(rule, impact, weight, findings) for the suggestions, highest impact (weight x occurrences) first."""
    rules = _rules_by_id()
    by_rule: Dict[str, List[Finding]] = {}
    for f in findings:
        if f.severity == "suggest":
            by_rule.setdefault(f.rule, []).append(f)
    groups = []
    for rule_id, items in by_rule.items():
        weight = rules[rule_id].weight if rule_id in rules else 1
        groups.append((rule_id, weight * len(items), weight, sorted(items, key=lambda f: (f.file, f.line))))
    groups.sort(key=lambda g: (-g[1], _ORDER.get(g[0], 999)))
    return groups


def report_improvements(findings: List[Finding]) -> str:
    groups = improvement_groups(findings)
    if not groups:
        return '    <p class="empty">No improvements suggested.</p>'
    rules = _rules_by_id()
    out = ['    <ol class="improvements" role="list">']
    for rank, (rule_id, impact, weight, items) in enumerate(groups, 1):
        why = rules[rule_id].why if rule_id in rules else ""
        times = f"{len(items)} occurrence" + ("" if len(items) == 1 else "s")
        out.append(f'      <li class="improvement" data-rule="{_a(rule_id)}" data-impact="{impact}" data-group>'
                   f'<span class="rank" aria-hidden="true">{rank}</span><div class="imp-body">'
                   f'<div class="imp-head"><h3><span class="sr-only">Rank {rank}: </span><code>{_t(rule_id)}</code></h3>'
                   f'<span class="impact">impact {impact} (weight {weight} × {times})</span></div>'
                   + (f'<p class="why"><span class="why-label">Why</span>{_t(why)}</p>' if why else "")
                   + "".join(_findings_list(items)) + "</div></li>")
    out.append("    </ol>")
    return "\n".join(out)


def report_scales(scales: Optional[Dict[str, List[dict]]]) -> str:
    if not scales or not any(scales.values()):
        return ""
    rows = []
    for kind, groups in scales.items():
        if groups:
            shown = ", ".join(f"{g['value']} ×{g['count']}" for g in groups[:12]) + (" …" if len(groups) > 12 else "")
            rows.append(f"<tr><th scope=\"row\">{_t(kind)}</th><td>{_t(shown)}</td></tr>")
    return ('  <section id="scales" aria-labelledby="scales-h">\n    <div class="section-head"><h2 id="scales-h">Inferred '
            'scales</h2><p class="note">No tokens yet: the values the code already uses, most used first. Near-duplicates '
            'and one-off values are reported above.</p></div>\n    <div class="table-wrap"><table><thead><tr>'
            '<th scope="col">Kind</th><th scope="col">Values (uses)</th></tr></thead><tbody>' + "".join(rows)
            + "</tbody></table></div>\n  </section>")


def render_report(template: str, findings: List[Finding], checked: int, mode: str, scales: Optional[Dict[str, List[dict]]],
                  doc: Optional[dict], settings: dict, root: Path, skill_dir: Path, day: str) -> str:
    """The audit report page from the fixed template: summary, Issues (errors then warnings, grouped by rule),
    Improvements (suggestions ranked by impact), and how to re-run. Styled with the project's tokens when there are any."""
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warn")
    suggestions = sum(1 for f in findings if f.severity == "suggest")
    project = (str(settings.get("project") or "").strip() or str(settings.get("Project") or "").strip()
               or root.name or "This project")
    script = rel(skill_dir / SCRIPT_REL, root)
    theme_css = "/* No tokens yet: Plumb's neutral page colours. */"
    bt = load_build_tokens() if doc is not None else None
    if bt is not None:
        try:
            theme_css = bt.page_theme_css(doc)
        except PlumbError:
            theme_css = "/* The tokens could not be turned into CSS (see the findings): Plumb's neutral page colours. */"
    if errors:
        verdict = ('<span class="sev sev-error"><span class="sev-shape" aria-hidden="true"></span> Fails</span> '
                   f"{_plural(errors, 'error')} to fix" + (f", {_plural(warnings, 'warning')} to review" if warnings else ""))
    else:
        verdict = ('<span class="sev sev-pass"><span class="sev-shape" aria-hidden="true"></span> Pass</span> '
                   "No errors" + (f", {_plural(warnings, 'warning')} to review" if warnings else ""))
    mode_text = "full audit" if mode == MODE_FULL else "inconsistency-only (no tokens yet)"
    mode_note = ""
    if mode == MODE_INCONSISTENCY:
        mode_note = ('    <p class="note mode-note">Mode: inconsistency-only. There are no tokens yet, so raw values are '
                     "not errors; the scales are inferred from the code and near-duplicates and one-off values are "
                     "warnings.</p>")
    present = [r.id for r in RULES if any(f.rule == r.id for f in findings)]
    present += sorted({f.rule for f in findings} - set(present))
    options = "\n".join(f'          <option value="{_a(r)}">{_t(r)} ({sum(1 for f in findings if f.rule == r)})</option>'
                        for r in present)
    values = {
        "header": f"<!-- GENERATED by {_t(script)} --html on {day}. Do not edit: run the audit again. -->",
        "title": _t(f"{project}: design audit {day}"),
        "project": _t(project),
        "date": _t(day),
        "mode": _t(mode_text),
        "plumb_version": _t(P.PLUMB_VERSION),
        "theme_css": theme_css,
        "verdict": verdict,
        "errors": str(errors),
        "warnings": str(warnings),
        "suggestions": str(suggestions),
        "files": str(checked),
        "mode_note": mode_note,
        "rule_options": options,
        "issues": report_issues(findings),
        "improvements": report_improvements(findings),
        "scales": report_scales(scales),
        "rerun": _t(f"python3 {script} --html"),
    }
    text = P.fill_template(template, values, REPORT_TEMPLATE)
    return text if text.endswith("\n") else text + "\n"


def write_report(out: Path, text: str, root: Path) -> bool:
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as exc:
        print(f"error: cannot write the report to {rel(out, root)} ({exc.strerror or exc})\n"
              f"fix: pass a writable path ending in .html, e.g. --html docs/design/audit.html", file=sys.stderr)
        return False
    print(f"wrote {rel(out, root)}", file=sys.stderr)
    return True




class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: {USAGE}\n")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _report(findings: List[Finding], checked: int, as_json: bool, mode: Optional[str] = None,
            scales: Optional[Dict[str, List[dict]]] = None) -> int:
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warn")
    suggestions = sum(1 for f in findings if f.severity == "suggest")
    if as_json:
        out: dict = {"version": P.PLUMB_VERSION}
        if mode:
            out["mode"] = mode
        out.update({"checked": checked, "errors": errors, "warnings": warnings, "suggestions": suggestions,
                    "findings": [f.to_json() for f in findings]})
        if scales is not None:
            out["scales"] = scales
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    else:
        for f in findings:
            print(f"{f.file}:{f.line}: {f.severity} {f.rule}: {f.message}")
            print(f"  fix: {f.fix}")
        if mode == MODE_INCONSISTENCY:
            print("mode: inconsistency-only (no tokens yet): the scales below are inferred from the code; near-duplicates "
                  "and one-off values are warnings, raw values are not errors")
            for kind, groups in (scales or {}).items():
                if groups:
                    shown = ", ".join(f"{g['value']} x{g['count']}" for g in groups[:8])
                    print(f"  scale {kind}: {shown}" + (" ..." if len(groups) > 8 else ""))
        if errors or warnings:
            print(f"audit: {_plural(errors, 'error')}, {_plural(warnings, 'warning')} in {_plural(checked, 'file')} checked")
        else:
            print(f"audit: no design-system issues in {_plural(checked, 'file')}")
        if suggestions:
            print(f"audit: {_plural(suggestions, 'suggestion')} (improvements; they never fail the audit)")
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


MODE_FULL, MODE_INCONSISTENCY = "full", "inconsistency-only"


def _html_target(given: str, root: Path, skill_dir: Path, settings: dict) -> Tuple[Path, str]:
    """(report path, template text) for --html; raises PlumbError when the template is missing or unreadable."""
    tpl = P.find_template(skill_dir, REPORT_TEMPLATE)
    if tpl is None:
        raise PlumbError(f"error: templates/{REPORT_TEMPLATE} is missing from {rel(skill_dir, root)}, so the HTML report "
                         f"cannot be written\nfix: copy it from the Plumb plugin's assets/skill/templates/ into "
                         f"{rel(skill_dir / 'templates', root)}/ (or run /plumb:upgrade), then run the audit again")
    try:
        template = tpl.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise PlumbError(f"error: {tpl}: cannot read the report template ({exc})\n"
                         f"fix: restore it from the Plumb plugin's assets/skill/templates/") from None
    if given:
        return Path(given).resolve(), template
    docs = str(settings.get("docs_dir") or "docs/design").replace("\\", "/").strip("/") or "docs/design"
    return (root / docs / f"audit-{datetime.date.today().isoformat()}.html").resolve(), template


def run_full(args: argparse.Namespace, root: Path, skill_dir: Path, doc: Optional[dict], settings: dict,
             tokens_file: Optional[Path] = None) -> int:
    explicit = bool(args.paths)
    targets = [Path(p).resolve() for p in args.paths] if explicit else [root.resolve()]
    existing = [t for t in targets if t.exists()]
    for t in targets:
        if not t.exists():
            print(f"note: {t} does not exist, skipped", file=sys.stderr)
    if not existing:
        print(f"error: none of {', '.join(str(t) for t in targets)} exist, nothing was checked\n"
              f"fix: pass the folders that hold your UI code, e.g. python3 {rel(skill_dir / SCRIPT_REL, root)} app components",
              file=sys.stderr)
        return 2
    files = collect_files(existing, root, skill_dir, settings, explicit)
    looked = ", ".join(rel(t, root) if rel(t, root) != "." else "the project root" for t in existing)
    ui = str(settings.get("UI files", "") or "").strip()
    if ui and not explicit:
        looked += f", narrowed by PLUMB.md UI files: {ui}"
    return audit_files(files, root, skill_dir, doc, settings, tokens_file, explicit, args.json, looked,
                       html_out=getattr(args, "html_out", None))


def audit_files(files: List[Path], root: Path, skill_dir: Path, doc: Optional[dict], settings: dict,
                tokens_file: Optional[Path], explicit: bool, as_json: bool, looked: str = "the paths given",
                html_out: Optional[Tuple[Path, str]] = None) -> int:
    """Full mode over a list of files: per-file rules, then the cross-file rules. With no tokens (doc None) this is
    inconsistency-only mode. A --changed mode (end-of-turn check) can call this with the changed files only."""
    inconsistency = doc is None
    skip = RAW_VALUE_RULES if inconsistency else frozenset()
    findings: List[Finding] = []
    ctxs: List[Ctx] = []
    generated: List[str] = []
    for path in files:
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
            generated.append(text)  # a header counts only on the paths the generators own
            continue
        ctx = make_ctx(name, text, doc, settings)
        if ctx is None:
            continue
        ctxs.append(ctx)
        findings.extend(file_findings(ctx, skip))
    if not ctxs:
        exts = " ".join(sorted(PLATFORM_OF))
        print(f"error: no UI files ({exts}) in {looked}, nothing was checked\n"
              f"fix: pass the folders that hold your UI code, e.g. python3 {rel(skill_dir / SCRIPT_REL, root)} app components",
              file=sys.stderr)
        return 2
    if doc is not None and load_build_tokens() is None:
        print(f"note: {_BUILD_TOKENS} is not next to audit.py: contrast and generated-file checks skipped", file=sys.stderr)
    proj = Project(root, skill_dir, doc, settings, ctxs, explicit, tokens_file, generated)
    findings.extend(cross_findings(proj))
    mode = MODE_INCONSISTENCY if inconsistency else MODE_FULL
    scales = proj.scales_inferred() if inconsistency else None
    code = _report(findings, len(ctxs), as_json, mode, scales)
    if html_out is not None:  # (path, template text): the terminal output above is unchanged
        page = render_report(html_out[1], findings, len(ctxs), mode, scales, doc, settings, root, skill_dir,
                             datetime.date.today().isoformat())
        if not write_report(html_out[0], page, root):
            return 2
    return code


def main(argv: Optional[List[str]] = None) -> int:
    P.utf8_stdio()
    parser = _Parser(prog="audit.py", description="Check UI source against the design tokens.")
    parser.add_argument("paths", nargs="*", metavar="PATHS", help="files or folders to check (default: the project)")
    parser.add_argument("--quick", metavar="FILE", help="check one file and report only what the edit adds (JSON)")
    parser.add_argument("--before", metavar="-|PATH", help="with --quick: the file's text before the edit (- reads stdin)")
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    parser.add_argument("--html", nargs="?", const="", metavar="OUT.html",
                        help="also write the HTML report (default <docs_dir>/audit-YYYY-MM-DD.html); put it after the PATHS")
    parser.add_argument("--root", metavar="SKILL_DIR", help="the design-system skill folder (default: this script's skill)")
    parser.add_argument("--project", metavar="PATH", help="project root when no PLUMB.md is found above the skill")
    parser.add_argument("--no-tokens", action="store_true",
                        help="inconsistency-only mode even when a tokens file exists (infer the scales from the code)")
    args = parser.parse_args(argv)
    if args.before and not args.quick:
        parser.error("--before works only with --quick FILE")
    if args.quick and args.paths:
        parser.error("--quick checks one file: pass no other paths")
    if args.quick and args.html is not None:
        parser.error("--quick prints JSON for one edit; --html is for the full audit (drop --quick)")
    if args.html and not args.html.lower().endswith((".html", ".htm")):
        parser.error(f"--html takes the report's path ending in .html, got {args.html!r} (put --html after the PATHS, "
                     f"or write --html=OUT.html)")
    skill_dir = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        root = find_project_root(skill_dir, Path(args.project) if args.project else None)
        tokens_file = None if args.no_tokens else find_tokens(skill_dir)
        doc = P.load_tokens(tokens_file) if tokens_file is not None else None
        settings = make_settings(root, doc)
        if doc is None and not args.no_tokens:
            print(f"note: no tokens file in {rel(skill_dir / 'assets' / 'tokens', root)}: inconsistency-only mode "
                  f"(only the checks that need no tokens ran)", file=sys.stderr)
        if args.quick:
            return run_quick(args, root, doc, settings)
        args.html_out = None
        if args.html is not None:
            args.html_out = _html_target(args.html, root, skill_dir, settings)
        return run_full(args, root, skill_dir, doc, settings, tokens_file)
    except PlumbError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        print(f"error: unexpected token structure ({type(exc).__name__}: {exc})\n"
              f"fix: open the tokens file and compare it with reference/tokens-format.md", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
