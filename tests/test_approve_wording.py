"""No script or hook output tells the agent to run build-prototype.py --approve on its own: every message that names
the command asks the user first ("ask the user: ... Only after their yes to that screen, record it: ... --approve ID"),
and the audit and the hooks print that way out as an `ask the user:` line, not a `fix:` line."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/plumb"
SOURCES = sorted([*(PLUGIN / "hooks").glob("*.py"), *(PLUGIN / "scripts").glob("*.py"),
                  *(PLUGIN / "assets/skill/scripts").glob("*.py")])
SUGGESTION = re.compile(r"(?<!\[)--approve (?:\{|ID\b|<)")  # a command line handed to the agent, not argparse or prose


def test_every_approve_suggestion_asks_the_user_first() -> None:
    for path in SOURCES:
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if SUGGESTION.search(line) and "add_argument" not in line:
                around = " ".join(lines[max(0, i - 4):i + 4])
                assert re.search(r"[Oo]nly after|ask the user|_ask_approve", around), f"{path.name}:{i + 1}: {line.strip()}"
                if "ask the user:" in around:  # one wording everywhere: the yes comes before the command
                    assert re.search(r"[Oo]nly after[\s\"f]*their yes", around), f"{path.name}:{i + 1}: {line.strip()}"


def test_audit_prints_ask_the_user_lines_as_they_are() -> None:
    sys.path.insert(0, str(PLUGIN / "assets/skill/scripts"))
    spec = importlib.util.spec_from_file_location("plumb_audit_wording", PLUGIN / "assets/skill/scripts/audit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plumb_audit_wording"] = mod
    spec.loader.exec_module(mod)
    assert mod.fix_line("ask the user: approve screen a? Only after their yes, record it: x --approve a") \
        .startswith("ask the user: ")
    assert mod.fix_line("use bg-primary") == "fix: use bg-primary"
    for name in ("stop_check.py", "pre_edit.py"):
        assert 'f.fix if f.fix.startswith("ask the user:") else f"fix: {f.fix}"' in (PLUGIN / "hooks" / name).read_text(
            encoding="utf-8")
