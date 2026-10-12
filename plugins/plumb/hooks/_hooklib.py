"""Shared code for Plumb's hooks (session_start.py, pre_edit.py, stop_check.py). Not a hook itself.

Claude Code and GitHub Copilot CLI run the same hooks.json and send Claude-style JSON on stdin, with these Copilot
differences (pinned by tests/test_copilot.py):

- its edit tool sends tool_input as apply_patch text ("*** Update File: <path>", "*** Add File:", "*** Delete File:",
  "*** Move to:") instead of {file_path}; parse_patch() reads it and Change.after() applies the hunks to the current
  file (when they do not apply, the edit check looks at the added lines only);
- its own camelCase input (toolName / toolArgs; toolArgs a JSON string, an object or raw patch text) and
  str_replace-style ({path, old_str, new_str}) or create-style ({path, file_text}) edit input;
- it hides an exit-2 hook's stderr from the model, so under Copilot (COPILOT_CLI set, patch text or camelCase input) a
  refusal is {"permissionDecision": "deny", ...} on stdout, flat and in hookSpecificOutput, with exit 0;
- no permission_mode; session start context goes out as {"additionalContext": ...}.

Kiro (IDE and CLI v3) runs the same scripts from the .kiro/hooks/plumb.json files scripts/kiro.py installs (pinned by
tests/test_kiro.py; formats from Kiro's docs, verify live): snake_case input like Claude Code with its own tool names
(fs_write, whose "command" is create / str_replace / insert / append, and execute_bash / execute_cmd) and, from 2.x,
camelCase event names (agentSpawn, preToolUse, stop: read as SessionStart, PreToolUse, Stop). Every installed command
carries --kiro (kiro_run): the hook then answers like Claude Code: a refusal is exit 2 with the reason on stderr (Kiro
blocks a PreToolUse on any non-zero exit), session start is plain stdout, the Stop block is
{"decision": "block", "reason": ...}; and every command it prints is /plumb-<name> (tool_text). The home file's commands
also carry --kiro-global; such a hook stands down only where the workspace's own Plumb hooks file runs the same plugin
(deferred_to_workspace).

Every JSON a hook prints is ASCII (non-ASCII as \\u escapes), so it survives any console code page on the way (Copilot
CLI on Windows runs the hooks through PowerShell and run.cmd).

read_payload() turns either into one Payload: the event, the tool kind (TOOL_KINDS: edit, write, multiedit, patch,
shell; a new tool's names are one more entry there), the file changes with a way to compute each file's text after the
edit, the shell command, whether to answer in Copilot's dialect, the session id and cwd.

The project is the nearest folder holding a PLUMB.md (not a template), searched from CLAUDE_PROJECT_DIR when the CLI
sets it, else from the payload's cwd and the current directory. No PLUMB.md: every hook does nothing, so a repository
without Plumb, and the Plumb repository itself, are never touched. PLUMB.md is read on every run (switches can change
between two edits); its `Key: value` lines are parsed here with the same rules as _plumb.read_plumb_md, so the guards
need no import at all (a non-UI edit stays far under 150 ms).

Trust boundary: the checks load audit.py (and through it build-prototype.py, build-tokens.py, _plumb.py) only from the
plugin's own install (PLUGIN_SCRIPTS, next to these hooks), never the copies in the project's design-system skill: the
project is data (PLUMB.md, the tokens JSON, screens.json, screen and source files); the git calls in audit.py turn off
the commands a repository's config can name (see SECURITY.md "Trust boundary"). When the project's copies are another
version, scripts_note() says so (run /plumb:upgrade); the checks still use the plugin's. When loading fails the checks
are skipped with one stderr line: hooks fail open. Snapshots live in a private per-user temp folder (snapshot_dir).

Python 3.9+, standard library only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
# The plugin's own copy of the design-system scripts, the only Python the hooks ever import or run (never the copies in
# a project: those run only on an explicit command, see SECURITY.md "Trust boundary").
PLUGIN_SCRIPTS = os.path.join(os.path.dirname(HOOKS_DIR), "assets", "skill", "scripts")
PLUMB_MD = "PLUMB.md"
SNAPSHOT_DAYS = 7
UI_EXT = frozenset((".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".astro", ".html", ".css", ".scss", ".swift", ".kt"))
# Windows and macOS (APFS, HFS+ by default) file systems ignore case: TOKENS.CSS is tokens.css there.
CASELESS = sys.platform in ("win32", "darwin")

# Tool names (lower case, without "_" and "-") -> what the tool does. Claude Code: Edit, Write, MultiEdit, Bash,
# PowerShell; Copilot CLI: the same names for a plugin's hooks, or edit, create, str_replace, apply_patch, bash,
# powershell in its own camelCase input.
TOOL_KINDS = {
    "edit": "edit", "strreplace": "edit", "strreplaceeditor": "edit", "write": "write", "create": "write",
    "multiedit": "multiedit", "applypatch": "patch", "patch": "patch", "bash": "shell", "powershell": "shell",
    "shell": "shell",
    # Kiro: fs_write (its input's "command" says create / str_replace / insert / append), execute_bash, and
    # execute_cmd (its Windows shell); the IDE's fsWrite / fsAppend / executePwsh (verify live).
    "fswrite": "write", "fsappend": "write", "executebash": "shell", "executecmd": "shell", "executepwsh": "shell",
}

# Kiro (IDE and CLI v3) sends Claude-style snake_case input. Its 2.x camelCase event names (still accepted by v3; verify
# live which spelling v3 sends) are read as Claude's.
KIRO_EVENTS = {"agentSpawn": "SessionStart", "preToolUse": "PreToolUse", "postToolUse": "PostToolUse", "stop": "Stop",
               "userPromptSubmit": "UserPromptSubmit"}
# The same constants as scripts/kiro.py. KIRO_ARG is on every command kiro.py installs: the hook then answers in Kiro's
# dialect (exit 2 + stderr, plain session-start text, the Stop decision JSON, commands written /plumb-<name>), never by
# guessing from the payload. KIRO_GLOBAL_ARG is on the home file's commands (~/.kiro/hooks/plumb.json). KIRO_MARK is in
# every file kiro.py installs (its ownership mark).
KIRO_ARG = "--kiro"
KIRO_GLOBAL_ARG = "--kiro-global"
KIRO_MARK = "installed by Plumb's kiro.py"
SCRIPT_TRIGGERS = {"session_start.py": "SessionStart", "pre_edit.py": "PreToolUse", "stop_check.py": "Stop"}


def kiro_run() -> bool:
    """This hook was started from a Kiro hooks file (kiro.py puts KIRO_ARG on every command)."""
    return KIRO_ARG in sys.argv[1:]


def tool_text(text: str) -> str:
    """text as the running tool names Plumb's commands: /plumb-<name> in Kiro (its skills are plumb-<name>)."""
    return re.sub(r"/plumb:(?=[a-z])", "/plumb-", text) if kiro_run() else text


