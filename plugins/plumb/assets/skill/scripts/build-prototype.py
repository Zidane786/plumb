#!/usr/bin/env python3
"""build-prototype.py: assemble the main prototype from one source file per screen.

Usage: build-prototype.py [--check] [--root SKILL_DIR] [--project PATH]
                          [--map ID --route=ROUTE --files GLOB [GLOB ...]] [--approve ID] [--synced ID]
       build-prototype.py --proposal NAME [--check] [--root SKILL_DIR] [--project PATH]
       build-prototype.py --check-tour FILE [--root SKILL_DIR] [--project PATH]

Reads <docs>/prototype/screens/<id>.html (docs = $extensions.plumb.docs_dir, default docs/design), the decision log
<docs>/decisions.md, the walkthroughs in <docs>/prototype/tours/ and the project's tokens, and writes these generated files:

  <docs>/prototype.html            the clickable app: a nav entry per screen, hash routing (#screen-ID, #screen-ID/STATE),
                                   a state switcher listing the screen's states, phone/desktop and light/dark toggles,
                                   each screen's own interactions, a "Why it looks like this" panel per screen, a
                                   Decisions page (#decisions), a guide-panel region (#plumb-guide) and the walkthrough
                                   player mount (#plumb-player) with the window.plumbPrototype API the player drives.
  <docs>/app.html                  the app view, for a demo: every screen full window with no prototype panels (no
                                   screens list, state switcher, toggles, decisions or player). Hash routes #/ID and
                                   #/ID/STATE (#screen-ID[/STATE] work too, so the screens' links do); it opens on the
                                   first screen by data-order, as does an unknown id. The same screen-script API
                                   (plumb.catalogue false) and window.plumbPrototype (go, setState, current, screen,
                                   setTheme, on) plus window.plumbTheme. Theme: the system's until a screen's own
                                   toggle picks one, then remembered in localStorage (when the browser allows it). The
                                   window is the frame (#pp-frame, container plumb-frame, isolation: isolate), so the md
                                   breakpoint follows the window; an element with data-app-sidebar is sticky, full
                                   height, from the md breakpoint; a dialog a change opens (a state change, plumb.go
                                   or a link to that state) is scrolled into view, one that was showing never is.
  <docs>/screens.html              the catalogue: a sidebar, every screen in every state in light and dark side by side,
                                   the control-state sheet (buttons, input, chip, link in default, hover, focus, pressed,
                                   disabled, loading) drawn from the tokens, and the Decisions page. Each copy is its
                                   own <iframe srcdoc> document, built by the page from the screen's one <template>
                                   (shared by all its copies; the page hides every outer state block but the copy's),
                                   with a <base> at the docs folder (relative images load as in prototype.html) and a
                                   CSP that allows no network, sized to its content: ids, url(#id), #id selectors,
                                   scripts and radio groups never meet another copy. The page grows with the screens,
                                   not screens × states. It needs JavaScript (a <noscript> note says so).
  <docs>/prototype/screens.json    the screen map. This script is its only writer: id, title, states, route, files
                                   (globs relative to the project root), files_hash, approved {by, at, hash, shared} | null
                                   (shared: the shared files' hashes, only when there are any), synced_from_code,
                                   status (to-build | built).

  <docs>/tours/<tour>.html          one per tour file: every screen plus that tour, opening straight into it (play
                                   mode for a client or whats-new audience, guide mode otherwise), in the tour's
                                   "view": app (the default) is the app view with the player on top, its closing card
                                   linking to prototype.html; prototype is the prototype page. It sits one folder
                                   down, so a <base href="../"> keeps links and images resolving from the docs folder.
                                   A page whose tour file is gone is removed (only pages this script generated).

Walkthroughs: <docs>/prototype/tours/<id>.json, one tour per file (id: letters, digits, _ and -, and not "<other tour>-<n>",
which reads as step n of that tour in a #tour- link). Every prototype.html carries the walkthrough player
(templates/player.js and player.css) with every tour; #tour-<id> and #tour-<id>-<n> open a tour or one of its steps.
  {"title", "audience": client|training|review|team|whats-new (default review), "view": app|prototype (default app:
   where tours/<id>.html plays it), "purpose", "speed": 0.5|1|1.5|2,
   "intro": {"title", "text", "hold"}, "closing": {...}, "chapters": [{"title", "text", "hold", "steps": [...]}] | "steps": [...]}
  step: {"screen", "state" (default: the screen's first), "title", "caption", "say" (spoken instead of the caption
         when the viewer turns the voice on in play mode; never shown), "target": SEL | "targets": [SEL, ...],
         "point": spotlight|ring|arrow|beacon|zoom|cursor|none | {"style", "label"}, "callout": {"text", "side"},
         "labels": [{"target", "text"}], "note": {"text", "x", "y"} (percent of the screen),
         "action": {"click": SEL|true} | {"type": TEXT, "target"?} | {"choose": VALUE, "target"?} | {"wait": MS},
         "your_turn": bool (guide mode waits for the learner's own click, typing or choice), "hint", "hold": MS}
  Every selector must match an element of that screen in that state (checked against the screen file's markup with a
  standard-library CSS subset: type, #id, .class, [attr op value i], descendant, >, +, ~, :first-/last-/only-child,
  :nth-child(), :nth-of-type(), :not(), :is(), :checked, :disabled, :required). A bad field, an unknown screen or state,
  a selector that matches nothing or one the check cannot read exits 2 naming the tour file, line and fix, also on --check.

The pages come from templates/prototype-shell.html.tmpl, app-shell.html.tmpl and screens.html.tmpl (the two shells
share templates/chrome-roles.css, the --pl-* roles of Plumb's own chrome; prototype.html's "Open as app" link opens
app.html#/ID[/STATE] on the screen on show). All inline the
project's `build-tokens.py --css-vars` export between /* plumb:tokens */ and /* plumb:tokens:end */, a small runtime and each
screen's scripts, so they open from disk with nothing loaded from the network. No timestamps: rebuilding gives the
same bytes.

Screen file contract (one per screen, <id>.html):
  <style> ... </style>                                    optional; selectors should start with [data-screen="ID"]
  <section data-screen="ID" data-title="Title" data-order="1">
    ... shared content shown in every state ...
    <div data-state="ready"> ... </div>                     one block per state; the first is the default
    <div data-state="loading"> ... </div>
  </section>
  <script data-screen-script> ... </script>               optional; runs once per rendered copy of the screen as
                                                          function (screen, plumb) { ... }: `screen` is the section
                                                          element; plumb.setState(name), plumb.go(id, state),
                                                          plumb.state(), plumb.catalogue (true in screens.html).
  ID is the file name without .html (letters, digits, _ and -). The md breakpoint follows the frame the screen sits in
  (phone or desktop; the window in app.html), so responsive screen CSS uses `@container plumb-frame (min-width: 48rem)`.
  data-app-sidebar on an app shell's sidebar keeps it in view in app.html (sticky, full height, from the md breakpoint).
  The _shared folder beside the screens is reserved for shared files (below); nothing in it is a screen.

Shared files: <screens folder>/_shared/*.css and *.js (the main screens/ and each variant's screens/; other files there
are not read). CSS is inlined once per page in name order, before the screens' styles (a selector that does not start
with [data-screen] is a warning). Each JS file runs for every screen (every copy in screens.html) before the screen's own
script, in name order, as function (screen, plumb) with the same API. Inlined as they are: "</script" in a JS file,
"</style" in a CSS file, fetch( / new XMLHttpRequest / WebSocket / EventSource / sendBeacon( / import, and in CSS
@import or url() with a remote or //-address exit 2. They are part of every screen's approval hash (with none it is the
screen file's own hash, so earlier approvals stand): editing one makes those approvals stale, and the build names it.
A screen file gets the same network check (its <style>, style="" and screen script), plus src / href / srcset / poster
/ data with an http(s): or // address on link, script, img, iframe, video, audio, source, object and embed: exit 2
with file:line on the build, --check, --check-tour and --proposal.

Change ids: data-guide="F01 · what changed and why" (a letter and digits, then ·) marks a changed element; the Guide
panel shows the id as a chip. A proposal lists its ids in <docs>/prototype/proposals/<NAME>/changes.md, one
`- **F01** title: what and why` line each: --proposal NAME exits 2 when a screen uses an id that is not listed (or there
is no changes.md), warns about a listed id no screen uses, and the index lists the changes. The main prototype's ids are
checked the same way only when <docs>/prototype/changes.md exists. data-guide text without a leading id is never checked.

Commands (every call rebuilds the generated files, so the pages always show the current map and approvals):
  --map ID --route=R --files G...   set a screen's route and source files; files_hash is the sha256 of those files
                                    (CRLF-normalised). status is "built" once every glob matches a file.
  --approve ID                      record the approval: git user.name (else $USER / %USERNAME%), today's ISO date,
                                    the sha256 of the screen file (CRLF-normalised; with shared files, of it and
                                    theirs); clears synced_from_code. Editing the screen (or a shared file) afterwards
                                    makes the approval stale: the build reports it. Run it only after the
                                    user said yes to that screen; every message that names it says "ask the user" first.
  --synced ID                       mark a screen as updated to match code that was already built.
  --map, --approve and --synced also refresh files_hash: the source baseline the audit compares against. A broken
                                    tour does not block them: the map is written, the pages are left as they were, and
                                    a warning names the tour problem (the next build or --check exits 2 on it).
  --check                           write nothing; exit 1 naming each stale or missing file (and a stale token block).
  --proposal NAME [--check]         build the variants of /plumb:prototype instead of the main prototype (below).
  --check-tour FILE                 validate one tour file (<docs>/prototype/tours/<id>.json, or just its id) against the
                                    screens, as the build does, and write nothing: exit 0 with an ok: line, 2 on a bad
                                    tour. It also warns (stderr, `warning:` lines, exit code unchanged) when a step's
                                    target, label or action element sits in an element the screen's own CSS hides at
                                    some frame widths: display: none, visibility: hidden or an off-canvas transform
                                    (translateX(-100%) and the like) in a top-level rule, shown again inside
                                    `@container plumb-frame (min-width: ...)` (or the reverse): "visible only when the
                                    frame is ≥ 48rem". It reads the _shared/*.css files and the screen's own styles
                                    (in the page's order): their top-level rules and @container plumb-frame blocks
                                    (min-/max-width, width, inline-size; cascade by !important, specificity and order;
                                    a descendant's own visibility: visible wins); a selector or query it cannot read
                                    is left out. The browser pass is the plugin's check-tour.py.

Proposals (/plumb:prototype's variants): <docs>/prototype/proposals/<NAME>/<variant>/screens/*.html are the variant's screen
files (the same contract) and <variant>/idea.md is optional (`# Title`, a paragraph with the idea, `- ` lines with the
trade-offs). --proposal NAME writes, per variant, <variant>/prototype.html, <variant>/app.html and
<variant>/screens.html (the same shell, app view and catalogue as the main pages, light and dark, the token block inlined, no tours, no
decisions) and <NAME>/index.html (the variants side by side with their idea, trade-offs and links: prototype.html to
review, app.html to demo, screens.html for every state) from
templates/proposal-index.html.tmpl. Variants are the folders of <NAME> (letters, digits, _ and -; a folder starting with
. or _ is skipped), in name order. All generated, byte-stable and offline; --check --proposal NAME exits 1 when one is
stale. The main build (and build-tokens.py) refreshes the token block of every generated proposal page, so old variants
keep rendering; their screen files are never touched. screens.json is not read or written.

Exit codes: 0 ok, 1 stale (--check), 2 bad input (error: ... then fix: ...). An unreadable decisions.md is a warning:
the build carries on with empty decision panels. Pages it builds over PAGE_WARN_BYTES (10 MB) are a warning too, also
on --check (one `warning: <page> is <N> MB, ...` line naming every such page, a note naming the heaviest screen files
and a fix: smaller screen files, e.g. inline data: images moved to image files, or git-ignore the pages and build in
CI); the pages are still written and the exit code does not change.

Python 3.9+, standard library only. Imports _plumb.py and build-tokens.py from its own directory.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html as _html
import importlib.util
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _plumb as P  # noqa: E402
from _plumb import PlumbError  # noqa: E402

SCRIPT_REL = "scripts/build-prototype.py"
SHELL_TEMPLATE = "prototype-shell.html.tmpl"
APP_TEMPLATE = "app-shell.html.tmpl"
CATALOGUE_TEMPLATE = "screens.html.tmpl"
INDEX_TEMPLATE = "proposal-index.html.tmpl"
PLAYER_CSS = "player.css"
PLAYER_JS = "player.js"
ROLES_CSS = "chrome-roles.css"
SCHEMA = 1
PAGE_WARN_BYTES = 10 * 1024 * 1024  # a generated page over this (10 MB) gets a size warning (size_warnings)
USAGE = ("[--check] [--map ID --route=ROUTE --files GLOB ...] [--approve ID] [--synced ID] [--proposal NAME] "
         "[--check-tour FILE] [--root SKILL_DIR] [--project PATH]")
_ID = re.compile(r"^\w[\w-]*\Z")
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_OUTSIDE_OK = frozenset(("html", "head", "body", "meta", "title"))
APPROVAL_TEXT = {"approved": "Approved", "stale": "Changed since approval", "synced": "Synced from code",
                 "none": "Not approved"}
STATUS_TEXT = {"built": "Built", "to-build": "To build", "proposal": "Variant"}


def _err(what: str, fix: str) -> PlumbError:
    return PlumbError(f"error: {what}\nfix: {fix}")


def _e(text: object) -> str:
    return _html.escape(str(text), quote=True)


def _load_build_tokens():
    path = Path(__file__).resolve().parent / "build-tokens.py"
    if not path.is_file():
        raise _err(f"{path.name} is missing next to build-prototype.py",
                   "restore the skill's scripts/ folder from the Plumb plugin (or run /plumb:upgrade)")
    spec = importlib.util.spec_from_file_location("plumb_build_tokens", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def sha256_text(text: str) -> str:
    return hashlib.sha256(P.normalise_text(text).encode("utf-8")).hexdigest()


def state_label(name: str) -> str:
    words = re.sub(r"[-_]+", " ", name).strip()
    return words[:1].upper() + words[1:]


# ---------------------------------------------------------------- screen files


class Screen:
    """One parsed screen file. `section` is the section's outer HTML (scripts and styles taken out); `marks` are the
    offsets in it where ` hidden` goes to hide the section itself (0) or one of its state blocks."""

    def __init__(self, sid: str, title: str, order: Optional[int], rel: str, text: str) -> None:
        self.id = sid
        self.title = title
        self.order = order
        self.rel = rel
        self.hash = sha256_text(text)
        self.own_hash = self.hash  # the screen file alone; hash adds the shared files (load_screens)
        self.states: List[str] = []
        self.section = ""
        self.section_mark = 0
        self.state_marks: List[Tuple[int, str]] = []
        self.styles: List[str] = []
        self.scripts: List[str] = []
        self.warnings: List[str] = []
        self.problem: Optional[PlumbError] = None  # a network load in it (check_screens raises it), as for shared files
        self._tree: Optional["_Node"] = None

    def tree(self) -> "_Node":
        """The section as an element tree (parsed once), for checking the selectors tours point at."""
        if self._tree is None:
            self._tree = parse_markup(self.section)
        return self._tree

    def render(self, state: Optional[str], hide_section: bool = False) -> str:
        """The section with every state block but `state` hidden (and the section itself, when asked)."""
        marks = [(off, name) for off, name in self.state_marks if name != state]
        if hide_section:
            marks.append((self.section_mark, ""))
        out, last = [], 0
        for off, _name in sorted(marks):
            out.append(self.section[last:off])
            out.append(" hidden")
            last = off
        out.append(self.section[last:])
        return "".join(out)


class _ScreenParser(HTMLParser):
    """Finds the data-screen section, its outermost data-state blocks, and the style and script blocks, by offset."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.text = text
        self.line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
        self.sections: List[dict] = []
        self.cur: Optional[dict] = None
        self.depth = 0
        self.state_tag: Optional[str] = None
        self.state_depth = 0
        self.raw: Optional[dict] = None  # an open <script> or <style>
        self.blocks: List[dict] = []
        self.stray: List[Tuple[int, str]] = []
        self.wrapper = 0

    def _here(self) -> Tuple[int, int]:
        line, col = self.getpos()
        return self.line_starts[line - 1] + col, line

    def handle_starttag(self, tag: str, attrs: list) -> None:
        off, line = self._here()
        a = {k: ("" if v is None else v) for k, v in attrs}
        if tag in ("script", "style"):
            self.raw = {"tag": tag, "start": off, "body": off + len(self.get_starttag_text() or ""), "attrs": a,
                        "line": line, "inside": self.cur is not None}
            return
        if self.cur is None:
            if tag == "section" and "data-screen" in a:
                self.cur = {"start": off, "line": line, "attrs": a, "tag_end": off + 1 + len(tag), "states": []}
                self.depth = 1
            elif tag in _OUTSIDE_OK:
                self.wrapper += tag == "title"
            else:
                self.stray.append((line, f"<{tag}>"))
            return
        if tag == "section":
            if "data-screen" in a:
                self.sections.append({"nested": True, "line": line, "attrs": a})
            self.depth += 1
        if self.state_tag is None and "data-state" in a:
            self.cur["states"].append((a["data-state"], off + 1 + len(tag), line))
            if tag not in _VOID:
                self.state_tag, self.state_depth = tag, 1
        elif self.state_tag == tag:
            self.state_depth += 1

    def handle_endtag(self, tag: str) -> None:
        off, line = self._here()
        if tag in ("script", "style"):
            if self.raw is not None and self.raw["tag"] == tag:
                end = self.text.find(">", off)
                self.raw.update(body_end=off, end=(end + 1) if end != -1 else len(self.text))
                self.blocks.append(self.raw)
                self.raw = None
            return
        if self.cur is None:
            if tag == "title":
                self.wrapper = max(0, self.wrapper - 1)
            return
        if self.state_tag == tag:
            self.state_depth -= 1
            if self.state_depth == 0:
                self.state_tag = None
        if tag == "section":
            self.depth -= 1
            if self.depth == 0:
                end = self.text.find(">", off)
                self.cur["end"] = (end + 1) if end != -1 else len(self.text)
                self.sections.append(self.cur)
                self.cur = None

    def handle_data(self, data: str) -> None:
        if self.cur is None and self.raw is None and not self.wrapper and data.strip():
            self.stray.append((self.getpos()[0], repr(data.strip()[:30])))


