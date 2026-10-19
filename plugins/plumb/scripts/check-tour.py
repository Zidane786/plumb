#!/usr/bin/env python3
"""check-tour.py: play a tour page in a headless browser already on this machine and check every step.

    check-tour.py <docs>/tours/<id>.html [--width 1280 --width 1440] [--browser PATH] [--timeout S]

Used by /plumb:tour after build-prototype.py wrote the tour page (and after `build-prototype.py --check-tour`, the static
check). Plumb installs and downloads nothing: it only runs a Chrome, Edge or Chromium that is already installed, found
with screenshot.py's search (the PATH names, then the usual install folders), or the one --browser names.

It copies the page into a scratch folder (<project>/.plumb-tmp/ inside a Plumb project, i.e. a PLUMB.md at or above
the page; else the system's temp folder), with its <base> pointed at the original's folder (so images and links resolve
as they do for the original) and a checker script added. The browser opens the copy headless, light theme, once per
--width (default 1280 and 1440; the window is W x 900), with --dump-dom and --virtual-time-budget: the checker walks
every step of the page's tour in guide mode, then in play mode, through window.plumbPlayer (start at each position,
play paused at once: nothing waits real time), and per step checks:

  - the page shows the step's screen in the step's state (window.plumbPrototype.current());
  - each target, label target and action element: the match the player points at (window.plumbPlayer.node: its first
    match the player can show; with none, the reason is given for a match in the step's state) is laid out (not
    display: none), not visibility: hidden, not opacity: 0, not zero-size, inside the window once the player has scrolled to it, and not
    covered at the centre of its part clear of the panel (above it; below it while the panel is at the top of the
    window) by the walkthrough panel or a screen's own fixed or sticky layer (elementFromPoint; the player's own
    overlays are left out);
  - the dock is not covered: elementFromPoint at its centre is the dock or inside it (unless the panel is hidden).

It writes the results into the page as JSON (<pre id="plumb-tour-check">), which this script reads from the dumped DOM.
The scratch copy and the browser's throwaway profile are deleted afterwards.

  PAGE          a tour page build-prototype.py wrote (<docs>/tours/<id>.html, either view)
  --width       window width in CSS pixels, repeatable (default: 1280 and 1440)
  --browser     the browser executable to use instead of searching
  --timeout     seconds before a browser that hangs is stopped, per width (default 120)

Output: `ok: <n> steps × guide/play × 1280, 1440` (exit 0); else one line per problem,
`step 12 (Chapter › Title): the target ".x" is hidden (visibility: hidden) at 1280 (guide, play)`, and a fix: line
(exit 2). Exit codes: 0 every step passed · 1 the browser ran but gave no result (or hung) · 2 problems found or bad
input (error: then fix:) · 3 no browser found (a note: line and a fix:; the static check still runs).
On Linux, a browser that stops with "No usable sandbox" (user namespaces off, no setuid helper) is run once more with
--no-sandbox, said in a note: line (the page is a local offline copy in a throwaway profile); never otherwise, except
as root (as screenshot.py).
Python 3.9+, standard library only; no shell. Plugin-side (not copied into projects), like screenshot.py.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))

import screenshot as S  # noqa: E402 - the plugin's own browser search, scratch folder and process handling

DEFAULT_WIDTHS = (1280, 1440)
HEIGHT = 900
SETTLE_MS = 350  # page time per position before it is measured (transitions finish)
NO_BROWSER = ("note: tour check skipped: no browser found (looked for Chrome, Edge and Chromium; Plumb installs "
              "nothing)\nfix: ask the user whether a Chrome, Edge or Chromium already on this machine can be used and "
              "pass its path with --browser PATH, or check the tour by hand in the agent's own browser tool. The static "
              "check (build-prototype.py --check-tour) still runs.")
TOURS_DATA = re.compile(r'<script type="application/json" id="plumb-tours">(.*?)</script>', re.S)
RESULT = re.compile(r'<pre id="plumb-tour-check"[^>]*>(.*?)</pre>', re.S)
SANDBOX = re.compile(r"no usable sandbox|setuid sandbox|without --no-sandbox", re.I)
DONE = re.compile(r'<pre id="plumb-tour-check"[^>]*>\{"done":\s*true')
BASE = re.compile(r'<base\s+href="([^"]*)"\s*/?>', re.I)

# Catches the page's own script errors from the start (injected first in <head>).
ERRORS_JS = """<script>
window.__plumbTourErrors = [];
window.addEventListener("error", function (e) { window.__plumbTourErrors.push(String(e.message || e)); });
</script>"""

# The checker (injected before </body>, after the player). Every text it reports is plain; the result goes into a
# hidden <pre> as JSON, updated after each position, with done: true at the end.
CHECKER_JS = """<script>
(function () {
  "use strict";
  var SETTLE = %(settle)d;
  var out = { done: false, steps: 0, positions: 0, checked: 0, results: [], errors: [], fatal: "" };
  var pre = null;
  function save() {
    out.errors = (window.__plumbTourErrors || []).slice(0, 20);
    if (!pre) { pre = document.createElement("pre"); pre.id = "plumb-tour-check"; pre.hidden = true; document.body.appendChild(pre); }
    pre.textContent = JSON.stringify(out);
  }
  function describe(n) {
    if (!n || !n.tagName) return "nothing";
    var s = n.tagName.toLowerCase();
    if (n.id) s += "#" + n.id;
    var cls = (n.getAttribute("class") || "").split(/\\s+/).filter(Boolean).slice(0, 2);
    return s + cls.map(function (c) { return "." + c; }).join("");
  }
  function box(node) {
    if (getComputedStyle(node).display !== "contents") return node;
    for (var c = node.firstElementChild; c; c = c.nextElementSibling) { var b = box(c); if (b && b.getClientRects().length) return b; }
    return node;
  }
  function why(node) {
    var s = box(node), a;
    if (!s.getClientRects().length) {
      for (a = s; a; a = a.parentElement) {
        if (getComputedStyle(a).display === "none") return "hidden (display: none" + (a === s ? "" : " on " + describe(a)) + ")";
      }
      return "not laid out";
    }
    var vis = getComputedStyle(s).visibility;
    if (vis === "hidden" || vis === "collapse") return "hidden (visibility: " + vis + ")";
    for (a = s; a; a = a.parentElement) {
      if (parseFloat(getComputedStyle(a).opacity) === 0) return "hidden (opacity: 0" + (a === s ? "" : " on " + describe(a)) + ")";
    }
    var r = s.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return "zero-size (" + Math.round(r.width) + " × " + Math.round(r.height) + " px)";
    var vw = document.documentElement.clientWidth || window.innerWidth, vh = window.innerHeight;
    if (r.right <= 0 || r.left >= vw || r.bottom <= 0 || r.top >= vh) {
      return "outside the viewport (at " + Math.round(r.left) + ", " + Math.round(r.top) + ")";
    }
    /* what paints on top at the centre of its part clear of the walkthrough panel: the panel itself, or a screen's
       own fixed or sticky layer (the player's overlays take no clicks and are left out). The panel is centred with a
       maximum width, so it clips the target only where the two boxes really overlap (across and down): a corner
       toast or button beside the panel is not covered by it. The panel sits at the bottom of the window, or at its
       top for a step whose pinned target it would cover there: where it is now is read from the page, and at the
       top the part clear of it starts below its bottom edge */
    var dock = document.getElementById("pl-dock"), ceiling = 0, floor = vh;
    if (dock && !dock.hidden && dock.getClientRects().length) {
      var d = dock.getBoundingClientRect();
      if (r.right > d.left && r.left < d.right && r.bottom > d.top && r.top < d.bottom) {
        if (d.top + d.bottom < vh) ceiling = d.bottom; else floor = d.top;
      }
    }
    var top = Math.max(r.top, ceiling), bottom = Math.min(r.bottom, floor), left = Math.max(r.left, 0), right = Math.min(r.right, vw);
    if (bottom <= top) return "covered by the walkthrough panel";
    var hit = document.elementFromPoint((left + right) / 2, (top + bottom) / 2);
    if (hit && hit !== s && !s.contains(hit) && !node.contains(hit) && !hit.contains(s) && !hit.closest(".pl-layer, .pl-card")) {
      return hit.closest("#pl-dock, .pl-pill") ? "covered by the walkthrough panel" : "covered by " + describe(hit);
    }
    return "";
  }
  function check(step) {
    var A = window.plumbPrototype, problems = [];
    var cur = A.current();
    if (cur.screen !== step.screen || cur.state !== step.state) {
      problems.push("the page shows " + (cur.screen ? "screen " + cur.screen + " (" + cur.state + ")" : "no screen") +
        ", not " + step.screen + " (" + step.state + ")");
    }
    var section = A.screen(step.screen);
    var wanted = [], seen = {};
    function want(name, sel) { if (sel && !seen[sel]) { seen[sel] = 1; wanted.push([name, sel]); } }
    step.targets.forEach(function (sel) { want("the target " + JSON.stringify(sel), sel); });
    step.labels.forEach(function (lab) { want("the label " + JSON.stringify(lab.text) + " (" + lab.target + ")", lab.target); });
    if (step.action && step.action.target) want("the action's element " + JSON.stringify(step.action.target), step.action.target);
    wanted.forEach(function (w) {
      if (!section) { problems.push(w[0] + ": screen " + step.screen + " is not on the page"); return; }
      var list;
      try { list = section.querySelectorAll(w[1]); } catch (err) { problems.push(w[0] + " is not a selector the browser reads"); return; }
      if (!list.length) { problems.push(w[0] + " matches nothing on the page"); return; }
      var P = window.plumbPlayer;
      if (P && typeof P.node === "function") {
        /* the match the player points at (the first one it can show) is the one judged */
        var at = P.node(w[1]);
        if (at) { var bad = why(at); if (bad) problems.push(w[0] + " is " + bad); return; }
        /* it can show none: why, for a match in the step's state first (not one in another state) */
        var mine = [], rest = [], reason = "";
        Array.prototype.forEach.call(list, function (n) {
          var st = n.closest("[data-state]");
          (st && st.getAttribute("data-state") !== step.state ? rest : mine).push(n);
        });
        mine.concat(rest).forEach(function (n) { if (!reason) reason = why(n); });
        problems.push(w[0] + " is " + (reason || "not pointed at (the walkthrough finds no match it can show)"));
        return;
      }
      /* a page from a player without node(): any match that passes will do */
      var first = "";
      for (var i = 0; i < list.length; i++) {
        var r = why(list[i]);
        if (!r) return;
        if (!first) first = r;
      }
      problems.push(w[0] + " is " + first);
    });
    var dock = document.getElementById("pl-dock");
    if (dock && !dock.hidden) {
      var d = dock.getBoundingClientRect();
      var vw = document.documentElement.clientWidth || window.innerWidth, vh = window.innerHeight;
      var x = Math.min(Math.max(d.left + d.width / 2, 0), vw - 1), y = Math.min(Math.max(d.top + d.height / 2, 0), vh - 1);
      var hit = document.elementFromPoint(x, y);
      if (!hit || (hit !== dock && !dock.contains(hit))) problems.push("the dock is covered by " + describe(hit));
    }
    return problems;
  }
  function run() {
    var P = window.plumbPlayer, A = window.plumbPrototype, el = document.getElementById("plumb-tours");
    var data = null;
    try { data = JSON.parse(el.textContent); } catch (err) { data = null; }
    var id = data && data.autostart && data.autostart.tour;
    if (!P || !A || !id) { out.fatal = "the page has no walkthrough player or no tour to start"; out.done = true; save(); return; }
    var tour = data.tours.filter(function (t) { return t.id === id; })[0];
    var byN = {};
    tour.steps.forEach(function (s) { byN[s.n] = s; });
    out.steps = tour.steps.length;
    var modes = ["guide", "play"], mi = 0, pos = 0, total = 0;
    function begin() {
      try {
        P.start(id, { mode: modes[mi], pos: pos, focus: false });
        if (modes[mi] === "play") P.pause();
        total = P.state().total;
      } catch (err) {
        (window.__plumbTourErrors || []).push("the player failed at position " + pos + " (" + modes[mi] + "): " + err);
      }
      total = Math.max(total, pos + 1);
      out.positions = total;
      setTimeout(measure, SETTLE);
    }
    function measure() {
      var st = P.state();
      if (st.step !== null && byN[st.step]) {
        var problems;
        try { problems = check(byN[st.step]); } catch (err) { problems = ["the check failed: " + err]; }
        out.results.push({ mode: modes[mi], n: st.step, problems: problems });
      }
      out.checked += 1;
      save();
      pos += 1;
      if (pos >= total) { pos = 0; mi += 1; }
      if (mi >= modes.length) { P.leave(); out.done = true; save(); return; }
      begin();
    }
    save();
    begin();
  }
  function ready() { setTimeout(run, SETTLE); }
  if (document.readyState === "complete") ready(); else window.addEventListener("load", ready);
})();
</script>"""


def utf8_stdio() -> None:
    S.utf8_stdio()


class Refusal(S.Refusal):
    pass


# ---------------------------------------------------------------- the page


def read_page(page: Path) -> Tuple[str, dict, List[dict]]:
    """(page text, the tour it opens, its chapters); refuses a page that is not a tour page."""
    fix = ("pass a tour page build-prototype.py wrote, <docs>/tours/<id>.html (run build-prototype.py first; "
           "/plumb:tour writes the tour file)")
    if not page.is_file():
        raise Refusal(f"{page}: file not found", fix)
    try:
        text = page.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refusal(f"{page}: cannot read the page ({exc})", fix) from None
    m = TOURS_DATA.search(text)
    data = None
    if m:
        try:
            data = json.loads(m.group(1))
        except ValueError:
            data = None
    start = (data or {}).get("autostart") or {}
    tour = next((t for t in (data or {}).get("tours", []) if isinstance(t, dict) and t.get("id") == start.get("tour")), None)
    if tour is None or not isinstance(tour.get("steps"), list) or not tour["steps"]:
        raise Refusal(f"{page}: not a tour page (no walkthrough that opens with the page)", fix)
    return text, tour, tour.get("chapters") or []


def scratch_copy(text: str, page: Path) -> str:
    """The page with its <base> pointing at the original's folder (absolute), the error catcher and the checker."""
    page_uri = page.resolve().as_uri()
    m = BASE.search(text)
    if m:
        href = urljoin(page_uri, html.unescape(m.group(1)))
        text = text[:m.start()] + f'<base href="{html.escape(href, quote=True)}">' + ERRORS_JS + text[m.end():]
    else:
        head = re.search(r"<head[^>]*>", text, re.I)
        tag = f'<base href="{html.escape(urljoin(page_uri, "."), quote=True)}">' + ERRORS_JS
        text = text[:head.end()] + tag + text[head.end():] if head else tag + text
    checker = CHECKER_JS % {"settle": SETTLE_MS}
    end = text.lower().rfind("</body>")
    return text[:end] + checker + "\n" + text[end:] if end != -1 else text + checker


