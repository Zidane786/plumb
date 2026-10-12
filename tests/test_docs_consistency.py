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


def test_init_prints_the_placement_block_in_full() -> None:
    # Claude asked "Plumb found the setup above. OK?" with no block above.
    flat = _flat(SKILLS / "init/SKILL.md")
    for phrase in ("print the block in the chat, in full", "verbatim", "never summarise it",
                   "the setup above", "docs/design/ in <root>", "ui files"):
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
ROUTE_DOCS = skill_files() + [p for p in sorted(REFERENCE.glob("*.md")) if p.name != "scripts.md"] + [
    SPEC, USAGE, REPO / "TEST.md"]  # scripts.md belongs to the engine change and follows separately


@pytest.mark.parametrize("path", ROUTE_DOCS, ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_routes_are_passed_as_one_argument(path: Path) -> None:
    # `--route /` made Copilot ask for path access to `/`.
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"--route [</A-Z]", text), f"{path.relative_to(REPO)}: write --route=<route>"


@pytest.mark.parametrize("path", [p for p in skill_files() if "`&&`" in p.read_text(encoding="utf-8")],
                         ids=lambda p: p.parent.name)
def test_batching_advice_names_the_powershell_caveat(path: Path) -> None:
    assert "powershell 5.1" in _flat(path), f"{path.parent.name}: Windows PowerShell 5.1 has no `&&`"


def test_extract_asks_theme_switch_and_reduced_motion() -> None:
    flat = _flat(SKILLS / "extract/SKILL.md")
    for phrase in ("theme_switch", "reduced_motion", "$extensions.plumb.web.theme_switch",
                   "$extensions.plumb.motion.reduced", "always ask these two", "prefers-reduced-motion", ".dark"):
        assert phrase in flat, f"extract: {phrase!r}"


def test_create_shows_the_stylesheet_diff_and_passes_the_settings_as_answers() -> None:
    flat = _flat(SKILLS / "create/SKILL.md")
    assert "`build-tokens.py --check` prints the diff" in flat
    assert "`theme_switch` / `reduced_motion`" in flat
    assert "`theme_switch`" in _flat(REFERENCE / "interview.md") and "`reduced_motion`" in _flat(REFERENCE / "interview.md")


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
