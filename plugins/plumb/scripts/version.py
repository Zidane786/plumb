#!/usr/bin/env python3
"""version.py: compare a project's Plumb version with the plugin's, and list the upgrades in between.

    version.py --project P --plugin R [--json]

  --project   the project root (the folder holding PLUMB.md) or the PLUMB.md file itself
  --plugin    the plugin root (the folder holding .claude-plugin/plugin.json and upgrades/)
  --json      print {"project", "plugin", "state", "between", "files_differ"}

The project's version is PLUMB.md's version line (`<!-- plumb vX.Y.Z · ... -->`, its first line); the plugin's is
plugin.json's "version". state is the project compared with the plugin: "same", "older" (run /plumb:upgrade) or
"newer" (a teammate upgraded with a newer plugin: update the plugin, never downgrade the project). between lists every
upgrades/<version>.md with project < version <= plugin, in ascending order, compared as numbers (1.10.0 > 1.9.0);
it is empty unless state is "older". files_differ (only when state is "same") lists Plumb's own files in the project
(the design-system skill's scripts/*.py, templates/* and assets/platforms/README.md, the ones scaffold.py copies) that
are missing or differ from the plugin's copies, ignoring line endings and a BOM: another build of the same version (a
pre-release or branch build, or a hand edit). Which one is newer cannot be told from the files, so /plumb:upgrade shows
the evidence and asks. PLUMB.md is read by the hooks' rules (_hooklib.plumb_md_keys). Used by /plumb:upgrade and
/plumb:status. It only reads.

Exit codes: 0 ok (whatever the state), 2 bad input (`error: ...` then `fix: ...`). Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
VERSION_LINE = re.compile(r"<!--\s*plumb\s+v(\S+)")
UPGRADE_FILE = re.compile(r"^(\d+\.\d+\.\d+)\.md$")
# PLUMB.md's `Key: value` lines, read exactly as the hooks read them (hooks/_hooklib.py plumb_md_keys).
_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9 _/-]*?):(?:\s+(.*)|\s*)$")
_NOTE = re.compile(r"\s{2,}\((?!\s*(?:next-app|next-pages|nuxt|sveltekit|angular|router)\s*\))[^)]*\)\s*$")
HEAD_LINES = 5  # the version line is the first line; a blank line or two before it is tolerated


class VersionError(Exception):
    def __init__(self, what: str, fix: str) -> None:
        super().__init__(f"error: {what}\nfix: {fix}")


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is not None:
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - leave an odd stream as it is
                pass


def parse_version(text: str, where: str, fix: str) -> Tuple[int, int, int]:
    m = VERSION.match(text.strip())
    if not m:
        raise VersionError(f"{where}: {text!r} is not a version like 1.0.0", fix)
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def project_version(project: Path) -> str:
    path = project if project.is_file() else project / "PLUMB.md"
    if not path.is_file():
        raise VersionError(f"no PLUMB.md in {project}: this project is not set up for Plumb",
                           "run /plumb:init in the project (or pass --project with the folder that holds PLUMB.md)")
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError as exc:
        raise VersionError(f"cannot read {path} ({exc.strerror or exc})", "check the file exists and is readable") from None
    for line in text.replace("\r\n", "\n").split("\n")[:HEAD_LINES]:
        m = VERSION_LINE.search(line)
        if m:
            found = m.group(1)
            parse_version(found, f"{path.name} version line", "write the first line as "
                          "`<!-- plumb v1.0.0 · written by /plumb:init, safe to edit values -->` with the project's version")
            return found
    raise VersionError(f"{path} has no version line (its first line should be `<!-- plumb vX.Y.Z · ... -->`)",
                       "add `<!-- plumb v1.0.0 · written by /plumb:init, safe to edit values -->` as the first line, "
                       "with the Plumb version that set the project up (ask the user if unsure), or re-run /plumb:init")


def plugin_version(plugin: Path) -> str:
    path = plugin / ".claude-plugin" / "plugin.json"
    fix = "pass --plugin with the Plumb plugin's root folder (the one holding .claude-plugin/plugin.json)"
    if not path.is_file():
        raise VersionError(f"{path}: plugin.json not found", fix)
    try:
        doc = json.loads(path.read_bytes().decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise VersionError(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
                           "reinstall or update the Plumb plugin (its plugin.json is damaged)") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise VersionError(f"cannot read {path} ({exc})", fix) from None
    version = doc.get("version") if isinstance(doc, dict) else None
    if not isinstance(version, str):
        raise VersionError(f"{path} has no \"version\"", "reinstall or update the Plumb plugin")
    parse_version(version, "plugin.json version", "reinstall or update the Plumb plugin")
    return version


def upgrades_between(plugin: Path, old: Tuple[int, int, int], new: Tuple[int, int, int]) -> List[str]:
    folder = plugin / "upgrades"
    found = []
    if folder.is_dir():
        for path in folder.iterdir():
            m = UPGRADE_FILE.match(path.name)
            if m and path.is_file():
                v = parse_version(m.group(1), str(path), "rename it to <major>.<minor>.<patch>.md")
                if old < v <= new:
                    found.append((v, m.group(1)))
    return [name for _v, name in sorted(found)]


def plumb_md_keys(text: str) -> dict:
    """PLUMB.md's `Key: value` lines (comments, code fences, headings, bullets, quotes and tables ignored; a trailing
    '   (note)' dropped; a value in backticks unwrapped; the last one wins), as the hooks read them."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out: dict = {}
    fence = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if fence or not s or s[0] in "#-*>|":
            continue
        m = _KEY.match(s)
        if not m:
            continue
        val = _NOTE.sub("", (m.group(2) or "").strip()).strip()
        if len(val) >= 2 and val[0] == val[-1] == "`":
            val = val[1:-1].strip()
        out[m.group(1).strip()] = val
    return out


