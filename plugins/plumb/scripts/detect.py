#!/usr/bin/env python3
"""Plumb repo layout and stack detection (used by /plumb:init).

    detect.py --cwd PATH [--json]

Finds where the project and its UI live, so init can show "Plumb found: ..." and wait for the
user's confirmation. It only reads; it never writes anything.

Layouts: monorepo, mixed, frontend, backend, single (nothing recognised), parent (outside git, the folder has no
project markers but child folders do), new (outside git and empty, or only dotfiles: a new project starts here).
git is optional: outside a repo, a folder with project markers is itself the project root ("in_repo": false, with a
reason, so confidence is at most medium). A folder that holds other git repos is never a project root: it is a
parent, and "children" lists the project folders found under it (git repos and folders with markers, by path, up to
the scan depth). Outside git, "enclosing" names the nearest folder above with monorepo markers or a PLUMB.md (then
confidence is low: the project may be that folder). Detection is a first guess; the init skill confirms it.

UI files: each UI package has "files" (a count) and "ui_files" (the PLUMB.md `UI files:` value its stack needs, or
null when scaffold.py's platform default fits). Angular needs its own: the component templates, classes and styles in
its source folders (angular.json projects.*.sourceRoot, else src/: *.component.ts/.html/.scss/.css), the route configs
and the global stylesheet, never every .ts; when any component is named without the .component suffix (Angular 20,
alone or mixed, or an unpaired @Component class) every .ts/.html/.scss/.css there (a medium-confidence reason says so).
"proposal.ui_files" joins the packages' values, and is also set when web packages sit next to iOS or Android ones
(the web folders plus the mobile packages' folders, since the audit needs a file in a listed folder AND with a listed
name); null otherwise. An Angular package counts its templates plus the .ts/.scss/.css files that carry the
.component suffix or pair by name with a template or style, and unpaired @Component classes. A marker folder nested in
a package (src/index.html) counts for the nearest package, never for a UI package above a backend one.
SwiftUI sources (import SwiftUI) with no Package.swift or Xcode project are a UI package at the folder they share,
with low confidence.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

EXCLUDE = {
    "node_modules", ".git", "dist", "build", ".next", "Pods", "DerivedData", ".venv", "venv",
    "__pycache__", "target", ".turbo", ".nuxt", ".svelte-kit", ".gradle", ".idea", "coverage",
}
# Folders never searched for nested projects or repos: build output plus vendored and dependency code
# (a git checkout under vendor/ is a dependency of the project, not a project of its own).
NOT_PROJECTS = EXCLUDE | {"vendor", "vendors", "third_party", "third-party", "external", "externals", "out"}
MAX_DEPTH = 5
MAX_ENTRIES = 60000
UI_EXTS = {".tsx", ".jsx", ".vue", ".svelte", ".html", ".swift", ".kt"}
# Angular component files beyond the templates: classes and styles. A .ts/.scss/.css counts when its name carries the
# .component suffix or it pairs by name with a template or style in the same folder (Angular 20 names: app.ts +
# app.html), so services, main.ts, routes and specs are not counted.
ANGULAR_EXTS = (".ts", ".html", ".scss", ".css")
# PLUMB.md `UI files:` for an Angular package (its src/ folder): component templates, classes and styles, the route
# configs (the audit's route discovery) and the global stylesheet; never every .ts (services, guards, models).
ANGULAR_UI_NAMES = ("*.component.ts", "*.component.html", "*.component.scss", "*.component.css", "*.routes.ts",
                    "*routing.module.ts", "styles.scss", "styles.css")
# Angular 20 drops the .component suffix: no glob tells a component class from a service, so every source file counts.
ANGULAR_UI_NAMES_UNSUFFIXED = ("*.ts", "*.html", "*.scss", "*.css")
LONELY_TS_MAX = 400  # unpaired .ts files read for @Component( per package (Angular 20 inline-template components)
SWIFTUI_GUESS_REASON = ("SwiftUI sources (import SwiftUI) without Package.swift or an Xcode project: {path} is a guess "
                        "for the app folder")
MARKER_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "go.mod", "pom.xml", "build.gradle",
    "build.gradle.kts", "Cargo.toml", "Gemfile", "Package.swift", "index.html",
}
MONOREPO_FILES = ["pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json", "rush.json"]
FRAMEWORK_LABEL = {
    "next": "Next.js", "react": "React", "vue": "Vue", "svelte": "Svelte", "angular": "Angular",
    "html": "plain HTML", "swiftui": "SwiftUI", "uikit": "UIKit", "compose": "Jetpack Compose",
    "android-views": "Android Views",
    "react-native": "React Native",
}
STYLING_LABEL = {"tailwind-v4": "Tailwind v4", "tailwind-v3": "Tailwind v3", "css": "CSS", "native": "native styles"}
# PLUMB.md `UI files:` when the stack needs nothing special (scaffold.py writes the same; one source, here).
PLATFORM_UI_FILES = {"web": "app/**, src/**, components/** · *.tsx *.jsx *.vue *.svelte *.css", "ios": "*.swift",
                     "android": "*.kt"}
BLOCK_MARK = "/* plumb:start"


def default_ui_files(platforms: List[str]) -> str:
    """The platform default for PLUMB.md's `UI files:` (web when no platform is known yet)."""
    return " · ".join(PLATFORM_UI_FILES[p] for p in (platforms or ["web"]) if p in PLATFORM_UI_FILES)