def budget_ms(tour: dict) -> int:
    """Page time for both modes: every position (cards and steps), measured after SETTLE_MS, plus room to load."""
    positions = len(tour["steps"]) + len(tour.get("chapters") or []) + bool(tour.get("intro")) + bool(tour.get("closing"))
    return 5000 + positions * 2 * (SETTLE_MS + 150)


# ---------------------------------------------------------------- the browser


def _linux() -> bool:
    return sys.platform.startswith("linux")


def command(browser: Path, url: str, profile: Path, width: int, budget: int) -> List[str]:
    args = [str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--disable-sync", "--disable-background-networking",
            "--disable-component-update", f"--user-data-dir={profile}", f"--window-size={width},{HEIGHT}",
            f"--virtual-time-budget={budget}", "--blink-settings=preferredColorScheme=1", "--dump-dom"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")  # Chrome refuses to start as root (containers, CI) without it
    args.append(url)
    return args


def _finished(data: bytes) -> bool:
    text = data.decode("utf-8", errors="replace")
    return bool(DONE.search(text)) and text.rstrip().lower().endswith("</html>")


def run_browser(args: List[str], dom: Path, log: Path, timeout: float) -> Optional[int]:
    """Run the browser until it exits, or until the dumped DOM is complete (a build that keeps running), or the
    timeout (None). Output goes to files, not pipes (helper processes can outlive the browser)."""
    try:
        out_fh, err_fh = open(dom, "wb"), open(log, "wb")
    except OSError as exc:
        raise Refusal(f"cannot write in {dom.parent} ({exc.strerror or exc})",
                      "check the scratch folder is writable, then run this again", 1) from None
    with out_fh, err_fh:
        try:
            proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=out_fh, stderr=err_fh,
                                    start_new_session=not S.WINDOWS)
        except OSError as exc:
            raise Refusal(f"cannot run {args[0]} ({exc.strerror or exc})",
                          "pass a working browser with --browser PATH, or check the tour in the agent's browser tool", 1) from None
        try:
            deadline = time.monotonic() + timeout
            while True:
                code = proc.poll()
                if code is not None:
                    return code
                try:
                    done = _finished(dom.read_bytes())
                except OSError:
                    done = False
                if done:
                    S._stop(proc)
                    return 0
                if time.monotonic() > deadline:
                    S._stop(proc)
                    return None
                time.sleep(S.POLL_SECONDS)
        except BaseException:
            S._stop(proc)
            raise


