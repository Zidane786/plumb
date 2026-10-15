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

A hook that fails open (a crash, a script it cannot load, a timeout) also writes one line to the Plumb feedback log,
~/.plumb/feedback/hooks.md (%USERPROFILE%\\.plumb\\feedback on Windows): Plumb's own mistakes, for Plumb's developers,
read with /plumb:feedback; never written into the project, private (0700 folders, a 0600 file, no symlink followed),
redacted (redact), and never able to fail or block the hook (log_failure).

Python 3.9+, standard library only.
"""

from __future__ import annotations

import fnmatch
import glob
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
from typing import Dict, List, Optional, Tuple

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
# The plugin's own copy of the design-system scripts, the only Python the hooks ever import or run (never the copies in
# a project: those run only on an explicit command, see SECURITY.md "Trust boundary").
PLUGIN_SCRIPTS = os.path.join(os.path.dirname(HOOKS_DIR), "assets", "skill", "scripts")
PLUMB_MD = "PLUMB.md"
SNAPSHOT_DAYS = 7
# Where Plumb's skills and scripts keep scratch files, in the project root (any skill may use it). Only init, create and
# extract write the marker file in it, SETUP_MARKER, while their setup runs (and remove the whole folder when it ends):
# while the marker exists the end-of-turn check stands down.
SETUP_TMP = ".plumb-tmp"
SETUP_MARKER = ".plumb-tmp/setup-in-progress"


SETUP_MARKER_HOURS = 6  # an older marker is a setup that never finished: the end-of-turn check runs again


def setup_marker_time(root: str) -> Optional[float]:
    """When <root>/.plumb-tmp/setup-in-progress was last written (its modification time), or None without one."""
    try:
        path = os.path.join(root, *SETUP_MARKER.split("/"))
        return os.path.getmtime(path) if os.path.isfile(path) else None
    except OSError:
        return None


def setup_marker_stale(root: str) -> Optional[float]:
    """The marker's time when it is older than SETUP_MARKER_HOURS (a setup left behind), else None."""
    when = setup_marker_time(root)
    if when is None or time.time() - when <= SETUP_MARKER_HOURS * 3600:
        return None
    return when


def setup_in_progress(root: str) -> bool:
    """A Plumb setup (init, create, extract) is running: <root>/.plumb-tmp/setup-in-progress exists and was written in
    the last SETUP_MARKER_HOURS hours. Anyone who can write in the project can create it, so it only turns off the
    soft end-of-turn check; the edit check and the guards never look at it."""
    when = setup_marker_time(root)
    return when is not None and time.time() - when <= SETUP_MARKER_HOURS * 3600
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
_LOG_CONTEXT: Dict[str, object] = {}  # the payload and project of this run, for log_failure


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


# Plumb's block inside a web copy (the same markers as _plumb.BLOCK_START / BLOCK_END; a test keeps them equal): the
# guard refuses only an edit that changes the text from the start marker to the end marker.
BLOCK_START = "/* plumb:start \u2014 GENERATED by Plumb, do not edit inside */"
BLOCK_END = "/* plumb:end */"


def block_text(text: str) -> Optional[str]:
    """Plumb's block in text (markers included), or None: no block, or broken markers (not one of each, start first)."""
    if text.count(BLOCK_START) != 1 or text.count(BLOCK_END) != 1:
        return None
    start, end = text.index(BLOCK_START), text.index(BLOCK_END)
    return text[start:end + len(BLOCK_END)] if end > start else None


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
    if isinstance(text, str) and text.startswith("\ufeff"):  # a UTF-8 BOM some Windows launchers write first
        text = text[1:]
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    payload = Payload(raw)
    _LOG_CONTEXT["payload"] = payload  # for log_failure: the event, tool and path of a hook that fails open
    return payload


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
# A trailing '   (note)' is a comment, unless it is a route kind (`Routes: app  (next-app)`), as in _plumb.
_NOTE = re.compile(r"\s{2,}\((?!\s*(?:next-app|next-pages|nuxt|sveltekit|angular|router)\s*\))[^)]*\)\s*$")
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
        skill with a PLUMB.md, else this project. Found once per hook run (the guard asks it for every path)."""
        cached = getattr(self, "_home_root", None)
        if cached is None:
            cached = self.root_s
            if self.skill_dir is not None:
                found = find_project(str(self.skill_dir.parent))
                if found is not None:
                    cached = str(found)
            self._home_root = cached
        return cached


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
                project = Project(root)
                _LOG_CONTEXT["project"] = project  # for log_failure
                return project
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
        log_failure(f"the plugin's {file_name} is missing, so the design checks were skipped",
                    f"the plugin's {file_name} loads and the design checks run")
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
        log_failure(f"cannot load the plugin's {file_name} ({type(exc).__name__}: {exc}), so the design checks were "
                    f"skipped", f"the plugin's {file_name} loads and the design checks run", exc=exc)
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


# ---------------------------------------------------------------- the Plumb feedback log (hook failures)

FEEDBACK_HOOKS = "hooks.md"
FEEDBACK_MAX_BYTES = 512 * 1024  # a bigger hooks.md is left alone: the log never grows without bound
FEEDBACK_FIELD = 240  # characters kept of each free-text field (one line each, never a source dump)
FEEDBACK_LINE = 1200  # characters kept of a whole line
FEEDBACK_HEADER = ("# Plumb hook failures\n\n"
                   "Written by Plumb's hooks when one failed open (a crash or a timeout), one line each in Given / "
                   "Expected form. Plumb's own mistakes only; read them with /plumb:feedback (Kiro: /plumb-feedback).\n\n")


def _make_private(folder: Path) -> None:
    """Tighten a folder of ours to 0700 (POSIX): a real directory (never through a symlink: it is opened with
    O_NOFOLLOW and changed through that handle) owned by this user. The agent's write tool may have made it 0775 under
    a umask of 002; someone else's folder or a symlink is left alone (and then refused by _ours)."""
    if not hasattr(os, "getuid") or not hasattr(os, "fchmod"):
        return
    st = os.lstat(str(folder))
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or not st.st_mode & 0o077:
        return
    fd = os.open(str(folder), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        if os.fstat(fd).st_uid == os.getuid():
            os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def feedback_dir(create: bool = True) -> Optional[Path]:
    """The Plumb feedback folder: ~/.plumb/feedback (%USERPROFILE%\\.plumb\\feedback on Windows), outside every project.
    ~/.plumb and feedback/ are created 0700 (create=False: only an existing one is used), and made 0700 when they are
    this user's own real folders with wider permissions (_make_private). None when either is missing (create=False), a
    symlink (or on Windows any reparse point), someone else's or still writable by others (the same rules as
    snapshot_dir), or the home folder is missing."""
    try:
        home = Path.home()
        if not home.is_dir():
            return None
        for folder in (home / ".plumb", home / ".plumb" / "feedback"):
            if create:
                try:
                    os.mkdir(str(folder), 0o700)
                except FileExistsError:
                    pass
            elif not os.path.lexists(str(folder)):
                return None
            _make_private(folder)
            if not _ours(os.lstat(str(folder)), folder=True):
                return None
        return home / ".plumb" / "feedback"
    except (OSError, RuntimeError, KeyError):
        return None


_LITERAL = re.compile(r"""(?<![\w])(['"])(?:(?!\1)[^\n]){4,}?\1(?![\w])""")
_ABS_POSIX = re.compile(r"""(?<![\w.~/-])/(?:[^\s'"<>|:;,()/]+/)+([^\s'"<>|:;,()/]+)""")
_ABS_WINDOWS = re.compile(r"""(?<![\w])[A-Za-z]:[\\/](?:[^\s'"<>|:;,()\\/]+[\\/])*([^\s'"<>|:;,()\\/]+)""")
_BEARER = re.compile(r"\bBearer\s+[^\s,;'\"]+", re.I)
_KEY_VALUE = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|"
                        r"client[_-]?secret|auth(?:orization)?)(\s*[=:]\s*)(?!Bearer\b)(?!<redacted>)[^\s,;'\"]+")
_TOKENS = re.compile(r"\b(?:(?:sk|pk|rk)-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abposr]-[A-Za-z0-9-]{10,}|"
                     r"(?:AKIA|ASIA)[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]*){0,2}|[0-9a-fA-F]{32,})\b")
_LONG_RUN = re.compile(r"(?<![\w+/=-])[A-Za-z0-9+_-]{32,}={0,2}")


def redact(text: str, root: str = "") -> str:
    """A failure message with the data taken out and its shape kept, for hooks.md: paths inside the project become
    project-relative (kept, quoted or not); other quoted literals longer than three characters become '<redacted>' (a short one such as a key name
    stays); other absolute paths keep only their base name (<path>/name); token-like strings (sk-…, ghp_…, xox…-,
    AKIA…, a JWT, long hex or base64 runs) and the values of key=value secrets (password, token, api_key, Bearer …)
    become <redacted>."""
    out = str(text).replace("\x00", "")
    for base in sorted({root, os.path.realpath(root)}, key=len, reverse=True) if root else ():
        for sep in {os.sep, "/"}:
            out = out.replace(base + sep, "\x00")  # marks a project path: kept, even quoted
        out = out.replace(base, "<project>")
    out = _LITERAL.sub(lambda m: m.group(0) if m.group(0)[1:2] == "\x00" else
                       f"{m.group(1)}<redacted>{m.group(1)}", out).replace("\x00", "")
    out = _ABS_WINDOWS.sub(r"<path>/\1", out)
    out = _ABS_POSIX.sub(r"<path>/\1", out)
    out = _BEARER.sub("Bearer <redacted>", out)
    out = _KEY_VALUE.sub(r"\1\2<redacted>", out)
    out = _TOKENS.sub("<redacted>", out)
    return _LONG_RUN.sub(lambda m: "<redacted>" if re.search(r"\d", m.group(0)) and re.search(r"[A-Za-z]", m.group(0))
                         else m.group(0), out)


def _one_line(text: object, root: str = "") -> str:
    out = " ".join(redact(" ".join(str(text).split()), root).split()).replace("·", "-")
    return out if len(out) <= FEEDBACK_FIELD else out[:FEEDBACK_FIELD - 1] + "…"


def _cli_name(payload: Optional["Payload"]) -> str:
    if kiro_run():
        return "kiro"
    if os.environ.get("COPILOT_CLI") or (payload is not None and payload.copilot):
        return "copilot-cli"
    return "claude-code"


def _failure_where(exc: Optional[BaseException]) -> str:
    """The last frames of a crash's traceback, as file:line function (base names only, never a full path)."""
    if exc is None or exc.__traceback__ is None:
        return ""
    import traceback
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if not f.filename.startswith("<")][-2:]
    return " < ".join(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in reversed(frames))


