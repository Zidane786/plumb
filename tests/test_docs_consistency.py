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
# Internal project names that must never appear in product text. Add more without committing them: set
# PLUMB_INTERNAL_NAMES to a comma-separated list (e.g. in a private CI secret or your shell).
INTERNAL_NAME_LIST = ["keel", "caredesk"]


def _internal_names() -> "re.Pattern[str]":
    import os
    extra = [n.strip() for n in os.environ.get("PLUMB_INTERNAL_NAMES", "").split(",") if n.strip()]
    names = sorted({n.lower() for n in INTERNAL_NAME_LIST + extra})
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)


INTERNAL_NAMES = _internal_names()
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


# Skills that write HTML pages follow Effective HTML when installed and Plumb's built-in quality bar otherwise
# (owner requirement): each says so and links the bar. Init and status say whether it is available.
HTML_WRITERS = ("create", "extract", "prototype", "ux", "tour")
QUALITY_BAR_LINK = "](../../reference/prototypes.md)"  # no #anchor: test_kiro checks each copied link as a file


@pytest.mark.parametrize("name", HTML_WRITERS)
def test_html_writing_skills_name_the_effective_html_fallback(name: str) -> None:
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    flat = " ".join(text.split()).lower()
    assert "effective html" in flat, f"{name}: say that Effective HTML is used when it is available"
    assert "built-in quality bar" in flat, f"{name}: name Plumb's built-in quality bar as the fallback"
    assert QUALITY_BAR_LINK in text, f"{name}: link reference/prototypes.md 'The quality bar'"
    assert "never install" in flat, f"{name}: Effective HTML is optional; never install it"
    assert (REFERENCE / "prototypes.md").read_text(encoding="utf-8").count("## The quality bar (Effective HTML)") == 1


@pytest.mark.parametrize("name", ("init", "status"))
def test_init_and_status_report_effective_html(name: str) -> None:
    flat = " ".join((SKILLS / name / "SKILL.md").read_text(encoding="utf-8").split()).lower()
    assert "effective html" in flat and "built-in quality bar" in flat and "never install" in flat


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
    "the scaffold writes into the project only after the user approved the dry-run list": "scripts/scaffold.py",
    "does not fit this command": "scripts/scaffold.py",
    "run /plumb:init to record them": "hooks/session_start.py",
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


# TEST.md's expected output (level 3) next to the code that prints it: (what TEST.md says, the script, the code text).
TEST_EXPECTS = [
    ("done: 38 written, 0 kept", "scripts/scaffold.py", 'f"done: {wrote} written, {kept} kept"'),
    ("confirm: show the user this list; after their OK run the same command without --dry-run, plus --confirm",
     "scripts/scaffold.py", 'confirm: show the user this list; after their OK run the same command without --dry-run, '
                            'plus "'),
    ("error: the scaffold writes into the project only after the user approved the dry-run list", "scripts/scaffold.py",
     "the scaffold writes into the project only after the user approved the dry-run list"),
    ("ok: 5 generated files are up to date", "assets/skill/scripts/build-tokens.py",
     'f"ok: {len(files)} generated files are up to date"'),
    ("`stale: …`", "assets/skill/scripts/build-tokens.py", 'f"stale: {rel(path, root)}{note}"'),
    ("ui/card.css:1: error raw-colour: raw colour #ff0000", "assets/skill/scripts/audit.py",
     'f"{f.file}:{f.line}: {f.severity} {f.rule}: {f.message}"'),
    ("raw-colour: raw colour", "assets/skill/scripts/audit.py", '"raw-colour", "error", WEB, "file", check_raw_colour, '
                                                              '"raw colour {match}"'),
    ("proposal demo: 2 variants (a-calm: 1 screen, b-dense: 1 screen)", "assets/skill/scripts/build-prototype.py",
     "f\"proposal {name}: {len(folders)} variant{'s' if len(folders) != 1 else ''} ({', '.join(summary)})\""),
    ("approved home (", "assets/skill/scripts/build-prototype.py",
     "f\"approved {args.approve} ({e['approved']['by']}, {e['approved']['at']})\""),
    ("1 tour: first-look (3 steps, play mode)", "assets/skill/scripts/build-prototype.py",
     "f\"{t['id']} ({len(t['steps'])} steps, {t['mode']} mode)\""),
    ('steps[1].target "[data-test=new]"\n   matches nothing', "assets/skill/scripts/build-prototype.py",
     'matches nothing in {screen.rel} (state {state})'),
    ("wrote: shot.png (<browser>, 390x900, dark)", "scripts/screenshot.py",
     'f"wrote: {args.out} ({browser.name}, {args.width}x{args.height}, {args.theme})"'),
    ("note: visual comparison skipped: no browser found", "scripts/screenshot.py",
     "note: visual comparison skipped: no browser found"),
]


@pytest.mark.parametrize("expected,source,code", TEST_EXPECTS, ids=[t[0][:40] for t in TEST_EXPECTS])
def test_test_md_expectations_match_the_code(expected: str, source: str, code: str) -> None:
    flat = " ".join((REPO / "TEST.md").read_text(encoding="utf-8").split())
    assert " ".join(expected.split()) in flat, f"TEST.md no longer expects {expected!r}: update TEST_EXPECTS too"
    assert code in (PLUGIN / source).read_text(encoding="utf-8"), \
        f"{source} no longer prints {code!r}: TEST.md expects {expected!r}; fix TEST.md and this entry"


