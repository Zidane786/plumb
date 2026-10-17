"""Plumb's previous shell reader (1.0.0 before the write-target reader), kept as the guard's floor.

pre_edit.py refuses a shell command whenever this reader would have refused it, unless _hooklib's write-target
reader proves that every guarded path the command mentions is data or a read (default deny, prove safe). Do not
change what it refuses: tests/legacy_guard.py is the frozen copy the tests compare against. Standard library only."""

from __future__ import annotations

import os
import re
from typing import Callable, List, Optional, Tuple


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


_HEREDOC_OP = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z_][\w.-]*))")
_HEREDOC_MARK = re.compile(r"<<__plumb_heredoc_(\d+)__")
_SHELLS = ("sh", "bash", "zsh", "dash", "ksh", "pwsh", "powershell")


def _heredocs(command: str) -> Tuple[str, List[str]]:
    """The command with each here-document's body taken out, and the bodies. Its << operator becomes
    <<__plumb_heredoc_N__ (N indexes the bodies), so the stage that reads it can still find its body, while the body's
    lines (a script's comments with an apostrophe, its own ; and &&) are never read as commands of the outer shell.
    Quotes are followed outside the bodies; <<< (a here-string) is not a here-document. A body whose end line is
    missing runs to the end."""
    out: List[str] = []
    bodies: List[str] = []
    pending: List[Tuple[int, str, bool]] = []  # (body index, end word, <<- strips leading tabs)
    quote = ""
    arith = 0  # inside $(( … )) or (( … )): << is a shift there, never a here-document
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            elif ch == "\\" and quote == '"' and i + 1 < n:
                out.append(command[i + 1])
                i += 1
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            out.append(command[i:i + 2])
            i += 2
            continue
        if command.startswith("$((", i) or command.startswith("((", i):
            step = 3 if ch == "$" else 2
            arith += 1
            out.append(command[i:i + step])
            i += step
            continue
        if arith and command.startswith("))", i):
            arith -= 1
            out.append("))")
            i += 2
            continue
        if (not arith and command.startswith("<<", i) and not command.startswith("<<<", i)
                and (i == 0 or command[i - 1] != "<")):
            m = _HEREDOC_OP.match(command, i)
            if m:
                word = next(g for g in m.groups()[1:] if g is not None)
                pending.append((len(bodies), word, m.group(1) == "-"))
                out.append(f"<<__plumb_heredoc_{len(bodies)}__")
                bodies.append("")
                i = m.end()
                continue
        if ch == "\n" and pending:
            out.append(ch)
            i += 1
            for index, word, strip_tabs in pending:
                lines: List[str] = []
                while i < n:
                    end = command.find("\n", i)
                    line = command[i:] if end < 0 else command[i:end]
                    i = n if end < 0 else end + 1
                    if (line.lstrip("\t") if strip_tabs else line) == word:
                        break
                    lines.append(line.lstrip("\t") if strip_tabs else line)
                bodies[index] = "\n".join(lines)
            pending = []
            continue
        out.append(ch)
        i += 1
    return "".join(out), bodies


def _body_stages(body: str) -> List[str]:
    """The pipeline stages of a shell here-document's body (`bash <<EOF ... EOF`)."""
    return [stage for part in _split(body, ("&&", "||", ";", "\n")) for stage in _split(part, ("|",))]


def _stage_heredocs(stage: str, bodies: List[str]) -> Tuple[str, List[str]]:
    """The stage without its here-document markers, and the bodies it reads."""
    mine = [bodies[int(m.group(1))] for m in _HEREDOC_MARK.finditer(stage) if int(m.group(1)) < len(bodies)]
    return _HEREDOC_MARK.sub(" ", stage), mine


_PS_SHELLS = ("pwsh", "powershell")


def _shell_c_script(stage: str) -> Optional[str]:
    """The script a shell stage runs from its command line: `bash -c "…"`, `sh -ec '…'`, `zsh -lc …`, `pwsh -c …`,
    `powershell [-NoProfile] -Command …` (the rest of the line). None for any other stage."""
    words = re.findall(_WORD, _NO_WRITE.sub(" ", stage))
    i = 0
    while i < len(words) and (re.match(r"^[A-Za-z_]\w*=", words[i]) or words[i] in ("sudo", "command", "env",
                                                                                     "nohup", "time")):
        i += 1
    if i >= len(words):
        return None
    name = _command_name(_unquote(words[i]))
    if name not in _SHELLS:
        return None
    args = words[i + 1:]
    for j, word in enumerate(args):
        flag = _unquote(word).lower()
        if name in _PS_SHELLS:
            if flag.startswith("-") and len(flag) >= 2 and "-command".startswith(flag):
                rest = [_unquote(w) for w in args[j + 1:]]
                return " ".join(rest) if rest else None
            if not flag.startswith("-"):
                return None
            continue
        if re.match(r"^-[a-z]*c[a-z]*$", flag):
            return _unquote(args[j + 1]) if j + 1 < len(args) else None
        if not flag.startswith("-") and not flag.startswith("+"):
            return None  # a script file: its contents are not on the line
    return None