def parse_result(dom: str) -> Optional[dict]:
    found = RESULT.findall(dom)
    if not found:
        return None
    try:
        data = json.loads(html.unescape(found[-1]))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------- the report


def step_name(step: dict, chapters: List[dict]) -> str:
    title = step.get("title") or step.get("caption") or ""
    if len(title) > 60:
        title = title[:57].rstrip() + "..."
    ch = step.get("chapter")
    if isinstance(ch, int) and 0 <= ch < len(chapters) and chapters[ch].get("title"):
        return f"{chapters[ch]['title']} › {title}"
    return title


def report(tour: dict, chapters: List[dict], results: Dict[int, dict]) -> List[str]:
    """One line per (step, problem), with the widths and modes where it happens; page errors last."""
    where: Dict[Tuple[int, str], Dict[int, List[str]]] = {}
    order: List[Tuple[int, str]] = []
    errors: Dict[str, Dict[int, None]] = {}
    for width, data in results.items():
        for r in data.get("results", []):
            for problem in r.get("problems", []):
                key = (int(r.get("n", 0)), str(problem))
                if key not in where:
                    where[key] = {}
                    order.append(key)
                modes = where[key].setdefault(width, [])
                if r.get("mode") not in modes:
                    modes.append(str(r.get("mode")))
        for e in data.get("errors", []):
            errors.setdefault(str(e), {})[width] = None
    steps = {s.get("n"): s for s in tour["steps"]}
    lines = []
    for n, problem in sorted(order, key=lambda k: (k[0], order.index(k))):
        at = ", ".join(f"{w} ({', '.join(m)})" for w, m in where[(n, problem)].items())
        lines.append(f"step {n} ({step_name(steps.get(n, {}), chapters)}): {problem} at {at}")
    for e, widths in errors.items():
        lines.append(f"page: a script error: {e} at {', '.join(str(w) for w in widths)}")
    return lines


