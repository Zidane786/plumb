"""The plugin's skills and references agree with each other and with the spec.

- every `/plumb:<x>` mentioned in a skill or reference is a 1.0.0 command, and a skill folder;
- every skill has the required frontmatter, resolves ROOT like Slate's skills, links reference/ and says
  "ask the user and wait" (Plumb never installs or downloads anything);
- every relative markdown link, and every `ROOT/...` or `<ROOT>/...` path, in skills and references exists;
- skills ask one question at a time with a "(Recommended)" option; every skill that writes into a project says that
  nothing is written without the user's OK (status is read-only);
- no internal project names anywhere under plugins/ (Slate is the companion plugin and is allowed);
- the user docs (README.md, plugins/plumb/README.md, docs/USAGE.md, TEST.md, docs/what-you-get.html) name only real
  commands, link files that exist, and quote the hooks' and scripts' real messages; docs/USAGE.md has a section per
  command and both READMEs link it near the top; docs/what-you-get.html opens offline in light and dark.
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
INTERNAL_NAMES = re.compile(r"\b(keel|caredesk)\b", re.I)
TEXT_SUFFIXES = {".md", ".py", ".json", ".html", ".css", ".js", ".tmpl", ".snippet", ".sh", ".cmd", ".txt", ".toml",
                 ".yml", ".yaml", ".swift", ".kt", ".tailwind-v3", ".tailwind-v4"}
MAX_SKILL_LINES = 200
# Skills that write into a project keep the user in the loop (owner requirement).
CONFIRM_FIRST = COMMANDS - {"status"}
# Read-only skills that ask nothing.
NO_QUESTIONS = {"status"}
ROOT_PATH = re.compile(r"<?ROOT>?/([A-Za-z0-9_./-]*)")


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
    assert {"interview.md", "placement.md", "tokens-format.md", "wire-in.md"} <= {p.name for p in REFERENCE.glob("*.md")}


def test_every_reference_is_linked_from_a_skill() -> None:
    linked = set()
    for path in skill_files():
        linked.update(re.findall(r"\]\(\.\./\.\./reference/([a-z0-9-]+\.md)\)", path.read_text(encoding="utf-8")))
    for ref in sorted(REFERENCE.glob("*.md")):
        assert ref.name in linked, f"reference/{ref.name} is not linked from any skill"


def test_every_skill_folder_is_a_command() -> None:
    folders = {p.name for p in SKILLS.iterdir() if p.is_dir()}
    assert folders <= COMMANDS, f"skill folders that are not 1.0.0 commands: {sorted(folders - COMMANDS)}"
    assert folders == COMMANDS, f"commands without a skill folder: {sorted(COMMANDS - folders)}"


def test_every_command_mentioned_exists() -> None:
    built = {p.parent.name for p in skill_files()}
    for path in doc_files():
        for name in re.findall(r"/plumb:([a-z][a-z-]*)", path.read_text(encoding="utf-8")):
            assert name in COMMANDS, f"{path.relative_to(REPO)}: /plumb:{name} is not a Plumb command"
            assert name in built, f"{path.relative_to(REPO)}: /plumb:{name} has no skill folder"


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
    flat = " ".join(text.split()).lower()  # phrases may wrap across lines
    assert "ask the user and wait" in flat, "the never-install rule"
    assert "install or download" in flat


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_skill_keeps_the_user_in_the_loop(path: Path) -> None:
    text = " ".join(path.read_text(encoding="utf-8").split()).lower()
    name = path.parent.name
    if name not in NO_QUESTIONS:
        assert "(recommended)" in text, "options carry a recommendation marked (Recommended)"
        assert "one at a time" in text, "questions go one at a time"
    if name in CONFIRM_FIRST:
        assert "nothing is written without the user's ok" in text
    if name == "init":  # the confirmed "I'll create" block covers the docs folder too
        assert "docs/design/ in <root>" in text


@pytest.mark.parametrize("path", doc_files(), ids=lambda p: p.relative_to(PLUGIN).as_posix())
def test_root_paths_exist(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for m in ROOT_PATH.finditer(text):
        if text[m.end():m.end() + 1] == "<":
            continue  # a placeholder segment such as ROOT/skills/<name>/SKILL.md
        rel = m.group(1).rstrip(".,")
        assert (PLUGIN / rel).exists(), f"{path.relative_to(REPO)}: {m.group(0)} does not exist in the plugin"


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


# ---------------------------------------------------------------- the user docs

USAGE = REPO / "docs/USAGE.md"
WHAT_YOU_GET = REPO / "docs/what-you-get.html"
READMES = [REPO / "README.md", PLUGIN / "README.md"]
USER_DOCS = READMES + [USAGE, REPO / "TEST.md", WHAT_YOU_GET]
NEAR_THE_TOP = 30  # lines
# Messages the docs quote (troubleshooting, hooks): each must still be printed by the code, word for word.
QUOTED = {
    "with no approved prototype": "hooks/pre_edit.py",
    "is generated from the design tokens; a hand edit is lost on the next build": "hooks/pre_edit.py",
    "is Plumb's file; upgrades replace it": "hooks/pre_edit.py",
    "is generated by build-prototype.py from the screen files": "hooks/pre_edit.py",
    "Plumb edit check: this edit adds": "hooks/pre_edit.py",
    "Plumb end-of-turn check:": "hooks/stop_check.py",
    "read the skill before UI changes": "hooks/session_start.py",
    "design system not found": "hooks/session_start.py",
    "visual comparison skipped: no browser found": "scripts/screenshot.py",
    "no colour token is close": "assets/skill/scripts/audit.py",
    "generated files are up to date": "assets/skill/scripts/build-tokens.py",
    "no screen files in": "assets/skill/scripts/build-prototype.py",
    "several tokens files in": "assets/skill/scripts/build-tokens.py",
}


def _headings(text: str) -> List[str]:
    return re.findall(r"^#{1,4} (.+)$", text, re.M)


def test_user_docs_exist() -> None:
    missing = [str(p.relative_to(REPO)) for p in USER_DOCS if not p.is_file()]
    assert not missing, f"missing user docs: {missing}"


def test_usage_has_a_section_per_command() -> None:
    heads = _headings(USAGE.read_text(encoding="utf-8"))
    for name in sorted(COMMANDS):
        assert any(re.search(rf"/plumb:{name}\b", h) for h in heads), \
            f"docs/USAGE.md has no section headed `/plumb:{name}`"


def test_usage_covers_what_the_owner_asked_for() -> None:
    flat = " ".join(USAGE.read_text(encoding="utf-8").split()).lower()
    for topic in ("start here", "monorepo", "linked", "design only", "prototype first", "screens.html",
                  "guide mode", "play mode", "your turn", "who owns", "hooks", "decision", "no downloads", "offline",
                  "slate", "windows", "troubleshooting", "faq", "audit fix", "audit improve", "kiro", "copilot"):
        assert topic in flat, f"docs/USAGE.md does not cover {topic!r}"


@pytest.mark.parametrize("path", READMES, ids=lambda p: str(p.relative_to(REPO)))
def test_readmes_link_usage_near_the_top(path: Path) -> None:
    head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:NEAR_THE_TOP])
    assert "docs/USAGE.md" in head, f"{path.relative_to(REPO)} must link docs/USAGE.md in its first {NEAR_THE_TOP} lines"


@pytest.mark.parametrize("path", READMES, ids=lambda p: str(p.relative_to(REPO)))
def test_readmes_list_every_command(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for name in sorted(COMMANDS):
        assert f"`/plumb:{name}" in text, f"{path.relative_to(REPO)} does not list /plumb:{name}"
    assert "what-you-get.html" in text, f"{path.relative_to(REPO)} does not link the what-you-get page"


@pytest.mark.parametrize("path", USER_DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_user_docs_name_only_real_commands(path: Path) -> None:
    for name in re.findall(r"/plumb:([a-z][a-z-]*)", path.read_text(encoding="utf-8")):
        assert name in COMMANDS, f"{path.relative_to(REPO)}: /plumb:{name} is not a Plumb command"


@pytest.mark.parametrize("path", [p for p in USER_DOCS if p.suffix == ".md"], ids=lambda p: str(p.relative_to(REPO)))
def test_user_docs_relative_links_resolve(path: Path) -> None:
    # links inside fenced code blocks are samples of a project's files (a decision entry), not links of this doc
    text = re.sub(r"^```.*?^```", "", path.read_text(encoding="utf-8"), flags=re.M | re.S)
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue
        file = target.split("#", 1)[0]
        assert (path.parent / file).exists(), f"{path.relative_to(REPO)}: link {target} points nowhere"


def test_quoted_messages_are_real() -> None:
    usage = " ".join(USAGE.read_text(encoding="utf-8").split())
    for phrase, source in QUOTED.items():
        assert phrase in (PLUGIN / source).read_text(encoding="utf-8"), f"{source} no longer prints {phrase!r}"
        assert phrase in usage, f"docs/USAGE.md does not quote {phrase!r} (troubleshooting / hooks)"


def test_what_you_get_opens_offline_in_both_themes() -> None:
    text = WHAT_YOU_GET.read_text(encoding="utf-8")
    assert text.lstrip().lower().startswith("<!doctype html>")
    assert re.search(r"<html[^>]* lang=", text) and 'name="viewport"' in text and "<title>" in text
    remote = re.findall(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", text, re.I)
    assert not remote, "what-you-get.html must load nothing from the network (no CDN, no hosted fonts)"
    assert not re.search(r"@import|fonts\.googleapis|fonts\.gstatic|url\(\s*['\"]?https?:", text, re.I)
    assert "prefers-color-scheme: dark" in text and '[data-theme="dark"]' in text
    for name in sorted(COMMANDS):
        assert f"/plumb:{name}" in text, f"what-you-get.html does not show /plumb:{name}"