def launcher_path() -> str:
    """This plugin's hook launcher, as kiro.py names it in a hook's description ("Runs <launcher> <script> ...")."""
    return os.path.realpath(os.path.join(HOOKS_DIR, "run.cmd" if sys.platform == "win32" else "run.sh"))


def utf8_stdio() -> None:
    """Windows consoles and pipes default to cp1252; hooks speak UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - a stream that cannot be reconfigured is left as it is
            pass


def note(message: str) -> None:
    """The one stderr line a hook prints when it skips something (it never fails the tool call)."""
    print(tool_text("plumb: " + " ".join(str(message).split())), file=sys.stderr)


def normalise(text: str) -> str:
    if text.startswith("﻿"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ---------------------------------------------------------------- edits and patches


class Hunk:
    def __init__(self, header: str) -> None:
        self.header = header
        self.lines: List[str] = []  # each starts with " ", "-" or "+"


def _seek(lines: List[str], pattern: List[str], start: int) -> Optional[int]:
    """Where pattern occurs in lines at or after start: exact, then ignoring trailing spaces, then ignoring spaces at
    both ends (patches from models often lose trailing spaces)."""
    if not pattern:
        return None
    for same in (lambda a, b: a == b, lambda a, b: a.rstrip() == b.rstrip(), lambda a, b: a.strip() == b.strip()):
        for i in range(max(start, 0), len(lines) - len(pattern) + 1):
            if all(same(lines[i + j], pattern[j]) for j in range(len(pattern))):
                return i
    return None


def _apply_hunks(before: str, hunks: List[Hunk]) -> Optional[str]:
    text = normalise(before)
    trailing = text.endswith("\n")
    lines = text.split("\n")
    if trailing:
        lines.pop()
    cursor = 0
    for h in hunks:
        if h.header:
            at = _seek(lines, [h.header], cursor)
            if at is not None:
                cursor = at + 1
        old = [ln[1:] for ln in h.lines if ln[0] in " -"]
        if not old:  # only added lines: they go at the end
            lines.extend(ln[1:] for ln in h.lines if ln[0] == "+")
            cursor = len(lines)
            continue
        at = _seek(lines, old, cursor)
        if at is None:
            at = _seek(lines, old, 0)
        if at is None:
            return None
        j, out = at, []
        for ln in h.lines:
            if ln[0] == " ":
                out.append(lines[j])  # the file's own context line (its spaces kept)
                j += 1
            elif ln[0] == "-":
                j += 1
            else:
                out.append(ln[1:])
        lines[at:j] = out
        cursor = at + len(out)
    return "\n".join(lines) + ("\n" if trailing or lines else "")


class Change:
    """One file an edit touches. kind: write (whole content), edit (old -> new), multiedit, insert (after a line),
    append (Kiro: at the end), add / update / delete / move (apply_patch sections), path (the tool names a file but its
    new text is unknown)."""

    def __init__(self, path: str, kind: str, content: Optional[str] = None,
                 edits: Optional[List[Tuple[str, str, bool]]] = None, line: int = 0) -> None:
        self.path = path
        self.kind = kind
        self.content = content
        self.edits = edits or []
        self.line = line
        self.hunks: List[Hunk] = []
        self.add_lines: List[str] = []

    def after(self, before: Optional[str]) -> Optional[str]:
        """The file's text after the edit (LF line endings), or None when it cannot be known (an old string that is
        not in the file, a patch that does not apply, a delete)."""
        if self.kind in ("write",):
            return normalise(self.content or "")
        if self.kind == "add":
            return "\n".join(self.add_lines) + ("\n" if self.add_lines else "")
        if before is None:
            return None
        text = normalise(before)
        if self.kind in ("edit", "multiedit"):
            for old, new, every in self.edits:
                old, new = normalise(old), normalise(new)
                if not old or old not in text:
                    return None
                text = text.replace(old, new) if every else text.replace(old, new, 1)
            return text
        if self.kind == "append":  # Kiro's fs_write append: a newline first when the file does not end with one
            return text + ("\n" if text and not text.endswith("\n") else "") + normalise(self.content or "")
        if self.kind == "insert":
            lines = text.split("\n")
            at = min(max(self.line, 0), len(lines))
            return "\n".join(lines[:at] + normalise(self.content or "").split("\n") + lines[at:])
        if self.kind == "update":
            return _apply_hunks(text, self.hunks)
        return None

    def added(self) -> str:
        return "\n".join(ln[1:] for h in self.hunks for ln in h.lines if ln[0] == "+")

    def removed(self) -> str:
        return "\n".join(ln[1:] for h in self.hunks for ln in h.lines if ln[0] == "-")


PATCH_HEADER = re.compile(r"^\*\*\* (Update File|Add File|Delete File|Move to):[ \t]*(.+?)[ \t]*$")
PATCH_RE = re.compile(r"^\*\*\* (?:Begin Patch|Update File:|Add File:|Delete File:)", re.MULTILINE)
_PATCH_KIND = {"Update File": "update", "Add File": "add", "Delete File": "delete", "Move to": "move"}


def parse_patch(text: str) -> List[Change]:
    """Every file section of apply_patch text, in order. A "Move to" is its own change (the file it writes)."""
    changes: List[Change] = []
    cur: Optional[Change] = None
    for line in normalise(text).split("\n"):
        m = PATCH_HEADER.match(line)
        if m:
            kind = _PATCH_KIND[m.group(1)]
            change = Change(m.group(2), kind)
            changes.append(change)
            if kind != "move":
                cur = change
            continue
        if line.startswith("*** "):  # Begin Patch, End Patch, End of File
            if line.startswith("*** End Patch"):
                cur = None
            continue
        if cur is None:
            continue
        if cur.kind == "add":
            if line.startswith("+"):
                cur.add_lines.append(line[1:])
        elif cur.kind == "update":
            if line.startswith("@@"):
                cur.hunks.append(Hunk(line[2:].strip().rstrip("@").strip()))
                continue
            if not cur.hunks:
                cur.hunks.append(Hunk(""))
            if line[:1] in (" ", "-", "+"):
                cur.hunks[-1].lines.append(line)
            elif line == "":
                cur.hunks[-1].lines.append(" ")  # a blank context line that lost its space
    for c in changes:
        for h in c.hunks:
            while h.lines and h.lines[-1] == " ":  # trailing blank context: usually the patch's own last newline
                h.lines.pop()
        c.hunks = [h for h in c.hunks if h.lines]
    return changes


# ---------------------------------------------------------------- the payload


class Payload:
    """What a hook was asked about, in either CLI's shape."""

    def __init__(self, raw: dict) -> None:
        self.raw = raw
        event = str(raw.get("hook_event_name") or raw.get("hookEventName") or "")
        self.event = KIRO_EVENTS.get(event, event)
        camel = ("toolName" in raw or "toolArgs" in raw) and "tool_name" not in raw and "tool_input" not in raw
        name = raw.get("toolName") if camel else raw.get("tool_name")
        self.tool_name = name if isinstance(name, str) else ""
        self.kiro = kiro_run()
        tool_input = raw.get("toolArgs") if camel else raw.get("tool_input")
        if isinstance(tool_input, str) and camel:
            try:
                tool_input = json.loads(tool_input)
            except ValueError:
                pass  # raw patch text
        self.tool = TOOL_KINDS.get(re.sub(r"[\s_-]", "", self.tool_name.lower()), "")
        self.changes, self.command = _changes(self.tool, tool_input)
        # Only Copilot CLI sends patch text or camelCase input, so those are answered in its dialect even without
        # COPILOT_CLI. A hook started from a Kiro hooks file answers in Kiro's dialect whatever the environment says.
        self.copilot = not self.kiro and (camel or isinstance(tool_input, str) or bool(os.environ.get("COPILOT_CLI")))
        sid = raw.get("session_id") or raw.get("sessionId") or ""
        self.session_id = sid if isinstance(sid, str) else str(sid)
        cwd = raw.get("cwd")
        self.cwd = cwd if isinstance(cwd, str) and cwd else ""
        self.stop_hook_active = raw.get("stop_hook_active") is True

    @property
    def file_path(self) -> Optional[str]:
        return self.changes[0].path if self.changes else None