@pytest.mark.parametrize("path", [REPO / "README.md", USAGE, REPO / "TEST.md", WHAT_YOU_GET],
                         ids=lambda p: str(p.relative_to(REPO)))
def test_no_internal_project_names_in_the_user_docs(path: Path) -> None:
    hits = [f"{n}: {line.strip()[:80]}" for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if INTERNAL_NAMES.search(line)]
    assert not hits, f"internal project names in {path.relative_to(REPO)}:\n" + "\n".join(hits)


def test_internal_names_list_can_be_extended(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUMB_INTERNAL_NAMES", "Acme-Secret, other")
    rx = _internal_names()
    assert rx.search("built for acme-secret") and rx.search("Other") and rx.search("caredesk")
    assert not rx.search("acme") and not rx.search("others")


@pytest.mark.parametrize("path", [REPO / "README.md", PLUGIN / "README.md", USAGE], ids=lambda p: str(p.relative_to(REPO)))
def test_user_docs_say_effective_html_is_optional(path: Path) -> None:
    flat = " ".join(path.read_text(encoding="utf-8").split()).lower()
    assert "effective html (optional)" in flat or "optional, used when installed" in flat, path
    assert "built-in quality bar" in flat, f"{path.relative_to(REPO)}: name the fallback"
    if path == USAGE:
        assert "what if effective html isn't installed?" in flat


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


# ---------------------------------------------------------------- live-test rules (first live run, both CLIs)


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split()).lower()


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text[text.find("\n---\n", 4) + 5:]


APPROVE_RULE = "never run `--approve` (or record an approval) without the user's explicit yes to that screen"


