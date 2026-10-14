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
                exit_code: int = 0) -> None:
    """Append one line about a hook that failed open to ~/.plumb/feedback/hooks.md (Plumb's own mistakes, for Plumb's
    developers; never written into the project). Only in a project with a PLUMB.md. Given and Expected are redacted
    (redact) and cut to one short line. The same line (hook, project, Given) is written once a day; a timeout once per
    project and Plumb version (a slow repo is not news every day). Never raises, never prints, never blocks: any
    problem (no private folder, a symlinked or foreign hooks.md, a full log) leaves the log out. A PlumbError is the
    scripts' actionable refusal about the project's own files (a broken tokens file, a snapshot that is not valid):
    the project's problem, never logged."""
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
                  f"exit {exit_code} (failed open)", f"Given: {_one_line(given, str(root))}",
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
# What a Bash or PowerShell command writes, moves away or removes. A small lexer (quotes, escapes, here-documents,
# $( ), backticks, process substitution, subshells, comments, the operators) splits the command into simple commands;
# only real write targets count:
# - a redirect target (>, >>, 1>, 2>, &>, >|, <>), tee [-a], sed -i / perl -i, the destination of cp / mv / install /
#   rsync / ln (a folder destination writes <folder>/<source name>), truncate, dd of=, curl -o / wget -O, and
#   PowerShell's Set-Content, Add-Content, Out-File, Copy-Item, Move-Item, New-Item; rm and the other removals;
# - a shell's own script (bash -c "…", a here-document fed to a shell, eval's words, find -exec), read as commands;
# - an interpreter's inline code (python -c, node -e, deno eval, a here-document or an echo piped to an interpreter):
#   open("<path>", "w" | "a" | "x" | "+"), Path("<path>").write_text / write_bytes / open("w"), shutil.copy / move,
#   os.replace / rename, fs.writeFile / appendFile / copyFile / createWriteStream, Bun.write, Deno.writeTextFile,
#   [IO.File]::WriteAllText …, and the removals os.remove, shutil.rmtree, Path.unlink, fs.rm … A write whose target is
#   a name, not a literal, counts the literals that reach that name (its assignments, a for loop over it, what is
#   appended to it, the script's own arguments); when that cannot be followed (a function parameter), every literal
#   the code does not only read, run or import counts, as before.
# Everything else is data: quoted strings, the body of a here-document fed to anything but a shell or an interpreter
# (cat > Makefile <<EOF), and the text of echo, printf, git, grep … Reading, running and importing a guarded file is
# allowed. A quoted argument of a program not known here (ssh, watch, awk …) may be a command that program runs: its
# write targets count (writes only).


# A cheap first look: a command with none of these cannot write or remove a file.
WRITE_HINT = re.compile(r">|\btee\b|\bsed\b|\bperl\b|\bcp\b|\bmv\b|\binstall\b|\brsync\b|\bln\b|\bdd\b|truncate|"
                        r"write|open\(|shutil|os\.(?:replace|rename)|-content\b|out-file|copy-item|move-item|::|"
                        r"append|copyfile|\bfs\.|rename|\bcopy\b|cpSync|\bcp\(|\bcurl\b|\bwget\b|new-item|\bni\b|"
                        r"inplace|remove|rmtree|unlink|rmdir|rmSync|"
                        # removals and moves: rm, del, erase, rd, Remove-Item, ri, move, mi
                        r"\brm\b|\bdel\b|\berase\b|\brd\b|remove-item|\bri\b|\bmove\b|\bmi\b",
                        re.I)

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
                    out.append(_ANSI.get(text[j + 1], text[j + 1]))
                    j += 2
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

    __slots__ = ("words", "quoted", "redirs", "stdin", "subs", "piped")

    def __init__(self, piped: bool = False) -> None:
        self.words: List[str] = []
        self.quoted: List[bool] = []
        self.redirs: List[str] = []
        self.stdin: List[str] = []
        self.subs: List[str] = []
        self.piped = piped

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
            elif nxt is not None and (op in _WRITE_REDIRS or (op == ">&" and not re.fullmatch(r"\d*-?", nxt[1]))):
                cur.redirs.append(nxt[1])
        else:
            if not cur.empty():
                events.append(("cmd", cur))
            cur = _Simple(piped=t[0] == "op" and t[1] in ("|", "|&"))
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


def _word_path(word: str, base: str) -> Optional[str]:
    if not word or word.lower() in _NOT_FILES or word.startswith("/dev/fd/"):
        return None
    p = word.replace("\\", "/") if os.sep == "/" else word
    p = os.path.expanduser(_HOME_VAR.sub(lambda _m: "~", p))
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(base, p))


