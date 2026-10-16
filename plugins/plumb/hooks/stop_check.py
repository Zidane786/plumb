#!/usr/bin/env python3
"""Plumb Stop hook: the end-of-turn check (PLUMB.md `End-of-turn check: on`).

Compares the UI files and prototype screen files with the session snapshot session_start.py took (audit.changed_since;
no snapshot yet: it takes one now and stays quiet). No UI file changed: silent. Otherwise it runs the plugin's own
audit.py (never the project's copy: trust boundary, see _hooklib) on the changed files, in-process, as `audit.py --changed SNAPSHOT` does (audit.changed_findings): the errors each
changed file gained this session, a new route with no prototype, and prototype sync (a built screen whose source files
changed while its screen file did not; a screen that changed, or whose _shared/ CSS or JS changed, and is not approved).

- New errors: {"decision": "block", "reason": "<the list, at most 10, each error: + fix:>, then 'If the user asked you
  not to fix these now, say so and stop.'"} on stdout, so the agent goes on to fix them or say why not. It blocks once
  per finding: findings already blocked on this session (kept in <snapshot>.blocked.json) and any run with
  stop_hook_active true (the agent is already continuing because of this hook) only report them as
  {"systemMessage": ...}, so it can never loop.
- No errors: one line, "Plumb: N UI files checked, consistent".
- Quiet when nothing changed: the systemMessage and the consistent line are printed only when the set of errors
  differs from the last summary printed this session (kept in <snapshot>.summary.json), so the same errors are not
  repeated at the end of every turn.

GitHub Copilot CLI: whether a plugin's Stop hook reaches Copilot's agentStop and can make the agent continue is not
verified yet (spec §17); the hook answers it with the same JSON, and live testing decides. Without that, the edit check
stays the hard guard there.

Stands down (silent, exit 0) while <root>/.plumb-tmp/setup-in-progress exists: a Plumb setup (init, create,
extract) is running and its half-done state is expected. Only those skills write and remove that marker; other scratch
files in .plumb-tmp/ change nothing. The session snapshot is kept, so the files changed meanwhile are checked at the
first end of turn after the setup ends.

Fails open: no PLUMB.md, bad input, no design-system skill, a broken audit.py or tokens file: exit 0, at most one
stderr line. Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _hooklib as H  # noqa: E402

MAX_ISSUES = 10


def _key(f) -> str:
    return f"{f.rule}|{f.file}|{getattr(f, 'match', '') or f.message}"


def _listing(proj: H.Project, errors: list) -> List[str]:
    lines = []
    for f in errors[:MAX_ISSUES]:
        lines.append(f"error: {f.file} line {f.line}: {f.message}")
        lines.append(f.fix if f.fix.startswith("ask the user:") else f"fix: {f.fix}")
    if len(errors) > MAX_ISSUES:
        lines.append(f"... and {len(errors) - MAX_ISSUES} more: {proj.script('audit.py')} lists them all")
    return lines


def main() -> int:
    p = H.read_payload()
    if p is None:
        return 0
    proj = H.load_project(p)
    if proj is None or not proj.on("End-of-turn check") or not proj.skill_ok:
        return 0
    if H.setup_in_progress(proj.root_s):
        return 0  # a setup is running (<root>/.plumb-tmp/setup-in-progress): its half-done state is expected
    unreadable = proj.tokens_unreadable()
    if unreadable:  # the plugin's audit.py would wait on it (a FIFO, a link to a device): stay quiet
        H.note(unreadable)
        return 0
    path = H.snapshot_path(proj.root, p.session_id)
    if path is None:
        return 0  # no private temp folder (snapshot_dir said why): stay quiet
    A = H.load_script("audit.py", "plumb_audit")
    if A is None:
        return 0
    scripts = H.scripts_note(proj)
    if scripts:
        H.note(scripts + " (checked with the plugin's scripts)")
    try:
        doc = A.load_doc(proj.skill_dir)
        settings = A.make_settings(proj.root, doc)
        if not os.path.lexists(str(path)):
            H.write_json(path, A.take_snapshot(proj.root, proj.skill_dir, settings))
            return 0
        if H.read_private(path) is None:
            return 0
        snap = A.read_snapshot(path)
        changes = A.changed_since(snap, proj.root, proj.skill_dir, settings)
        if not changes:
            return 0
        findings, checked = A.changed_findings(snap, proj.root, proj.skill_dir, doc, settings, A.find_tokens(proj.skill_dir),
                                               changes)
    except Exception as exc:  # noqa: BLE001 - the end-of-turn check never breaks the turn
        H.note(f"the end-of-turn check was skipped ({type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''})")
        H.log_failure(f"the end-of-turn check was skipped ({type(exc).__name__}: {exc})",
                      "the end-of-turn check runs on the files changed this session", exc=exc)
        return 0
    errors = [f for f in findings if f.severity == "error"]
    keys = sorted({_key(f) for f in errors})
    summary_path = path.with_name(path.name[:-len(".json")] + ".summary.json")
    try:
        last = json.loads(H.read_private(summary_path) or "null")
    except (OSError, ValueError, TypeError):
        last = None
    changed = last != keys  # the summary is printed again only when the findings differ from the last one shown

    def shown() -> None:
        try:
            H.write_json(summary_path, keys)
        except OSError:
            pass  # without the record the next turn prints the summary again: noise, never a loop

    if not errors:
        if checked and changed:
            shown()
            print(f"Plumb: {checked} UI file{'' if checked == 1 else 's'} checked, consistent")
        return 0
    n = len(errors)
    blocked_path = path.with_name(path.name[:-len(".json")] + ".blocked.json")
    try:
        seen = set(json.loads(H.read_private(blocked_path) or "[]"))
    except (OSError, ValueError, TypeError):
        seen = set()
    if not p.stop_hook_active and any(k not in seen for k in keys):
        try:
            H.write_json(blocked_path, sorted(seen | set(keys)))
        except OSError:
            pass  # without the record the next turn may block again: still never a loop (stop_hook_active)
        shown()
        head = (f"Plumb end-of-turn check: {n} new design-system error{'' if n == 1 else 's'} in the files changed this "
                f"session. Fix them now, or tell the user why not (this check stops you once):")
        tail = "If the user asked you not to fix these now, say so and stop."
        print(json.dumps({"decision": "block",
                          "reason": H.tool_text("\n".join([head] + _listing(proj, errors) + [tail]))}))
        return 0
    if not changed:
        return 0  # the same errors as the last summary this session: said already
    shown()
    head = f"Plumb end-of-turn check: {n} design-system error{'' if n == 1 else 's'} remain in the files changed this session:"
    print(json.dumps({"systemMessage": H.tool_text("\n".join([head] + _listing(proj, errors)))}))
    return 0


if __name__ == "__main__":
    H.utf8_stdio()
    try:
        code = main()
    except Exception as _exc:  # noqa: BLE001
        H.note(f"end-of-turn check skipped ({type(_exc).__name__})")
        H.log_failure(f"end-of-turn check skipped ({type(_exc).__name__}: {_exc})",
                      "the end-of-turn check runs, or stays quiet", exc=_exc)
        code = 0
    sys.exit(code)