@pytest.mark.parametrize("path", [p for p in skill_files() if "--approve" in p.read_text(encoding="utf-8")]
                         + [REFERENCE / "prototypes.md"], ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_approve_needs_the_users_explicit_yes(path: Path) -> None:
    # Copilot ran `--synced x && --approve x` unasked: every place that names --approve carries the hard rule.
    assert APPROVE_RULE in _flat(path), f"{path.relative_to(REPO)}: say {APPROVE_RULE!r}"


def test_extract_never_approves_synced_screens_itself() -> None:
    flat = _flat(SKILLS / "extract/SKILL.md")
    assert "never chain `--approve` after `--synced`" in flat


def test_init_puts_the_placement_block_inside_the_question() -> None:
    # Claude asked "Plumb found the setup above. OK?" with no block above (live 1 and 2): Claude Code can hide text
    # printed right before a question, so the whole block is the question.
    flat = _flat(SKILLS / "init/SKILL.md")
    for phrase in ("the whole block inside it", "verbatim", "never summarise it", "the setup above",
                   "docs/design/ in <root>", "ui files", "routes", "(corrected: <why>)"):
        assert phrase in flat, f"init: {phrase!r}"
    assert re.search(r"detect\.py\" --cwd \. --json && .*detect\.py\" --cwd \.`", flat), \
        "init: one shell call gives the JSON and the text block"


def test_wire_in_is_never_skipped() -> None:
    # Copilot skipped the AGENTS.md row and the Makefile when neither file existed.
    for path in (SKILLS / "init/SKILL.md", REFERENCE / "wire-in.md"):
        flat = _flat(path)
        assert "even when the file does not exist" in flat, path
        assert "direct commands" in flat, f"{path}: a declined Makefile means PLUMB.md lists the direct commands"
    for name in ("create", "extract"):
        assert "never skip" in _flat(SKILLS / name / "SKILL.md"), f"{name}: finish with the wire-in, never skip it"


def test_create_asks_before_changing_an_existing_stylesheet() -> None:
    flat = _flat(SKILLS / "create/SKILL.md")
    for phrase in ("plumb:start", "plumb:end", "the rest stays the project's", "theme_switch", "motion.reduced"):
        assert phrase in flat, f"create: {phrase!r}"
    interview = _flat(REFERENCE / "interview.md")
    assert "$extensions.plumb.web.theme_switch" in interview and "$extensions.plumb.motion.reduced" in interview


def test_audit_asks_for_the_dev_server_and_never_probes() -> None:
    # Copilot ran curl against localhost:3000/3001/5173 instead of asking.
    for path in (SKILLS / "audit/SKILL.md", SKILLS / "ux/SKILL.md", REFERENCE / "copilot.md"):
        flat = _flat(path)
        assert "never probe" in flat and "curl" in flat, path
        assert "dev server" in flat, path


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_slate_is_offered_only_when_it_is_set_up(path: Path) -> None:
    # Copilot offered "Create Slate tickets" in a repo without Slate.
    flat = _flat(path)
    if re.search(r"slate tickets?(?! if any)", flat):  # "the Slate ticket if any" in a decision entry is a record
        assert "kanban/board.py" in flat and "never mention slate" in flat, \
            f"{path.parent.name}: offer Slate tickets only when kanban/board.py exists; otherwise never mention Slate"


@pytest.mark.parametrize("path", [p for p in skill_files() if "scripts/audit.py" in _body(p)],
                         ids=lambda p: p.parent.name)
def test_audit_exit_1_is_not_a_crash(path: Path) -> None:
    assert "exit 1 means errors found, not a crash" in _flat(path), path.parent.name


@pytest.mark.parametrize("path", doc_files(), ids=lambda p: p.relative_to(PLUGIN).as_posix())
def test_temp_files_stay_in_the_project(path: Path) -> None:
    # Copilot asked for access to /tmp; the answers JSON lives in <root>/.plumb-tmp/ (git-ignored, removed after).
    assert "system temp" not in _flat(path), f"{path.relative_to(REPO)}: temp files go in <root>/.plumb-tmp/"


def test_temp_folder_is_named_where_it_is_used() -> None:
    for path in (SKILLS / "init/SKILL.md", SKILLS / "create/SKILL.md", SKILLS / "extract/SKILL.md",
                 REFERENCE / "placement.md", REFERENCE / "interview.md"):
        assert ".plumb-tmp/" in path.read_text(encoding="utf-8"), path


SPEC = REPO / "docs/specs/2026-10-11-plumb-design.md"
ROUTE_DOCS = skill_files() + sorted(REFERENCE.glob("*.md")) + [SPEC, USAGE, REPO / "TEST.md"] + [
    PLUGIN / "assets/skill/scripts" / name for name in ("build-prototype.py", "audit.py")]  # usage text and fix lines


@pytest.mark.parametrize("path", ROUTE_DOCS, ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_routes_are_passed_as_one_argument(path: Path) -> None:
    # `--route /` made Copilot ask for path access to `/`.
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"--route [</A-Z{\"']", text), f"{path.relative_to(REPO)}: write --route=<route>"


@pytest.mark.parametrize("path", [p for p in skill_files() if "`&&`" in p.read_text(encoding="utf-8")],
                         ids=lambda p: p.parent.name)
def test_batching_advice_names_the_powershell_caveat(path: Path) -> None:
    assert "powershell 5.1" in _flat(path), f"{path.parent.name}: Windows PowerShell 5.1 has no `&&`"


def test_extract_asks_theme_switch_and_reduced_motion() -> None:
    flat = _flat(SKILLS / "extract/SKILL.md")
    for phrase in ("theme_switch", "reduced_motion", "$extensions.plumb.web.theme_switch",
                   "$extensions.plumb.motion.reduced", "always ask these", "prefers-reduced-motion",
                   "reset_palette"):
        assert phrase in flat, f"extract: {phrase!r}"


def test_create_shows_the_stylesheet_diff_and_passes_the_settings_as_answers() -> None:
    flat = _flat(SKILLS / "create/SKILL.md")
    assert "`build-tokens.py --check` prints the diff" in flat
    assert "`theme_switch` / `reduced_motion`" in flat
    assert "`theme_switch`" in _flat(REFERENCE / "interview.md") and "`reduced_motion`" in _flat(REFERENCE / "interview.md")


@pytest.mark.parametrize("name", ["create", "extract"])
def test_create_and_extract_move_a_stylesheets_own_theme_variables_and_name_motion_fade(name: str) -> None:
    flat = _flat(SKILLS / f"{name}/SKILL.md")
    for phrase in ("build-tokens.py --overrides", "motion-fade"):
        assert phrase in flat, f"{name}: {phrase!r}"
    create = _flat(SKILLS / "create/SKILL.md")
    for phrase in ("block-override", "--overrides --apply", "move them into the tokens (recommended", "only on yes",
                   "`used_in`", "the app's own code", "/plumb:audit fix"):
        assert phrase in create, f"create: {phrase!r}"
    for path in (REFERENCE / "scripts.md", USAGE, REPO / "TEST.md"):
        assert "--overrides" in _flat(path), path.name
        assert "--migrate" in _flat(path), path.name


def test_the_data_theme_switch_is_documented_and_extract_reads_next_themes() -> None:
    # One unambiguous rule for both CLIs (Copilot recommended "system + class" next to next-themes attribute="class").
    interview = (REFERENCE / "interview.md").read_text(encoding="utf-8")
    rule = " ".join(interview.split("## Theme switch: what to recommend", 1)[1].split("\n## ", 1)[0].split()).lower()
    for phrase in ("next-themes", 'attribute="class"', 'attribute="data-theme"', "ask anyway", "an array",
                   "when it holds \"class\"", "another attribute", "first row that matches",
                   "never recommend `both` when a row above it matches", "enablesystem", "inside the question",
                   "file:line"):
        assert phrase in rule or phrase in " ".join(interview.split()).lower(), f"interview.md theme switch: {phrase!r}"
    assert re.search(r'next-themes `<themeprovider attribute="class">`[^|]*\| `class` \|', rule), \
        "next-themes attribute=\"class\" recommends class"
    for name in ("create", "extract"):
        flat = _flat(SKILLS / name / "SKILL.md")
        assert "theme switch" in flat and "first matching row" in flat and "file:line" in flat, name
    assert "clipped to the nearest srgb colour" in _flat(REFERENCE / "tokens-format.md")
    assert "same-in-dark" in _flat(REFERENCE / "scripts.md") and "`notes`" in _flat(REFERENCE / "interview.md")
    for path in (REFERENCE / "tokens-format.md", REFERENCE / "interview.md", REFERENCE / "scripts.md",
                 SKILLS / "create/SKILL.md"):
        assert "data-theme" in _flat(path), path.name


def test_spec_states_the_new_rules() -> None:
    flat = _flat(SPEC).replace("*", "")
    for phrase in ("the project's design system outranks effective html", "craft only", "plumb:start",
                   "theme_switch", "motion.reduced", "make target"):
        assert phrase in flat, f"spec: {phrase!r}"
    assert "effective html is the reference for every prototype" not in flat


@pytest.mark.parametrize("name", sorted(USER_ONLY))
def test_user_only_skills_say_they_are_already_loaded(name: str) -> None:
    # Copilot hides disable-model-invocation skills from its skill tool, so the model's extra call fails noisily.
    assert "already loaded" in _flat(SKILLS / name / "SKILL.md"), name


@pytest.mark.parametrize("name", ("audit", "ux", "create", "extract", "prototype"))
def test_end_of_turn_check_respects_dont_fix_now(name: str) -> None:
    flat = _flat(SKILLS / name / "SKILL.md")
    assert "end-of-turn check" in flat and "not to fix now" in flat and "report and stop" in flat, name


def test_copilot_reference_covers_the_live_findings() -> None:
    flat = _flat(REFERENCE / "copilot.md")
    for phrase in ("allowed-tools", "--allow-tool", "skill not found", "--route=/", ".plumb-tmp/", "one shell call"):
        assert phrase in flat, f"copilot.md: {phrase!r}"


SYSTEM_WINS = "the project's design system outranks effective html"


@pytest.mark.parametrize("name", HTML_WRITERS)
def test_the_projects_design_system_outranks_effective_html(name: str) -> None:
    # Owner requirement: Effective HTML is for craft only; palette, type, spacing, radius and motion come from the system.
    flat = _flat(SKILLS / name / "SKILL.md").replace("*", "")
    assert SYSTEM_WINS in flat and "craft only" in flat and "the system wins" in flat, name
    if name == "create":
        assert "directions page is the one exception" in flat


def test_quality_bar_states_the_system_outranks_effective_html() -> None:
    text = (REFERENCE / "prototypes.md").read_text(encoding="utf-8")
    section = text.split("## The quality bar (Effective HTML)", 1)[1].split("\n## ", 1)[0]
    flat = " ".join(section.split()).lower().replace("*", "")
    for phrase in (SYSTEM_WINS, "craft only", "the system wins", "inlined token block", "audit exits 0",
                   "directions page"):
        assert phrase in flat, phrase


# ---------------------------------------------------------------- live-test rules (second live run, both CLIs)


def _sections(path: Path) -> Dict[str, str]:
    """`## heading` → its body, for a skill's numbered checkpoints."""
    parts = re.split(r"^## (.+)$", _body(path), flags=re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


@pytest.mark.parametrize("path", skill_files() + [REFERENCE / "interview.md", REFERENCE / "copilot.md"],
                         ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_confirmation_content_goes_inside_the_question(path: Path) -> None:
    # Claude Code hid the "Plumb found" block and the "Right?" summary printed right before AskUserQuestion.
    flat = _flat(path).replace("*", "")
    assert "inside the question" in flat or "in the question text" in flat, path.name
    assert "never only in a message before" in flat, f"{path.relative_to(REPO)}: never only before the question"
    if path.name == "SKILL.md" and path.parent.name in ("init", "create", "extract"):
        assert "claude code can hide" in flat and "copilot cli's ask tool" in flat, path.parent.name


# Create's and extract's checkpoints: each `## N. … — STOP` section ends in "STOP: ask, wait for the answer".
CHECKPOINTS = {
    "create": ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.", "11.", "12.", "13.", "14.", "16."],
    "extract": ["1.", "2.", "3.", "4.", "5.", "6–8.", "9.", "10–15.", "16.", "17.", "18."],
}


@pytest.mark.parametrize("name", sorted(CHECKPOINTS))
def test_create_and_extract_checkpoints_stop_and_wait(name: str) -> None:
    # Copilot's create skipped the direction pick, the token set and the dry-run OK, then ran the scaffold unasked.
    path = SKILLS / name / "SKILL.md"
    sections = _sections(path)
    for number in CHECKPOINTS[name]:
        heads = [h for h in sections if h.startswith(number + " ")]
        assert heads, f"{name}: no checkpoint section {number}"
        head = heads[0]
        assert "STOP" in head, f"{name} {head!r}: the heading says STOP"
        body = " ".join(sections[head].split()).replace("*", "")
        # the section itself says it, in full: no heading-only or bullet-only "— STOP"
        assert re.search(r"STOP(?: after each(?: question)?| per \w+| at each)?: ask, wait for the answer\.", body), \
            f"{name} {head!r}: the section must say 'STOP: ask, wait for the answer.'"
    flat = _flat(path)
    for phrase in ("never skip one", "a permission prompt from your tool", "is never the user's ok",
                   "final checklist — walk it before you say done", "contrast evidence", "decisions.md",
                   "a first prototype screen" if name == "create" else "every confirmed route has a screen file",
                   "every checkpoint that applied", "not applicable: say which and why",
                   "remove the whole `<root>/.plumb-tmp/`"):
        assert phrase in flat, f"{name}: {phrase!r}"


@pytest.mark.parametrize("path", [SKILLS / "create/SKILL.md", SKILLS / "extract/SKILL.md", REFERENCE / "interview.md"],
                         ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_the_real_scaffold_needs_the_dry_runs_confirm_token(path: Path) -> None:
    # The engine refuses the real scaffold without --confirm <token>, which only the dry run prints.
    flat = _flat(path)
    assert "--confirm <token>" in flat and "dry run" in flat, path.name
    if path.name == "SKILL.md" and path.parent.name == "create":
        assert "--dry-run`" in flat and "never run the real scaffold without a dry run the user ok'd" in flat
        assert "in a new shell call" in flat, "the dry run and the real run are never one shell call"


TEMP_ELSEWHERE = re.compile(r"(?<![\w.-])(/tmp\b|%TEMP%)")


@pytest.mark.parametrize("path", doc_files(), ids=lambda p: p.relative_to(PLUGIN).as_posix())
def test_scratch_files_only_in_plumb_tmp(path: Path) -> None:
    # Claude wrote <root>/../check.txt; Copilot's status wrote /tmp/…json; its prototype read a guessed path.
    text = " ".join(path.read_text(encoding="utf-8").split())
    for m in TEMP_ELSEWHERE.finditer(text):
        before = text[max(0, m.start() - 120):m.start()].lower()
        assert re.search(r"\b(never|no)\b", before), \
            f"{path.relative_to(REPO)}: {m.group(0)} named as a place to write; scratch files go in <root>/.plumb-tmp/"
    flat = _flat(path)
    if path.name == "SKILL.md" and path.parent.name != "status" and ("scratch" in flat or "temporary" in flat):
        assert ".plumb-tmp/" in flat, path.parent.name


MARKER = ".plumb-tmp/setup-in-progress"
SETUP_SKILLS = ("init", "create", "extract")


def test_scratch_folder_and_setup_marker_are_documented() -> None:
    # Ruling I1: the end-of-turn stand-down keys on the marker FILE only; other skills may use .plumb-tmp/ for scratch.
    flat = _flat(REFERENCE / "interview.md").replace("*", "")
    for phrase in ("## scratch files", MARKER, "only init, create and extract write it",
                   "the end-of-turn check stands down while the marker exists", "remove the whole `.plumb-tmp/`",
                   "clean up their own files", "never `/tmp`"):
        assert phrase in flat, f"interview.md: {phrase!r}"
    for name in ("create", "extract"):
        assert f"`<root>/{MARKER}`" in _flat(SKILLS / name / "SKILL.md"), f"{name}: writes the marker at the start"
    init = _flat(SKILLS / "init/SKILL.md")
    assert f"`<root>/{MARKER}` exists" in init, "init: the resume check keys on the marker file"
    status = _flat(SKILLS / "status/SKILL.md")
    assert f"`<root>/{MARKER}` exists" in status, "status: the half-setup report keys on the marker file"
    assert ".plumb-tmp/` exists" not in status and ".plumb-tmp/` exists" not in init.replace(f"{MARKER}` exists", "")


@pytest.mark.parametrize("path", [p for p in skill_files() if p.parent.name not in SETUP_SKILLS + ("status",)],
                         ids=lambda p: p.parent.name)
def test_other_skills_never_write_the_setup_marker(path: Path) -> None:
    flat = _flat(path)
    assert "never write `setup-in-progress`" in flat and "clean up your own files" in flat, path.parent.name


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_every_skill_resolves_its_roots_first(path: Path) -> None:
    # Copilot's prototype read the project's references at a guessed path outside the repo.
    flat = _flat(path).replace("*", "")
    assert "resolve again, never guess" in flat, path.parent.name
    assert "<root>" in flat, path.parent.name
    if path.parent.name not in ("init", "create", "extract"):
        assert "project root `<root>`:" in flat and "never from a path you remember" in flat, path.parent.name


def test_status_never_suggests_setup_commands_when_set_up() -> None:
    # Copilot's status suggested /plumb:extract for a project that has PLUMB.md.
    flat = _flat(SKILLS / "status/SKILL.md").replace("*", "")
    assert "/plumb:create" not in flat and "/plumb:extract" not in flat
    assert "never suggest the setup commands create or extract" in flat
    assert "status writes no file at all" in flat and "never save output to a file" in flat
    assert "routes:" in flat and "/plumb:init" in flat


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_every_skill_says_scripts_give_evidence_not_answers(path: Path) -> None:
    flat = _flat(path).replace("*", "")
    assert "scripts give evidence, not answers" in flat, path.parent.name
    assert "(corrected: <why>)" in flat and "(added: <why>)" in flat, path.parent.name
    assert "](../../reference/interview.md)" in path.read_text(encoding="utf-8"), path.parent.name


def test_interview_starts_with_scripts_give_evidence() -> None:
    text = (REFERENCE / "interview.md").read_text(encoding="utf-8")
    assert _headings(text)[1] == "Scripts give evidence, not answers", "it is the first rule"
    flat = _flat(REFERENCE / "interview.md")
    for script in ("detect.py", "scaffold.py", "build-tokens.py", "audit.py", "build-prototype.py", "screenshot.py",
                   "--inventory", "--overrides"):
        assert script in flat, script
    for phrase in ("popover", "sidebar-accent", "a burst of identical errors", "setup gap",
                   "allowed raw values:", "matches 0 files"):
        assert phrase in flat, phrase


INVESTIGATORS = ("init", "create", "extract", "audit", "ux")


@pytest.mark.parametrize("name", INVESTIGATORS)
def test_skills_investigate_before_asking(name: str) -> None:
    flat = _flat(SKILLS / name / "SKILL.md").replace("*", "")
    assert "investigate first" in flat, name
    if name in ("init", "create", "extract"):
        assert "routes" in flat and "ui files" in flat, name
    interview = _flat(REFERENCE / "interview.md").replace("*", "")
    for phrase in ("## investigate first", "evidence table", "| fact | value | evidence | confidence |",
                   "found: <value> (<file:line>)", "couldn't find", "what gets recorded", "routes:", "`routes`"):
        assert phrase in interview, f"interview.md: {phrase!r}"


def test_init_verifies_ui_files_and_asks_about_a_git_ignored_skill() -> None:
    flat = _flat(SKILLS / "init/SKILL.md").replace("*", "")
    for phrase in ("count the files each proposed ui-file pattern matches", "check-ignore", "never proceed silently",
                   "!.claude/skills/", "git cannot re-include", "(recommended)"):
        assert phrase in flat, f"init: {phrase!r}"


def test_palette_reset_is_asked_where_it_matters() -> None:
    interview = _flat(REFERENCE / "interview.md").replace("*", "")
    for phrase in ("`reset_palette`", "$extensions.plumb.web.reset_palette", "reset (`true`, recommended)",
                   "recommend keep (`false`)"):
        assert phrase in interview, f"interview.md: {phrase!r}"
    assert "reset_palette" in _flat(SKILLS / "create/SKILL.md")
    extract = _flat(SKILLS / "extract/SKILL.md").replace("*", "")
    assert "recommend keep (`false`) and explain" in extract


def test_ux_patterns_are_seven_questions() -> None:
    assert "c16 is seven questions" in _flat(REFERENCE / "interview.md").replace("*", "")
    assert "say which you skip and why" in _flat(SKILLS / "create/SKILL.md")
    assert "say which you skip and why" in _flat(SKILLS / "extract/SKILL.md")


def test_a_new_agents_md_is_a_whole_file() -> None:
    # Copilot created "# Agent guidance" and a bare row.
    flat = _flat(REFERENCE / "wire-in.md")
    for phrase in ("never a bare row", "## read before you work", "| when | read | rule |", "|---|---|---|"):
        assert phrase in flat, f"wire-in.md: {phrase!r}"
    assert "never a bare row" in _flat(SKILLS / "init/SKILL.md")


def test_copilot_prompts_are_documented_honestly() -> None:
    flat = _flat(REFERENCE / "copilot.md").replace("*", "")
    for phrase in ("what to expect", "one shell call per checkpoint", "--add-dir", "--allow-tool 'shell(python3)'",
                   "no setting that pre-allows only plumb's scripts", "never the user's answer to a plumb checkpoint"):
        assert phrase in flat, f"copilot.md: {phrase!r}"


def test_user_docs_and_spec_state_the_live_2_rules() -> None:
    usage = _flat(USAGE).replace("*", "")
    for phrase in ("plumb's scripts read what you confirmed; they don't guess your layout", "inside the question",
                   "scripts give evidence, not answers", "routes:", ".plumb-tmp/", "!.claude/skills/",
                   "never \"create\" or \"extract\""):
        assert phrase in usage, f"USAGE.md: {phrase!r}"
    spec = _flat(SPEC).replace("*", "")
    for phrase in ("what the user confirms is inside the question", "scripts give evidence, not answers",
                   "investigate first", "--confirm <token>", "reset_palette", "stop: ask, wait for the answer",
                   "final checklist"):
        assert phrase in spec, f"spec: {phrase!r}"
    test_md = _flat(REPO / "TEST.md")
    for phrase in ("inside the question", "--confirm <token>", "git-ignored", "routes:", "final checklist"):
        assert phrase in test_md, f"TEST.md: {phrase!r}"


# ---------------------------------------------------------------- review fixes (live-2 skills review)

# PLUMB.md `Routes:` is `<path> (<kind>)`, comma-separated, or `none` (the engine's _plumb.parse_routes).
ROUTE_KINDS = ("next-app", "next-pages", "nuxt", "sveltekit", "router", "angular")
ROUTE_EXAMPLE = re.compile(r"`([A-Za-z0-9_.][^`(]*?) \(([a-z-]+)\)`")


def test_routes_are_recorded_with_their_kind() -> None:
    interview = _flat(REFERENCE / "interview.md").replace("*", "")
    for kind in ROUTE_KINDS:
        assert f"({kind})" in interview, f"interview.md: no example of the {kind} kind"
    for phrase in ("`<path> (<kind>)`", "`none`", "never leave the kind to be guessed"):
        assert phrase in interview, f"interview.md: {phrase!r}"
    for name in ("init", "extract"):
        assert "(<kind>)" in _flat(SKILLS / name / "SKILL.md"), f"{name}: record each route root with its kind"


def test_route_examples_parse() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("_plumb_routes", PLUGIN / "assets/skill/scripts/_plumb.py")
    assert spec and spec.loader
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)  # type: ignore[union-attr]
    assert set(core.ROUTE_KINDS) == set(ROUTE_KINDS), "the skills name exactly the engine's route kinds"
    assert core.parse_routes("none") == ([], [])
    found = 0
    for path in (REFERENCE / "interview.md", SKILLS / "init/SKILL.md", SKILLS / "extract/SKILL.md", USAGE):
        for m in ROUTE_EXAMPLE.finditer(path.read_text(encoding="utf-8")):
            entry, kind = m.group(1).strip(), m.group(2)
            if kind not in ROUTE_KINDS:
                continue  # another parenthesised note, not a route
            found += 1
            assert not entry.startswith("/") and ".." not in entry.split("/"), f"{path.name}: {m.group(0)}"
            roots, problems = core.parse_routes(f"{entry} ({kind})")  # the engine's own parser
            assert roots == [(entry, kind)] and not problems, f"{path.name}: {m.group(0)} does not parse: {problems}"
    assert found >= 6, "examples of `<path> (<kind>)` in interview.md, init, extract and USAGE"


def test_investigate_first_covers_every_stack() -> None:
    section = (REFERENCE / "interview.md").read_text(encoding="utf-8").split("## Investigate first", 1)[1]
    flat = " ".join(section.split("\n## ", 1)[0].split()).lower()
    for phrase in (".xcassets", "colorset", "uiappfonts", "values-night/", "themes.xml", "theme.kt", "res/font",
                   "angular.json", "@angular/material", "@custom-variant dark", "darkmode", "createtheme", "chakra",
                   "styled-components", "storybook", "i18n"):
        assert phrase in flat, f"interview.md Investigate first: {phrase!r}"


def test_theme_switch_rule_reads_tailwind_dark_config_and_unsupported_attributes() -> None:
    interview = (REFERENCE / "interview.md").read_text(encoding="utf-8")
    rule = " ".join(interview.split("## Theme switch: what to recommend", 1)[1].split("\n## ", 1)[0].split()).lower()
    assert re.search(r"@custom-variant dark[^|]*\.dark[^|]*\| `class` \|", rule), "v4 @custom-variant on .dark → class"
    assert re.search(r"darkmode: 'media'[^|]*\| `system` \|", rule), "v3 darkMode: 'media' → system"
    assert "recommend switching the app's attribute to `class`" in rule, "an unsupported next-themes attribute (M7)"


PLUGIN_SCRIPTS = {
    "detect.py": "scripts/detect.py", "scaffold.py": "scripts/scaffold.py", "version.py": "scripts/version.py",
    "screenshot.py": "scripts/screenshot.py", "build-tokens.py": "assets/skill/scripts/build-tokens.py",
    "audit.py": "assets/skill/scripts/audit.py", "build-prototype.py": "assets/skill/scripts/build-prototype.py",
}
_HELP: Dict[str, str] = {}


def _script_help(name: str) -> str:
    if name not in _HELP:
        import subprocess
        import sys
        r = subprocess.run([sys.executable, str(PLUGIN / PLUGIN_SCRIPTS[name]), "--help"], capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
        _HELP[name] = r.stdout + r.stderr
    return _HELP[name]


def _script_flags(text: str) -> List[tuple]:
    """(script, flag) for each `--flag` written after a script's name in a code span or fenced line."""
    fenced = re.findall(r"^```[a-z]*\n(.*?)^```", text, re.M | re.S)
    prose = re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)
    spans = [" ".join(s.split()) for s in re.findall(r"`([^`]+)`", prose)]  # an inline command may wrap a line
    commands = [c for s in spans for c in re.split(r"&&|;|\|\|", s)]
    commands += [c for block in fenced for line in block.splitlines() for c in re.split(r"&&|;|\|\||─▶", line)]
    out = []
    names = "|".join(re.escape(n) for n in PLUGIN_SCRIPTS)
    for command in commands:
        found = list(re.finditer(rf"(?<![\w-])({names})\b", command))
        if not found:
            continue
        last = found[-1]  # flags belong to the last script named before them
        for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", command[last.end():]):
            out.append((last.group(1), flag))
    return out


@pytest.mark.parametrize("path", doc_files(), ids=lambda p: p.relative_to(PLUGIN).as_posix())
def test_every_script_flag_a_skill_names_exists(path: Path) -> None:
    missing = []
    for script, flag in _script_flags(path.read_text(encoding="utf-8")):
        if flag in _script_help(script):
            continue
        missing.append(f"{script} {flag}")
    assert not missing, f"{path.relative_to(REPO)} names flags the scripts don't have: {sorted(set(missing))}"


def test_flag_check_sees_the_flags() -> None:
    found = _script_flags((SKILLS / "create/SKILL.md").read_text(encoding="utf-8"))
    assert ("scaffold.py", "--dry-run") in found and ("build-tokens.py", "--overrides") in found


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_skills_stay_within_the_line_budget(path: Path) -> None:
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= MAX_SKILL_LINES, f"{path.parent.name}: {lines} lines (max {MAX_SKILL_LINES})"
    if path.parent.name in SETUP_SKILLS:  # headroom for the longest flows
        assert lines <= 185, f"{path.parent.name}: {lines} lines; keep it at 185 or fewer, detail in reference/"


def test_init_rechecks_git_ignore_and_lists_its_rules() -> None:
    text = (SKILLS / "init/SKILL.md").read_text(encoding="utf-8")
    flat = _flat(SKILLS / "init/SKILL.md")
    for phrase in ("run `git -c \"<root>\" check-ignore -v", "again after", "`.git/info/exclude`",
                   "`!.claude/skills/**`"):
        assert phrase in flat, f"init: {phrase!r}"
    rules = text.split("**Rules.**", 1)[1].split("\n\n", 1)[0]
    assert len(re.findall(r"^- ", rules, re.M)) >= 6, "init's rules are a short list, not one paragraph"


def test_long_diffs_are_summarised_with_the_full_diff_on_disk() -> None:
    flat = _flat(REFERENCE / "interview.md")
    for phrase in ("the first ~40 lines", "+/- counts", "`<root>/.plumb-tmp/", "never summarise a list of files or values"):
        assert phrase in flat, f"interview.md: {phrase!r}"


# ---------------------------------------------------------------- aligned with the engine (confirm gate, routes, palette)


@pytest.mark.parametrize("path", [p for p in skill_files() if re.search(r"scaffold\.py\"? --project-root", _body(p))],
                         ids=lambda p: p.parent.name)
def test_every_real_scaffold_run_goes_through_the_confirm_gate(path: Path) -> None:
    # update and upgrade run scaffold for real too: dry run, the list inside the question, then --confirm.
    flat = _flat(path).replace("*", "")
    assert "--dry-run" in flat and "--confirm <token>" in flat, path.parent.name
    assert "exactly as the dry run printed it" in flat and "in a new shell call" in flat, path.parent.name
    assert "inside the question" in flat, path.parent.name


def test_the_dry_runs_confirm_line_is_quoted_as_the_engine_prints_it() -> None:
    scaffold = (PLUGIN / "scripts/scaffold.py").read_text(encoding="utf-8")
    assert "after their OK run the same command without --dry-run, plus" in scaffold
    flat = _flat(REFERENCE / "interview.md")
    assert "after their ok run the same command without --dry-run, plus --confirm <12-hex token>" in flat


def test_palette_reset_explains_all_six_namespaces_and_what_the_audit_still_reports() -> None:
    interview = _flat(REFERENCE / "interview.md").replace("*", "")
    for phrase in ("all six namespaces", "`text-lg`", "off-scale", "`false` keeps all six open"):
        assert phrase in interview, f"interview.md: {phrase!r}"
    for name in ("create", "extract"):
        flat = _flat(SKILLS / name / "SKILL.md")
        assert "six" in flat and "`text-lg`" in flat, f"{name}: say what reset_palette false keeps and what the audit flags"


def test_overrides_look_change_notes_are_inside_the_question() -> None:
    assert "the look changes; ask the user" in (PLUGIN / "assets/skill/scripts/build-tokens.py").read_text(
        encoding="utf-8") or "the look changes; ask the user" in (
        PLUGIN / "assets/skill/scripts/_plumb.py").read_text(encoding="utf-8")
    assert "the look changes; ask the user" in _flat(REFERENCE / "interview.md").replace("*", "")
    for name in ("create", "extract"):
        assert "\"the look changes\" note on its own line" in _flat(SKILLS / name / "SKILL.md"), name


def test_release_notes_cover_the_live_2_changes() -> None:
    changelog = (PLUGIN / "CHANGELOG.md").read_text(encoding="utf-8").split("\n## ", 2)[1]
    flat = " ".join(changelog.split()).lower()
    for phrase in ("--confirm", "routes:", "reset_palette", "setup-in-progress", "inside the question",
                   "git-ignored"):
        assert phrase in flat, f"CHANGELOG 1.0.0: {phrase!r}"
    upgrade = _flat(PLUGIN / "upgrades/1.0.0.md")
    assert "routes:" in upgrade and "/plumb:init" in upgrade, "older projects: record Routes with /plumb:init"


def test_setup_marker_is_rewritten_at_every_checkpoint() -> None:
    # Re-review N2: a setup longer than 6 hours must keep the end-of-turn stand-down.
    assert "rewrite the marker at every checkpoint" in _flat(REFERENCE / "interview.md")
    for name in SETUP_SKILLS:
        flat = _flat(SKILLS / name / "SKILL.md")
        assert "rewrite it at every checkpoint" in flat or "rewrite the marker" in flat, name
    assert "rewrite the marker" in _flat(SKILLS / "init/SKILL.md"), "init rewrites it when it resumes a setup"


def test_init_rechecks_with_check_ignore_q() -> None:
    # Re-review N3: after the fix, `-v` still prints a matching `!` line (kept); `-q` exit 1 is the clear answer.
    flat = _flat(SKILLS / "init/SKILL.md")
    assert "check-ignore -q" in flat and "exit 1" in flat and "a `!` line means kept" in flat