def _log_project() -> Optional[Path]:
    project = _LOG_CONTEXT.get("project")
    if isinstance(project, Project):
        return project.root
    try:  # a crash before load_project: only a folder holding a PLUMB.md is a Plumb project (no PLUMB.md: no log)
        return find_project(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    except Exception:  # noqa: BLE001
        return None


_NEW_FILE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def _create_with(path: Path, data: bytes) -> bool:
    """Create `path` already holding `data` (the header and the first line), atomically: a private temporary file is
    linked into place, so no other hook ever sees hooks.md without its header. False when it exists already (another
    hook made it first: append instead)."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    fd = os.open(str(tmp), _NEW_FILE, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            os.link(str(tmp), str(path))
            return True
        except FileExistsError:
            return False
        except (OSError, AttributeError, NotImplementedError):  # no hard links here: one exclusive create instead
            try:
                fd2 = os.open(str(path), _NEW_FILE, 0o600)
            except FileExistsError:
                return False
            with os.fdopen(fd2, "wb") as fh:
                fh.write(data)
            return True
    finally:
        try:
            os.unlink(str(tmp))
        except OSError:
            pass


def log_failure(given: str, expected: str, category: str = "crash", exc: Optional[BaseException] = None,
                exit_code: int = 0, outcome: Optional[str] = None) -> None:
    """Append one line about a hook that failed open to ~/.plumb/feedback/hooks.md (Plumb's own mistakes, for Plumb's
    developers; never written into the project). Only in a project with a PLUMB.md. Given and Expected are redacted
    (redact) and cut to one short line. The same line (hook, project, Given) is written once a day; a timeout once per
    project and Plumb version (a slow repo is not news every day). Never raises, never prints, never blocks: any
    problem (no private folder, a symlinked or foreign hooks.md, a full log) leaves the log out. A PlumbError is the
    scripts' actionable refusal about the project's own files (a broken tokens file, a snapshot that is not valid):
    the project's problem, never logged. outcome: what the hook did instead of failing open (the shell guard: whether
    it refused)."""
    try:
        if exc is not None and type(exc).__name__ == "PlumbError":
            return
        root = _log_project()
        if root is None:
            return
        folder = feedback_dir()
        if folder is None:
            return
        payload = _LOG_CONTEXT.get("payload")
        p = payload if isinstance(payload, Payload) else None
        hook = os.path.basename(sys.argv[0] or "") or "hook"
        real_root = os.path.realpath(str(root))
        rel = ""
        if p is not None and p.file_path:
            inside = under(resolve(p.file_path, p.cwd or str(root)), real_root)
            rel = inside if inside is not None else os.path.basename(p.file_path)
        fields = [hook, category, f"Plumb {plugin_version() or 'unknown'}", _cli_name(p), sys.platform,
                  f"project {root.name}", f"event {(p.event if p else '') or SCRIPT_TRIGGERS.get(hook, '?')}",
                  f"tool {(p.tool_name if p else '') or '-'}", f"path {_one_line(rel) or '-'}",
                  outcome or f"exit {exit_code} (failed open)", f"Given: {_one_line(given, str(root))}",
                  f"Expected: {_one_line(expected, str(root))}"]
        where = _failure_where(exc)
        if where:
            fields.append(f"at {where}")
        rest = " · ".join(fields)[:FEEDBACK_LINE]
        now = time.localtime()
        day = time.strftime("%Y-%m-%d", now)
        path = folder / FEEDBACK_HOOKS
        if os.path.lexists(str(path)):
            st = os.lstat(str(path))
            if not _ours(st, folder=False) or st.st_size >= FEEDBACK_MAX_BYTES:
                return
            text = read_private(path) or ""
            if any(ln.split(" ", 3)[3:] == [rest] and (category == "timeout" or ln.startswith(f"- {day} "))
                   for ln in text.splitlines()):
                return  # said already (today; for a timeout, on this Plumb version)
        line = f"- {day} {time.strftime('%H:%M', now)} {rest}\n"
        if not os.path.lexists(str(path)) and _create_with(path, (FEEDBACK_HEADER + line).encode("utf-8")):
            return
        flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(str(path), flags)
        with os.fdopen(fd, "ab") as fh:
            if not _ours(os.fstat(fh.fileno()), folder=False):
                return
            fh.write(line.encode("utf-8"))
    except Exception:  # noqa: BLE001 - the log never fails a hook
        return


# ---------------------------------------------------------------- shell commands
#
# What a Bash or PowerShell command writes, moves away or removes, for the guard. The earlier reader
# (_shell_legacy.py) decides; this reader adds what it finds, and may turn the earlier reader's refusal into an allow
# only in three provable patterns and a commit message (pre_edit._proven):
# (a) a here-document / here-string / echo / printf / tee text written to a file that the same command may not use
#     again (_data_file_used: it does not run, source, pipe, import, or name the file, its stem or its folder a second
#     time; it is not code while the command starts an interpreter; it is not a file a program picks up by itself:
#     sitecustomize.py, *.pth, .bashrc, .npmrc, package.json, Makefile, .git/, .husky/, a git hook): the text is data;
# (b) the words of a read-only program (cat, head, tail, grep, rg, wc, diff, ls, stat, file, sha*sum, jq …);
# (c) inline code (python -c, node -e, a here-document fed to an interpreter) that gives each guarded literal straight
#     to a read sink (open(p) to read, json.load(open(p)), Path(p).read_text / exists / is_file, spec_from_file_location,
#     fs.readFileSync / existsSync, require), runs no command or code, opens nothing through opener= / os.open /
#     os.fdopen, imports nothing by a name it builds, and writes only to plain literals that are not guarded, not next
#     to a guarded file, not /dev/fd/ or /proc/, and not used again (a); printing a guarded literal is not a read;
# (d) a git commit message: the values of -m / --message / -F / --file / -t and stdin are data; not with a git option
#     that runs something (-c, --config-env, --exec-path), a variable set before git, or a hook the command wrote.
# Anything else keeps the earlier decision: an unknown program's words (other text), a runner (npx, poetry run …),
# xargs, a script run, a variable or $( ) it cannot resolve in a target or a cd, code piped from a file, an f-string,
# nesting deeper than it reads, too many globbed paths, a parse error, or the time budget. Brackets nested past
# _MAX_NESTING are not read at all, and pre_edit refuses such a command (and one the reader crashed on) when it names
# a guarded path. A write target it cannot work out ($( ), backticks, ${…}, a for / read loop variable) is kept in
# eff.computed with the text it is built from (variable values, the words a loop variable takes; the whole command
# for ${!N} or a read from an unknown source), and pre_edit refuses it when that text names a guarded path in full.
#
# A small lexer (quotes, escapes, here-documents, $( ), backticks, process substitution, subshells, comments, the
# operators) splits the command into simple commands. Their write targets: a redirect (>, >>, 1>, 2>, &>, >|, <>),
# tee [-a], sed -i / perl -i / sed's w FILE, sort -o, uniq IN OUT, the destination of cp / mv / install / rsync / ln (a
# folder destination writes <folder>/<source name>; a recursive copy or a move writes into the folder: refused like a
# removal when it holds a guarded file), truncate, dd of=, curl -o / --output-dir / wget -O, PowerShell's Set-Content,
# Add-Content, Out-File, New-Item, Copy-Item, Move-Item; the removals (rm, del, Remove-Item, git rm, the sources of
# mv …). A shell's own script (bash -c with $1 … mapped, a here-document fed to a shell, eval, source <(echo …),
# script -c, su -c, watch, find -exec) is read as commands; a file the command wrote and then runs (python FILE,
# bash FILE, source, make -f, python - < FILE) is read as the code it runs; an interpreter's inline code for its writes
# (open(…, "w"), Path(…).write_text, shutil, os.replace, fs.writeFile, [IO.File]::WriteAllText …), with write targets
# put together from the code's constants (os.path.join, Path / 'x', +, f-strings, %, .format, ${}). Shell variables set
# in the command (OUT=…), $PWD and $CLAUDE_PROJECT_DIR are followed; braces and globs in a target are expanded.


# A cheap first look: a command with none of these cannot write or remove a file (this reader's forms and the
# previous reader's).
WRITE_HINT = re.compile(r">|\btee\b|\bsed\b|\bperl\b|\bcp\b|\bmv\b|\binstall\b|\brsync\b|\bln\b|\bdd\b|truncate|"
                        r"write|open\(|\.dump|shutil|os\.(?:replace|rename)|-content\b|out-file|copy-item|move-item|"
                        r"::|append|copyfile|\bfs\.|rename|\bcopy\b|cpSync|\bcp\(|\bcurl\b|\bwget\b|new-item|\bni\b|"
                        r"inplace|remove|rmtree|unlink|rmdir|rmSync|tee-object|\bsc\b|\bac\b|\bcpi\b|\bsort\b|\buniq\b|"
                        # removals and moves: rm, del, erase, rd, Remove-Item, ri, move, mi
                        r"\brm\b|\bdel\b|\berase\b|\brd\b|remove-item|\bri\b|\bmove\b|\bmi\b",
                        re.I)
SHELL_BUDGET = 1.5  # seconds this reader may take (the hook's timeout is 10 s); past it the previous reader decides
_MAX_TARGETS = 2000  # more targets than this: the reader is unsure (the previous reader decides on the rest)
_MAX_GLOB = 500
_ESCAPABLE = frozenset(" \t\n'\"\\$`;&|<>()*?[]#~{}!")  # outside quotes \x is x for these; \x stays \x for the rest
_CONTROL = ("&&", "||", ";;", "|&", ";", "|", "&")
_REDIRS = ("&>>", "&>", "<<<", "<<-", "<<", "<>", "<&", ">>", ">|", ">&", "<", ">")
_WRITE_REDIRS = frozenset((">", ">>", ">|", "&>", "&>>", "<>"))
_NOT_FILES = frozenset(("-", "/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "nul", "$null", "con"))
_ANSI = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "0": "\0", "e": "\x1b", "a": "\a"}
_MAX_DEPTH = 6  # nested scripts (bash -c inside $( ) inside eval …) read this deep
_UV_VALUE_FLAGS = ("--with", "--python", "-p", "--project", "--directory", "--from", "--env-file", "--group", "--extra",
                   "--with-requirements", "--index", "--index-url")


def _balanced(text: str, i: int, open_ch: str = "(", close_ch: str = ")") -> int:
    """The index of the bracket that closes text[i] (quotes and escapes followed), or len(text)."""
    depth, quote, n = 0, "", len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = ""
        elif c == "\\":
            i += 2
            continue
        elif c in "'\"`":
            quote = c
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _backtick_end(text: str, i: int) -> int:
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "`":
            return i
        i += 1
    return -1


def _dquote(text: str, i: int, buf: List[str], subs: List[str]) -> int:
    """Read a double-quoted string from text[i] (after the opening quote) into buf; $( ) and backticks into subs."""
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            return i + 1
        if c == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt in '"\\$`':
                buf.append(nxt)
                i += 2
                continue
            if nxt == "\n":
                i += 2
                continue
        if text.startswith("$((", i):
            end = _balanced(text, i + 1)
            buf.append(text[i:end + 1])
            i = end + 1
            continue
        if text.startswith("$(", i):
            end = _balanced(text, i + 1)
            subs.append(text[i + 2:end])
            buf.append(text[i:end + 1])
            i = end + 1
            continue
        if c == "`":
            end = _backtick_end(text, i + 1)
            if end > 0:
                subs.append(text[i + 1:end])
                buf.append(text[i:end + 1])
                i = end + 1
                continue
        buf.append(c)
        i += 1
    return n


def _read_bodies(text: str, i: int, pending: List[Tuple[int, str, bool]], toks: List[tuple]) -> int:
    """Read the here-document bodies that start after a line's end, in order; a body whose end line never comes runs
    to the end (bash runs nothing after it)."""
    n = len(text)
    for index, word, strip_tabs in pending:
        lines: List[str] = []
        while i < n:
            end = text.find("\n", i)
            line = text[i:] if end < 0 else text[i:end]
            i = n if end < 0 else end + 1
            if line.endswith("\r"):
                line = line[:-1]
            if strip_tabs:
                line = line.lstrip("\t")
            if line == word:
                break
            lines.append(line)
        toks[index] = ("r", toks[index][1], "\n".join(lines))
    return i


def _ansi_escape(text: str, j: int) -> Tuple[str, int]:
    """The character a $'...' escape at text[j] (after the backslash) stands for, and the index after it: \\n, \\t …,
    \\xHH, \\NNN (octal), \\uHHHH, \\UHHHHHHHH, \\cX."""
    c = text[j]
    for lead, size, base in (("x", 2, 16), ("u", 4, 16), ("U", 8, 16)):
        if c == lead:
            m = re.match(r"[0-9A-Fa-f]{1,%d}" % size, text[j + 1:j + 1 + size])
            if m:
                return chr(min(int(m.group(0), base), 0x10FFFF)), j + 1 + len(m.group(0))
            return "\\" + c, j + 1
    m = re.match(r"[0-7]{1,3}", text[j:j + 3])
    if m:
        return chr(int(m.group(0), 8)), j + len(m.group(0))
    if c == "c" and j + 1 < len(text):
        return chr(ord(text[j + 1]) & 0x1F), j + 2
    return _ANSI.get(c, c), j + 1


def _lex(text: str) -> List[tuple]:
    """The tokens of a shell command: ("w", text, quoted, subs) words (quotes removed; subs = the scripts of their
    $( ), backticks and <( ) / >( )), ("r", operator, here-document body) redirects, ("op", operator) and ("nl",)."""
    toks: List[tuple] = []
    pending: List[Tuple[int, str, bool]] = []  # here-documents whose body starts after the next line end
    delim_for: Optional[Tuple[int, bool]] = None  # a << just read: the next word is its end word
    buf: List[str] = []
    subs: List[str] = []
    quoted = word = False
    wdepth = 0  # ( inside a word (PowerShell's [IO.File]::Write(…), extglob): its ) is the word's too
    i, n = 0, len(text)

    def flush() -> None:
        nonlocal buf, subs, quoted, word, wdepth, delim_for
        if not word:
            return
        value = "".join(buf)
        if delim_for is not None:
            pending.append((delim_for[0], value.replace("\\", ""), delim_for[1]))
            delim_for = None
        toks.append(("w", value, quoted, subs))
        buf, subs, quoted, word, wdepth = [], [], False, False, 0

    while i < n:
        c = text[i]
        if c in " \t\r":
            flush()
            i += 1
        elif c == "\n":
            flush()
            toks.append(("nl",))
            i += 1
            if pending:
                i = _read_bodies(text, i, pending, toks)
                pending = []
        elif c == "\\":
            if text.startswith("\n", i + 1):
                i += 2
            elif text.startswith("\r\n", i + 1):
                i += 3
            elif i + 1 < n:
                nxt = text[i + 1]
                buf.append(nxt if nxt in _ESCAPABLE else c + nxt)
                quoted = quoted or nxt in _ESCAPABLE
                word = True
                i += 2
            else:
                buf.append(c)
                word = True
                i += 1
        elif c == "'":
            end = text.find("'", i + 1)
            end = n if end < 0 else end
            buf.append(text[i + 1:end])
            quoted = word = True
            i = end + 1
        elif text.startswith("$'", i):
            j, out = i + 2, []
            while j < n and text[j] != "'":
                if text[j] == "\\" and j + 1 < n:
                    ch, j = _ansi_escape(text, j + 1)
                    out.append(ch)
                else:
                    out.append(text[j])
                    j += 1
            buf.append("".join(out))
            quoted = word = True
            i = j + 1
        elif c == '"':
            i = _dquote(text, i + 1, buf, subs)
            quoted = word = True
        elif text.startswith("$((", i) or (not word and text.startswith("((", i)):  # arithmetic: << is a shift
            end = _balanced(text, i + (1 if c == "$" else 0))
            buf.append(text[i:end + 1])
            word = True
            i = end + 1
        elif text.startswith("$(", i) or (not word and c in "<>" and text.startswith("(", i + 1)):
            end = _balanced(text, i + 1)  # $(cmd), <(cmd), >(cmd): a script that runs
            subs.append(text[i + 2:end])
            buf.append(text[i:end + 1])
            word = True
            i = end + 1
        elif text.startswith("${", i):
            end = _balanced(text, i + 1, "{", "}")
            buf.append(text[i:end + 1])
            word = True
            i = end + 1
        elif c == "`":
            end = _backtick_end(text, i + 1)
            if end < 0:
                buf.append(c)
                i += 1
            else:
                subs.append(text[i + 1:end])
                buf.append(text[i:end + 1])
                i = end + 1
            word = True
        elif c == "#" and not word:
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif c in "<>" or text.startswith("&>", i):
            if word and not quoted and "".join(buf).isdigit():
                buf, subs, word = [], [], False  # 2>, 1>>: the file descriptor
            else:
                flush()
            op = next(o for o in _REDIRS if text.startswith(o, i))
            toks.append(("r", op, None))
            i += len(op)
            if op in ("<<", "<<-"):
                delim_for = (len(toks) - 1, op == "<<-")
        elif c in "&|;":
            flush()
            op = next(o for o in _CONTROL if text.startswith(o, i))
            toks.append(("op", op))
            i += len(op)
        elif c == "(" and word:
            buf.append(c)
            wdepth += 1
            i += 1
        elif c == ")" and word and wdepth:
            buf.append(c)
            wdepth -= 1
            i += 1
        elif c in "()":
            flush()
            toks.append(("op", c))
            i += 1
        else:
            buf.append(c)
            word = True
            i += 1
    flush()
    for index, _word, _strip in pending:  # a here-document on the last line: an empty body
        toks[index] = ("r", toks[index][1], "")
    return toks


class _Simple:
    """One simple command: its words, write redirects, stdin bodies (here-documents, here-strings) and the scripts of
    its command substitutions; piped says its input comes from the command before it."""

    __slots__ = ("words", "quoted", "redirs", "appends", "inputs", "stdin", "subs", "piped", "pipe_out")

    def __init__(self, piped: bool = False) -> None:
        self.words: List[str] = []
        self.quoted: List[bool] = []
        self.redirs: List[str] = []
        self.appends: List[str] = []  # the redirect targets written with >> (appended to)
        self.inputs: List[str] = []  # < FILE
        self.stdin: List[str] = []
        self.subs: List[str] = []
        self.piped = piped
        self.pipe_out = False  # its output goes into the next command (|)

    def empty(self) -> bool:
        return not (self.words or self.redirs or self.stdin or self.subs)


def _commands(toks: List[tuple]) -> List[tuple]:
    """("cmd", _Simple), ("push",) at a subshell's ( and ("pop",) at its ), in order."""
    events: List[tuple] = []
    cur = _Simple()
    k = 0
    while k < len(toks):
        t = toks[k]
        if t[0] == "w":
            cur.words.append(t[1])
            cur.quoted.append(t[2])
            cur.subs += t[3]
        elif t[0] == "r":
            op = t[1]
            nxt = toks[k + 1] if k + 1 < len(toks) and toks[k + 1][0] == "w" else None
            if nxt is not None:
                k += 1
                cur.subs += nxt[3]
            if op in ("<<", "<<-"):
                cur.stdin.append(t[2] or "")
            elif op == "<<<":
                if nxt is not None:
                    cur.stdin.append(nxt[1])
            elif op == "<" and nxt is not None:
                cur.inputs.append(nxt[1])
            elif nxt is not None and (op in _WRITE_REDIRS or (op == ">&" and not re.fullmatch(r"\d*-?", nxt[1]))):
                cur.redirs.append(nxt[1])
                if op in (">>", "&>>", "<>"):
                    cur.appends.append(nxt[1])
        else:
            piped = t[0] == "op" and t[1] in ("|", "|&")
            if not cur.empty():
                cur.pipe_out = piped
                events.append(("cmd", cur))
            cur = _Simple(piped=piped)
            if t[0] == "op" and t[1] == "(":
                events.append(("push",))
            elif t[0] == "op" and t[1] == ")":
                events.append(("pop",))
        k += 1
    if not cur.empty():
        events.append(("cmd", cur))
    return events


