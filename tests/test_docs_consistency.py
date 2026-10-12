"""The plugin's skills and references agree with each other and with the spec.

- every `/plumb:<x>` mentioned in a skill or reference is a 1.0.0 command, and (once built) a skill folder;
- every skill has the required frontmatter, resolves ROOT like Slate's skills, links reference/ and says
  "ask the user and wait" (Plumb never installs or downloads anything);
- every relative markdown link in skills and references points at a file that exists;
- no internal project names anywhere under plugins/ (Slate is the companion plugin and is allowed).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/plumb"
SKILLS = PLUGIN / "skills"
REFERENCE = PLUGIN / "reference"

# The spec's command table (section 3): every command 1.0.0 ships.
COMMANDS = {"init", "create", "extract", "prototype", "tour", "audit", "ux", "update", "upgrade", "status"}
# Heavy flows run only when the user typed them (spec section 3).
USER_ONLY = {"init", "create", "extract", "update", "upgrade"}
# Skills still being written in a parallel task of the 1.0.0 build; remove a name once its folder exists.
PENDING = {"prototype", "tour", "audit", "ux", "update", "upgrade", "status"}
INTERNAL_NAMES = re.compile(r"\b(keel|caredesk)\b", re.I)
TEXT_SUFFIXES = {".md", ".py", ".json", ".html", ".css", ".js", ".tmpl", ".snippet", ".sh", ".cmd", ".txt", ".toml",
                 ".yml", ".yaml", ".swift", ".kt", ".tailwind-v3", ".tailwind-v4"}
MAX_SKILL_LINES = 200


def skill_files() -> List[Path]:
    return sorted(SKILLS.glob("*/SKILL.md"))


def doc_files() -> List[Path]:
    return skill_files() + sorted(REFERENCE.glob("*.md"))


def frontmatter(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: frontmatter must open on the first line"
    end = text.find("\n---\n", 4)
    assert end > 0, f"{path}: frontmatter is not closed"
    out: Dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            out[key.strip()] = value.strip()
    return out


def test_there_are_skills_and_references() -> None:
    names = {p.parent.name for p in skill_files()}
    assert {"init", "create", "extract"} <= names
    assert {"interview.md", "placement.md", "tokens-format.md"} <= {p.name for p in REFERENCE.glob("*.md")}


def test_every_skill_folder_is_a_command() -> None:
    folders = {p.name for p in SKILLS.iterdir() if p.is_dir()}
    assert folders <= COMMANDS, f"skill folders that are not 1.0.0 commands: {sorted(folders - COMMANDS)}"
    assert not (folders & PENDING), f"built now, remove from PENDING: {sorted(folders & PENDING)}"


def test_every_command_mentioned_exists() -> None:
    built = {p.parent.name for p in skill_files()}
    for path in doc_files():
        for name in re.findall(r"/plumb:([a-z][a-z-]*)", path.read_text(encoding="utf-8")):
            assert name in COMMANDS, f"{path.relative_to(REPO)}: /plumb:{name} is not a Plumb command"
            assert name in built | PENDING, f"{path.relative_to(REPO)}: /plumb:{name} has no skill folder"


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_skill_frontmatter(path: Path) -> None:
    meta = frontmatter(path)
    assert meta.get("name") == path.parent.name
    assert len(meta.get("description", "")) > 40
    if path.parent.name in USER_ONLY:
        assert meta.get("disable-model-invocation") == "true", f"{path.parent.name} must only run when typed"


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_skill_body_rules(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= MAX_SKILL_LINES, "skills stay lean: move detail into reference/"
    assert "${CLAUDE_PLUGIN_ROOT}" in text and "/../.." in text, "ROOT resolution like Slate's skills"
    assert re.search(r"\]\(\.\./\.\./reference/[a-z0-9-]+\.md\)", text), "link at least one reference/ file"
    assert "ask the user and wait" in text.lower(), "the never-install rule"
    assert "install or download" in text.lower()


@pytest.mark.parametrize("path", doc_files(), ids=lambda p: p.relative_to(PLUGIN).as_posix())
def test_relative_links_resolve(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue
        file = target.split("#", 1)[0]
        assert (path.parent / file).exists(), f"{path.relative_to(REPO)}: link {target} points nowhere"


def test_no_internal_project_names_under_plugins() -> None:
    hits = []
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in ("Makefile.snippet",):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if INTERNAL_NAMES.search(line):
                hits.append(f"{path.relative_to(REPO)}:{n}: {line.strip()[:80]}")
    assert not hits, "internal project names under plugins/:\n" + "\n".join(hits)