def copy_state(root: Path, rel: str) -> Optional[str]:
    """What the tokens build will do to an existing web copy, for the placement block: None when the file does not
    exist (or is empty), else one line."""
    path = root / rel
    try:
        text = path.read_bytes().decode("utf-8", "replace") if path.is_file() else ""
    except OSError:
        return None
    if not text.strip():
        return None
    if BLOCK_MARK in text:
        return rel + " exists with Plumb's block: the build updates only the block; the rest stays yours"
    return rel + " exists: Plumb will add a marked block; the rest stays yours"


# Shared helpers live in the skill template: plugins/plumb/assets/skill/scripts/_plumb.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "assets" / "skill" / "scripts"))
from _plumb import PlumbError, read_plumb_md, utf8_stdio  # noqa: E402


def normalize_cwd(value: str) -> str:
    """Accept Windows-style separators handed to a POSIX shell (a path that does not exist as typed)."""
    if os.sep == "/" and "\\" in value and not Path(value).exists():
        return value.replace("\\", "/")
    return value


def read_small(path: Path, limit: int = 65536) -> str:
    try:
        with open(str(path), "rb") as fh:
            return fh.read(limit).decode("utf-8", "replace").lstrip("﻿")
    except OSError:
        return ""


# --- repo root -------------------------------------------------------------------------------


def find_root(cwd: Path) -> Tuple[Optional[Path], bool]:
    """Return (repo root or None, git_available)."""
    git_ok = True
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(cwd), capture_output=True,
            encoding="utf-8", timeout=10,
        )
        if p.returncode == 0 and p.stdout.strip():
            return Path(p.stdout.strip()), True
    except (FileNotFoundError, PermissionError):
        git_ok = False
    except (OSError, subprocess.SubprocessError):
        pass
    for d in [cwd] + list(cwd.parents):
        if (d / ".git").exists():
            return d, git_ok
    return None, git_ok


# --- scanning --------------------------------------------------------------------------------


class Scan:
    def __init__(self) -> None:
        self.dirs: Dict[str, List[str]] = {}  # rel dir -> entry names (only marker dirs)
        self.ui_files: Dict[str, int] = {}
        self.css: Dict[str, List[str]] = {}
        self.swift: Dict[str, List[str]] = {}
        self.angular_extra: Dict[str, int] = {}     # owner -> Angular component classes and styles (see ANGULAR_EXTS)
        self.component_suffix: Dict[str, int] = {}  # owner -> *.component.ts files (the pre-Angular-20 naming)
        self.loose_swift: List[str] = []            # .swift files outside every marker folder
        self.unsuffixed_paired: Dict[str, int] = {}  # owner -> unsuffixed .ts paired with a template or style
        self.lonely_ts: Dict[str, List[str]] = {}    # owner -> other unsuffixed .ts (up to LONELY_TS_MAX)


def _angular_extra(names: List[str]) -> Tuple[int, int, int, List[str]]:
    """Among one folder's file names (see ANGULAR_EXTS): (component classes and styles, *.component.ts files,
    unsuffixed .ts files paired with a template or style (Angular 20 names), the other unsuffixed .ts files: read later
    for @Component( when the package is Angular)."""
    stems: Dict[str, int] = {}
    files = []  # (name, ext, stem), lower-case ext and stem
    for n in names:
        low = n.lower()
        ext = os.path.splitext(low)[1]
        if low.endswith(".spec.ts") or ext not in ANGULAR_EXTS:
            continue
        stem = low[: -len(ext)]
        stems[stem] = stems.get(stem, 0) + 1
        files.append((n, ext, stem))
    extra = sum(1 for _, ext, stem in files
                if ext != ".html" and (stem.endswith(".component") or stems[stem] >= 2))
    suffixed = sum(1 for _, ext, stem in files if ext == ".ts" and stem.endswith(".component"))
    plain = [(n, stem) for n, ext, stem in files if ext == ".ts" and not stem.endswith(".component")]
    paired = sum(1 for _, stem in plain if stems[stem] >= 2)
    lonely = [n for n, stem in plain if stems[stem] < 2]
    return extra, suffixed, paired, lonely