# $HOME, ${HOME} (sh), %USERPROFILE% (cmd), $env:USERPROFILE / $env:HOME (PowerShell) at the start of a path: read as ~.
_HOME_VAR = re.compile(r"^(?:\$HOME|\$\{HOME\}|%USERPROFILE%|\$env:USERPROFILE|\$env:HOME)(?=[/\\]|$)", re.I)
_VAR = re.compile(r"\$(?:\{([A-Za-z_]\w*|\d+|[@*])\}|([A-Za-z_]\w*|\d|[@*]))")  # $NAME, ${NAME}, $1, "$@"
_HERE_PREFIX = re.compile(r"^(?:\$PWD|\$\{PWD\}|\$\(pwd\)|`pwd`)(?=[/\\]|$)")
_ROOT_PREFIX = re.compile(r"^(?:\$CLAUDE_PROJECT_DIR|\$\{CLAUDE_PROJECT_DIR\}|\$env:CLAUDE_PROJECT_DIR"
                          r"|\$\(git rev-parse --show-toplevel\)|`git rev-parse --show-toplevel`)(?=[/\\]|$)")


class _Budget(Exception):
    """The reader's time budget ran out."""


class _Scope:
    """Where a command runs: its folders (more than one when a cd could not be resolved exactly), the variables set
    earlier in the command, pushd's stack, and (shared by the whole command) the files it wrote, with their text when
    the reader knows it."""

    __slots__ = ("bases", "vars", "dirs", "written", "loops")

    def __init__(self, bases: Tuple[str, ...], variables: Dict[str, str], dirs: Optional[List[Tuple[str, ...]]] = None,
                 written: Optional[Dict[str, Optional[str]]] = None,
                 loops: Optional[Dict[str, List[str]]] = None) -> None:
        self.bases = bases
        self.vars = variables
        self.dirs = dirs if dirs is not None else []
        self.written = written if written is not None else {}
        self.loops = loops if loops is not None else {}  # for / read variables: the words they may take

    def copy(self) -> "_Scope":
        return _Scope(self.bases, dict(self.vars), list(self.dirs), self.written, dict(self.loops))

    def expand(self, word: str) -> str:
        return _VAR.sub(lambda m: self.vars.get(m.group(1) or m.group(2), m.group(0)), word) if "$" in word else word


def _braces(word: str, limit: int = 64) -> List[str]:
    """{a,b} expanded (the first group, then the rest), at most limit words."""
    m = re.search(r"\{([^{}]*,[^{}]*)\}", word)
    if not m:
        return [word]
    out: List[str] = []
    for part in m.group(1).split(","):
        out += _braces(word[:m.start()] + part + word[m.end():], limit)
        if len(out) >= limit:
            break
    return out[:limit]


class ShellEffects:
    """What a shell command writes (files, and folders it writes into), removes, and what is needed to judge it against
    the earlier reader: unsure (why the reader cannot prove anything: the earlier reader decides), other (text outside
    the provable positions: a guarded path in it means the earlier reader decides), code_writes (inline code's plain
    literal targets: one next to a guarded file means the earlier reader decides), trouble (a budget overrun or an
    internal error, for the hooks' log). See the notes above."""

    def __init__(self, root: Optional[str], deadline: float) -> None:
        self.root = root
        self.deadline = deadline
        self.writes: List[str] = []
        self.removals: List[str] = []
        self.folder_writes: List[str] = []
        self.code_writes: List[str] = []
        self.other: List[Tuple[str, Tuple[str, ...]]] = []  # (text, the folders it was in)
        self.unsure: List[str] = []
        self.trouble: Optional[Tuple[str, str, Optional[BaseException]]] = None
        self.data_files: List[Tuple[str, str]] = []  # (absolute path, the word) of what (a) wrote
        # targets the reader cannot work out ($( ), backticks, ${…}): their text (with the values of the variables
        # they use) and the folders they were in; pre_edit refuses one that names a guarded path
        self.computed: List[Tuple[str, Tuple[str, ...]]] = []
        self.command = ""  # the whole command (an indirect ${!N} target is checked against all of it)
        self._seen: Dict[int, set] = {0: set(), 1: set(), 2: set(), 3: set()}

    def doubt(self, why: str) -> None:
        if why not in self.unsure:
            self.unsure.append(why)

    def tick(self) -> None:
        if time.monotonic() > self.deadline:
            raise _Budget()

    def note(self, scope: _Scope, *texts: str) -> None:
        """Text outside the provable positions (an unknown command's words, code's literals, an assignment's value),
        with the folders it was in. Past _MAX_TARGETS texts the reader is unsure."""
        for t in texts:
            if not t:
                continue
            if len(self.other) >= _MAX_TARGETS:
                self.doubt("more text than the reader checks")
                return
            self.other.append((t, scope.bases))

    def _paths(self, word: str, scope: _Scope, strict: bool, target: bool = False) -> List[str]:
        """The absolute paths a word names: variables set in the command expanded, $PWD the folder,
        $CLAUDE_PROJECT_DIR the project, ~ and $HOME the home folder; in a target (strict) braces and globs expanded,
        and a part left unresolved ($X, `…`) makes the reader unsure."""
        if not word or word.lower() in _NOT_FILES or word.startswith("/dev/fd/"):
            return []
        w = scope.expand(word)
        bases = scope.bases
        m = _HERE_PREFIX.match(w)
        if m:
            w = w[m.end():].lstrip("/\\") or "."
        else:
            m = _ROOT_PREFIX.match(w)
            if m:
                env = os.environ.get("CLAUDE_PROJECT_DIR") if "CLAUDE_PROJECT_DIR" in m.group(0) else None
                root = env or self.root
                if not env and strict:
                    self.doubt("a path under a folder the reader can only guess")
                if root:
                    w = w[m.end():].lstrip("/\\") or "."
                    bases = (root,) if env else tuple(dict.fromkeys(scope.bases + (root,)))
        if os.sep == "/":
            w = w.replace("\\", "/")
        w = os.path.expanduser(_HOME_VAR.sub(lambda _m: "~", w))
        if strict and ("$" in w or "`" in w):
            if target and len(self.computed) < _MAX_TARGETS:
                used: List[str] = []
                for m in re.finditer(r"\$\{?#?(!?)([A-Za-z_]\w*)", word):
                    name = m.group(2)
                    used += [scope.vars[name]] if name in scope.vars else []
                    used += scope.loops.get(name, [])
                    if m.group(1) or scope.loops.get(name) == [_ANY]:  # ${!N}, read from an unknown source
                        used.append(self.command)
                self.computed.append((" ".join([word, w] + used), scope.bases))
            self.doubt("a variable or a command the reader cannot resolve in a path")
        out: List[str] = []
        for x in (_braces(w) if strict else [w]):
            for b in bases:
                full = os.path.normpath(x if os.path.isabs(x) else os.path.join(b, x))
                out.append(full)
                if strict and re.search(r"[*?\[]", x):
                    matches = glob.glob(full)
                    if len(matches) > _MAX_GLOB:
                        self.doubt("a glob with more matches than the reader checks")
                    out += [os.path.normpath(p) for p in matches[:_MAX_GLOB]]
        return out

    def _add(self, kind: int, word: str, scope: _Scope) -> List[str]:
        lst = (self.writes, self.removals, self.folder_writes, self.code_writes)[kind]
        seen = self._seen[kind]
        found = self._paths(word, scope, True, kind < 3)
        for p in found:
            if p in seen:
                continue
            if len(lst) >= _MAX_TARGETS:
                self.doubt("more paths than the reader checks")
                break
            seen.add(p)
            lst.append(p)
        return found

    def write(self, word: str, scope: _Scope, text: Optional[str] = None) -> None:
        """A file write. text: what the file then holds, when the reader knows it (a here-document, echo's words)."""
        for p in self._add(0, word, scope):
            scope.written[p] = text

    def remove(self, word: str, scope: _Scope) -> None:
        self._add(1, word, scope)

    def write_folder(self, word: str, scope: _Scope) -> None:
        """A write into a folder (a recursive copy, a move of a folder, code writing what it lists there): refused like
        a removal when the folder holds a guarded file."""
        for p in self._add(2, word, scope):
            scope.written[p] = None


