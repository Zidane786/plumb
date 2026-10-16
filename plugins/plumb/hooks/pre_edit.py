#!/usr/bin/env python3
"""Plumb PreToolUse hook (Edit, Write, MultiEdit, Bash, PowerShell; Copilot CLI's edit tool and apply_patch too).

Only in a project with a PLUMB.md (see _hooklib): anywhere else, including Plumb's own repository, it allows everything.
In such a project, in this order:

1. Guard, always on: refuses a hand edit to
   - a generated file: <skill>/assets/platforms/web/tokens.css and tailwind.tokens.js, the mobile themes
     (assets/platforms/mobile/ios/*Theme.swift, android/*Theme.kt, and any *Theme.swift / *Theme.kt that carries the
     GENERATED header), Plumb's block in the copies listed in $extensions.plumb.web.copies (an edit tool's change that
     leaves the text from /* plumb:start ... */ to /* plumb:end */ as it is passes: the rest of a copy is the
     project's; a shell write or removal of a copy is refused), <docs>/specimen.html, <docs>/prototype.html,
     <docs>/app.html, <docs>/screens.html, <docs>/prototype/screens.json, <docs>/tours/*.html (a prototype, app,
     catalogue or tour page that exists without the GENERATED header naming build-prototype.py is someone's own page,
     another tool's or hand-written, and is left alone: the build refuses to replace it) and the proposal pages
     <docs>/prototype/proposals/<name>/index.html and <name>/<variant>/{prototype,app,screens}.html (one that does not
     carry the header `build-prototype.py --proposal` writes is someone's own page and is left alone);
   - one of Plumb's own files: the design-system skill's [P] files (scripts/*.py, templates/*,
     assets/platforms/README.md) and anything under the plugin root (CLAUDE_PLUGIN_ROOT): upgrades replace them; and
     the Kiro files kiro.py installed (a marked .kiro/hooks/plumb.json, a .kiro/skills/plumb-<name>/ whose SKILL.md is
     marked, in the project or the home folder): editing them could switch the checks off.
   Shell commands (shell_refusal): the earlier reader (_shell_legacy.py) decides, and _hooklib's shell reader adds what
   it finds. Refused when the shell reader finds a guarded file among the real write targets: a redirect (>, >>, 1>,
   2>, &>, >|), tee [-a], sed -i / w FILE, perl -i, sort -o, the destination of cp / mv / install / rsync / ln (a
   recursive copy or a move into a folder that holds a guarded file), truncate, dd of=, Set-Content, Add-Content,
   Out-File, Copy-Item / Move-Item onto, a shell's own script (bash -c, a here-document fed to a shell, eval), a file
   the command wrote and then runs, and in inline code (python -c, node -e, a here-document fed to an interpreter)
   open(<path>, "w"|"a"|"x"), Path(<path>).write_text / write_bytes, shutil.copy, fs.writeFile and the like, with
   targets put together from the code's constants. A target that uses a for / select / while-read loop variable is
   refused when the variable could hold a guarded path, or a name the target turns into one (_loop_refusal, against
   the guarded paths only); a target the reader cannot work out ($( ), backticks, ${…}) when its text or the value of
   a variable it uses names a guarded file or folder by its full path (_Guarded.target). A refusal of the earlier
   reader becomes an allow only when the shell reader proves it (_proven): (a) a here-document / echo / printf / tee
   text written to a file the same command does not run, import, name again or leave where a program picks it up (a
   Makefile whose lines run the scripts is fine; sitecustomize.py, .bashrc, a git hook are not), (b) a read-only
   program's words, (c) inline code that only reads its guarded literals (json.load, importlib, Path.read_text) and
   writes only to plain literals away from them, (d) a git commit message (-m / -F / -t values, a here-document on
   stdin), unless git is given an option that runs something, a variable is set before it, or the command wrote a hook.
   Every other word must name no guarded path by guard()'s own rule (files that do not exist yet, the plugin root, a
   folder that holds a guarded file or a parent of one). Running build-tokens.py or build-prototype.py, and anything
   that writes elsewhere, is allowed. Removing or moving away a guarded file (rm, rmdir, unlink, del, Remove-Item, git
   rm, the sources of mv / Move-Item / git mv, os.remove, shutil.rmtree), or a folder that holds one, is refused the
   same way; ~, $HOME,
   ${HOME}, %USERPROFILE% and $env:USERPROFILE in a path are the home folder. A command longer than SHELL_HUGE, one
   whose brackets nest deeper than the reader reads, and one the reader fails on (a crash, the recursion limit) are
   not read: refused when a word names a guarded file or folder (or a parent of one), else the earlier reader decides;
   a crash, a timeout and a command too long to read log one line with the real outcome.
2. Prototype first (PLUMB.md `Prototype sync: on`): refuses an edit that creates a new route (a new page file, or a new
   path in a router config, under PLUMB.md's `Routes:` only; with no `Routes:` line it allows the edit, and the session
   start note says the routes are not recorded) unless a screen in screens.json
   covers it (same route, a source glob matching the file, or the route's slug as its id) and its current screen file
   is the approved one: `fix: /plumb:prototype <slug>`.
3. Edit check (PLUMB.md `Edit check: on`): for a UI file (the audit's file types, inside PLUMB.md's `UI files`), the
   file's text before and after the edit goes through audit.quick(), and only the errors the edit adds
   are refused: at most 10, each `error: line N: ...` then `fix: ...`.

The checks use the plugin's own audit.py (never the project's copy: trust boundary, see _hooklib); the project is
only read as data. Claude Code: a refusal is exit 2 with the reason on stderr. Copilot CLI: exit 0 with a JSON deny on stdout. Anything
unexpected (bad input, no design-system skill, a broken tokens file, the plugin's audit.py failing to load) allows the
edit, with at most one
stderr line. Standard library only.
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _hooklib as H  # noqa: E402

MAX_ISSUES = 10
# Matched without case where paths are compared without it (H.CASELESS, settled once the project is known).
_THEME = r"Theme\.(?:swift|kt)$"
_PLATFORM_OUTPUTS = (r"assets/platforms/web/(?:tokens\.css|tailwind\.tokens\.js)",
                     r"assets/platforms/mobile/ios/[^/]*Theme\.swift",
                     r"assets/platforms/mobile/android/[^/]*Theme\.kt")


def _case() -> int:
    return re.I if H.CASELESS else 0


def _generated_header(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(1500).decode("utf-8", "replace")
    except OSError:
        return False
    head = "\n".join(head.splitlines()[:5])
    return "GENERATED" in head and re.search(r"do not edit", head, re.I) is not None


def _prototype_header(path: str) -> bool:
    """The page carries the header build-prototype.py writes (GENERATED … naming build-prototype.py): the test
    build-prototype.py uses before replacing a page. A page another tool generated there, or a hand-written one, is
    someone's own: the build refuses to replace it, and the guard leaves it alone so it can be moved out of the way."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(2000).decode("utf-8", "replace")
    except OSError:
        return False
    head = "\n".join(head.splitlines()[:5])
    return _generated_header(path) and "plumb:start" not in head and "build-prototype.py" in head