# ---------------------------------------------------------------- command line


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # shaped like every other refusal
        self.exit(2, f"error: {message}\nfix: python3 check-tour.py <docs>/tours/<id>.html [--width 1280 --width 1440] "
                     f"[--browser PATH]\n")


def main(argv: Optional[List[str]] = None) -> int:
    utf8_stdio()
    parser = _Parser(prog="check-tour.py", description="Play a tour page headless and check every step.")
    parser.add_argument("page", metavar="PAGE", help="the tour page, <docs>/tours/<id>.html")
    parser.add_argument("--width", type=int, action="append", metavar="W",
                        help="window width, repeatable (default 1280 and 1440)")
    parser.add_argument("--browser", metavar="PATH", help="the browser executable (default: search this machine)")
    parser.add_argument("--timeout", type=float, default=120.0, metavar="S", help="stop a hung browser (default 120)")
    args = parser.parse_args(argv)
    widths = list(dict.fromkeys(args.width or DEFAULT_WIDTHS))
    try:
        for w in widths:
            if not 320 <= w <= 10000:
                raise Refusal(f"--width {w} is out of range (320 to 10000)", "pass --width 1280 --width 1440")
        if not 0 < args.timeout <= 1800:
            raise Refusal(f"--timeout {args.timeout:g} is out of range (above 0, at most 1800 s)", "pass --timeout 120")
        page = Path(args.page)
        text, tour, chapters = read_page(page)
        if args.browser:
            browser = Path(args.browser)
            if not browser.is_file():
                raise Refusal(f"--browser {args.browser}: no such file",
                              "pass the browser's executable (e.g. the path inside Google Chrome.app/Contents/MacOS/)")
        else:
            found = S.find_browser()
            if found is None:
                print(NO_BROWSER, file=sys.stderr)
                return 3
            browser = found
        results = check(browser, page, text, tour, widths, args.timeout)
    except S.Refusal as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    lines = report(tour, chapters, results)
    n = len(tour["steps"])
    if lines:
        print("\n".join(lines))
        src = page.resolve().parent.parent / "prototype" / "tours" / f"{tour['id']}.json"
        print(f"fix: change those steps in {_shown(src)} (or the screens they point at), rebuild with "
              f"build-prototype.py, then run check-tour.py again")
        return 2
    print(f"ok: {n} step{'s' if n != 1 else ''} × guide/play × {', '.join(str(w) for w in widths)}")
    return 0