def parse_screen(path: Path, rel: str) -> Screen:
    try:
        text = P.normalise_text(P.read_project_text(path, limit=P.PAGE_READ_LIMIT))
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{rel}: cannot read the screen file ({exc})", "save it as UTF-8") from None
    parser = _ScreenParser(text)
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # noqa: BLE001 - the stdlib parser is lenient; anything it raises is bad input
        raise _err(f"{rel}: cannot parse the HTML ({exc})", "fix the markup so the file is valid HTML") from None
    stem = path.name[: -len(".html")]
    if parser.cur is not None:
        raise _err(f"{rel}:{parser.cur['line']}: the <section data-screen> is never closed", "add the closing </section>")
    if not parser.sections:
        raise _err(f"{rel}: no <section data-screen=\"{stem}\"> in the screen file",
                   f"wrap the screen in <section data-screen=\"{stem}\" data-title=\"...\"> with a <div data-state=\"ready\"> "
                   f"block per state")
    found = parser.sections[0]
    if len(parser.sections) > 1:
        other = parser.sections[1]
        raise _err(f"{rel}:{other['line']}: duplicate screen section (data-screen=\"{other['attrs'].get('data-screen')}\"; "
                   f"the first is on line {found['line']}): one file holds one screen",
                   f"move the second screen to its own file in {rel.rsplit('/', 1)[0]}/")
    sid = found["attrs"]["data-screen"].strip()
    where = f"{rel}:{found['line']}"
    if not _ID.match(sid) or not _ID.match(stem):
        bad = sid if not _ID.match(sid) else stem
        raise _err(f"{where}: screen id \"{bad}\" may only use letters, digits, _ and -",
                   "rename the file and its data-screen to an id such as booking-details")
    if sid != stem:
        raise _err(f"{where}: data-screen=\"{sid}\" does not match the file name {path.name}",
                   f"set data-screen=\"{stem}\" (or rename the file to {sid}.html)")
    if not found["states"]:
        raise _err(f"{where}: the screen has no data-state blocks",
                   "wrap each state in its own block inside the section: <div data-state=\"ready\">...</div>, "
                   "<div data-state=\"loading\">...</div>, ...")
    order_text = found["attrs"].get("data-order", "").strip()
    try:
        order = int(order_text) if order_text else None
    except ValueError:
        raise _err(f"{where}: data-order=\"{order_text}\" is not a whole number", "use data-order=\"1\", \"2\", ...") from None
    title = " ".join(found["attrs"].get("data-title", "").split()) or sid
    screen = Screen(sid, title, order, rel, text)
    for name, _off, line in found["states"]:
        if not _ID.match(name.strip()):
            raise _err(f"{rel}:{line}: data-state=\"{name}\" may only use letters, digits, _ and -",
                       "name states like ready, loading, empty, error, long-text")
        if name.strip() not in screen.states:
            screen.states.append(name.strip())
    if parser.stray:
        line, what = parser.stray[0]
        raise _err(f"{rel}:{line}: {what} is outside the screen section", "move it inside <section data-screen> (or delete it)")
    screen.problem = screen_network_load(text, parser.blocks, rel)
    start, end = found["start"], found["end"]
    cut: List[Tuple[int, int]] = []
    for blk in parser.blocks:
        if blk.get("body_end") is None:
            continue
        body = text[blk["body"]: blk["body_end"]]
        if blk["tag"] == "style":
            screen.styles.append(body.strip("\n"))
            for off, sel in unscoped_selectors(body):
                line = text.count("\n", 0, blk["body"] + off) + 1
                screen.warnings.append(f"{rel}:{line}: the style rule \"{sel}\" does not start with "
                                       f"[data-screen=\"{sid}\"], so it also styles the shell and every other screen")
        else:
            if "data-screen-script" not in blk["attrs"]:
                raise _err(f"{rel}:{blk['line']}: a <script> without data-screen-script",
                           "mark the screen's script <script data-screen-script> (it then runs once per copy of the screen, "
                           "with `screen` and `plumb` in scope)")
            if blk["attrs"].get("src"):
                raise _err(f"{rel}:{blk['line']}: <script data-screen-script src=...> loads a file",
                           "put the script inline in the screen file")
            screen.scripts.append(body.strip("\n"))
        if start <= blk["start"] < end:
            cut.append((blk["start"], blk["end"]))
    # the section's outer HTML with its script and style blocks cut out; offsets moved to match
    pieces, marks, last = [], [], start
    for a, b in sorted(cut):
        pieces.append(text[last:a])
        last = b
    pieces.append(text[last:end])
    screen.section = "".join(pieces)

    def moved(off: int) -> int:
        return off - start - sum(b - a for a, b in cut if b <= off)

    screen.section_mark = moved(found["tag_end"])
    for name, off, _line in found["states"]:
        marks.append((moved(off), name.strip()))
    screen.state_marks = marks
    return screen


# ---------------------------------------------------------------- network loads in a screen file

_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|$)", re.S)
_LOAD_TAG = re.compile(r"<(link|script|img|iframe|video|audio|source|object|embed)\b([^>]*)>", re.I)
_ANY_TAG = re.compile(r"<[a-zA-Z][\w:-]*\b([^>]*)>")
_LOAD_ATTR = re.compile(r"""\s(src|href|srcset|poster|data)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_STYLE_ATTR = re.compile(r"""\sstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_REMOTE_URL = re.compile(r"\s*(?:https?:|//)", re.I)
_CSS_LOAD_FIX = ("put the rules in this file (an @import is not inlined, and the catalogue loads nothing) and use "
                 "relative or data: URLs")
_JS_LOAD_FIX = "keep the data in the script (a constant or JSON in the file): the pages load nothing from the network"
_ATTR_LOAD_FIX = ("use a relative or data: URL (a copy of the file in the project): the pages load nothing from the "
                  "network")


def _blank(text: str, a: int, b: int) -> str:
    return text[:a] + re.sub(r"[^\n]", " ", text[a:b]) + text[b:]


def screen_network_load(text: str, blocks: List[dict], rel: str) -> Optional[PlumbError]:
    """The first thing in a screen file that loads from the network, as the refusal (exit 2, file:line) the build and
    --check raise, else None: in its <style> blocks and style="" attributes the shared CSS scan (@import, a remote or
    //-address url()), in its <script data-screen-script> the shared JS scan (fetch(, XMLHttpRequest, WebSocket, …;
    comments and string text do not count), and src / href / srcset / poster / data holding an http(s): or //
    address on link, script, img, iframe, video, audio, source, object and embed. HTML comments do not count."""
    hits: List[Tuple[int, str, str]] = []  # (offset, what, fix)
    masked = _HTML_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    for blk in blocks:
        if blk.get("body_end") is None:
            continue
        a, b = blk["body"], blk["body_end"]
        body = text[a:b]
        if blk["tag"] == "style":
            found = _CSS_REMOTE.search(_CSS_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), body))
            fix = _CSS_LOAD_FIX
        else:
            found = _JS_NETWORK.search(blank_js(body))
            fix = _JS_LOAD_FIX
        if found:
            hits.append((a + found.start(), found.group(0), fix))
        masked = _blank(masked, a, b)
    for tag in _LOAD_TAG.finditer(masked):
        for attr in _LOAD_ATTR.finditer(tag.group(2)):
            value = next(v for v in attr.groups()[1:] if v is not None)
            urls = value.split(",") if attr.group(1).lower() == "srcset" else [value]
            remote = next((u.split()[0] for u in urls if u.strip() and _REMOTE_URL.match(u)), None)
            if remote:
                hits.append((tag.start(2) + attr.start(), remote, _ATTR_LOAD_FIX))
    for tag in _ANY_TAG.finditer(masked):
        for attr in _STYLE_ATTR.finditer(tag.group(1)):
            value = attr.group(1) if attr.group(1) is not None else attr.group(2)
            found = _CSS_REMOTE.search(value)
            if found:
                hits.append((tag.start(1) + attr.start(), found.group(0), _CSS_LOAD_FIX))
    if not hits:
        return None
    off, what, fix = min(hits)
    line = text.count("\n", 0, off) + 1
    return _err(f"{rel}:{line}: \"{' '.join(what.split())}\" loads from the network; a screen file must not load "
                f"anything (the pages open offline)", fix)


def check_screens(screens: List[Screen]) -> None:
    """Refuse (exit 2) the first screen file that loads from the network (screen_network_load)."""
    for s in screens:
        if s.problem is not None:
            raise s.problem


# ---------------------------------------------------------------- screen CSS scope

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_GROUP_AT = frozenset(("media", "container", "supports", "layer", "scope", "document", "starting-style"))
_SCOPED = re.compile(r"\[\s*data-screen\s*[~|^$*]?=")


def _close_brace(css: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(css)


def unscoped_selectors(css: str) -> List[Tuple[int, str]]:
    """(offset, selector) for every style rule selector that does not start with [data-screen=...]. Rules inside
    @media, @container, @supports and @layer are checked; @keyframes, @font-face and the like are not style rules."""
    css = _CSS_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), css)
    found: List[Tuple[int, str]] = []

    def walk(pos: int, end: int) -> None:
        while pos < end:
            brace = css.find("{", pos, end)
            if brace == -1:
                return
            semi = css.rfind(";", pos, brace)
            if semi != -1:
                pos = semi + 1
            prelude = css[pos:brace]
            close = _close_brace(css, brace)
            head = prelude.strip()
            if head.startswith("@"):
                if head[1:].split(None, 1)[0].lower().split("(")[0] in _GROUP_AT:
                    walk(brace + 1, close)
            else:
                offset = pos
                for part in prelude.split(","):
                    sel = part.strip()
                    if sel and not _SCOPED.match(sel):
                        found.append((offset + len(part) - len(part.lstrip()), " ".join(sel.split())))
                    offset += len(part) + 1
            pos = close + 1

    walk(0, len(css))
    return found


def screen_files(folder: Path) -> List[Path]:
    """The screen files of a screens folder: every <id>.html file directly in it, as always (the _shared folder is a
    folder, so nothing in it is a screen)."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.html") if p.is_file())


def load_screens(folder: Path, root: Path, rel, shared: Optional[List["Shared"]] = None) -> List[Screen]:
    """The folder's screens in data-order. Each screen's hash (what an approval records) also covers the folder's
    shared files (load_shared); with none it is the screen file's own hash, as before shared files existed."""
    if shared is None:
        shared = load_shared(folder, root, rel)
    screens: List[Screen] = []
    seen: Dict[str, str] = {}
    for path in screen_files(folder):
        screen = parse_screen(path, rel(path, root))
        key = screen.id.casefold()
        if key in seen:
            raise _err(f"{screen.rel}: duplicate screen id \"{screen.id}\" (also {seen[key]})",
                       "give each screen its own id: rename one of the files and its data-screen")
        seen[key] = screen.rel
        screen.own_hash = screen.hash
        screen.hash = combined_hash(screen.own_hash, shared_hashes(shared))
        screens.append(screen)
    screens.sort(key=lambda s: (s.order if s.order is not None else 10 ** 9, s.id.casefold(), s.id))
    return screens


# ---------------------------------------------------------------- shared files (<screens>/_shared/*.css, *.js)

SHARED_DIR = "_shared"
_JS_NETWORK = re.compile(r"(?:(?<![\w$.])|(?<=window\.)|(?<=globalThis\.)|(?<=self\.))(?:fetch|importScripts)\s*\("
                         r"|\bnew\s+(?:XMLHttpRequest|WebSocket|EventSource)\b|\bsendBeacon\s*\(|(?<![\w$.])import\s*\("
                         r"|^[ \t]*import\b[^(\n]*(?:\bfrom\b|['\"])", re.M)
_CSS_REMOTE = re.compile(r"url\(\s*['\"]?\s*(?:[a-z][a-z0-9+.-]*:)?//|@import\b", re.I)
_SHARED_SCOPED = re.compile(r"\[\s*data-screen\s*(?:[~|^$*]?=|\])")


_JS_REGEX_AFTER = frozenset(("return", "typeof", "case", "in", "of", "delete", "void", "instanceof", "new", "throw",
                             "yield", "await", "else", "do"))


def blank_js(text: str) -> str:
    """The JS with every comment and the inside of every string and template literal turned to spaces (newlines and the
    quote marks kept, so offsets and lines stay): a comment or text that mentions fetch( or an import loads nothing.
    A template literal's ${...} expressions stay code. A / after an operator, ( , = : [ ! & | ? { } ; or a keyword
    such as return, typeof or case starts a regex literal, blanked like a string (a deliberately small reader: after anything else, / divides)."""
    out = list(text)
    i, n = 0, len(text)
    depth: List[int] = []  # one entry per open ${...}: the { nesting inside it

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    def regex_may_start(k: int) -> bool:
        """A / at k starts a regex literal when the code before it ends in an operator or punctuation (or nothing),
        or a keyword that takes an expression (return, typeof, case, in, of, …); after a name, a number, ) ] or a
        postfix ++ / -- it divides."""
        k -= 1
        while k >= 0 and out[k] in " \t\r\n":
            k -= 1
        if k < 0:
            return True
        if out[k] in "+-":
            return not (k > 0 and out[k - 1] == out[k])  # i++ / 2 divides
        if out[k] in "(,=:[!&|?{};*%<>~^":
            return True
        end = k + 1
        while k >= 0 and (out[k].isalnum() or out[k] in "_$"):
            k -= 1
        return text[k + 1:end] in _JS_REGEX_AFTER

    def template(j: int) -> int:
        """Blank template text from j to the closing backtick or the next ${; return where code resumes."""
        start = j
        while j < n and text[j] != "`" and not text.startswith("${", j):
            j += 2 if text[j] == "\\" else 1
        blank(start, j)
        if text.startswith("${", j):
            depth.append(0)
            return j + 2
        return j + 1

    while i < n:
        c = text[i]
        if c == "/" and text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end == -1 else end
            blank(i, end)
            i = end
        elif c == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            blank(i, end)
            i = end
        elif c == "/" and regex_may_start(i):
            j = i + 1
            in_class = False
            while j < n and text[j] != "\n" and (in_class or text[j] != "/"):
                if text[j] == "\\":
                    j += 1
                elif text[j] == "[":
                    in_class = True
                elif text[j] == "]":
                    in_class = False
                j += 1
            blank(i + 1, j)
            i = j + 1
        elif c == "`":
            i = template(i + 1)
        elif c in "'\"":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1
        elif c == "{" and depth:
            depth[-1] += 1
            i += 1
        elif c == "}" and depth:
            if depth[-1] == 0:
                depth.pop()
                i = template(i + 1)  # back in the template's text
            else:
                depth[-1] -= 1
                i += 1
        else:
            i += 1
    return "".join(out)


class Shared:
    """One shared file: `name` is its path inside the screens folder (_shared/base.css), `rel` from the project root."""

    def __init__(self, name: str, rel: str, kind: str, text: str) -> None:
        self.name, self.rel, self.kind, self.text = name, rel, kind, text.strip("\n")
        self.hash = sha256_text(text)
        self.warnings: List[str] = []
        self.problem: Optional[PlumbError] = None  # why it cannot be inlined (check_shared raises it)


def check_shared(shared: List[Shared]) -> None:
    """Refuse (exit 2) the first shared file that cannot be inlined: </script or </style in it, or a network load."""
    for s in shared:
        if s.problem is not None:
            raise s.problem


def load_shared(folder: Path, root: Path, rel) -> List[Shared]:
    """<folder>/_shared/*.css and *.js in name order (a name starting with . is skipped; other files there are not
    read). CSS goes into every page once; each JS file runs for every screen before the screen's own script. Each file
    is checked before it is inlined (`problem`, raised by check_shared): no </script or </style inside, nothing loaded
    from the network (JS comments and string text do not count). Only a file that cannot be read raises here."""
    base = folder / SHARED_DIR
    if not base.is_dir():
        return []
    out: List[Shared] = []
    for path in sorted((p for p in base.iterdir() if p.is_file() and p.suffix in (".css", ".js")
                        and not p.name.startswith(".")), key=lambda p: p.name):
        prel = rel(path, root)
        try:
            text = P.normalise_text(P.read_project_text(path, limit=P.PAGE_READ_LIMIT))
        except (OSError, UnicodeDecodeError) as exc:
            raise _err(f"{prel}: cannot read the shared file ({exc})", "save it as UTF-8") from None
        kind = path.suffix[1:]
        shared = Shared(f"{SHARED_DIR}/{path.name}", prel, kind, text)
        tag = "script" if kind == "js" else "style"
        close = re.search(rf"</{tag}", text, re.I)
        found = (_JS_NETWORK if kind == "js" else _CSS_REMOTE).search(
            blank_js(text) if kind == "js" else _CSS_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text))
        if close:
            line = text.count("\n", 0, close.start()) + 1
            shared.problem = _err(
                f"{prel}:{line}: \"</{tag}\" inside a shared {kind.upper()} file ends the page's <{tag}> block early",
                "write it as \"<\\/script\" in a string (the file is inlined as it is)" if kind == "js" else
                "remove it: a shared CSS file holds CSS rules only, inlined as they are")
        elif found:
            line = text.count("\n", 0, found.start()) + 1
            what = " ".join(found.group(0).split())
            fix = ("put the rules in this file (an @import is not inlined, and the catalogue loads nothing) and use "
                   "relative or data: URLs" if kind == "css" else
                   "keep the data in the script (a constant or JSON in the file): the pages load nothing from the network")
            shared.problem = _err(f"{prel}:{line}: \"{what}\" loads from the network or another file; a shared file "
                                  f"must not", fix)
        if kind == "css":
            for off, sel in unscoped_selectors(text):
                if not _SHARED_SCOPED.match(sel):
                    line = text.count("\n", 0, off) + 1
                    shared.warnings.append(f"{prel}:{line}: the style rule \"{sel}\" does not start with [data-screen], "
                                           f"so it also styles the prototype's own panels")
        out.append(shared)
    return out


def shared_warning_lines(shared: List[Shared]) -> List[str]:
    """The unscoped-selector warnings of the shared CSS files (at most five per file), each file with its fix."""
    out: List[str] = []
    for s in shared:
        out += [f"warning: {w}" for w in s.warnings[:5]]
        if len(s.warnings) > 5:
            out.append(f"warning: {s.rel}: {len(s.warnings) - 5} more style rules like these")
        if s.warnings:
            out.append(f"fix: start each selector in {s.rel} with [data-screen] (every screen) or "
                       f"[data-screen=\"<id>\"] (one screen)")
    return out


def shared_hashes(shared: List[Shared]) -> List[Tuple[str, str]]:
    return [(s.name, s.hash) for s in shared]


def combined_hash(own: str, shared: List[Tuple[str, str]]) -> str:
    """What an approval records: the screen file's hash, and with shared files the hash of it and theirs (name order)."""
    if not shared:
        return own
    return sha256_text(own + "\n" + "".join(f"{name} {digest}\n" for name, digest in sorted(shared)))