def _script_stages(script: str) -> Tuple[List[str], List[str]]:
    """A -c script's pipeline stages and its here-document bodies."""
    script, bodies = _heredocs(script)
    return [stage for part in _split(script, ("&&", "||", ";", "\n")) for stage in _split(part, ("|",))], bodies


def _stage_command(stage: str) -> str:
    words = [_unquote(w) for w in re.findall(_WORD, _NO_WRITE.sub(" ", stage))]
    while words and (re.match(r"^[A-Za-z_]\w*=", words[0]) or words[0] in ("sudo", "command", "env", "nohup", "time")):
        words.pop(0)
    return _command_name(words[0]) if words else ""


def _heredoc_targets(stage: str, docs: List[str]) -> List[str]:
    """What the here-documents a stage reads write: a shell's body is read as commands (each stage of it); another
    program's body (python -, node -) that writes counts every path it names and every word of the stage line."""
    out: List[str] = []
    shell = _stage_command(stage) in _SHELLS
    for body in docs:
        if shell:
            for inner in _body_stages(body):
                out += _stage_targets(inner)
        elif _GENERIC.search(body):
            out += re.findall(r"[^\s'\"`=(),;|&<>]+", _REDIR.sub(" ", _NO_WRITE.sub(" ", stage)))
            out += re.findall(r"[^\s'\"`=(),;|&<>]+", body)
            for outer in _quoted(body):
                out += [outer] + _quoted(outer)
    return out


def _stage_targets(stage: str, bodies: Optional[List[str]] = None) -> List[str]:
    """The files one pipeline stage writes (best effort). A stage that runs a Plumb builder may write generated files
    itself; only its redirects and tee count. A here-document the stage reads is its input: a shell's body is read as
    commands; any other body (a python - script) that writes counts every path in it and on the stage line."""
    stage, docs = _stage_heredocs(stage, bodies or [])
    targets = _heredoc_targets(stage, docs) if docs else []
    cleaned = _NO_WRITE.sub(" ", stage)
    targets += [_unquote(m.group(1)) for m in _REDIR.finditer(cleaned)]
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
    script = _shell_c_script(stage)
    if script is not None:  # bash -c "…": the script's own commands
        inner, inner_bodies = _script_stages(script)
        for st in inner:
            targets += _stage_targets(st, inner_bodies)
    return targets


_REMOVERS = ("rm", "rmdir", "unlink", "del", "erase", "rd", "remove-item", "ri")
_PS_REMOVERS = ("remove-item", "ri", "del", "erase", "rd")
_MOVERS = ("mv", "move", "move-item", "mi")


def _stage_removals(stage: str, bodies: Optional[List[str]] = None) -> List[str]:
    """The files or folders one pipeline stage removes or moves away (best effort): rm, rmdir, unlink, del / erase /
    rd (cmd), Remove-Item (ri, del), git rm, and the sources of mv / move, Move-Item (mi) and git mv. A shell
    here-document's body (`bash <<EOF`) is read as commands too."""
    stage, docs = _stage_heredocs(stage, bodies or [])
    if docs and _stage_command(stage) in _SHELLS:
        return [r for body in docs for inner in _body_stages(body) for r in _stage_removals(inner)]
    script = _shell_c_script(stage)
    if script is not None:  # bash -c "…", pwsh -c …: the script's own commands
        inner, inner_bodies = _script_stages(script)
        return [r for st in inner for r in _stage_removals(st, inner_bodies)]
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


def _shell_paths(command: str, cwd: str, stage_paths: Callable[[str, List[str]], List[str]]) -> List[str]:
    out: List[str] = []
    base = cwd
    command, bodies = _heredocs(command)
    for part in _split(command, ("&&", "||", ";", "\n")):
        m = _CD.match(part)
        if m:
            target = _unquote(m.group(1))
            base = os.path.normpath(os.path.join(base, target.replace("\\", "/") if os.sep == "/" else target))
            continue
        for stage in _split(part, ("|",)):
            for t in stage_paths(stage, bodies):
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
