"""Windows guard: every Python script Plumb ships or runs in CI must speak UTF-8.

Windows consoles and pipes default to cp1252, so printing "→", "·" or "—" crashes a script that
doesn't reconfigure its output, and text files or subprocess output are misread without an
explicit encoding. These checks are static, so they catch the problem on any OS.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
# Every .py under plugins/plumb (hooks, the generator and audit copied into projects, ...) and scripts/.
SCRIPTS = sorted([*(REPO / "plugins/plumb").rglob("*.py"), *(REPO / "scripts").glob("*.py")])


def calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def kw(call: ast.Call, name: str):
    return next((k for k in call.keywords if k.arg == name), None)


def fname(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    names = [node.test.left, *node.test.comparators]
    return any(isinstance(n, ast.Name) and n.id == "__name__" for n in names) and any(
        isinstance(n, ast.Constant) and n.value == "__main__" for n in names
    )


def _has_main_guard(path: Path) -> bool:
    return any(_is_main_guard(n) for n in ast.parse(path.read_text(encoding="utf-8")).body)


ENTRY_POINTS = [p for p in SCRIPTS if _has_main_guard(p)]


@pytest.mark.parametrize("path", ENTRY_POINTS, ids=lambda p: str(p.relative_to(REPO)))
def test_entry_points_reconfigure_output_to_utf8(path: Path) -> None:
    """The `if __name__ == "__main__"` block or main() must call x.reconfigure(...) or [mod.]utf8_stdio()."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    paths = [n for n in tree.body if _is_main_guard(n)]
    paths += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    found = [c for root in paths for c in calls(root) if fname(c) in ("reconfigure", "utf8_stdio")]
    assert found, f"{path.name}: the __main__ path must call .reconfigure( or utf8_stdio( to set UTF-8 output"


def test_entry_point_check_sees_real_calls_only() -> None:
    assert ENTRY_POINTS, "no entry points found"
    assert not any(p.name == "_plumb.py" for p in ENTRY_POINTS)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: str(p.relative_to(REPO)))
def test_text_io_and_subprocess_name_an_encoding(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for c in calls(tree):
        name = fname(c)
        if name in ("read_text", "write_text") and not kw(c, "encoding"):
            bad.append(f"line {c.lineno}: {name}() without encoding=")
        if name == "open" and isinstance(c.func, ast.Name):
            mode = c.args[1] if len(c.args) > 1 else (kw(c, "mode").value if kw(c, "mode") else None)
            binary = isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value
            if not binary and not kw(c, "encoding"):
                bad.append(f"line {c.lineno}: open() in text mode without encoding=")
        if name in ("run", "Popen", "check_output"):
            t = kw(c, "text") or kw(c, "universal_newlines")
            if t is not None and isinstance(t.value, ast.Constant) and t.value.value is True and not kw(c, "encoding"):
                bad.append(f"line {c.lineno}: subprocess.{name}(text=True) without encoding=")
    assert not bad, f"{path.name}:\n  " + "\n  ".join(bad)