def screen_file_hash(path: Path) -> str:
    """The approval hash of one screen file, from its text and its folder's shared files (read, not checked): what the
    edit hook compares an approval with. Raises OSError / UnicodeDecodeError when a file cannot be read."""
    own = sha256_text(P.read_project_text(path, limit=P.PAGE_READ_LIMIT))
    base = path.parent / SHARED_DIR
    pairs = []
    if base.is_dir():
        for p in base.iterdir():
            if p.is_file() and p.suffix in (".css", ".js") and not p.name.startswith("."):
                pairs.append((f"{SHARED_DIR}/{p.name}", sha256_text(P.read_project_text(p, limit=P.PAGE_READ_LIMIT))))
    return combined_hash(own, pairs)


def stale_reason(entry: dict, screen: Screen, shared: List[Shared], folder_rel: str) -> str:
    """Why an approval went stale, when shared files are part of it: the shared files added, changed or removed since,
    and whether the screen file changed too. "" when only the screen file changed (or nothing can be said)."""
    approved = entry.get("approved") or {}
    recorded = approved.get("shared") if isinstance(approved.get("shared"), dict) else {}
    recorded = {str(k): str(v) for k, v in recorded.items()}
    now = dict(shared_hashes(shared))
    moved = []
    for name in sorted(set(recorded) | set(now)):
        if name not in now:
            moved.append(f"{folder_rel}{name} was removed")
        elif name not in recorded:
            moved.append(f"{folder_rel}{name} was added")
        elif recorded[name] != now[name]:
            moved.append(f"{folder_rel}{name} changed")
    if not moved:
        return ""
    own_too = combined_hash(screen.own_hash, sorted(recorded.items())) != approved.get("hash")
    return (f" (the shared {'files' if len(moved) > 1 else 'file'}: {'; '.join(moved)}; shared files reach every "
            f"screen{'; the screen file changed too' if own_too else ''})")


# ---------------------------------------------------------------- change ids (data-guide="F01 · ..." + changes.md)

_CHANGE_ID = re.compile(r"^\s*([A-Za-z]\d+)\s*·")
_CHANGE_LINE = re.compile(r"^[-*]\s+\*\*([A-Za-z]\d+)\*\*\s*(.*?)\s*$")
CHANGE_LINE_FORMAT = "- **F01** title: what changed and why"


def change_id(text: str) -> Optional[str]:
    """The change id a data-guide text starts with ("F01 · what changed and why": a letter and digits, then ·)."""
    m = _CHANGE_ID.match(text or "")
    return m.group(1) if m else None


def guide_ids(screen: Screen) -> List[str]:
    """The change ids the screen's data-guide texts start with, in document order, each once."""
    out: List[str] = []
    for node in screen.tree().walk():
        cid = change_id(node.attrs.get("data-guide", ""))
        if cid and cid not in out:
            out.append(cid)
    return out


def read_changes(path: Path, root: Path, rel) -> Optional[List[dict]]:
    """changes.md: one `- **F01** title: what and why` line per change, as [{id, title, why}]; other lines are free
    text. None when the file does not exist."""
    if not path.is_file():
        return None
    prel = rel(path, root)
    try:
        text = P.normalise_text(P.read_project_text(path))
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{prel}: cannot read the change list ({exc})", "save it as UTF-8") from None
    out: List[dict] = []
    lines: Dict[str, int] = {}
    for n, raw in enumerate(text.split("\n"), 1):
        m = _CHANGE_LINE.match(raw.strip())
        if not m:
            continue
        cid, rest = m.group(1), m.group(2).lstrip(":·—–- ").strip()
        if cid in lines:
            raise _err(f"{prel}:{n}: change id {cid} is listed twice (also line {lines[cid]})",
                       f"give each change its own id (a letter and digits), one line each: {CHANGE_LINE_FORMAT}")
        lines[cid] = n
        title, _sep, why = rest.partition(": ")
        out.append({"id": cid, "title": title.strip().rstrip(":"), "why": why.strip()})
    return out


def check_change_ids(screens: List[Screen], changes: Optional[List[dict]], changes_rel: str, again: str,
                     scope: str) -> List[str]:
    """Every change id a screen's data-guide uses must be listed in changes.md (exit 2 naming the screen, the id and the
    fix); a listed id no screen uses is a warning (returned). data-guide text without an id is not checked."""
    listed = {c["id"] for c in changes or []}
    used: Dict[str, List[str]] = {}
    for s in screens:
        for cid in guide_ids(s):
            used.setdefault(cid, []).append(s.rel)
    unknown = sorted((r, cid) for cid, rels in used.items() if cid not in listed for r in rels)
    if unknown:
        where = ", ".join(f"{r} uses {cid}" for r, cid in unknown)
        missing = " (no such file)" if changes is None else ""
        raise _err(f"change id{'s' if len(unknown) > 1 else ''} not listed in {changes_rel}{missing}: {where}",
                   f"add one line per change to {changes_rel}, e.g. \"- **{unknown[0][1]}** title: what changed and "
                   f"why\" (or correct the id in the screen file's data-guide), then run {again}")
    return [f"warning: {changes_rel}: {c['id']} is listed but no screen of {scope} uses it\n"
            f"fix: mark the changed element data-guide=\"{c['id']} · what changed and why\" in its screen file, or "
            f"remove the line" for c in changes or [] if c["id"] not in used]


# ---------------------------------------------------------------- decisions.md

_DS_HEAD = re.compile(r"^##\s+(DS-(\d{4})(\d{2})(\d{2})-[\w.-]+)\s*(?:[·:—–|-]+\s*(.*?))?\s*$")
_FIELD = re.compile(r"^[-*]\s+([A-Za-z][A-Za-z /()-]*?):\s*(.*)$")
_SUB = re.compile(r"^\s+(?:[-*]\s+)?(.*\S)\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?=[^\s*])([^*]+?)(?<=\S)\*(?![*\w])")
_PLACEHOLDER = re.compile("\x00(\\d+)\x00")
_UNSAFE_URL = re.compile(r"^\s*(?:javascript|data|vbscript):", re.I)
WHO_KEYS = ("decided by", "who", "by")


def parse_decisions(text: str) -> List[dict]:
    """`## DS-YYYYMMDD-slug · title` entries with their `- Key: value` lines (indented lines continue the last one)."""
    entries: List[dict] = []
    cur: Optional[dict] = None
    for raw in P.normalise_text(text).split("\n"):
        line = raw.rstrip()
        head = _DS_HEAD.match(line)
        if head:
            cur = {"id": head.group(1), "title": (head.group(5) or "").strip() or head.group(1),
                   "id_date": f"{head.group(2)}-{head.group(3)}-{head.group(4)}", "fields": [], "notes": [],
                   "pos": len(entries)}
            entries.append(cur)
            continue
        if line.startswith("#"):
            cur = None
            continue
        if cur is None or not line.strip():
            continue
        field = _FIELD.match(line)
        if field:
            cur["fields"].append([field.group(1).strip(), field.group(2).strip(), []])
            continue
        sub = _SUB.match(line)
        if sub and cur["fields"] and raw[:1] in (" ", "\t"):
            cur["fields"][-1][2].append(sub.group(1))
            continue
        cur["notes"].append(line.strip())
    for e in entries:
        fields = {k.lower(): (v, subs) for k, v, subs in e["fields"]}
        e["date"] = fields.get("date", (e["id_date"], []))[0] or e["id_date"]
        e["by"] = next((fields[k][0] for k in WHO_KEYS if k in fields and fields[k][0]), "")
        names = fields.get("screens", ("", []))
        tokens = [t.strip("`'\" ") for t in re.split(r"[,\s]+", " ".join([names[0], *names[1]])) if t.strip("`'\" ")]
        e["all"] = any(t.lower() in ("all", "*") for t in tokens)
        e["screens"] = [t for t in tokens if t.lower() not in ("all", "*")]
    entries.sort(key=lambda e: (e["id_date"], e["pos"]), reverse=True)
    return entries


def inline(text: str) -> str:
    """Escaped text with `code`, **bold**, *italic* and [links](url); script URLs stay plain text.

    Code spans become placeholders first, so their content is never read as markup. Links come next: a label may hold a
    code span (restored as <code> later); an href holding one gets the literal backtick text back, never markup. Then
    bold and italic (which may span a code span), and last the placeholders turn into <code>."""
    codes: List[str] = []

    def stash(m: "re.Match[str]") -> str:
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    def literal(fragment: str) -> str:
        return _PLACEHOLDER.sub(lambda m: f"`{codes[int(m.group(1))]}`", fragment)

    def link(m: "re.Match[str]") -> str:
        url = literal(_html.unescape(m.group(2)))
        if _UNSAFE_URL.match(url):
            return m.group(0)
        return f'<a href="{_e(url)}">{m.group(1)}</a>'

    out = _e(_CODE.sub(stash, text.replace("\x00", "")))
    out = _LINK.sub(link, out)
    out = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", out)
    return _PLACEHOLDER.sub(lambda m: f"<code>{_e(codes[int(m.group(1))])}</code>", out)


def decision_applies(entry: dict, sid: str) -> bool:
    return entry["all"] or any(s.casefold() == sid.casefold() for s in entry["screens"])


# ---------------------------------------------------------------- source files (--map, status)


def safe_glob(glob: str, where: str = "") -> str:
    """A glob relative to the project root; an absolute path, a drive or `..` is refused (never walked)."""
    g = glob.strip().strip("`").replace("\\", "/")
    while g.startswith("./"):
        g = g[2:]
    bad = (not g or g.startswith("/") or re.match(r"^[A-Za-z]:", g) is not None or ".." in g.split("/"))
    if bad and where:
        raise _err(f"{where} has the source glob \"{glob}\", which is not a path inside the project",
                   "re-map the screen with globs relative to the project root: build-prototype.py --map ID --route=R "
                   "--files \"app/billing/**\" (or restore the file with git)")
    if bad:
        raise _err(f"--files \"{glob}\" is not a path inside the project",
                   "write globs relative to the project root, e.g. --files \"app/billing/**\" components/billing-form.tsx")
    return g


def glob_files(root: Path, glob: str) -> List[str]:
    """Project-relative files matching the glob (** any folders, * within one; no wildcard = that path and below)."""
    parts = glob.split("/")
    base: List[str] = []
    for part in parts:
        if any(c in part for c in "*?[{"):
            break
        base.append(part)
    rx = P.glob_rx(glob)
    start = root.joinpath(*base) if base else root
    if start.is_file():
        return [glob] if rx.match(glob) else []
    if not start.is_dir():
        return []
    found = []
    for folder, dirs, files in os.walk(start):
        dirs[:] = sorted(d for d in dirs if d not in P.SKIP_DIRS)
        for name in files:
            relp = Path(folder, name).relative_to(root).as_posix()
            if rx.match(relp):
                found.append(relp)
    return sorted(found)


def files_status(root: Path, globs: List[str]) -> str:
    """"built" once every glob matches a file, else "to-build"."""
    return "built" if globs and all(glob_files(root, g) for g in globs) else "to-build"


def files_state(root: Path, globs: List[str]) -> Tuple[Optional[str], str]:
    """(sha256 over the matched files, CRLF-normalised | None when nothing matches, status)."""
    matched = {g: glob_files(root, g) for g in globs}
    status = "built" if globs and all(matched.values()) else "to-build"
    paths = sorted({p for found in matched.values() for p in found})
    if not paths:
        return None, status
    h = hashlib.sha256()
    for relp in paths:
        try:
            data = P.read_project_bytes(root / relp, P.PAGE_READ_LIMIT)
        except OSError:
            continue
        try:
            data = P.normalise_text(data.decode("utf-8")).encode("utf-8")
        except UnicodeDecodeError:
            pass
        h.update(relp.encode("utf-8") + b"\0" + data + b"\0")
    return h.hexdigest(), status