def _first_str(d: dict, keys: Tuple[str, ...]) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def _changes(kind: str, tool_input: object) -> Tuple[List[Change], Optional[str]]:
    if isinstance(tool_input, str):
        if PATCH_RE.search(tool_input):
            return parse_patch(tool_input), None
        return [], (tool_input if kind == "shell" else None)
    if not isinstance(tool_input, dict):
        return [], None
    path = _first_str(tool_input, ("file_path", "path", "notebook_path"))
    command = tool_input.get("command")
    if isinstance(command, str):
        if kind == "shell" or (path is None and not any(k in tool_input for k in ("old_str", "new_str", "file_text"))):
            return [], command
        if command == "view":  # str_replace_editor's read
            return [], None
    if path is None:
        for value in tool_input.values():
            if isinstance(value, str) and PATCH_RE.search(value):
                return parse_patch(value), None
        return [], None
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        pairs = [(e.get("old_string") or e.get("old_str") or "", e.get("new_string") or e.get("new_str") or "",
                  e.get("replace_all") is True) for e in edits if isinstance(e, dict)]
        return [Change(path, "multiedit", edits=[(str(a), str(b), c) for a, b, c in pairs])], None
    old = tool_input.get("old_string", tool_input.get("old_str"))
    new = tool_input.get("new_string", tool_input.get("new_str"))
    if isinstance(old, str):
        return [Change(path, "edit", edits=[(old, new if isinstance(new, str) else "",
                                             tool_input.get("replace_all") is True)])], None
    content = tool_input.get("content", tool_input.get("file_text"))
    if command == "append":  # Kiro's fs_write append: new_str (or file_text / content; verify live) goes at the end
        added = new if isinstance(new, str) else content
        return [Change(path, "append", content=added) if isinstance(added, str) else Change(path, "path")], None
    if isinstance(content, str):
        return [Change(path, "write", content=content)], None
    line = tool_input.get("insert_line")
    if isinstance(line, str) and line.strip().isdigit():  # Kiro may send the line number as text
        line = int(line.strip())
    if isinstance(new, str) and isinstance(line, int) and not isinstance(line, bool):
        return [Change(path, "insert", content=new, line=line)], None
    return [Change(path, "path")], None


def read_payload(text: Optional[str] = None) -> Optional[Payload]:
    """The hook input from stdin (or text), or None when it is not a JSON object."""
    if text is None:
        try:
            text = sys.stdin.buffer.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return None
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    return Payload(raw) if isinstance(raw, dict) else None


def refuse(message: str, copilot: bool) -> int:
    """Block the tool call with an actionable reason. Claude Code: exit 2, reason on stderr. Copilot CLI: exit 0 and a
    JSON deny on stdout (it hides an exit-2 hook's stderr from the model). Kiro: as Claude Code, commands written
    /plumb-<name>."""
    message = tool_text(message)
    if copilot:
        print(json.dumps({"permissionDecision": "deny", "permissionDecisionReason": message,
                          "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": message}}))
        return 0
    print(message, file=sys.stderr)
    return 2


# ---------------------------------------------------------------- paths


def resolve(path: str, base: str) -> str:
    """An absolute, normalised path (symlinks resolved) for a path from a payload or a command."""
    if os.sep == "/":
        path = path.replace("\\", "/")
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    return os.path.realpath(os.path.normpath(path))


