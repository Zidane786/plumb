#!/usr/bin/env python3
"""Plumb repo layout and stack detection (used by /plumb:init).

    detect.py --cwd PATH [--json]

Finds where the project and its UI live, so init can show "Plumb found: ..." and wait for the
user's confirmation. It only reads; it never writes anything.

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
MAX_DEPTH = 5
MAX_ENTRIES = 60000
UI_EXTS = {".tsx", ".jsx", ".vue", ".svelte", ".html", ".swift", ".kt"}
MARKER_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "go.mod", "pom.xml", "build.gradle",
    "build.gradle.kts", "Cargo.toml", "Gemfile", "Package.swift", "index.html",
}
MONOREPO_FILES = ["pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json", "rush.json"]
FRAMEWORK_LABEL = {
    "next": "Next.js", "react": "React", "vue": "Vue", "svelte": "Svelte", "angular": "Angular",
    "html": "plain HTML", "swiftui": "SwiftUI", "uikit": "UIKit", "compose": "Jetpack Compose",
    "android-views": "Android Views",
}
STYLING_LABEL = {"tailwind-v4": "Tailwind v4", "tailwind-v3": "Tailwind v3", "css": "CSS"}


class PlumbError(Exception):
    """Message is already 'error: ...' then 'fix: ...' lines."""


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


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
            if owner is None:
                continue
            ext = os.path.splitext(e.name)[1].lower()
            file_rel = e.name if rel == "." else rel + "/" + e.name
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
    if framework is None and "index.html" in nameset and not ancestor_ui and "package.json" not in nameset:
        if scan.css.get(rel):
            framework = "html"
    if framework is None and "index.html" in nameset and "package.json" in nameset and scan.css.get(rel):
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
        item["global_css"] = global_css(framework, base, existing_css, others, deps, names, dir_has, file_has)
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
        "platforms": platforms, "files": scan.ui_files.get(rel, 0),
    }


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


def kebab(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text


def project_name(root: Path) -> str:
    raw = ""
    if (root / "package.json").is_file():
        raw = str(load_package_json(root / "package.json").get("name") or "")
        raw = raw.split("/")[-1]
    return kebab(raw) or kebab(root.name) or "project"


# --- PLUMB.md --------------------------------------------------------------------------------


def read_existing(root: Path) -> dict:
    out = {"plumb_md": False, "skill": None, "role": None}
    path = root / "PLUMB.md"
    if not path.is_file():
        return out
    out["plumb_md"] = True
    for line in read_small(path, 1 << 20).splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z ]*?):\s*(.*?)\s*$", line)
        if not m:
            continue
        key, val = m.group(1).strip().lower(), m.group(2).strip()
        if key == "design system" and val:
            out["skill"] = val.strip("`").strip()
        elif key == "role" and val:
            out["role"] = val.split()[0].lower()
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
    return ui, no_ui


def list_children(cwd: Path) -> List[dict]:
    kids: List[dict] = []
    try:
        entries = sorted(os.scandir(str(cwd)), key=lambda e: e.name.lower())
    except OSError:
        return kids
    for e in entries:
        try:
            if not e.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        if e.name.startswith(".") or e.name in EXCLUDE:
            continue
        child = Path(e.path)
        is_repo = (child / ".git").exists()
        ui, no_ui = classify(child, 3)
        looks_like_project = bool(ui or no_ui) or any(
            (child / m).exists() for m in ("package.json", "pyproject.toml", "go.mod", "build.gradle", "build.gradle.kts")
        ) or any(x.name.endswith(".xcodeproj") for x in _safe_iter(child))
        if is_repo or looks_like_project:
            kids.append({"name": e.name, "path": e.name, "is_repo": is_repo, "has_ui": bool(ui)})
    return kids


def _safe_iter(path: Path) -> List[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []


def detect(cwd) -> dict:
    cwd = Path(cwd).resolve()
    root, git_ok = find_root(cwd)
    existing = {"plumb_md": False, "skill": None, "role": None}
    if root is None:
        return {
            "root": cwd.as_posix(), "opened": ".", "layout": "parent", "monorepo": None,
            "ui_packages": [], "no_ui": [], "children": list_children(cwd), "git": git_ok,
            "existing": existing, "proposal": None,
        }
    root = root.resolve()
    try:
        opened = cwd.relative_to(root).as_posix()
    except ValueError:
        opened = "."
    marker = monorepo_marker(root)
    ui, no_ui = classify(root)
    if marker:
        layout = "monorepo"
    elif ui:
        layout = "frontend"
    elif no_ui:
        layout = "backend"
    else:
        layout = "single"
    name = project_name(root)
    copies = [join(u["path"], u["global_css"]) for u in ui if "global_css" in u]
    platforms: List[str] = []
    for u in ui:
        for p in u["platforms"]:
            if p not in platforms:
                platforms.append(p)
    for u in ui:
        u.pop("global_css", None)
    skill = ".claude/skills/" + name + "-design-system"
    return {
        "root": root.as_posix(), "opened": opened, "layout": layout, "monorepo": marker,
        "ui_packages": ui, "no_ui": no_ui, "children": [], "git": git_ok,
        "existing": read_existing(root),
        "proposal": {
            "project": name, "skill_dir": skill, "plumb_md": "PLUMB.md", "copies": copies,
            "platforms": platforms,
            "alternatives": [".github/skills/" + name + "-design-system", "~/.claude/skills/" + name + "-design-system"],
        },
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
    p = r["proposal"]
    lines.append("I'll create:")
    lines.append("  " + p["skill_dir"] + "/   at the repo root")
    lines.append("  " + p["plumb_md"] + "   at the repo root")
    for c in p["copies"]:
        lines.append("  generated copy → " + c)
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
