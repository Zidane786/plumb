#!/usr/bin/env python3
"""Plumb Stop hook: the end-of-turn check (PLUMB.md `End-of-turn check: on`).

Compares the UI files and prototype screen files with the session snapshot session_start.py took (audit.changed_since;
no snapshot yet: it takes one now and stays quiet). No UI file changed: silent. Otherwise it runs the project's
audit on the changed files, in-process, as `audit.py --changed SNAPSHOT` does (audit.changed_findings): the errors each
changed file gained this session, a new route with no prototype, and prototype sync (a built screen whose source files
changed while its screen file did not; a screen that changed and is not approved).

- New errors: {"decision": "block", "reason": "<the list, at most 10, each error: + fix:>"} on stdout, so the agent
  goes on to fix them or say why not. It blocks once per finding: findings already blocked on this session (kept in
  <snapshot>.blocked.json) and any run with stop_hook_active true (the agent is already continuing because of this
  hook) only report them as {"systemMessage": ...}, so it can never loop.
- No errors: one line, "Plumb: N UI files checked, consistent".

GitHub Copilot CLI: whether a plugin's Stop hook reaches Copilot's agentStop and can make the agent continue is not
verified yet (spec §17); the hook answers it with the same JSON, and live testing decides. Without that, the edit check
stays the hard guard there.

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
        lines.append(f"fix: {f.fix}")
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
    path = H.snapshot_path(proj.root, p.session_id)
    A = H.load_script(proj, "audit.py", "plumb_audit")
    if A is None:
        return 0
    try:
        doc = A.load_doc(proj.skill_dir)
        settings = A.make_settings(proj.root, doc)
        if not path.is_file():
            H.write_json(path, A.take_snapshot(proj.root, proj.skill_dir, settings))
            return 0
        snap = A.read_snapshot(path)
        changes = A.changed_since(snap, proj.root, proj.skill_dir, settings)
        if not changes:
            return 0
        findings, checked = A.changed_findings(snap, proj.root, proj.skill_dir, doc, settings, A.find_tokens(proj.skill_dir),
                                               changes)
    except Exception as exc:  # noqa: BLE001 - the end-of-turn check never breaks the turn
        H.note(f"the end-of-turn check was skipped ({type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''})")
        return 0
    errors = [f for f in findings if f.severity == "error"]
    if not errors:
        if checked:
            print(f"Plumb: {checked} UI file{'' if checked == 1 else 's'} checked, consistent")
        return 0
    n = len(errors)
    blocked_path = path.with_name(path.name[:-len(".json")] + ".blocked.json")
    try:
        seen = set(json.loads(blocked_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        seen = set()
    keys = [_key(f) for f in errors]
    if not p.stop_hook_active and any(k not in seen for k in keys):
        try:
            H.write_json(blocked_path, sorted(seen | set(keys)))
        except OSError:
            pass  # without the record the next turn may block again: still never a loop (stop_hook_active)
        head = (f"Plumb end-of-turn check: {n} new design-system error{'' if n == 1 else 's'} in the files changed this "
                f"session. Fix them now, or tell the user why not (this check stops you once):")
        print(json.dumps({"decision": "block", "reason": "\n".join([head] + _listing(proj, errors))}))
        return 0
    head = f"Plumb end-of-turn check: {n} design-system error{'' if n == 1 else 's'} remain in the files changed this session:"
    print(json.dumps({"systemMessage": "\n".join([head] + _listing(proj, errors))}))
    return 0


if __name__ == "__main__":
    H.utf8_stdio()
    try:
        code = main()
    except Exception as _exc:  # noqa: BLE001
        H.note(f"end-of-turn check skipped ({type(_exc).__name__})")
        code = 0
    sys.exit(code)