def under(path: str, root: str) -> Optional[str]:
    """path relative to root (posix), "" for root itself, None when it is outside."""
    a, b = path.rstrip("/\\"), root.rstrip("/\\")
    ca, cb = (os.path.normcase(a).lower(), os.path.normcase(b).lower()) if CASELESS else (a, b)
    if len(ca) != len(a) or len(cb) != len(b):
        ca, cb = a, b
    if ca == cb:
        return ""
    for sep in {os.sep, "/"}:
        if ca.startswith(cb + sep):
            return a[len(b) + 1:].replace("\\", "/")
    return None


def fold(text: str) -> str:
    """text for comparing paths: lower case where the file system ignores case."""
    return text.lower() if CASELESS else text


def plugin_root() -> str:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return os.path.realpath(env if env else os.path.dirname(HOOKS_DIR))


def plugin_version() -> Optional[str]:
    try:
        with open(os.path.join(plugin_root(), ".claude-plugin", "plugin.json"), encoding="utf-8-sig") as fh:
            v = json.load(fh).get("version")
        return v if isinstance(v, str) else None
    except (OSError, ValueError, AttributeError):
        return None


def version_tuple(v: Optional[str]) -> Optional[Tuple[int, ...]]:
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def newer_plugin() -> Optional[Tuple[str, str]]:
    """(version, folder) of the newest Plumb next to this one (the plugin cache keeps one folder per version) when it
    is newer than this plugin, else None. Kiro's copies point at one folder, so after a plugin update they run the old
    one until kiro.py install runs again."""
    root = plugin_root()
    mine = version_tuple(plugin_version())
    best: Optional[Tuple[Tuple[int, ...], str, str]] = None
    try:
        siblings = sorted(os.listdir(os.path.dirname(root)))
    except OSError:
        return None
    for name in siblings:
        folder = os.path.join(os.path.dirname(root), name)
        if os.path.realpath(folder) == root:
            continue
        try:
            with open(os.path.join(folder, ".claude-plugin", "plugin.json"), encoding="utf-8-sig") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or doc.get("name") != "plumb" or not isinstance(doc.get("version"), str):
            continue
        v = version_tuple(doc["version"])
        if v is not None and mine is not None and v > mine and (best is None or v > best[0]):
            best = (v, doc["version"], os.path.realpath(folder))
    return (best[1], best[2]) if best else None


KIRO_SKILL = re.compile(r"(?:^|/)\.kiro/skills/(plumb-[^/]+)/(.+)$", re.I if CASELESS else 0)
KIRO_HOOKS = re.compile(r"(?:^|/)\.kiro/hooks/plumb\.json$", re.I if CASELESS else 0)


def kiro_own_file(path: str) -> Optional[str]:
    """The folder holding .kiro when path is one of the files kiro.py installed there (a marked
    .kiro/hooks/plumb.json, or anything in a .kiro/skills/plumb-<name>/ folder whose SKILL.md is marked), else None."""
    p = path.replace("\\", "/")  # an absolute path: the match starts at the "/" before .kiro
    m = KIRO_SKILL.search(p)
    if m:
        marked = KIRO_MARK in (_read(os.path.join(p[:m.start(2)], "SKILL.md")) or "")
        return (p[:m.start()] or "/") if marked else None
    m = KIRO_HOOKS.search(p)
    if m and kiro_hooks_doc(path) is not None:
        return p[:m.start()] or "/"
    return None


# ---------------------------------------------------------------- the project (PLUMB.md)


_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9 _/-]*?):(?:\s+(.*)|\s*)$")
_NOTE = re.compile(r"\s{2,}\([^)]*\)\s*$")
_VERSION = re.compile(r"<!--\s*plumb\s+v(\d+(?:\.\d+)*)", re.I)
_PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")
_ON = re.compile(r"^\s*(?:on|yes|true)\b", re.I)
_SAFE_PYTHON = re.compile(r"py -3|py(?:\.exe)?|(?:[\w.:/\\-]*[/\\])?python[\d.]*(?:\.exe)?")
_SAFE_ARG = re.compile(r"[\w.@+/:\\-]+")


def _safe_arg(text: str) -> str:
    """A path for a fix: line, double-quoted (with no ", $ or backtick left in it) unless it is plain."""
    return text if _SAFE_ARG.fullmatch(text) else '"' + re.sub(r'["`$]', "", text) + '"'


