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
     <docs>/app.html, <docs>/screens.html, <docs>/prototype/screens.json and <docs>/tours/*.html (a tour page that does
     not carry the GENERATED header is someone's own page and is left alone);
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
   targets put together from the code's constants. A target the reader cannot work out ($( ), backticks, ${…}, a
   for / read loop variable) is refused when its text, the value of a variable it uses or the words a loop variable
   takes name a guarded file or folder by its full path (_Guarded.target). A refusal of the earlier reader becomes an
   allow only when the shell reader proves it (_proven): (a) a here-document / echo / printf / tee text written to a
   file the same command does not run, import, name again or leave where a program picks it up (a Makefile whose
   lines run the scripts is fine; sitecustomize.py, .bashrc, a git hook are not), (b) a read-only program's words,
   (c) inline code that only reads its guarded literals (json.load, importlib, Path.read_text) and writes only to
   plain literals away from them, (d) a git commit message (-m / -F / -t values, a here-document on stdin),
   unless git is given an option that runs something, a variable is set before it, or the command wrote a hook. Every
   other word must name no guarded path by guard()'s own rule (files that do not exist yet, the plugin root, a
   folder that holds a guarded file or a parent of one). Running build-tokens.py or build-prototype.py, and anything
   that writes elsewhere, is
   allowed. Removing or moving away a guarded file (rm, rmdir, unlink, del, Remove-Item, git rm, the sources of mv /
   Move-Item / git mv, os.remove, shutil.rmtree), or a folder that holds one, is refused the same way; ~, $HOME,
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

import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _hooklib as H  # noqa: E402

MAX_ISSUES = 10
_CASE = re.I if H.CASELESS else 0
_THEME = re.compile(r"Theme\.(?:swift|kt)$", _CASE)
_PLATFORM_OUTPUTS = (re.compile(r"assets/platforms/web/(?:tokens\.css|tailwind\.tokens\.js)", _CASE),
                     re.compile(r"assets/platforms/mobile/ios/[^/]*Theme\.swift", _CASE),
                     re.compile(r"assets/platforms/mobile/android/[^/]*Theme\.kt", _CASE))


def _generated_header(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(1500).decode("utf-8", "replace")
    except OSError:
        return False
    head = "\n".join(head.splitlines()[:5])
    return "GENERATED" in head and re.search(r"do not edit", head, re.I) is not None


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
            if any(rx.fullmatch(in_skill) for rx in _PLATFORM_OUTPUTS):
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
        return _prototype_output(proj, shown)
    if here == f"{docs}/prototype/screens.json":
        return _map_output(proj, shown)
    if here.startswith(f"{docs}/tours/") and here.endswith(".html") and "/" not in here[len(docs) + 7:]:
        if not os.path.isfile(path) or _generated_header(path):
            return _prototype_output(proj, shown)
    if _THEME.search(in_project) and os.path.isfile(path) and _generated_header(path):
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


def _shell_paths_refusal(proj: H.Project, paths: List[str], removal: bool, cwd: str) -> Optional[str]:
    for target in paths:
        path = os.path.realpath(target)
        why = removal_guard(proj, path, cwd) if removal else guard(proj, path)
        if why and is_copy(proj, path) and _has_block(path):
            why = _copy_shell_output(proj, copy_shown(proj, path))
        if why:
            return why
    return None


SHELL_HUGE = 64 * 1024  # characters: a longer command is not read; it is refused when it names a guarded path
NAMES_BUDGET = 3.0  # seconds to look for guarded paths in a command the reader could not read; past it: refused
_FIXED_NAMES = ("specimen.html", "prototype.html", "app.html", "screens.html", "screens.json", "build-tokens.py",
                "build-prototype.py")
_WORD_SPLIT = re.compile(r"[\s'\"`=,;()<>|&{}\[\]]+")
_MAX_WORDS = 20000


class _Guarded:
    """The guard's own rule, for the words of a command: a path is guarded when guard() protects it (whether it exists
    or not: the plugin root, the skill's [P] files, a theme, a tour …) or it is a folder that holds a guarded file (a
    guarded folder or a parent of one). File names of the guarded files are matched as text too."""

    def __init__(self, proj: H.Project, cwd: str) -> None:
        self.proj = proj
        self.files = guarded_files(proj, cwd)  # existing ones, the plugin root included
        self.names = sorted(set(_FIXED_NAMES) | {os.path.basename(f) for f in self.files if os.path.isfile(f)})
        self.seen: dict = {}
        root = os.path.realpath(proj.root_s)
        folders = {os.path.dirname(f) for f in self.files if os.path.isfile(f)}
        folders.add(os.path.realpath(os.path.join(proj.root_s, proj.docs_rel)))
        if proj.skill_dir is not None:
            skill = os.path.realpath(str(proj.skill_dir))
            folders |= {skill, os.path.join(skill, "scripts"), os.path.join(skill, "templates")}
        # a guarded folder: one that holds guarded files itself (never the project root or a folder above it)
        self.folders = {f for f in folders if H.under(root, f) is None}

    def path(self, path: str) -> bool:
        try:
            real = os.path.realpath(path)
            if real not in self.seen:
                self.seen[real] = bool(guard(self.proj, real)) or (
                    os.path.isdir(real) and any(H.under(f, real) is not None for f in self.files))
            return self.seen[real]
        except (OSError, ValueError):
            return True  # a path the system cannot even look up: not proved safe

    def target(self, text: str, bases, deadline: float) -> Optional[str]:
        """For a target the reader could not work out: the first guarded file or guarded folder that a word of text
        names by its full path (from one of bases, or absolute; a glob by its folder), shown from the project root, or
        None. A bare file name, `.` and the project root never count."""
        for word in dict.fromkeys(w for w in _WORD_SPLIT.split(text) if w and not w.startswith(("$", "-"))):
            if time.monotonic() > deadline:
                return "a path Plumb ran out of time to check"
            w = os.path.expanduser(word.replace("\\", "/") if os.sep == "/" else word).rstrip("/\\")
            if not w or not re.search(r"[/\\]", w):
                continue  # a bare name: only a full path counts
            globbed = re.search(r"[*?\[]", w) is not None
            for base in bases:
                full = os.path.normpath(w if os.path.isabs(w) else os.path.join(base, w))
                candidates = [os.path.dirname(full)] if globbed else [full]
                for c in candidates:
                    try:
                        real = os.path.realpath(c)
                    except (OSError, ValueError):
                        continue
                    if real in self.folders or (not globbed and guard(self.proj, real)):
                        return H.under(real, os.path.realpath(self.proj.root_s)) or real
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
            if time.monotonic() > deadline:
                return "a path Plumb ran out of time to check"
            w = word[7:] if word.startswith("file://") else word
            w = os.path.expanduser(os.path.expandvars(w.replace("\\", "/") if os.sep == "/" else w))
            for base in bases:
                if self.path(os.path.normpath(w if os.path.isabs(w) else os.path.join(base, w))):
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
    deadline = time.monotonic() + NAMES_BUDGET
    if any(rule.text(text, bases, deadline) for text, bases in eff.other):
        return False
    for target in eff.code_writes:
        real = os.path.realpath(target)
        if rule.path(real) or any(os.path.dirname(f) == os.path.dirname(real) for f in rule.files):
            return False
    return True


def _unread(proj: H.Project, command: str, base: str, cwd: str, rule: Optional[_Guarded] = None) -> Optional[str]:
    """For a command the reader could not read: the first of its words that names a guarded file or folder (or a
    parent of one) by the guard's rule, or None."""
    return (rule or _Guarded(proj, cwd)).text(command, tuple(dict.fromkeys((base, cwd))), time.monotonic() + NAMES_BUDGET)


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
    (_Guarded.target); a reader that ran out of time leaves the decision to the earlier reader. A crash, a timeout and a command
    too long to read are logged once, with the real outcome."""
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
    why = (_shell_paths_refusal(proj, eff.writes, False, cwd) or _shell_paths_refusal(proj, eff.removals, True, cwd)
           or _shell_paths_refusal(proj, eff.folder_writes, True, cwd))
    if why is None and eff.computed:  # a target it cannot work out ($( ), `…`, ${…}, a loop variable) naming one
        deadline = time.monotonic() + NAMES_BUDGET
        named = next((n for n in (rule().target(text, bases, deadline) for text, bases in eff.computed) if n), None)
        if named is not None:
            why = (f"error: this shell command writes to a path Plumb cannot work out, and that path is built from "
                   f"{named}, a path Plumb guards\nfix: write each target path out in full so Plumb can check it (and "
                   f"change {named} the way Plumb's own message for it says)")
    hit = None
    if why is None and eff.trouble is not None and eff.trouble[1] in ("crash", "deep"):
        hit = _unread(proj, command, base, cwd, rule())
        if hit is not None:
            why = _unread_refusal(hit, "it is too complex to read")
    if why is None:
        floor = (_shell_paths_refusal(proj, H.legacy_targets(command, base), False, cwd)
                 or _shell_paths_refusal(proj, H.legacy_removals(command, base), True, cwd))
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
        return approved.get("hash") == bp.sha256_text(screen.read_bytes().decode("utf-8-sig", "replace"))
    except OSError:
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