def plumb_file_rels(src: Path) -> List[str]:
    """Plumb's own [P] files, relative to the skill: scripts/*.py, templates/* and assets/platforms/README.md, as found
    in the plugin's assets/skill/ (scaffold.py copies the same list)."""
    rels = [f"scripts/{f.name}" for f in sorted((src / "scripts").glob("*.py")) if f.is_file()]
    if (src / "templates").is_dir():
        rels += [f"templates/{f.name}" for f in sorted((src / "templates").iterdir()) if f.is_file()]
    if (src / "assets/platforms/README.md").is_file():
        rels.append("assets/platforms/README.md")
    return rels


def _same_text(a: Path, b: Path) -> bool:
    try:
        x, y = a.read_bytes(), b.read_bytes()
    except OSError:
        return False
    if x == y:
        return True
    norm = lambda data: data.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")  # noqa: E731 - a Windows checkout
    return norm(x) == norm(y)


def plumb_files_differ(project: Path, plugin: Path) -> List[str]:
    """Plumb's own files in the project's design-system skill that are missing or differ from the plugin's copies,
    as project-relative paths. Nothing when PLUMB.md names no skill inside the project, the skill isn't there yet,
    or the repo is linked (its design system lives in the home repo)."""
    root = project.parent if project.is_file() else project
    try:
        text = (root / "PLUMB.md").read_bytes().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    except OSError:
        return []
    keys = plumb_md_keys(text)
    if keys.get("Role", "").strip().lower().startswith("linked"):
        return []
    rel = keys.get("Design system", "").strip().replace("\\", "/")
    if rel.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", rel) or ".." in rel.split("/"):
        return []  # only a skill inside the project is compared
    rel = rel.strip("/")
    if not rel:
        return []
    skill, src = root / rel, plugin / "assets" / "skill"
    if not skill.is_dir() or not src.is_dir():
        return []
    try:  # a skill folder linked from outside the project is not compared, as the session-start line (files_note)
        Path(os.path.realpath(skill)).relative_to(Path(os.path.realpath(root)))
    except ValueError:
        return []
    return [f"{rel}/{r}" for r in plumb_file_rels(src) if not _same_text(skill / r, src / r)]


def compare(project: Path, plugin: Path) -> dict:
    pv, gv = project_version(project), plugin_version(plugin)
    pt = parse_version(pv, "PLUMB.md", "")
    gt = parse_version(gv, "plugin.json", "")
    state = "same" if pt == gt else ("older" if pt < gt else "newer")
    between = upgrades_between(plugin, pt, gt) if state == "older" else []
    differ = plumb_files_differ(project, plugin) if state == "same" else []
    return {"project": pv, "plugin": gv, "state": state, "between": between, "files_differ": differ}


def plain(result: dict) -> str:
    p, g = result["project"], result["plugin"]
    if result["state"] == "same" and result["files_differ"]:
        n = len(result["files_differ"])
        return (f"Plumb {p} on both, but {n} of Plumb's files in the project differ from the plugin's (another build of "
                f"{p}, or a hand edit; which is newer cannot be told from the files): /plumb:upgrade shows them and asks "
                f"before refreshing. " + ", ".join(result["files_differ"]))
    if result["state"] == "same":
        return f"Plumb {p}: the project is up to date with the plugin."
    if result["state"] == "newer":
        return (f"The project is on Plumb {p}, newer than this plugin ({g}): a teammate upgraded it. Never downgrade the "
                f"project; update the plugin by running, in your own terminal: claude plugin marketplace update plumb, then "
                f"claude plugin update plumb@plumb (Copilot CLI: copilot plugin marketplace update plumb, then copilot "
                f"plugin update plumb@plumb).")
    steps = ", ".join(result["between"]) or "none"
    return f"The project is on Plumb {p}, the plugin is {g}: run /plumb:upgrade. Upgrade notes in between: {steps}."


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: python3 version.py --project <project root> --plugin <plugin root> [--json]\n")


def main(argv: Optional[List[str]] = None) -> int:
    utf8_stdio()
    parser = _Parser(prog="version.py", description="Compare the project's Plumb version with the plugin's.")
    parser.add_argument("--project", required=True, metavar="P", help="project root (or its PLUMB.md)")
    parser.add_argument("--plugin", required=True, metavar="R", help="the Plumb plugin's root folder")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    try:
        result = compare(Path(args.project).resolve(), Path(args.plugin).resolve())
    except VersionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    else:
        print(plain(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