def walk(root: Path, max_depth: int = MAX_DEPTH) -> Scan:
    scan = Scan()
    budget = [MAX_ENTRIES]

    def visit(path: Path, rel: str, depth: int, owner: Optional[str]) -> None:
        try:
            entries = list(os.scandir(str(path)))
        except OSError:
            return
        budget[0] -= len(entries)
        names = [e.name for e in entries]
        is_marker = any(n in MARKER_FILES or n.endswith(".xcodeproj") for n in names)
        own = rel if is_marker else owner
        if own is not None:
            files = []
            for e in entries:
                try:
                    if e.is_file(follow_symlinks=False):
                        files.append(e.name)
                except OSError:
                    continue
            extra, suffixed, paired, lonely = _angular_extra(files)
            scan.angular_extra[own] = scan.angular_extra.get(own, 0) + extra
            scan.component_suffix[own] = scan.component_suffix.get(own, 0) + suffixed
            scan.unsuffixed_paired[own] = scan.unsuffixed_paired.get(own, 0) + paired
            if lonely:
                lst = scan.lonely_ts.setdefault(own, [])
                lst.extend(n if rel == "." else rel + "/" + n for n in lonely if len(lst) < LONELY_TS_MAX)
        if is_marker:
            scan.dirs[rel] = names
            owner = rel
            scan.ui_files.setdefault(rel, 0)
        for e in entries:
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if e.name in EXCLUDE or e.name.endswith(".xcodeproj") or depth >= max_depth or budget[0] <= 0:
                    continue
                child_rel = e.name if rel == "." else rel + "/" + e.name
                visit(Path(e.path), child_rel, depth + 1, owner)
                continue
            ext = os.path.splitext(e.name)[1].lower()
            file_rel = e.name if rel == "." else rel + "/" + e.name
            if owner is None:
                if ext == ".swift":
                    scan.loose_swift.append(file_rel)
                continue
            if ext in UI_EXTS:
                scan.ui_files[owner] += 1
            if ext in (".css", ".scss") and len(scan.css.setdefault(owner, [])) < 40:
                scan.css[owner].append(file_rel)
            if ext == ".swift" and len(scan.swift.setdefault(owner, [])) < 40:
                scan.swift[owner].append(file_rel)

    visit(root, ".", 0, None)
    return scan


def join(pkg_rel: str, sub: str) -> str:
    return sub if pkg_rel == "." else pkg_rel + "/" + sub


def rel_within(pkg_rel: str, file_rel: str) -> str:
    return file_rel if pkg_rel == "." else file_rel[len(pkg_rel) + 1:]


def load_package_json(path: Path) -> dict:
    try:
        doc = json.loads(read_small(path, 1 << 20))
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}


def dep_map(doc: dict) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        val = doc.get(key)
        if isinstance(val, dict):
            out.update({str(k): str(v) for k, v in val.items()})
    return out


def major(spec: str) -> Optional[int]:
    m = re.search(r"(\d+)", spec or "")
    return int(m.group(1)) if m else None


GLOBAL_CSS_CANDIDATES = [
    "app/globals.css", "src/app/globals.css", "styles/globals.css", "src/styles/globals.css",
    "src/styles.scss", "src/styles.css", "src/index.css", "src/app.css", "src/globals.css",
    "styles.css", "index.css",
]


def analyze(root: Path, rel: str, names: List[str], scan: Scan, ancestor_ui: bool) -> Optional[dict]:
    """Classify one marker directory. Returns {'ui': {...}} or {'no_ui': {...}} or None."""
    base = root if rel == "." else root / rel
    nameset = set(names)
    deps: Dict[str, str] = {}
    pj: dict = {}
    if "package.json" in nameset:
        pj = load_package_json(base / "package.json")
        deps = dep_map(pj)

    def dir_has(sub: str) -> bool:
        return (base / sub).is_dir()

    def file_has(sub: str) -> bool:
        return (base / sub).is_file()

    # Native mobile first
    gradle = [n for n in ("build.gradle", "build.gradle.kts") if n in nameset]
    gradle_text = "\n".join(read_small(base / n).lower() for n in gradle)
    if gradle and "compose" in gradle_text:
        return {"ui": _ui(rel, "compose", "css", False, ["android"], scan)}
    if gradle and "android" in gradle_text:
        return {"ui": _ui(rel, "android-views", "css", False, ["android"], scan)}
    xcode = any(n.endswith(".xcodeproj") for n in names)
    if xcode or "Package.swift" in nameset:
        owned = scan.swift.get(rel, [])
        uses_swiftui = any("import SwiftUI" in read_small(root / f, 8192) for f in owned)
        if uses_swiftui:
            return {"ui": _ui(rel, "swiftui", "css", False, ["ios"], scan)}
        if xcode:
            return {"ui": _ui(rel, "uikit", "css", False, ["ios"], scan)}

    framework = None
    if "react-native" in deps or "expo" in deps or any(k.startswith("@react-native/") for k in deps):
        item = _ui(rel, "react-native", "native", False, ["ios", "android"], scan)
        item["supported"] = False
        item["note"] = "React Native themes are a later release; Plumb does not generate a theme for it in 1.0.0"
        return {"ui": item}
    if "next" in deps or any(n.startswith("next.config.") for n in names):
        framework = "next"
    elif "@angular/core" in deps:
        framework = "angular"
    elif "svelte" in deps or "@sveltejs/kit" in deps:
        framework = "svelte"
    elif "vue" in deps or "nuxt" in deps:
        framework = "vue"
    elif "react" in deps or "react-dom" in deps:
        framework = "react"
    tailwind_dep = any(k == "tailwindcss" or k.startswith("@tailwindcss/") for k in deps)
    if framework is None and tailwind_dep:
        framework = "html"
    if framework is None and "index.html" in nameset and not ancestor_ui:
        inline = "<style" in read_small(base / "index.html", 65536).lower()
        if scan.css.get(rel) or inline or "package.json" not in nameset:
            framework = "html"

    if framework is not None:
        existing_css = [c for c in GLOBAL_CSS_CANDIDATES if file_has(c)]
        others = [rel_within(rel, c) for c in scan.css.get(rel, [])][:20]
        css_text = "\n".join(read_small(base / c, 16384) for c in existing_css + others)
        has_v4_import = re.search(r"""@import\s+["']tailwindcss""", css_text) is not None
        has_config = any(n.startswith("tailwind.config.") for n in names)
        dep_major = major(deps.get("tailwindcss", ""))
        if has_v4_import or any(k.startswith("@tailwindcss/") for k in deps) or (dep_major or 0) >= 4:
            styling = "tailwind-v4"
        elif has_config or "tailwindcss" in deps or "@tailwind " in css_text:
            styling = "tailwind-v3"
        else:
            styling = "css"
        shadcn = "components.json" in nameset
        item = _ui(rel, framework, styling, shadcn, ["web"], scan)
        if framework == "angular":
            item["ui_files"] = angular_ui_files(rel)  # finished in classify(), once the nested folders are known
        gpath = global_css(framework, base, existing_css, others, deps, names, dir_has, file_has)
        item["global_css"] = {"path": gpath, "exists": file_has(gpath)}
        return {"ui": item}

    # Backend markers
    py = (read_small(base / "pyproject.toml") + "\n" + read_small(base / "requirements.txt")).lower()
    for fw in ("fastapi", "django", "flask"):
        if re.search(r"(?<![\w-])" + fw + r"(?![\w])", py):
            return {"no_ui": {"path": rel, "stack": fw}}
    if "go.mod" in nameset:
        return {"no_ui": {"path": rel, "stack": "go"}}
    if "pom.xml" in nameset or gradle:
        return {"no_ui": {"path": rel, "stack": "java"}}
    if "Cargo.toml" in nameset:
        return {"no_ui": {"path": rel, "stack": "rust"}}
    if "Gemfile" in nameset and "rails" in read_small(base / "Gemfile").lower():
        return {"no_ui": {"path": rel, "stack": "rails"}}
    for node in ("express", "fastify", "@nestjs/core", "koa", "hono"):
        if node in deps:
            return {"no_ui": {"path": rel, "stack": node.split("/")[-1] if node.startswith("@") else node}}
    return None