def approver(root: Path) -> str:
    try:
        r = subprocess.run(["git", "config", "user.name"], cwd=str(root), capture_output=True, text=True,
                           encoding="utf-8", timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    for var in ("USER", "USERNAME"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return "unknown"


def approval_state(entry: dict, screen: Screen) -> str:
    if entry.get("synced_from_code"):
        return "synced"
    approved = entry.get("approved")
    if isinstance(approved, dict):
        return "approved" if approved.get("hash") == screen.hash else "stale"
    return "none"


# ---------------------------------------------------------------- the map (screens.json)


def read_map(path: Path, rel_path: str) -> Dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(P.read_project_text(path, limit=P.PAGE_READ_LIMIT))
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{rel_path}: cannot read the screen map ({exc})", "restore it with git (git checkout -- "
                   f"{rel_path}); only build-prototype.py writes it") from None
    except json.JSONDecodeError as exc:
        raise _err(f"{rel_path}:{exc.lineno}: the screen map is not valid JSON ({exc.msg})",
                   f"restore it with git (git checkout -- {rel_path}); only build-prototype.py writes it") from None
    screens = data.get("screens") if isinstance(data, dict) else None
    if not isinstance(screens, list):
        raise _err(f"{rel_path}: the screen map has no \"screens\" list",
                   f"restore it with git (git checkout -- {rel_path}); only build-prototype.py writes it")
    return {s["id"]: s for s in screens if isinstance(s, dict) and isinstance(s.get("id"), str)}


def map_entry(screen: Screen, old: Optional[dict], root: Path, map_rel: str = "screens.json") -> dict:
    old = old or {}
    where = f"{map_rel} (screen {screen.id})"
    files = [safe_glob(f, where) for f in old.get("files") or [] if isinstance(f, str)]
    approved = old.get("approved")
    if isinstance(approved, dict):
        shared = approved.get("shared")
        approved = {"by": str(approved.get("by", "")), "at": str(approved.get("at", "")), "hash": str(approved.get("hash", ""))}
        if isinstance(shared, dict) and shared:  # the shared files the approval saw (only when there were any)
            approved["shared"] = {str(k): str(v) for k, v in sorted(shared.items())}
    else:
        approved = None
    status = files_status(root, files)
    route = old.get("route")
    files_hash = old.get("files_hash")
    return {
        "id": screen.id,
        "title": screen.title,
        "states": list(screen.states),
        "route": route if isinstance(route, str) else None,
        "files": files,
        "files_hash": files_hash if isinstance(files_hash, str) else None,
        "approved": approved,
        "synced_from_code": bool(old.get("synced_from_code", False)),
        "status": status,
    }


def map_text(entries: List[dict], header: str) -> str:
    return json.dumps({"$generated": header, "version": SCHEMA, "screens": entries}, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- screen markup as a tree (for the tour target check)


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: Dict[str, str], parent: Optional["_Node"]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: List["_Node"] = []
        self.parent = parent

    def walk(self):
        for child in self.children:
            yield child
            yield from child.walk()


_BLOCKS_CLOSE_P = frozenset("address article aside blockquote details dialog div dl fieldset figcaption figure footer form "
                            "h1 h2 h3 h4 h5 h6 header hgroup hr main menu nav ol p pre section table ul".split())
_IMPLIED_END = {"li": ("li",), "dt": ("dt", "dd"), "dd": ("dt", "dd"), "option": ("option",), "tr": ("tr", "td", "th"),
                "td": ("td", "th"), "th": ("td", "th")}


class _TreeBuilder(HTMLParser):
    """A forgiving element tree: void elements never open, a few implied end tags close (li, p, dt/dd, option, td)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {}, None)
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list) -> None:
        closes = _IMPLIED_END.get(tag, ())
        while len(self.stack) > 1 and self.stack[-1].tag in closes:
            self.stack.pop()
        if tag in _BLOCKS_CLOSE_P and len(self.stack) > 1 and self.stack[-1].tag == "p":
            self.stack.pop()
        node = _Node(tag, {k: ("" if v is None else v) for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return


def parse_markup(text: str) -> _Node:
    builder = _TreeBuilder()
    builder.feed(text)
    builder.close()
    return builder.root


# ---------------------------------------------------------------- CSS selectors (the subset a tour may use)


class SelectorError(Exception):
    """A selector the check cannot read (`unsupported` names the part it cannot check, e.g. ":hover")."""

    def __init__(self, message: str, unsupported: str = "") -> None:
        super().__init__(message)
        self.unsupported = unsupported


_SIMPLE = re.compile(r"""
    (?P<type>\*|[A-Za-z][\w-]*)
  | \#(?P<id>(?:[\w-]|\\.)+)
  | \.(?P<cls>(?:[\w-]|\\.)+)
  | \[\s*(?P<attr>[\w:-]+)\s*(?:(?P<op>[~|^$*]?=)\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<uq>(?:[\w-]|\\.)+))
        \s*(?:(?P<flag>[iIsS])\s*)?)?\]
  | ::(?P<element>[\w-]+)
  | :(?P<pseudo>[\w-]+)(?:\((?P<arg>(?:[^()"']|"[^"]*"|'[^']*'|\([^()]*\))*)\))?
""", re.X)
_NTH = re.compile(r"^\s*(?:(?P<odd>odd)|(?P<even>even)|(?P<b0>[+-]?\d+)|(?P<a>[+-]?\d*)n\s*(?:(?P<sign>[+-])\s*(?P<b>\d+))?)\s*$",
                  re.I)
_STRUCTURAL = ("first-child", "last-child", "only-child", "first-of-type", "last-of-type", "only-of-type")
_NTH_PSEUDO = ("nth-child", "nth-last-child", "nth-of-type", "nth-last-of-type")
_LIST_PSEUDO = ("not", "is", "where")
_STATE_PSEUDO = ("checked", "disabled", "enabled", "required", "optional")
_FORM_CONTROLS = frozenset(("button", "input", "select", "textarea", "option", "optgroup", "fieldset"))


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def _split_top(text: str) -> List[str]:
    """Split on commas outside brackets, parentheses and quotes."""
    parts, depth, quote, cur = [], 0, "", []
    for ch in text:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def _nth(arg: str) -> Tuple[int, int]:
    m = _NTH.match(arg or "")
    if not m:
        raise SelectorError(f"\"{arg}\" is not an nth formula (use a number, odd, even or An+B)")
    if m.group("odd"):
        return 2, 1
    if m.group("even"):
        return 2, 0
    if m.group("b0") is not None:
        return 0, int(m.group("b0"))
    a_text = m.group("a")
    a = -1 if a_text == "-" else 1 if a_text in ("", "+") else int(a_text)
    b = int(m.group("b") or 0) * (-1 if m.group("sign") == "-" else 1)
    return a, b


def _parse_compound(text: str, i: int) -> Tuple[dict, int]:
    comp: dict = {"tag": None, "ids": [], "classes": [], "attrs": [], "pseudos": []}
    start = i
    while i < len(text):
        m = _SIMPLE.match(text, i)
        if not m:
            break
        if m.group("type"):
            if i != start:
                raise SelectorError(f"the element name \"{m.group('type')}\" must come first in \"{text[start:m.end()]}\"")
            comp["tag"] = m.group("type").lower()
        elif m.group("id"):
            comp["ids"].append(_unescape(m.group("id")))
        elif m.group("cls"):
            comp["classes"].append(_unescape(m.group("cls")))
        elif m.group("attr"):
            value = next((m.group(g) for g in ("dq", "sq", "uq") if m.group(g) is not None), None)
            comp["attrs"].append((m.group("attr").lower(), m.group("op"), _unescape(value) if value is not None else None,
                                  (m.group("flag") or "").lower() == "i"))
        elif m.group("element"):
            raise SelectorError(f"the pseudo-element ::{m.group('element')} is not an element on the screen",
                                f"::{m.group('element')}")
        else:
            name, arg = m.group("pseudo").lower(), m.group("arg")
            if name in _STRUCTURAL or name in _STATE_PSEUDO:
                if arg is not None:
                    raise SelectorError(f":{name} takes no argument")
                comp["pseudos"].append((name, None))
            elif name in _NTH_PSEUDO:
                comp["pseudos"].append((name, _nth(arg)))
            elif name in _LIST_PSEUDO:
                if not (arg or "").strip():
                    raise SelectorError(f":{name}() needs a selector")
                comp["pseudos"].append((name, parse_selector(arg)))
            else:
                raise SelectorError(f"it uses :{name}", f":{name}")
        i = m.end()
    if i == start:
        what = repr(text[i]) if i < len(text) else "the end"
        raise SelectorError(f"unexpected {what} at position {i + 1}")
    return comp, i


def _parse_complex(text: str) -> List[Tuple[Optional[str], dict]]:
    text = text.strip()
    if not text:
        raise SelectorError("it is empty")
    parts: List[Tuple[Optional[str], dict]] = []
    comb: Optional[str] = None
    i, n = 0, len(text)
    while True:
        comp, i = _parse_compound(text, i)
        parts.append((comb, comp))
        j = i
        while j < n and text[j].isspace():
            j += 1
        if j >= n:
            return parts
        if text[j] in ">+~":
            comb = text[j]
            j += 1
            while j < n and text[j].isspace():
                j += 1
            if j >= n:
                raise SelectorError(f"it ends with the combinator \"{comb}\"")
        elif j > i:
            comb = " "
        else:
            raise SelectorError(f"unexpected {text[j]!r} at position {j + 1}")
        i = j


def parse_selector(text: str) -> List[List[Tuple[Optional[str], dict]]]:
    if not isinstance(text, str) or not text.strip():
        raise SelectorError("it is empty")
    return [_parse_complex(part) for part in _split_top(text)]


def _elements(node: Optional[_Node]) -> List[_Node]:
    return [c for c in node.children] if node is not None else []


def _attr_ok(node: _Node, name: str, op: Optional[str], value: Optional[str], fold: bool) -> bool:
    if name not in node.attrs:
        return False
    if op is None:
        return True
    have, want = node.attrs[name], value or ""
    if fold:
        have, want = have.casefold(), want.casefold()
    if op == "=":
        return have == want
    if op == "~=":
        return bool(want) and want in have.split()
    if op == "|=":
        return have == want or have.startswith(want + "-")
    if not want:
        return False
    return {"^=": have.startswith, "$=": have.endswith, "*=": have.__contains__}[op](want)


def _nth_ok(index: int, ab: Tuple[int, int]) -> bool:
    a, b = ab
    if a == 0:
        return index == b
    return (index - b) % a == 0 and (index - b) // a >= 0


def _pseudo_ok(node: _Node, name: str, arg) -> bool:
    siblings = _elements(node.parent)
    if name in _LIST_PSEUDO:
        hit = any(_complex_ok(node, parts, len(parts) - 1) for parts in arg)
        return not hit if name == "not" else hit
    if name == "checked":
        return ("checked" in node.attrs and node.tag == "input") or ("selected" in node.attrs and node.tag == "option")
    if name in ("disabled", "enabled"):
        if node.tag not in _FORM_CONTROLS:
            return False
        return ("disabled" in node.attrs) == (name == "disabled")
    if name in ("required", "optional"):
        if node.tag not in ("input", "select", "textarea"):
            return False
        return ("required" in node.attrs) == (name == "required")
    same = [s for s in siblings if s.tag == node.tag]
    pool = same if "of-type" in name else siblings
    pos = pool.index(node) + 1
    last = len(pool) - pos + 1
    if name in ("first-child", "first-of-type"):
        return pos == 1
    if name in ("last-child", "last-of-type"):
        return last == 1
    if name in ("only-child", "only-of-type"):
        return len(pool) == 1
    return _nth_ok(last if "last" in name else pos, arg)


def _compound_ok(node: _Node, comp: dict) -> bool:
    if node.tag == "#root":
        return False
    if comp["tag"] not in (None, "*") and node.tag != comp["tag"]:
        return False
    if any(node.attrs.get("id") != i for i in comp["ids"]):
        return False
    classes = node.attrs.get("class", "").split()
    if any(c not in classes for c in comp["classes"]):
        return False
    if not all(_attr_ok(node, *a) for a in comp["attrs"]):
        return False
    return all(_pseudo_ok(node, name, arg) for name, arg in comp["pseudos"])


def _complex_ok(node: _Node, parts: List[Tuple[Optional[str], dict]], idx: int) -> bool:
    comb, comp = parts[idx]
    if not _compound_ok(node, comp):
        return False
    if idx == 0:
        return True
    if comb in (" ", ">"):
        parent = node.parent
        while parent is not None and parent.tag != "#root":
            if _complex_ok(parent, parts, idx - 1):
                return True
            if comb == ">":
                return False
            parent = parent.parent
        return False
    siblings = _elements(node.parent)
    before = siblings[: siblings.index(node)]
    if comb == "+":
        return bool(before) and _complex_ok(before[-1], parts, idx - 1)
    return any(_complex_ok(s, parts, idx - 1) for s in before)


def select(tree: _Node, selector: str, state: str) -> List[_Node]:
    """The elements of the screen section matching `selector` that show in `state`, as section.querySelectorAll would
    find them (the section itself takes part in combinators but is not a result). Raises SelectorError."""
    parsed = parse_selector(selector)
    section = next((n for n in tree.walk() if "data-screen" in n.attrs), None)
    if section is None:
        return []
    found, stack = [], list(reversed(section.children))
    while stack:
        node = stack.pop()
        name = node.attrs.get("data-state")
        if name is not None and name.strip() != state and _outer_state(node, section):
            continue
        if any(_complex_ok(node, parts, len(parts) - 1) for parts in parsed):
            found.append(node)
        stack.extend(reversed(node.children))
    return found


def _outer_state(node: _Node, section: _Node) -> bool:
    """True when no [data-state] or [data-screen] sits between this element and the section (an outer state block)."""
    parent = node.parent
    while parent is not None and parent is not section:
        if "data-state" in parent.attrs or "data-screen" in parent.attrs:
            return False
        parent = parent.parent
    return parent is section


# ---------------------------------------------------------------- tour files (<docs>/prototype/tours/<id>.json)

AUDIENCES = ("client", "training", "review", "team", "whats-new")
PLAY_AUDIENCES = ("client", "whats-new")
SPEEDS = (0.5, 1, 1.5, 2)
POINTS = ("spotlight", "ring", "arrow", "beacon", "zoom", "cursor", "none")
SIDES = ("top", "right", "bottom", "left")
ACTIONS = ("click", "type", "choose", "wait")
MAX_MS = 60000
TOUR_FIELDS = ("title", "audience", "view", "purpose", "speed", "intro", "closing", "chapters", "steps")
VIEWS = ("app", "prototype")
CARD_FIELDS = ("title", "text", "hold")
CHAPTER_FIELDS = ("title", "text", "hold", "steps")
STEP_FIELDS = ("screen", "state", "title", "caption", "say", "target", "targets", "point", "callout", "labels", "note", "action",
               "your_turn", "hint", "hold")
TOUR_FIX = "see the tour format in the design-system skill's references (or run /plumb:tour <flow> to rewrite it)"


def json_lines(text: str) -> Dict[tuple, int]:
    """{path: line} for every value in a valid JSON document; a path is a tuple of keys and list indexes."""
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    lines: Dict[tuple, int] = {}
    n = len(text)

    def line_at(i: int) -> int:
        lo, hi = 0, len(starts)
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if starts[mid] <= i:
                lo = mid
            else:
                hi = mid
        return lo + 1

    def ws(i: int) -> int:
        while i < n and text[i] in " \t\r\n":
            i += 1
        return i

    def string_end(i: int) -> int:
        i += 1
        while i < n:
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == '"':
                return i + 1
            i += 1
        return n

    def value(i: int, path: tuple) -> int:
        i = ws(i)
        lines[path] = line_at(i)
        ch = text[i] if i < n else ""
        if ch in "{[":
            close, index = ("}" if ch == "{" else "]"), 0
            i = ws(i + 1)
            if i < n and text[i] == close:
                return i + 1
            while i < n:
                i = ws(i)
                if ch == "{":
                    end = string_end(i)
                    key = json.loads(text[i:end])
                    i = ws(end) + 1  # the colon
                    i = value(i, path + (key,))
                else:
                    i = value(i, path + (index,))
                    index += 1
                i = ws(i)
                if i < n and text[i] == ",":
                    i += 1
                    continue
                return i + 1
            return n
        if ch == '"':
            return string_end(i)
        m = re.compile(r"[^\s,\]}]*").match(text, i)
        return m.end() if m else i + 1

    try:
        value(0, ())
    except (IndexError, ValueError):
        pass
    return lines


def _path_text(path: tuple) -> str:
    out = ""
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out


def _show(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


class _TourReader:
    """Validates one tour file against the screens and normalises it for the player."""

    def __init__(self, tid: str, rel: str, text: str, screens: Dict[str, Screen], screens_rel: str) -> None:
        self.id, self.rel, self.text = tid, rel, text
        self.screens, self.screens_rel = screens, screens_rel
        self.lines: Dict[tuple, int] = {}
        self.raw_steps: List[Tuple[tuple, dict]] = []

    def fail(self, path: tuple, what: str, fix: str) -> PlumbError:
        line = None
        for cut in range(len(path), -1, -1):
            line = self.lines.get(path[:cut])
            if line is not None:
                break
        where = f"{self.rel}:{line}" if line is not None else self.rel
        return _err(f"{where}: {what}", fix)

    def known(self, obj: dict, path: tuple, allowed: Tuple[str, ...], name: str) -> None:
        for key in obj:
            if key.startswith("$"):
                continue
            if key not in allowed:
                raise self.fail(path + (key,), f"{name} has an unknown field {_show(key)}",
                                f"use only {', '.join(allowed)} (or remove it)")

    def text_field(self, obj: dict, key: str, path: tuple, name: str, required: bool = False) -> str:
        value = obj.get(key)
        if value is None:
            if required:
                raise self.fail(path, f"{name} has no {_show(key)}", f"add {_show(key)}: \"...\" to {name}")
            return ""
        if not isinstance(value, str):
            raise self.fail(path + (key,), f"{_label(path + (key,))} must be text", f"write it in quotes: {_show(key)}: \"...\"")
        if required and not value.strip():
            raise self.fail(path + (key,), f"{name}: {_show(key)} is empty", f"write the {key} of {name}")
        return " ".join(value.split()) if key == "title" else value.strip()

    def ms(self, obj: dict, key: str, path: tuple) -> Optional[int]:
        value = obj.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not 0 <= value <= MAX_MS:
            raise self.fail(path + (key,), f"{_label(path + (key,))} {_show(value)} must be a whole number of milliseconds "
                                           f"from 0 to {MAX_MS}", f"set {_show(key)}: 1500 (milliseconds at 1x speed)")
        return int(value)

    def obj(self, value: object, path: tuple, shape: str) -> dict:
        if not isinstance(value, dict):
            raise self.fail(path, f"{_label(path)} must be an object like {shape}", f"write it as {shape}")
        return value

    def selector(self, sel: object, path: tuple, screen: Screen, state: str) -> str:
        label = _label(path)
        if not isinstance(sel, str) or not sel.strip():
            raise self.fail(path, f"{label} must be a CSS selector in quotes", "write it like \"[data-tour=save]\" or \".save\"")
        sel = sel.strip()
        tree = screen.tree()
        try:
            found = select(tree, sel, state)
        except SelectorError as exc:
            if exc.unsupported:
                raise self.fail(path, f"{label} {_show(sel)} uses {exc.unsupported}, which build-prototype.py cannot check "
                                      f"against the screen file",
                                "point at the element with a class or data attribute, e.g. [data-tour=save]") from None
            raise self.fail(path, f"{label} {_show(sel)} is not a CSS selector build-prototype.py can read ({exc})",
                            "write a selector such as [data-tour=save], .save or form > button") from None
        if not found:
            raise self.fail(path, f"{label} {_show(sel)} matches nothing in {screen.rel} (state {state})",
                            f"point it at an element of screen {screen.id} in state {state} (a class or data attribute "
                            f"such as [data-tour=save]), or add the element to {screen.rel}")
        return sel

    def card(self, value: object, path: tuple) -> Optional[dict]:
        if value is None:
            return None
        name = _label(path)
        card = self.obj(value, path, '{"title": "...", "text": "..."}')
        self.known(card, path, CARD_FIELDS, name)
        return {"title": self.text_field(card, "title", path, name, True), "text": self.text_field(card, "text", path, name),
                "hold": self.ms(card, "hold", path)}

    def read(self) -> dict:
        try:
            doc = json.loads(self.text)
        except json.JSONDecodeError as exc:
            raise _err(f"{self.rel}:{exc.lineno}: the tour is not valid JSON ({exc.msg})",
                       f"fix the JSON in {self.rel} (a missing comma or bracket near line {exc.lineno})") from None
        self.lines = json_lines(self.text)
        if not isinstance(doc, dict):
            raise _err(f"{self.rel}: a tour file holds one JSON object", 'write it as {"title": "...", "audience": '
                       '"review", "steps": [{"screen": "...", "title": "...", "caption": "..."}]}')
        self.known(doc, (), TOUR_FIELDS, "the tour")
        title = self.text_field(doc, "title", (), "the tour", True)
        audience = doc.get("audience", "review")
        if audience not in AUDIENCES:
            raise self.fail(("audience",), f"audience {_show(audience)} is not one of {', '.join(AUDIENCES)}",
                            "use client or whats-new for a demo that plays by itself; training, review or team for a "
                            "step-by-step guide")
        view = doc.get("view", "app")
        if not isinstance(view, str) or view not in VIEWS:
            raise self.fail(("view",), f"view {_show(view)} is not one of {', '.join(VIEWS)}",
                            'set "view": "app" (the full-window app, the default) or "view": "prototype" (the prototype '
                            'page with its screens list and decisions rail), or remove the line')
        speed = doc.get("speed", 1)
        if isinstance(speed, bool) or speed not in SPEEDS:
            raise self.fail(("speed",), f"speed {_show(speed)} is not one of 0.5, 1, 1.5, 2", "set \"speed\": 1")
        purpose = self.text_field(doc, "purpose", (), "the tour")
        intro, closing = self.card(doc.get("intro"), ("intro",)), self.card(doc.get("closing"), ("closing",))
        chapters_in, steps_in = doc.get("chapters"), doc.get("steps")
        if chapters_in is not None and steps_in:
            raise self.fail(("steps",), "the tour has both \"steps\" and \"chapters\"",
                            "put every step inside a chapter, or drop \"chapters\" and keep one \"steps\" list")
        raw: List[Tuple[tuple, object, Optional[int]]] = []
        chapters = []
        if chapters_in is not None:
            if not isinstance(chapters_in, list):
                raise self.fail(("chapters",), "\"chapters\" must be a list of {\"title\": \"...\", \"steps\": [...]}",
                                "write \"chapters\": [{\"title\": \"...\", \"steps\": [...]}]")
            for ci, ch in enumerate(chapters_in):
                path = ("chapters", ci)
                ch = self.obj(ch, path, '{"title": "...", "steps": [...]}')
                self.known(ch, path, CHAPTER_FIELDS, _label(path))
                ctitle = self.text_field(ch, "title", path, _label(path), True)
                steps = ch.get("steps")
                if not isinstance(steps, list) or not steps:
                    raise self.fail(path + ("steps",), f"{_label(path)} has no steps",
                                    f"add \"steps\": [{{\"screen\": \"...\", \"title\": \"...\"}}] to {_label(path)}")
                chapters.append({"title": ctitle, "text": self.text_field(ch, "text", path, _label(path)),
                                 "hold": self.ms(ch, "hold", path), "first": len(raw)})
                raw += [(path + ("steps", si), s, ci) for si, s in enumerate(steps)]
        else:
            if steps_in is not None and not isinstance(steps_in, list):
                raise self.fail(("steps",), "\"steps\" must be a list of steps", "write \"steps\": [{\"screen\": \"...\"}]")
            raw = [(("steps", si), s, None) for si, s in enumerate(steps_in or [])]
        if not raw:
            raise self.fail(("steps",), "the tour has no steps",
                            "add \"steps\": [{\"screen\": \"...\", \"title\": \"...\", \"caption\": \"...\"}]")
        steps = [self.step(path, s, chapter, n) for n, (path, s, chapter) in enumerate(raw, 1)]
        self.raw_steps = [(path, s) for path, s, _chapter in raw]  # for --check-tour's breakpoint warnings
        return {"id": self.id, "title": title, "audience": audience, "view": view, "purpose": purpose,
                "mode": "play" if audience in PLAY_AUDIENCES else "guide", "speed": speed, "intro": intro,
                "closing": closing, "chapters": chapters, "steps": steps}

    def step(self, path: tuple, value: object, chapter: Optional[int], n: int) -> dict:
        name = _label(path)
        s = self.obj(value, path, '{"screen": "...", "title": "...", "caption": "..."}')
        self.known(s, path, STEP_FIELDS, name)
        sid = s.get("screen")
        if sid is None:
            raise self.fail(path, f"{name} has no \"screen\"", f"add \"screen\": \"<id>\" (one of {', '.join(self.screens)})")
        screen = self.screens.get(sid) if isinstance(sid, str) else None
        if screen is None:
            raise self.fail(path + ("screen",), f"{name} names screen {_show(sid)}, which has no screen file",
                            f"use one of: {', '.join(self.screens)} (or write {self.screens_rel}{sid}.html with "
                            f"/plumb:prototype {sid})")
        state = s.get("state")
        if state is None:
            state = screen.states[0]
        elif state not in screen.states:
            raise self.fail(path + ("state",), f"{name} names state {_show(state)} of screen {screen.id}, which has states "
                                               f"{', '.join(screen.states)}",
                            f"use one of those states, or add <div data-state=\"{state}\"> to {screen.rel}")
        title = self.text_field(s, "title", path, name)
        caption = self.text_field(s, "caption", path, name)
        if not title and not caption:
            raise self.fail(path, f"{name} needs a \"title\" or a \"caption\"",
                            "add \"title\": \"...\" (the step's name) and \"caption\": \"...\" (what to notice)")
        say = self.text_field(s, "say", path, name)  # spoken instead of the caption when the voice is on; never shown
        if s.get("target") is not None and s.get("targets") is not None:
            raise self.fail(path + ("targets",), f"{name} has both \"target\" and \"targets\"",
                            "keep one: \"target\": \".x\" for one element, \"targets\": [\".x\", \".y\"] for several")
        if s.get("targets") is not None:
            targets_in = s["targets"]
            if not isinstance(targets_in, list) or not targets_in:
                raise self.fail(path + ("targets",), f"{name}: \"targets\" must be a list of selectors",
                                "write \"targets\": [\".x\", \".y\"] (or \"target\": \".x\" for one element)")
            targets = [self.selector(t, path + ("targets", i), screen, state) for i, t in enumerate(targets_in)]
        elif s.get("target") is not None:
            targets = [self.selector(s["target"], path + ("target",), screen, state)]
        else:
            targets = []
        point, point_label = s.get("point"), ""
        if isinstance(point, dict):
            self.known(point, path + ("point",), ("style", "label"), _label(path + ("point",)))
            point_label = self.text_field(point, "label", path + ("point",), _label(path + ("point",)))
            point = point.get("style")
        if point is None:
            point = "spotlight" if targets else "none"
        if point not in POINTS:
            raise self.fail(path + ("point",), f"{name}: point {_show(point)} is not one of {', '.join(POINTS)}",
                            "use spotlight (dims the rest), ring, arrow, beacon, zoom, cursor or none")
        if point != "none" and not targets:
            raise self.fail(path + ("point",), f"{name} has point {point} but no target",
                            "add \"target\": \"<selector>\" (the element to point at), or set \"point\": \"none\"")
        callout = None
        if s.get("callout") is not None:
            cpath = path + ("callout",)
            c = self.obj(s["callout"], cpath, '{"text": "...", "side": "bottom"}')
            self.known(c, cpath, ("text", "side"), _label(cpath))
            side = c.get("side", "bottom")
            if side not in SIDES:
                raise self.fail(cpath + ("side",), f"{_label(cpath)}.side {_show(side)} is not one of {', '.join(SIDES)}",
                                "set \"side\": \"bottom\" (or top, right, left)")
            if not targets:
                raise self.fail(cpath, f"{_label(cpath)} needs a target to attach to", "add \"target\": \"<selector>\" to the step")
            callout = {"text": self.text_field(c, "text", cpath, _label(cpath), True), "side": side}
        labels = []
        if s.get("labels") is not None:
            if not isinstance(s["labels"], list):
                raise self.fail(path + ("labels",), f"{name}: \"labels\" must be a list",
                                "write \"labels\": [{\"target\": \".x\", \"text\": \"1\"}]")
            for li, lab in enumerate(s["labels"]):
                lpath = path + ("labels", li)
                lab = self.obj(lab, lpath, '{"target": ".x", "text": "1 Title"}')
                self.known(lab, lpath, ("target", "text"), _label(lpath))
                text = self.text_field(lab, "text", lpath, _label(lpath), True)
                if lab.get("target") is None:
                    raise self.fail(lpath, f"{_label(lpath)} has no \"target\"", "add \"target\": \"<selector>\"")
                labels.append({"target": self.selector(lab["target"], lpath + ("target",), screen, state), "text": text})
        note = None
        if s.get("note") is not None:
            npath = path + ("note",)
            nt = self.obj(s["note"], npath, '{"text": "...", "x": 60, "y": 20}')
            self.known(nt, npath, ("text", "x", "y"), _label(npath))
            text = self.text_field(nt, "text", npath, _label(npath), True)
            xy = []
            for axis in ("x", "y"):
                v = nt.get(axis)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
                    raise self.fail(npath + (axis,), f"{_label(npath)}.{axis} {_show(v)} must be a number from 0 to 100 "
                                                     f"(percent of the screen)", f"set \"{axis}\": 50")
                xy.append(v)
            note = {"text": text, "x": xy[0], "y": xy[1]}
        action = self.action(s, path, screen, state, targets)
        your_turn = s.get("your_turn", False)
        if your_turn is None:
            your_turn = False
        if not isinstance(your_turn, bool):
            raise self.fail(path + ("your_turn",), f"{name}: your_turn must be true or false", "set \"your_turn\": true")
        if your_turn and (action is None or action["kind"] == "wait"):
            raise self.fail(path + ("your_turn",), f"{name}: your_turn needs an action the learner does: click, type or choose",
                            "add \"action\": {\"click\": \"<selector>\"} (or type / choose), or drop \"your_turn\"")
        return {"n": n, "screen": screen.id, "state": state, "title": title, "caption": caption, "say": say, "targets": targets,
                "point": point, "pointLabel": point_label, "callout": callout, "labels": labels, "note": note,
                "action": action, "yourTurn": your_turn, "hint": self.text_field(s, "hint", path, name),
                "hold": self.ms(s, "hold", path), "chapter": chapter}

    def action(self, s: dict, path: tuple, screen: Screen, state: str, targets: List[str]) -> Optional[dict]:
        if s.get("action") is None:
            return None
        apath = path + ("action",)
        a = self.obj(s["action"], apath, '{"click": "<selector>"}')
        self.known(a, apath, ACTIONS + ("target",), _label(apath))
        kinds = [k for k in ACTIONS if a.get(k) is not None]
        if len(kinds) != 1:
            raise self.fail(apath, f"{_label(apath)} needs exactly one of click, type, choose, wait",
                            "write {\"click\": \"<selector>\"}, {\"type\": \"text\"}, {\"choose\": \"option\"} or {\"wait\": 1000}")
        kind = kinds[0]
        value = a[kind]
        kpath = apath + (kind,)
        if kind == "wait":
            return {"kind": "wait", "target": "", "value": "", "ms": self.ms(a, "wait", apath)}
        own = a.get("target")
        if kind == "click":
            if isinstance(value, str):
                if own is not None:
                    raise self.fail(apath + ("target",), f"{_label(apath)} names its element twice (click and target)",
                                    "keep {\"click\": \"<selector>\"}")
                return {"kind": "click", "target": self.selector(value, kpath, screen, state), "value": "", "ms": 0}
            if value is not True:
                raise self.fail(kpath, f"{_label(kpath)} must be a selector or true (the step's target)",
                                "write {\"click\": \"<selector>\"} or {\"click\": true}")
        elif not isinstance(value, str) or not value:
            raise self.fail(kpath, f"{_label(kpath)} must be the text to {'type' if kind == 'type' else 'choose'}",
                            f"write {{\"{kind}\": \"...\"}}")
        if own is not None:
            target = self.selector(own, apath + ("target",), screen, state)
        elif targets:
            target = targets[0]
        else:
            raise self.fail(kpath, f"{_label(kpath)} needs a target: give the step a \"target\" or the action one",
                            f"add \"target\": \"<selector>\" to the step (or to {_label(apath)})")
        return {"kind": kind, "target": target, "value": "" if kind == "click" else value, "ms": 0}


def _label(path: tuple) -> str:
    return _path_text(path) or "the tour"


def check_tour_ids(ids: List[Tuple[str, str]]) -> None:
    """Refuse two tours whose ids differ only in case (one file on Windows and macOS) and ids that read as another
    tour's step in a link (#tour-demo-2 is step 2 of demo, so no tour may be called demo-2)."""
    seen: Dict[str, str] = {}
    for tid, rel in ids:
        key = tid.casefold()
        if key in seen:
            raise _err(f"{rel}: duplicate tour id \"{key}\" (also {seen[key]})",
                       "give each tour its own file name: rename one of them")
        seen[key] = rel
    names = {tid for tid, _rel in ids}
    for tid, rel in ids:
        m = re.match(r"^(.+)-(\d+)$", tid)
        if m and m.group(1) in names:
            raise _err(f"{rel}: the tour id \"{tid}\" reads as step {m.group(2)} of tour \"{m.group(1)}\" in a link "
                       f"(#tour-{tid})", f"rename {rel} so its name does not end in -<number>, e.g. {m.group(1)}-part-{m.group(2)}.json")


def load_tours(folder: Path, screens: List[Screen], root: Path, rel, screens_rel: str) -> List[dict]:
    files = sorted((p for p in folder.glob("*.json") if p.is_file()), key=lambda p: p.name) if folder.is_dir() else []
    by_id = {s.id: s for s in screens}
    ids = []
    for path in files:
        tid, prel = path.name[: -len(".json")], rel(path, root)
        if not _ID.match(tid):
            raise _err(f"{prel}: tour id \"{tid}\" may only use letters, digits, _ and -",
                       "rename the file to an id such as booking-demo.json")
        ids.append((tid, prel))
    check_tour_ids(ids)
    tours = []
    for path, (tid, prel) in zip(files, ids):
        try:
            text = P.normalise_text(P.read_project_text(path))
        except (OSError, UnicodeDecodeError) as exc:
            raise _err(f"{prel}: cannot read the tour file ({exc})", "save it as UTF-8") from None
        tours.append(_TourReader(tid, prel, text, by_id, screens_rel).read())
    return tours


# ---------------------------------------------------------------- --check-tour: one tour file, and the frame widths at
# which a screen's own CSS hides a step's target (a standard-library reader of top-level rules and
# @container plumb-frame blocks; a selector or query it cannot read is left out, silently)

_LENGTH = r"(\d*\.?\d+)\s*(rem|em|px)"
_QUERY = re.compile(r"^\(\s*(?:(min|max)-(?:width|inline-size)\s*:\s*" + _LENGTH
                    + r"|(?:width|inline-size)\s*(>=|<=|>|<)\s*" + _LENGTH + r")\s*\)$", re.I)
_OFF_CANVAS = re.compile(r"translate(x|y|3d)?\(([^()]*)\)")
_PERCENT = re.compile(r"^([+-]?\d*\.?\d+)%$")
_EPS = 0.01
_HUGE = 10.0 ** 6


def _frame_query(text: str) -> Optional[List[Tuple[str, bool, float, str]]]:
    """The parts of `@container plumb-frame <text>` as (min|max, strict, px, as written); None when unreadable.
    Reads (min-width: X), (max-width: X), (width >= X) and the like, and the same with inline-size."""
    parts = []
    for raw in re.split(r"\s+and\s+", text.strip(), flags=re.I):
        m = _QUERY.match(raw.strip())
        if not m:
            return None
        if m.group(1):
            kind, strict, num, unit = m.group(1).lower(), False, m.group(2), m.group(3)
        else:
            op, num, unit = m.group(4), m.group(5), m.group(6)
            kind, strict = ("min" if op.startswith(">") else "max"), len(op) == 1
        parts.append((kind, strict, float(num) * (1 if unit.lower() == "px" else 16), f"{num}{unit.lower()}"))
    return parts


def _holds(cond: Optional[list], width: float) -> bool:
    for kind, strict, px, _text in cond or ():
        if kind == "min" and not (width > px if strict else width >= px):
            return False
        if kind == "max" and not (width < px if strict else width <= px):
            return False
    return True


def _declarations(body: str) -> List[Tuple[str, str, bool]]:
    """(property, value, !important) of a rule body; nested rules and odd pieces are left out."""
    pieces, depth, quote, cur = [], 0, "", []
    for ch in body:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            pieces.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    pieces.append("".join(cur))
    out = []
    for piece in pieces:
        if ":" not in piece or "{" in piece or "}" in piece:
            continue
        name, value = piece.split(":", 1)
        value = " ".join(value.split()).lower()
        important = bool(re.search(r"!\s*important$", value))
        out.append((name.strip().lower(), re.sub(r"\s*!\s*important$", "", value), important))
    return out


def css_rules(css: str) -> List[Tuple[str, List[Tuple[str, str, bool]], Optional[list]]]:
    """(selector list, declarations, frame condition or None) for each top-level style rule and each rule inside an
    `@container plumb-frame (...)` block, in source order. Other at-rules (@media, @supports, ...) are left out."""
    css = _CSS_COMMENT.sub(" ", css)
    rules: list = []

    def walk(pos: int, end: int, cond: Optional[list]) -> None:
        while pos < end:
            brace = css.find("{", pos, end)
            if brace == -1:
                return
            semi = css.rfind(";", pos, brace)
            if semi != -1:
                pos = semi + 1
            head = css[pos:brace].strip()
            close = _close_brace(css, brace)
            if head.startswith("@"):
                m = re.match(r"@container\s+plumb-frame\s+(.*)$", head, re.I | re.S)
                inner = _frame_query(m.group(1)) if m and cond is None else None
                if inner:
                    walk(brace + 1, close, inner)
            elif head:
                rules.append((head, _declarations(css[brace + 1:close]), cond))
            pos = close + 1

    walk(0, len(css), None)
    return rules


def _specificity(parts: List[Tuple[Optional[str], dict]]) -> Tuple[int, int, int]:
    a = b = c = 0
    for _comb, comp in parts:
        a += len(comp["ids"])
        b += len(comp["classes"]) + len(comp["attrs"])
        c += comp["tag"] not in (None, "*")
        for name, arg in comp["pseudos"]:
            if name in ("not", "is"):
                best = max(_specificity(p) for p in arg)
                a, b, c = a + best[0], b + best[1], c + best[2]
            elif name != "where":
                b += 1
    return a, b, c


def _off_canvas(prop: str, value: str) -> bool:
    """A transform (or translate) that moves the element its own full width or height away: an off-canvas drawer."""
    if prop == "translate":
        args = value.split()[:2]
    else:
        args = []
        for m in _OFF_CANVAS.finditer(value):
            found = [a.strip() for a in m.group(2).split(",")]
            args += found[:1] if m.group(1) in ("x", "y") else found[:2]
    return any(m and abs(float(m.group(1))) >= 100 for m in (_PERCENT.match(a) for a in args))


_HIDES = {"display": lambda v: v == "none", "visibility": lambda v: v in ("hidden", "collapse"),
          "transform": lambda v: _off_canvas("transform", v), "translate": lambda v: _off_canvas("translate", v)}


class _ScreenCSS:
    """The screen's own CSS applied to its markup in one state: for each element, the hiding properties that rules set
    on it, with their cascade order (!important, specificity, source order) and frame condition."""

    def __init__(self, screen: Screen, state: str, shared_css: Tuple[str, ...] = ()) -> None:
        self.decls: Dict[_Node, Dict[str, list]] = {}
        self.bounds: Dict[float, str] = {}
        tree, order = screen.tree(), 0
        for css in (*shared_css, *screen.styles):  # the page's order: the shared files first, then the screen's own
            for selectors, decls, cond in css_rules(css):
                wanted = [d for d in decls if d[0] in _HIDES]
                if not wanted:
                    continue
                for sel in _split_top(selectors):
                    order += 1
                    try:
                        parts = parse_selector(sel)
                        nodes = select(tree, sel, state)
                    except SelectorError:
                        continue
                    spec = _specificity(parts[0])
                    for _kind, _strict, px, text in cond or ():
                        self.bounds.setdefault(px, text)
                    for node in nodes:
                        props = self.decls.setdefault(node, {})
                        for prop, value, important in wanted:
                            props.setdefault(prop, []).append(((important, spec, order), cond, value))

    def samples(self) -> List[Tuple[float, str, str]]:
        """(width, how a visible run starting here reads, how one ending here reads), smallest first."""
        out = [(0.0, "", "")]
        for px in sorted(self.bounds):
            text = self.bounds[px]
            out += [(px - _EPS, f"≥ {text}", f"< {text}"), (px, f"≥ {text}", f"≤ {text}"), (px + _EPS, f"> {text}", f"≤ {text}")]
        return out + [(_HUGE, "", "")]

    def hidden(self, node: _Node, width: float) -> Optional[Tuple[_Node, str]]:
        """(the element that hides it, "property: value") when the node or an ancestor is hidden at this frame width.
        visibility inherits and a descendant may set it back: the nearest element that sets it decides."""
        visibility_set = False
        while node is not None and node.tag != "#root":
            for prop, cands in self.decls.get(node, {}).items():
                if prop == "visibility" and visibility_set:
                    continue
                live = [c for c in cands if _holds(c[1], width)]
                if live:
                    value = max(live, key=lambda c: c[0])[2]
                    if prop == "visibility":
                        visibility_set = True
                    if _HIDES[prop](value):
                        return node, f"{prop}: {value}"
            node = node.parent
        return None


def _describe(node: _Node) -> str:
    out = node.tag + (f"#{node.attrs['id']}" if node.attrs.get("id") else "")
    return out + "".join(f".{c}" for c in node.attrs.get("class", "").split()[:2])


def breakpoint_warnings(reader: "_TourReader", tour: dict, screens: Dict[str, Screen],
                        shared_css: Tuple[str, ...] = ()) -> List[str]:
    """One line per step selector whose elements the screen's own CSS shows only at some frame widths."""
    cache: Dict[Tuple[str, str], _ScreenCSS] = {}
    out: List[str] = []
    for (path, raw), step in zip(reader.raw_steps, tour["steps"]):
        screen = screens[step["screen"]]
        key = (screen.id, step["state"])
        if key not in cache:
            cache[key] = _ScreenCSS(screen, step["state"], shared_css)
        sheet = cache[key]
        if not sheet.bounds:
            continue
        found: List[Tuple[tuple, str]] = []
        if isinstance(raw.get("targets"), list):
            found += [(path + ("targets", i), t) for i, t in enumerate(raw["targets"])]
        elif raw.get("target") is not None:
            found.append((path + ("target",), raw["target"]))
        for i, lab in enumerate(raw.get("labels") or []):
            found.append((path + ("labels", i, "target"), lab["target"]))
        action = raw.get("action") or {}
        for key2 in ("click", "target"):
            if isinstance(action.get(key2), str):
                found.append((path + ("action", key2), action[key2]))
        seen = set()
        for spath, sel in found:
            sel = sel.strip()
            if sel in seen:
                continue
            seen.add(sel)
            nodes = select(screen.tree(), sel, step["state"])
            samples = sheet.samples()
            shown, why = [], None
            for width, _lo, _hi in samples:
                hid = [sheet.hidden(n, width) for n in nodes]
                shown.append(not all(hid))
                if all(hid) and why is None:
                    why = hid[0]
            if all(shown) or not any(shown) or why is None:
                continue
            runs, start = [], None
            for i, on in enumerate(shown + [False]):
                if on and start is None:
                    start = i
                elif not on and start is not None:
                    lo, hi = samples[start][1], samples[i - 1][2]
                    runs.append(" and ".join(t for t in (lo, hi) if t))
                    start = None
            node, how = why
            where = ("is hidden by the screen's CSS" if node in nodes
                     else f"sits inside {_describe(node)}, which the screen's CSS hides")
            line = reader.lines.get(spath) or reader.lines.get(path)
            out.append(f"{reader.rel}:{line}: step {step['n']}, {_label(spath)} {_show(sel)} {where} ({how}): visible only "
                       f"when the frame is {' or '.join(runs)}")
    return out


def check_tour_file(given: str, root: Path, docs: Path, screens: List[Screen], rel, folder: Path, command: str,
                    shared: Optional[List["Shared"]] = None) -> int:
    """--check-tour FILE: validate one tour file against the screens and warn about frame widths; writes nothing."""
    tours_dir = docs / "prototype" / "tours"
    path = Path(given)
    if not path.is_file() and not path.is_absolute():
        for alt in (root / given, tours_dir / given, tours_dir / f"{given}.json"):
            if alt.is_file():
                path = alt
                break
    example = f"{command} --check-tour {rel(tours_dir, root)}/<id>.json"
    if not path.is_file():
        raise _err(f"--check-tour {given}: no such tour file", f"pass the tour file: {example}")
    tid = path.name[: -len(".json")] if path.name.lower().endswith(".json") else ""
    prel = rel(path, root)
    if not tid:
        raise _err(f"--check-tour {prel}: a tour file is <id>.json", f"pass the tour's .json file: {example}")
    if not _ID.match(tid):
        raise _err(f"{prel}: tour id \"{tid}\" may only use letters, digits, _ and -",
                   "rename the file to an id such as booking-demo.json")
    try:
        text = P.normalise_text(P.read_project_text(path))
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{prel}: cannot read the tour file ({exc})", "save it as UTF-8") from None
    by_id = {s.id: s for s in screens}
    reader = _TourReader(tid, prel, text, by_id, rel(folder, root) + "/")
    tour = reader.read()
    warnings = breakpoint_warnings(reader, tour, by_id, tuple(s.text for s in shared or () if s.kind == "css"))
    for line in warnings:
        print(f"warning: {line}", file=sys.stderr)
    if warnings:
        print("fix: play the tour where the frame is that wide (the app view's frame is the window; the prototype "
              "page's is its desktop frame), or point those steps at elements the screen shows at every width; "
              "/plumb:tour then checks it in a browser with check-tour.py", file=sys.stderr)
    n = len(tour["steps"])
    extra = f"; {len(warnings)} warning{'s' if len(warnings) != 1 else ''}" if warnings else ""
    print(f"ok: {prel}: {n} step{'s' if n != 1 else ''} ({tour['mode']} mode, {tour['view']} view) "
          f"{'match' if n != 1 else 'matches'} the "
          f"screens{extra}")
    return 0


# ---------------------------------------------------------------- pages


def screen_styles(screens: List[Screen]) -> str:
    blocks = [f'<style data-screen-style="{_e(s.id)}">\n{css}\n</style>' for s in screens for css in s.styles]
    return "\n".join(blocks)


_SHARED_RUNTIME = """window.plumbScreens.shared = [];
window.plumbScreens.useShared = function (id) {
  window.plumbScreens.shared.forEach(function (s) {
    window.plumbScreens.define(id, function (screen, plumb) {
      try { s[1].call(this, screen, plumb); }
      catch (err) { console.error("Plumb: the shared script " + s[0] + " failed on screen " + id + ":", err); }
    });
  });
};"""


def shared_styles(shared: List[Shared]) -> str:
    """The shared CSS files, each once, in name order (before the screens' own styles, so a screen can override)."""
    return "\n".join(f'<style data-shared-style="{_e(s.name)}">\n{s.text}\n</style>' for s in shared if s.kind == "css")


def shared_scripts(shared: List[Shared]) -> str:
    """The shared JS files, each once, as functions every screen runs before its own script (screen_scripts)."""
    js = [s for s in shared if s.kind == "js"]
    if not js:
        return ""
    out = [f"<script>\n{_SHARED_RUNTIME}\n</script>"]
    for s in js:
        out.append(f'<script data-shared-script="{_e(s.name)}">\nwindow.plumbScreens.shared.push([{json_script(s.name)}, '
                   f"function (screen, plumb) {{\n{s.text}\n}}]);\n</script>")
    return "\n".join(out)


def page_parts(screens: List[Screen], shared: List[Shared]) -> Tuple[str, str]:
    """(styles, scripts) of a page: the shared files once, then each screen's own."""
    styles = "\n".join(x for x in (shared_styles(shared), screen_styles(screens)) if x)
    uses = any(s.kind == "js" for s in shared)
    scripts = "\n".join(x for x in (shared_scripts(shared), screen_scripts(screens, uses)) if x)
    return styles, scripts


def screen_scripts(screens: List[Screen], shared_js: bool = False) -> str:
    out = []
    for s in screens:
        if shared_js:  # the shared scripts run for this screen first, as its first definitions
            out.append(f"<script>\nwindow.plumbScreens.useShared({json_script(s.id)});\n</script>")
        for body in s.scripts:
            out.append(f"<script>\nwindow.plumbScreens.define({json.dumps(s.id, ensure_ascii=False)}, "
                       f"function (screen, plumb) {{\n{body}\n}});\n</script>")
    return "\n".join(out)


def json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=False).replace("<", "\\u003c")


def _badge(state: str) -> str:
    return (f'<span class="badge badge-{state}"><span class="mark" aria-hidden="true"></span>'
            f'{_e(APPROVAL_TEXT[state])}</span>')


def _decision_body(e: dict, ids: Dict[str, str], screen_links: bool, link_log: bool) -> str:
    meta = [f'<time>{_e(e["date"])}</time>']
    if e["by"]:
        meta.append(f"Decided by {inline(e['by'])}")
    rows = []
    for key, value, subs in e["fields"]:
        if key.lower() in ("date", "screens") or key.lower() in WHO_KEYS:
            continue
        body = inline(value)
        if subs:
            body += "<ul>" + "".join(f"<li>{inline(s)}</li>" for s in subs) + "</ul>"
        rows.append(f"<div><dt>{_e(key)}</dt><dd>{body}</dd></div>")
    notes = "".join(f"<p>{inline(n)}</p>" for n in e["notes"])
    out = [f'<p class="dc-id"><code>{_e(e["id"])}</code></p>', f'<h3 class="dc-title">{_e(e["title"])}</h3>',
           f'<p class="dc-meta">{" · ".join(meta)}</p>']
    if rows:
        out.append(f'<dl class="dc-fields">{"".join(rows)}</dl>')
    if notes:
        out.append(f'<div class="dc-notes">{notes}</div>')
    if screen_links:
        if e["all"]:
            out.append('<p class="dc-screens">Applies to every screen</p>')
        else:
            links = []
            for name in e["screens"]:
                sid = next((k for k in ids if k.casefold() == name.casefold()), None)
                links.append(f'<a href="#screen-{_e(sid)}">{_e(ids[sid])}</a>' if sid else f"<span>{_e(name)}</span>")
            if links:
                out.append(f'<p class="dc-screens">Screens: {", ".join(links)}</p>')
    if link_log:
        out.append(f'<p class="dc-more"><a href="#decision-{_e(e["id"])}">In the decision log</a></p>')
    return "".join(out)


def decisions_page(entries: List[dict], screens: List[Screen], source: str, cls: str, hidden: bool) -> str:
    ids = {s.id: s.title for s in screens}
    attr = " hidden" if hidden else ""
    head = (f'<section id="decisions" class="decisions {cls}" aria-labelledby="decisions-h"{attr}>'
            f'<h2 id="decisions-h" tabindex="-1">Decisions</h2>'
            f'<p class="note">Every design decision recorded in <code>{_e(source)}</code>, newest first, with who made it '
            f'and the screens it shapes. Read them before changing a screen.</p>')
    if not entries:
        return head + '<p class="empty">No decisions recorded yet.</p></section>'
    items = "".join(f'<li><article id="decision-{_e(e["id"])}" class="dc" data-decision="{_e(e["id"])}" tabindex="-1">'
                    f'{_decision_body(e, ids, True, False)}</article></li>' for e in entries)
    return head + f'<ol class="dc-list" role="list">{items}</ol></section>'


def why_panels(entries: List[dict], screens: List[Screen]) -> str:
    out = []
    ids = {s.id: s.title for s in screens}
    for i, s in enumerate(screens):
        mine = [e for e in entries if decision_applies(e, s.id)]
        attr = " hidden" if i else ""
        if mine:
            count = f"{len(mine)} decision{'s' if len(mine) != 1 else ''} shape this screen."
            body = ('<ol class="why-list" role="list">' + "".join(
                f'<li><article class="dc dc-compact" data-decision="{_e(e["id"])}">{_decision_body(e, ids, False, True)}'
                f'</article></li>' for e in mine) + "</ol>")
        else:
            count = "No decisions recorded for this screen yet."
            body = ('<p class="empty">Decisions are logged in decisions.md when a screen is chosen or changed '
                    '(/plumb:prototype, /plumb:update); they show here.</p>')
        out.append(f'<section class="why-panel" data-why-for="{_e(s.id)}" aria-label="Decisions for {_e(s.title)}"{attr}>'
                   f'<p class="why-count">{_e(count)}</p>{body}</section>')
    return "\n".join(out)


def _link_control(state: str, theme: str) -> str:
    cls = {"hover": " is-hover", "focus": " is-focus", "pressed": " is-pressed", "loading": " is-loading"}.get(state, "")
    data = f'data-component="link" data-state="{state}"'
    if state == "disabled":
        return f'<a class="c-link" {data} role="link" aria-disabled="true">View the invoice</a>'
    if state == "loading":
        return (f'<a class="c-link{cls}" {data} href="#controls" aria-busy="true">'
                f'<span class="spinner" aria-hidden="true"></span>Opening</a>')
    return f'<a class="c-link{cls}" {data} href="#controls">View the invoice</a>'


CONTROL_ROWS = (("button-primary", "Button, primary"), ("button-secondary", "Button, secondary"),
                ("button-outline", "Button, outline"), ("button-danger", "Button, danger"),
                ("input", "Input"), ("chip", "Chip"), ("link", "Link"))


def control_sheet(bt) -> str:
    out = ['<div class="ctl-themes">']
    for theme, label in (("light", "Light"), ("dark", "Dark")):
        out.append(f'<div class="pl-{theme} ctl-panel"><h3 class="group-h">{label}</h3>')
        for comp, title in CONTROL_ROWS:
            cells = []
            for state, name in bt.COMPONENT_STATES:
                widget = _link_control(state, theme) if comp == "link" else bt._component(comp, state, theme)
                cells.append(f'<li class="ctl-cell"><span class="state-name">{name}</span>{widget}</li>')
            out.append(f'<div class="ctl-row"><h4>{title}</h4><ul class="ctl-states" role="list">{"".join(cells)}</ul></div>')
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


def _meta_line(entry: dict, approval: str) -> str:
    """id · route · build status · approval, as separate items (the separators are decoration)."""
    bits = [f"<code>{_e(entry['id'])}</code>"]
    if entry.get("route"):
        bits.append(f"<span>route <code>{_e(entry['route'])}</code></span>")
    bits.append(f"<span>{_e(STATUS_TEXT[entry['status']])}</span>")
    bits.append(_badge(approval))
    return '<span class="sep" aria-hidden="true">·</span>'.join(bits)


def player_slots(ctx: dict, tour: Optional[dict]) -> Dict[str, str]:
    """The walkthrough player (templates/player.css and player.js) and the tours it plays: every tour in prototype.html,
    one tour that starts by itself in a standalone tour page."""
    config = {"tours": [tour] if tour else ctx["tours"],
              "autostart": {"tour": tour["id"], "mode": tour["mode"]} if tour else None}
    return {
        "player_css": f"<style>\n{ctx['player_css'].strip()}\n</style>",
        "player": (f'<script type="application/json" id="plumb-tours">{json_script(config)}</script>\n'
                   f"<script>\n{ctx['player_js'].strip()}\n</script>"),
    }


def build_prototype(ctx: dict, template: str, tour: Optional[dict] = None) -> str:
    """prototype.html, or with `tour` the standalone page docs/tours/<id>.html: the same prototype one folder down (a
    <base> keeps links and images resolving from the docs folder) that opens straight into that tour."""
    screens: List[Screen] = ctx["screens"]
    entries = ctx["entries"]
    nav, groups, frame, data = [], [], [], []
    for i, s in enumerate(screens):
        e = entries[s.id]
        appr = approval_state(e, s)
        current = ' aria-current="page"' if i == 0 else ""
        nav.append(f'<li><a href="#screen-{_e(s.id)}" data-nav="{_e(s.id)}" title="{_e(s.title)}" data-approval="{appr}" '
                   f'data-status="{e["status"]}"{current}><span class="nav-title">{_e(s.title)}</span>'
                   f'<span class="nav-meta">{_badge(appr)}<span class="nav-status">{_e(STATUS_TEXT[e["status"]])}</span>'
                   f'</span></a></li>')
        buttons = "".join(f'<button type="button" class="seg" data-set-state="{_e(st)}" '
                          f'aria-pressed="{"true" if j == 0 else "false"}">{_e(state_label(st))}</button>'
                          for j, st in enumerate(s.states))
        hidden = " hidden" if i else ""
        groups.append(f'<div class="segs" role="group" aria-label="State of {_e(s.title)}" data-states-for="{_e(s.id)}"'
                      f'{hidden}>{buttons}</div>')
        frame.append(s.render(s.states[0], hide_section=bool(i)))
        data.append({"id": s.id, "title": s.title, "states": s.states, "route": e["route"], "status": e["status"],
                     "approval": appr, "approvalText": APPROVAL_TEXT[appr], "meta": _meta_line(e, appr)})
    first = screens[0]
    values = {
        "header": f"<!-- {_e(tour_header(ctx, tour) if tour else ctx['header'])} -->",
        "base": '<base href="../">' if tour else "",
        "chrome_roles": ctx["chrome_roles"].strip(),
        "title": _e(f"{tour['title']} · {ctx['project']} walkthrough" if tour else f"{first.title} · {ctx['project']} prototype"),
        "project": _e(ctx["project"]),
        "plumb_version": _e(P.PLUMB_VERSION),
        "source": _e(ctx["screens_rel"]),
        "theme_css": ctx["theme_css"],
        "screen_styles": ctx["styles"],
        "nav": "\n".join(nav),
        "screen_title": _e(first.title),
        "first_screen_href": f"#screen-{_e(first.id)}",
        "first_app_href": f"app.html#/{_e(first.id)}",
        "screen_meta": _meta_line(entries[first.id], approval_state(entries[first.id], first)),
        "state_groups": "\n".join(groups),
        "frame": "\n".join(frame),
        "why": why_panels(ctx["decisions"], screens),
        "decisions": decisions_page(ctx["decisions"], screens, ctx["decisions_rel"], "pp-decisions pp-ui", hidden=True),
        "data": json_script({"project": ctx["project"], "screens": data}),
        "screen_scripts": ctx["scripts"],
    }
    values.update(player_slots(ctx, tour))
    text = P.fill_template(template, values, SHELL_TEMPLATE)
    return text if text.endswith("\n") else text + "\n"


def build_app(ctx: dict, template: str, tour: Optional[dict] = None) -> str:
    """app.html: every screen full window with no prototype panels, hash routes #/ID and #/ID/STATE (and the prototype's
    #screen-ID[/STATE]), the same screen-script API and window.plumbPrototype. It opens on the first screen by
    data-order. No player. With `tour` (a tour whose view is app, the default) it is the tour page docs/tours/<id>.html:
    the same app one folder down (a <base> keeps links and images resolving from the docs folder) with the walkthrough
    player on top, opening straight into that tour."""
    screens: List[Screen] = ctx["screens"]
    entries = ctx["entries"]
    frame = [s.render(s.states[0], hide_section=bool(i)) for i, s in enumerate(screens)]
    data = [{"id": s.id, "title": s.title, "states": s.states, "route": entries[s.id]["route"]} for s in screens]
    first = screens[0]
    values = {
        "header": f"<!-- {_e(tour_header(ctx, tour) if tour else (ctx.get('app_header') or ctx['header']))} -->",
        "base": '<base href="../">' if tour else "",
        "title": _e(f"{tour['title']} · {ctx['project']} walkthrough" if tour else f"{first.title} · {ctx['project']}"),
        "chrome_roles": ctx["chrome_roles"].strip(),
        "theme_key": json_script(f"plumb-app-theme:{ctx.get('base_project') or ctx['project']}"),
        "theme_css": ctx["theme_css"],
        "screen_styles": ctx["styles"],
        "frame": "\n".join(frame),
        "data": json_script({"project": ctx["project"], "screens": data}),
        "screen_scripts": ctx["scripts"],
        "player_css": "",
        "player": "",
    }
    if tour:
        values.update(player_slots(ctx, tour))
    text = P.fill_template(template, values, APP_TEMPLATE)
    return text if text.endswith("\n") else text + "\n"


def tour_header(ctx: dict, tour: dict) -> str:
    return (f"GENERATED by {ctx['script_rel']} from {ctx['tours_rel']}{tour['id']}.json, {ctx['screens_rel']}*.html, "
            f"{ctx['decisions_rel']} and {ctx['tokens_rel']}. Do not edit: edit the tour file or the screen files, then run "
            f"build-prototype.py.")


def build_catalogue(ctx: dict, template: str, bt) -> str:
    """screens.html: every screen × state × theme as its own iframe copy. A screen's markup, styles and scripts are in
    the page once (three <template>s), shared by all its copies; the page's script builds each copy from them and hides
    every outer state block but the copy's, as Screen.render does. So the page grows with the screens, not with
    screens × states × 2, and the token block is in it once. The shared files are in it once too (two more templates
    every copy takes before the screen's own styles and scripts)."""
    screens: List[Screen] = ctx["screens"]
    entries = ctx["entries"]
    shared: List[Shared] = ctx.get("shared") or []
    uses_js = any(x.kind == "js" for x in shared)
    nav, body = [], []
    if shared:
        body.append(f'<template data-shared-styles>{shared_styles(shared)}</template>'
                    f'<template data-shared-scripts>{shared_scripts(shared)}</template>')
    for s in screens:
        e = entries[s.id]
        appr = approval_state(e, s)
        states = "".join(f'<li><a href="#screen-{_e(s.id)}/{_e(st)}">{_e(state_label(st))}</a></li>' for st in s.states)
        nav.append(f'<li><a href="#screen-{_e(s.id)}" data-nav="{_e(s.id)}">{_e(s.title)}</a>'
                   f'<ul class="sc-nav-states" role="list">{states}</ul></li>')
        blocks = []
        for st in s.states:
            label = state_label(st)
            pair = []
            for theme, name in (("light", "Light"), ("dark", "Dark")):
                # each copy is its own document (an iframe built from the template by the page's script), so ids,
                # url(#id), #id selectors, getElementById and radio groups never meet another copy's. No sandbox: an
                # opaque-origin frame may not load the screen's relative file:// images; its CSP keeps the network out
                # the markup is the screen's one shared template (below); the page hides the other states per copy
                pair.append(f'<figure class="sc-frame pl-{theme}" data-copy="{_e(s.id)}/{_e(st)}/{theme}">'
                            f'<figcaption>{name}</figcaption>'
                            f'<iframe class="sc-iframe" '
                            f'title="{_e(s.title)}: {_e(label)}, {theme} theme"></iframe></figure>')
            copies = "".join(pair)
            code = f" <code>{_e(st)}</code>" if label.lower() != st.lower() else ""
            blocks.append(f'<div class="sc-state" id="screen-{_e(s.id)}/{_e(st)}"><h3 class="sc-state-h sc-ui">'
                          f'{_e(label)}{code}</h3><div class="sc-pair">{copies}</div></div>')
        body.append(f'<section class="sc-screen" id="screen-{_e(s.id)}" aria-labelledby="sc-h-{_e(s.id)}">'
                    f'<header class="sc-head sc-ui"><div><h2 id="sc-h-{_e(s.id)}">{_e(s.title)}</h2>'
                    f'<p class="sc-meta">{_meta_line(e, appr)}</p></div>'
                    f'<a class="sc-open" href="prototype.html#screen-{_e(s.id)}">Open in the prototype</a></header>'
                    + "".join(blocks)
                    + f'<template data-screen-markup="{_e(s.id)}">{s.section}</template>'
                    + f'<template data-screen-styles="{_e(s.id)}">{screen_styles([s])}</template>'
                    + f'<template data-screen-scripts="{_e(s.id)}">{screen_scripts([s], uses_js)}</template>'
                    + "</section>")
    count = sum(len(s.states) for s in screens)
    values = {
        "header": f"<!-- {_e(ctx['header'])} -->",
        "title": _e(f"{ctx['project']}: screens"),
        "project": _e(ctx["project"]),
        "plumb_version": _e(P.PLUMB_VERSION),
        "source": _e(ctx["screens_rel"]),
        "summary": _e(f"{len(screens)} screen{'s' if len(screens) != 1 else ''}, {count} state{'s' if count != 1 else ''}"),
        "theme_css": ctx["theme_css"],
        "nav": "\n".join(nav),
        "catalogue": "\n".join(body),
        "controls": control_sheet(bt),
        "decisions": decisions_page(ctx["decisions"], screens, ctx["decisions_rel"], "sc-section sc-ui", hidden=False),
    }
    text = P.fill_template(template, values, CATALOGUE_TEMPLATE)
    return text if text.endswith("\n") else text + "\n"


_DATA_URI = re.compile(r"\bdata:[^\s\"'()<>]+", re.I)
MIB = 1024 * 1024


def screen_weight(s: Screen) -> Tuple[int, int]:
    """(bytes the screen adds to each page, bytes of those in inline data: URIs): its markup, styles and scripts."""
    text = s.section + "".join(s.styles) + "".join(s.scripts)
    return len(text.encode("utf-8")), sum(len(m.group(0)) for m in _DATA_URI.finditer(text))


def size_warnings(files: Dict[Path, str], root: Path, rel, command: str, screens: List[Screen]) -> str:
    """One warning for every generated page (.html) over PAGE_WARN_BYTES (big pages open slowly and weigh on the
    repository; data files such as screens.json are not pages), the screen files that weigh most, and a fix. Every
    page holds each screen file once, so smaller screen files are what make the pages smaller."""
    big = [(rel(path, root), len(text.encode("utf-8"))) for path, text in sorted(files.items())
           if path.suffix == ".html" and len(text.encode("utf-8")) > PAGE_WARN_BYTES]
    if not big:
        return ""
    pages = ", ".join(f"{page} is {_mb(size)} MB" for page, size in big)
    why = "a generated page should stay under (slow to open, heavy in the repository)"
    lines = [f"warning: {pages}: over the {_limit()} MB {why}"]
    heavy = sorted(((screen_weight(s), s.rel) for s in screens), key=lambda x: (-x[0][0], x[1]))[:3]
    heavy = [h for h in heavy if h[0][0] * 10 >= heavy[0][0][0]]  # up to three, none under a tenth of the heaviest
    if heavy:
        parts = []
        for (size, data), name in heavy:
            extra = f", {_mb(data)} MB of it inline data: URIs" if data * 10 >= size else ""
            parts.append(f"{name} ({_mb(size)} MB{extra})")
        lines.append(f"note: every page holds each screen file once; the largest: {', '.join(parts)}")
    lines.append(f"fix: make the screen files smaller: move inline data: images and large inline SVG into image files "
                 f"in the docs folder and point at them with a relative src (screens load relative images), and cut "
                 f"very long sample content; or git-ignore the pages (they are generated: {command} rebuilds them), "
                 f"but a git-ignored page is missing on a fresh clone, so --check then fails: run the build in CI "
                 f"instead of --check, or keep the pages committed")
    return "\n".join(lines)


def _mb(size: int) -> str:
    """Megabytes (MiB, as ls -lh and the hosting limits count them), rounded up to one decimal: a page just over the
    limit never reads as the limit itself."""
    tenths = -(-size * 10 // MIB)
    return f"{tenths // 10}.{tenths % 10}"


def _limit() -> str:
    whole, rest = divmod(PAGE_WARN_BYTES, MIB)
    return str(whole) if not rest else f"{PAGE_WARN_BYTES / MIB:.3g}"


def orphan_tour_pages(folder: Path, pages: Dict[Path, str]) -> List[Path]:
    """Generated pages in <docs>/tours/ whose tour file is gone (a hand-written file there is never touched)."""
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.html")):
        if path in pages or not path.is_file():
            continue
        try:
            head = P.read_project_head(path).decode("utf-8", errors="replace")
        except OSError:
            continue
        if P.is_prototype_page(head):  # an empty one too: what a build cut short leaves
            found.append(path)
    return found


def not_plumbs(paths, root: Path, rel) -> List[str]:
    """The pages among `paths` that exist but this script did not write (another tool's page, or one written by hand),
    project-relative: never replaced."""
    found = []
    for path in paths:
        if path.suffix != ".html" or not path.is_file():
            continue
        try:
            head = P.read_project_head(path).decode("utf-8", errors="replace")
        except OSError:
            continue  # unreadable: the write reports it; never taken for someone else's page
        if not P.is_prototype_page(head):
            found.append(rel(path, root))
    return found


_arg = P.shell_word


def _move_targets(found: List[str], root: Path) -> List[str]:
    """Where to move each page that is in the way: <name>.before-plumb.html next to it (a tour page's one folder up:
    every page in tours/ is the build's), with -2, -3 … when that name is taken or already chosen for another page."""
    taken: set = set()
    out = []
    for page in found:
        folder, _, name = page.rpartition("/")
        if folder.rpartition("/")[2] == "tours":
            folder = folder.rpartition("/")[0]
        stem = (f"{folder}/" if folder else "") + name[: -len(".html")]
        target, n = f"{stem}.before-plumb.html", 1
        while target in taken or (root / target).exists():
            n += 1
            target = f"{stem}.before-plumb-{n}.html"
        taken.add(target)
        out.append(target)
    return out


def _moves(found: List[str], root: Path) -> str:
    return "; ".join(f"mv {_arg(f)} {_arg(t)}" for f, t in zip(found, _move_targets(found, root)))


def not_plumbs_error(found: List[str], root: Path, again: str) -> PlumbError:
    one = len(found) == 1
    return _err(f"{', '.join(found)} {'is' if one else 'are'} not Plumb's (not written by build-prototype.py), and this "
                f"build writes {'that path' if one else 'those paths'}: nothing was written",
                f"ask the user before moving {'it' if one else 'them'} out of the way ({_moves(found, root)}), then run "
                f"{again} again")


def not_plumbs_lines(found: List[str], root: Path, again: str) -> List[str]:
    return [f"not Plumb's: {f} (another tool's page or one written by hand: the build would replace it)" for f in found] + [
        f"fix: ask the user before moving {'it' if len(found) == 1 else 'them'} out of the way ({_moves(found, root)}), "
        f"then run {again}"]


def _rerun(command: str, args: argparse.Namespace) -> str:
    """The command as it was given (its --map, --approve or --synced kept), for a refusal's fix line."""
    extra: List[str] = []
    if args.map:
        extra += ["--map", args.map, f"--route={args.route}", "--files", *(args.files or [])]
    if args.approve:
        extra += ["--approve", args.approve]
    if args.synced:
        extra += ["--synced", args.synced]
    return " ".join([command] + [_arg(x) for x in extra])


def read_template(skill_dir: Path, name: str) -> str:
    tpl = P.find_template(skill_dir, name)
    if tpl is None:
        raise _err(f"templates/{name} is missing from the skill",
                   "copy it from the Plumb plugin's assets/skill/templates/ (or run /plumb:upgrade)")
    try:
        return P.read_project_text(tpl)
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{tpl}: cannot read the template ({exc})", "restore it from the Plumb plugin's assets/skill/templates/") from None


def token_region(text: str, bt) -> Optional[str]:
    start = text.find(bt.TOKEN_BLOCK_START)
    end = text.find(bt.TOKEN_BLOCK_END, start + 1)
    return text[start:end] if start != -1 and end != -1 else None


# ---------------------------------------------------------------- proposals (--proposal NAME)


def proposal_pages(docs: Path) -> List[Path]:
    """Every generated page of every proposal: <docs>/prototype/proposals/*/index.html and */*/{prototype,screens}.html
    written by this script (a hand-written page there is never touched)."""
    base = docs / "prototype" / "proposals"
    if not base.is_dir():
        return []
    found = sorted(p for pattern in P.PROPOSAL_PAGE_GLOBS for p in base.glob(pattern))
    out = []
    for path in found:
        try:
            head = P.read_project_head(path).decode("utf-8", errors="replace")
        except OSError:
            continue
        if path.is_file() and P.is_generated_proposal_page(head):
            out.append(path)
    return out


def proposal_refresh(docs: Path, doc: dict, bt) -> Dict[Path, str]:
    """The generated proposal pages with their token region rebuilt from the tokens (only the ones that changed)."""
    out: Dict[Path, str] = {}
    for path in proposal_pages(docs):
        try:
            current = P.normalise_text(P.read_project_text(path, "utf-8", limit=P.PAGE_READ_LIMIT))
        except (OSError, UnicodeDecodeError):
            continue
        refreshed = bt.refresh_prototype_theme(current, doc)
        if refreshed is not None and refreshed != current:
            out[path] = refreshed
    return out


def read_idea(path: Path) -> Tuple[Optional[str], List[str], List[str]]:
    """idea.md: (title from `# Title`, the idea's paragraphs, the trade-offs from `- ` lines)."""
    if not path.is_file():
        return None, [], []
    try:
        text = P.normalise_text(P.read_project_text(path))
    except (OSError, UnicodeDecodeError) as exc:
        raise _err(f"{path}: cannot read the variant's idea ({exc})", "save idea.md as UTF-8 text") from None
    title, paras, trade, cur = None, [], [], []
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("# ") and title is None:
            title = line[2:].strip() or None
        elif line.startswith(("- ", "* ")):
            trade.append(line[2:].strip())
        elif line:
            cur.append(line)
            continue
        if cur:
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    return title, paras, trade


def inside_or_refuse(path: Path, parent: Path, root: Path, rel) -> None:
    """Refuse a proposal or variant folder that resolves outside where it sits (a symlink to somewhere else): pages are
    written into it, so it must stay inside the proposals folder."""
    try:
        path.resolve().relative_to(parent)
    except ValueError:
        raise _err(f"{rel(path, root)} leads outside {rel(parent, root)} (a link to another folder), so nothing is "
                   f"written there", f"replace the link with a real folder inside {rel(parent, root)}/ (copy the "
                   f"variant's screen files into it), then run the command again") from None


def proposal_entry(s: Screen) -> dict:
    return {"id": s.id, "title": s.title, "states": list(s.states), "route": None, "files": [], "files_hash": None,
            "approved": None, "synced_from_code": False, "status": "proposal"}


def variant_card(name: str, title: str, paras: List[str], trade: List[str], screens: List[Screen]) -> str:
    states = sum(len(s.states) for s in screens)
    listed = ", ".join(s.title for s in screens)
    idea = "".join(f'<p class="idea">{inline(p)}</p>' for p in paras)
    tradeoffs = ('<ul class="tradeoffs">' + "".join(f"<li>{inline(x)}</li>" for x in trade) + "</ul>") if trade else ""
    return (f'    <li class="variant" data-variant="{_e(name)}"><p class="letter">{_e(name)}</p><h2>{_e(title)}</h2>'
            f'{idea}{tradeoffs}<p class="screens">{len(screens)} screen{"s" if len(screens) != 1 else ""}, {states} '
            f'state{"s" if states != 1 else ""}: {_e(listed)}</p><p class="views">'
            f'<a class="view primary" href="{_e(name)}/prototype.html">Review: prototype.html</a>'
            f'<a class="view" href="{_e(name)}/app.html">Demo: app.html</a>'
            f'<a class="view" href="{_e(name)}/screens.html">Every state, light and dark</a></p></li>')


def changes_list(changes: Optional[List[dict]], used_in: Dict[str, List[str]]) -> str:
    """The proposal's changes.md as the index's Changes section: each id as a chip, its title and why, and where it is
    used (variant: screen). Empty when there is no changes.md or it lists nothing."""
    if not changes:
        return ""
    items = []
    for c in changes:
        title = f"<strong>{inline(c['title'])}</strong>" if c["title"] else ""
        why = (": " if title else "") + inline(c["why"]) if c["why"] else ""
        where = used_in.get(c["id"], [])
        place = (f'<span class="where">{_e("In " + ", ".join(where))}</span>' if where
                 else '<span class="where">No screen uses it yet</span>')
        items.append(f'<li class="change" id="change-{_e(c["id"])}"><span class="chip">{_e(c["id"])}</span>'
                     f'<span class="change-text">{title}{why}</span>{place}</li>')
    return ('<section class="changes" aria-labelledby="changes-h"><h2 id="changes-h">Changes</h2>'
            '<p class="changes-lede">Each id marks the elements it changed (data-guide); the Guide panel of every '
            'prototype shows it.</p><ul class="change-list" role="list">' + "".join(items) + "</ul></section>")


def run_proposal(args: argparse.Namespace, skill_dir: Path, root: Path, doc: dict, settings: dict, docs: Path,
                 command: str, bt, tokens_file: Path) -> int:
    rel = bt.rel
    name = args.proposal
    base = docs / "prototype" / "proposals" / name
    again = f"{command} --proposal {name}"
    if not base.is_dir():
        raise _err(f"{rel(base, root)}/: no such proposal",
                   f"write the variants first with /plumb:prototype <screen> (screen files in {rel(base, root)}/<variant>/screens/)")
    proposals_root = (docs / "prototype" / "proposals").resolve()
    inside_or_refuse(base, proposals_root, root, rel)
    folders = sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
    if not folders:
        raise _err(f"{rel(base, root)}/ has no variant folders",
                   f"write each variant's screen files in {rel(base, root)}/<variant>/screens/<id>.html, then run {again}")
    project_name = str(settings.get("project") or "").strip() or "Product"
    tokens_rel = rel(tokens_file, root)
    script_rel = rel(skill_dir / SCRIPT_REL, root)
    shell = read_template(skill_dir, SHELL_TEMPLATE)
    app_tpl = read_template(skill_dir, APP_TEMPLATE)
    catalogue_tpl = read_template(skill_dir, CATALOGUE_TEMPLATE)
    player_css, player_js = read_template(skill_dir, PLAYER_CSS), read_template(skill_dir, PLAYER_JS)
    chrome_roles = read_template(skill_dir, ROLES_CSS)
    files: Dict[Path, str] = {}
    variant_screens: List[Screen] = []
    cards, summary = [], []
    shared_warnings: List[str] = []
    used_in: Dict[str, List[str]] = {}
    for folder in folders:
        if not _ID.match(folder.name):
            raise _err(f"{rel(folder, root)}: a variant folder name may hold only letters, digits, _ and -",
                       "rename the folder, e.g. a-calm-list")
        screens_dir = folder / "screens"
        inside_or_refuse(folder, base.resolve(), root, rel)
        inside_or_refuse(screens_dir, base.resolve(), root, rel)
        if not screen_files(screens_dir):
            raise _err(f"{rel(folder, root)}: variant {folder.name} has no screen files in screens/",
                       f"write its screens as {rel(screens_dir, root)}/<id>.html (or remove the folder), then run {again}")
        shared = load_shared(screens_dir, root, rel)
        check_shared(shared)
        screens = load_screens(screens_dir, root, rel, shared)
        check_screens(screens)
        variant_screens += screens
        shared_warnings += shared_warning_lines(shared)
        for s in screens:
            for cid in guide_ids(s):
                used_in.setdefault(cid, []).append(f"{folder.name}: {s.title}")
        title, paras, trade = read_idea(folder / "idea.md")
        title = title or state_label(folder.name)
        header = (f"GENERATED by {script_rel} --proposal {name} from {rel(screens_dir, root)}/*.html and {tokens_rel}. "
                  f"Do not edit: edit the variant's screen files, then run build-prototype.py --proposal {name}.")
        ctx = {
            "screens": screens, "entries": {s.id: proposal_entry(s) for s in screens}, "decisions": [],
            "header": header, "project": f"{project_name} · {title}", "screens_rel": rel(screens_dir, root) + "/",
            "decisions_rel": rel(docs / "decisions.md", root), "tours": [], "tours_rel": "", "tokens_rel": tokens_rel,
            "script_rel": script_rel, "player_css": player_css, "player_js": player_js, "base_project": project_name,
            "shared": shared, "chrome_roles": chrome_roles,
        }
        ctx["styles"], ctx["scripts"] = page_parts(screens, shared)
        ctx["theme_css"] = bt.prototype_theme_css(doc, scoped=False)
        files[folder / "prototype.html"] = build_prototype(ctx, shell)
        files[folder / "app.html"] = build_app(ctx, app_tpl)
        ctx["theme_css"] = bt.prototype_theme_css(doc, scoped=True)
        files[folder / "screens.html"] = build_catalogue(ctx, catalogue_tpl, bt)
        cards.append(variant_card(folder.name, title, paras, trade, screens))
        summary.append(f"{folder.name}: {len(screens)} screen{'s' if len(screens) != 1 else ''}")
    changes_path = base / "changes.md"
    changes = read_changes(changes_path, root, rel)
    id_warnings = check_change_ids(variant_screens, changes, rel(changes_path, root), again, f"proposal {name}")
    values = {
        "header": f"<!-- {_e(f'GENERATED by {script_rel} --proposal {name} from {rel(base, root)}/*/screens/*.html, idea.md and {tokens_rel}. Do not edit: run build-prototype.py --proposal {name}.')} -->",
        "title": _e(f"{project_name}: {name} proposal"),
        "project": _e(project_name),
        "name": _e(name),
        "count": _e(f"{len(folders)} variant{'s' if len(folders) != 1 else ''} for {name}"),
        "plumb_version": _e(P.PLUMB_VERSION),
        "theme_css": bt.prototype_theme_css(doc, scoped=False),
        "variants": "\n".join(cards),
        "changes": changes_list(changes, used_in),
        "source": _e(rel(base, root) + "/"),
        "rerun": _e(again),
    }
    index = P.fill_template(read_template(skill_dir, INDEX_TEMPLATE), values, INDEX_TEMPLATE)
    files[base / "index.html"] = index if index.endswith("\n") else index + "\n"
    line = f"proposal {name}: {len(folders)} variant{'s' if len(folders) != 1 else ''} ({', '.join(summary)})"

    warning = size_warnings(files, root, rel, again, variant_screens)
    for line_ in shared_warnings + id_warnings:
        print(line_, file=sys.stderr)
    foreign = not_plumbs(files, root, rel)
    if args.check:
        if foreign:
            print("\n".join(not_plumbs_lines(foreign, root, again)))
            return 1
        stale = []
        for path, text in files.items():
            try:
                current = (P.normalise_text(P.read_project_text(path, "utf-8", "replace", P.PAGE_READ_LIMIT)) if path.exists()
                           else None)
            except OSError:
                current = None
            if current != text:
                stale.append(f"stale: {rel(path, root)}" + (" (missing)" if current is None else ""))
        if warning:  # --check builds every page in memory: a page over the limit is said here too (exit code unchanged)
            print(warning, file=sys.stderr)
        if stale:
            print("\n".join(stale))
            print(f"fix: {again}")
            return 1
        print(f"ok: {line}: up to date")
        return 0
    if foreign:
        raise not_plumbs_error(foreign, root, again)
    wrote = 0
    for path, text in files.items():
        try:
            current = P.read_project_bytes(path, P.PAGE_READ_LIMIT) if path.exists() else None
        except OSError:
            current = None
        if current == text.encode("utf-8"):
            continue
        if not bt._write(path, text, root):
            return 2
        wrote += 1
        print(f"wrote {rel(path, root)}")
    if warning:
        print(warning, file=sys.stderr)
    print(line if wrote else f"ok: {line}: up to date")
    print(f"open {rel(base / 'index.html', root)} to compare them")
    return 0


# ---------------------------------------------------------------- cli


def _script_command() -> str:
    """python3 <this script, relative to the project root>, as the other refusals name it."""
    skill_dir = Path(__file__).resolve().parents[1]
    try:
        bt = _load_build_tokens()
        return f"python3 {bt.rel(skill_dir / SCRIPT_REL, bt.find_project_root(skill_dir))}"
    except Exception:  # noqa: BLE001 - only the wording of a usage line depends on it
        return f"python3 {SCRIPT_REL}"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: {_script_command()} {USAGE}\n")

    def refuse(self, message: str, fix: str) -> None:
        """A refusal whose fix is one exact command rather than the usage line."""
        self.exit(2, f"error: {message}\nfix: {fix}\n")


def main(argv: Optional[List[str]] = None) -> int:
    P.utf8_stdio()
    parser = _Parser(prog="build-prototype.py",
                     description="Assemble prototype.html, app.html, screens.html and screens.json.")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 when an output is stale or missing")
    parser.add_argument("--map", metavar="ID", help="set the route and source files of a screen")
    parser.add_argument("--route", metavar="ROUTE", help="the screen's route, e.g. /billing (with --map)")
    parser.add_argument("--files", metavar="GLOB", nargs="+", help="source files or globs, relative to the project root")
    parser.add_argument("--approve", metavar="ID", help="record your approval of a screen")
    parser.add_argument("--synced", metavar="ID", help="mark a screen as updated from already-built code")
    parser.add_argument("--proposal", metavar="NAME",
                        help="build the variants in <docs>/prototype/proposals/NAME/ (both views each + index.html)")
    parser.add_argument("--check-tour", metavar="FILE",
                        help="validate one tour file against the screens and warn about frame widths; writes nothing")
    parser.add_argument("--root", metavar="SKILL_DIR", help="the design-system skill folder (default: this script's skill)")
    parser.add_argument("--project", metavar="PATH", help="project root when no PLUMB.md is found above the skill")
    args = parser.parse_args(argv)
    if (args.route is not None or args.files is not None) and not args.map:
        parser.error("--route and --files go with --map ID")
    if args.map and (not (args.route or "").strip() or not args.files):
        missing = " and ".join(f for f, v in (("--route", (args.route or "").strip()), ("--files", args.files)) if not v)
        parser.error(f"--map {args.map} needs {missing}")
    if args.check and (args.map or args.approve or args.synced):
        parser.error("--check writes nothing, so it does not combine with --map, --approve or --synced")
    if args.check_tour is not None and (args.check or args.map or args.approve or args.synced or args.proposal):
        parser.error("--check-tour FILE checks one tour file and writes nothing; run it on its own")
    if args.proposal is not None:
        if args.map or args.approve or args.synced:
            parser.error("--proposal builds the variants only; run --map, --approve or --synced on their own")
        if not _ID.match(args.proposal):
            # the name cleaned up into a folder name ("nav refresh" -> nav-refresh), or an example when nothing is left
            fixed = re.sub(r"[^\w-]+", "-", args.proposal).strip("-") or "nav-refresh"
            fixed = fixed if _ID.match(fixed) else "nav-refresh"
            parser.refuse(f"--proposal takes the proposal's folder name (letters, digits, _ and -), got {args.proposal!r}",
                          f"use a proposal name of letters, digits, _ and -, e.g. {_script_command()} --proposal {fixed}")
    skill_dir = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    project = Path(args.project) if args.project else None
    try:
        return _run(args, skill_dir, project)
    except PlumbError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        print(f"error: unexpected input ({type(exc).__name__}: {exc})\n"
              f"fix: check the tokens file against reference/tokens-format.md and the screen files against "
              f"reference/prototypes.md", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace, skill_dir: Path, project: Optional[Path]) -> int:
    bt = _load_build_tokens()
    rel = bt.rel
    root = bt.find_project_root(skill_dir, project)
    tokens_file = bt.find_tokens_file(skill_dir)
    doc = P.load_tokens(tokens_file)
    settings = P.plumb_settings(doc)
    docs_setting = str(settings.get("docs_dir") or "docs/design").rstrip("/")
    docs = bt.safe_copy_path(root, docs_setting, "$extensions.plumb.docs_dir")
    folder = docs / "prototype" / "screens"
    proto_path, cat_path, map_path = docs / "prototype.html", docs / "screens.html", docs / "prototype" / "screens.json"
    app_path = docs / "app.html"
    decisions_path = docs / "decisions.md"
    command = f"python3 {rel(skill_dir / SCRIPT_REL, root)}"
    if args.proposal is not None:
        return run_proposal(args, skill_dir, root, doc, settings, docs, command, bt, tokens_file)
    has_screens = bool(screen_files(folder))
    if not has_screens:
        if args.check:
            print(f"ok: no screen files in {rel(folder, root)}/ yet: no prototype to check")
            return 0
        raise _err(f"no screen files in {rel(folder, root)}/",
                   "write the first screen with /plumb:prototype <screen> (one <id>.html per screen)")
    shared = load_shared(folder, root, rel)
    screens = load_screens(folder, root, rel, shared)
    by_id = {s.id: s for s in screens}
    changes_path = docs / "prototype" / "changes.md"
    if args.check_tour is not None:
        check_shared(shared)
        check_screens(screens)
        return check_tour_file(args.check_tour, root, docs, screens, rel, folder, command, shared)
    tours_folder, pages_folder = docs / "prototype" / "tours", docs / "tours"
    mutating = bool(args.map or args.approve or args.synced)
    tour_error: Optional[PlumbError] = None
    blocked_by = "a tour is broken"
    id_warnings: List[str] = []
    try:
        check_shared(shared)
        check_screens(screens)
        changes = read_changes(changes_path, root, rel)
        # change ids in the main screens are checked only when the prototype keeps a change list
        if changes is not None:
            id_warnings = check_change_ids(screens, changes, rel(changes_path, root), command, "the prototype")
    except PlumbError as exc:
        if not mutating:
            raise
        # like a broken tour: --map / --approve / --synced still record the map; the pages wait for the fix
        tour_error, blocked_by = exc, "a shared file, a screen file or a change id is refused"
    try:
        tours = load_tours(tours_folder, screens, root, rel, rel(folder, root) + "/")
    except PlumbError as exc:
        if not mutating:
            raise
        # --map / --approve / --synced change the screen map, not the tours: record the change and say the pages wait
        tours = []
        if tour_error is None:
            tour_error = exc
    old = read_map(map_path, rel(map_path, root))
    for flag in ("map", "approve", "synced"):
        sid = getattr(args, flag)
        if sid and sid not in by_id:
            known = ", ".join(s.id for s in screens)
            raise _err(f"--{flag} {sid}: no such screen (screens: {known})",
                       f"write {rel(folder, root)}/{sid}.html first (/plumb:prototype {sid}), or use one of the ids listed")
    entries = {s.id: map_entry(s, old.get(s.id), root, rel(map_path, root)) for s in screens}
    done: List[str] = []
    if args.map:
        globs = []
        for raw in args.files:
            globs += [safe_glob(g) for g in raw.split(",") if g.strip()]
        e = entries[args.map]
        e["route"], e["files"] = args.route.strip(), globs
        e["files_hash"], e["status"] = files_state(root, globs)
        done.append(f"mapped {args.map} to {e['route']} ({len(globs)} source glob{'s' if len(globs) != 1 else ''}, "
                    f"{STATUS_TEXT[e['status']].lower()})")
    if args.synced:
        e = entries[args.synced]
        e["synced_from_code"] = True
        e["files_hash"] = files_state(root, e["files"])[0]
        done.append(f"marked {args.synced} as synced from code\n"
                    f"ask the user: does screen {args.synced} in {rel(proto_path, root)}#screen-{args.synced} show what "
                    f"they want? Only after their yes to that screen, record it: "
                    f"{command} --approve {args.synced}")
    if args.approve:
        e = entries[args.approve]
        e["approved"] = {"by": approver(root), "at": datetime.date.today().isoformat(), "hash": by_id[args.approve].hash}
        if shared:  # which shared files the approval saw, so a later change to one is named (stale_reason)
            e["approved"]["shared"] = dict(shared_hashes(shared))
        e["synced_from_code"] = False
        e["files_hash"] = files_state(root, e["files"])[0]
        done.append(f"approved {args.approve} ({e['approved']['by']}, {e['approved']['at']})")

    decisions: List[dict] = []
    if decisions_path.exists():
        try:
            decisions = parse_decisions(P.read_project_text(decisions_path, limit=P.PAGE_READ_LIMIT))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"warning: cannot read {rel(decisions_path, root)} ({exc}): the decision panels are empty\n"
                  f"fix: save {rel(decisions_path, root)} as UTF-8", file=sys.stderr)
    for e in decisions:
        unknown = [n for n in e["screens"] if not any(n.casefold() == s.id.casefold() for s in screens)]
        if unknown and not args.check:
            print(f"note: {e['id']} names screen(s) with no screen file: {', '.join(unknown)}")

    tokens_rel = rel(tokens_file, root)
    header = (f"GENERATED by {rel(skill_dir / SCRIPT_REL, root)} from {rel(folder, root)}/*.html, "
              f"{rel(decisions_path, root)} and {tokens_rel}. Do not edit: edit the screen files, then run build-prototype.py.")
    if tour_error is not None:
        text = map_text([entries[s.id] for s in screens], header)
        try:
            current = P.read_project_bytes(map_path, P.PAGE_READ_LIMIT) if map_path.exists() else None
        except OSError:
            current = None
        if current != text.encode("utf-8"):
            if not bt._write(map_path, text, root):
                return 2
            print(f"wrote {rel(map_path, root)}")
        for line in done:
            print(line)
        problem = re.sub(r", then run \S.*$", "", str(tour_error).replace("error: ", "", 1)).split("\nfix: ", 1)
        print(f"warning: the pages were not rebuilt because {blocked_by}: {problem[0]}\n"
              f"fix: {problem[1] if len(problem) > 1 else 'fix the file it names'}, then run {command}", file=sys.stderr)
        return 0
    project_name = str(settings.get("project") or "").strip() or "Product"
    ctx = {
        "screens": screens, "entries": entries, "decisions": decisions, "header": header, "project": project_name,
        "base_project": project_name,
        "screens_rel": rel(folder, root) + "/", "decisions_rel": rel(decisions_path, root),
        "shared": shared, "tours": tours,
        "tours_rel": rel(tours_folder, root) + "/", "tokens_rel": tokens_rel, "script_rel": rel(skill_dir / SCRIPT_REL, root),
        "player_css": read_template(skill_dir, PLAYER_CSS), "player_js": read_template(skill_dir, PLAYER_JS),
        "chrome_roles": read_template(skill_dir, ROLES_CSS),
        "app_header": (f"GENERATED by {rel(skill_dir / SCRIPT_REL, root)} from {rel(folder, root)}/*.html and "
                       f"{tokens_rel}. Do not edit: edit the screen files, then run build-prototype.py."),
    }
    ctx["styles"], ctx["scripts"] = page_parts(screens, shared)
    ctx["theme_css"] = bt.prototype_theme_css(doc, scoped=False)
    shell = read_template(skill_dir, SHELL_TEMPLATE)
    proto = build_prototype(ctx, shell)
    app_tpl = read_template(skill_dir, APP_TEMPLATE)
    app = build_app(ctx, app_tpl)
    # a tour page follows its tour's view: the app view with the player on top (the default), or the prototype page
    tour_pages = {pages_folder / f"{t['id']}.html": build_app(ctx, app_tpl, t) if t["view"] == "app"
                  else build_prototype(ctx, shell, t) for t in tours}
    ctx["theme_css"] = bt.prototype_theme_css(doc, scoped=True)
    catalogue = build_catalogue(ctx, read_template(skill_dir, CATALOGUE_TEMPLATE), bt)
    files = {proto_path: proto, app_path: app, cat_path: catalogue,
             map_path: map_text([entries[s.id] for s in screens], header)}
    files.update(tour_pages)
    files.update(proposal_refresh(docs, doc, bt))
    orphans = orphan_tour_pages(pages_folder, tour_pages)
    count = f"{len(screens)} screens, {len(tours)} tour{'s' if len(tours) != 1 else ''}"
    size_warning = size_warnings(files, root, rel, command, screens)

    foreign = not_plumbs(files, root, rel)
    if args.check:
        if foreign:
            for line in not_plumbs_lines(foreign, root, command):
                print(line)
            return 1
        stale = []
        for path, text in files.items():
            try:
                current = (P.normalise_text(P.read_project_text(path, "utf-8", "replace", P.PAGE_READ_LIMIT)) if path.exists()
                           else None)
            except OSError:
                current = None
            if current == text:
                continue
            if current is None:
                stale.append(f"stale: {rel(path, root)} (missing)")
            elif path.suffix == ".html" and token_region(current, bt) != token_region(text, bt):
                stale.append(f"stale: {rel(path, root)} (token block: the tokens changed since the last build)")
            else:
                stale.append(f"stale: {rel(path, root)}")
        stale += [f"stale: {rel(path, root)} (its tour file is gone)" for path in orphans]
        for line in shared_warning_lines(shared) + id_warnings:
            print(line, file=sys.stderr)
        if size_warning:  # --check builds every page in memory: a page over the limit is said here too (exit code unchanged)
            print(size_warning, file=sys.stderr)
        if stale:
            print("\n".join(stale))
            print(f"fix: {command}")
            return 1
        print(f"ok: {len(files)} generated files are up to date ({count})")
        return 0

    if foreign:
        raise not_plumbs_error(foreign, root, _rerun(command, args))
    for s in screens:
        for line in s.warnings[:5]:
            print(f"warning: {line}", file=sys.stderr)
        if len(s.warnings) > 5:
            print(f"warning: {s.rel}: {len(s.warnings) - 5} more style rules like these", file=sys.stderr)
        if s.warnings:
            print(f"fix: start each selector in {s.rel} with [data-screen=\"{s.id}\"]", file=sys.stderr)
    for line in shared_warning_lines(shared) + id_warnings:
        print(line, file=sys.stderr)
    removed = sorted(set(old) - set(by_id))
    for sid in removed:
        print(f"note: screen {sid} has no file any more: removed from {rel(map_path, root)}")
    wrote = 0
    for path, text in files.items():
        try:
            current = P.read_project_bytes(path, P.PAGE_READ_LIMIT) if path.exists() else None
        except OSError:
            current = None
        if current == text.encode("utf-8"):
            continue
        if not bt._write(path, text, root):
            return 2
        wrote += 1
        print(f"wrote {rel(path, root)}")
    for path in orphans:
        try:
            path.unlink()
        except OSError as exc:
            print(f"error: cannot remove {rel(path, root)} ({exc})\nfix: delete it by hand: its tour file is gone",
                  file=sys.stderr)
            return 2
        wrote += 1
        print(f"removed {rel(path, root)} (its tour file is gone)")
    if orphans and pages_folder.is_dir() and not any(pages_folder.iterdir()):
        try:
            pages_folder.rmdir()
        except OSError:
            pass
    if size_warning:
        print(size_warning, file=sys.stderr)
    for line in done:
        print(line)
    states = {s.id: approval_state(entries[s.id], s) for s in screens}
    for s in screens:
        appr = entries[s.id]["approved"]
        if states[s.id] == "stale":
            why = stale_reason(entries[s.id], s, shared, rel(folder, root) + "/")
            print(f"note: screen {s.id} changed since {appr['by']} approved it on {appr['at']}{why}\n"
                  f"ask the user: approve screen {s.id} as it is now ({rel(proto_path, root)}#screen-{s.id})? Only after "
                  f"their yes to that screen, record it: {command} --approve {s.id}")
    counts = {k: sum(1 for v in states.values() if v == k) for k in APPROVAL_TEXT}
    to_build = sum(1 for s in screens if entries[s.id]["status"] == "to-build")
    if not wrote:
        extra = f" and {len(tour_pages)} tour page{'s' if len(tour_pages) != 1 else ''}" if tour_pages else ""
        print(f"ok: {rel(proto_path, root)}, {rel(app_path, root)}, {rel(cat_path, root)} and "
              f"{rel(map_path, root)}{extra} are up to date")
    if tours:
        print(f"{len(tours)} tour{'s' if len(tours) != 1 else ''}: "
              + ", ".join(f"{t['id']} ({len(t['steps'])} steps, {t['mode']} mode)" for t in tours))
    print(f"{len(screens)} screens: {counts['approved']} approved, {counts['stale']} changed since approval, "
          f"{counts['synced']} synced from code, {counts['none']} not approved; {to_build} to build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