def _command_name(word: str) -> str:
    name = re.split(r"[/\\]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


_RESERVED = frozenset(("if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "coproc"))
# Commands that run the rest of their words as a command (read through), and their flags that take a value.
_WRAPPERS: Dict[str, Tuple[str, ...]] = {
    "sudo": ("-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group"), "doas": ("-u", "-C"),
    "command": (), "builtin": (), "exec": ("-a",), "nohup": (), "time": ("-f", "-o"), "env": ("-u",),
    "nice": ("-n",), "ionice": ("-c", "-n", "-p"), "stdbuf": ("-i", "-o", "-e"),
    "timeout": ("-s", "-k", "--signal", "--kill-after"), "xargs": ("-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"),
    "chronic": (), "unbuffer": (), "caffeinate": ("-w", "-t"), "busybox": (),
}
# Runners (read through, but the reader is unsure: what they run is resolved by another tool): name → its subcommands
# that run a command ("" = the name itself runs one).
_RUNNERS: Dict[str, Tuple[str, ...]] = {
    "poetry": ("run",), "pipenv": ("run",), "pdm": ("run",), "hatch": ("run",), "rye": ("run",), "pixi": ("run",),
    "conda": ("run",), "mamba": ("run",), "micromamba": ("run",), "npm": ("exec", "x"), "pnpm": ("exec", "dlx"),
    "yarn": ("exec", "dlx"), "bun": ("x",), "npx": ("",), "bunx": ("",), "uvx": ("",), "pipx": ("run",),
}
_RUNNER_VALUE_FLAGS = ("-n", "--name", "-p", "--prefix", "--from", "--with", "--python", "-e", "--environment",
                       "--package", "--spec", "-c", "--call", "--env", "--cwd")


def _command_start(words: List[str], eff: ShellEffects) -> int:
    """The index of the word that names the command: after FOO=bar, reserved words (if, then, do …), wrappers that run
    their words as a command (sudo, env, nice, timeout, xargs, busybox, uv run …) and runners (npx, poetry run …)."""
    i, n = 0, len(words)
    while i < n:
        w = words[i]
        name = _command_name(w)
        if re.match(r"^[A-Za-z_]\w*=", w) or w in _RESERVED:
            i += 1
        elif name in _WRAPPERS:
            if name == "xargs":
                eff.doubt("xargs adds words the reader cannot see")
            i += 1
            while i < n and words[i].startswith("-") and len(words[i]) > 1:
                if words[i] == "--":
                    i += 1
                    break
                if name == "env" and (words[i] in ("-C", "-S", "--chdir", "--split-string")
                                      or words[i].startswith(("--chdir=", "--split-string="))):
                    eff.doubt("env runs its command in another way")
                i += 2 if words[i] in _WRAPPERS[name] else 1
            if name == "timeout" and i < n:
                i += 1  # the duration
        elif name == "uv" and i + 1 < n and words[i + 1] == "run":
            i += 2
            while i < n and words[i].startswith("-"):
                i += 2 if words[i] in _UV_VALUE_FLAGS else 1
        elif name in _RUNNERS and ("" in _RUNNERS[name] or (i + 1 < n and words[i + 1] in _RUNNERS[name])):
            eff.doubt(f"{name} runs a command another tool resolves")
            i += 1 if "" in _RUNNERS[name] else 2
            while i < n and words[i].startswith("-") and len(words[i]) > 1:
                if words[i] == "--":
                    i += 1
                    break
                i += 2 if words[i] in _RUNNER_VALUE_FLAGS else 1
        else:
            break
    return i


_PS_PATH_FLAGS = ("-path", "-filepath", "-literalpath", "-pspath")
_PS_VALUE_FLAGS = ("-value", "-encoding", "-filter", "-include", "-exclude", "-inputobject", "-width", "-stream",
                   "-credential", "-delimiter", "-itemtype", "-type", "-name")


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
        for sep in (":", "="):
            k, eq, v = w.partition(sep)
            if eq and k.lower() in flags and v:
                return v
    return None


def _sed_files(args: List[str], perl: bool = False) -> List[str]:
    script_given, i = False, 0
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


def _sed_scripts(args: List[str]) -> List[str]:
    """sed's scripts: the -e / --expression values, else the first positional word."""
    out = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-e", "--expression")]
    out += [a.split("=", 1)[1] for a in args if a.startswith("--expression=")]
    if not out:
        pos = [a for a in args if not a.startswith("-")]
        out = pos[:1]
    return out


# cp / mv / install / ln / rsync: the flags that take a value, per command.
_COPY_VALUE_FLAGS = {
    "cp": ("-t", "--target-directory", "-S", "--suffix"), "mv": ("-t", "--target-directory", "-S", "--suffix"),
    "ln": ("-t", "--target-directory", "-S", "--suffix"),
    "install": ("-t", "--target-directory", "-m", "--mode", "-o", "--owner", "-g", "--group", "-S", "--suffix"),
    "rsync": ("-e", "--rsh", "-f", "--filter", "--exclude", "--include", "-T", "--temp-dir", "--backup-dir",
              "--partial-dir", "--chmod", "--chown", "--files-from", "--exclude-from", "--include-from", "-B",
              "--block-size"),
    "copy": (), "move": (),
}


def _copy_writes(name: str, args: List[str], scope: _Scope, eff: ShellEffects) -> None:
    """The destination of cp / mv / install / rsync / ln (and cmd's copy / move): the last word, or -t DIR; a folder
    destination (several sources, a trailing slash, or an existing folder) writes <folder>/<source name> too. A
    recursive copy, rsync or a move writes into folders: <dest>/<source name>, and <dest> itself when the source ends
    in / or the destination does not exist yet."""
    vf = _COPY_VALUE_FLAGS[name]
    into = _flag_value(args, ("-t", "--target-directory")) if "-t" in vf else None
    pos = _positional(args, vf)
    if name in ("copy", "move"):
        pos = [p for p in pos if not re.fullmatch(r"/[A-Za-z-]+", p)]  # cmd's /y /b switches
    recursive = name in ("rsync", "mv", "move") or any(
        re.fullmatch(r"-[a-zA-Z]*[rRa][a-zA-Z]*", a) or a in ("--recursive", "--archive") for a in args)
    if into is not None:
        folder, sources = into, pos
        eff.write(folder, scope)
    elif name == "ln" and len(pos) == 1:
        folder, sources = ".", pos  # ln -s TARGET: a link named like the target, here
    elif len(pos) >= 2:
        dest, sources = pos[-1], pos[:-1]
        eff.write(dest, scope)
        full = eff._paths(dest, scope, False)
        exists = any(os.path.isdir(p) for p in full)
        if recursive and (not exists or any(s.endswith(("/", "\\", "/.")) for s in sources)):
            eff.write_folder(dest, scope)
        if not (len(pos) > 2 or dest.endswith(("/", "\\")) or exists):
            return
        folder = dest
    else:
        return
    if len(sources) > _MAX_GLOB:
        eff.doubt("more sources than the reader checks")
        return
    for s in sources:
        leaf = re.split(r"[/\\]", s.rstrip("/\\"))[-1]
        if leaf and leaf not in (".", ".."):
            target = folder.rstrip("/\\") + "/" + leaf
            eff.write(target, scope)
            if recursive:
                eff.write_folder(target, scope)


_REMOVERS = ("rm", "rmdir", "unlink", "del", "erase", "rd", "remove-item", "ri")
_PS_REMOVERS = ("remove-item", "ri", "del", "erase", "rd")
_MOVERS = ("mv", "move", "move-item", "mi")
_PS_WRITERS = ("set-content", "add-content", "out-file", "clear-content", "sc", "ac", "tee-object", "new-item", "ni")


def _removals(name: str, args: List[str]) -> List[str]:
    """What rm, rmdir, unlink, del / erase / rd (cmd), Remove-Item (ri, del), git rm, and the sources of mv / move,
    Move-Item (mi) and git mv remove or move away."""
    if name == "git" and args and args[0] in ("rm", "mv"):
        name, args = args[0], args[1:]
    if name in ("del", "erase", "rd", "move"):  # cmd's /q /s /f switches
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


_SHELLS = ("sh", "bash", "zsh", "dash", "ksh", "fish", "pwsh", "powershell")
_PS_SHELLS = ("pwsh", "powershell")


def _shell_script(name: str, args: List[str]) -> Tuple[Optional[str], List[str], Optional[str]]:
    """A shell's words read: the script it runs from its command line (`bash -c "…"`, `sh -ec '…'`, `pwsh -c …`,
    `powershell -Command …`), the words after it ($0, $1 …), and the script file it runs (None: it reads stdin)."""
    j = 0
    while j < len(args):
        flag = args[j].lower()
        if name in _PS_SHELLS:
            if flag.startswith("-") and len(flag) >= 2 and "-command".startswith(flag):
                rest = args[j + 1:]
                return (" ".join(rest) if rest else None), [], None
            if flag.startswith("-") and len(flag) >= 3 and "-file".startswith(flag):
                return None, [], args[j + 1] if j + 1 < len(args) else None
            if not flag.startswith("-"):
                return None, [], args[j]
            j += 2 if flag in ("-executionpolicy", "-ep", "-workingdirectory", "-wd", "-outputformat", "-inputformat",
                               "-configurationname", "-settingsfile", "-version", "-psconsolefile") else 1
            continue
        if re.match(r"^-[a-z]*c[a-z]*$", flag):
            return (args[j + 1] if j + 1 < len(args) else None), args[j + 2:], None
        if flag in ("-o", "+o", "--rcfile", "--init-file"):
            j += 2
            continue
        if flag == "-s":
            return None, [], None
        if not flag.startswith(("-", "+")):
            return None, [], None if flag in ("/dev/stdin", "/dev/fd/0") else args[j]
        j += 1
    return None, [], None


_PY_NAME = re.compile(r"python[\d.]*|py|pypy[\d.]*")
_NODE_NAMES = ("node", "nodejs", "bun", "deno", "tsx", "ts-node", "esno", "vite-node")
_STDIN_FILES = ("-", "/dev/stdin", "/dev/fd/0")


def _python_code(args: List[str]) -> Tuple[List[str], List[str], str, Optional[str]]:
    """What python runs from its command line: the code (-c CODE), the code's arguments, where the code comes from
    ("code", "stdin" for `-` / /dev/stdin / no script, "script", "module"), and the script file or module name."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in _STDIN_FILES:
            return [], args[i + 1:], "stdin", None
        if a.startswith("--"):
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            flags, skip = a[1:], 0
            for k, ch in enumerate(flags):
                if ch == "c":
                    if flags[k + 1:]:
                        return [flags[k + 1:]], args[i + 1:], "code", None
                    return args[i + 1:i + 2], args[i + 2:], "code", None
                if ch == "m":
                    module = flags[k + 1:] or (args[i + 1] if i + 1 < len(args) else "")
                    return [], [], "module", module
                if ch in "XW":
                    skip = 0 if flags[k + 1:] else 1
                    break
            i += 1 + skip
            continue
        return [], args[i + 1:], "script", a
    return [], [], "stdin", None


def _node_code(name: str, args: List[str]) -> Tuple[List[str], List[str], str, Optional[str]]:
    """What node / bun / deno / tsx runs from its command line (as _python_code)."""
    if name == "deno":
        if not args or args[0] != "eval":
            pos = _positional(args[1:], ())
            return [], [], "script", pos[0] if args[:1] == ["run"] and pos else None
        pos = _positional(args[1:], ("--ext", "--import-map", "--config", "-c", "--location"))
        return pos[:1], pos[1:], "code", None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-e", "--eval", "-p", "--print", "-pe"):
            return args[i + 1:i + 2], args[i + 2:], "code", None
        if a.startswith(("--eval=", "--print=")):
            return [a.split("=", 1)[1]], args[i + 1:], "code", None
        if a in _STDIN_FILES:
            return [], args[i + 1:], "stdin", None
        if a in ("-r", "--require", "--import", "--loader", "-C", "--conditions", "--env-file"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        if name == "bun" and a == "run" and i + 1 < len(args):
            return [], args[i + 2:], "script", args[i + 1]
        return [], args[i + 1:], "script", a
    return [], [], "stdin", None


# (b) Programs that only read what they are given (a guarded path among their words is a read), with the words that
# make them write or run something (then they are not).
_READ_ONLY: Dict[str, Tuple[str, ...]] = {
    "cat": (), "head": (), "tail": (), "more": (), "grep": (), "egrep": (), "fgrep": (), "rg": ("--pre",), "ag": (),
    "ack": (), "wc": (), "diff": ("--output",), "cmp": (), "comm": (), "ls": (), "stat": (), "file": ("-C",),
    "sha1sum": (), "sha224sum": (), "sha256sum": (), "sha384sum": (), "sha512sum": (), "shasum": (), "md5sum": (),
    "md5": (), "jq": (), "du": (), "df": (), "realpath": (), "readlink": (), "basename": (), "dirname": (),
    "test": (), "[": (), "[[": (), "printenv": (), "pwd": (), "which": (), "type": (), "true": (), "false": (),
    ":": (), "tr": (), "cut": (), "od": (), "nl": (), "get-content": (), "gc": (), "select-string": (), "sls": (),
    "test-path": (), "get-childitem": (), "gci": (), "dir": (), "get-item": (), "resolve-path": (), "join-path": (),
    "split-path": (), "convertfrom-json": (), "select-object": (), "where-object": (), "measure-object": (),
    "format-table": (), "format-list": (), "out-string": (), "out-null": (), "write-host": (),
}
# Builtins with nothing to read (their words go to the earlier reader's text check like any other).
_NEUTRAL = frozenset(("set", "unset", "exit", "return", "sleep", "wait", "shift", "trap", "umask", "ulimit"))
# git words that make it run a command or a filter.
_GIT_RUNS = frozenset(("--exec", "-x", "--tree-filter", "--index-filter", "--msg-filter", "--env-filter",
                       "--commit-filter", "--parent-filter", "--tag-name-filter", "filter-branch", "bisect", "foreach",
                       "-c", "--config-env", "difftool", "mergetool", "--upload-pack", "--receive-pack"))


def _cd(words: List[str], scope: _Scope, eff: ShellEffects) -> bool:
    """Move scope for cd / pushd / popd / Set-Location; False for any other command. A folder the reader cannot resolve
    keeps the current folders and adds the project's, and makes it unsure."""
    name = _command_name(words[0]) if words else ""
    if name == "popd":
        scope.bases = scope.dirs.pop() if scope.dirs else scope.bases
        return True
    if name not in ("cd", "pushd", "chdir", "set-location", "sl"):
        return False
    pos = [w for w in _positional(words[1:], ("-path", "-literalpath")) if w.lower() != "/d"]
    target = _flag_value(words[1:], ("-path", "-literalpath")) or (pos[0] if pos else "~")
    if name == "pushd":
        scope.dirs.append(scope.bases)
    if target == "-":
        eff.doubt("cd - goes back to a folder the reader does not track")
        return True
    expanded = scope.expand(target)
    if ("$" in expanded or "`" in expanded) and not (_HERE_PREFIX.match(expanded) or _ROOT_PREFIX.match(expanded)) \
            and not _HOME_VAR.match(expanded):
        eff.doubt("a cd into a folder the reader cannot resolve")
        scope.bases = tuple(dict.fromkeys(scope.bases + ((eff.root,) if eff.root else ())))
        return True
    folders = eff._paths(target, scope, True)
    if folders:
        scope.bases = tuple(dict.fromkeys(folders))
    return True


def _literal_output(script: str) -> Optional[str]:
    """What a script prints, when it is one echo / printf of literal words or one cat of a here-document
    (`<(echo '…')`, `$(printf '…')`, `$(cat <<'EOF' … EOF)`)."""
    events = _commands(_lex(script))
    if len(events) != 1 or events[0][0] != "cmd":
        return None
    cmd = events[0][1]
    if cmd.redirs or cmd.subs or cmd.inputs or not cmd.words:
        return None
    if cmd.words == ["cat"] and cmd.stdin:
        return "\n".join(cmd.stdin)
    if _command_name(cmd.words[0]) not in ("echo", "printf"):
        return None
    words = cmd.words[1:]
    if words and words[0] == "-n":
        words = words[1:]
    return " ".join(words).replace("\\n", "\n")


def _run_file(word: str, kind: str, argv: List[str], scope: _Scope, eff: ShellEffects, depth: int) -> None:
    """A command runs a file (a script, a module, a makefile, a shell's stdin). When the same command wrote that file,
    its text is read as what it runs; a file it wrote but whose text the reader doesn't know makes it unsure."""
    for path in eff._paths(word, scope, False):
        if path not in scope.written:
            continue
        text = scope.written[path]
        if text is None:
            eff.doubt("runs a file the command wrote, whose text the reader does not know")
            continue
        first = text.split("\n", 1)[0]
        if kind == "sh" and first.startswith("#!") and ("python" in first or "node" in first):
            kind = "py" if "python" in first else "js"
        if depth >= _MAX_DEPTH:
            eff.doubt("commands nested deeper than the reader follows")
        elif kind in ("py", "js"):
            _code(text, kind, argv, scope, eff, depth + 1)
        elif kind == "make":
            _script("\n".join(ln[1:] for ln in text.split("\n") if ln.startswith("\t")), scope.copy(), eff, depth + 1)
        else:
            _script(text, scope.copy(), eff, depth + 1)


def _data_write(cmd: _Simple, text: str, targets: List[str], scope: _Scope, eff: ShellEffects) -> None:
    """(a) A here-document, here-string or echo / printf text written to files: the text is data, and the files are
    remembered (written) so that a command that runs one reads it as code."""
    for t in targets:
        eff.write(t, scope, None if t in cmd.appends else text)
        eff.data_files.append((t, scope.expand(t)))


def _simple(cmd: _Simple, scope: _Scope, eff: ShellEffects, depth: int, before: Optional[_Simple],
            after: Optional[_Simple]) -> None:
    """The writes and removals of one simple command; and whether its words are in a provable position (b, a, c),
    else they go to eff.other."""
    eff.tick()
    for target in cmd.redirs:
        eff.write(target, scope)
    start = _command_start(cmd.words, eff)
    prefix, words = cmd.words[:start], cmd.words[start:]
    eff.note(scope, *prefix)  # FOO=… and wrapper words before the command are never a provable position
    if not words:
        return
    name, args = _command_name(words[0]), words[1:]
    stdin = list(cmd.stdin)
    piped_unknown = False
    piped_data: Optional[str] = None
    if not stdin and cmd.piped and before is not None:  # echo "code" | python3: the code is the echo's words
        prev = before.words[_command_start(before.words, eff):]
        if prev and _command_name(prev[0]) in ("echo", "printf"):
            piped_data = " ".join(prev[1:]).replace("\\n", "\n")
            stdin = [piped_data]
        elif prev and _command_name(prev[0]) == "cat" and len(prev) == 1 and before.stdin:
            stdin = list(before.stdin)
            piped_data = "\n".join(stdin)
        else:
            piped_unknown = True
    after_words = after.words[_command_start(after.words, eff):] if after is not None else []
    into_tee = bool(after_words) and _command_name(after_words[0]) in ("tee", "tee-object")
    provable = False
    for item in _removals(name, args):
        eff.remove(item, scope)
    if name in _READ_ONLY and not (name == "cat" and stdin and not _positional(args, ())):
        provable = not any(a.startswith(_READ_ONLY[name]) for a in args if _READ_ONLY[name])
    elif name in ("echo", "printf", "write-output", "cat"):  # (a) cat <<EOF > F, echo … > F, echo … | tee F
        text = "\n".join(stdin) if name == "cat" else " ".join(args).replace("\\n", "\n")
        if name == "printf" and len(args) > 1 and "%" in args[0]:
            text = None  # a format: the file's text is not the words
        provable = bool(cmd.redirs) or into_tee
        _data_write(cmd, text, list(cmd.redirs), scope, eff)
    elif name in ("tee", "tee-object"):
        targets = _positional(args, ("--output-error", "-filepath", "-literalpath", "-variable"))
        value = _flag_value(args, ("-filepath", "-literalpath"))
        targets = [value] if value else targets
        text = "\n".join(stdin) if stdin else piped_data
        _data_write(cmd, text, targets, scope, eff)
        provable = bool(stdin) or (cmd.piped and before is not None and (piped_data is not None or _command_name(
            (before.words[_command_start(before.words, eff):] or [""])[0]) in _READ_ONLY))
    elif name in ("sed", "gsed"):
        if any(re.match(r"^-[a-zA-Z0-9]*i", a) or a.startswith("--in-place") for a in args):
            for f in _sed_files(args):
                eff.write(f, scope)
        for script in _sed_scripts(args):  # w FILE, s/…/…/w FILE, e (runs a command)
            for m in re.finditer(r"(?:^|[;\n}]|/[gpIiMme0-9]*)\s*[wW]\s+([^;\n}]+)", script):
                eff.write(m.group(1).strip(), scope)
            if re.search(r"(?:^|[;\n])\s*e\b|/e\b", script):
                eff.doubt("sed runs a command")
    elif name == "perl":
        eff.doubt("perl code is not read")
        if any(re.match(r"^-[a-zA-Z0-9]*i", a) for a in args):  # -pi, -0pi, -0777 -pi, -i.bak
            for f in _sed_files(args, perl=True):
                eff.write(f, scope)
    elif name == "sort":
        out = _flag_value(args, ("-o", "--output"))
        if out:
            eff.write(out, scope)
    elif name == "uniq":
        pos = _positional(args, ("-f", "-s", "-w", "--skip-fields", "--skip-chars", "--check-chars"))
        if len(pos) > 1:
            eff.write(pos[1], scope)
    elif name in _COPY_VALUE_FLAGS:
        _copy_writes(name, args, scope, eff)
    elif name == "git":
        if args[:1] == ["mv"]:
            _copy_writes("mv", args[1:], scope, eff)
        if any(a in _GIT_RUNS or a.startswith(("--exec=", "-x=", "--exec-path", "--config-env=")) for a in args):
            eff.doubt("git runs a command or a filter")
        message = _git_commit_message(args)
        if message is not None:  # (d) git commit -m / -F / -t / stdin: the message is data
            if any(_HOOK_FILE.search(p.replace("\\", "/")) for p in scope.written) or \
                    any("hookspath" in a.lower() for a in args):
                eff.doubt("git commit runs a hook the command wrote")
            if any(_ASSIGNMENT.match(w) and not _GIT_SAFE_ENV.match(w) for w in prefix):
                eff.doubt("git commit with variables set before it (an editor, a config, a hooks folder)")
            eff.note(scope, *message)
            provable = True
    elif name == "truncate":
        for f in _positional(args, ("-s", "--size", "-r", "--reference")):
            eff.write(f, scope)
    elif name == "dd":
        for a in args:
            if a.startswith("of="):
                eff.write(a[3:], scope)
    elif name == "curl":
        folder = _flag_value(args, ("--output-dir",))
        for k, a in enumerate(args):
            if (a == "--output" or re.fullmatch(r"-[a-zA-Z]*o", a)) and k + 1 < len(args):
                eff.write(os.path.join(folder, args[k + 1]) if folder else args[k + 1], scope)
            elif a.startswith("--output="):
                eff.write(a.split("=", 1)[1], scope)
        if folder:
            eff.write_folder(folder, scope)
            for a in args:
                if re.match(r"^[a-z]+://", a):
                    leaf = a.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
                    if leaf:
                        eff.write(os.path.join(folder, leaf), scope)
    elif name == "wget":
        for k, a in enumerate(args):
            if (a == "--output-document" or re.fullmatch(r"-[a-zA-Z]*O", a)) and k + 1 < len(args):
                eff.write(args[k + 1], scope)
            elif a.startswith("--output-document="):
                eff.write(a.split("=", 1)[1], scope)
            elif re.fullmatch(r"-O.+", a):
                eff.write(a[2:], scope)
    elif name in _PS_WRITERS:
        value = _flag_value(args, _PS_PATH_FLAGS)
        pos = _positional(args, _PS_VALUE_FLAGS + _PS_PATH_FLAGS)
        for item in ([value] if value else pos[:1]):
            for x in item.split(","):
                eff.write(x.strip(), scope)
    elif name in ("copy-item", "move-item", "cpi", "mi"):
        value = _flag_value(args, ("-destination",))
        pos = _positional(args, _PS_VALUE_FLAGS + _PS_PATH_FLAGS + ("-destination",))
        for item in ([value] if value else pos[1:2]):
            eff.write(item, scope)
            if name in ("move-item", "mi") or any(a.lower() == "-recurse" for a in args):
                eff.write_folder(item, scope)
    elif name in _SHELLS:
        eff.doubt("a shell runs commands")
        script, params, file_word = _shell_script(name, args)
        if script is not None:
            inner = scope.copy()
            for k, v in enumerate(params):  # sh -c '… "$1" …' _ FILE: $0, $1 … are the words after the script
                inner.vars[str(k)] = v
            inner.vars["@"] = inner.vars["*"] = " ".join(params[1:])
            _script(script, inner, eff, depth + 1)
        elif file_word is not None:
            _source(file_word, cmd, scope, eff, depth)
        else:
            if piped_unknown:
                eff.doubt("a shell reads commands from another command")
            for body in stdin:
                _script(body, scope.copy(), eff, depth + 1)
            for word in cmd.inputs:  # bash < FILE
                _run_file(word, "sh", [], scope, eff, depth)
    elif name in ("source", "."):
        eff.doubt("source runs a script")
        if args:
            _source(args[0], cmd, scope, eff, depth)
    elif name == "eval":
        eff.doubt("eval runs a command")
        parts = []
        for word in args:
            m = re.fullmatch(r"\$\((.*)\)|`(.*)`", word, re.S)
            out = _literal_output(m.group(1) or m.group(2)) if m else word
            if out is None:
                eff.doubt("eval runs the output of a command")
                out = ""
            parts.append(out)
        _script(" ".join(parts), scope.copy(), eff, depth + 1)
    elif name in ("script", "su", "runuser", "watch"):
        eff.doubt(f"{name} runs a command")
        if name == "watch":
            rest = _positional(args, ("-n", "--interval", "-d", "--differences"))
            _script(" ".join(rest), scope.copy(), eff, depth + 1)
        else:
            run = _flag_value(args, ("-c", "--command"))
            if run:
                _script(run, scope.copy(), eff, depth + 1)
    elif name == "find":
        eff.doubt("find is not read")
        _find_exec(args, scope, eff, depth)
    elif name in ("make", "gmake"):
        eff.doubt("make runs recipes")
        mk = _flag_value(args, ("-f", "--file", "--makefile"))
        if mk:
            _run_file(mk, "make", [], scope, eff, depth)
    elif _PY_NAME.fullmatch(name) or name in _NODE_NAMES:
        lang = "py" if _PY_NAME.fullmatch(name) else "js"
        code, argv, kind, file_word = _python_code(args) if lang == "py" else _node_code(name, args)
        if kind == "stdin":
            code = stdin
            if piped_unknown:
                eff.doubt("code piped from another command")
            for word in cmd.inputs:  # python3 - < FILE
                eff.doubt("code read from a file")
                _run_file(word, lang, argv, scope, eff, depth)
        elif kind in ("script", "module"):
            eff.doubt("a script runs")
            if file_word:
                path = file_word.replace(".", "/") + ".py" if kind == "module" else file_word
                _run_file(path, lang, argv, scope, eff, depth)
        for text in code:
            _code(text, lang, argv, scope, eff, depth)
        provable = kind in ("code", "stdin")
        if provable:
            eff.note(scope, *argv)
    elif "/" in words[0] or "\\" in words[0]:  # ./fix.sh: a script file run directly
        eff.doubt("a script runs")
        _run_file(words[0], "sh", args, scope, eff, depth)
    elif name in _NEUTRAL:
        provable = True
    if not provable:
        eff.note(scope, *words, *cmd.stdin)


def _source(word: str, cmd: _Simple, scope: _Scope, eff: ShellEffects, depth: int) -> None:
    """A shell, source or . runs this script word: a file (the command may have written it), or <(echo …)."""
    m = re.fullmatch(r"<\((.*)\)", word, re.S)
    if m:
        out = _literal_output(m.group(1))
        if out is None:
            eff.doubt("runs the output of a command")
        else:
            _script(out, scope.copy(), eff, depth + 1)
        return
    _run_file(word, "sh", [], scope, eff, depth)


_GIT_GLOBAL_VALUE = ("-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix")
_GIT_MESSAGE = ("-m", "--message", "-F", "--file", "-t", "--template")
_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
_GIT_SAFE_ENV = re.compile(r"^(?:GIT_(?:AUTHOR|COMMITTER)_(?:NAME|EMAIL|DATE)|LC_\w+|LANG|LANGUAGE|TZ)=")
# Files git runs as hooks: anything under .git/ or .husky/, a folder named like a hooks folder (a core.hooksPath), and
# a file named as a git hook wherever it is.
_HOOK_FILE = re.compile(r"(?:^|/)(?:\.git|\.husky)(?:/|$)|(?:^|/)[^/]*hooks?(?:/|$)|(?:^|/)(?:applypatch-msg|"
                        r"pre-applypatch|post-applypatch|pre-commit|pre-merge-commit|prepare-commit-msg|commit-msg|"
                        r"post-commit|pre-rebase|post-checkout|post-merge|pre-push|pre-receive|update|post-receive|"
                        r"post-update|push-to-checkout|pre-auto-gc|post-rewrite|sendemail-validate|fsmonitor-watchman|"
                        r"reference-transaction|post-index-change|p4-\w+)(?:\.\w+)?$", re.I)


def _git_commit_message(args: List[str]) -> Optional[List[str]]:
    """(d) For `git [global options] commit …`: its words other than the message (the values of -m / --message / -F /
    --file / -t / --template, also inside a short-option cluster like -am), which stay other text; None for any other
    git command, or a global option that runs something (-c, --config-env, --exec-path)."""
    i, out = 0, []
    while i < len(args) and args[i].startswith("-"):
        if args[i].startswith(("-c", "--exec-path", "--config-env")):
            return None
        step = 2 if args[i] in _GIT_GLOBAL_VALUE else 1
        out += args[i:i + (1 if args[i] == "-C" else step)]  # -C DIR: where git runs (commit writes only in .git)
        i += step
    if i >= len(args) or args[i] != "commit":
        return None
    out.append("commit")
    rest, k = args[i + 1:], 0
    longs = tuple(f + "=" for f in _GIT_MESSAGE if f.startswith("--"))
    while k < len(rest):
        a = rest[k]
        k += 1
        if a == "--":
            out += rest[k:]
            break
        if a in _GIT_MESSAGE:
            k += 1  # the value is the message (or the file it is read from)
            continue
        if a.startswith(longs):
            continue
        m = re.match(r"-([A-Za-z]*?)([mFtcC])", a)
        if m and not a.startswith("--"):
            flags, value = m.group(1), a[m.end():]
            if m.group(2) in "mFt":  # -am MSG, -mMSG, -m'MSG': the rest of the word or the next word is the message
                if not value:
                    k += 1
                out.append("-" + flags)
                continue
            if not value and k < len(rest):  # -c / -C COMMIT: a value, still checked
                out.append(rest[k])
                k += 1
        out.append(a)
    return out


def _find_exec(args: List[str], scope: _Scope, eff: ShellEffects, depth: int) -> None:
    """find … -exec CMD … ; (or +, -execdir, -ok): CMD is read as a command; {} is each file found (unknown here), so
    the reader is unsure; so it is for -delete and -fprint."""
    k = 0
    while k < len(args):
        if args[k] in ("-delete", "-fprint", "-fprint0", "-fprintf", "-fls"):
            eff.doubt(f"find {args[k]} writes or removes files the reader cannot list")
        if args[k] in ("-exec", "-execdir", "-ok", "-okdir"):
            eff.doubt("find runs a command on files the reader cannot list")
            end = next((j for j in range(k + 1, len(args)) if args[j] in (";", "+")), len(args))
            inner = _Simple()
            inner.words = args[k + 1:end]
            inner.quoted = [False] * len(inner.words)
            if depth < _MAX_DEPTH:
                _simple(inner, scope, eff, depth + 1, None, None)
            k = end
        k += 1


def _assign(words: List[str], scope: _Scope, eff: ShellEffects) -> bool:
    """Record NAME=value words (alone, or after export / declare / local / readonly; PowerShell's $name = value) in
    scope. True when the command is only that. The values go to eff.other."""
    rest = words[1:] if words and words[0] in ("export", "declare", "local", "readonly", "typeset") else words
    if len(words) == 3 and words[0].startswith("$") and words[1] == "=" and re.fullmatch(r"\$[A-Za-z_]\w*", words[0]):
        scope.vars[words[0][1:]] = words[2]
        eff.note(scope, words[2])
        return True
    pairs = [re.match(r"^([A-Za-z_]\w*)=(.*)$", w, re.S) for w in rest]
    if not rest or not all(pairs):
        return False
    for m in pairs:
        scope.vars[m.group(1)] = scope.expand(m.group(2))
        eff.note(scope, m.group(2))
    return True


_ANY = "\x00any"  # a read variable whose source the reader does not know


def _bind_loop(words: List[str], cmd: _Simple, before: Optional[_Simple], scope: _Scope, eff: ShellEffects) -> None:
    """`for VAR in WORDS`: VAR may take each word (a glob expanded in the folder, the paths named inside a $( ) such as
    $(ls docs/*.html)); `PRODUCER | while read VAR`: the producer's words; a read with any other source: unknown (its
    target is then checked against the whole command)."""
    if len(words) >= 2 and words[0] == "for" and re.fullmatch(r"[A-Za-z_]\w*", words[1]):
        values = words[3:] if words[2:3] == ["in"] else []
        scope.loops[words[1]] = _loop_words(values, scope)
    elif words and _command_name(words[0]) == "read":
        names = [w for w in words[1:] if re.fullmatch(r"[A-Za-z_]\w*", w)]
        if cmd.piped and before is not None:
            source = _loop_words(before.words[_command_start(before.words, eff) + 1:] + list(before.stdin), scope)
        else:
            source = [_ANY]
        for name in names:
            scope.loops[name] = source


def _loop_words(values: List[str], scope: _Scope) -> List[str]:
    out: List[str] = []
    for v in values:
        inner = re.findall(r"\$\((.*?)\)|`(.*?)`", v, re.S)
        parts = [x for pair in inner for x in pair if x] or [v]
        for part in parts:
            for word in part.split() if part is not v else [v]:
                if word.startswith("-"):
                    continue
                out.append(word)
                if re.search(r"[*?\[]", word):
                    for base in scope.bases:
                        full = word if os.path.isabs(word) else os.path.join(base, word)
                        out += glob.glob(full)[:_MAX_GLOB]
        if len(out) > _MAX_TARGETS:
            break
    return out[:_MAX_TARGETS]


def _script(text: str, scope: _Scope, eff: ShellEffects, depth: int = 0) -> None:
    """Read a shell script's commands for their writes and removals. `cd DIR` moves the folder for the commands after
    it (not past the end of a subshell); a command substitution runs in the folder of its command."""
    if not text.strip():
        return
    if depth > _MAX_DEPTH:
        eff.doubt("commands nested deeper than the reader follows")
        return
    if "]::" in text:  # PowerShell's .NET calls: [IO.File]::WriteAllText('…', …)
        eff.doubt("PowerShell .NET calls are not proved")
        _code(text, "ps", [], scope, eff, depth)
    scopes = [scope]
    events = _commands(_lex(text))
    before: Optional[_Simple] = None
    for index, event in enumerate(events):
        eff.tick()
        if event[0] == "push":
            scopes.append(scopes[-1].copy())
            before = None
            continue
        if event[0] == "pop":
            if len(scopes) > 1:
                scopes.pop()
            before = None
            continue
        cmd = event[1]
        here = scopes[-1]
        nxt = events[index + 1] if index + 1 < len(events) else None
        after = nxt[1] if cmd.pipe_out and nxt is not None and nxt[0] == "cmd" else None
        for sub in cmd.subs:  # a substitution that only prints literal text writes nothing: its text is a word
            if _literal_output(sub) is None:
                _script(sub, here.copy(), eff, depth + 1)
        words = cmd.words[_command_start(cmd.words, eff):]
        _bind_loop(words, cmd, before, here, eff)
        if not cmd.redirs and _assign(cmd.words, here, eff):
            pass
        elif not _cd(words, here, eff):
            _simple(cmd, here, eff, depth, before, after)
        elif cmd.redirs:
            for target in cmd.redirs:
                eff.write(target, here)
        before = cmd


# ---------------------------------------------------------------- inline code (python -c, node -e, PowerShell .NET)


_LIT = re.compile(r"\x01(\d+)\x02")
_CALL = re.compile(r"([A-Za-z_$][\w$]*)\s*\(")
_PATH_CALL = re.compile(r"^(?:pathlib\s*\.\s*)?(?:Pure)?(?:Posix|Windows)?Path\s*\(\s*\x01(\d+)\x02\s*\)$")
_PATHLIKE = re.compile(r"(?:Pure)?(?:Posix|Windows)?Path")
_MODE = re.compile(r"^[rwaxbtU+]{1,4}$")
_FS_MODULES = ("os", "shutil", "fs", "fsp", "Deno", "Bun", "promises")
# (c) Read sinks: a guarded literal given straight to one of these is only read (its argument position).
_READ_SINKS = {
    "readfilesync": 0, "readfile": 0, "existssync": 0, "statsync": 0, "readtextfile": 0, "readtextfilesync": 0,
    "require": 0, "spec_from_file_location": 1, "sourcefileloader": 1, "readalltext": 0, "readalllines": 0,
    "readallbytes": 0,
}
_PATH_READS = ("read_text", "read_bytes", "exists", "is_file", "is_dir", "stat")
# Calls that run commands or code: the reader is unsure (it reads a literal command or code given to them).
_RUNS_CODE = frozenset((
    "system", "popen", "execsync", "execfilesync", "execfile", "spawnsync", "spawn", "exec", "eval", "getoutput",
    "getstatusoutput", "startfile", "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp", "execlpe",
    "spawnv", "spawnve", "spawnvp", "spawnl", "spawnlp", "run", "call", "check_call", "check_output", "fork",
    "run_path", "run_module",
))
_LISTING = re.compile(r"\b(?:listdir|iterdir|scandir|glob|rglob|iglob|walk|readdirSync|readdir)\s*\(")
_NOT_NAMES = frozenset((
    "True", "False", "None", "and", "or", "not", "in", "is", "if", "else", "for", "while", "lambda", "return", "with",
    "as", "import", "from", "def", "class", "await", "async", "new", "const", "let", "var", "function", "of", "typeof",
    "this", "self", "null", "undefined", "true", "false", "os", "sys", "pathlib", "Path", "json", "shutil", "re",
    "io", "codecs", "fs", "fsp", "require", "process", "Deno", "Bun", "console", "Math", "JSON", "Object", "Array",
    "String", "str", "int", "len",
))


def _mask(code: str, lang: str) -> Tuple[str, List[Tuple[str, bool]]]:
    """The code with comments removed and each string literal replaced by \\x01N\\x02, and the literals (value, exact:
    not an f-string or template with a placeholder in it). The code's own \\x01 / \\x02 are blanked first."""
    code = code.replace("\x01", " ").replace("\x02", " ")
    out: List[str] = []
    lits: List[Tuple[str, bool]] = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if (c == "#" and lang in ("py", "ps")) or (lang == "js" and code.startswith("//", i)):
            end = code.find("\n", i)
            i = n if end < 0 else end
            continue
        if lang == "js" and code.startswith("/*", i):
            end = code.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if c in "'\"" or (c == "`" and lang == "js"):
            prefix = ""
            if lang == "py":
                j = i
                while j > 0 and i - j < 2 and code[j - 1] in "rRbBuUfF":
                    j -= 1
                if j == i or j == 0 or not (code[j - 1].isalnum() or code[j - 1] == "_"):
                    prefix = code[j:i]
                    del out[len(out) - len(prefix):]
            triple = lang == "py" and code.startswith(c * 3, i)
            q = c * 3 if triple else c
            raw = "r" in prefix.lower()
            j, buf = i + len(q), []
            while j < n and not code.startswith(q, j):
                ch = code[j]
                if lang == "ps" and c == "'" and code.startswith("''", j):
                    buf.append("'")
                    j += 2
                    continue
                if ch == "\\" and lang != "ps" and j + 1 < n:
                    nxt = code[j + 1]
                    if raw:
                        buf.append(ch + nxt)
                    else:
                        buf.append({"n": "\n", "t": "\t"}.get(nxt, nxt if nxt in "\\'\"`" else ch + nxt))
                    j += 2
                    continue
                buf.append(ch)
                j += 1
            value = "".join(buf)
            exact = not (("f" in prefix.lower() and "{" in value) or (c == "`" and "${" in value)
                         or (lang == "ps" and c == '"' and "$" in value))
            out.append(f"\x01{len(lits)}\x02")
            lits.append((value, exact))
            i = j + len(q)
            continue
        out.append(c)
        i += 1
    return "".join(out), lits


def _brackets(s: str) -> Tuple[Dict[int, int], Dict[int, int]]:
    """Matching brackets of masked code: open index → close index, and back."""
    o2c: Dict[int, int] = {}
    c2o: Dict[int, int] = {}
    stack: List[int] = []
    for i, c in enumerate(s):
        if c in "([{":
            stack.append(i)
        elif c in ")]}" and stack:
            j = stack.pop()
            o2c[j] = i
            c2o[i] = j
    return o2c, c2o


def _skip_space_back(s: str, i: int) -> int:
    while i > 0 and s[i - 1] in " \t\r\n":
        i -= 1
    return i


def _is_method(s: str, name_start: int) -> bool:
    """The name at s[name_start] is called as a method: `.name(` or `::name(`."""
    j = _skip_space_back(s, name_start)
    return j > 0 and (s[j - 1] == "." or s[j - 2:j] == "::")


def _receiver(s: str, end: int, c2o: Dict[int, int]) -> str:
    """The expression a method is called on: s[:end] ends with `.` or `::` before the method name."""
    j = end
    while j > 0 and s[j - 1] in ".: \t":
        j -= 1
    k = j
    while k > 0:
        c = s[k - 1]
        if c in ")]":
            back = c2o.get(k - 1, -1)
            if back < 0:
                break
            k = back
        elif c.isalnum() or c in "_$.\x01\x02" or (c == ":" and k > 1 and s[k - 2] == ":"):
            k -= 1
        else:
            break
    return re.sub(r"\s+", "", s[k:j])


def _call_args(s: str, open_idx: int, o2c: Dict[int, int]) -> List[str]:
    """The top-level arguments of the call whose ( is at s[open_idx]."""
    end = o2c.get(open_idx, len(s))
    args, depth, cur = [], 0, []
    for c in s[open_idx + 1:end]:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            args.append("".join(cur))
            cur = []
            continue
        cur.append(c)
    if "".join(cur).strip():
        args.append("".join(cur))
    return [a.strip() for a in args]


def _positional_args(args: List[str]) -> List[str]:
    return [a for a in args if not re.match(r"^\*{0,2}[A-Za-z_]\w*\s*=(?!=)", a)]


def _keyword(args: List[str], names: Tuple[str, ...]) -> Optional[str]:
    for a in args:
        m = re.match(r"^([A-Za-z_]\w*)\s*=(?!=)\s*(.*)$", a, re.S)
        if m and m.group(1) in names:
            return m.group(2)
    return None


class _Call:
    __slots__ = ("name", "recv", "method", "open", "args", "pos")

    def __init__(self, name: str, recv: str, method: bool, open_idx: int, args: List[str]) -> None:
        self.name, self.recv, self.method, self.open, self.args = name, recv, method, open_idx, args
        self.pos = _positional_args(args)


_TOKEN = re.compile(r"\s*(\x01\d+\x02|[A-Za-z_$][\w$]*|\d+|[()\[\],.+/%*]|\S)")
_JOINS = ("join", "joinpath", "resolve", "path", "purepath", "posixpath", "windowspath", "pureposixpath")
_SAME = ("abspath", "realpath", "normpath", "expanduser", "str", "fspath", "string", "absolute", "as_posix",
         "expanduser", "normalize")


class _Values:
    """The strings an expression of inline code can be (at most 16), folded from its literals, the names given a
    value in the code (assignments, for loops over a list), os.path.join / path.join / Path / `/`, +, f-strings, %,
    .format, `${}`, dirname / basename / splitext and the like. None: not known. Folders the code lists and then
    writes into (for f in os.listdir(D)) are collected."""

    def __init__(self, code: "_Code") -> None:
        self.c = code
        self.folders: List[str] = []
        self.seen: set = set()

    def of(self, expr: str, depth: int = 0) -> Optional[List[str]]:
        self.toks = [t for t in _TOKEN.findall(expr)]
        self.k = 0
        self.depth = depth
        try:
            out = self.expr()
        except (IndexError, ValueError):
            return None
        return out if self.k == len(self.toks) else None

    def peek(self) -> str:
        return self.toks[self.k] if self.k < len(self.toks) else ""

    def take(self) -> str:
        t = self.toks[self.k]
        self.k += 1
        return t

    def expr(self) -> Optional[List[str]]:
        left = self.term()
        while self.peek() in ("+", "/", "%"):
            op = self.take()
            right = self.term()
            if left is None or right is None:
                left = None
                continue
            if op == "%":
                left = [re.sub(r"%[sdr]", lambda _m, v=r: v, a, count=1) for a in left for r in right][:16]
            elif op == "/":
                left = [a.rstrip("/") + "/" + b.lstrip("/") for a in left for b in right][:16]
            else:
                left = [a + b for a in left for b in right][:16]
        return left

    def term(self) -> Optional[List[str]]:
        t = self.take()
        name = ""
        if _LIT.fullmatch(t):
            value, exact = self.c.lits[int(t[1:-1])]
            val = [value] if exact else self.template(value)
        elif t == "(":
            val = self.expr()
            while self.peek() == ",":  # a tuple: (a, b) — only its first part is a path
                self.take()
                self.expr()
            if self.take() != ")":
                raise ValueError
        elif t == "[":
            items: List[str] = []
            known = True
            while self.peek() not in ("]", ""):
                v = self.expr()
                if v is None:
                    known = False
                else:
                    items += v
                if self.peek() == ",":
                    self.take()
            self.take()
            val = items[:16] if known else None
        elif re.fullmatch(r"[A-Za-z_$][\w$]*", t):
            name = t
            val = None
        else:
            return None
        chain = name
        while self.peek() in (".", "(", "["):
            op = self.take()
            if op == ".":
                attr = self.take()
                if chain:
                    chain += "." + attr
                    continue
                low = attr.lower()
                if self.peek() == "(":
                    self.take()
                    args = self.call_args()
                    val = self.method(val, low, args)
                else:
                    val = self.attribute(val, low)
            elif op == "(":
                args = self.call_args()
                val = self.call(chain, args) if chain else None
                chain = ""
            else:
                index = self.expr()
                self.take()
                if chain in ("sys.argv", "process.argv", "Deno.args"):
                    val = list(self.c.argv)
                    chain = ""
                elif chain:
                    val = self.name(chain)
                    chain = ""
                    val = None if val is None else val
                else:
                    val = val[:1] if val and index in (["0"], None) else None
        if chain:
            val = self.name(chain)
        return val

    def call_args(self) -> List[Optional[List[str]]]:
        args: List[Optional[List[str]]] = []
        while self.peek() not in (")", ""):
            if re.fullmatch(r"[A-Za-z_]\w*", self.peek()) and self.k + 1 < len(self.toks) and \
                    self.toks[self.k + 1] == "=":
                self.k += 2  # a keyword argument: its value only
            args.append(self.expr())
            if self.peek() == ",":
                self.take()
        self.take()
        return args

    def template(self, value: str) -> Optional[List[str]]:
        """An f-string / template: {name} and ${name} filled from the names' values."""
        parts = re.split(r"\$?\{([A-Za-z_$][\w$.]*)(?:![rsa])?(?::[^}]*)?\}", value)
        out = [""]
        for i, part in enumerate(parts):
            if i % 2 == 0:
                out = [o + part for o in out]
                continue
            vals = self.name(part)
            if vals is None:
                return None
            out = [o + v for o in out for v in vals][:16]
        return out

    def module(self, head: str) -> bool:
        """head (os, os.path, a name given require('path')) is a module, not a value."""
        first = head.split(".")[0]
        if first in _NOT_NAMES:
            return True
        srcs = self.c.sources(first)
        return bool(srcs) and all(re.match(r"\s*(?:await\s+)?(?:require|import)\(", t) for _k, t in srcs)

    def call(self, chain: str, args: List[Optional[List[str]]]) -> Optional[List[str]]:
        head, _, last = chain.rpartition(".")
        last = last.lower()
        if head and not self.module(head):  # here.joinpath(…): a method of a value
            return self.method(self.name(head), last, args)
        if any(a is None for a in args):
            return None
        if last in _JOINS:
            out = [""]
            for a in args:
                out = [(o.rstrip("/") + "/" + v if o else v) for o in out for v in a][:16]
            return out
        if last in _SAME and args:
            return args[0]
        if last == "dirname" and args:
            return [os.path.dirname(v.rstrip("/")) or "." for v in args[0]]
        if last == "basename" and args:
            return [v.rstrip("/").rsplit("/", 1)[-1] for v in args[0]]
        if last == "splitext" and args:
            return [os.path.splitext(v)[0] for v in args[0]]
        if last in ("getcwd", "cwd"):
            return ["."]
        return None

    def method(self, val: Optional[List[str]], low: str, args: List[Optional[List[str]]]) -> Optional[List[str]]:
        if val is None or any(a is None for a in args):
            return None
        if low == "joinpath":
            out = val
            for a in args:
                out = [o.rstrip("/") + "/" + v for o in out for v in a][:16]
            return out
        if low in _SAME or low == "resolve":
            return val
        if low == "with_name" and args:
            return [os.path.join(os.path.dirname(v), n) for v in val for n in args[0]][:16]
        if low == "with_suffix" and args:
            return [os.path.splitext(v)[0] + s for v in val for s in args[0]][:16]
        if low == "format":
            out = []
            for v in val:
                filled = v
                for a in args:
                    filled = re.sub(r"\{[^{}]*\}", lambda _m, x=a[0]: x, filled, count=1)
                out.append(filled)
            return out
        if low == "replace" and len(args) == 2:
            return [v.replace(args[0][0], args[1][0]) for v in val]
        return None

    def attribute(self, val: Optional[List[str]], low: str) -> Optional[List[str]]:
        if val is None:
            return None
        if low == "parent":
            return [os.path.dirname(v.rstrip("/")) or "." for v in val]
        if low == "name":
            return [v.rstrip("/").rsplit("/", 1)[-1] for v in val]
        return None

    def name(self, name: str) -> Optional[List[str]]:
        if name in ("sys.argv", "process.argv", "Deno.args", "argv"):
            return list(self.c.argv) or None
        if "." in name or name in _NOT_NAMES or name in self.seen or self.depth > 5:
            return None
        self.seen.add(name)
        out: List[str] = []
        for kind, src in self.c.sources(name):
            if kind == "for" and _LISTING.search(src):  # for f in os.listdir(D): D is written into
                m = _LISTING.search(src)
                before = src[:m.start()].rstrip()
                receiver = before[:-1].rstrip() if before.endswith(".") else ""
                module = re.fullmatch(r"[A-Za-z_][\w.]*", receiver) and (receiver.split(".")[0] in _NOT_NAMES or receiver == "glob")
                listed = receiver if receiver and not module else src[m.end():].split(")", 1)[0].split(",")[0]
                sub = _Values(self.c)
                inner = sub.of(listed, self.depth + 1)
                self.folders += inner or []
                self.folders += sub.folders
                return None
            sub = _Values(self.c)
            sub.seen = self.seen
            vals = sub.of(src.rstrip(":").strip(), self.depth + 1)
            self.folders += sub.folders
            if vals is None:
                return None
            out += vals
        return out[:16] or None


class _Code:
    """Inline code being read: its masked text, literals, calls, and the arguments it was given."""

    def __init__(self, code: str, lang: str, argv: List[str], eff: ShellEffects) -> None:
        self.text, self.lits = _mask(code, lang)
        self.lang = lang
        self.argv = argv
        self.o2c, self.c2o = _brackets(self.text)
        self.calls: List[_Call] = []
        s = self.text
        for m in _CALL.finditer(s):
            if len(self.calls) % 256 == 0:
                eff.tick()
            method = _is_method(s, m.start())
            before = _skip_space_back(s, m.start())
            if not method and re.search(r"(?<![\w$])(?:def|function|class)$", s[max(0, before - 9):before]):
                continue  # a definition, not a call
            recv = _receiver(s, m.start(), self.c2o) if method else ""
            self.calls.append(_Call(m.group(1), recv, method, m.end() - 1, _call_args(s, m.end() - 1, self.o2c)))

    def lit(self, expr: Optional[str]) -> Optional[str]:
        """The value of an argument that is exactly one exact string literal (or Path(literal))."""
        if not expr:
            return None
        m = _LIT.fullmatch(expr.strip()) or _PATH_CALL.fullmatch(expr.strip())
        if m and self.lits[int(m.group(1))][1]:
            return self.lits[int(m.group(1))][0]
        return None

    def writes_mode(self, mode: Optional[str]) -> bool:
        if mode is None:
            return False
        m = _LIT.fullmatch(mode.strip())
        if m:
            return bool(set(self.lits[int(m.group(1))][0]) & set("wax+"))
        return True  # a mode that is not a literal may write

    def sources(self, name: str) -> List[Tuple[str, str]]:
        """Where a name gets its value: ("=", expression) for an assignment, ("for", iterable) for a for loop,
        ("append", value) for what is appended to it; empty when nothing is found (or it is a parameter)."""
        n = re.escape(name)
        s = self.text
        found = [("=", m.group(1)) for m in re.finditer(
            rf"(?<![\w$.]){n}[ \t]*(?::[^=\n;]{{0,120}})?(?:\+=|:=|=)(?!=)[ \t]*([^\n;]*)", s)]
        found += [("for", m.group(1)) for m in re.finditer(
            rf"\bfor\b[ \t]*\(?[ \t]*(?:const[ \t]+|let[ \t]+|var[ \t]+)?[\w$, \t()\[\]]{{0,200}}?(?<![\w$]){n}"
            rf"(?![\w$])[\w$, \t()\[\]]{{0,200}}?[ \t](?:in|of)[ \t]+([^\n]*)", s)]
        found += [("append", m.group(1)) for m in re.finditer(
            rf"(?<![\w$.]){n}[ \t]*\.[ \t]*(?:append|extend|insert|add|push|unshift)[ \t]*\(([^\n]*)\)", s)]
        if re.search(rf"\bdef\s+\w+\s*\([^)\n]{{0,300}}(?<![\w$]){n}(?![\w$])|\blambda\b[^:\n]{{0,300}}"
                     rf"(?<![\w$]){n}(?![\w$])|(?<![\w$]){n}[ \t]*=>|\([^()\n]{{0,300}}(?<![\w$]){n}(?![\w$])"
                     rf"[^()\n]{{0,300}}\)[ \t]*=>|\bfunction\b[^(\n]{{0,80}}\([^)\n]{{0,300}}(?<![\w$]){n}(?![\w$])",
                     s):
            return []  # a parameter: not followed
        return found

    def candidates(self, expr: str) -> Tuple[List[str], List[str], bool]:
        """The paths a write's target expression can be, the folders the code lists and writes into, and whether the
        target was put together exactly (False: only its literals were found, as a fallback)."""
        values = _Values(self)
        vals = values.of(expr)
        if vals is not None:
            return vals, values.folders, True
        lits = [self.lits[int(i)][0] for i in _LIT.findall(expr)]
        out = lits[-1:]
        if len(lits) > 1:
            out.append("/".join([lits[0].rstrip("/\\")] + [v.strip("/\\") for v in lits[1:]]))
        if re.search(r"\bargv\b|\bargs\b", expr):
            out += self.argv
        return out, values.folders, False


def _read_sink(c: _Code, call: _Call) -> Optional[str]:
    """(c) The argument a read sink is given straight: open(p) or open(p, "r" / "rb"), Path(p).read_text / read_bytes /
    exists / is_file / is_dir / stat, spec_from_file_location(name, p), fs.readFileSync / existsSync, require(p),
    os.path.exists / isfile (json.load(open(p)): p is open's)."""
    low = call.name.lower()
    pos = call.pos
    if low == "open" and call.recv in ("", "io", "codecs", "builtins"):
        mode = _keyword(call.args, ("mode",)) or (pos[1] if len(pos) > 1 else None)
        return None if c.writes_mode(mode) else (_keyword(call.args, ("file",)) or (pos[0] if pos else None))
    if _PATHLIKE.fullmatch(call.name) and pos:
        close = c.o2c.get(call.open, -1)
        after = re.match(r"\s*\.\s*([A-Za-z_]\w*)\s*\(", c.text[close + 1:close + 80]) if close >= 0 else None
        return pos[0] if after and after.group(1) in _PATH_READS else None
    if low in ("exists", "isfile", "isdir", "getsize") and call.recv in ("os.path", "path"):
        return pos[0] if pos else None
    index = _READ_SINKS.get(low)
    if index is not None and len(pos) > index and (low != "require" or not call.method):
        return pos[index]
    return None


def _code(code: str, lang: str, argv: List[str], scope: _Scope, eff: ShellEffects, depth: int) -> None:
    """Read inline code (lang "py", "js" or "ps") for the files it writes and removes; and for (c): the reader is
    unsure when it runs commands or code, opens files in a way it does not check (opener=, os.open, os.fdopen), or
    writes to anything but a plain literal (a /dev/fd/ or /proc/ target included); its literals that are not given
    straight to a read sink go to eff.other; its plain literal targets to eff.code_writes."""
    eff.tick()
    c = _Code(code, lang, argv, eff)
    s = c.text
    writes: List[Tuple[str, int]] = []  # (target expression, 0 file / 1 removal / 2 folder)
    read_ok: set = set()
    aliases = {m.group(2): m.group(1) for m in re.finditer(r"\bimport\s+(os|shutil)\s+as\s+([A-Za-z_]\w*)", s)}
    for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?(?:require|import)\(\s*"
                         r"\x01(\d+)\x02\s*\)|\bimport\s+(?:\*\s+as\s+)?([A-Za-z_$][\w$]*)\s+from\s+\x01(\d+)\x02", s):
        value = c.lits[int(m.group(2) or m.group(4))][0]
        if re.fullmatch(r"(?:node:)?fs(?:/promises)?|fs-extra", value):
            aliases[m.group(1) or m.group(3)] = "fs"
    bare = {n.split()[-1] for m in re.finditer(r"\bfrom\s+(?:os|shutil)\s+import\s+\(?([^\n;)]+)", s)
            for n in m.group(1).split(",") if n.strip()}  # from shutil import copy, move as mv
    for call in c.calls:
        name, method, args, pos = call.name, call.method, call.args, call.pos
        low = name.lower()
        recv = aliases.get(call.recv, call.recv)
        path_recv = _PATH_CALL.fullmatch(recv) is not None
        module = (recv in _FS_MODULES or re.search(r"(?:^|\.)(?:fs|promises)$", recv) is not None
                  or recv.startswith("require(") or (not method and name in bare))
        dotnet = re.search(r"\[(?:System\.)?IO\.(?:File|FileInfo|Directory)\]$", recv, re.I) is not None
        sink = _read_sink(c, call)
        if sink is not None and _LIT.fullmatch(sink.strip()):
            read_ok.add(int(sink.strip()[1:-1]))
        if _keyword(args, ("opener",)) is not None or (low in ("open", "fdopen") and recv == "os") or low == "fdopen":
            eff.doubt("inline code that opens a file in a way the reader does not check")
        if (low in ("import_module", "__import__") or (low in ("require", "import") and not method)) \
                and (not pos or c.lit(pos[0]) is None):
            eff.doubt("inline code that loads code by a name it builds")
        if low in _RUNS_CODE or name == "Function" or re.search(r"\bshell\s*=\s*True\b", ",".join(args)):
            eff.doubt("inline code that runs commands or code")
            first = pos[0] if pos else None
            value = c.lit(first)
            if value is not None and depth < _MAX_DEPTH:
                if low in ("exec", "eval") and not method and lang == "py":
                    _code(value, "py", argv, scope, eff, depth + 1)  # exec("open('…', 'w')")
                elif low not in ("exec", "eval", "run", "run_path", "run_module") or recv or "shell" in ",".join(args):
                    _script(value, scope.copy(), eff, depth + 1)  # os.system("…"), execSync("…")
            elif first and first.startswith("[") and first.endswith("]"):  # subprocess.run(["cp", "a", "b"])
                inner_text = "(" + first[1:-1] + ")"
                items = [c.lit(x) for x in _call_args(inner_text, 0, _brackets(inner_text)[0])]
                if items and all(x is not None for x in items) and depth < _MAX_DEPTH:
                    inner = _Simple()
                    inner.words = [str(x) for x in items]
                    inner.quoted = [True] * len(items)
                    _simple(inner, scope, eff, depth + 1, None, None)
            continue
        if low == "open":
            if recv == "os":
                flags = pos[1] if len(pos) > 1 else ""
                if pos and re.search(r"O_(?:WRONLY|RDWR|CREAT|APPEND|TRUNC)", flags):
                    writes.append((pos[0], 0))
            elif path_recv or (method and not module and recv not in ("io", "codecs", "builtins", "gzip", "bz2",
                                                                            "lzma", "tarfile")
                               and (not pos or (c.lit(pos[0]) is not None and _MODE.match(c.lit(pos[0]) or "")))):
                if c.writes_mode(_keyword(args, ("mode",)) or (pos[0] if pos else None)):
                    writes.append((recv, 0))  # Path(…).open("w")
            elif c.writes_mode(_keyword(args, ("mode", "flags")) or (pos[1] if len(pos) > 1 else None)):
                target = _keyword(args, ("file",)) or (pos[0] if pos else None)
                if target:
                    writes.append((target, 0))
        elif low in ("write_text", "write_bytes", "touch") and method:
            writes.append((recv, 0))
        elif low in ("writefile", "writefilesync", "appendfile", "appendfilesync", "createwritestream", "outputfile",
                     "outputfilesync", "writejson", "writejsonsync", "outputjson", "outputjsonsync", "writetextfile",
                     "writetextfilesync", "truncatesync") or (low == "write" and recv == "Bun") \
                or (low == "truncate" and (module or recv == "")) \
                or (dotnet and low in ("writealltext", "writealllines", "writeallbytes", "appendalltext",
                                       "appendalllines", "create", "createtext", "appendtext", "openwrite")):
            if pos:
                writes.append((pos[0], 0))
        elif low in ("copy", "copy2", "copyfile", "copytree", "copyfilesync", "cp", "cpsync", "copysync", "link",
                     "linksync", "symlink", "symlinksync") and (module or dotnet or recv.endswith("shutil")
                                                                 or low.startswith(("copyfile", "cpsync", "copysync"))):
            if len(pos) > 1:
                writes.append((pos[1], 2 if low in ("copytree", "cp", "cpsync") else 0))
                if low in ("copytree", "cp", "cpsync"):
                    writes.append((pos[1], 0))
        elif low in ("move", "rename", "renames", "renamesync", "replace") and (module or dotnet
                                                                                 or recv.endswith("shutil")):
            if len(pos) > 1:
                writes += [(pos[1], 0), (pos[1], 2), (pos[0], 1)]
        elif low in ("rename", "replace") and path_recv:
            if pos:
                writes += [(pos[0], 0), (pos[0], 2)]
            writes.append((recv, 1))
        elif low == "rename" and method and recv and not module:  # p.rename(target)
            if pos:
                writes += [(pos[0], 0), (pos[0], 2)]
        elif (low in ("remove", "removedirs") and (recv in ("os", "Deno") or (not method and name in bare))) \
                or low in ("rmtree", "rmsync", "rmdirsync", "unlinksync") \
                or (low in ("rm", "rmdir", "unlink") and (module or recv == "") and pos) \
                or (dotnet and low == "delete"):
            if pos:
                writes.append((pos[0], 1))
        elif low in ("unlink", "rmdir") and method and not pos:  # Path(…).unlink()
            writes.append((recv, 1))
        elif low in ("input", "fileinput") and re.search(r"\binplace\s*=\s*(?:True|1)\b", ",".join(args)):
            files = _keyword(args, ("files",)) or (pos[0] if pos else None)
            if files:
                writes.append((files, 0))
    for expr, kind in writes:
        found, folders, exact = c.candidates(expr)
        plain = c.lit(expr)
        if plain is None or re.match(r"/dev/fd/|/proc/", plain):
            eff.doubt("inline code that writes to a path it builds")
        else:
            eff._add(3, plain, scope)
            eff.data_files.append((plain, plain))  # like (a): void when the file may be used again or picked up
        if not found and not folders:
            eff.doubt("inline code that writes or removes somewhere the reader cannot follow")
        for p in found:
            if kind == 1:
                eff.remove(p, scope)
            elif kind == 2:
                eff.write_folder(p, scope)
            else:
                eff.write(p, scope)
        for folder in folders:
            eff.write_folder(folder, scope)
    if lang == "ps":
        return
    if any(not exact for _value, exact in c.lits):
        eff.doubt("inline code with an f-string or a template")
    eff.note(scope, *(value for index, (value, _exact) in enumerate(c.lits) if index not in read_ok))


# Files a program picks up by itself (startup files, hooks, project files) and code that can be imported by name.
_PICKED_UP = re.compile(r"(?:^|/)(?:sitecustomize\.py|usercustomize\.py|[^/]*\.pth|\.pythonrc(?:\.py)?|\.bashrc|"
                        r"\.bash_profile|\.bash_login|\.bash_logout|\.profile|\.zshrc|\.zprofile|\.zshenv|\.zlogin|"
                        r"\.zlogout|\.kshrc|\.npmrc|\.yarnrc(?:\.yml)?|\.envrc|\.env|\.curlrc|\.wgetrc|\.vimrc|\.exrc|"
                        r"\.gitconfig|\.gitattributes|\.gitmodules|\.pre-commit-config\.yaml|\.lintstagedrc[^/]*|"
                        r"lefthook\.ya?ml|package\.json|[Mm]akefile|GNUmakefile|[^/]*\.mk|conftest\.py|"
                        r"pyproject\.toml|setup\.py|setup\.cfg|tox\.ini|noxfile\.py|tasks\.py|fabfile\.py|[Jj]ustfile|"
                        r"Taskfile\.ya?ml|Rakefile|Gemfile|Dockerfile|build\.gradle(?:\.kts)?|pom\.xml|"
                        r"CMakeLists\.txt|Cargo\.toml|build\.rs|deno\.jsonc?|bunfig\.toml|[^/]*\.config\.[cm]?[jt]s)$")
_CODE_SUFFIX = re.compile(r"\.(?:py|pyc|pyw|pth|js|mjs|cjs|ts|mts|cts|jsx|tsx|sh|bash|zsh|ps1|psm1|rb|pl|pm|php|lua|"
                          r"r|mk)$", re.I)
_LOADERS = re.compile(r"\b(?:python[\d.]*|py|pypy[\d.]*|node|nodejs|bun|deno|tsx|ts-node|bash|sh|zsh|dash|ksh|source|"
                      r"make|npm|npx|pnpm|yarn|uv|uvx|import|require|PYTHONPATH|NODE_PATH|NODE_OPTIONS|sys\.path|runpy|"
                      r"perl|ruby|php|lua|Rscript|pwsh|powershell|PERL5LIB|RUBYLIB)\b|(?:^|\s)\.\s")


# Ways a command runs text later, somewhere the reader does not follow: a trap, a shell function or alias, a startup
# variable a shell reads (BASH_ENV, ENV, PROMPT_COMMAND), eval, source / . of anything.
_DEFERRED = re.compile(r"\btrap\b|\balias\b|\bfunction\s+[\w.:-]+|[\w.:-]+\s*\(\s*\)\s*[{(]|\bBASH_ENV\b|"
                       r"(?:^|[\s;&|({])ENV=|\bPROMPT_COMMAND\b|\bZDOTDIR\b|\beval\b|\bsource\b|(?:^|[\s;&|({])\.\s")


class _Words:
    """The command's words counted once (names, stems, and whether it starts a program that loads code), so that the
    (a) check stays linear however many files the command writes."""

    def __init__(self, command: str) -> None:
        self.command = command
        self.names: Dict[str, int] = {}
        self.stems: Dict[str, int] = {}
        for w in re.findall(r"[^\s/\\'\"`=;|&<>(){}\[\],:]+", command):
            self.names[w] = self.names.get(w, 0) + 1
            stem = w.split(".", 1)[0]
            self.stems[stem] = self.stems.get(stem, 0) + 1
        self.loads = _LOADERS.search(command) is not None
        self.deferred = _DEFERRED.search(command) is not None
        self.globs = re.findall(r"[^\s'\"`=;|&<>(){}]*[*?\[][^\s'\"`=;|&<>(){}]*", command)[:_MAX_TARGETS]
        self.folders: Dict[str, int] = {}

    def folder_count(self, folder: str) -> int:
        if folder not in self.folders:
            self.folders[folder] = self.command.count(folder)
        return self.folders[folder]


def _data_file_used(words: "_Words", path: str, word: str) -> bool:
    """(a) is void for a file F the command writes (as data, or from (c)'s inline code) when F may be used later
    without being run by name: its name, stem or folder appears again in the command; it is a file a program picks up
    by itself (startup, hook or project files: sitecustomize.py, *.pth, .bashrc, .npmrc, package.json, Makefile,
    anything under .git/ or .husky/, a hooks folder or a file named as a git hook); the command can run text later
    where the reader does not follow (a trap, a shell function or alias, BASH_ENV / ENV / PROMPT_COMMAND, eval,
    source); a glob in it matches F's name; or it is code (.py, .js, .sh …, or a file with no suffix) and the command
    also starts an interpreter, a shell or a package tool, or imports."""
    if "$" in word or "`" in word:
        return True
    norm = word.replace("\\", "/").rstrip("/")
    leaf = norm.rsplit("/", 1)[-1]
    if not leaf:
        return True
    stem = leaf.split(".", 1)[0]
    folder = norm.rsplit("/", 1)[0] if "/" in norm else ""
    if words.names.get(leaf, 0) > 1 or (stem and words.stems.get(stem, 0) > 1):
        return True
    if folder and folder not in (".", "/tmp") and words.folder_count(folder) > 1:
        return True
    for p in (path.replace("\\", "/"), norm):
        if _PICKED_UP.search(p) or _HOOK_FILE.search(p):
            return True
    if words.deferred:  # a trap, function, alias, BASH_ENV / ENV / PROMPT_COMMAND, eval or source may run it later
        return True
    if any(fnmatch.fnmatchcase(leaf, g.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]) for g in words.globs):
        return True  # a glob (source *.md, cat notes/*) can reach it without its name
    return (bool(_CODE_SUFFIX.search(leaf)) or "." not in leaf) and words.loads


_EFFECTS_CACHE: Dict[Tuple[str, str, Optional[str]], ShellEffects] = {}
_MAX_NESTING = 200  # brackets ( [ { nested deeper than this are not read (the reader would hit the recursion limit)


def _nesting(command: str) -> int:
    """How deep the command's brackets nest, counted over the raw text (quotes included)."""
    depth = most = 0
    for m in re.finditer(r"[(\[{]|[)\]}]", command):
        if m.group(0) in "([{":
            depth += 1
            most = max(most, depth)
        elif depth:
            depth -= 1
    return most


def shell_effects(command: str, cwd: str, root: Optional[str] = None) -> ShellEffects:
    """What a shell command (Bash or PowerShell) writes, removes and how it is judged, run in cwd, in the project at
    root (for $CLAUDE_PROJECT_DIR and a cd the reader can only guess). Past its time budget, or on an internal error,
    the reader is unsure (the earlier reader decides) and eff.trouble says why (pre_edit logs it with the outcome)."""
    key = (command, cwd, root)
    if key not in _EFFECTS_CACHE:
        try:  # PLUMB_SHELL_BUDGET: seconds, for tests
            budget = float(os.environ.get("PLUMB_SHELL_BUDGET") or SHELL_BUDGET)
        except ValueError:
            budget = SHELL_BUDGET
        eff = ShellEffects(root, time.monotonic() + budget)
        eff.command = command
        scope = _Scope((cwd,), {})
        try:
            if _nesting(command) > _MAX_NESTING:  # not read: pre_edit refuses it when it names a guarded path
                eff.doubt("brackets nested deeper than the reader reads")
                eff.trouble = (f"the command nests brackets deeper than {_MAX_NESTING}", "deep", None)
            else:
                _script(command, scope, eff)
                counted = _Words(command) if eff.data_files else None
                for path, word in eff.data_files:  # (a): a file the command writes and may use again is not data
                    if _data_file_used(counted, path, word):
                        eff.doubt("a file the command writes is used again in it, or is one a program picks up")
        except _Budget:
            eff.doubt("the reader ran out of its time budget")
            eff.trouble = ("the shell reader ran past its time budget", "timeout", None)
        except Exception as exc:  # noqa: BLE001 - never fail open: the earlier reader decides
            eff.doubt(f"the reader failed ({type(exc).__name__})")
            eff.trouble = (f"the shell reader failed ({type(exc).__name__}: {exc})", "crash", exc)
        _EFFECTS_CACHE.clear()
        _EFFECTS_CACHE[key] = eff
    return _EFFECTS_CACHE[key]


_LEGACY: List[object] = []


def _legacy():
    """The earlier shell reader (_shell_legacy.py, the plugin's own file next to this one)."""
    if not _LEGACY:
        spec = importlib.util.spec_from_file_location("plumb_shell_legacy", os.path.join(HOOKS_DIR, "_shell_legacy.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        _LEGACY.append(module)
    return _LEGACY[0]


def legacy_targets(command: str, cwd: str) -> List[str]:
    """What the earlier shell reader counted as the command's writes (the guard's floor)."""
    return _legacy().shell_targets(command, cwd)  # type: ignore[attr-defined]


def legacy_removals(command: str, cwd: str) -> List[str]:
    """What the earlier shell reader counted as the command's removals (the guard's floor)."""
    return _legacy().shell_removals(command, cwd)  # type: ignore[attr-defined]
