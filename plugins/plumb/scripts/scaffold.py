#!/usr/bin/env python3
"""scaffold.py: lay the project's design-system skill (and PLUMB.md) into a project from the plugin's templates.

Run by /plumb:create and /plumb:extract:

  scaffold.py --project-root P --name NAME --skill-dir D --platforms web,ios,android
              --styling tailwind-v4|tailwind-v3|css [--answers answers.json] [--docs-dir docs/design]
              (--dry-run | --confirm TOKEN)

  --skill-dir   the skill folder relative to the project root, e.g. .claude/skills/<project>-design-system
                (forward or back slashes; it must stay inside the project)
  --docs-dir    where the design pages live (default docs/design); recorded in the tokens file
  --dry-run     print what would be written (`would write:` / `skip:`) and write nothing; the last line names the
                confirm token for exactly this command, answers file and file list
  --confirm T   the real run: the token the dry run printed. Without it, or when the answers, the arguments or the
                files changed since the dry run, nothing is written (error: + ask the user: show the dry-run list and
                get their OK). Human in the loop: the person sees and approves the list before anything is written.

Ownership (spec 5.1):
  [P] plugin-owned, ALWAYS overwritten (printed `wrote:`): scripts/*.py, templates/*, assets/platforms/README.md
  [Y] yours, written only when absent (printed `wrote:`, else `skip: <path> (yours, kept)`): SKILL.md, design.md,
      assets/tokens/<project>.tokens.json (skipped when the folder already holds any *.tokens.json),
      assets/icons/icon-map.json, assets/platforms/web/tokens.css.template, references/** (only the chosen platforms'),
      PLUMB.md (project root), <docs-dir>/decisions.md, <docs-dir>/prototype/screens/ (a .gitkeep)

  scaffold.py --relocate FROM TO --project-root P [--dry-run]
      Move an existing design-system skill folder and update every reference in one step: PLUMB.md (the Design system line
      and the command lines), the Plumb row in AGENTS.md / CLAUDE.md (only that row), the Makefile lines that name the
      skill path. web.copies stay project-relative (checked, not changed). Then runs the moved build-tokens.py --check;
      generated files carry the old path in their header, so a stale result is regenerated once and checked again.
      Refuses (error/fix) when TO exists and is not empty, when TO is outside the project, or when FROM is not a Plumb
      design-system skill (needs SKILL.md and assets/tokens/*.tokens.json). --dry-run lists every change, writes nothing.

  scaffold.py --verify --project-root P
      Check that PLUMB.md's skill path exists, that the AGENTS.md / CLAUDE.md row and the Makefile point at it, that
      every `make <target>` PLUMB.md names exists in the Makefile (a target missing from a Makefile that includes
      other files is a note), and that the copy targets resolve (not in a `Role: linked` repo: the home owns them). Prints `ok:` / `problem:` / `note:` lines; when the skill is found in a default place
      (.claude/skills/*-design-system, .github/skills/*-design-system) other than where PLUMB.md says, prints the
      suggested --relocate command. It also checks PLUMB.md's Routes: (each recorded path exists, each entry has a
      kind; not recorded is a note), UI files: (matching 0 files while the project has UI code is a problem) and, in a
      repository, that the skill folder, PLUMB.md and the docs folder are not ignored (check-ignore; a problem with
      the fix). Exit 0 when there is no problem, 1 otherwise.

Generated files ([G]) are not written here: run build-tokens.py afterwards. Nothing is installed or downloaded.

Placeholders in the templates are {{NAME}} (upper case); every one is filled from the answers or a neutral default, so a
scaffold always builds. Anything not answered is listed in a "Neutral defaults" note in design.md.

answers.json (every key optional; unknown keys are ignored with a note):
  {
    "description": "one or two sentences: what the product is",
    "audience":    "who uses it",
    "direction":   "name of the chosen design direction",
    "voice":       "tone of the copy",
    "themes":      "light-and-dark" | "light-only",
    "python":      "python3",                          (the command PLUMB.md and the Makefile use)
    "role":        "home" | "linked",
    "ui_packages": ". (Next.js · Tailwind v4)",        (PLUMB.md)
    "routes":      "frontend/src/app (next-app)",       (PLUMB.md `Routes:`: the app's page roots the agent found and the
                   user confirmed, each "<path> (<kind>)": next-app, next-pages, nuxt, sveltekit, angular (the routes
                   file), router (another router config file or glob), comma separated, or "none"; a missing kind is
                   refused; unanswered: not recorded (web) or none (mobile only).
                   Scripts and hooks read routes only from here: they never guess the layout)
    "ui_files":    "app/**, components/** · *.tsx *.css",   (PLUMB.md; unanswered: detect.py's value for the chosen
                   platforms' packages (Angular: src/** · *.component.ts ... styles.css; web next to iOS/Android: the
                   mobile folders too; a chosen platform with no package keeps *.swift / *.kt), printed as a note;
                   else the platform default)
    "allowed_raw": "components/ui/**",
    "web_copies":  ["app/globals.css"],                (project-relative files that get Plumb's marked block of the
                   generated CSS; an existing file keeps everything outside the block, and a note says so)
    "theme_switch": "both" | "system" | "class" | "data-theme",  (how the web app switches to dark: the system setting, a .dark
                   class, either, or data-theme="dark" on <html> as next-themes sets it; default both)
    "reduced_motion": "none" | "keep-fades",           (what reduced motion keeps on the web: nothing, or the opacity
                   and colour fades; default none)
    "reset_palette": true | false,                     ($extensions.plumb.web.reset_palette, Tailwind v4: true = Plumb's
                   block switches off Tailwind's default palette and scales, only the tokens exist (create, a new app);
                   false = they stay until the app is migrated, the audit suggests each move (extract, an existing
                   app). Unanswered: false when the app's UI files already use default palette classes (a note says
                   so), else true)
    "colors": {"light": {"primary": "#0f6b66", ...}, "dark": {"primary": "#4fb3c4", ...}},
        names: background surface sunk on-surface on-surface-muted primary on-primary outline outline-input danger
               on-danger success on-success scrim; values #rgb | #rrggbb | #rrggbbaa. Other tokens: edit the tokens file.
    "fonts":       {"sans": "Inter", "mono": "JetBrains Mono"},   (first family; the system stack follows)
    "type_scale":  {"body": ["16px", "24px"], ...},    name -> [font size, line height];
        names: display h1 h2 h3 body-lg body sm xs
    "spacing":     {"2": "8px", ...},                  Tailwind steps: 1 2 3 4 5 6 8 10 12 16
    "radius":      {"sm": "4px", "md": "8px", "lg": "12px"},
    "shadows":     {"card": {"light": "#0f121714", "dark": "#00000066"}, "popover": {...}},
    "motion":      {"fast": "150ms", "mid": "200ms", "slow": "300ms"},
    "icons":       [{"concept": "home", "lucide": "house", "sfSymbol": "house", "materialSymbol": "home"}, ...]
  }

Exit codes: 0 ok, 2 bad input (`error: ...` then `fix: ...` on stderr). Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL_SRC = PLUGIN_ROOT / "assets" / "skill"
TEMPLATES_SRC = PLUGIN_ROOT / "templates"
PLUMB_VERSION = "1.0.0"

PLATFORMS = ("web", "ios", "android")
PLATFORM_LABEL = {"web": "Web", "ios": "iOS", "android": "Android"}
STYLINGS = ("tailwind-v4", "tailwind-v3", "css")
STYLING_LABEL = {"tailwind-v4": "Tailwind CSS v4", "tailwind-v3": "Tailwind CSS v3", "css": "plain CSS"}
THEMES = ("light-and-dark", "light-only")
ROLES = ("home", "linked")
THEME_SWITCHES = ("both", "system", "class", "data-theme")  # $extensions.plumb.web.theme_switch
REDUCED_MOTION = ("none", "keep-fades")  # $extensions.plumb.motion.reduced

RAW_JSON_SLOTS = frozenset(("ICONS_JSON", "PLATFORMS_JSON", "COPIES_JSON", "RESET_PALETTE"))
SLOT = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
DIMENSION = re.compile(r"^\d+(?:\.\d+)?(?:px|rem|em)$")
DURATION = re.compile(r"^\d+(?:\.\d+)?(?:ms|s)$")


class ScaffoldError(Exception):
    """A refusal: `error: ...` then `fix: ...` (or `ask the user: ...`)."""

    def __init__(self, message: str, fix: str) -> None:
        super().__init__(f"error: {message}\n" + (fix if fix.startswith("ask the user:") else f"fix: {fix}"))


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is not None:
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - leave an odd stream as it is
                pass


# ---------------------------------------------------------------- neutral defaults (every answer has one)

DEFAULT_COLORS: Dict[str, Dict[str, str]] = {
    "light": {
        "background": "#ffffff", "surface": "#ffffff", "sunk": "#f3f5f7", "on-surface": "#1b2230",
        "on-surface-muted": "#475467", "primary": "#0f6b66", "on-primary": "#ffffff", "outline": "#d5dae1",
        "outline-input": "#6b7686", "danger": "#b42318", "on-danger": "#ffffff", "success": "#067647",
        "on-success": "#ffffff", "scrim": "#0f1217cc",
    },
    "dark": {
        "background": "#0f1217", "surface": "#171b22", "sunk": "#0b0e12", "on-surface": "#e7eaef",
        "on-surface-muted": "#a9b1bd", "primary": "#4fb3c4", "on-primary": "#0b1417", "outline": "#2a313c",
        "outline-input": "#7a8696", "danger": "#f97066", "on-danger": "#1a0705", "success": "#47cd89",
        "on-success": "#04170d", "scrim": "#000000cc",
    },
}
DEFAULT_TYPE: Dict[str, Tuple[str, str]] = {
    "display": ("48px", "56px"), "h1": ("36px", "44px"), "h2": ("30px", "38px"), "h3": ("24px", "32px"),
    "body-lg": ("18px", "28px"), "body": ("16px", "24px"), "sm": ("14px", "20px"), "xs": ("12px", "16px"),
}
DEFAULT_SPACING: Dict[str, str] = {
    "1": "4px", "2": "8px", "3": "12px", "4": "16px", "5": "20px", "6": "24px", "8": "32px", "10": "40px",
    "12": "48px", "16": "64px",
}
DEFAULT_RADIUS = {"sm": "4px", "md": "8px", "lg": "12px"}
DEFAULT_SHADOWS = {
    "card": {"light": "#0f121714", "dark": "#00000066"},
    "popover": {"light": "#0f121724", "dark": "#00000099"},
}
DEFAULT_MOTION = {"fast": "150ms", "mid": "200ms", "slow": "300ms"}
DEFAULT_FONTS = {"sans": "system-ui", "mono": "ui-monospace"}
DEFAULT_ICONS: List[Dict[str, str]] = [
    {"concept": c, "lucide": l, "sfSymbol": s, "materialSymbol": m} for c, l, s, m in (
        ("home", "house", "house", "home"), ("search", "search", "magnifyingglass", "search"),
        ("add", "plus", "plus", "add"), ("close", "x", "xmark", "close"), ("check", "check", "checkmark", "check"),
        ("warning", "triangle-alert", "exclamationmark.triangle", "warning"),
        ("error", "octagon-x", "xmark.octagon", "error"), ("info", "info", "info.circle", "info"),
        ("settings", "settings", "gearshape", "settings"), ("menu", "menu", "line.3.horizontal", "menu"),
        ("back", "arrow-left", "chevron.left", "arrow_back"), ("delete", "trash-2", "trash", "delete"),
        ("edit", "pencil", "pencil", "edit"), ("user", "user", "person", "person"),
    )
]
KNOWN_KEYS = frozenset((
    "name", "description", "audience", "direction", "voice", "themes", "python", "role", "ui_packages", "ui_files",
    "allowed_raw", "web_copies", "colors", "fonts", "type_scale", "spacing", "radius", "shadows", "motion", "icons",
    "theme_switch", "reduced_motion", "routes", "reset_palette",
))
# Answers that, when absent, are listed in design.md as neutral defaults.
DEFAULT_NOTE_KEYS = (("description", "description"), ("audience", "audience"), ("direction", "direction"),
                     ("voice", "voice"), ("colors", "colours"), ("fonts", "fonts"), ("type_scale", "type scale"),
                     ("spacing", "spacing"), ("radius", "radii"), ("shadows", "shadows"), ("motion", "motion"))


# ---------------------------------------------------------------- answers


def _bad(path: str, got: object, want: str, fix: str) -> ScaffoldError:
    return ScaffoldError(f"answers {path} is {got!r}, {want}", fix)


def _obj(answers: dict, key: str) -> dict:
    value = answers.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScaffoldError(f"answers.{key} must be an object", f"write answers.{key} as an object, see the scaffold.py docstring")
    return value


def _text(answers: dict, key: str, default: str) -> str:
    value = answers.get(key)
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip() or re.search(r"[\r\n]", value) and key != "description":
        raise ScaffoldError(f"answers.{key} must be a non-empty text" + ("" if key == "description" else " on one line"),
                            f"set answers.{key} to a string")
    return " ".join(value.split()) if key != "description" else value.strip().replace("\r\n", "\n")


def load_answers(path: Optional[str]) -> dict:
    if not path:
        return {}
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ScaffoldError(f"cannot read the answers file {path} ({exc.strerror or exc})",
                            "pass --answers with an existing answers.json, or leave it out") from None
    except UnicodeDecodeError:
        raise ScaffoldError(f"the answers file {path} is not UTF-8", "save it as UTF-8") from None
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ScaffoldError(f"the answers file {path} is not valid JSON ({exc})", "fix the JSON, then run the scaffold again") from None
    if not isinstance(data, dict):
        raise ScaffoldError(f"the answers file {path} must hold a JSON object", "wrap the answers in { ... }")
    return data


def _merge(answers: dict, key: str, defaults: Dict[str, str], check: "re.Pattern[str]", want: str) -> Dict[str, str]:
    given = _obj(answers, key)
    out = dict(defaults)
    for name, value in given.items():
        if name not in defaults:
            raise ScaffoldError(f"answers.{key} has the unknown name {name!r}",
                                f"use one of: {', '.join(defaults)} (other tokens are added by editing the tokens file)")
        if not isinstance(value, str) or not check.match(value):
            raise _bad(f"{key}.{name}", value, want, f"write answers.{key}.{name} as {want}")
        out[name] = value
    return out


def resolve_answers(answers: dict, name: str, platforms: List[str]) -> Tuple[Dict[str, str], dict, List[str]]:
    """(placeholder values for tokens/design, extras: icons/copies/themes..., names of the unanswered groups)."""
    for key in answers:
        if key not in KNOWN_KEYS:
            print(f"note: answers key {key!r} is not used by the scaffold", file=sys.stderr)
    v: Dict[str, str] = {}
    colors = _obj(answers, "colors")
    for mode in colors:
        if mode not in ("light", "dark"):
            raise ScaffoldError(f"answers.colors has {mode!r}", 'use "light" and "dark"')
    for mode, suffix in (("light", ""), ("dark", "_DARK")):
        given = colors.get(mode, {})
        if not isinstance(given, dict):
            raise ScaffoldError(f"answers.colors.{mode} must be an object", "map colour names to #hex values")
        merged = _merge({"c": given}, "c", DEFAULT_COLORS[mode], HEX, "a hex colour such as #1f7a8c")
        for token, value in merged.items():
            v["COLOR_" + token.upper().replace("-", "_") + suffix] = value
    fonts = _obj(answers, "fonts")
    for key, default in DEFAULT_FONTS.items():
        given = fonts.get(key, default)
        if not isinstance(given, str) or not given.strip() or re.search(r"[\r\n]", given):
            raise _bad(f"fonts.{key}", given, "not a font family name", f"write answers.fonts.{key} as a family name")
        v["FONT_" + key.upper()] = given.strip()
    type_given = _obj(answers, "type_scale")
    for name_, pair in type_given.items():
        if name_ not in DEFAULT_TYPE:
            raise ScaffoldError(f"answers.type_scale has the unknown name {name_!r}", f"use one of: {', '.join(DEFAULT_TYPE)}")
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, str) and DIMENSION.match(x) for x in pair)):
            raise _bad(f"type_scale.{name_}", pair, "not [font size, line height]", 'write it as ["16px", "24px"]')
    for token, (size, line) in DEFAULT_TYPE.items():
        size, line = type_given.get(token, (size, line))
        key = token.upper().replace("-", "_")
        v[f"TYPE_{key}_SIZE"], v[f"TYPE_{key}_LINE"] = size, line
    for token, value in _merge(answers, "spacing", DEFAULT_SPACING, DIMENSION, 'a size such as "8px"').items():
        v["SPACE_" + token] = value
    for token, value in _merge(answers, "radius", DEFAULT_RADIUS, DIMENSION, 'a size such as "8px"').items():
        v["RADIUS_" + token.upper()] = value
    for token, value in _merge(answers, "motion", DEFAULT_MOTION, DURATION, 'a duration such as "150ms"').items():
        v["DURATION_" + token.upper()] = value
    shadows = _obj(answers, "shadows")
    for token, default in DEFAULT_SHADOWS.items():
        given = shadows.get(token, {})
        if not isinstance(given, dict):
            raise ScaffoldError(f"answers.shadows.{token} must be an object", 'write {"light": "#0f121714", "dark": "#00000066"}')
        merged = _merge({"s": given}, "s", default, HEX, "a hex colour with alpha such as #0f121714")
        v["SHADOW_" + token.upper()], v["SHADOW_" + token.upper() + "_DARK"] = merged["light"], merged["dark"]
    for token in shadows:
        if token not in DEFAULT_SHADOWS:
            raise ScaffoldError(f"answers.shadows has the unknown name {token!r}", f"use one of: {', '.join(DEFAULT_SHADOWS)}")

    themes = answers.get("themes", "light-and-dark")
    if themes not in THEMES:
        raise _bad("themes", themes, "not a theme choice", f"use one of: {', '.join(THEMES)}")
    role = answers.get("role", "home")
    if role not in ROLES:
        raise _bad("role", role, "not a role", f"use one of: {', '.join(ROLES)}")
    switch = answers.get("theme_switch", "both")
    if switch not in THEME_SWITCHES:
        raise _bad("theme_switch", switch, "not a theme switch", f"use one of: {', '.join(THEME_SWITCHES)}")
    reduced = answers.get("reduced_motion", "none")
    if reduced not in REDUCED_MOTION:
        raise _bad("reduced_motion", reduced, "not a reduced-motion choice", f"use one of: {', '.join(REDUCED_MOTION)}")
    v["THEME_SWITCH"], v["REDUCED_MOTION"] = switch, reduced
    copies = answers.get("web_copies", [])
    if not isinstance(copies, list) or not all(isinstance(c, str) and safe_rel(c) for c in copies):
        raise ScaffoldError("answers.web_copies must be a list of project-relative paths",
                            'write it like ["app/globals.css"]; no absolute paths, no ..')
    icons = answers.get("icons", DEFAULT_ICONS)
    if not isinstance(icons, list) or not icons:
        raise ScaffoldError("answers.icons must be a non-empty list", 'write entries like {"concept": "home", "sfSymbol": "house", "materialSymbol": "home"}')
    for i, entry in enumerate(icons):
        for key in ("concept", "sfSymbol", "materialSymbol"):
            if not isinstance(entry, dict) or not isinstance(entry.get(key), str) or not entry[key]:
                raise ScaffoldError(f"answers.icons[{i}] is missing {key}", f"add {key} to that icon entry")

    unanswered = [label for key, label in DEFAULT_NOTE_KEYS if key not in answers]
    v["DESCRIPTION"] = _text(answers, "description", f"{name} (not described yet: say what it is and who it is for).")
    v["AUDIENCE"] = _text(answers, "audience", f"the people who use {name} (not answered yet)")
    v["DIRECTION"] = _text(answers, "direction", "Neutral")
    v["VOICE"] = _text(answers, "voice", "plain, calm and direct (default)")
    v["THEMES"] = themes
    v["ROLE"] = role
    if unanswered:
        v["DEFAULTS_NOTE"] = ("> Neutral defaults: " + ", ".join(unanswered) + " were not answered when this was created. "
                              "They are placeholders, not decisions; replace them through `/plumb:update`.")
    else:
        v["DEFAULTS_NOTE"] = ""
    extras = {"icons": icons, "copies": copies, "answers": answers}
    return v, extras, unanswered


# ---------------------------------------------------------------- paths and names


def safe_rel(text: str) -> Optional[str]:
    """A project-relative posix path (backslashes accepted), or None when empty, absolute or escaping."""
    path = text.strip().replace("\\", "/")
    if not path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def project_rel(text: str, root: Path, flag: str, example: str) -> str:
    rel = safe_rel(text)
    if rel is None and text.strip() and (text.strip().startswith("/") or re.match(r"^[A-Za-z]:[\\/]", text.strip())):
        try:  # an absolute path is fine when it is inside the project
            rel = Path(text.strip()).resolve().relative_to(root.resolve()).as_posix() or None
        except (ValueError, OSError):
            rel = None
    if rel is None:
        raise ScaffoldError(f"{flag} {text!r} is not a folder inside the project",
                            f"give a path relative to the project root, e.g. {flag} {example}")
    return rel


def slugify(name: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def pascal(slug: str) -> str:
    out = "".join(w[:1].upper() + w[1:] for w in slug.split("-") if w)
    return out if not out[:1].isdigit() else "P" + out


def parse_platforms(text: str) -> List[str]:
    chosen = [p.strip().lower() for p in text.split(",") if p.strip()]
    bad = [p for p in chosen if p not in PLATFORMS]
    if bad or not chosen:
        raise ScaffoldError(f"the platform list {text!r} " + (f"has {', '.join(bad)}" if bad else "is empty"),
                            f"use --platforms with any of: {', '.join(PLATFORMS)} (comma separated), e.g. --platforms web,ios")
    return [p for p in PLATFORMS if p in chosen]


# ---------------------------------------------------------------- placeholder values for the structure


def platform_values(platforms: List[str], styling: str) -> Dict[str, str]:
    mobile = [p for p in platforms if p != "web"]
    rows: List[str] = []

    def row(path: str, text: str) -> None:
        rows.append(f"| [{path}]({path}) | {text} |")

    if "web" in platforms:
        row("references/web/stack.md", "Web dependencies, folders, commands, dev-only pages.")
        row("references/web/components.md", "Web building blocks: layers, variants, recipes.")
        row("references/web/ux-guidelines.md", "Web page anatomy, breakpoints, forms, feedback, keyboard.")
        row("references/web/dark-mode.md", "Web dark-mode implementation and switching.")
    if mobile:
        row("references/mobile/README.md", "Any iOS or Android work: touch targets, safe areas, navigation, type scaling.")
        row("references/mobile/components.md", "Mobile-only components and mobile behaviour of shared ones.")
    if "ios" in platforms:
        row("references/mobile/ios/ios.md", "iOS conventions: SwiftUI, navigation, SF Symbols, Dynamic Type, VoiceOver.")
        row("references/mobile/ios/components.md", "The SwiftUI building block for each component.")
    if "android" in platforms:
        row("references/mobile/android/android.md", "Android conventions: Compose, Material 3, TalkBack, predictive back.")
        row("references/mobile/android/components.md", "The Compose building block for each component.")
    spec = {"web": "[web](references/web/components.md)", "ios": "[iOS](references/mobile/ios/components.md)",
            "android": "[Android](references/mobile/android/components.md)"}
    links = [spec[p] for p in platforms]
    mobile_links = {"ios": "[iOS](ios/ios.md)", "android": "[Android](android/android.md)"}
    return {
        "PLATFORMS": ", ".join(platforms),
        "PLATFORMS_JSON": json.dumps(platforms),
        "PLATFORM_FILE_ROWS": "\n".join(rows),
        "PLATFORM_SPEC_LINKS": ", ".join(links[:-1]) + (" and " if len(links) > 1 else "") + links[-1],
        "MOBILE_PLATFORM_LINKS": ", ".join(mobile_links[p] for p in mobile) or "(no mobile platform chosen)",
        "PLATFORM_HEADERS": " | ".join(PLATFORM_LABEL[p] for p in platforms),
        "PLATFORM_CELLS": " | ".join("to build" for _ in platforms),
        "PLATFORM_SEPARATORS": "---|" * len(platforms),
        "STYLING": styling,
        "STYLING_LABEL": STYLING_LABEL[styling],
    }


PLATFORM_UI_FILES = {"web": "app/**, src/**, components/** · *.tsx *.jsx *.vue *.svelte *.css", "ios": "*.swift",
                     "android": "*.kt"}
PLATFORM_UI_NAMES = {"ios": "*.swift", "android": "*.kt"}
DETECT = Path(__file__).resolve().parent / "detect.py"


def load_detect():
    """detect.py from this folder (its project-id rule and stack scan)."""
    spec = importlib.util.spec_from_file_location("plumb_detect_for_scaffold", DETECT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def detected_ui_files(root: Path, platforms: List[str]) -> Optional[str]:
    """The UI files the project's stack needs when the platform default does not fit, from detect.py's scan of the
    project root (only the packages of the chosen platforms): Angular's component files, or web next to iOS/Android
    with the mobile folders. A chosen mobile platform with no package yet keeps its file names (*.swift, *.kt). None
    when the default fits; when the scan fails, None with a note."""
    try:
        mod = load_detect()
        ui, _ = mod.classify(root)
        value = mod.ui_files_for([u for u in ui if set(u["platforms"]) & set(platforms)], root)
    except Exception as exc:  # noqa: BLE001 - detection is a convenience: fall back to the platform default
        print(f"note: UI files: the platform default (detecting the stack failed: {exc})", file=sys.stderr)
        return None
    if value is None:
        return None
    names = value.partition(" · ")[2].split()
    extra = [PLATFORM_UI_NAMES[p] for p in platforms if p in PLATFORM_UI_NAMES and PLATFORM_UI_NAMES[p] not in names]
    return " ".join([value] + extra)


def project_ui_files(platforms: List[str], answers: dict, root: Optional[Path], say: bool = False) -> str:
    """PLUMB.md's `UI files:` value: the answer, else detect.py's value for the chosen platforms' packages (with a
    note when say), else the platform default."""
    ui_files = answers.get("ui_files")
    if not ui_files and root is not None and "web" in platforms:
        ui_files = detected_ui_files(root, platforms)
        if ui_files and say:
            print(f"note: UI files from the detected stack: {ui_files} (to change it, pass ui_files in --answers)",
                  file=sys.stderr)
    return ui_files or " · ".join(PLATFORM_UI_FILES[p] for p in platforms)


def load_plugin_audit():
    """The plugin's audit.py (its palette-class scan), or None."""
    try:
        spec = importlib.util.spec_from_file_location("plumb_audit_for_scaffold", SKILL_SRC / "scripts" / "audit.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["plumb_audit_for_scaffold"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception:  # noqa: BLE001 - the default is a convenience
        return None


def resolve_reset_palette(answers: dict, styling: str, platforms: List[str], root: Path, skill_rel: str) -> bool:
    """$extensions.plumb.web.reset_palette: the `reset_palette` answer (create on a new app: true; extract on an
    existing app: false), else true unless the app's UI files already use Tailwind's default palette classes (Tailwind
    v4 only): then false, so the first build does not take their colour away, with a note saying so."""
    given = answers.get("reset_palette")
    if given is not None:
        if not isinstance(given, bool):
            raise _bad("reset_palette", given, "not true or false",
                       "write answers.reset_palette as true (only the tokens exist) or false (Tailwind's default "
                       "palette and scales stay until the app is migrated)")
        return given
    if styling != "tailwind-v4" or "web" not in platforms:
        return True
    audit = load_plugin_audit()
    if audit is None:
        return True
    settings = {"UI files": project_ui_files(platforms, answers, root), "web": {"styling": styling}}
    try:
        count, files, _examples = audit.palette_uses(root, root / skill_rel, None, settings)
    except Exception:  # noqa: BLE001
        return True
    if not count:
        return True
    print(f"note: reset_palette false: the app uses {count} Tailwind default palette class{'es' if count != 1 else ''} "
          f"in {len(files)} UI file{'s' if len(files) != 1 else ''}, so Tailwind's palette stays until they move to "
          f"tokens (to close it now, pass \"reset_palette\": true in --answers)", file=sys.stderr)
    return False


def plumb_md_values(platforms: List[str], styling: str, docs: str, skill_dir: str, name: str, answers: dict,
                    base: Dict[str, str], root: Optional[Path] = None) -> Dict[str, str]:
    ui_files = project_ui_files(platforms, answers, root, say=True)
    return {
        "ROUTES": routes_value(answers, platforms),
        "PROJECT": name, "SKILL_DIR": skill_dir + "/", "ROLE": base["ROLE"], "PLATFORMS": ", ".join(platforms),
        "UI_PACKAGES": answers.get("ui_packages") or (f". ({STYLING_LABEL[styling]})" if "web" in platforms else "."),
        "PYTHON": base["PYTHON"], "EDIT_CHECK": "on", "END_CHECK": "on", "THEMES": base["THEMES"],
        "UI_FILES": ui_files, "ALLOWED_RAW": answers.get("allowed_raw") or ("components/ui/**" if "web" in platforms else "none"),
        "PROTOTYPE_MAIN": f"{docs}/prototype.html", "SCREENS_PAGE": f"{docs}/screens.html",
        "SCREENS_MAP": f"{docs}/prototype/screens.json", "PROTOTYPE_SYNC": "on",
        "DATE": base["DATE"], "DIRECTION": base["DIRECTION"],
    }


ROUTES_UNRECORDED = "(not recorded yet: /plumb:init records the app's page roots)"


def routes_value(answers: dict, platforms: List[str]) -> str:
    """PLUMB.md's `Routes:` value: the `routes` answer (the page roots the agent found and the user confirmed, e.g.
    "frontend/src/app (next-app)"), checked by the same parser the audit and the hooks use; unanswered: "none" without
    a web platform, else a placeholder that reads as not recorded (scripts never guess the app's layout)."""
    given = answers.get("routes")
    if given is None:
        return "none" if "web" not in platforms else ROUTES_UNRECORDED
    if not isinstance(given, str) or not given.strip() or re.search(r"[\r\n]", given):
        raise ScaffoldError("answers.routes must be a non-empty text on one line",
                            'write it like "frontend/src/app (next-app)", "src/app/app.routes.ts (router)" or "none"')
    roots, problems = load_plumb_core().parse_routes(given)
    if problems or roots is None:
        raise ScaffoldError("answers.routes: " + ("; ".join(problems) if problems else f"{given!r} is not a value"),
                            'write each page root as "<path> (<kind>)", kinds: next-app, next-pages, nuxt, sveltekit, '
                            'angular (the routes file), router (another router config file), comma separated; or "none"')
    return " ".join(given.split())


def load_plumb_core():
    """The plugin's _plumb.py (the PLUMB.md parsers the audit and hooks use)."""
    spec = importlib.util.spec_from_file_location("plumb_core_for_scaffold", SKILL_SRC / "scripts" / "_plumb.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------- token names in the references

MISSING_TOKEN = "`<{what}: no such token yet, add one with /plumb:update>`"


def project_tokens(existing: Optional[Path], planned: str) -> dict:
    """The tokens the references will sit next to: the project's tokens file when it is already there (kept as it is),
    else the one this scaffold writes. {} when it cannot be read (every name then shows as a marked placeholder)."""
    try:
        text = existing.read_text(encoding="utf-8-sig") if existing is not None else planned
        doc = json.loads(text)
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def has_token(doc: dict, path: str) -> bool:
    node: object = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, dict) and "$value" in node


def token_ref(doc: dict, candidates: Tuple[str, ...], what: str) -> str:
    """The first candidate token the project has, as `path`, else a clearly marked placeholder."""
    for path in candidates:
        if has_token(doc, path):
            return f"`{path}`"
    return MISSING_TOKEN.format(what=what)


def group_refs(doc: dict, group: str, limit: int, what: str) -> str:
    """The first tokens of a group (`shadow.card`, `shadow.popover`), or a marked placeholder."""
    node = doc.get(group) if isinstance(doc.get(group), dict) else {}
    names = [k for k, v in node.items() if not k.startswith("$") and isinstance(v, dict) and "$value" in v][:limit]
    return ", ".join(f"`{group}.{n}`" for n in names) if names else MISSING_TOKEN.format(what=what)


def token_names(doc: dict) -> Dict[str, str]:
    """The token names components.md and design.md quote, taken from the project's tokens (live test 2, B15: never a
    token the project does not have)."""
    refs = {
        "TOK_COLOR_PRIMARY": token_ref(doc, ("color.primary",), "the primary colour"),
        "TOK_TYPE_LABEL": token_ref(doc, ("typography.sm", "typography.label", "typography.body"), "a label text style"),
        "TOK_RADIUS_CONTROL": token_ref(doc, ("radius.md", "radius.sm"), "a control radius"),
        "TOK_RADIUS_CARD": token_ref(doc, ("radius.lg", "radius.md"), "a card radius"),
        "TOK_SHADOW_CARD": token_ref(doc, ("shadow.card", "shadow.sm", "shadow.raised"), "a card shadow"),
        "TOK_TYPE_TITLE": token_ref(doc, ("typography.h3", "typography.h2", "typography.title"), "a page title style"),
        "TOK_MOTION_FAST": token_ref(doc, ("motion.duration.fast",), "a short duration"),
        "TOK_SPACING": group_refs(doc, "spacing", 2, "the spacing steps"),
        "TOK_SHADOWS": group_refs(doc, "shadow", 4, "the elevation steps"),
    }
    found = [v for k, v in refs.items() if k in ("TOK_COLOR_PRIMARY", "TOK_TYPE_LABEL", "TOK_RADIUS_CONTROL",
                                                  "TOK_MOTION_FAST") and not v.startswith("`<")]
    refs["TOK_EXAMPLES"] = ", ".join(found) if found else "`color.<name>`, `radius.<name>`"
    return refs


# ---------------------------------------------------------------- rendering


def render(text: str, values: Dict[str, str], where: str, json_mode: bool = False) -> str:
    text = text.replace("\r\n", "\n").lstrip("﻿")

    def sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in values:
            raise ScaffoldError(f"{where} uses the unknown placeholder {m.group(0)}",
                                "restore the template from the Plumb plugin (assets/skill/)")
        value = values[key]
        if json_mode and key not in RAW_JSON_SLOTS:
            return json.dumps(value, ensure_ascii=False)[1:-1]
        return value

    return SLOT.sub(sub, text)


def read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ScaffoldError(f"cannot read the Plumb template {path} ({exc})",
                            "reinstall or update the Plumb plugin: ask the user and wait for their decision") from None


# ---------------------------------------------------------------- the plan


class Item:
    def __init__(self, dest: Path, content: str, owner: str) -> None:
        self.dest, self.content, self.owner = dest, content, owner  # owner: "P" always written, "Y" only when absent


def build_plan(args: argparse.Namespace, root: Path, skill_rel: str, docs: str, name: str, slug: str,
               platforms: List[str], answers: dict) -> List[Item]:
    values, extras, _ = resolve_answers(answers, name, platforms)
    values.update(platform_values(platforms, args.styling))
    # The interpreter init detected; else python on Windows (python.org with PATH, the Store and conda all have it; the
    # py launcher only comes with python.org) and python3 elsewhere.
    python_default = "python" if os.name == "nt" else "python3"
    values["PYTHON"] = str(answers.get("python") or python_default)
    values["RESET_PALETTE"] = json.dumps(resolve_reset_palette(answers, args.styling, platforms, root, skill_rel))
    values["DATE"] = datetime.date.today().isoformat()
    values.update({
        "NAME": name, "NAME_YAML": name.replace("\\", "\\\\").replace('"', '\\"'), "SLUG": slug,
        "SKILL_NAME": skill_rel.rsplit("/", 1)[-1], "SKILL_DIR": skill_rel + "/", "DOCS_DIR": docs,
        "THEME_NAME": pascal(slug),
        "ICONS_JSON": json.dumps(extras["icons"], indent=2, ensure_ascii=False).replace("\n", "\n  "),
        "COPIES_JSON": json.dumps(extras["copies"], ensure_ascii=False),
    })
    skill = root / skill_rel
    src = SKILL_SRC
    plan: List[Item] = []
    tokens_dir = skill / "assets/tokens"
    existing = sorted(tokens_dir.glob("*.tokens.json")) if tokens_dir.is_dir() else []
    tokens_text = render(read_source(src / "assets/tokens/tokens.json.tmpl"), values, "assets/tokens/tokens.json.tmpl",
                         json_mode=True)
    values.update(token_names(project_tokens(existing[0] if existing else None, tokens_text)))

    # [P] plugin-owned
    for script in sorted((src / "scripts").glob("*.py")):
        plan.append(Item(skill / "scripts" / script.name, read_source(script), "P"))
    tpl_dir = src / "templates"
    for tpl in sorted(p for p in tpl_dir.iterdir() if p.is_file()):
        plan.append(Item(skill / "templates" / tpl.name, read_source(tpl), "P"))
    plan.append(Item(skill / "assets/platforms/README.md", read_source(src / "assets/platforms/README.md"), "P"))

    # [Y] yours
    def y(src_rel: str, dest_rel: str, json_mode: bool = False) -> None:
        plan.append(Item(skill / dest_rel, render(read_source(src / src_rel), values, src_rel, json_mode), "Y"))

    y("SKILL.md.tmpl", "SKILL.md")
    y("design.md.tmpl", "design.md")
    token_name = existing[0].name if existing else f"{slug}.tokens.json"
    plan.append(Item(skill / f"assets/tokens/{token_name}", tokens_text, "Y"))
    y("assets/icons/icon-map.json.tmpl", "assets/icons/icon-map.json", json_mode=True)
    plan.append(Item(skill / "assets/platforms/web/tokens.css.template",
                     read_source(src / f"assets/platforms/web/tokens.css.template.{args.styling}"), "Y"))
    for ref in ("components", "inventory", "ux", "accessibility", "motion", "vocabulary", "dark-mode", "fidelity"):
        y(f"references/{ref}.md.tmpl", f"references/{ref}.md")
    if "web" in platforms:
        for ref in ("stack", "components", "ux-guidelines", "dark-mode"):
            y(f"references/web/{ref}.md.tmpl", f"references/web/{ref}.md")
    if "ios" in platforms or "android" in platforms:
        for ref in ("README", "components"):
            y(f"references/mobile/{ref}.md.tmpl", f"references/mobile/{ref}.md")
    if "ios" in platforms:
        for ref in ("ios", "components"):
            y(f"references/mobile/ios/{ref}.md.tmpl", f"references/mobile/ios/{ref}.md")
    if "android" in platforms:
        for ref in ("android", "components"):
            y(f"references/mobile/android/{ref}.md.tmpl", f"references/mobile/android/{ref}.md")

    # PLUMB.md, the decision log, the screens folder
    plumb_values = plumb_md_values(platforms, args.styling, docs, skill_rel, name, answers, values, root)
    plan.append(Item(root / "PLUMB.md", render(read_source(TEMPLATES_SRC / "PLUMB.md"), plumb_values, "templates/PLUMB.md"), "Y"))
    entry = read_source(TEMPLATES_SRC / "decision-entry.md").strip()
    log = (f"# Design decisions\n\nPlumb's design decision log for {name}. Append-only: one entry per decision, "
           f"each with a collision-free id.\n\nEntry format:\n\n```markdown\n{entry}\n```\n")
    plan.append(Item(root / docs / "decisions.md", log, "Y"))
    if not (root / docs / "prototype/screens").exists():
        plan.append(Item(root / docs / "prototype/screens/.gitkeep", "", "Y"))
    return plan


BLOCK_MARK = "/* plumb:start"


def copy_notes(root: Path, answers: dict, dry_run: bool) -> None:
    """One note per web copy that already exists with the project's own content: the tokens build will add Plumb's
    marked block to it (and keep the rest), so the person can be shown that before the first build."""
    for copy in answers.get("web_copies") or []:
        rel = safe_rel(copy) if isinstance(copy, str) else None
        path = root / rel if rel else None
        if path is None or not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        head = "\n".join(text.splitlines()[:5])
        if not text.strip() or BLOCK_MARK in text or ("GENERATED" in head and "build-tokens.py" in head):
            continue
        print(f"note: {rel} already exists with your own CSS: the tokens build (build-tokens.py) "
              f"{'would add' if dry_run else 'adds'} Plumb's block (/* plumb:start ... */ to /* plumb:end */) near its "
              f"top, after its @import lines, and keeps every other line as it is; only the block is Plumb's")


def check_blockers(root: Path, plan: List[Item]) -> None:
    for item in plan:
        parts = item.dest.relative_to(root).parts
        probe = root
        for part in parts[:-1]:
            probe = probe / part
            if probe.exists() and not probe.is_dir():
                raise ScaffoldError(f"{probe.relative_to(root).as_posix()} is a file, so {item.dest.relative_to(root).as_posix()} cannot be written",
                                    f"move or rename {probe.relative_to(root).as_posix()}, then run the scaffold again")
        if item.dest.is_dir():
            raise ScaffoldError(f"{item.dest.relative_to(root).as_posix()} is a folder where a file belongs",
                                "move that folder away, then run the scaffold again")


def confirm_token(root: Path, args: argparse.Namespace, skill_rel: str, docs: str, platforms: List[str],
                  answers: dict, plan: List[Item]) -> str:
    """The token the dry run prints and the real run must be given (--confirm): a hash of the project, the arguments,
    the answers and the file list with what happens to each file (written, or kept), so it fits only the list the
    person saw and approved."""
    listing = [[item.dest.relative_to(root).as_posix(),
                "skip" if item.owner == "Y" and item.dest.exists() else "write"] for item in plan]
    data = {"root": root.as_posix(), "name": " ".join(args.name.split()), "skill_dir": skill_rel, "docs_dir": docs,
            "platforms": platforms, "styling": args.styling, "answers": answers, "files": listing}
    text = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def check_confirm(given: Optional[str], token: str) -> None:
    """The real run needs the dry run's token for this exact command, answers and file list."""
    ask = ("ask the user: show them the file list from the same command with --dry-run (it writes nothing), and after "
           "their OK run the same command without --dry-run, plus --confirm <token> exactly as the dry run printed it")
    if not given:
        raise ScaffoldError("the scaffold writes into the project only after the user approved the dry-run list "
                            "(no --confirm token given)", ask)
    if given.strip() != token:
        raise ScaffoldError(f"--confirm {given.strip()} does not fit this command: the answers, the arguments or the "
                            f"files changed since the dry run (or it is another run's token)", ask)


_CHECK_IGNORE = re.compile(r"^(?P<source>.*?):(?P<line>\d+):(?P<pattern>.*)$")


def parse_check_ignore(line: str) -> Optional[Tuple[str, str, str, str]]:
    """One `git check-ignore -v` line, `<source>:<line>:<pattern>\\t<path>`, as (source, line, pattern, path); None
    when it is not one. Split on the first tab; the source may hold a drive colon (`C:/Users/…/ignore` on Windows) and
    the pattern may hold colons, so the line number is the first `:<digits>:` after the source. A quoted path (git
    quotes unusual names) loses its quotes."""
    info, tab, path = line.partition("\t")
    m = _CHECK_IGNORE.match(info)
    if not tab or not m:
        return None
    path = path.strip()
    if len(path) >= 2 and path[0] == path[-1] == '"':
        path = path[1:-1]
    return m.group("source"), m.group("line"), m.group("pattern"), path


class Ignored(NamedTuple):
    shown: str    # the design-system path as shown (a folder ends in /)
    pattern: str  # the pattern that ignores it
    source: str   # where that pattern is: a .gitignore, .git/info/exclude, or the global excludes file
    line: str


class Unignore(NamedTuple):
    pattern: str
    replace: bool          # True: the pattern's line is replaced by `lines`; False: `lines` go right after it
    lines: List[str]
    override: List[str]    # lines for the repo's own .gitignore that win over a pattern in another file


def _source_kind(source: str) -> str:
    src = source.replace("\\", "/")
    if src == ".git/info/exclude" or src.endswith("/.git/info/exclude"):
        return "exclude"
    if not re.match(r"^(?:[A-Za-z]:)?/", src) and (src == ".gitignore" or src.endswith("/.gitignore")):
        return "gitignore"
    return "global"


def unignore_fix(shown: str, pattern: str, source: str) -> Unignore:
    """The edit that makes git keep `shown`, for the pattern's shape. git never looks inside an excluded folder, so a
    folder pattern above the path (.claude/) becomes .claude/* plus a negation for the next folder; .claude/** needs
    the next folder and everything in it negated; .claude/* needs only the next folder. Anything else gets a negation
    of the path itself. `override`: the same result from the repo's own .gitignore, which wins over .git/info/exclude
    and the global excludes file (re-include the folder, ignore its contents, keep the next folder)."""
    path = shown.rstrip("/")
    pat = pattern.strip().lstrip("/").rstrip("/")

    def under(base: str) -> Optional[str]:
        if base and not any(c in base for c in "*?[") and path.startswith(base + "/"):
            return path[len(base) + 1:].split("/")[0]
        return None

    if pat.endswith("/**") and under(pat[:-3]):
        base = pat[:-3]
        nxt = under(base)
        lines = [f"!{base}/{nxt}/", f"!{base}/{nxt}/**"]
        return Unignore(pattern, False, lines, lines)
    if pat.endswith("/*") and under(pat[:-2]):
        base = pat[:-2]
        lines = [f"!{base}/{under(base)}/"]
        return Unignore(pattern, False, lines, lines)
    nxt = under(pat)
    if nxt:
        return Unignore(pattern, True, [f"{pat}/*", f"!{pat}/{nxt}/"], [f"!{pat}/", f"{pat}/*", f"!{pat}/{nxt}/"])
    comps = path.split("/")
    if pat and "/" not in pat and not any(c in pat for c in "*?[") and pat in comps:
        k = comps.index(pat)  # a name with no folder in front (skills/) matches at any depth: re-include the folder
        if k < len(comps) - 1 or shown.endswith("/"):  # it hit, anchored at the project root
            anchored = "!/" + "/".join(comps[:k + 1]) + "/"
            return Unignore(pattern, False, [anchored], [anchored])
    return Unignore(pattern, False, [f"!{shown}"], [f"!{shown}"])


def _quoted(lines: List[str]) -> str:
    q = [f'"{line}"' for line in lines]
    return q[0] if len(q) == 1 else ", ".join(q[:-1]) + " and " + q[-1]


def unignore_hint(item: Ignored) -> str:
    """The exact edit, in the file the pattern is really in (check-ignore -v names it)."""
    fix = unignore_fix(item.shown, item.pattern, item.source)
    kind = _source_kind(item.source)
    where = {"gitignore": f"in {item.source}", "exclude": "in .git/info/exclude",
             "global": f"in your global git excludes file {item.source} (line {item.line}; it applies to every repo)"}[kind]
    if fix.replace:
        text = f'{where} replace the line "{item.pattern}" with "{fix.lines[0]}" and add {_quoted(fix.lines[1:])} after it'
    else:
        text = f'{where} add {_quoted(fix.lines)} after the line "{item.pattern}"'
        if fix.lines == [f"!{item.shown}"]:
            text += " (or remove that line)"
    if kind == "global":
        text += f", or keep that file and add {_quoted(fix.override)} to this repo's .gitignore"
    return text


def ignored_by_git(root: Path, skill_rel: str, docs: str) -> List[Ignored]:
    """The design-system paths git would never commit, for the skill folder, PLUMB.md and the docs folder
    (`git check-ignore -v`, a file inside each folder, so a folder that does not exist yet is checked too), with the
    pattern and the file it is in (a .gitignore, .git/info/exclude or the global excludes file). Run with the plugin's
    hardened git call (no project hooks, filters or pagers; git found on PATH outside the project). [] outside a git
    repo, without git, or when nothing is ignored."""
    audit = load_plugin_audit()
    if audit is None:
        return []
    probes = {f"{skill_rel}/SKILL.md": f"{skill_rel}/", "PLUMB.md": "PLUMB.md", f"{docs}/decisions.md": f"{docs}/"}
    try:
        out = audit._git(root, "check-ignore", "-v", "--", *probes)
    except Exception:  # noqa: BLE001 - the check is advice; it never stops a scaffold
        return []
    found: List[Ignored] = []
    for raw_line in (out or "").splitlines():
        parsed = parse_check_ignore(raw_line)
        if parsed is None:
            continue
        source, number, pattern, path = parsed
        if pattern.startswith("!") or path not in probes:
            continue  # a negation pattern matched: the path is kept
        found.append(Ignored(probes[path], pattern, source, number))
    return found


def ignore_lines(found: List[Ignored], what: str) -> List[str]:
    """`<what>: <path> is git-ignored by <pattern> ...` and the ask-the-user line, for each ignored path."""
    out = []
    for item in found:
        out.append(f"{what}: {item.shown} is git-ignored by {item.pattern} ({item.source} line {item.line}) \u2014 the "
                   f"design system would never be committed, so teammates and CI would not get it")
        out.append(f"fix: ask the user: un-ignore it ({unignore_hint(item)}), or choose another location for it")
    return out


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def execute(root: Path, plan: List[Item], dry_run: bool) -> Tuple[int, int]:
    wrote = kept = 0
    for item in plan:
        rel = item.dest.relative_to(root).as_posix()
        if item.owner == "Y" and item.dest.exists():
            print(f"skip: {rel} (yours, kept)")
            kept += 1
            continue
        if dry_run:
            print(f"would write: {rel}")
        else:
            try:
                write_file(item.dest, item.content)
            except OSError as exc:
                raise ScaffoldError(f"cannot write {rel} ({exc.strerror or exc})",
                                    "check the folder is writable and no file blocks the path, then run the scaffold again") from None
            print(f"wrote: {rel}")
        wrote += 1
    return wrote, kept


# ---------------------------------------------------------------- relocate and verify

AGENT_FILES = ("AGENTS.md", "CLAUDE.md")
DEFAULT_SKILL_PLACES = (".claude/skills", ".github/skills")
DESIGN_LINE = re.compile(r"^Design system:\s*`?([^`\n]*?)`?\s*(?:\(.*\))?\s*$", re.M)


def is_plumb_skill(folder: Path) -> bool:
    tokens = folder / "assets" / "tokens"
    return (folder / "SKILL.md").is_file() and tokens.is_dir() and any(tokens.glob("*.tokens.json"))


def read_keep(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def path_pattern(rel: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![\w./-])" + re.escape(rel.rstrip("/")) + r"/")


def is_plumb_row(line: str) -> bool:
    return line.lstrip().startswith("|") and "SKILL.md" in line and "/plumb:prototype" in line


def edit_lines(text: str, pattern: "re.Pattern[str]", new: str, only: "Optional[object]" = None) -> Tuple[str, int]:
    """Replace the old path in the lines `only` accepts (all lines when None); returns (text, lines changed)."""
    out, count = [], 0
    for line in text.splitlines(keepends=True):
        if (only is None or only(line)) and pattern.search(line):  # type: ignore[operator]
            line = pattern.sub(lambda _m: new + "/", line)
            count += 1
        out.append(line)
    return "".join(out), count


def relocate(root: Path, src_arg: str, dst_arg: str, dry_run: bool) -> int:
    src_rel = project_rel(src_arg, root, "--relocate FROM", ".claude/skills/old-design-system")
    dst_rel = project_rel(dst_arg, root, "--relocate TO", ".github/skills/demo-design-system")
    src, dst = root / src_rel, root / dst_rel
    if src_rel == dst_rel:
        raise ScaffoldError("FROM and TO are the same folder", "give a different TO, e.g. --relocate FROM .github/skills/demo-design-system")
    if not src.is_dir() or not is_plumb_skill(src):
        raise ScaffoldError(f"{src_rel} is not a Plumb design-system skill (it needs SKILL.md and assets/tokens/*.tokens.json)",
                            "pass the skill folder as FROM; `scaffold.py --verify --project-root <root>` finds it")
    if dst_rel.startswith(src_rel + "/"):
        raise ScaffoldError(f"TO {dst_rel} is inside FROM {src_rel}", "choose a TO outside the skill folder")
    if dst.exists() and (not dst.is_dir() or any(dst.iterdir())):
        raise ScaffoldError(f"{dst_rel} already exists and is not empty", f"choose another TO, or move {dst_rel} away first")
    for parent in dst.parents:
        if parent == root:
            break
        if parent.exists() and not parent.is_dir():
            raise ScaffoldError(f"{parent.relative_to(root).as_posix()} is a file, so {dst_rel} cannot be created",
                                "choose another TO")
    pattern = path_pattern(src_rel)
    edits: List[Tuple[Path, str, str]] = []  # (file, new text, label)
    plumb_md = root / "PLUMB.md"
    if plumb_md.is_file():
        new, n = edit_lines(read_keep(plumb_md), pattern, dst_rel)
        if n:
            edits.append((plumb_md, new, f"PLUMB.md ({n} line{'s' if n != 1 else ''})"))
    else:
        print("note: no PLUMB.md in the project root, nothing to update there")
    for name in AGENT_FILES:
        path = root / name
        if path.is_file():
            new, n = edit_lines(read_keep(path), pattern, dst_rel, is_plumb_row)
            if n:
                edits.append((path, new, f"{name} (the Plumb row)"))
    makefile = find_makefile(root)
    if makefile is not None:
        new, n = edit_lines(read_keep(makefile), pattern, dst_rel)
        if n:
            edits.append((makefile, new, f"{makefile.name} ({n} line{'s' if n != 1 else ''})"))
    tokens = sorted((src / "assets/tokens").glob("*.tokens.json"))[0]
    try:
        copies = json.loads(tokens.read_text(encoding="utf-8")).get("$extensions", {}).get("plumb", {}).get("web", {}).get("copies", [])
    except (OSError, ValueError, AttributeError):
        copies = []
    for copy in copies if isinstance(copies, list) else []:
        rel = safe_rel(copy) if isinstance(copy, str) else None
        if rel is None or not (root / rel).parent.is_dir():
            print(f"note: web copy {copy!r} does not resolve inside the project; fix $extensions.plumb.web.copies in {tokens.name}")
    if dry_run:
        print(f"would move: {src_rel} -> {dst_rel}")
        for path, _, label in edits:
            print(f"would update: {label}")
        print(f"would run: {dst_rel}/scripts/build-tokens.py --check")
        print("dry run: nothing written")
        return 0
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_dir():
            dst.rmdir()
        os.replace(str(src), str(dst))
    except OSError as exc:
        raise ScaffoldError(f"cannot move {src_rel} to {dst_rel} ({exc.strerror or exc})",
                            "close programs using the folder, then run the same command again") from None
    print(f"moved: {src_rel} -> {dst_rel}")
    for path, new, label in edits:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
        print(f"updated: {label}")
    return check_moved(root, dst_rel)


def run_tokens(root: Path, dst_rel: str, *flags: str) -> "Tuple[int, str]":
    script = root / dst_rel / "scripts" / "build-tokens.py"
    if not script.is_file():
        return 2, f"{dst_rel}/scripts/build-tokens.py is missing"
    r = subprocess.run([sys.executable, str(script), *flags], capture_output=True, text=True, encoding="utf-8",
                       cwd=str(root))
    return r.returncode, (r.stdout + r.stderr).strip()


def check_moved(root: Path, dst_rel: str) -> int:
    code, out = run_tokens(root, dst_rel, "--check")
    if code == 0:
        print("check: ok (build-tokens.py --check)")
        return 0
    if code == 1:
        print("check: stale after the move (the generated files name the old path); regenerating once")
        code, out = run_tokens(root, dst_rel)
        if code == 0:
            code, out = run_tokens(root, dst_rel, "--check")
            if code == 0:
                print("check: ok after regenerating")
                return 0
    print(f"check: failed ({out.splitlines()[0] if out else 'no output'})")
    print(f"error: the moved skill does not pass build-tokens.py --check\nfix: python {dst_rel}/scripts/build-tokens.py", file=sys.stderr)
    return 1


def find_skills(root: Path) -> List[str]:
    found: List[str] = []
    for place in DEFAULT_SKILL_PLACES:
        base = root / place
        if base.is_dir():
            found += [f"{place}/{d.name}" for d in sorted(base.glob("*-design-system")) if d.is_dir() and is_plumb_skill(d)]
    return found


MAKE_REF = re.compile(r"[(`]make ([A-Za-z0-9_.-]+)")
MAKEFILES = ("Makefile", "makefile", "GNUmakefile")
# A rule line: targets, then `:` or `::`, never `:=` / `::=` (assignments); recipe lines start with a tab.
MAKE_RULE = re.compile(r"^([A-Za-z0-9_.%/-][A-Za-z0-9_.%/ \t-]*?)[ \t]*::?(?!=)", re.M)
MAKE_INCLUDE = re.compile(r"^-?(?:include|sinclude)[ \t]+(.+)$", re.M)
ROLE_LINE = re.compile(r"^Role:\s*([a-z]+)", re.M)


def find_makefile(root: Path) -> Optional[Path]:
    """The project's Makefile (GNU make's names), or None."""
    for name in MAKEFILES:
        path = root / name
        if path.is_file():
            return path
    return None


def makefile_targets(root: Path) -> "Tuple[Optional[set], List[str]]":
    """(the targets the project's Makefile defines, the files it includes); (None, []) when there is no Makefile."""
    path = find_makefile(root)
    if path is None:
        return None, []
    text = read_keep(path)
    targets = {t for m in MAKE_RULE.finditer(text) for t in m.group(1).split() if not t.startswith(".")}
    includes = [f for m in MAKE_INCLUDE.finditer(text) for f in m.group(1).split()]
    return targets, includes


def check_make_targets(text: str, root: Path) -> "Tuple[Optional[str], Optional[str], Optional[str]]":
    """PLUMB.md must not send anyone to a `make` target that does not exist (the user may have declined the Makefile).
    Returns (ok, note, problem) texts for verify to print; at most one is set. Prints nothing."""
    named = list(dict.fromkeys(MAKE_REF.findall(text)))
    if not named:
        return None, None, None
    targets, includes = makefile_targets(root)
    if targets is None:
        return None, None, f"PLUMB.md names {', '.join(f'`make {t}`' for t in named)} but there is no Makefile"
    missing = [t for t in named if t not in targets]
    if not missing:
        return "PLUMB.md's make targets exist in the Makefile", None, None
    listed = ", ".join(f"`make {t}`" for t in missing)
    if includes:
        return None, (f"PLUMB.md names {listed}; the Makefile does not define it but includes {', '.join(includes)} "
                      "(check the target is there)"), None
    return None, None, (f"PLUMB.md names {listed} but the Makefile has no {', '.join(missing)} "
                        f"target{'s' if len(missing) != 1 else ''}")


def check_routes(keys: dict, root: Path) -> List[Tuple[str, str]]:
    """PLUMB.md `Routes:`: each recorded page root (a folder, or a router file or glob) exists. Not recorded is a note
    (a project set up before 1.0.0's Routes line keeps working: the route checks stay off until /plumb:init records
    them). Returns (ok | note | problem, text) lines."""
    core = load_plumb_core()
    roots, problems = core.parse_routes(keys.get("Routes"))
    out: List[Tuple[str, str]] = [("problem", p) for p in problems]
    if roots is None:
        out.append(("note", core.ROUTES_NOT_RECORDED + "; until then the prototype-first check and route-not-prototyped "
                    "are off"))
        return out
    if not roots and not problems:
        out.append(("ok", "Routes: none (no page routes to check)"))
    for path, kind in roots:
        router = kind in core.ROUTER_KINDS
        if router and any(c in path for c in core.GLOB_CHARS):
            rx = core.glob_rx(path)
            fixed = root / core.glob_base(path)
            found = fixed.is_dir() and any(rx.match(f.relative_to(root).as_posix()) for f in fixed.rglob("*") if f.is_file())
        else:
            found = (root / path).is_file() if router else (root / path).is_dir()
        if found:
            out.append(("ok", f"Routes: {path} ({kind}) exists"))
        else:
            out.append(("problem", f"Routes: {path} ({kind}) does not exist in the project"))
    if any(kind == "problem" for kind, _t in out):
        out.append(("fix", "ask the user: correct Routes: in PLUMB.md to the folders (or router files) that "
                    "hold the app's pages, each as <path> (<kind>)"))
    return out


UI_FILES_SCAN_MAX = 50000


def check_ui_files(keys: dict, root: Path, skill_rel: str) -> List[Tuple[str, str]]:
    """PLUMB.md `UI files:` must cover at least one file (globs from the project root, as the audit reads them): a
    value that matches 0 files switches the audit and the checks off without a word. A folder glob that matches
    nothing is a note."""
    value = str(keys.get("UI files", "") or "").strip()
    if not value:
        return []
    core = load_plumb_core()
    left, _, right = value.partition("·")
    items = core.split_globs(left) + core.split_globs(right)  # a brace glob (*.{tsx,css}) stays whole
    dirs = [i for i in items if "/" in i]
    names = [i for i in items if "/" not in i]
    dir_rx = [(d, core.glob_rx(d)) for d in dirs]
    name_rx = [core.glob_rx(n) for n in names]
    used = {d: 0 for d in dirs}
    total = seen = sources = 0
    docs = (root / str(keys.get("docs_dir") or "docs/design")).resolve()
    skill = (root / skill_rel).resolve() if skill_rel else None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in core.SKIP_DIRS and not d.startswith(".git"))
        if Path(dirpath).resolve() in (skill, docs):
            dirnames[:] = []
            continue
        for fn in filenames:
            seen += 1
            if seen > UI_FILES_SCAN_MAX:
                break
            if core.source_ext(fn) is None:
                continue
            sources += 1
            if name_rx and not any(rx.match(fn) for rx in name_rx):
                continue
            rel = (Path(dirpath) / fn).relative_to(root).as_posix()
            hit = [d for d, rx in dir_rx if rx.match(rel)]
            for d in hit:
                used[d] += 1
            if hit or not dirs:
                total += 1
    if total == 0 and not sources:
        return [("note", f"PLUMB.md UI files: {value} matches no file yet (the project has no UI code yet)")]
    if total == 0:
        return [("problem", f"PLUMB.md UI files: {value} matches 0 files (globs are read from the project root, e.g. "
                            f"frontend/src/** for a UI package in frontend/), so the audit and the checks see nothing"),
                ("fix", "ask the user: correct UI files: in PLUMB.md to the folders that hold the UI code")]
    out = [("ok", f"PLUMB.md UI files: matches {total} file{'s' if total != 1 else ''}")]
    out += [("note", f"UI files: {d} matches 0 files") for d, n in used.items() if n == 0]
    return out


def verify(root: Path) -> int:
    problems = 0

    def problem(text: str) -> None:
        nonlocal problems
        problems += 1
        print(f"problem: {text}")

    plumb_md = root / "PLUMB.md"
    if not plumb_md.is_file():
        print("problem: no PLUMB.md in the project root")
        found = find_skills(root)
        if found:
            print(f"fix: ask the user to run /plumb:init (a design-system skill exists at {found[0]})")
        else:
            print("fix: run /plumb:init, then /plumb:create or /plumb:extract")
        return 1
    plumb_text = read_keep(plumb_md)
    role = ROLE_LINE.search(plumb_text)
    linked = bool(role and role.group(1) == "linked")
    m = DESIGN_LINE.search(plumb_text)
    skill_rel = ""
    if not m or not m.group(1).strip():
        problem("PLUMB.md has no `Design system:` line")
    else:
        skill_rel = m.group(1).strip().replace("\\", "/").rstrip("/")
        skill_dir = (root / skill_rel)
        if skill_dir.is_dir() and is_plumb_skill(skill_dir):
            print(f"ok: PLUMB.md names {skill_rel}/ and it is a design-system skill")
        else:
            problem(f"PLUMB.md names {skill_rel}/ but no design-system skill is there")
            found = [f for f in find_skills(root) if f != skill_rel]
            if found:
                print(f"found: a design-system skill at {found[0]}")
                print(f"fix: python {Path(__file__).resolve().as_posix()} --relocate {found[0]} {skill_rel} "
                      f"--project-root {root.as_posix()}   (or edit the Design system line in PLUMB.md to {found[0]}/)")
            else:
                print("fix: run /plumb:create or /plumb:extract to make the skill, or correct the Design system line in PLUMB.md")
            skill_rel = ""
    if skill_rel:
        marker = skill_rel + "/"
        rows = 0
        for name in AGENT_FILES:
            path = root / name
            if not path.is_file():
                continue
            for line in read_keep(path).splitlines():
                if is_plumb_row(line):
                    rows += 1
                    if marker in line.replace("\\", "/"):
                        print(f"ok: {name} row points at {marker}SKILL.md")
                    else:
                        problem(f"the Plumb row in {name} does not name {marker}SKILL.md")
                        print(f"fix: change the path in that row to {marker}SKILL.md")
        if not rows:
            print("note: no Plumb row in AGENTS.md or CLAUDE.md (/plumb:init step 4 asks the user whether to add it)")
        makefile = find_makefile(root)
        lines = [l for l in read_keep(makefile).splitlines() if "build-tokens.py" in l or "audit.py" in l] if makefile else []
        if not lines and not linked:  # a linked repo gets the row and the checks only, never Makefile targets
            print("note: no Plumb targets in a Makefile (/plumb:init step 4 asks the user whether to add them)")
        for line in lines:
            if marker in line.replace("\\", "/"):
                print(f"ok: {makefile.name} line points at {marker}")  # type: ignore[union-attr]
            else:
                problem(f"{makefile.name} line {line.strip()!r} does not name {marker}")  # type: ignore[union-attr]
                print(f"fix: change its path to {marker}scripts/...")
        tokens = sorted((root / skill_rel / "assets/tokens").glob("*.tokens.json"))
        try:
            copies = json.loads(tokens[0].read_text(encoding="utf-8"))["$extensions"]["plumb"]["web"]["copies"]
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            copies = []
        if linked and copies:
            print("note: web copies belong to the home repo (Role: linked); check them there")
            copies = []
        for copy in copies if isinstance(copies, list) else []:
            rel = safe_rel(copy) if isinstance(copy, str) else None
            if rel is None:
                problem(f"web copy {copy!r} is not a project-relative path")
                print(f"fix: edit $extensions.plumb.web.copies in {tokens[0].name}")
            elif not (root / rel).parent.is_dir():
                problem(f"web copy {rel}: its folder does not exist")
                print(f"fix: edit $extensions.plumb.web.copies in {tokens[0].name}, or create the folder")
            elif not (root / rel).is_file():
                print(f"note: web copy {rel} is not written yet (run the tokens build)")
            else:
                print(f"ok: web copy {rel} resolves")
    keys = load_plumb_core().read_plumb_md(plumb_md)
    docs_rel = str(keys.get("docs_dir") or "docs/design").replace("\\", "/").strip("/") or "docs/design"
    if skill_rel and not skill_rel.startswith("../"):
        for line in ignore_lines(ignored_by_git(root, skill_rel, docs_rel), "problem"):
            if line.startswith("problem: "):
                problem(line[len("problem: "):])
            else:
                print(line)
    for kind, text in check_routes(keys, root) + check_ui_files(keys, root, skill_rel):
        if kind == "problem":
            problem(text)
        else:
            print(f"{kind}: {text}")
    make_ok, make_note, make_problem = check_make_targets(plumb_text, root)
    if make_ok:
        print(f"ok: {make_ok}")
    if make_note:
        print(f"note: {make_note}")
    if make_problem:
        problem(make_problem)
        print("fix: ask the user: add the Plumb targets (templates/Makefile.snippet) to the Makefile, or change "
              "PLUMB.md's Commands lines to the direct commands (drop each \"(make ...)\")")
    print("verify: ok" if not problems else f"verify: {problems} problem{'s' if problems != 1 else ''}")
    return 0 if not problems else 1


# ---------------------------------------------------------------- command line
# ---------------------------------------------------------------- command line


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        print(f"error: {message}\nfix: run scaffold.py --help for the options", file=sys.stderr)
        raise SystemExit(2)


def parse(argv: Optional[List[str]]) -> argparse.Namespace:
    p = Parser(description="Lay the design-system skill into a project (Plumb).")
    p.add_argument("--project-root", required=True)
    p.add_argument("--name", help="the product's name")
    p.add_argument("--skill-dir", help="skill folder relative to the project root")
    p.add_argument("--platforms", help="comma separated: web, ios, android")
    p.add_argument("--styling", help="tailwind-v4, tailwind-v3 or css")
    p.add_argument("--relocate", nargs=2, metavar=("FROM", "TO"), help="move the skill folder and update every reference")
    p.add_argument("--verify", action="store_true", help="check PLUMB.md, AGENTS/CLAUDE, the Makefile and the copy targets")
    p.add_argument("--answers", help="answers.json (see the module docstring)")
    p.add_argument("--docs-dir", default="docs/design")
    p.add_argument("--dry-run", action="store_true", help="print what would be written, write nothing")
    p.add_argument("--confirm", metavar="TOKEN", help="the real run: the token the dry run printed")
    args = p.parse_args(argv)
    if args.relocate and args.verify:
        p.error("--relocate and --verify cannot be combined")
    if not args.relocate and not args.verify:
        for flag in ("name", "skill_dir", "platforms", "styling"):
            if getattr(args, flag) is None:
                p.error("the following arguments are required: --" + flag.replace("_", "-"))
    return args


def run(args: argparse.Namespace) -> int:
    root = Path(args.project_root)
    if not root.is_dir():
        raise ScaffoldError(f"the project root {args.project_root!r} is not a folder", "pass --project-root with the project's folder")
    root = root.resolve()
    if args.relocate:
        return relocate(root, args.relocate[0], args.relocate[1], args.dry_run)
    if args.verify:
        return verify(root)
    name = " ".join(args.name.split())
    if not name or not slugify(name) or re.search(r"[\x00-\x1f]", args.name.replace("\n", " ").replace("\t", " ")):
        raise ScaffoldError(f"the name {args.name!r} has no letters or digits to build a project id from",
                            "pass --name with the product's name, e.g. --name \"Acme Notes\"")
    platforms = parse_platforms(args.platforms)
    if args.styling not in STYLINGS:
        raise ScaffoldError(f"the styling {args.styling!r} is not one of {', '.join(STYLINGS)}",
                            f"pass --styling {STYLINGS[0]} (or tailwind-v3, css)")
    detect = load_detect()
    skill_rel = project_rel(args.skill_dir, root, "--skill-dir",
                            f".claude/skills/{detect.project_name(root)}-design-system")
    slug = detect.project_id(root, skill_rel)  # the same rule detect.py proposed the skill folder with
    docs = project_rel(args.docs_dir, root, "--docs-dir", "docs/design")
    answers = load_answers(args.answers)
    plan = build_plan(args, root, skill_rel, docs, name, slug, platforms, answers)
    check_blockers(root, plan)
    token = confirm_token(root, args, skill_rel, docs, platforms, answers, plan)
    if not args.dry_run:
        check_confirm(args.confirm, token)
    wrote, kept = execute(root, plan, args.dry_run)
    copy_notes(root, answers, args.dry_run)
    for line in ignore_lines(ignored_by_git(root, skill_rel, docs), "warning"):
        print(line)
    if args.dry_run:
        print(f"dry run: nothing written ({wrote} would be written, {kept} kept)")
        print(f"confirm: show the user this list; after their OK run the same command without --dry-run, plus "
              f"--confirm {token}")
    else:
        print(f"done: {wrote} written, {kept} kept")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    utf8_stdio()
    args = parse(argv)
    try:
        return run(args)
    except ScaffoldError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    utf8_stdio()
    sys.exit(main())