def _shown(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def check(browser: Path, page: Path, text: str, tour: dict, widths: List[int], timeout: float) -> Dict[int, dict]:
    tmp, created = S.scratch_dir(out=page)
    try:
        copy = tmp / page.name
        try:
            with open(copy, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(scratch_copy(text, page))
        except OSError as exc:
            raise Refusal(f"cannot write the scratch copy in {tmp} ({exc.strerror or exc})",
                          "check the project folder is writable, then run this again", 1) from None
        url, budget, results = copy.resolve().as_uri(), budget_ms(tour), {}
        no_sandbox = False
        fix = ("open the tour page in a browser to see whether it plays, then run this again; or pass a longer --timeout, "
               "or another Chrome, Edge or Chromium already on this machine with --browser PATH")
        for width in widths:
            for attempt in (1, 2):
                dom, log = tmp / f"dom-{width}-{attempt}.html", tmp / f"browser-{width}-{attempt}.log"
                args = command(browser, url, tmp / f"profile-{width}-{attempt}", width, budget)
                if no_sandbox and "--no-sandbox" not in args:
                    args.insert(-1, "--no-sandbox")
                code = run_browser(args, dom, log, timeout)
                if code is None:
                    raise Refusal(f"{browser.name} did not finish within {timeout:g} s at width {width}", fix, 1)
                data = parse_result(dom.read_text(encoding="utf-8", errors="replace") if dom.is_file() else "")
                said = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
                if data is None and attempt == 1 and "--no-sandbox" not in args and _linux() and SANDBOX.search(said):
                    # Linux without unprivileged user namespaces (or the setuid helper): Chrome cannot sandbox itself
                    print(f"note: {browser.name} has no usable sandbox on this machine: ran it again with --no-sandbox "
                          f"(the page is a local offline copy in a throwaway profile)", file=sys.stderr)
                    no_sandbox = True
                    continue
                break
            if data is None:
                said = S._last_line(said.encode("utf-8"))
                raise Refusal(f"{browser.name} gave no tour check result at width {width} (exit {code})"
                              + (f": {said}" if said else ""), fix, 1)
            if data.get("fatal"):
                raise Refusal(f"{page}: {data['fatal']}", "rebuild the page with build-prototype.py, then run this again")
            if not data.get("done"):
                raise Refusal(f"the tour check stopped after {data.get('checked', 0)} of {2 * int(data.get('positions') or 0)} "
                              f"positions at width {width}", fix, 1)
            results[width] = data
        return results
    finally:
        S.remove_tree(tmp)
        if created is not None:  # this run made <project>/.plumb-tmp/: leave nothing behind
            try:
                (created / ".gitignore").unlink()
                created.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