def _ui(rel: str, framework: str, styling: str, shadcn: bool, platforms: List[str], scan: Scan) -> dict:
    return {
        "path": rel, "framework": framework, "styling": styling, "shadcn": shadcn,
        "platforms": platforms, "files": scan.ui_files.get(rel, 0), "supported": True, "global_css": None,
        "ui_files": None,
    }


def angular_ui_files(rel: str, suffixed: bool = True, roots: Optional[List[str]] = None) -> str:
    """PLUMB.md `UI files:` for an Angular package at rel: its source folders (angular.json sourceRoot, default src/),
    component files only (see ANGULAR_UI_NAMES); every source file when any component is named without the .component
    suffix (Angular 20 names, alone or mixed with the older ones, or an inline-template class)."""
    names = ANGULAR_UI_NAMES if suffixed else ANGULAR_UI_NAMES_UNSUFFIXED
    return ", ".join(join(rel, r + "/**") for r in (roots or ["src"])) + " · " + " ".join(names)


def ui_files_for(ui: List[dict]) -> Optional[str]:
    """The PLUMB.md `UI files:` value these UI packages need, or None when scaffold.py's platform default fits: only web
    packages other than Angular, or only mobile ones. Angular needs its own; web next to iOS or Android needs the
    mobile folders too (the audit takes a file only when it is in a listed folder AND has a listed name)."""
    ui = [u for u in ui if u.get("supported", True)]  # React Native: no theme in 1.0.0, so no UI files of its own
    web = any("web" in u["platforms"] for u in ui)
    mobile = any("web" not in u["platforms"] for u in ui)
    if not any(u.get("ui_files") for u in ui) and not (web and mobile):
        return None
    dirs: List[str] = []
    names: List[str] = []

    def add(items: List[str], values) -> None:
        for v in values:
            if v not in items:
                items.append(v)

    for u in ui:
        if u.get("ui_files"):
            left, _, right = u["ui_files"].partition(" · ")
            add(dirs, [d.strip() for d in left.split(",") if d.strip()])
            add(names, right.split())
        elif "web" in u["platforms"]:
            add(dirs, ["app/**", "src/**", "components/**"] if u["path"] == "." else [join(u["path"], "**")])
            add(names, ["*.tsx", "*.jsx", "*.vue", "*.svelte", "*.css"])
        else:
            add(dirs, [join(u["path"], "**")] if u["path"] != "." else ["**"])
            add(names, ["*.swift"] if "ios" in u["platforms"] else ["*.kt"])
    return ", ".join(dirs) + " · " + " ".join(names)


def global_css(framework, base, existing, others, deps, names, dir_has, file_has) -> str:
    def first(*options: str) -> Optional[str]:
        return next((o for o in options if o in existing), None)

    if framework == "next":
        found = first("app/globals.css", "src/app/globals.css", "styles/globals.css", "src/styles/globals.css")
        if found:
            return found
        if dir_has("src/app"):
            return "src/app/globals.css"
        if dir_has("app"):
            return "app/globals.css"
        if dir_has("src/pages"):
            return "src/styles/globals.css"
        if dir_has("pages"):
            return "styles/globals.css"
        return "app/globals.css"
    if framework == "angular":
        return first("src/styles.scss", "src/styles.css") or "src/styles.css"
    if framework == "html":
        return first("styles.css", "index.css") or (others[0] if others else "styles.css")
    found = first("src/index.css", "src/app.css", "src/styles.css", "src/globals.css", "styles.css", "index.css")
    if found:
        return found
    return "src/app.css" if framework == "svelte" else "src/index.css"