def _own(shown: str) -> str:
    return (f"error: {shown} is Plumb's file; upgrades replace it\n"
            f"fix: use /plumb:update for design changes, or propose the improvement to the Plumb repo")


def _tokens_output(proj: H.Project, shown: str) -> str:
    return (f"error: {shown} is generated from the design tokens; a hand edit is lost on the next build\n"
            f"fix: change the tokens with /plumb:update, then rebuild: {proj.script('build-tokens.py')}")


def _prototype_output(proj: H.Project, shown: str) -> str:
    docs = proj.docs_rel
    return (f"error: {shown} is generated by build-prototype.py from the screen files; a hand edit is lost on the next "
            f"build\nfix: edit the screen files in {docs}/prototype/screens/ (or the tours in {docs}/prototype/tours/), "
            f"then rebuild: {proj.script('build-prototype.py')}")


def _tour_output(proj: H.Project, shown: str, tour: str) -> str:
    docs = proj.docs_rel
    source = f"{docs}/prototype/tours/{tour}.json"
    return (f"error: {shown} is generated by build-prototype.py from the screen files and the tour file {source}; a "
            f"hand edit is lost on the next build\nfix: edit the tour file {source} (or the screen files in "
            f"{docs}/prototype/screens/), then rebuild: {proj.script('build-prototype.py')}")


def _proposal_output(proj: H.Project, shown: str, name: str, variant: Optional[str]) -> str:
    base = f"{proj.docs_rel}/prototype/proposals/{name}"
    sources = (f"the screen files in {base}/{variant}/screens/ (and its _shared/ files)" if variant else
               f"each variant's screen files and idea.md in {base}/<variant>/")
    return (f"error: {shown} is generated by build-prototype.py from the screen files of the proposal {name}; a hand "
            f"edit is lost on the next build\nfix: edit {sources}, then rebuild: "
            f"{proj.script('build-prototype.py')} --proposal {H._safe_arg(name)}")


_PROPOSAL_PAGES = ("prototype.html", "app.html", "screens.html")


def _proposal_page(proj: H.Project, in_project: str) -> Optional[tuple]:
    """(name, variant or None) when this project path is where `build-prototype.py --proposal` writes a page:
    <docs>/prototype/proposals/<name>/index.html or <name>/<variant>/{prototype,app,screens}.html; else None."""
    f = H.fold
    base = f"{f(proj.docs_rel)}/prototype/proposals/"
    if not f(in_project).startswith(base):
        return None
    parts = in_project[len(base):].split("/")
    if len(parts) == 2 and parts[0] and f(parts[1]) == f("index.html"):
        return parts[0], None
    if len(parts) == 3 and parts[0] and parts[1] and f(parts[2]) in {f(n) for n in _PROPOSAL_PAGES}:
        return parts[0], parts[1]
    return None