def plumb_md_keys(text: str) -> Dict[str, str]:
    """PLUMB.md's `Key: value` lines, by the rules of _plumb.read_plumb_md (comments, code fences, headings, bullets,
    quotes and tables ignored; a trailing '   (note)' dropped; a value in backticks unwrapped)."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out: Dict[str, str] = {}
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


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8-sig", "replace")
    except OSError:
        return None


def find_project(start: str) -> Optional[Path]:
    """The nearest folder at or above start holding a PLUMB.md that is a project's (not the template in Plumb's own
    repository, which still has {{PLACEHOLDERS}})."""
    folder = os.path.realpath(start)
    while True:
        candidate = os.path.join(folder, PLUMB_MD)
        if os.path.isfile(candidate):
            text = _read(candidate)
            if text is not None and not _PLACEHOLDER.search(text):
                return Path(folder)
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


class Project:
    """A project with Plumb: its root, PLUMB.md's switches and the design-system skill it names."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root_s = str(root)
        text = _read(os.path.join(self.root_s, PLUMB_MD)) or ""
        first = text.lstrip("﻿").split("\n", 1)[0]
        m = _VERSION.search(first)
        self.version = m.group(1) if m else None
        self.keys = plumb_md_keys(text)
        self.skill_rel = self.keys.get("Design system", "").strip().replace("\\", "/").rstrip("/")
        self.skill_dir: Optional[Path] = Path(resolve(self.skill_rel, self.root_s)) if self.skill_rel else None
        self.linked = self.keys.get("Role", "").strip().lower().startswith("linked")
        python = self.keys.get("Python", "").strip()
        # Echoed into fix: lines an agent may run, so only an interpreter name or path is taken from PLUMB.md.
        self.python = python if _SAFE_PYTHON.fullmatch(python) else "python3"
        self._doc: Optional[dict] = None
        self._doc_read = False

    def on(self, key: str) -> bool:
        return _ON.match(self.keys.get(key, "") or "") is not None

    @property
    def skill_ok(self) -> bool:
        return self.skill_dir is not None and self.skill_dir.is_dir()

    @property
    def name(self) -> str:
        return self.skill_rel.rsplit("/", 1)[-1] if self.skill_rel else "design system"

    def script(self, name: str) -> str:
        """The command that runs one of the skill's scripts, for fix lines."""
        return f"{self.python} {_safe_arg(f'{self.skill_rel}/scripts/{name}')}"

    def tokens_doc(self) -> Optional[dict]:
        """The tokens file (the one *.tokens.json in the skill's assets/tokens/), or None (missing, several, broken)."""
        if not self._doc_read:
            self._doc_read = True
            folder = self.skill_dir / "assets" / "tokens" if self.skill_dir else None
            found = sorted(folder.glob("*.tokens.json")) if folder is not None and folder.is_dir() else []
            if len(found) == 1:
                try:
                    doc = json.loads(found[0].read_bytes().decode("utf-8-sig"))
                    self._doc = doc if isinstance(doc, dict) else None
                except (OSError, ValueError):
                    self._doc = None
        return self._doc

    def _plumb_settings(self) -> dict:
        doc = self.tokens_doc() or {}
        ext = doc.get("$extensions") if isinstance(doc.get("$extensions"), dict) else {}
        plumb = ext.get("plumb") if isinstance(ext.get("plumb"), dict) else {}
        return plumb

    @property
    def docs_rel(self) -> str:
        docs = self._plumb_settings().get("docs_dir") or "docs/design"
        return str(docs).replace("\\", "/").strip().strip("/") or "docs/design"

    @property
    def copies(self) -> List[str]:
        web = self._plumb_settings().get("web")
        copies = web.get("copies") if isinstance(web, dict) else None
        out = []
        for c in copies or []:
            if isinstance(c, str) and c.strip():
                c = c.replace("\\", "/").strip()
                while c.startswith("./"):
                    c = c[2:]
                out.append(c)
        return out

    def home_root(self) -> str:
        """The project that owns the skill (a linked repo's skill lives in its home repo): the nearest folder above the
        skill with a PLUMB.md, else this project."""
        if self.skill_dir is not None:
            found = find_project(str(self.skill_dir.parent))
            if found is not None:
                return str(found)
        return self.root_s


def kiro_hooks_doc(path: str) -> Optional[list]:
    """The hooks of a .kiro/hooks/plumb.json that kiro.py wrote (every hook carries KIRO_MARK), else None."""
    try:
        doc = json.loads(_read(path) or "")
    except ValueError:
        return None
    hooks = doc.get("hooks") if isinstance(doc, dict) else None
    if not isinstance(hooks, list) or not hooks or not all(
            isinstance(h, dict) and KIRO_MARK in str(h.get("description") or "") for h in hooks):
        return None
    return hooks


def deferred_to_workspace(payload: Optional[Payload]) -> bool:
    """Kiro CLI runs the home hooks file and a workspace's side by side. A hook started from the home file
    (KIRO_GLOBAL_ARG) stands down only where the workspace's own file (cwd/.kiro/hooks/plumb.json: Kiro runs hooks in
    the workspace root; no walk up) will do the same job: Plumb's, written for the workspace (no KIRO_GLOBAL_ARG), its
    hook for this trigger (and matcher) enabled and running this very plugin's launcher, which exists. Otherwise (a
    workspace file from an old or removed plugin folder, a disabled hook, a foreign file) the home hook runs."""
    if KIRO_GLOBAL_ARG not in sys.argv[1:]:
        return False
    start = (payload.cwd if payload else "") or os.getcwd()
    hooks = kiro_hooks_doc(os.path.join(start, ".kiro", "hooks", "plumb.json"))
    if hooks is None:
        return False
    script = os.path.basename(sys.argv[0])
    trigger = SCRIPT_TRIGGERS.get(script)
    launcher = launcher_path()
    if trigger is None or not os.path.isfile(launcher):
        return False
    matcher = ("shell" if payload is not None and payload.tool == "shell" else "write") if trigger == "PreToolUse" else None
    runs = f"Runs {launcher} {script} {KIRO_ARG}."
    for h in hooks:
        action = h.get("action") if isinstance(h.get("action"), dict) else {}
        if (h.get("trigger") == trigger and h.get("matcher") == matcher and h.get("enabled", True) is not False
                and runs in str(h.get("description") or "") and KIRO_GLOBAL_ARG not in str(action.get("command") or "")):
            return True
    return False


def load_project(payload: Optional[Payload]) -> Optional[Project]:
    """The project the hook runs for: from CLAUDE_PROJECT_DIR when the CLI sets it (only there), else from the
    payload's cwd, else from the current directory. None without a PLUMB.md, and None for a hook from Kiro's home hooks
    file where the workspace has its own (deferred_to_workspace)."""
    if deferred_to_workspace(payload):
        return None
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    starts = [env] if env else [payload.cwd if payload else "", os.getcwd()]
    for start in starts:
        if start:
            root = find_project(start)
            if root is not None:
                return Project(root)
    return None


def load_script(file_name: str, module_name: str):
    """One of the plugin's own design-system scripts (audit.py, build-prototype.py) as a module, or None with one note.

    Trust boundary: always the copy installed with the plugin (PLUGIN_SCRIPTS, next to these hooks), never the copy in
    the project's skill folder, so a hook never runs the repository's own Plumb scripts; the project
    is only read as data (PLUMB.md, the tokens JSON, screens.json, the screen and source files). The module is
    registered in sys.modules before it runs (its dataclasses need that); its folder goes first on sys.path so its own
    `import _plumb` is the plugin's too."""
    path = Path(PLUGIN_SCRIPTS) / file_name
    if not path.is_file():
        note(f"the plugin's {file_name} is missing, so the design checks are skipped (the guards stay on); reinstall "
             f"the Plumb plugin")
        return None
    if sys.path[:1] != [PLUGIN_SCRIPTS]:
        sys.path.insert(0, PLUGIN_SCRIPTS)
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except BaseException as exc:  # noqa: BLE001 - a broken script must never break the tool call
        sys.modules.pop(module_name, None)
        if isinstance(exc, KeyboardInterrupt):
            raise
        note(f"cannot load the plugin's {file_name} ({type(exc).__name__}: {exc}), so the design checks are skipped "
             f"(the guards stay on); reinstall the Plumb plugin")
        return None