# --- project name ----------------------------------------------------------------------------


TRANSLIT = {"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "đ": "d", "ł": "l", "þ": "th", "ð": "d", "ı": "i",
            "Ø": "O", "Æ": "AE", "Œ": "OE", "Đ": "D", "Ł": "L", "Þ": "Th", "Ð": "D"}


def kebab(text: str) -> str:
    text = "".join(TRANSLIT.get(c, c) for c in text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text


def project_name(root: Path) -> str:
    """The project id: the root package.json's name (without an @scope/), else the folder's name, made lower-case
    with hyphens by kebab(); "project" when neither has a letter or digit. The one rule detect.py proposes the skill
    folder (<id>-design-system) with and scaffold.py names the tokens file with (project_id)."""
    raw = ""
    if (root / "package.json").is_file():
        raw = str(load_package_json(root / "package.json").get("name") or "")
        raw = raw.split("/")[-1]
    return kebab(raw) or kebab(root.name) or "project"


SKILL_SUFFIX = "-design-system"


def project_id(root: Path, skill_dir: Optional[str] = None) -> str:
    """The project id scaffold.py writes (tokens file <id>.tokens.json, $extensions.plumb.project, the theme names):
    the confirmed skill folder's name without -design-system when it is named that way (detect.py proposed it from
    project_name, or the person chose another), else project_name(root). So the two never disagree."""
    if skill_dir:
        folder = str(skill_dir).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        if folder.endswith(SKILL_SUFFIX):
            own = kebab(folder[:-len(SKILL_SUFFIX)])
            if own:
                return own
    return project_name(root)


# --- PLUMB.md --------------------------------------------------------------------------------


def read_existing(root: Path) -> dict:
    out = {"plumb_md": False, "skill": None, "role": None}
    path = root / "PLUMB.md"
    if not path.is_file():
        return out
    out["plumb_md"] = True
    doc = {k.lower(): v for k, v in read_plumb_md(path).items()}
    if doc.get("design system"):
        out["skill"] = doc["design system"]
    if doc.get("role"):
        out["role"] = doc["role"].split()[0].lower()
    return out


# --- layout ----------------------------------------------------------------------------------


def monorepo_marker(root: Path) -> Optional[str]:
    for name in MONOREPO_FILES:
        if (root / name).is_file():
            return name
    pj = root / "package.json"
    if pj.is_file() and "workspaces" in load_package_json(pj):
        return "package.json workspaces"
    if (root / "apps").is_dir() and (root / "packages").is_dir():
        return "apps/ + packages/"
    if (root / "frontend").is_dir() and (root / "backend").is_dir():
        return "frontend/ + backend/"
    return None


def classify(root: Path, max_depth: int = MAX_DEPTH) -> Tuple[List[dict], List[dict]]:
    scan = walk(root, max_depth)
    ui: List[dict] = []
    no_ui: List[dict] = []
    ui_dirs: List[str] = []
    for rel in sorted(scan.dirs, key=lambda r: (0 if r == "." else r.count("/") + 1, r)):
        ancestor_ui = any(rel == d or d == "." or rel.startswith(d + "/") for d in ui_dirs)
        res = analyze(root, rel, scan.dirs[rel], scan, ancestor_ui)
        if not res:
            continue
        if "ui" in res:
            ui.append(res["ui"])
            ui_dirs.append(rel)
        else:
            no_ui.append(res["no_ui"])
    _absorb(root, scan, ui, no_ui)
    loose = loose_swiftui(root, scan)
    if loose:
        ui.append(loose)
    return ui, no_ui


def _absorb(root: Path, scan: Scan, ui: List[dict], no_ui: List[dict]) -> None:
    """Count each UI package's files with those of the marker folders nested in it that are not packages of their own
    (src/index.html makes src/ a marker folder; a folder inside a backend package counts for nobody), and finish an
    Angular package's UI files from its source roots and component naming."""
    packages = [(u["path"], u) for u in ui] + [(n["path"], None) for n in no_ui]
    paths = {p for p, _ in packages}

    def owner(rel: str) -> Optional[dict]:
        best: Optional[Tuple[str, Optional[dict]]] = None
        for p, u in packages:
            if (p == "." or rel.startswith(p + "/")) and (best is None or len(p) > len(best[0])):
                best = (p, u)
        return best[1] if best else None  # None also when the nearest package is a backend

    members: Dict[str, List[str]] = {u["path"]: [u["path"]] for u in ui}
    for rel in scan.dirs:
        if rel in paths:
            continue
        u = owner(rel)
        if u is not None:
            u["files"] += scan.ui_files.get(rel, 0)
            members[u["path"]].append(rel)
    for u in ui:
        if u["framework"] != "angular":
            continue
        mine = members[u["path"]]
        base = root if u["path"] == "." else root / u["path"]
        extra = sum(scan.angular_extra.get(r, 0) for r in mine)
        suffixed = sum(scan.component_suffix.get(r, 0) for r in mine)
        paired = sum(scan.unsuffixed_paired.get(r, 0) for r in mine)
        lonely = [f for r in mine for f in scan.lonely_ts.get(r, [])][:LONELY_TS_MAX]
        inline = [f for f in lonely if "@Component(" in read_small(root / f, 16384)]
        u["files"] += extra + len(inline)
        unsuffixed = paired + len(inline) > 0
        u["ui_files"] = angular_ui_files(u["path"], not unsuffixed, angular_source_roots(base))
        if unsuffixed:
            u["naming"] = "mixed" if suffixed else "unsuffixed"


def angular_source_roots(base: Path) -> List[str]:
    """The source folders of an Angular workspace (angular.json projects.*.sourceRoot, relative to the workspace),
    in file order; ["src"] when angular.json is missing, unreadable (JSON with comments), or names none inside it."""
    try:
        doc = json.loads(read_small(base / "angular.json", 1 << 20))
    except ValueError:
        return ["src"]
    projects = doc.get("projects") if isinstance(doc, dict) else None
    roots: List[str] = []
    if isinstance(projects, dict):
        for proj in projects.values():
            sr = proj.get("sourceRoot") if isinstance(proj, dict) else None
            if not isinstance(sr, str):
                continue
            sr = sr.replace("\\", "/").strip()
            if sr.startswith("/"):  # absolute: outside the workspace
                continue
            sr = sr.strip("/")
            if sr.startswith("./"):
                sr = sr[2:]
            parts = sr.split("/")
            if not sr or ".." in parts or ":" in parts[0]:
                continue
            if sr not in roots:
                roots.append(sr)
    return roots or ["src"]


def loose_swiftui(root: Path, scan: Scan) -> Optional[dict]:
    """SwiftUI sources outside every marker folder (no Package.swift, no Xcode project): a UI package at the folder
    the SwiftUI files share, flagged as a guess (it lowers the confidence)."""
    swiftui = [f for f in scan.loose_swift[:200] if "import SwiftUI" in read_small(root / f, 8192)]
    if not swiftui:
        return None
    parts = [f.split("/")[:-1] for f in swiftui]
    common: List[str] = []
    for segs in zip(*parts):
        if any(s != segs[0] for s in segs):
            break
        common.append(segs[0])
    rel = "/".join(common) or "."
    files = sum(1 for f in scan.loose_swift if rel == "." or f.startswith(rel + "/"))
    item = _ui(rel, "swiftui", "css", False, ["ios"], scan)
    item["files"] = files
    item["guess"] = SWIFTUI_GUESS_REASON.format(path=rel)
    return item


def list_children(cwd: Path, max_depth: int = MAX_DEPTH) -> List[dict]:
    """Project folders under cwd, up to max_depth levels down (cheap: markers only, no full scan).

    A git repo or a folder with project markers is listed (path relative to cwd) and is not searched for more
    projects; only a nested git repo inside a non-repo project folder is still listed, because a project root must
    never contain another repo. Folders with no markers are searched deeper."""
    kids: List[dict] = []
    budget = [MAX_ENTRIES]

    def visit(folder: Path, rel: str, depth: int, repos_only: bool) -> None:
        try:
            entries = sorted(os.scandir(str(folder)), key=lambda e: e.name.lower())
        except OSError:
            return
        budget[0] -= len(entries)
        for e in entries:
            try:
                if not e.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if e.name.startswith(".") or e.name in NOT_PROJECTS or e.name.endswith(".xcodeproj"):
                continue
            child = Path(e.path)
            child_rel = e.name if not rel else rel + "/" + e.name
            names = [x.name for x in _safe_iter(child)]
            is_repo = ".git" in names
            looks_like_project = any(n in MARKER_FILES or n.endswith(".xcodeproj") for n in names if n != "index.html")
            if is_repo or (looks_like_project and not repos_only):
                kids.append({"name": child_rel, "path": child_rel, "is_repo": is_repo,
                             "has_ui": _quick_ui(child, names)})
            if is_repo or depth + 1 >= max_depth or budget[0] <= 0:
                continue
            visit(child, child_rel, depth + 1, repos_only or looks_like_project)

    visit(cwd, "", 0, False)
    return kids


def enclosing_project(cwd: Path) -> Optional[dict]:
    """Outside git: the nearest folder above cwd with monorepo markers or a PLUMB.md (the project may be that one)."""
    for d in cwd.parents:
        markers = [n for n in MONOREPO_FILES if (d / n).is_file()]
        pj = d / "package.json"
        if pj.is_file() and "workspaces" in load_package_json(pj):
            markers.append("package.json workspaces")
        plumb = (d / "PLUMB.md").is_file()
        if markers or plumb:
            return {"root": d.as_posix(), "markers": markers, "plumb_md": plumb}
        if (d / ".git").exists():
            break
    return None


def _top_ui(folder: Path, ns: List[str]) -> bool:
    if any(n.endswith(".xcodeproj") for n in ns) or "index.html" in ns:
        return True
    if "package.json" in ns:
        deps = dep_map(load_package_json(folder / "package.json"))
        ui = ("next", "react", "vue", "svelte", "@sveltejs/kit", "@angular/core", "nuxt", "tailwindcss",
              "react-native", "expo")
        return any(k in deps for k in ui)
    for g in ("build.gradle", "build.gradle.kts"):
        if g in ns and "compose" in read_small(folder / g).lower():
            return True
    return False


def _quick_ui(child: Path, names: List[str]) -> bool:
    """Cheap has-UI flag for the parent listing: the top level plus two levels of the usual UI folders."""
    if _top_ui(child, names):
        return True
    for sub in ("frontend", "web", "client", "app", "apps"):
        d = child / sub
        if d.is_dir():
            ns = [x.name for x in _safe_iter(d)]
            if _top_ui(d, ns):
                return True
            for n in ns:
                if n not in EXCLUDE and (d / n).is_dir() and _top_ui(d / n, [y.name for y in _safe_iter(d / n)]):
                    return True
    return False


def _safe_iter(path: Path) -> List[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []


def confidence(layout: str, marker: Optional[str], ui: List[dict], no_ui: List[dict]) -> Tuple[str, List[str]]:
    low: List[str] = []
    medium: List[str] = []
    if not ui and not no_ui:
        low.append("no project markers found (no package.json, pyproject, go.mod, Xcode project, ...)")
    for u in ui:
        g = u.get("global_css")
        if g and not g["exists"]:
            low.append(u["path"] + ": no global CSS found, copy path " + g["path"] + " is a guess")
        if not u.get("supported", True):
            medium.append(u["path"] + ": " + u["note"])
        if u.get("guess"):
            low.append(u["guess"])
        if u.get("naming") in ("unsuffixed", "mixed"):
            medium.append(u["path"] + ": Angular files without the .component suffix (Angular 20 names"
                          + (", next to suffixed ones" if u["naming"] == "mixed" else "")
                          + "): UI files cover every .ts, .html, .scss and .css in the source folders")
    if len(ui) > 1 and not marker:
        low.append("several UI packages without monorepo markers")
    if layout == "mixed":
        medium.append("backend and UI live in one repo without monorepo markers")
    if low:
        return "low", low + medium
    if medium:
        return "medium", medium
    return "high", []


def detect(cwd) -> dict:
    cwd = Path(cwd).resolve()
    root, git_ok = find_root(cwd)
    existing = {"plumb_md": False, "skill": None, "role": None}
    in_repo = root is not None
    if root is None:
        # Not inside git (git is optional): the opened folder is the project when it has project markers, a parent
        # of projects when only its children do, and a new project when it is empty (or holds only dotfiles).
        # A folder that holds other git repos is never a project root.
        names = [x.name for x in _safe_iter(cwd)]
        own = _has_markers(cwd, names)
        children = list_children(cwd)
        if children and (not own or any(c["is_repo"] for c in children)):
            return {
                "root": cwd.as_posix(), "opened": ".", "layout": "parent", "monorepo": None,
                "ui_packages": [], "no_ui": [], "children": children, "git": False, "in_repo": False,
                "git_available": git_ok, "existing": existing, "proposal": None, "enclosing": None,
                "confidence": "low", "reasons": ["not inside a repo: the folder is a parent of projects"],
            }
        if not own and not [n for n in names if not n.startswith(".")]:
            return _new_project(cwd, git_ok)
        root = cwd
    root = root.resolve()
    try:
        opened = cwd.relative_to(root).as_posix()
    except ValueError:
        opened = "."
    marker = monorepo_marker(root)
    ui, no_ui = classify(root)
    if marker:
        layout = "monorepo"
    elif ui and no_ui:
        layout = "mixed"
    elif ui:
        layout = "frontend"
    elif no_ui:
        layout = "backend"
    else:
        layout = "single"
    name = project_name(root)
    copies: List[str] = []
    platforms: List[str] = []
    for u in ui:
        if u.get("global_css"):
            u["global_css"]["path"] = join(u["path"], u["global_css"]["path"])
            if u["supported"]:
                copies.append(u["global_css"]["path"])
        for p in u["platforms"]:
            if p not in platforms:
                platforms.append(p)
    conf, reasons = confidence(layout, marker, ui, no_ui)
    enclosing = None
    if not in_repo:
        reasons.append(NO_GIT_REASON)
        conf = "medium" if conf == "high" else conf
        enclosing = enclosing_project(root)
        if enclosing:
            reasons.append(_enclosing_reason(enclosing))
            conf = "low"
    return {
        "root": root.as_posix(), "opened": opened, "layout": layout, "monorepo": marker,
        "ui_packages": ui, "no_ui": no_ui, "children": [], "git": git_ok and in_repo, "in_repo": in_repo,
        "git_available": git_ok, "existing": read_existing(root),
        "proposal": _proposal(name, copies, platforms, ui_files_for(ui)),
        "enclosing": enclosing, "confidence": conf, "reasons": reasons,
    }


def _enclosing_reason(enc: dict) -> str:
    what = ", ".join(enc["markers"] + (["PLUMB.md"] if enc["plumb_md"] else []))
    return "enclosing folder " + enc["root"] + " has " + what + ": the project may be that folder"


NO_GIT_REASON = "not a git repo: the folder you opened is taken as the project root (git is optional)"


def _proposal(name: str, copies: List[str], platforms: List[str], ui_files: Optional[str] = None) -> dict:
    return {
        "project": name, "skill_dir": ".claude/skills/" + name + "-design-system", "plumb_md": "PLUMB.md",
        "docs_dir": "docs/design", "copies": copies, "platforms": platforms, "ui_files": ui_files,
        "alternatives": [".github/skills/" + name + "-design-system", "~/.claude/skills/" + name + "-design-system"],
    }


def _has_markers(folder: Path, names: List[str]) -> bool:
    """The folder itself looks like a project: a manifest, an Xcode project or a monorepo marker."""
    if any(n in MARKER_FILES or n in MONOREPO_FILES or n.endswith(".xcodeproj") for n in names):
        return True
    return monorepo_marker(folder) is not None


def _new_project(cwd: Path, git_ok: bool) -> dict:
    """An empty folder (or only dotfiles) outside git: a new project starts here."""
    enclosing = enclosing_project(cwd)
    reasons = ["empty folder: a new project starts here", NO_GIT_REASON]
    if enclosing:
        reasons.append(_enclosing_reason(enclosing))
    return {
        "root": cwd.as_posix(), "opened": ".", "layout": "new", "monorepo": None,
        "ui_packages": [], "no_ui": [], "children": [], "git": False, "in_repo": False,
        "git_available": git_ok, "existing": read_existing(cwd), "proposal": _proposal(project_name(cwd), [], []),
        "enclosing": enclosing, "confidence": "low" if enclosing else "medium", "reasons": reasons,
    }


# --- output ----------------------------------------------------------------------------------


def human(r: dict) -> str:
    lines: List[str] = []
    if r["layout"] == "parent":
        lines.append("Plumb found: no repo here. " + r["root"] + " looks like a parent folder.")
        if r["children"]:
            lines.append("Projects under it:")
            for c in r["children"]:
                tags = ("repo" if c["is_repo"] else "folder") + (" · has UI" if c["has_ui"] else "")
                lines.append("  " + c["name"] + "   (" + tags + ")")
        else:
            lines.append("No projects found under it.")
        lines.append("Which one? Nothing is written in the parent.")
        return "\n".join(lines) + "\n"
    if not r.get("in_repo", True):
        note = "the folder you opened; not a git repo, git is optional"
        if r["layout"] == "new":
            note = "empty folder: a new project starts here; " + note
    else:
        note = "git root" if r["git"] else "repo root, git not available"
    if r["opened"] != ".":
        note += "; you opened " + r["opened"]
    lines.append("Plumb found:")
    lines.append("  project    " + r["root"] + "   (" + note + ")")
    layout = r["layout"] + (" (" + r["monorepo"] + ")" if r["monorepo"] else "")
    lines.append("  layout     " + layout)
    for u in r["ui_packages"]:
        bits = [FRAMEWORK_LABEL.get(u["framework"], u["framework"]), STYLING_LABEL.get(u["styling"], u["styling"])]
        if u["shadcn"]:
            bits.append("shadcn")
        lines.append("  UI         " + u["path"] + "   " + " · ".join(bits) + "   (" + str(u["files"]) + " UI files)")
    for n in r["no_ui"]:
        lines.append("  no UI      " + n["path"] + "   " + n["stack"])
    if not r["ui_packages"] and not r["no_ui"]:
        lines.append("  UI         none found")
    ex = r["existing"]
    if ex["plumb_md"]:
        lines.append("  existing   PLUMB.md" + (" → " + ex["skill"] if ex["skill"] else "")
                     + (" (role: " + ex["role"] + ")" if ex["role"] else ""))
    enc = r.get("enclosing")
    if enc:
        lines.append("  enclosing  " + enc["root"] + "   ("
                     + ", ".join(enc["markers"] + (["PLUMB.md"] if enc["plumb_md"] else [])) + ": the project?)")
    p = r["proposal"]
    lines.append("I'll create:")
    lines.append("  " + p["skill_dir"] + "/   in " + r["root"])
    lines.append("  " + p["plumb_md"] + "   in " + r["root"])
    lines.append("  " + p["docs_dir"] + "/   in " + r["root"]
                 + "   (directions or extract page, decision log, prototype, reports)")
    root = Path(r["root"])
    for c in p["copies"]:
        lines.append("  generated copy → " + c + "   (Plumb's marked block of the token CSS)")
        state = copy_state(root, c)
        if state:
            lines.append("  " + state)
    ui_files = p.get("ui_files") or default_ui_files(p.get("platforms") or [])
    lines.append("  UI files   " + ui_files + "   (PLUMB.md: what the audit and the checks cover)")
    for u in r["ui_packages"]:
        if not u["supported"]:
            lines.append("  not supported yet: " + u["path"] + " (" + u["note"] + ")")
    if r["confidence"] != "high":
        lines.append("confidence " + r["confidence"] + ": " + "; ".join(r["reasons"]) + " (explore and ask)")
    lines.append("OK, or change something?")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Detect the repo layout and UI stack for Plumb init.")
    ap.add_argument("--cwd", default=".", help="folder the session was opened in")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    try:
        cwd = Path(normalize_cwd(args.cwd))
        if not cwd.is_dir():
            raise PlumbError("error: " + args.cwd + " is not a folder\nfix: pass an existing folder, e.g. detect.py --cwd .")
        result = detect(cwd)
    except PlumbError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(human(result))
    return 0


if __name__ == "__main__":
    utf8_stdio()
    sys.exit(main())