class _Effects:
    """The files a command writes and removes (absolute, in order, once each)."""

    def __init__(self) -> None:
        self.writes: List[str] = []
        self.removals: List[str] = []

    def write(self, word: str, base: str) -> None:
        path = _word_path(word, base)
        if path is not None and path not in self.writes:
            self.writes.append(path)

    def remove(self, word: str, base: str) -> None:
        path = _word_path(word, base)
        if path is not None and path not in self.removals:
            self.removals.append(path)


def _command_name(word: str) -> str:
    name = re.split(r"[/\\]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


_RESERVED = frozenset(("if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "coproc"))
# Commands that run the rest of their words as a command, and the flags of theirs that take a value.
_WRAPPERS: Dict[str, Tuple[str, ...]] = {
    "sudo": ("-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group"), "doas": ("-u", "-C"),
    "command": (), "builtin": (), "exec": ("-a",), "nohup": (), "time": ("-f", "-o"), "env": ("-u", "-C", "-S"),
    "nice": ("-n",), "ionice": ("-c", "-n", "-p"), "stdbuf": ("-i", "-o", "-e"), "timeout": ("-s", "-k", "--signal",
                                                                                            "--kill-after"),
    "xargs": ("-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"), "chronic": (), "unbuffer": (), "caffeinate": ("-w", "-t"),
}


def _command_start(words: List[str]) -> int:
    """The index of the word that names the command: after FOO=bar, reserved words (if, then, do …) and wrappers that
    run their words as a command (sudo, env, nice, timeout, xargs, uv run …)."""
    i, n = 0, len(words)
    while i < n:
        w = words[i]
        name = _command_name(w)
        if re.match(r"^[A-Za-z_]\w*=", w) or w in _RESERVED:
            i += 1
        elif name in _WRAPPERS:
            i += 1
            while i < n and words[i].startswith("-") and len(words[i]) > 1:
                if words[i] == "--":
                    i += 1
                    break
                i += 2 if words[i] in _WRAPPERS[name] else 1
            if name == "timeout" and i < n:
                i += 1  # the duration
        elif name == "uv" and i + 1 < n and words[i + 1] == "run":
            i += 2
            while i < n and words[i].startswith("-"):
                i += 2 if words[i] in _UV_VALUE_FLAGS else 1
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


def _copy_writes(name: str, args: List[str], base: str, out: _Effects) -> None:
    """The destination of cp / mv / install / rsync / ln (and cmd's copy / move): the last word, or -t DIR; a folder
    destination (several sources, a trailing slash, or an existing folder) writes <folder>/<source name> too."""
    vf = _COPY_VALUE_FLAGS[name]
    into = _flag_value(args, ("-t", "--target-directory")) if "-t" in vf else None
    pos = _positional(args, vf)
    if name in ("copy", "move"):
        pos = [p for p in pos if not re.fullmatch(r"/[A-Za-z-]+", p)]  # cmd's /y /b switches
    if into is not None:
        folder, sources = into, pos
        out.write(folder, base)
    elif name == "ln" and len(pos) == 1:
        folder, sources = ".", pos  # ln -s TARGET: a link named like the target, here
    elif len(pos) >= 2:
        dest, sources = pos[-1], pos[:-1]
        out.write(dest, base)
        full = _word_path(dest, base)
        if not (len(pos) > 2 or dest.endswith(("/", "\\")) or (full is not None and os.path.isdir(full))):
            return
        folder = dest
    else:
        return
    for s in sources:
        leaf = re.split(r"[/\\]", s.rstrip("/\\"))[-1]
        if leaf and leaf not in (".", ".."):
            out.write(folder.rstrip("/\\") + "/" + leaf, base)


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


def _shell_script(name: str, args: List[str]) -> Tuple[Optional[str], bool]:
    """A shell's script from its words: (`bash -c "…"`, `sh -ec '…'`, `pwsh -c …`, `powershell -Command …` (the rest of
    the line), or None; and whether it reads its commands from stdin (no script file named)."""
    j = 0
    while j < len(args):
        flag = args[j].lower()
        if name in _PS_SHELLS:
            if flag.startswith("-") and len(flag) >= 2 and "-command".startswith(flag):
                rest = args[j + 1:]
                return (" ".join(rest) if rest else None), False
            if flag.startswith("-") and len(flag) >= 3 and "-file".startswith(flag):
                return None, False
            if not flag.startswith("-"):
                return None, False
            j += 2 if flag in ("-executionpolicy", "-ep", "-workingdirectory", "-wd", "-outputformat", "-inputformat",
                               "-configurationname", "-settingsfile", "-version", "-psconsolefile") else 1
            continue
        if re.match(r"^-[a-z]*c[a-z]*$", flag):
            return (args[j + 1] if j + 1 < len(args) else None), False
        if flag in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            j += 2
            continue
        if flag == "-s":
            return None, True
        if not flag.startswith(("-", "+")):
            return None, False  # a script file: its contents are not on the line
        j += 1
    return None, True


_PY_NAME = re.compile(r"python[\d.]*|py|pypy[\d.]*")


def _python_code(args: List[str], stdin: List[str]) -> Tuple[List[str], List[str]]:
    """The code python runs from its command line (-c CODE, or stdin for `-` / no script) and the code's arguments."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-":
            return stdin, args[i + 1:]
        if a.startswith("--"):
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            flags, skip = a[1:], 0
            for k, ch in enumerate(flags):
                if ch == "c":
                    if flags[k + 1:]:
                        return [flags[k + 1:]], args[i + 1:]
                    return (args[i + 1:i + 2], args[i + 2:])
                if ch == "m":
                    return [], []  # a module runs: its code is not on the line
                if ch in "XW":
                    skip = 0 if flags[k + 1:] else 1
                    break
            i += 1 + skip
            continue
        return [], []  # a script file
    return stdin, []


def _node_code(name: str, args: List[str], stdin: List[str]) -> Tuple[List[str], List[str]]:
    """The code node / bun / deno runs from its command line (-e / --eval / -p, deno eval, or stdin) and its arguments."""
    i = 0
    if name == "deno":
        if not args or args[0] != "eval":
            return [], []
        pos = _positional(args[1:], ("--ext", "--import-map", "--config", "-c", "--location"))
        return pos[:1], pos[1:]
    while i < len(args):
        a = args[i]
        if a in ("-e", "--eval", "-p", "--print", "-pe"):
            return args[i + 1:i + 2], args[i + 2:]
        if a.startswith(("--eval=", "--print=")):
            return [a.split("=", 1)[1]], args[i + 1:]
        if a == "-":
            return stdin, args[i + 1:]
        if a in ("-r", "--require", "--import", "--loader", "-C", "--conditions", "--env-file"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return [], []  # a script file (or bun run …)
    return stdin, []


# Programs whose quoted words are data (text, patterns, messages, code read elsewhere), never a command they run.
_DATA_PROGRAMS = frozenset((
    "echo", "printf", "cat", "grep", "egrep", "fgrep", "rg", "ag", "ack", "git", "gh", "jq", "yq", "ls", "wc", "head",
    "tail", "sort", "uniq", "cut", "tr", "diff", "cmp", "comm", "test", "[", "[[", "true", "false", "which", "type",
    "file", "stat", "du", "df", "mkdir", "touch", "chmod", "chown", "sleep", "date", "basename", "dirname", "realpath",
    "readlink", "read", "export", "local", "declare", "typeset", "set", "unset", "alias", "printenv", "sha256sum",
    "shasum", "md5sum", "md5", "base64", "xxd", "od", "column", "less", "more", "open", "code", "npm", "pnpm", "yarn",
    "npx", "bunx", "make", "gmake", "tsc", "eslint", "prettier", "pytest", "pip", "pip3", "uv", "uvx", "claude",
    "copilot", "for", "case", "in", "select", "function", "return", "exit", "break", "continue", "source", ".", "cd",
    "pushd", "popd", "perl", "ruby", "write-output", "write-host", "write-error", "get-content", "gc", "select-string",
    "sls", "get-childitem", "gci", "dir", "test-path", "convertfrom-json", "convertto-json", "out-host", "out-null",
    "out-string", "format-table", "format-list", "select-object", "where-object", "sort-object", "measure-object",
    "get-item", "resolve-path", "join-path", "split-path", "cls", "clear", "curl", "wget", "find", "tee", "sed",
    "gsed", "cp", "mv", "install", "rsync", "ln", "truncate", "dd", "copy", "move", "copy-item", "move-item", "cpi",
    "mi", "eval",
) + _REMOVERS + _PS_WRITERS + _SHELLS)


def _cd(words: List[str], base: str) -> Optional[str]:
    """The folder a cd / pushd / Set-Location moves to, or None for any other command."""
    if not words or _command_name(words[0]) not in ("cd", "pushd", "chdir", "set-location", "sl"):
        return None
    pos = [w for w in _positional(words[1:], ()) if w.lower() not in ("/d",)]
    target = _flag_value(words[1:], ("-path", "-literalpath")) or (pos[0] if pos else None)
    if target is None or target == "-":
        return None
    return _word_path(target, base)


def _simple(cmd: _Simple, base: str, out: _Effects, depth: int, before: Optional[_Simple]) -> None:
    """The writes and removals of one simple command, run in folder base."""
    for target in cmd.redirs:
        out.write(target, base)
    start = _command_start(cmd.words)
    words, quoted = cmd.words[start:], cmd.quoted[start:]
    if not words:
        return
    name, args = _command_name(words[0]), words[1:]
    stdin = list(cmd.stdin)
    if not stdin and cmd.piped and before is not None:  # echo "code" | python3: the code is the echo's words
        prev = before.words[_command_start(before.words):]
        if prev and _command_name(prev[0]) in ("echo", "printf"):
            stdin = [" ".join(prev[1:]).replace("\\n", "\n")]
        elif prev and _command_name(prev[0]) == "cat" and len(prev) == 1:
            stdin = list(before.stdin)
    for item in _removals(name, args):
        out.remove(item, base)
    if name == "tee":
        for f in _positional(args, ("--output-error",)):
            out.write(f, base)
    elif name in ("sed", "gsed"):
        if any(re.match(r"^-[a-zA-Z]*i", a) or a.startswith("--in-place") for a in args):
            for f in _sed_files(args):
                out.write(f, base)
    elif name == "perl":
        if any(re.match(r"^-[a-zA-Z]*i", a) for a in args):
            for f in _sed_files(args, perl=True):
                out.write(f, base)
    elif name in _COPY_VALUE_FLAGS:
        _copy_writes(name, args, base, out)
    elif name == "git" and args[:1] == ["mv"]:
        _copy_writes("mv", args[1:], base, out)
    elif name == "truncate":
        for f in _positional(args, ("-s", "--size", "-r", "--reference")):
            out.write(f, base)
    elif name == "dd":
        for a in args:
            if a.startswith("of="):
                out.write(a[3:], base)
    elif name == "curl":
        for k, a in enumerate(args):
            if (a in ("--output", "-o") or re.fullmatch(r"-[a-zA-Z]*o", a)) and k + 1 < len(args):
                out.write(args[k + 1], base)
            elif a.startswith("--output="):
                out.write(a.split("=", 1)[1], base)
    elif name == "wget":
        value = _flag_value(args, ("-o", "--output-document"))
        if value is None:
            value = next((args[k + 1] for k, a in enumerate(args[:-1]) if a == "-O"), None)
        if value is not None:
            out.write(value, base)
    elif name in _PS_WRITERS:
        value = _flag_value(args, _PS_PATH_FLAGS)
        pos = _positional(args, _PS_VALUE_FLAGS + _PS_PATH_FLAGS)
        for item in ([value] if value else pos[:1]):
            for x in item.split(","):
                out.write(x.strip(), base)
    elif name in ("copy-item", "move-item", "cpi", "mi"):
        value = _flag_value(args, ("-destination",))
        pos = _positional(args, _PS_VALUE_FLAGS + _PS_PATH_FLAGS + ("-destination",))
        for item in ([value] if value else pos[1:2]):
            out.write(item, base)
    elif name in _SHELLS:
        script, reads_stdin = _shell_script(name, args)
        if script is not None:
            _script(script, base, out, depth + 1)
        elif reads_stdin:
            for body in stdin:
                _script(body, base, out, depth + 1)
    elif name == "eval":
        _script(" ".join(args), base, out, depth + 1)
    elif name == "find":
        _find_exec(args, base, out, depth)
    elif _PY_NAME.fullmatch(name) or name in ("node", "nodejs", "bun", "deno"):
        lang = "py" if _PY_NAME.fullmatch(name) else "js"
        code, argv = _python_code(args, stdin) if lang == "py" else _node_code(name, args, stdin)
        for text in code:
            _code(text, lang, argv, base, out)
    elif name not in _DATA_PROGRAMS:  # ssh host "…", watch "…", awk '{print > "f"}': the writes a command there makes
        for word, was_quoted in zip(args, quoted[1:]):
            if was_quoted and re.search(r"[\s<>|;&]", word):
                inner = _Effects()
                _script(word, base, inner, depth + 1)
                for path in inner.writes:  # awk '{print > "f"}': the target as written and without the code's } ) ]
                    for p in (path, path.rstrip(")]};")):
                        if p and p not in out.writes:
                            out.writes.append(p)


def _find_exec(args: List[str], base: str, out: _Effects, depth: int) -> None:
    """find … -exec CMD … ; (or +, -execdir, -ok): CMD is a command; {} is each file found (unknown here)."""
    k = 0
    while k < len(args):
        if args[k] in ("-exec", "-execdir", "-ok", "-okdir"):
            end = next((j for j in range(k + 1, len(args)) if args[j] in (";", "+")), len(args))
            inner = _Simple()
            inner.words = args[k + 1:end]
            inner.quoted = [False] * len(inner.words)
            if depth < _MAX_DEPTH:
                _simple(inner, base, out, depth + 1, None)
            k = end
        k += 1


def _script(text: str, base: str, out: _Effects, depth: int = 0) -> None:
    """Read a shell script's commands for their writes and removals. `cd DIR` moves the folder for the commands
    after it (not past the end of a subshell); a command substitution runs in the folder of its command."""
    if depth > _MAX_DEPTH or not text.strip():
        return
    if "]::" in text:  # PowerShell's .NET calls: [IO.File]::WriteAllText('…', …)
        _code(text, "ps", [], base, out)
    folders = [base]
    before: Optional[_Simple] = None
    for event in _commands(_lex(text)):
        if event[0] == "push":
            folders.append(folders[-1])
            before = None
            continue
        if event[0] == "pop":
            if len(folders) > 1:
                folders.pop()
            before = None
            continue
        cmd = event[1]
        here = folders[-1]
        for sub in cmd.subs:
            _script(sub, here, out, depth + 1)
        start = _command_start(cmd.words)
        moved = _cd(cmd.words[start:], here)
        if moved is not None:
            folders[-1] = moved
        else:
            _simple(cmd, here, out, depth, before)
        before = cmd


# ---------------------------------------------------------------- inline code (python -c, node -e, PowerShell .NET)


_LIT = re.compile(r"\x01(\d+)\x02")
_CALL = re.compile(r"([A-Za-z_$][\w$]*)\s*\(")
_PATH_CALL = re.compile(r"^(?:pathlib\s*\.\s*)?(?:Pure)?(?:Posix|Windows)?Path\s*\(\s*\x01(\d+)\x02\s*\)$")
_MODE = re.compile(r"^[rwaxbtU+]{1,4}$")
_FS_MODULES = ("os", "shutil", "fs", "fsp", "Deno", "Bun", "promises")
# Calls that only read, run or import the path they are given (for the conservative reading, see _code).
_READ_CALLS = frozenset((
    "read_text", "read_bytes", "exists", "is_file", "is_dir", "isfile", "isdir", "islink", "getsize", "getmtime", "stat",
    "lstat", "listdir", "scandir", "iterdir", "glob", "iglob", "rglob", "load", "loads", "spec_from_file_location",
    "sourcefileloader", "run_path", "import_module", "__import__", "require", "readfilesync", "readfile", "existssync",
    "statsync", "readdirsync", "readdir", "readtextfile", "readtextfilesync", "realpath", "abspath", "relpath",
    "basename", "dirname", "splitext", "expanduser", "print", "log", "run", "call", "check_call", "check_output",
    "popen", "execfilesync", "spawnsync", "execsync", "spawn", "exec", "execfile", "system", "fnmatch", "readalltext",
    "readalllines", "readallbytes", "load_module", "exec_module", "module_from_spec", "access", "accesssync",
))
_NOT_NAMES = frozenset((
    "True", "False", "None", "and", "or", "not", "in", "is", "if", "else", "for", "while", "lambda", "return", "with",
    "as", "import", "from", "def", "class", "await", "async", "new", "const", "let", "var", "function", "of", "typeof",
    "this", "self", "null", "undefined", "true", "false", "os", "sys", "path", "pathlib", "Path", "json", "shutil", "re",
    "io", "codecs", "fs", "fsp", "require", "process", "Deno", "Bun", "console", "Math", "JSON", "Object", "Array",
    "String", "str", "int", "len",
))


def _mask(code: str, lang: str) -> Tuple[str, List[Tuple[str, bool]]]:
    """The code with comments removed and each string literal replaced by \\x01N\\x02, and the literals (value, exact:
    not an f-string or template with a placeholder in it)."""
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


def _close_back(s: str, i: int) -> int:
    """The index of the bracket that opens the one closing at s[i], or -1."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    while i >= 0:
        c = s[i]
        if c in pairs:
            stack.append(pairs[c])
        elif c in "([{":
            if not stack or stack.pop() != c:
                return -1
            if not stack:
                return i
        i -= 1
    return -1


def _skip_space_back(s: str, i: int) -> int:
    while i > 0 and s[i - 1] in " \t\r\n":
        i -= 1
    return i


def _is_method(s: str, name_start: int) -> bool:
    """The name at s[name_start] is called as a method: `.name(` or `::name(`."""
    j = _skip_space_back(s, name_start)
    return j > 0 and (s[j - 1] == "." or s[j - 2:j] == "::")


def _receiver(s: str, end: int) -> str:
    """The expression a method is called on: s[:end] ends with `.` or `::` before the method name."""
    j = end
    while j > 0 and s[j - 1] in ".: \t":
        j -= 1
    k = j
    while k > 0:
        c = s[k - 1]
        if c in ")]":
            back = _close_back(s, k - 1)
            if back < 0:
                break
            k = back
        elif c.isalnum() or c in "_$.\x01\x02" or (c == ":" and k > 1 and s[k - 2] == ":"):
            k -= 1
        else:
            break
    return re.sub(r"\s+", "", s[k:j])


def _call_args(s: str, open_idx: int) -> List[str]:
    """The top-level arguments of the call whose ( is at s[open_idx]."""
    args, depth, cur = [], 0, []
    for c in s[open_idx:]:
        if c in "([{":
            depth += 1
            if depth == 1:
                continue
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                break
        elif c == "," and depth == 1:
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


class _Code:
    """Inline code being read: its masked text, literals, and the arguments it was given."""

    def __init__(self, code: str, lang: str, argv: List[str]) -> None:
        self.text, self.lits = _mask(code, lang)
        self.argv = argv
        self.unresolved = False

    def lit(self, expr: Optional[str]) -> Optional[str]:
        """The value of an argument that is exactly one exact string literal."""
        m = _LIT.fullmatch(expr.strip()) if expr else None
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

    def sources(self, name: str) -> Optional[List[str]]:
        """The expressions a name gets its value from (assignments, for loops, what is appended to it), or None when
        it cannot be followed (a parameter, or nothing found)."""
        n = re.escape(name)
        s = self.text
        if re.search(rf"\bdef\s+\w+\s*\([^)]*(?<![\w$]){n}(?![\w$])|\blambda\b[^:\n]*(?<![\w$]){n}(?![\w$])[^:\n]*:"
                     rf"|\bfunction\b[^(]*\([^)]*(?<![\w$]){n}(?![\w$])|(?<![\w$]){n}\s*=>"
                     rf"|\([^()]*(?<![\w$]){n}(?![\w$])[^()]*\)\s*=>", s):
            return None
        found = [m.group(1) for m in re.finditer(
            rf"(?<![\w$.]){n}\s*(?::[^=\n;]*)?(?:\+=|:=|=)(?!=)\s*([^\n;]*)", s)]
        found += [m.group(1) for m in re.finditer(
            rf"\bfor\b\s*\(?\s*(?:const\s+|let\s+|var\s+)?[\w$,\s()\[\]]*?(?<![\w$]){n}(?![\w$])[\w$,\s()\[\]]*?"
            rf"\s(?:in|of)\s+([^\n]*)", s)]
        found += [m.group(1) for m in re.finditer(
            rf"(?<![\w$.]){n}\s*\.\s*(?:append|extend|insert|add|push|unshift|update)\s*\(([^\n]*)", s)]
        if re.search(rf"\bas\s+{n}(?![\w$])|\bimport\b[^\n]*(?<![\w$.]){n}(?![\w$])", s):
            found.append("")
        return found or None

    def paths(self, expr: str, depth: int = 0, seen: Optional[set] = None) -> List[str]:
        """The paths an expression can be: its literals (the last one, and all of them joined), the code's
        arguments when it reads argv, and, through each name in it, the expressions that name gets its value from."""
        seen = set() if seen is None else seen
        vals = [self.lits[int(i)] for i in _LIT.findall(expr)]
        out: List[str] = []
        if vals:
            last, exact = vals[-1]
            out.append(last)
            if not exact:
                tail = re.split(r"[{}]", last)[-1].lstrip("/\\")
                if tail:
                    out.append(tail)
            if len(vals) > 1:
                out.append("/".join([vals[0][0].rstrip("/\\")] + [v.strip("/\\") for v, _ in vals[1:]]))
        bare = _LIT.sub(" ", expr)
        if re.search(r"\b(?:argv|args)\b", bare):
            out += self.argv
        for m in re.finditer(r"(?<![\w$.])([A-Za-z_$][\w$]*)(?!\s*\()(?![\w$])", bare):
            name = m.group(1)
            if name in _NOT_NAMES or name in seen or depth > 4:
                continue
            seen.add(name)
            srcs = self.sources(name)
            if srcs is None:
                self.unresolved = True
                continue
            for src in srcs:
                out += self.paths(src, depth + 1, seen)
        return out

    def read_only_literals(self) -> set:
        """The literals passed straight to a call that only reads, runs or imports them (open(…) to read,
        json.load, spec_from_file_location, require, subprocess.run, Path(…).read_text …)."""
        s = self.text
        stack: List[Optional[Tuple[str, str, int]]] = []
        found = set()
        i = 0
        while i < len(s):
            c = s[i]
            if c == "(":
                end = _skip_space_back(s, i)
                start = end
                while start > 0 and (s[start - 1].isalnum() or s[start - 1] in "_$"):
                    start -= 1
                name = s[start:end]
                if name and not name[0].isdigit() and name not in ("if", "for", "while", "in", "and", "or", "not",
                                                                   "return"):
                    stack.append((name, _receiver(s, start) if _is_method(s, start) else "", i))
                else:
                    stack.append(None)
            elif c in "[{":
                stack.append(None)
            elif c in ")]}":
                if stack:
                    stack.pop()
            elif c == "\x01":
                end = s.index("\x02", i)
                index = int(s[i + 1:end])
                if self._read_only(s, [e for e in reversed(stack) if e is not None]):
                    found.add(index)
                i = end
            i += 1
        return found

    def _read_only(self, s: str, calls: List[Tuple[str, str, int]]) -> bool:
        for name, recv, open_idx in calls:
            low = name.lower()
            if re.fullmatch(r"(?:Pure)?(?:Posix|Windows)?Path", name):
                close = _balanced(s, open_idx)
                after = re.match(r"\s*\.\s*([A-Za-z_]\w*)\s*\(", s[close + 1:])
                if after:
                    if after.group(1).lower() in _READ_CALLS:
                        return True
                    if after.group(1) == "open":
                        args = _call_args(s, close + 1 + after.end() - 1)
                        pos = _positional_args(args)
                        return not self.writes_mode(_keyword(args, ("mode",)) or (pos[0] if pos else None))
                    return False
                continue  # Path(…) passed on: what the enclosing call does with it
            if low == "open" and recv not in ("os",):
                args = _call_args(s, open_idx)
                pos = _positional_args(args)
                return not self.writes_mode(_keyword(args, ("mode", "flags")) or (pos[1] if len(pos) > 1 else None))
            if low == "append" or low == "insert":
                return recv == "sys.path"
            return low in _READ_CALLS
        return False


def _code(code: str, lang: str, argv: List[str], base: str, out: _Effects) -> None:
    """Read inline code (lang "py", "js" or "ps") for the files it writes and removes, run in folder base."""
    c = _Code(code, lang, argv)
    s = c.text
    writes: List[str] = []  # destination expressions
    removals: List[str] = []
    aliases = {m.group(2): m.group(1) for m in re.finditer(r"\bimport\s+(os|shutil)\s+as\s+([A-Za-z_]\w*)", s)}
    for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?(?:require|import)\(\s*"
                         r"\x01(\d+)\x02\s*\)|\bimport\s+(?:\*\s+as\s+)?([A-Za-z_$][\w$]*)\s+from\s+\x01(\d+)\x02", s):
        value = c.lits[int(m.group(2) or m.group(4))][0]
        if re.fullmatch(r"(?:node:)?fs(?:/promises)?|fs-extra", value):
            aliases[m.group(1) or m.group(3)] = "fs"
    bare = {n.split()[-1] for m in re.finditer(r"\bfrom\s+(?:os|shutil)\s+import\s+\(?([^\n;)]+)", s)
            for n in m.group(1).split(",") if n.strip()}  # from shutil import copy, move as mv
    for m in _CALL.finditer(s):
        name, open_idx = m.group(1), m.end() - 1
        low = name.lower()
        method = _is_method(s, m.start())
        before = _skip_space_back(s, m.start())
        if not method and re.search(r"(?<![\w$])(?:def|function)$", s[max(0, before - 9):before]):
            continue  # a definition, not a call
        recv = _receiver(s, m.start()) if method else ""
        recv = aliases.get(recv, recv)
        args = _call_args(s, open_idx)
        pos = _positional_args(args)
        path_recv = _PATH_CALL.fullmatch(recv) is not None
        module = (recv in _FS_MODULES or re.search(r"(?:^|\.)(?:fs|promises)$", recv) is not None
                  or recv.startswith("require(") or (not method and name in bare))
        dotnet = re.search(r"\[(?:System\.)?IO\.(?:File|FileInfo|Directory)\]$", recv, re.I) is not None
        if low == "open":
            if recv == "os":
                flags = pos[1] if len(pos) > 1 else ""
                if pos and re.search(r"O_(?:WRONLY|RDWR|CREAT|APPEND|TRUNC)", flags):
                    writes.append(pos[0])
            elif path_recv or (method and not module and recv not in ("io", "codecs", "builtins", "gzip", "bz2",
                                                                            "lzma", "tarfile")
                               and (not pos or (c.lit(pos[0]) is not None and _MODE.match(c.lit(pos[0]) or "")))):
                if c.writes_mode(_keyword(args, ("mode",)) or (pos[0] if pos else None)):
                    writes.append(recv)  # Path(…).open("w")
            elif pos and c.writes_mode(_keyword(args, ("mode", "flags")) or (pos[1] if len(pos) > 1 else None)):
                writes.append(pos[0])
        elif low in ("write_text", "write_bytes") and method:
            writes.append(recv)
        elif low in ("writefile", "writefilesync", "appendfile", "appendfilesync", "createwritestream", "outputfile",
                     "outputfilesync", "writejson", "writejsonsync", "outputjson", "outputjsonsync", "writetextfile",
                     "writetextfilesync", "truncatesync") or (low == "write" and recv == "Bun") \
                or (low == "truncate" and (module or recv == "")) \
                or (dotnet and low in ("writealltext", "writealllines", "writeallbytes", "appendalltext",
                                       "appendalllines", "create", "createtext", "appendtext", "openwrite")):
            if pos:
                writes.append(pos[0])
        elif low in ("copy", "copy2", "copyfile", "copytree", "copyfilesync", "cp", "cpsync", "copysync", "link",
                     "linksync", "symlink", "symlinksync") and (module or dotnet or recv.endswith("shutil")
                                                                 or low.startswith(("copyfile", "cpsync", "copysync"))):
            if len(pos) > 1:
                writes.append(pos[1])
        elif low in ("move", "rename", "renames", "renamesync", "replace") and (module or dotnet
                                                                                 or recv.endswith("shutil")):
            if len(pos) > 1:
                writes.append(pos[1])
                removals.append(pos[0])
        elif low in ("rename", "replace") and path_recv:
            if pos:
                writes.append(pos[0])
            removals.append(recv)
        elif low == "rename" and method and recv and not module:  # p.rename(target)
            if pos:
                writes.append(pos[0])
        elif (low in ("remove", "removedirs") and (recv in ("os", "Deno") or (not method and name in bare))) \
                or low in ("rmtree", "rmsync", "rmdirsync", "unlinksync") \
                or (low in ("rm", "rmdir", "unlink") and (module or recv == "") and pos) \
                or (dotnet and low == "delete"):
            if pos:
                removals.append(pos[0])
        elif low in ("unlink", "rmdir") and method and not pos:  # Path(…).unlink()
            removals.append(recv)
        elif low in ("input", "fileinput") and re.search(r"\binplace\s*=\s*(?:True|1)\b", ",".join(args)):
            files = _keyword(args, ("files",)) or (pos[0] if pos else None)
            if files:
                writes.append(files)
    if not writes and not removals:
        return
    for expr in writes:
        for p in _expr_targets(c, expr):
            out.write(p, base)
    for expr in removals:  # a removal whose target cannot be followed counts only the paths followed (never guessed)
        for p in _expr_targets(c, expr):
            out.remove(p, base)
    if any(_unresolved_write(c, expr) for expr in writes):  # Ruling: a write to a name that cannot be followed
        read_only = c.read_only_literals()
        for index, (value, _exact) in enumerate(c.lits):
            if index not in read_only:
                out.write(value, base)
        for a in argv:
            out.write(a, base)


def _expr_targets(c: _Code, expr: str) -> List[str]:
    value = c.lit(expr)
    if value is not None:
        return [value]
    path = _PATH_CALL.fullmatch(expr.strip())
    if path:
        return [c.lits[int(path.group(1))][0]]
    return c.paths(expr)


def _unresolved_write(c: _Code, expr: str) -> bool:
    if c.lit(expr) is not None or _PATH_CALL.fullmatch(expr.strip()):
        return False
    c.unresolved = False
    c.paths(expr)
    return c.unresolved


_EFFECTS_CACHE: Dict[Tuple[str, str], _Effects] = {}


def _effects(command: str, cwd: str) -> _Effects:
    key = (command, cwd)
    if key not in _EFFECTS_CACHE:
        out = _Effects()
        _script(command, cwd, out)
        _EFFECTS_CACHE.clear()
        _EFFECTS_CACHE[key] = out
    return _EFFECTS_CACHE[key]


def shell_targets(command: str, cwd: str) -> List[str]:
    """The files a shell command (Bash or PowerShell) writes, as absolute paths: its real write targets only (see the
    notes above). Running a script (build-tokens.py, build-prototype.py) counts only its redirects: what a script
    writes itself is how generated files are meant to change. `cd DIR` moves the base for the commands after it; ~,
    $HOME, ${HOME}, %USERPROFILE% and $env:USERPROFILE are the home folder."""
    return list(_effects(command, cwd).writes)


def shell_removals(command: str, cwd: str) -> List[str]:
    """The files or folders a shell command removes or moves away (rm, del, Remove-Item, git rm, the sources of
    mv / Move-Item / git mv, and inline code's os.remove, shutil.rmtree, Path.unlink, fs.rm …), as absolute paths, read
    like shell_targets."""
    return list(_effects(command, cwd).removals)