_SCRIPT_VERSION = re.compile(r"""^PLUMB_VERSION\s*=\s*["']([^"']+)["']""", re.M)


def _script_version(path: Path) -> Optional[str]:
    """PLUMB_VERSION of a _plumb.py, read as text (the project's copy is never imported)."""
    text = _read(str(path))
    m = _SCRIPT_VERSION.search(text or "")
    return m.group(1) if m else None


def script_versions(project: Project) -> Tuple[Optional[str], Optional[str]]:
    """(the project's copied scripts' version, the plugin's), both read as text."""
    mine = _script_version(project.skill_dir / "scripts" / "_plumb.py") if project.skill_dir is not None else None
    return mine, _script_version(Path(PLUGIN_SCRIPTS) / "_plumb.py")


def scripts_note(project: Project) -> Optional[str]:
    """One line when the project's copied scripts are another version than the plugin's (the hooks check with the
    plugin's either way), else None."""
    mine, plugin = script_versions(project)
    if mine is None or plugin is None or mine == plugin:
        return None
    return f"this project's Plumb scripts are v{mine}; the plugin is v{plugin} \u2014 run /plumb:upgrade"


# ---------------------------------------------------------------- session snapshots


def _private_dir_name() -> str:
    """plumb-<uid> on POSIX (a shared /tmp needs the uid in the name). On Windows the temp folder is already the user's
    own (%LOCALAPPDATA%\\Temp), so it is just plumb (never a name taken from an environment variable)."""
    return f"plumb-{os.getuid()}" if hasattr(os, "getuid") else "plumb"


_REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT: a symlink, junction or mount point on Windows


def _ours(st: os.stat_result, folder: bool) -> bool:
    """A real directory (folder) or regular file: not a symlink (nor, on Windows, any reparse point such as a
    junction); on POSIX also owned by this user and not writable by group or others. On Windows ownership and mode bits
    mean nothing to os.stat; the per-user temp folder is what keeps others out."""
    if stat.S_ISLNK(st.st_mode) or not (stat.S_ISDIR(st.st_mode) if folder else stat.S_ISREG(st.st_mode)):
        return False
    if getattr(st, "st_file_attributes", 0) & _REPARSE_POINT:
        return False
    if hasattr(os, "getuid"):
        return st.st_uid == os.getuid() and not st.st_mode & 0o022
    return True


_DIR_CHECKED: List[Optional[Path]] = []


def snapshot_dir() -> Optional[Path]:
    """The hooks' private folder in the OS temp folder: plumb-<uid>, created 0700 (on Windows plumb in the per-user temp
    folder). None (with one note) when it is a symlink or reparse point, someone else's, or writable by others: then
    nothing is read, written or deleted."""
    if _DIR_CHECKED:
        return _DIR_CHECKED[0]
    folder = Path(tempfile.gettempdir()) / _private_dir_name()
    result: Optional[Path] = None
    try:
        try:
            os.mkdir(str(folder), 0o700)
        except FileExistsError:
            pass
        if _ours(os.lstat(str(folder)), folder=True):
            result = folder
        else:
            note(f"the temp folder {folder} is not private to you (a symlink, someone else's or writable by others), "
                 f"so no session snapshot is kept; remove it")
    except OSError as exc:
        note(f"no temp folder for the session snapshot ({exc.strerror or exc})")
    _DIR_CHECKED.append(result)
    return result


def snapshot_path(project: Path, session_id: str) -> Optional[Path]:
    """Where the session's snapshot lives: the private temp folder, keyed by project and session, never in the repo.
    None when there is no private folder (see snapshot_dir)."""
    folder = snapshot_dir()
    if folder is None:
        return None
    key = hashlib.sha256(os.path.realpath(str(project)).encode("utf-8")).hexdigest()[:12]
    sid = re.sub(r"[^\w.-]", "_", session_id or "")[:80] or "session"
    return folder / f"{key}-{sid}.json"


def read_private(path: Path) -> Optional[str]:
    """A file of ours in the private folder (a regular file we own), else None."""
    try:
        if not _ours(os.lstat(str(path)), folder=False):
            return None
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return None