def _proposal_header(path: str) -> bool:
    """The page carries the header `build-prototype.py --proposal NAME` writes (the test build-prototype.py and
    build-tokens.py use to refresh it): a page another tool generated there, or a hand-written one, is not Plumb's."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(2000).decode("utf-8", "replace")
    except OSError:
        return False
    head = "\n".join(head.splitlines()[:5])
    return (_generated_header(path) and "plumb:start" not in head
            and re.search(r"build-prototype\.py --proposal \S", head) is not None)


def _map_output(proj: H.Project, shown: str) -> str:
    cmd = proj.script("build-prototype.py")
    return (f"error: {shown} is generated: build-prototype.py is its only writer\n"
            f"fix: change it through {cmd} --map ID --route=ROUTE --files GLOB or {cmd} --synced ID; {cmd} --approve ID "
            f"only after the user said yes to that screen")


def _kiro_own(proj: H.Project, shown: str, base: str) -> str:
    home = os.path.realpath(os.path.expanduser("~"))
    scope = "" if os.path.realpath(base) == home else f" --project {H._safe_arg(base)}"
    kiro = H._safe_arg(os.path.join(H.plugin_root(), "scripts", "kiro.py"))
    return (f"error: {shown} is Plumb's Kiro file, written by kiro.py; a hand edit is lost on the next install and can "
            f"switch Plumb's checks off\n"
            f"ask the user: to refresh it, run {proj.python} {kiro} install{scope} yourself; to turn a check off, change "
            f"Edit check: or End-of-turn check: in PLUMB.md (/plumb:update for design changes)")


def guard(proj: H.Project, path: str) -> Optional[str]:
    """The refusal for writing this absolute path by hand, or None."""
    if H.under(path, H.plugin_root()) is not None:
        return _own(path)
    in_project = H.under(path, proj.root_s)
    shown = in_project if in_project else path
    kiro_base = H.kiro_own_file(path)  # a marked .kiro/hooks/plumb.json or .kiro/skills/plumb-<name>/ (any .kiro)
    if kiro_base is not None:
        return _kiro_own(proj, shown, kiro_base)
    f = H.fold  # compare paths without case where the file system ignores it
    if proj.skill_dir is not None:
        in_skill = H.under(path, str(proj.skill_dir))
        if in_skill:
            parts = f(in_skill).split("/")
            if ((len(parts) == 2 and parts[0] == "scripts" and parts[1].endswith(".py"))
                    or (len(parts) >= 2 and parts[0] == "templates") or f(in_skill) == f("assets/platforms/README.md")):
                return _own(shown)
            if any(re.fullmatch(rx, in_skill, _case()) for rx in _PLATFORM_OUTPUTS):
                return _tokens_output(proj, shown)
    home = proj.home_root()
    in_home = H.under(path, home)
    if in_home and f(in_home) in {f(c) for c in proj.copies}:
        return _tokens_output(proj, in_home if home == proj.root_s else path)
    if not in_project:
        return None
    docs, here = f(proj.docs_rel), f(in_project)
    if here == f"{docs}/specimen.html":
        return _tokens_output(proj, shown)
    if here in (f"{docs}/prototype.html", f"{docs}/app.html", f"{docs}/screens.html"):
        if not os.path.isfile(path) or _prototype_header(path):
            return _prototype_output(proj, shown)
        return None
    if here == f"{docs}/prototype/screens.json":
        return _map_output(proj, shown)
    if here.startswith(f"{docs}/tours/") and here.endswith(".html") and "/" not in here[len(docs) + 7:]:
        if not os.path.isfile(path) or _prototype_header(path):
            return _tour_output(proj, shown, in_project[len(docs) + 7:-len(".html")])
    proposal = _proposal_page(proj, in_project)
    if proposal is not None and (not os.path.isfile(path) or _proposal_header(path)):
        return _proposal_output(proj, shown, *proposal)
    if re.search(_THEME, in_project, _case()) and os.path.isfile(path) and _generated_header(path):
        return _tokens_output(proj, shown)
    return None


def is_copy(proj: H.Project, path: str) -> bool:
    """The path is one of the web copies ($extensions.plumb.web.copies), where Plumb owns only its marked block."""
    in_home = H.under(path, proj.home_root())
    return bool(in_home) and H.fold(in_home) in {H.fold(c) for c in proj.copies}


def copy_edit_keeps_block(path: str, change: H.Change) -> bool:
    """True when this edit to a web copy leaves Plumb's block exactly as it is: the rest of the file is the project's.
    A copy with no block yet is the project's own file (the next build adds the block), unless it is a whole file an
    older build generated (its GENERATED header); so is one with broken markers (the build refuses it until they are
    fixed by hand). A delete or move, or an edit whose result cannot be known (an old string not in the file), counts
    as changing the block; an apply_patch update that does not apply is judged by its own lines
    (unapplied_patch_keeps_block)."""
    if change.kind in ("delete", "move", "path"):
        return False
    try:
        with open(path, "rb") as fh:
            before: Optional[str] = H.normalise(fh.read().decode("utf-8", "replace"))
    except FileNotFoundError:
        before = None
    except OSError:
        return False
    if before is None:
        return True  # no file yet: nothing generated to protect
    block = H.block_text(before)
    if block is None:
        if H.BLOCK_START in before or H.BLOCK_END in before:
            return True  # broken markers (no edit can break them: it would change the block): the build refuses
            #              until they are fixed, so let them be fixed by hand
        return not _generated_header(path)
    after = change.after(before)
    if after is None and change.kind == "update":
        return unapplied_patch_keeps_block(before, change)
    return after is not None and H.block_text(after) == block


def unapplied_patch_keeps_block(before: str, change: H.Change) -> bool:
    """An apply_patch update whose hunks do not apply to the copy (models often send context lines that are not in the
    file): judged by its own lines instead of refused. It changes Plumb's block when it adds a block marker, removes a
    line that is found only inside the block, or a hunk's context lines are found only inside the block (between the
    markers). Anything else (context found outside, or nowhere: apply_patch cannot place it in the block either) is
    the project's part of the file."""
    if H.BLOCK_START in change.added() or H.BLOCK_END in change.added():
        return False
    lines = before.split("\n")
    start = next(i for i, ln in enumerate(lines) if H.BLOCK_START in ln)
    end = next(i for i, ln in enumerate(lines) if H.BLOCK_END in ln)

    def where(text: str) -> List[int]:
        want = text.strip()
        if not re.search(r"\w", want):  # a lone "}" or ");" is everywhere: it places nothing
            return []
        return [i for i, ln in enumerate(lines) if ln.strip() == want]

    for hunk in change.hunks:
        removed = [ln[1:] for ln in hunk.lines if ln[0] == "-" and ln[1:].strip()]
        context = [ln[1:] for ln in hunk.lines if ln[0] == " " and ln[1:].strip()]
        for text in removed:
            found = where(text)
            if found and all(start <= i <= end for i in found):
                return False
        anchors = [i for text in context for i in where(text)]
        if anchors and all(start < i < end for i in anchors):
            return False
    return True