def write_json(path: Path, data: object) -> None:
    """Write a file in the private folder: a fresh 0600 file (O_EXCL, no symlink followed), then renamed into place."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        os.unlink(str(tmp))
    except OSError:
        pass
    fd = os.open(str(tmp), flags, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
    os.replace(str(tmp), str(path))


def clean_snapshots(days: int = SNAPSHOT_DAYS) -> None:
    """Delete our snapshots older than `days`: only regular files we own, only in the private folder."""
    folder = snapshot_dir()
    if folder is None:
        return
    cutoff = time.time() - days * 24 * 3600
    try:
        entries = list(folder.iterdir())
    except OSError:
        return
    for p in entries:
        try:
            st = os.lstat(str(p))
            if p.suffix in (".json", ".tmp") and _ours(st, folder=False) and st.st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- shell commands


# A cheap first look: a command with none of these cannot write a file.
WRITE_HINT = re.compile(r">|\btee\b|\bsed\b|\bperl\b|\bcp\b|\bmv\b|\binstall\b|\brsync\b|\bln\b|\bdd\b|\btruncate\b|"
                        r"write|\bopen\(|\.dump|shutil|os\.(?:replace|rename)|-content\b|out-file|copy-item|move-item|::|"
                        r"append|copyfile|\bfs\.|rename|"
                        # removals and moves: rm, rmdir, unlink, del, erase, rd, Remove-Item, ri, move, mi
                        r"\brm\b|\brmdir\b|\bunlink\b|\bdel\b|\berase\b|\brd\b|remove-item|\bri\b|\bmove\b|\bmi\b",
                        re.I)
_WORD = r"(\"[^\"]*\"|'[^']*'|[^\s;&|<>]+)"
_REDIR = re.compile(r"\d?>>?\|?\s*" + _WORD)
_TEE = re.compile(r"\btee\b((?:\s+-{1,2}[\w-]+)*)((?:\s+" + _WORD + r")+)", re.I)
_NO_WRITE = re.compile(r"\d?>&\d|\d?>>?\s*(?:/dev/null|\$null|nul)(?![\w./\\-])", re.I)
_GENERIC = re.compile(r"write_text|write_bytes|\.write\(|json\.dump|shutil\.(?:copy\w*|move)|os\.(?:replace|rename)\(|"
                      # Node, Bun, Deno (node -e, bun -e, deno eval): fs writes, copies and renames
                      r"\b(?:writeFile|appendFile|copyFile|writeTextFile|createWriteStream|rename|cp)(?:Sync)?\(|"
                      r"\bopen\([^)]*,\s*(?:mode\s*=\s*)?\\?['\"][rbt]*[wax+]|\btruncate\b|\bdd\b[^|;&]*\bof=|"
                      r"::(?:write|append)all\w*\(", re.I)
# Running Plumb's own builders is how generated files are meant to change: a pipeline stage whose interpreter's script
# argument (the first word after its flags) is build-tokens.py or build-prototype.py.
_BUILDER_SCRIPT = re.compile(r"(?:^|[/\\])build-(?:tokens|prototype)\.py$", re.I)
_UV_VALUE_FLAGS = ("--with", "--python", "-p", "--project", "--directory", "--from", "--env-file", "--group", "--extra",
                   "--with-requirements", "--index", "--index-url")
_CD = re.compile(r"^\s*(?:cd|pushd|set-location|sl)\s+(?:/d\s+)?(\"[^\"]*\"|'[^']*'|\S+)\s*$", re.I)


def _unquote(word: str) -> str:
    return word[1:-1] if len(word) >= 2 and word[0] == word[-1] and word[0] in "\"'" else word


def _split(command: str, seps: Tuple[str, ...]) -> List[str]:
    """Split at top-level separators (not inside quotes)."""
    parts: List[str] = []
    cur: List[str] = []
    quote = ""
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            cur.append(ch)
            i += 1
            continue
        sep = next((s for s in seps if command.startswith(s, i)), None)
        if sep is not None:
            parts.append("".join(cur))
            cur = []
            i += len(sep)
            continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return [p for p in parts if p.strip()]


_PS_PATH_FLAGS = ("-path", "-filepath", "-literalpath", "-pspath")
_PS_VALUE_FLAGS = ("-value", "-encoding", "-filter", "-include", "-exclude", "-inputobject", "-width", "-stream",
                   "-credential", "-delimiter")


def _positional(words: List[str], value_flags: Tuple[str, ...]) -> List[str]:
    out, skip, ended = [], False, False
    for w in words:
        if skip:
            skip = False
            continue
        if w == "--" and not ended:  # end of options: what follows is positional
            ended = True
            continue
        if w.startswith("-") and len(w) > 1 and not ended:
            skip = w.lower() in value_flags
            continue
        out.append(w)
    return out


def _flag_value(words: List[str], flags: Tuple[str, ...]) -> Optional[str]:
    for i, w in enumerate(words[:-1]):
        if w.lower() in flags:
            return words[i + 1]
    for w in words:
        k, eq, v = w.partition(":")
        if eq and k.lower() in flags and v:
            return v
    return None


def _sed_files(args: List[str], perl: bool = False) -> List[str]:
    files, script_given, i = [], False, 0
    pos: List[str] = []
    while i < len(args):
        a = args[i]
        if a in ("-e", "-f", "--expression", "--file") or (perl and a in ("-e", "-E")):
            script_given, i = True, i + 2
            continue
        if a.startswith(("--expression=", "--file=")):
            script_given = True
        elif a == "-i" and i + 1 < len(args) and args[i + 1] == "":  # BSD sed: -i '' (no backup suffix)
            i += 2
            continue
        elif a.startswith("-") and len(a) > 1:
            pass
        else:
            pos.append(a)
        i += 1
    files = pos if script_given else pos[1:]
    return [f for f in files if f]


def _command_name(word: str) -> str:
    name = re.split(r"[/\\]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _runs_builder(words: List[str]) -> bool:
    """The stage runs build-tokens.py or build-prototype.py itself: python[3][.x] / py [-3] / uv run [flags] python,
    then interpreter flags (not -c or -m), then that script as the first argument."""
    i, n = 0, len(words)
    name = _command_name(words[0]) if words else ""
    if name == "uv":
        if n < 2 or words[1] != "run":
            return False
        i = 2
        while i < n and words[i].startswith("-"):
            i += 2 if words[i] in _UV_VALUE_FLAGS else 1
        if i >= n:
            return False
        name = _command_name(words[i])
    if not re.fullmatch(r"python[\d.]*|py", name):
        return False
    i += 1
    while i < n and words[i].startswith("-") and len(words[i]) > 1:
        if words[i] in ("-c", "-m"):
            return False
        i += 2 if words[i] in ("-X", "-W", "-Q") else 1
    return i < n and _BUILDER_SCRIPT.search(words[i]) is not None


_QUOTED = re.compile(r"'([^']*)'|\"((?:[^\"\\]|\\.)*)\"")


def _quoted(text: str) -> List[str]:
    """The contents of the quoted strings in text (backslash-escaped quotes unescaped)."""
    return [a if a or not b else b.replace('\\"', '"') for a, b in _QUOTED.findall(text)]


def _stage_targets(stage: str) -> List[str]:
    """The files one pipeline stage writes (best effort). A stage that runs a Plumb builder may write generated files
    itself; only its redirects and tee count."""
    cleaned = _NO_WRITE.sub(" ", stage)
    targets = [_unquote(m.group(1)) for m in _REDIR.finditer(cleaned)]
    for m in _TEE.finditer(cleaned):
        targets += [_unquote(w) for w in re.findall(_WORD, m.group(2))]
    rest = _TEE.sub(" ", _REDIR.sub(" ", cleaned))
    words = [_unquote(w) for w in re.findall(_WORD, rest)]
    while words and re.match(r"^[A-Za-z_]\w*=", words[0]):  # FOO=bar cmd
        words.pop(0)
    if words and words[0] in ("sudo", "command", "env", "nohup", "time"):
        words.pop(0)
    if not words or _runs_builder(words):
        return targets
    name = _command_name(words[0])
    args = words[1:]
    if name in ("sed", "gsed") and any(re.match(r"^-[a-zA-Z]*i", a) or a.startswith("--in-place") for a in args):
        targets += _sed_files(args)
    elif name == "perl" and any(re.match(r"^-[a-zA-Z]*i", a) for a in args):
        targets += _sed_files(args, perl=True)
    elif name in ("cp", "mv", "install", "rsync", "ln", "copy", "move"):
        pos = _positional(args, ("-t", "--target-directory", "-m", "--mode", "-o", "-g"))
        if len(pos) >= 2:
            targets.append(pos[-1])
    elif name in ("set-content", "add-content", "out-file", "clear-content", "sc", "ac", "tee-object"):
        value = _flag_value(args, _PS_PATH_FLAGS)
        pos = _positional(args, _PS_VALUE_FLAGS + _PS_PATH_FLAGS)
        targets += [value] if value else pos[:1]
    elif name in ("copy-item", "move-item", "cpi", "mi"):
        value = _flag_value(args, ("-destination",))
        pos = _positional(args, _PS_VALUE_FLAGS + _PS_PATH_FLAGS + ("-destination",))
        targets += [value] if value else pos[1:2]
    if _GENERIC.search(rest):  # a write that doesn't name its target in a way read here: every path it mentions,
        targets += re.findall(r"[^\s'\"`=(),;|&<>]+", rest)  # by its words and by every quoted string (spaces kept),
        for outer in _quoted(stage):  # also one level down (python -c "open('/a b/x.css', 'w')")
            targets += [outer] + _quoted(outer)
    return targets


_REMOVERS = ("rm", "rmdir", "unlink", "del", "erase", "rd", "remove-item", "ri")
_PS_REMOVERS = ("remove-item", "ri", "del", "erase", "rd")
_MOVERS = ("mv", "move", "move-item", "mi")


def _stage_removals(stage: str) -> List[str]:
    """The files or folders one pipeline stage removes or moves away (best effort): rm, rmdir, unlink, del / erase /
    rd (cmd), Remove-Item (ri, del), git rm, and the sources of mv / move, Move-Item (mi) and git mv."""
    rest = _TEE.sub(" ", _REDIR.sub(" ", _NO_WRITE.sub(" ", stage)))
    words = [_unquote(w) for w in re.findall(_WORD, rest)]
    while words and re.match(r"^[A-Za-z_]\w*=", words[0]):  # FOO=bar cmd
        words.pop(0)
    if words and words[0] in ("sudo", "command", "env", "nohup", "time"):
        words.pop(0)
    if not words:
        return []
    name, args = _command_name(words[0]), words[1:]
    if name == "git" and args and args[0] in ("rm", "mv"):
        name, args = args[0], args[1:]
    if name in ("del", "erase", "rd"):  # cmd's /q /s /f switches
        args = [a for a in args if not re.fullmatch(r"/[A-Za-z](?::\S*)?", a)]
    if name in _PS_REMOVERS:
        value = _flag_value(args, _PS_PATH_FLAGS)
        pos = _positional(args, _PS_VALUE_FLAGS + _PS_PATH_FLAGS)
        items = ([value] if value else []) + pos
    elif name in _REMOVERS:
        items = _positional(args, ())
    elif name in ("move-item", "mi"):
        value = _flag_value(args, _PS_PATH_FLAGS)
        pos = _positional(args, _PS_VALUE_FLAGS + _PS_PATH_FLAGS + ("-destination",))
        items = [value] if value else pos[:1]
    elif name in _MOVERS:
        pos = _positional(args, ("-t", "--target-directory", "-S", "--suffix"))
        into = any(a in ("-t", "--target-directory") or a.startswith("--target-directory=") for a in args)
        items = pos if into else pos[:-1]
    else:
        return []
    if name in _PS_REMOVERS + ("move-item", "mi"):  # PowerShell lists: a.css, b.css
        items = [x.strip() for item in items for x in item.split(",")]
    return [i for i in items if i]


# $HOME, ${HOME} (sh), %USERPROFILE% (cmd), $env:USERPROFILE / $env:HOME (PowerShell) at the start of a path: read as ~.
_HOME_VAR = re.compile(r"^(?:\$HOME|\$\{HOME\}|%USERPROFILE%|\$env:USERPROFILE|\$env:HOME)(?=[/\\]|$)", re.I)


def _shell_paths(command: str, cwd: str, stage_paths: Callable[[str], List[str]]) -> List[str]:
    out: List[str] = []
    base = cwd
    for part in _split(command, ("&&", "||", ";", "\n")):
        m = _CD.match(part)
        if m:
            target = _unquote(m.group(1))
            base = os.path.normpath(os.path.join(base, target.replace("\\", "/") if os.sep == "/" else target))
            continue
        for stage in _split(part, ("|",)):
            for t in stage_paths(stage):
                if not t or t in ("-", "/dev/null"):
                    continue
                p = t.replace("\\", "/") if os.sep == "/" else t
                p = _HOME_VAR.sub(lambda _m: "~", p)
                p = os.path.expanduser(p)
                full = os.path.normpath(p if os.path.isabs(p) else os.path.join(base, p))
                if full not in out:
                    out.append(full)
    return out


def shell_targets(command: str, cwd: str) -> List[str]:
    """The files a shell command (Bash or PowerShell) looks like it writes, as absolute paths (best effort). What
    build-tokens.py and build-prototype.py write themselves does not count (that is how generated files are meant to
    change), only the redirects of the pipeline stage that runs them; every other stage is read as usual.
    `cd DIR` moves the base for the commands after it; ~, $HOME, ${HOME}, %USERPROFILE% and $env:USERPROFILE are the
    home folder."""
    return _shell_paths(command, cwd, _stage_targets)


def shell_removals(command: str, cwd: str) -> List[str]:
    """The files or folders a shell command looks like it removes or moves away (rm, del, Remove-Item, git rm, the
    sources of mv / Move-Item / git mv), as absolute paths (best effort), read like shell_targets."""
    return _shell_paths(command, cwd, _stage_removals)