def _has_block(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return H.BLOCK_START in fh.read().decode("utf-8", "replace")
    except OSError:
        return False


def copy_shown(proj: H.Project, path: str) -> str:
    """How a web copy's path is shown in a refusal: relative to the project that owns the skill when that is this
    project, else in full (as guard() shows it)."""
    home = proj.home_root()
    in_home = H.under(path, home)
    return in_home if in_home and home == proj.root_s else path


def _copy_block_output(proj: H.Project, shown: str) -> str:
    return (f"error: {shown} is generated from the design tokens between its /* plumb:start ... */ and /* plumb:end */ "
            f"lines, and this edit changes that block; a hand edit there is lost on the next build\n"
            f"fix: edit only outside the block (the rest of {shown} is yours), or change the tokens with /plumb:update, "
            f"then rebuild: {proj.script('build-tokens.py')}")


def _copy_shell_output(proj: H.Project, shown: str) -> str:
    return (f"error: {shown} is generated only between its /* plumb:start ... */ and /* plumb:end */ lines (the rest of "
            f"the file is yours), and a shell command that writes, moves or removes the file cannot be checked for what "
            f"it does to that block\n"
            f"fix: change the lines outside the block with the edit tool (Edit / apply_patch / str_replace), and the "
            f"block through the tokens with /plumb:update, then rebuild: {proj.script('build-tokens.py')}")


def guarded_files(proj: H.Project, cwd: str) -> List[str]:
    """The guarded files that exist now (the plugin root as one entry), for a removal of a folder that may hold them."""
    found: List[str] = [H.plugin_root()]
    if proj.skill_dir is not None:
        skill = proj.skill_dir
        for pattern in ("scripts/*.py", "templates/**/*", "assets/platforms/README.md",
                        "assets/platforms/web/tokens.css", "assets/platforms/web/tailwind.tokens.js",
                        "assets/platforms/mobile/ios/*Theme.swift", "assets/platforms/mobile/android/*Theme.kt"):
            found += [str(f) for f in skill.glob(pattern) if f.is_file()]
    home = proj.home_root()
    found += [os.path.join(home, c) for c in proj.copies]
    docs = os.path.join(proj.root_s, proj.docs_rel)
    found += [os.path.join(docs, n) for n in ("specimen.html", "prototype.html", "app.html", "screens.html",
                                               os.path.join("prototype", "screens.json"))]
    found += [str(f) for f in Path(docs, "tours").glob("*.html")]
    proposals = Path(docs, "prototype", "proposals")
    found += [str(f) for pattern in ("*/index.html",) + tuple(f"*/*/{n}" for n in _PROPOSAL_PAGES)
              for f in proposals.glob(pattern) if f.is_file() and _proposal_header(str(f))]
    for kiro_base in {proj.root_s, os.path.expanduser("~"), cwd}:
        kiro = Path(kiro_base, ".kiro")
        found.append(str(kiro / "hooks" / "plumb.json"))
        found += [str(f) for f in kiro.glob("skills/plumb-*/SKILL.md")]
    return [os.path.realpath(f) for f in found if os.path.exists(f)]


def removal_guard(proj: H.Project, path: str, cwd: str) -> Optional[str]:
    """The refusal for removing (or moving away) this absolute path by hand: a guarded file, or a folder that holds
    one; else None."""
    why = guard(proj, path)
    if why or not os.path.isdir(path):
        return why
    for f in guarded_files(proj, cwd):
        if H.under(f, path) is not None:
            why = guard(proj, f)
            if why:
                return why
    return None


class _Checked:
    """What one shell command's checks share: the (path, removal) pairs found allowed (the shell reader and the earlier
    reader list mostly the same paths) and the real paths worked out (H.real_path)."""

    def __init__(self) -> None:
        self.allowed: set = set()
        self.reals: dict = {}


def _shell_paths_refusal(proj: H.Project, paths: List[str], removal: bool, cwd: str,
                         checked: Optional[_Checked] = None) -> Optional[str]:
    """The refusal for the first of these paths (absolute, normalised) the guard refuses, or None."""
    checked = checked or _Checked()
    for target in paths:
        key = (target, removal)
        if key in checked.allowed:
            continue
        path = H.real_path(target, checked.reals)
        why = removal_guard(proj, path, cwd) if removal else guard(proj, path)
        if why and is_copy(proj, path) and _has_block(path):
            why = _copy_shell_output(proj, copy_shown(proj, path))
        if why:
            return why
        checked.allowed.add(key)
    return None


SHELL_HUGE = 64 * 1024  # characters: a longer command is not read; it is refused when it names a guarded path
NAMES_BUDGET = 3.0  # seconds to look for guarded paths in a command the reader could not read; past it: refused
_DOCS_PAGES = ("specimen.html", "prototype.html", "app.html", "screens.html", "prototype/screens.json")
_FIXED_NAMES = ("specimen.html", "prototype.html", "app.html", "screens.html", "screens.json", "build-tokens.py",
                "build-prototype.py")
_WORD_SPLIT = re.compile(r"[\s'\"`=,;()<>|&{}\[\]]+")
_MAX_WORDS = 20000


def _glob_match(path: str, pattern: str) -> bool:
    """A glob match the way the shell does it: *, ? and [...] never cross a /, so both have the same number of parts."""
    a, b = path.replace("\\", "/").split("/"), pattern.replace("\\", "/").split("/")
    return len(a) == len(b) and all(fnmatch.fnmatchcase(x, y) for x, y in zip(a, b))


class _Guarded:
    """The guard's own rule, for the words of a command: a path is guarded when guard() protects it (whether it exists
    or not: the plugin root, the skill's [P] files, a theme, a tour …) or it is a folder that holds a guarded file (a
    guarded folder or a parent of one). File names of the guarded files are matched as text too."""

    def __init__(self, proj: H.Project, cwd: str) -> None:
        self.proj = proj
        self.files = guarded_files(proj, cwd)  # existing ones, the plugin root included
        self.names = sorted(set(_FIXED_NAMES) | {os.path.basename(f) for f in self.files if os.path.isfile(f)})
        self.seen: dict = {}
        self.reals: dict = {}  # H.real_path's work, shared by every word of the command
        root = os.path.realpath(proj.root_s)
        # the folders Plumb owns whole: the docs folder (its generated pages), the design-system skill, its scripts/
        # and templates/ (never the project root or a folder above it, never the folder of a project file Plumb
        # writes a block into, such as app/ for app/globals.css)
        folders = {os.path.realpath(os.path.join(proj.root_s, proj.docs_rel))}
        if proj.skill_dir is not None:
            skill = os.path.realpath(str(proj.skill_dir))
            folders |= {skill, os.path.join(skill, "scripts"), os.path.join(skill, "templates")}
        self.folders = {f for f in folders if H.under(root, f) is None}
        self.patterns = [f for f in self.files if os.path.isfile(f)] + [
            os.path.realpath(os.path.join(proj.root_s, proj.docs_rel, n)) for n in _DOCS_PAGES]

    def path(self, path: str) -> bool:
        try:
            real = H.real_path(path, self.reals)
            if real not in self.seen:
                self.seen[real] = bool(guard(self.proj, real)) or (
                    os.path.isdir(real) and any(H.under(f, real) is not None for f in self.files))
            return self.seen[real]
        except (OSError, ValueError):
            return True  # a path the system cannot even look up: not proved safe

    def glob_hit(self, pattern: str) -> Optional[str]:
        """A guarded file a glob pattern (an absolute path) can match: an existing one, a generated page, or a file not
        built yet that guard() would protect (the pattern with its wildcards filled in)."""
        hit = next((f for f in self.patterns if _glob_match(f, pattern)), None)
        if hit is None:
            sample = re.sub(r"\[[^\]]*\]", "x", pattern).replace("*", "x").replace("?", "x")
            hit = sample if guard(self.proj, sample) else None
        return hit

    def could_yield(self, items, deadline: float) -> List[str]:
        """What a loop source could hold that matters: for each item, the guarded paths it could yield, in the form the
        shell would give them (a literal as written; a glob's guarded matches; `ls DIR`'s guarded entries as bare names
        and as DIR/name; `find DIR`'s guarded files, filtered by -name / -type / -mindepth / -maxdepth). Only the
        guarded paths are matched, never the file system."""
        out: List[str] = []
        for kind, value, bases in items:
            if H.clock() >= deadline:
                break
            if kind == "lit":
                out.append(value)
                continue
            folder = value[0] if kind == "find" else value
            for base in bases:
                try:
                    full = os.path.realpath(folder if os.path.isabs(folder) else os.path.join(base, folder))
                except (OSError, ValueError):
                    continue
                if kind == "glob":
                    sample = re.sub(r"\[[^\]]*\]", "x", full).replace("*", "x").replace("?", "x")
                    hits = [g for g in self.patterns if _glob_match(g, full)]
                    hits += [sample] if guard(self.proj, sample) else []
                    real_base = os.path.realpath(base)
                    out += [h if os.path.isabs(folder) else os.path.relpath(h, real_base) for h in hits]
                elif kind == "ls":  # ls DIR prints bare names (DIR/name with several folders)
                    for g in self.patterns:
                        if os.path.dirname(g) == full:
                            out += [os.path.basename(g), os.path.join(folder, os.path.basename(g))]
                else:  # find DIR [-name PAT] [-type f|d] prints DIR/relative
                    _dir, pattern, icase, ftype, mindepth, maxdepth = value
                    pool = sorted(self.folders) if ftype == "d" else (self.patterns if ftype in ("", "f") else [])
                    for g in pool:
                        rel = H.under(g, full)
                        if rel is None:
                            continue
                        depth = len(rel.split("/")) if rel else 0
                        if depth < mindepth or (maxdepth is not None and depth > maxdepth):
                            continue
                        name = os.path.basename(g)
                        if pattern and not fnmatch.fnmatchcase(name.lower() if icase else name,
                                                               pattern.lower() if icase else pattern):
                            continue
                        out.append(os.path.join(folder, os.path.relpath(g, full)))
        return list(dict.fromkeys(out))[:_MAX_WORDS]

    def target(self, words: List[str], bases, deadline: float) -> Optional[str]:
        """For a target the reader could not work out: the first guarded file or guarded folder (one Plumb owns whole)
        that one of its words names by its full path (from one of bases, or absolute; a glob by what it can match),
        shown from the project root, or None. Each word is a path as it stands (never split again). A bare file name,
        `.` and the project root never count."""
        root = os.path.realpath(self.proj.root_s)
        for word in dict.fromkeys(w for w in words if w and not w.startswith(("$", "-", "\x00"))):
            if H.clock() >= deadline:
                return "a path Plumb ran out of time to check"
            w = os.path.expanduser(word.replace("\\", "/") if os.sep == "/" else word).rstrip("/\\")
            if not w or not re.search(r"[/\\]", w) or "$" in w or "`" in w:
                continue  # a bare name, or a word with a part still unknown: only a full path counts
            for form, base in ((f, b) for f in H.path_forms(w) for b in bases):
                try:
                    real = os.path.realpath(os.path.normpath(form if os.path.isabs(form) else os.path.join(base, form)))
                except (OSError, ValueError):
                    continue
                if re.search(r"[*?\[]", w):
                    hit = self.glob_hit(real)
                    if hit:
                        return H.under(hit, root) or hit
                elif real in self.folders or guard(self.proj, real):
                    return H.under(real, root) or real
        return None

    def text(self, text: str, bases, deadline: float) -> Optional[str]:
        """The first guarded name or path in text (each word resolved in each of bases, ~ and $VARS expanded), or
        None. A bare word counts too: `docs` names the folder that holds the generated pages."""
        name = next((n for n in self.names if n in text), None)
        if name is not None:
            return name
        words = [w for w in _WORD_SPLIT.split(text) if w]
        if len(words) > _MAX_WORDS:
            return "a path among more words than Plumb checks"
        for word in dict.fromkeys(words):
            if H.clock() >= deadline:
                return "a path Plumb ran out of time to check"
            w = word[7:] if word.startswith("file://") else word
            w = os.path.expanduser(os.path.expandvars(w.replace("\\", "/") if os.sep == "/" else w))
            for form, base in ((f, b) for f in H.path_forms(w) for b in bases):
                if self.path(os.path.normpath(form if os.path.isabs(form) else os.path.join(base, form))):
                    return word
        return None


def _proven(proj: H.Project, eff: "H.ShellEffects", cwd: str, rule: Optional[_Guarded] = None) -> bool:
    """The shell reader proves the command's guarded paths are data or reads: (a) a here-document / echo / printf / tee
    text written to a file the command does not use again, (b) a read-only program's words, (c) inline code that gives
    each guarded literal straight to a read sink and writes only to plain literals away
    from the guarded files, (d) a git commit message. Every other word (eff.other) must name no guarded path by the
    guard's own rule."""
    if eff.unsure:
        return False
    rule = rule or _Guarded(proj, cwd)
    deadline = H.clock() + NAMES_BUDGET
    if any(rule.text(text, bases, deadline) for text, bases in eff.other):
        return False
    for target in eff.code_writes:
        real = os.path.realpath(target)
        if rule.path(real) or any(os.path.dirname(f) == os.path.dirname(real) for f in rule.files):
            return False
    return True


_MAX_TRIES = 20000  # loop values tried in the targets of one command; past it the command-wide rule decides


def _loop_refusal(proj: H.Project, eff: "H.ShellEffects", rule: "_Guarded", cwd: str) -> Optional[str]:
    """A write or removal target that uses a loop variable (or ${!N}): refused when the variable could hold a guarded
    path, or a name the target turns into one (each value _Guarded.could_yield gives is put into the target, after the
    command's other variables); with a source the reader does not know, or a target that still has an unknown part,
    when the target's own text names a guarded folder or file, or the command names a guarded path anywhere. Past the
    number of tries or the time the check has, the command-wide rule decides alone: refused when the command names a
    guarded path, else the earlier reader decides."""
    deadline = H.clock() + NAMES_BUDGET
    command_hit: List[Optional[str]] = []
    literal_seen: dict = {}
    yields: dict = {}
    tries = 0

    def in_command() -> Optional[str]:
        if not command_hit:
            command_hit.append(rule.target(eff.command_words(), tuple(dict.fromkeys((cwd, proj.root_s))),
                                           H.clock() + NAMES_BUDGET))
        return command_hit[0]

    def unknown(word: str, scope) -> Optional[str]:
        literal = H.literal_part(word)
        if literal not in literal_seen:
            literal_seen[literal] = rule.target([literal], scope.bases, deadline) if literal.strip("/.") else None
        hit = literal_seen[literal] or in_command()
        if hit is None:
            return None
        return (f"error: this shell command writes to or removes a path that comes from a source Plumb cannot read "
                f"({word}), and it names {hit}, a path Plumb guards\nfix: write each target path out in full so "
                f"Plumb can check it (and change {hit} the way Plumb's own message for it says)")

    def past_limits() -> Optional[str]:
        hit = in_command()
        if hit is None:
            return None  # nothing guarded is named: the earlier reader decides
        return (f"error: this shell command is too large for Plumb to check (more loop targets or values than it tries "
                f"in time), and it names {hit}, a path Plumb guards\nfix: split it into shorter loops, or write each "
                f"target path out in full (and change {hit} the way Plumb's own message for it says)")

    for kind, word, sources, scope in eff.loop_targets:
        if H.clock() >= deadline or "#" in sources:
            return past_limits()
        if any(items == [H._ANY] for items in sources.values()):
            why = unknown(word, scope)
            if why:
                return why
            continue
        choices = []
        for name, items in sources.items():
            if id(items) not in yields:
                yields[id(items)] = rule.could_yield(items, deadline)
            choices.append([(name, v) for v in yields[id(items)]])
        count = 1
        for options in choices:
            count *= len(options)
        tries += count
        if tries > _MAX_TRIES:
            return past_limits()
        combos = [[]]
        for options in choices:
            combos = [c + [o] for c in combos for o in options]
        for combo in combos:
            if H.clock() >= deadline:
                return past_limits()
            paths = H.substitute(word, dict(combo), scope, proj.root_s)
            if paths is None:  # a part still unknown after the variables ($TMPDIR, $OUT): the target's own text only
                literal = H.literal_part(word)
                if literal.strip("/.") and literal not in literal_seen:
                    literal_seen[literal] = rule.target([literal], scope.bases, deadline)
                hit = literal_seen.get(literal) if literal.strip("/.") else None
                if hit is not None:
                    return (f"error: this shell command writes to or removes {word}, built from {hit}, a path Plumb "
                            f"guards\nfix: write each target path out in full so Plumb can check it (and change {hit} "
                            f"the way Plumb's own message for it says)")
                break
            why = _shell_paths_refusal(proj, paths, kind in (1, 2), cwd)
            if why:
                return why
    return None


def _unread(proj: H.Project, command: str, base: str, cwd: str, rule: Optional[_Guarded] = None) -> Optional[str]:
    """For a command the reader could not read: the first of its words that names a guarded file or folder (or a
    parent of one) by the guard's rule, or None."""
    bases = tuple(dict.fromkeys((base, cwd)))
    return (rule or _Guarded(proj, cwd)).text(command, bases, H.clock() + NAMES_BUDGET)


def _unread_refusal(hit: str, why: str) -> str:
    return (f"error: Plumb could not check this shell command ({why}) and it names {hit}, a path Plumb guards\n"
            f"fix: split it into shorter, simpler commands (and change {hit} the way Plumb's own message for it says)")


def shell_refusal(proj: H.Project, command: str, base: str, cwd: str) -> Optional[str]:
    """The refusal for a shell command, or None. The earlier reader (_shell_legacy.py) decides, and the shell reader
    adds what it finds: refused when the shell reader finds a guarded file among its write, removal or folder write
    targets; and whenever the earlier reader would refuse it, unless the shell reader proves the guarded paths are only
    data or reads (_proven). A command it does not read (over SHELL_HUGE, brackets nested past the reader's depth) or
    one the reader failed on (a crash, the recursion limit) is refused when any of its words names a guarded file or
    folder; a write or removal target it cannot work out is refused when it names a guarded path in full
    (_Guarded.target); a reader that ran out of time leaves the decision to the earlier reader. A crash, a timeout
    and a command too long to read are logged once, with the real outcome."""
    command = command.replace("\x00", "")  # a NUL byte never reaches a shell: read the rest
    if not H.WRITE_HINT.search(command):
        return None
    built: List[_Guarded] = []

    def rule() -> _Guarded:  # built once per command, only when needed (it globs the guarded files)
        if not built:
            built.append(_Guarded(proj, cwd))
        return built[0]

    if len(command) > SHELL_HUGE:
        size = f"{len(command) // 1024} KB"
        hit = _unread(proj, command, base, cwd, rule())
        H.log_failure(f"a shell command of {size}, too long to read", "the command read (a guarded path in it refuses "
                      "it)", category="timeout", outcome=f"{'refused' if hit else 'allowed'} without reading it")
        return _unread_refusal(hit, size) if hit else None
    eff = H.shell_effects(command, base, proj.root_s)
    checked = _Checked()  # paths found allowed are not checked again
    why = (_shell_paths_refusal(proj, eff.writes, False, cwd, checked)
           or _shell_paths_refusal(proj, eff.removals, True, cwd, checked)
           or _shell_paths_refusal(proj, eff.folder_writes, True, cwd, checked))
    if why is None and eff.loop_targets:
        why = _loop_refusal(proj, eff, rule(), cwd)
    if why is None and eff.computed:  # a target it cannot work out ($( ), `…`, ${…}, a loop variable) naming one
        deadline = H.clock() + NAMES_BUDGET
        named = next((n for n in (rule().target(words, bases, deadline) for words, bases in eff.computed) if n), None)
        if named is not None:
            why = (f"error: this shell command writes to or removes a path Plumb cannot work out, and that path is "
                   f"built from {named}, a path Plumb guards\nfix: write each target path out in full so Plumb can "
                   f"check it (and change {named} the way Plumb's own message for it says)")
    hit = None
    if why is None and eff.trouble is not None and eff.trouble[1] in ("crash", "deep"):
        hit = _unread(proj, command, base, cwd, rule())
        if hit is not None:
            why = _unread_refusal(hit, "it is too complex to read")
    if why is None:
        floor = (_shell_paths_refusal(proj, H.legacy_targets(command, base), False, cwd, checked)
                 or _shell_paths_refusal(proj, H.legacy_removals(command, base), True, cwd, checked))
        if floor is not None and not _proven(proj, eff, cwd, rule()):
            why = floor
    if eff.trouble is not None and eff.trouble[1] != "deep":  # deep nesting is the command's, not Plumb's mistake
        given, category, exc = eff.trouble
        outcome = ("refused without reading it (it names a guarded path)" if hit is not None
                   else f"{'refused' if why else 'allowed'}: the earlier reader decided")
        H.log_failure(given, "the command read within the budget", category=category, exc=exc, outcome=outcome)
    return why


# ---------------------------------------------------------------- prototype first and the edit check


def _approved(bp, root: Path, docs: str, entry: dict) -> bool:
    approved = entry.get("approved")
    screen = root / docs / "prototype" / "screens" / f"{entry.get('id')}.html"
    if not isinstance(approved, dict) or not screen.is_file():
        return False
    try:
        return approved.get("hash") == bp.screen_file_hash(screen)  # the screen file and its folder's _shared files
    except (OSError, UnicodeDecodeError):
        return False


def prototype_first(proj: H.Project, A, settings: dict, rel: str, before: Optional[str], after: str) -> Optional[str]:
    root = Path(proj.root_s)
    roots = A.route_roots(settings)  # PLUMB.md `Routes:` only; not recorded: fail open (session start says so)
    if not roots:
        return None
    routes = A.discover_routes(root, [(rel, after)], roots)
    if not routes:
        return None
    old = {A._route_key(r.route) for r in A.discover_routes(root, [(rel, before)], roots)} if before is not None else set()
    routes = [r for r in routes if A._route_key(r.route) not in old]
    if not routes:
        return None
    bp = A.load_build_prototype()
    if bp is None:
        H.note("build-prototype.py is missing next to audit.py, so the prototype-first check is skipped")
        return None
    docs = str(settings.get("docs_dir") or "docs/design").replace("\\", "/").strip().strip("/") or "docs/design"
    map_rel = f"{docs}/prototype/screens.json"
    entries = dict(bp.read_map(root / map_rel, map_rel))
    folder = root / docs / "prototype" / "screens"
    for r in routes:
        target = r.source or r.file
        slug = A._route_slug(r.route)
        if slug not in entries and (folder / f"{slug}.html").is_file():
            entries[slug] = {"id": slug, "approved": None, "files": [], "route": None}  # a screen not built into the map yet
        covering = [e for e in entries.values() if isinstance(e, dict) and (
            A.same_route(e.get("route"), r.route) or e.get("id") == slug
            or any(isinstance(g, str) and A.P.glob_rx(g).match(target) for g in (e.get("files") or [])))]
        if any(_approved(bp, root, docs, e) for e in covering):
            continue
        what = f"{rel} is a new screen" if r.file == rel and r.line == 1 else f"{rel} adds route {r.route}, a new screen"
        if covering:
            sid = covering[0].get("id")
            return (f"error: {what} whose prototype (screen {sid}) is not approved yet\n"
                    f"ask the user: approve screen {sid} in {docs}/prototype.html#screen-{sid}? Only after their yes, record it: "
                    f"{proj.script('build-prototype.py')} --approve {sid}")
        return (f"error: {what} with no approved prototype\n"
                f"fix: /plumb:prototype {slug} (design the screen, get the user's approval, then build it to match)")
    return None


def edit_refusal(proj: H.Project, rel: str, errors: list) -> str:
    n = len(errors)
    lines = [f"Plumb edit check: this edit adds {n} design-system error{'' if n == 1 else 's'} to {rel}"]
    for f in errors[:MAX_ISSUES]:
        lines.append(f"error: line {f.line}: {f.message}")
        lines.append(f.fix if f.fix.startswith("ask the user:") else f"fix: {f.fix}")
    if n > MAX_ISSUES:
        more = n - MAX_ISSUES
        lines.append(f"... and {more} more error{'' if more == 1 else 's'}: {proj.script('audit.py')} {rel} lists them all")
    return "\n".join(lines)


def checks(p: H.Payload, proj: H.Project, base: str) -> Optional[str]:
    sync, edit_on = proj.on("Prototype sync"), proj.on("Edit check")
    if not (sync or edit_on) or not proj.skill_ok:
        return None
    items = []
    for c in p.changes:
        if c.kind in ("delete", "move", "path"):
            continue
        path = H.resolve(c.path, base)
        rel = H.under(path, proj.root_s)
        if not rel or os.path.splitext(rel)[1].lower() not in H.UI_EXT:
            continue
        items.append((c, path, rel))
    if not items:
        return None
    A = H.load_script("audit.py", "plumb_audit")
    if A is None:
        return None
    try:
        root = Path(proj.root_s)
        doc = A.load_doc(proj.skill_dir)
        settings = A.make_settings(root, doc)
        wanted = A.ui_matcher(root, proj.skill_dir, settings)
        for c, path, rel in items:
            before = None
            if os.path.isfile(path):
                if os.path.getsize(path) > A.MAX_BYTES:
                    continue
                before = A.read_source(Path(path))
            after = c.after(before)
            partial = after is None and c.kind == "update" and before is not None
            if after is None and not partial:
                continue
            if sync:
                why = prototype_first(proj, A, settings, rel, before, after if after is not None else c.added())
                if why:
                    return why
            if edit_on and wanted(root / rel):
                if partial:  # the hunks do not apply to the file: check what they add against what they remove
                    new = A.quick(rel, c.removed(), c.added(), doc, settings)
                else:
                    new = A.quick(rel, before, after, doc, settings)
                errors = [f for f in new if f.severity == "error"]
                if errors:
                    return edit_refusal(proj, rel, errors)
    except Exception as exc:  # noqa: BLE001 - the checks never break an edit
        H.note(f"the design checks were skipped ({type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''})")
        H.log_failure(f"the design checks were skipped ({type(exc).__name__}: {exc})",
                      "the edit check and the prototype-first check run on this edit", exc=exc)
        return None
    return None


def main() -> int:
    p = H.read_payload()
    if p is None:
        return 0
    proj = H.load_project(p)
    if proj is None:
        return 0
    base = p.cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if p.command is not None:
        why = shell_refusal(proj, p.command, base, p.cwd or base)
        return H.refuse(why, p.copilot) if why else 0
    if not p.changes:
        return 0
    for c in p.changes:
        path = H.resolve(c.path, base)
        why = guard(proj, path)
        if why and is_copy(proj, path):
            if copy_edit_keeps_block(path, c):
                why = None  # an edit outside Plumb's block: the rest of a web copy is the project's
            elif _has_block(path):
                why = _copy_block_output(proj, copy_shown(proj, path))
        if why:
            return H.refuse(why, p.copilot)
    why = checks(p, proj, base)
    return H.refuse(why, p.copilot) if why else 0


if __name__ == "__main__":
    H.utf8_stdio()
    try:
        code = main()
    except Exception as _exc:  # noqa: BLE001 - never break a tool call on odd input
        H.note(f"pre-edit check skipped ({type(_exc).__name__})")
        H.log_failure(f"pre-edit check skipped ({type(_exc).__name__}: {_exc})",
                      "the guards and checks run, or allow the tool call quietly", exc=_exc)
        code = 0
    sys.exit(code)
