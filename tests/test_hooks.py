"""Plumb's hooks, end to end: session start, the pre-edit guards and checks, the end-of-turn check.

Every case runs the hook as the CLI does: through hooks/run.sh (sh on macOS, Linux and Git Bash on Windows) and, on
Windows, through hooks.json's powershell command (run.cmd), with real Claude Code payload samples from
tests/fixtures/hooks/claude/. It asserts the exit code, stdout and stderr. Copilot CLI's shapes are in test_copilot.py;
the launcher itself in test_run_sh.py. The last section unit-tests _hooklib's parsers in-process and audit.py's
--snapshot / --changed modes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

from hook_support import (BUILD_PROTOTYPE, BUILD_TOKENS, CI, HOOKS, LAUNCHERS, MAP, PLUGIN, PROPOSALS, REPO, SCREENS,
                          SKILL_REL, actionable, allowed, build_proposal, context, git, git_init, hook_env, make_project,
                          needs_git, notes, patch, payload, plant_markers, plugin_copy, plumb_md, plumb_tmp, read,
                          refused, run_hook, run_script, set_plumb, write)

pytestmark = pytest.mark.skipif(not LAUNCHERS, reason="no hook launcher (sh or PowerShell) on this machine")


@pytest.fixture(params=LAUNCHERS)
def launcher(request) -> str:
    return request.param


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    return make_project(tmp_path)


def pre(launcher: str, tmp_path: Path, proj: Path, name: str, copilot: bool = False, env=None, cwd=None, **values):
    values.setdefault("CWD", str(proj))
    return run_hook(launcher, "pre_edit.py", payload("claude", name, **values), cwd or proj,
                    hook_env(tmp_path, copilot, env))


def edit(launcher, tmp_path, proj, rel: str, old: str, new: str, **kw):
    return pre(launcher, tmp_path, proj, "edit", FILE=str(proj / rel), OLD=old, NEW=new, **kw)


def write_tool(launcher, tmp_path, proj, rel: str, content: str, **kw):
    return pre(launcher, tmp_path, proj, "write", FILE=str(proj / rel), CONTENT=content, **kw)


def bash(launcher, tmp_path, proj, command: str, name: str = "bash", **kw):
    return pre(launcher, tmp_path, proj, name, COMMAND=command, **kw)


def session_start(launcher, tmp_path, proj, copilot=False, env=None, session="sess-1"):
    return run_hook(launcher, "session_start.py", payload("claude", "session_start", CWD=str(proj), SESSION=session),
                    proj, hook_env(tmp_path, copilot, env))


def stop(launcher, tmp_path, proj, active=False, copilot=False, env=None, session="sess-1"):
    return run_hook(launcher, "stop_check.py", payload("claude", "stop", CWD=str(proj), ACTIVE=active, SESSION=session),
                    proj, hook_env(tmp_path, copilot, env))


def snapshots(tmp_path: Path):
    folder = plumb_tmp(tmp_path)
    return sorted(p for p in folder.glob("*.json") if not p.name.endswith((".blocked.json", ".summary.json"))) \
        if folder.is_dir() else []


RAW = 'className="bg-[#ff0000]"'
H1 = "<h1>Today&apos;s tables</h1>"
H1_RAW = f"<h1 {RAW}>Today&apos;s tables</h1>"


# ---------------------------------------------------------------- session start


STATUS = re.compile(r"^Plumb: demo-design-system 1\.0\.0 · tokens (up to date|stale) · (\d+ audit issues?|audit not run) · "
                    r"read the skill before UI changes$")


def test_session_start_prints_the_status_line(launcher, tmp_path, proj):
    text = context(session_start(launcher, tmp_path, proj))
    first = text.splitlines()[0]
    m = STATUS.match(first)
    assert m, text
    assert m.group(1) == "up to date"
    assert re.match(r"\d+ audit issues?", m.group(2)), first
    assert "run /plumb:upgrade" not in text and "warning:" not in text


def test_session_start_says_tokens_are_stale(launcher, tmp_path, proj):
    tokens = proj / SKILL_REL / "assets/tokens/demo.tokens.json"
    doc = json.loads(read(tokens))
    doc["radius"]["md"]["$value"] = "9px" if doc["radius"]["md"]["$value"] != "9px" else "10px"
    write(tokens, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    text = context(session_start(launcher, tmp_path, proj))
    assert "· tokens stale ·" in text.splitlines()[0], text


def test_session_start_audit_capped_says_audit_not_run(launcher, tmp_path, proj):
    text = context(session_start(launcher, tmp_path, proj, env={"PLUMB_AUDIT_TIMEOUT": "0"}))
    assert "· audit not run ·" in text.splitlines()[0], text


def test_session_start_is_silent_without_plumb_md(launcher, tmp_path):
    empty = tmp_path / "no-plumb"
    empty.mkdir()
    r = session_start(launcher, tmp_path, empty)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    assert snapshots(tmp_path) == []


def test_session_start_is_silent_in_the_plumb_repo(launcher, tmp_path):
    r = session_start(launcher, tmp_path, REPO)
    assert r.returncode == 0 and r.stdout == ""


def test_session_start_nudges_an_upgrade_when_the_project_is_older(launcher, tmp_path, proj):
    set_plumb(proj, version="0.9.0")
    text = context(session_start(launcher, tmp_path, proj))
    assert text.startswith("Plumb: demo-design-system 0.9.0 · ")
    assert "Plumb 1.0.0 is installed; this project's design system is 0.9.0: run /plumb:upgrade" in text


def test_session_start_no_nudge_when_the_project_is_newer(launcher, tmp_path, proj):
    set_plumb(proj, version="1.0.10")
    assert "run /plumb:upgrade" not in context(session_start(launcher, tmp_path, proj))


def test_session_start_warns_when_the_linked_design_system_is_missing(launcher, tmp_path, proj):
    set_plumb(proj, role="linked", skill="../home-repo/.claude/skills/demo-design-system")
    lines = context(session_start(launcher, tmp_path, proj)).splitlines()
    assert lines[0].startswith("Plumb: demo-design-system 1.0.0 · design system not found")
    warn = next(i for i, ln in enumerate(lines) if ln.startswith("warning: "))
    assert "../home-repo/.claude/skills/demo-design-system/" in lines[warn] and "linked" in lines[warn]
    assert lines[warn + 1].startswith("fix: ")


def test_session_start_writes_the_snapshot_and_cleans_old_ones(launcher, tmp_path, proj):
    folder = plumb_tmp(tmp_path)
    folder.mkdir(parents=True)
    old = folder / "0123456789ab-old.json"
    old.write_text("{}", encoding="utf-8")
    week_ago = time.time() - 8 * 24 * 3600
    os.utime(str(old), (week_ago, week_ago))
    fresh = folder / "0123456789ab-fresh.json"
    fresh.write_text("{}", encoding="utf-8")
    r = session_start(launcher, tmp_path, proj, session="abc-123")
    assert r.returncode == 0, r.stderr
    assert not old.exists() and fresh.exists()
    (snap,) = [p for p in snapshots(tmp_path) if p.name.endswith("-abc-123.json")]
    data = json.loads(read(snap))
    assert data["mode"] == "mtime" and data["version"] == 1
    assert "app/page.tsx" in data["mtimes"] and f"{SCREENS}/home.html" in data["mtimes"]
    assert not any(k.startswith(SKILL_REL) for k in data["mtimes"])
    # a resumed session keeps its first snapshot
    before = read(snap)
    write(proj / "app/page.tsx", read(proj / "app/page.tsx") + "\n")
    session_start(launcher, tmp_path, proj, session="abc-123")
    assert read(snap) == before


@needs_git
def test_session_start_snapshot_in_git_records_changed_files(launcher, tmp_path, proj):
    git_init(proj)
    write(proj / "components/draft.tsx", "export const Draft = () => <p>draft</p>;\n")
    write(proj / "app/page.tsx", read(proj / "app/page.tsx") + "// wip\n")
    session_start(launcher, tmp_path, proj)
    (snap,) = snapshots(tmp_path)
    data = json.loads(read(snap))
    assert data["mode"] == "git" and re.fullmatch(r"[0-9a-f]{40}", data["head"])
    assert sorted(data["files"]) == ["app/page.tsx", "components/draft.tsx"]
    assert data["files"]["components/draft.tsx"]["text"].startswith("export const Draft")


def test_session_start_fails_open_with_a_broken_plugin_audit(launcher, tmp_path, proj):
    plugin = plugin_copy(tmp_path)
    write(plugin / "assets/skill/scripts/audit.py", "raise RuntimeError('broken')\n")
    r = session_start(launcher, tmp_path, proj, env={"CLAUDE_PLUGIN_ROOT": str(plugin)})
    text = context(r)
    assert text.startswith("Plumb: demo-design-system 1.0.0 · ")
    assert "audit not run" in text
    assert len(notes(r)) <= 1 and len(r.stderr.splitlines()) <= (1 if launcher == "sh" else 20)


# ---------------------------------------------------------------- trust boundary: hooks run only the plugin's own code


def test_hooks_never_run_the_projects_copied_scripts(launcher, tmp_path, proj):
    markers = plant_markers(proj, tmp_path)
    _start(launcher, tmp_path, proj)
    # the checks still work, with the plugin's own scripts
    assert "#ff0000" in refused(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW))
    assert "/plumb:prototype billing" in refused(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    assert "#ff0000" in _block(stop(launcher, tmp_path, proj))
    assert [m.name for m in markers if m.exists()] == []


def test_project_scripts_of_another_version_get_one_note(launcher, tmp_path, proj):
    core = proj / SKILL_REL / "scripts/_plumb.py"
    write(core, read(core).replace('PLUMB_VERSION = "1.0.0"', 'PLUMB_VERSION = "0.9.0"'))
    markers = plant_markers(proj, tmp_path)
    text = context(session_start(launcher, tmp_path, proj))
    assert "this project's Plumb scripts are v0.9.0; the plugin is v1.0.0 — run /plumb:upgrade" in text
    # the plugin's generator may differ from the project's: no "stale" verdict from another version's rules
    assert text.startswith("Plumb: demo-design-system 1.0.0 · tokens not checked (scripts v0.9.0 ≠ v1.0.0) · ")
    assert [m.name for m in markers if m.exists()] == []
    assert "Plumb scripts are" not in context(session_start(launcher, tmp_path, make_project(tmp_path, "other")))


# ---------------------------------------------------------------- pre-edit: generated files


GENERATED = [
    f"{SKILL_REL}/assets/platforms/web/tokens.css",
    "app/globals.css",
    f"{SKILL_REL}/assets/platforms/mobile/ios/DemoTheme.swift",
    f"{SKILL_REL}/assets/platforms/mobile/android/DemoTheme.kt",
    "docs/design/specimen.html",
    "docs/design/prototype.html",
    "docs/design/app.html",
    "docs/design/screens.html",
    MAP,
    "docs/design/tours/onboarding.html",
]


@pytest.mark.parametrize("rel", GENERATED)
def test_edit_and_write_to_generated_files_are_refused(launcher, tmp_path, proj, rel):
    reason = refused(write_tool(launcher, tmp_path, proj, rel, "/* by hand */\n"))
    actionable(reason)
    assert reason.startswith(f"error: {rel} is generated")
    command = BUILD_TOKENS if rel.endswith((".css", ".swift", ".kt", "specimen.html")) else BUILD_PROTOTYPE
    assert command in reason
    if (proj / rel).is_file():
        reason = refused(edit(launcher, tmp_path, proj, rel, "GENERATED", "generated"))
        assert reason.startswith(f"error: {rel} is generated")


def test_a_tour_page_refusal_names_its_tour_file(launcher, tmp_path, proj):
    reason = refused(write_tool(launcher, tmp_path, proj, "docs/design/tours/onboarding.html", "x"))
    assert reason.startswith("error: docs/design/tours/onboarding.html is generated by build-prototype.py from the "
                             "screen files and the tour file docs/design/prototype/tours/onboarding.json"), reason
    assert "fix: edit the tour file docs/design/prototype/tours/onboarding.json (or the screen files in " in reason
    reason = refused(write_tool(launcher, tmp_path, proj, "docs/design/prototype.html", "x"))
    assert "from the screen files; a hand edit" in reason and "tour file" not in reason


def test_generated_file_given_as_a_relative_path_is_refused(launcher, tmp_path, proj):
    reason = refused(pre(launcher, tmp_path, proj, "write", FILE="app/globals.css", CONTENT="x"))
    assert reason.startswith("error: app/globals.css is generated")


BLOCK_END = "/* plumb:end */"


def test_block_markers_match_the_core():
    hooklib = read(HOOKS / "_hooklib.py")
    core = read(PLUGIN / "assets/skill/scripts/_plumb.py")
    for marker in ('BLOCK_START = "/* plumb:start \\u2014 GENERATED by Plumb, do not edit inside */"',
                   'BLOCK_END = "/* plumb:end */"'):
        assert marker in hooklib and marker in core


def test_a_web_copy_is_the_projects_outside_plumbs_block(launcher, tmp_path, proj):
    css = proj / "app/globals.css"
    text = read(css)
    assert text.count(BLOCK_END) == 1
    own = "\nbody {\n  margin: 0;\n}\n"
    # an edit after the block, or a whole-file write that keeps the block as it is: the project's own CSS
    allowed(edit(launcher, tmp_path, proj, "app/globals.css", BLOCK_END + "\n", BLOCK_END + "\n" + own))
    allowed(write_tool(launcher, tmp_path, proj, "app/globals.css", text + own))
    write(css, text + own)
    allowed(edit(launcher, tmp_path, proj, "app/globals.css", "margin: 0;", "margin: 0 auto;"))
    # an edit inside the block, a write that drops it, or a shell write: refused with the way out
    reason = refused(edit(launcher, tmp_path, proj, "app/globals.css", "color-scheme: dark;", "color-scheme: light;"))
    actionable(reason)
    assert reason.startswith("error: app/globals.css is generated from the design tokens between its /* plumb:start")
    assert "edit only outside the block" in reason and BUILD_TOKENS in reason
    assert refused(write_tool(launcher, tmp_path, proj, "app/globals.css", own)).startswith("error: app/globals.css")
    assert " is generated" in refused(bash(launcher, tmp_path, proj, "sed -i '' 's/margin: 0/margin: 1px/' app/globals.css"))
    assert " is generated" in refused(bash(launcher, tmp_path, proj, "rm app/globals.css"))


def test_a_web_copy_without_a_block_yet_is_the_projects_own_file(launcher, tmp_path, proj):
    write(proj / "app/globals.css", '@import "tailwindcss";\n\nbody { margin: 0; }\n')
    allowed(edit(launcher, tmp_path, proj, "app/globals.css", "margin: 0;", "margin: 1px;"))
    write(proj / "app/globals.css", "/* GENERATED by x/build-tokens.py. Do not edit. */\n:root {}\n")  # an old whole copy
    assert " is generated" in refused(edit(launcher, tmp_path, proj, "app/globals.css", ":root {}", ":root { }"))


@pytest.mark.parametrize("command", [
    "sed -i '' 's/a/b/' app/globals.css",
    "sed -i.bak -e 's/a/b/' docs/design/prototype.html",
    "echo '<p>x</p>' > docs/design/screens.html",
    "printf 'x' >> docs/design/specimen.html",
    "cat new.json | tee docs/design/prototype/screens.json",
    "cat a.css | tee -a .claude/skills/demo-design-system/assets/platforms/web/tokens.css > /dev/null",
    "cp /tmp/theme.swift .claude/skills/demo-design-system/assets/platforms/mobile/ios/DemoTheme.swift",
    "mv draft.kt .claude/skills/demo-design-system/assets/platforms/mobile/android/DemoTheme.kt",
    "cd docs/design && echo x > tours/intro.html",
    "python3 -c \"open('app/globals.css', 'w').write('x')\"",
    f"{BUILD_TOKENS} --css-vars > app/globals.css",
])
def test_shell_writes_to_generated_files_are_refused(launcher, tmp_path, proj, command):
    reason = refused(bash(launcher, tmp_path, proj, command))
    actionable(reason)
    assert " is generated" in reason


@pytest.mark.parametrize("command", [
    "Set-Content -Path app/globals.css -Value 'x'",
    "'x' | Out-File docs\\design\\specimen.html",
    "Add-Content docs/design/prototype.html '<p>'",
    "Copy-Item C:\\temp\\theme.css -Destination app\\globals.css",
])
def test_powershell_writes_to_generated_files_are_refused(launcher, tmp_path, proj, command):
    reason = refused(bash(launcher, tmp_path, proj, command, name="powershell"))
    assert " is generated" in reason


@pytest.mark.parametrize("command", [
    f"{BUILD_TOKENS}",
    f"python3 {SKILL_REL}/scripts/build-tokens.py --check > /tmp/out.txt",
    f"{BUILD_PROTOTYPE} --approve home",
    f"uv run python {SKILL_REL}/scripts/build-prototype.py && git add docs/design/prototype.html",
    "cat app/globals.css",
    "cp app/globals.css /tmp/backup.css",
    "git diff -- docs/design/screens.html",
    "git checkout -- app/globals.css",
    "grep -n primary app/globals.css > /tmp/hits.txt",
    "echo hello > notes.txt",
    "ls docs/design 2>&1 >/dev/null",
])
def test_shell_reads_and_plumb_builds_are_allowed(launcher, tmp_path, proj, command):
    allowed(bash(launcher, tmp_path, proj, command))


@pytest.mark.parametrize("rel", [
    f"{SKILL_REL}/assets/tokens/demo.tokens.json",
    f"{SKILL_REL}/assets/platforms/web/tokens.css.template",
    f"{SKILL_REL}/SKILL.md",
    f"{SCREENS}/home.html",
    "docs/design/decisions.md",
    "README.md",
])
def test_your_files_are_not_guarded(launcher, tmp_path, proj, rel):
    allowed(write_tool(launcher, tmp_path, proj, rel, "notes\n"))


# ---------------------------------------------------------------- pre-edit: proposal pages

PROPOSAL = f"{PROPOSALS}/nav"
PROPOSAL_PAGES = [f"{PROPOSAL}/index.html", f"{PROPOSAL}/a-calm/prototype.html", f"{PROPOSAL}/a-calm/app.html",
                  f"{PROPOSAL}/a-calm/screens.html"]


@pytest.mark.parametrize("rel", PROPOSAL_PAGES)
def test_edit_and_write_to_proposal_pages_are_refused(launcher, tmp_path, proj, rel):
    build_proposal(proj)
    assert "--proposal nav" in "\n".join(read(proj / rel).splitlines()[:3])
    for r in (write_tool(launcher, tmp_path, proj, rel, "<p>by hand</p>\n"),
              edit(launcher, tmp_path, proj, rel, "GENERATED", "generated")):
        reason = refused(r)
        actionable(reason)
        assert reason.startswith(f"error: {rel} is generated by build-prototype.py from the screen files of the "
                                 f"proposal nav"), reason
        assert f"{BUILD_PROTOTYPE} --proposal nav" in reason
        where = f"{PROPOSAL}/a-calm/screens/" if "/a-calm/" in rel else f"{PROPOSAL}/<variant>/"
        assert where in reason


@pytest.mark.parametrize("command", [
    f"echo x > {PROPOSAL}/a-calm/app.html",
    f"sed -i.bak 's/a/b/' {PROPOSAL}/index.html",
    f"cp /tmp/x.html {PROPOSAL}/a-calm/screens.html",
    f"rm -rf {PROPOSAL}",  # a folder that holds generated pages
    f"rm {PROPOSAL}/a-calm/prototype.html",
    f"for f in {PROPOSAL}/*/app.html; do echo x > \"$f\"; done",
    "cd docs/design/prototype/proposals && echo x > nav/index.html",
    f"python3 -c \"open('{PROPOSAL}/a-calm/app.html', 'w').write('x')\"",
])
def test_shell_writes_to_proposal_pages_are_refused(launcher, tmp_path, proj, command):
    build_proposal(proj)
    reason = refused(bash(launcher, tmp_path, proj, command))
    actionable(reason)
    assert "proposal" in reason, reason


def test_a_proposal_page_not_built_yet_is_refused(launcher, tmp_path, proj):
    reason = refused(write_tool(launcher, tmp_path, proj, f"{PROPOSALS}/menu/b-dense/app.html", "x"))
    assert reason.startswith("error: docs/design/prototype/proposals/menu/b-dense/app.html is generated by "
                             "build-prototype.py from the screen files of the proposal menu")
    assert f"{BUILD_PROTOTYPE} --proposal menu" in reason


@pytest.mark.parametrize("rel", [
    f"{PROPOSAL}/a-calm/screens/home.html",  # a variant's screen file: yours
    f"{PROPOSAL}/a-calm/screens/_shared/base.css",
    f"{PROPOSAL}/a-calm/idea.md",
    f"{PROPOSAL}/changes.md",
    f"{PROPOSAL}/a-calm/notes.html",  # not a page the build writes
    f"{PROPOSAL}/a-calm/deep/app.html",
    f"{PROPOSALS}/index.html",
])
def test_a_proposal_s_own_files_are_not_guarded(launcher, tmp_path, proj, rel):
    build_proposal(proj)
    allowed(write_tool(launcher, tmp_path, proj, rel, "notes\n"))
    allowed(bash(launcher, tmp_path, proj, f"echo x > {rel}"))


def test_a_hand_written_page_in_a_proposal_folder_is_left_alone(launcher, tmp_path, proj):
    """A page there without the header `build-prototype.py --proposal` writes is someone's own (as a tour page without
    the GENERATED header is): build-prototype.py and build-tokens.py never refresh it, and the guard leaves it alone.
    So is a page another tool generated there."""
    mine = f"{PROPOSALS}/mine"
    write(proj / mine / "index.html", "<!doctype html>\n<p>My notes on the options</p>\n")
    write(proj / mine / "a-one/app.html", "<!-- GENERATED by another tool. Do not edit. -->\n<p>x</p>\n")
    for rel in (f"{mine}/index.html", f"{mine}/a-one/app.html"):
        allowed(edit(launcher, tmp_path, proj, rel, "<p>", "<p class=\"x\">"))
        allowed(write_tool(launcher, tmp_path, proj, rel, "<p>mine</p>\n"))
        allowed(bash(launcher, tmp_path, proj, f"echo x >> {rel}"))
    allowed(bash(launcher, tmp_path, proj, f"rm -rf {mine}"))


# ---------------------------------------------------------------- pre-edit: Plumb's own files


PLUMB_OWN = (f"{SKILL_REL}/scripts/audit.py", f"{SKILL_REL}/scripts/_plumb.py", f"{SKILL_REL}/templates/player.js",
             f"{SKILL_REL}/templates/specimen.html.tmpl", f"{SKILL_REL}/assets/platforms/README.md")
OWN_FIX = "fix: use /plumb:update for design changes, or propose the improvement to the Plumb repo"


@pytest.mark.parametrize("rel", PLUMB_OWN)
def test_plumb_files_in_the_project_skill_are_refused(launcher, tmp_path, proj, rel):
    reason = refused(edit(launcher, tmp_path, proj, rel, "a", "b"))
    assert reason.startswith(f"error: {rel} is Plumb's file; upgrades replace it")
    assert OWN_FIX in reason
    actionable(reason)


@pytest.mark.parametrize("rel", ["hooks/pre_edit.py", "scripts/scaffold.py", "assets/skill/scripts/audit.py",
                                 "templates/PLUMB.md", "hooks/hooks.json"])
def test_files_under_the_plugin_root_are_refused_in_a_plumb_project(launcher, tmp_path, proj, rel):
    reason = refused(pre(launcher, tmp_path, proj, "edit", FILE=str(PLUGIN / rel), OLD="a", NEW="b"))
    assert "is Plumb's file; upgrades replace it" in reason and OWN_FIX in reason


def test_shell_writes_to_plumb_files_are_refused(launcher, tmp_path, proj):
    reason = refused(bash(launcher, tmp_path, proj, f"sed -i 's/x/y/' {SKILL_REL}/scripts/audit.py"))
    assert OWN_FIX in reason
    reason = refused(bash(launcher, tmp_path, proj, f"echo x >> {PLUGIN / 'hooks' / 'run.sh'}"))
    assert OWN_FIX in reason


@pytest.mark.parametrize("command, name, what", [
    ("rm app/globals.css", "bash", " is generated"),
    ("rm -f docs/design/prototype.html", "bash", " is generated"),
    ("mv docs/design/prototype/screens.json /tmp/x.json", "bash", " is generated"),
    ("rm -rf docs/design", "bash", " is generated"),  # a folder that holds generated files
    (f"rm {SKILL_REL}/scripts/audit.py", "bash", "is Plumb's file"),
    (f"git rm -q {SKILL_REL}/templates/player.js", "bash", "is Plumb's file"),
    (f"rm -rf {SKILL_REL}/templates", "bash", "is Plumb's file"),
    (f"unlink {SKILL_REL}/assets/platforms/README.md", "bash", "is Plumb's file"),
    (f"rm -rf {PLUGIN / 'hooks'}", "bash", "is Plumb's file"),
    ("Remove-Item -Path app/globals.css", "powershell", " is generated"),
    ("del app\\globals.css", "powershell", " is generated"),
    ("Move-Item docs/design/specimen.html C:\\temp\\s.html", "powershell", " is generated"),
    (f"ri -Recurse -Force {SKILL_REL}\\scripts", "powershell", "is Plumb's file"),
])
def test_shell_removals_of_guarded_files_are_refused(launcher, tmp_path, proj, command, name, what):
    reason = refused(bash(launcher, tmp_path, proj, command, name=name))
    actionable(reason)
    assert what in reason


@pytest.mark.parametrize("command", ["rm notes.txt", "rm -rf node_modules /tmp/build", "mv README.md docs/README.md",
                                     "git rm --cached README.md", "Remove-Item -Recurse dist", "rm -rf components/ui"])
def test_shell_removals_of_your_files_are_allowed(launcher, tmp_path, proj, command):
    allowed(bash(launcher, tmp_path, proj, command))


@pytest.mark.parametrize("command", ["sed -i 's/a/b/' $HOME/.plumb-test/x.css", "echo x > ${HOME}/.plumb-test/x.css",
                                     "rm $HOME/.plumb-test/x.css"])
def test_shell_paths_under_home_variables_are_expanded(H, command, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    expected = os.path.normpath(str(tmp_path / "home" / ".plumb-test" / "x.css"))
    found = _targets(H, command, str(tmp_path)) + _removals(H, command, str(tmp_path))
    assert expected in found, found


@pytest.mark.parametrize("command, removed", [
    ("rm -rf a b", ["a", "b"]),
    ("rm -- -odd", ["-odd"]),
    ("mv a b", ["a"]),
    ("mv a b c dest", ["a", "b", "c"]),
    ("git rm -r --cached x", ["x"]),
    ("git mv x y", ["x"]),
    ("unlink z", ["z"]),
    ("rmdir d", ["d"]),
    ("Remove-Item -LiteralPath a.css -Force", ["a.css"]),
    ("Remove-Item a.css, b.css", ["a.css", "b.css"]),
    ("del /q /s a.css", ["a.css"]),
    ("Move-Item -Path a.css -Destination b.css", ["a.css"]),
    ("cat a; ls b", []),
])
def test_shell_removal_targets(H, command, removed, tmp_path):
    found = [Path(t) for t in _removals(H, command, str(tmp_path))]
    assert [str(p.relative_to(tmp_path)).replace("\\", "/") for p in found] == removed


# Live test 2 (B12): a python heredoc whose comment has an apostrophe (next/font's) and whose body writes the screen
# files given on its command line, then a cd and a build-prototype.py run. Refused as if it wrote build-prototype.py.
HEREDOC_THEN_BUILD = (
    'D="{screens}"; python3 -I - "$D/dashboard.html" "$D/api-keys.html" <<\'EOF\'\n'
    "import sys, re\n"
    "# --font-sans resolves at :root, where next/font's variable is undefined, so a var() fallback is used.\n"
    "for p in sys.argv[1:]:\n"
    "    s = open(p).read()\n"
    "    s = s.replace(\"font-family: var(--font-sans);\", 'font-family: var(--font-sans, system-ui, sans-serif);')\n"
    "    open(p, \"w\").write(s); print(p.rsplit(\"/\",1)[1])\n"
    "EOF\n"
    'cd "{root}" && python3 {skill}/scripts/build-prototype.py 2>&1 | tail -1'
)


def test_a_heredoc_script_then_a_plumb_build_is_allowed(launcher, tmp_path, proj):
    command = HEREDOC_THEN_BUILD.format(screens=proj / SCREENS, root=proj, skill=SKILL_REL)
    allowed(bash(launcher, tmp_path, proj, command))


def test_heredoc_bodies_are_read_as_the_stage_input(H, tmp_path):
    command = HEREDOC_THEN_BUILD.format(screens=tmp_path / "s", root=tmp_path, skill=SKILL_REL)
    targets = [Path(t) for t in _targets(H, command, str(tmp_path))]
    assert not any(t.name == "build-prototype.py" for t in targets), targets
    # a heredoc that writes a guarded file it names is still caught, and so is a shell heredoc's own command
    for cmd, name in (("python3 - <<EOF\nopen('app/globals.css', 'w').write('x')\nEOF", "globals.css"),
                      ("bash <<'X'\necho x > docs/design/specimen.html\nX\necho done", "specimen.html"),
                      ("cat > app/globals.css <<'EOF'\nbody {}\nEOF", "globals.css"),
                      ("cat <<-EOF > docs/design/screens.html\n\t<p>it's</p>\n\tEOF", "screens.html")):
        found = [Path(t).name for t in _targets(H, cmd, str(tmp_path))]
        assert name in found, (cmd, found)
    assert _targets(H, "cat <<< 'x' > notes.txt", str(tmp_path)) == [str(tmp_path / "notes.txt")]


def test_an_arithmetic_shift_is_not_a_heredoc(H, tmp_path, launcher, proj):
    """Review M1: `$((a<<b))` must not read the next lines as a here-document body (they would escape the guard)."""
    for cmd in ("echo $((a<<b))\nrm app/globals.css", "x=$(( a << b )); rm app/globals.css",
                "(( n = a<<b ))\nrm app/globals.css"):
        removed = [Path(t).name for t in _removals(H, cmd, str(tmp_path))]
        assert "globals.css" in removed, (cmd, removed)
    reason = refused(bash(launcher, tmp_path, proj, "echo $((a<<b))\nrm app/globals.css"))
    assert " is generated" in reason
    # a real here-document right after arithmetic is still one
    found = [Path(t).name for t in _targets(H, "echo $((1<<2)); bash <<X\necho x > app/globals.css\nX",
                                                   str(tmp_path))]
    assert "globals.css" in found


@pytest.mark.parametrize("cmd", [
    'bash -c "rm app/globals.css"',
    "sh -c 'rm -f app/globals.css'",
    'zsh -lc "echo x > app/globals.css"',
    "bash -ec 'cd . && mv app/globals.css /tmp/x'",
    'pwsh -c "Remove-Item app/globals.css"',
    'powershell -NoProfile -Command "Set-Content app/globals.css x"',
    'powershell -Command Remove-Item app/globals.css',
])
def test_a_shell_c_script_is_read_as_commands(H, tmp_path, cmd, launcher, proj):
    """Review M9: `bash -c "…"` (and sh, zsh, pwsh -c, powershell -Command) runs its script: its writes and removals
    count like any other."""
    found = [Path(t).name for t in _targets(H, cmd, str(tmp_path)) + _removals(H, cmd, str(tmp_path))]
    assert "globals.css" in found, (cmd, found)
    reason = refused(bash(launcher, tmp_path, proj, cmd))
    assert " is generated" in reason or "Plumb" in reason


def test_a_shell_c_script_that_only_reads_is_allowed(H, tmp_path):
    assert _targets(H, 'bash -c "cat app/globals.css | wc -l"', str(tmp_path)) == []
    assert _removals(H, "sh -c 'ls app'", str(tmp_path)) == []


def test_a_heredoc_writing_a_generated_file_is_refused(launcher, tmp_path, proj):
    reason = refused(bash(launcher, tmp_path, proj, "python3 - <<'EOF'\n# it's the copy\n"
                                                    "open('app/globals.css', 'w').write('x')\nEOF"))
    assert " is generated" in reason


def test_running_plumb_scripts_is_allowed(launcher, tmp_path, proj):
    allowed(bash(launcher, tmp_path, proj, f"python3 {SKILL_REL}/scripts/audit.py app"))
    allowed(bash(launcher, tmp_path, proj, f"python3 {PLUGIN / 'scripts' / 'scaffold.py'} --help"))


def test_plumb_repo_itself_is_never_blocked(launcher, tmp_path):
    """No PLUMB.md: developing Plumb (its hooks, scripts, templates, fixtures) is never refused."""
    for rel in ("plugins/plumb/hooks/pre_edit.py", "plugins/plumb/assets/skill/scripts/audit.py",
                "plugins/plumb/templates/PLUMB.md", "tests/fixtures/projects/fidelity/next/app/page.tsx"):
        r = run_hook(launcher, "pre_edit.py", payload("claude", "edit", CWD=str(REPO), FILE=str(REPO / rel), OLD="a",
                                                      NEW=RAW), REPO, hook_env(tmp_path))
        allowed(r)
        assert r.stderr == ""
    allowed(run_hook(launcher, "pre_edit.py", payload("claude", "bash", CWD=str(REPO),
                                                      COMMAND="sed -i 's/a/b/' plugins/plumb/hooks/run.sh"),
                     REPO, hook_env(tmp_path)))


def test_project_without_plumb_md_is_never_blocked(launcher, tmp_path, proj):
    (proj / "PLUMB.md").unlink()
    allowed(edit(launcher, tmp_path, proj, f"{SKILL_REL}/scripts/audit.py", "a", "b"))
    allowed(write_tool(launcher, tmp_path, proj, "app/globals.css", "x"))
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", f"export default () => <p {RAW}/>;\n"))


# ---------------------------------------------------------------- pre-edit: prototype first


BILLING = "export default function Billing() {\n  return <main><h1>Billing</h1></main>;\n}\n"
BILLING_SCREEN = ('<section data-screen="billing" data-title="Billing" data-order="4">\n'
                  '  <div data-state="ready"><h1>Billing</h1></div>\n</section>\n')


def test_new_route_without_an_approved_screen_is_refused(launcher, tmp_path, proj):
    reason = refused(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))
    assert "error: app/billing/page.tsx is a new screen with no approved prototype" in reason
    assert "fix: /plumb:prototype billing" in reason


def test_new_route_in_a_route_group_uses_the_url_slug(launcher, tmp_path, proj):
    reason = refused(write_tool(launcher, tmp_path, proj, "app/(shop)/checkout/page.tsx", BILLING))
    assert "fix: /plumb:prototype checkout" in reason


def test_new_route_is_allowed_once_its_screen_is_approved(launcher, tmp_path, proj):
    write(proj / SCREENS / "billing.html", BILLING_SCREEN)
    r = run_script(proj, "build-prototype.py")
    assert r.returncode == 0, r.stderr
    reason = refused(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))
    assert "error: app/billing/page.tsx is a new screen whose prototype (screen billing) is not approved yet" in reason
    assert "ask the user: " in reason and "--approve billing" in reason
    r = run_script(proj, "build-prototype.py", "--approve", "billing")
    assert r.returncode == 0, r.stderr
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))


def test_new_route_mapped_to_an_approved_screen_is_allowed(launcher, tmp_path, proj):
    write(proj / SCREENS / "invoices.html", BILLING_SCREEN.replace("billing", "invoices"))
    assert run_script(proj, "build-prototype.py", "--map", "invoices", "--route", "/billing", "--files",
                      "app/billing/**").returncode == 0
    assert run_script(proj, "build-prototype.py", "--approve", "invoices").returncode == 0
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))


def test_screen_changed_after_approval_does_not_cover_a_new_route(launcher, tmp_path, proj):
    write(proj / SCREENS / "billing.html", BILLING_SCREEN)
    assert run_script(proj, "build-prototype.py", "--approve", "billing").returncode == 0
    write(proj / SCREENS / "billing.html", BILLING_SCREEN.replace("<h1>Billing</h1>", "<h1>Invoices</h1>"))
    assert "is not approved yet" in refused(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))


def test_an_approval_covers_the_shared_files_it_saw(launcher, tmp_path, proj):
    """The screens folder's _shared/*.css and *.js are part of every screen's approval: approved with them, the route
    is allowed; a shared file changed since, it is not."""
    write(proj / SCREENS / "billing.html", BILLING_SCREEN)
    write(proj / SCREENS / "_shared/base.css", "[data-screen] { color: inherit; }\n")
    assert run_script(proj, "build-prototype.py", "--approve", "billing").returncode == 0
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))
    write(proj / SCREENS / "_shared/base.css", "[data-screen] { color: red; }\n")
    assert "is not approved yet" in refused(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))


def test_new_route_in_a_monorepo_frontend_is_refused(launcher, tmp_path, proj):
    """The live-test monorepo: Next.js only in frontend/ (no next.config or next dependency at the repo root, where
    the design system is), Python in backend/. PLUMB.md's Routes: names frontend/src/app; nothing else is read."""
    text = read(proj / "PLUMB.md").replace("Routes: app (next-app)", "Routes: frontend/src/app (next-app)")
    write(proj / "PLUMB.md", text.replace("UI files: app/**, components/**", "UI files: frontend/src/**"))
    write(proj / "frontend/package.json", '{"dependencies": {"next": "16.0.0"}}\n')
    write(proj / "backend/main.py", "print('api')\n")
    reason = refused(write_tool(launcher, tmp_path, proj, "frontend/src/app/usage-reports/page.tsx", BILLING))
    assert "error: frontend/src/app/usage-reports/page.tsx is a new screen with no approved prototype" in reason
    assert "fix: /plumb:prototype usage-reports" in reason
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))  # not a recorded route root


def test_prototype_first_fails_open_when_routes_are_not_recorded(launcher, tmp_path, proj):
    """A PLUMB.md from before Routes: (or not filled yet): no guessing from next.config or package.json; the edit is
    allowed and session start says the routes are not recorded."""
    write(proj / "PLUMB.md", read(proj / "PLUMB.md").replace("Routes: app (next-app)\n", ""))
    write(proj / "next.config.mjs", "export default {};\n")
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))
    text = context(session_start(launcher, tmp_path, proj))
    assert "Routes not recorded \u2014 run /plumb:init to record them" in text
    write(proj / "PLUMB.md", read(proj / "PLUMB.md").replace(
        "Allowed raw values:", "Routes: (not recorded yet: /plumb:init records the app's page roots)\nAllowed raw values:"))
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))


def test_session_start_is_quiet_about_routes_once_recorded(launcher, tmp_path, proj):
    text = context(session_start(launcher, tmp_path, proj))
    assert "Routes not recorded" not in text and ".plumb-tmp" not in text


def test_prototype_first_is_off_when_prototype_sync_is_off(launcher, tmp_path, proj):
    set_plumb(proj, sync="off")
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))


def test_existing_routes_and_non_route_files_are_not_prototype_checked(launcher, tmp_path, proj):
    allowed(edit(launcher, tmp_path, proj, "app/page.tsx", H1, "<h1>Today&apos;s bookings</h1>"))
    allowed(write_tool(launcher, tmp_path, proj, "components/billing-summary.tsx",
                       "export const BillingSummary = () => <p>Billing</p>;\n"))
    allowed(write_tool(launcher, tmp_path, proj, "app/_drafts/billing/page.tsx", BILLING))  # _private: not a route


# ---------------------------------------------------------------- pre-edit: edit check


def test_edit_adding_a_raw_colour_is_refused(launcher, tmp_path, proj):
    reason = refused(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW))
    lines = reason.strip().splitlines()
    assert lines[0] == "Plumb edit check: this edit adds 1 design-system error to app/page.tsx"
    line = next(i for i, ln in enumerate(read(proj / "app/page.tsx").splitlines(), 1) if H1 in ln)
    assert lines[1].startswith(f"error: line {line}: ") and "#ff0000" in lines[1]
    assert lines[2].startswith("fix: ")
    actionable(reason)


def test_edit_that_keeps_an_old_raw_colour_is_allowed(launcher, tmp_path, proj):
    write(proj / "components/legacy.tsx", f'export const Legacy = () => <div {RAW}>old copy</div>;\n')
    allowed(edit(launcher, tmp_path, proj, "components/legacy.tsx", "old copy", "new copy"))
    reason = refused(edit(launcher, tmp_path, proj, "components/legacy.tsx", "old copy",
                          'new copy <span className="text-[#00ff00]">!</span>'))
    assert "#00ff00" in reason and "#ff0000" not in reason


def test_multiedit_is_checked_after_every_edit(launcher, tmp_path, proj):
    r = pre(launcher, tmp_path, proj, "multiedit", FILE=str(proj / "app/page.tsx"), OLD=H1, NEW=H1_RAW,
            OLD2="<main>", NEW2="<main className=\"p-4\">")
    assert "#ff0000" in refused(r)
    allowed(pre(launcher, tmp_path, proj, "multiedit", FILE=str(proj / "app/page.tsx"), OLD=H1,
                NEW="<h1>Tables</h1>", OLD2="<main>", NEW2="<main className=\"p-4\">"))


def test_write_of_a_new_component_with_raw_values_is_refused(launcher, tmp_path, proj):
    body = "".join(f'export const C{i} = () => <p className="bg-[#{i:02d}{i:02d}{i:02d}]">x</p>;\n' for i in range(15))
    reason = refused(write_tool(launcher, tmp_path, proj, "components/swatches.tsx", body))
    errors = [ln for ln in reason.splitlines() if ln.startswith("error: line ")]
    assert len(errors) == 10
    assert "and 5 more errors" in reason.splitlines()[-1]


def test_raw_values_are_allowed_where_plumb_md_allows_them(launcher, tmp_path, proj):
    allowed(edit(launcher, tmp_path, proj, "components/ui/button.tsx", 'className="bg-primary"', RAW))


def test_edit_check_off_allows_new_errors(launcher, tmp_path, proj):
    set_plumb(proj, edit="off")
    allowed(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW))


def test_non_ui_files_are_not_edit_checked(launcher, tmp_path, proj):
    allowed(edit(launcher, tmp_path, proj, "README.md", "Notes.", "Colour #ff0000."))
    allowed(write_tool(launcher, tmp_path, proj, "lib/data.py", "COLOUR = '#ff0000'\n"))
    allowed(write_tool(launcher, tmp_path, proj, "scripts/seed.tsx", f"export const x = <p {RAW}/>;\n"))  # not in UI files


def test_edit_whose_old_string_is_missing_is_allowed(launcher, tmp_path, proj):
    allowed(edit(launcher, tmp_path, proj, "app/page.tsx", "<h2>not there</h2>", H1_RAW))


def test_crlf_file_gives_the_same_result(launcher, tmp_path, proj):
    write(proj / "app/page.tsx", read(proj / "app/page.tsx"), newline="\r\n")
    allowed(edit(launcher, tmp_path, proj, "app/page.tsx", H1, "<h1>Tables</h1>"))
    assert "#ff0000" in refused(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW))


# ---------------------------------------------------------------- pre-edit: failing open


@pytest.mark.parametrize("stdin", ["", "not json", "[1, 2]", '{"tool_name": 5}', "\x00\xff garbage",
                                   '{"tool_name": "Edit", "tool_input": "str"}'])
def test_garbage_input_is_allowed(launcher, tmp_path, proj, stdin):
    r = run_hook(launcher, "pre_edit.py", stdin, proj, hook_env(tmp_path))
    allowed(r)


def test_broken_plugin_audit_fails_open_with_one_note(launcher, tmp_path, proj):
    plugin = plugin_copy(tmp_path)
    write(plugin / "assets/skill/scripts/audit.py", "def broken(:\n")
    env = {"CLAUDE_PLUGIN_ROOT": str(plugin)}
    r = edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW, env=env)
    allowed(r)
    lines = notes(r)
    assert len(lines) == 1 and lines[0].split("plumb: ", 1)[1].startswith("cannot load ")
    if launcher == "sh":
        assert r.stderr.strip() == lines[0]
    # the guards need no audit: still on
    refused(write_tool(launcher, tmp_path, proj, "app/globals.css", "x", env=env))


def test_broken_project_scripts_do_not_matter(launcher, tmp_path, proj):
    write(proj / SKILL_REL / "scripts/audit.py", "def broken(:\n")
    assert "#ff0000" in refused(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW))


def test_missing_design_system_fails_open(launcher, tmp_path, proj):
    set_plumb(proj, skill=".claude/skills/gone-design-system")
    r = edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW)
    allowed(r)
    assert len(notes(r)) <= 1


def test_broken_tokens_file_fails_open(launcher, tmp_path, proj):
    write(proj / SKILL_REL / "assets/tokens/demo.tokens.json", "{ not json")
    r = edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW)
    allowed(r)
    assert len(notes(r)) <= 1


# ---------------------------------------------------------------- timing (measured through the launcher)


def _best_hook(launcher, proj, tmp_path, script: str, stdin: str, check, limit: float, n: int = 12) -> float:
    """The fastest of at least 5 timed runs of the hook (up to n while none is under the limit). Only the hook's own
    process is timed: the payload and the environment are built once, before; one untimed warm-up run fills the disk
    cache and the .pyc files; each result is checked after its timing. A loaded machine (other test processes, CI
    neighbours) slows single runs down, while the hook's own cost shows in the fastest one."""
    env = hook_env(tmp_path)
    check(run_hook(launcher, script, stdin, proj, env))  # warm-up, not timed
    times = []
    for i in range(n):
        t = time.perf_counter()
        r = run_hook(launcher, script, stdin, proj, env)
        times.append(time.perf_counter() - t)
        check(r)
        if len(times) >= 5 and min(times) < limit:
            break
    assert len(times) >= 5
    return min(times)


def test_non_ui_edit_is_fast(launcher, tmp_path, proj):
    limit = 0.6 if CI or launcher == "powershell" else 0.15
    stdin = payload("claude", "edit", CWD=str(proj), FILE=str(proj / "README.md"), OLD="Notes.", NEW="More notes.")
    took = _best_hook(launcher, proj, tmp_path, "pre_edit.py", stdin, allowed, limit)
    assert took < limit, f"non-UI edit took {took * 1000:.0f} ms (limit {limit * 1000:.0f} ms)"


def test_ui_edit_is_fast(launcher, tmp_path, proj):
    limit = 3.0 if CI or launcher == "powershell" else 1.0
    stdin = payload("claude", "edit", CWD=str(proj), FILE=str(proj / "app/page.tsx"), OLD=H1, NEW=H1_RAW)
    took = _best_hook(launcher, proj, tmp_path, "pre_edit.py", stdin, refused, limit)
    assert took < limit, f"UI edit took {took * 1000:.0f} ms (limit {limit * 1000:.0f} ms)"


# ---------------------------------------------------------------- end-of-turn check


def _start(launcher, tmp_path, proj, session="sess-1"):
    r = session_start(launcher, tmp_path, proj, session=session)
    assert r.returncode == 0, r.stderr


def _block(r) -> str:
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["decision"] == "block"
    return out["reason"]


def _report(r) -> str:
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "decision" not in out
    return out["systemMessage"]


@pytest.fixture(params=["mtime", pytest.param("git", marks=needs_git)])
def mode(request, proj) -> str:
    if request.param == "git":
        git_init(proj)
    return request.param


def test_stop_without_ui_changes_is_silent(launcher, tmp_path, proj, mode):
    _start(launcher, tmp_path, proj)
    write(proj / "README.md", "# Demo\n\nChanged notes.\n")
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_stop_blocks_once_on_a_new_error(launcher, tmp_path, proj, mode):
    write(proj / "components/legacy.tsx", f'export const Legacy = () => <div className="bg-[#123456]">x</div>;\n')
    if mode == "git":
        git(proj, "add", "-A")
        git(proj, "commit", "-qm", "legacy")
    _start(launcher, tmp_path, proj)
    write(proj / "components/legacy.tsx", f'export const Legacy = () => <div className="bg-[#123456]"><b {RAW}>x</b></div>;\n')
    reason = _block(stop(launcher, tmp_path, proj))
    assert reason.startswith("Plumb end-of-turn check: ")
    assert "error: components/legacy.tsx line 1: " in reason and "#ff0000" in reason
    assert "#123456" not in reason  # there before the session: not new
    actionable(reason)
    assert reason.endswith("If the user asked you not to fix these now, say so and stop.")
    # Claude continued because of the block, or a later turn with the same error: never blocked again, and the same
    # summary is not repeated
    for active in (True, False):
        r = stop(launcher, tmp_path, proj, active=active)
        assert r.returncode == 0 and r.stdout == "", r.stdout


def test_stop_summary_is_printed_again_only_when_the_findings_change(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    two = 'export const V = () => <p className="bg-[#00ff00]">v</p>;\n'
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n" + two)
    _block(stop(launcher, tmp_path, proj))
    assert stop(launcher, tmp_path, proj).stdout == ""
    write(proj / "components/widget.tsx", "export const W = () => <p>w</p>;\n" + two)
    msg = _report(stop(launcher, tmp_path, proj))  # one fixed, one left: a new summary, no new block
    assert "#00ff00" in msg and "#ff0000" not in msg
    assert stop(launcher, tmp_path, proj).stdout == ""
    write(proj / "components/widget.tsx", "export const W = () => <p className=\"bg-primary\">w</p>;\n")
    assert stop(launcher, tmp_path, proj).stdout.strip() == "Plumb: 1 UI file checked, consistent"  # fixed: said once
    assert stop(launcher, tmp_path, proj).stdout == ""


def test_stop_hook_active_only_reports(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    msg = _report(stop(launcher, tmp_path, proj, active=True))
    assert "#ff0000" in msg


def test_stop_clean_run_prints_one_line(launcher, tmp_path, proj, mode):
    _start(launcher, tmp_path, proj)
    write(proj / "components/widget.tsx", "export const W = () => <p className=\"bg-primary\">w</p>;\n")
    write(proj / "components/other.tsx", "export const O = () => <p>o</p>;\n")
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and r.stdout.strip() == "Plumb: 2 UI files checked, consistent"


def test_stop_blocks_once_on_a_prototype_sync_miss(launcher, tmp_path, proj, mode):
    _start(launcher, tmp_path, proj)
    page = proj / "app/page.tsx"
    write(page, read(page).replace("No tables booked yet", "Nothing booked yet"))
    reason = _block(stop(launcher, tmp_path, proj))
    assert f"error: {SCREENS}/home.html line " in reason
    assert "update prototype screen home: states ready, loading, empty" in reason
    assert "--approve home" in reason
    ask = next(ln for ln in reason.splitlines() if "--approve home" in ln)
    assert ask.startswith("ask the user: ") and "Only after their yes to that screen" in ask  # never a bare --approve
    assert stop(launcher, tmp_path, proj, active=True).stdout == ""  # blocked once; the same summary is not repeated


def test_stop_no_sync_miss_when_the_screen_changed_too_but_asks_for_approval(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    page = proj / "app/page.tsx"
    write(page, read(page).replace("No tables booked yet", "Nothing booked yet"))
    screen = proj / SCREENS / "home.html"
    write(screen, read(screen).replace("No tables booked yet", "Nothing booked yet"))
    reason = _block(stop(launcher, tmp_path, proj))
    assert "update prototype screen" not in reason
    assert "screen home" in reason and "not approved" in reason and "--approve home" in reason


def test_stop_no_sync_miss_after_approving_the_new_baseline(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    page = proj / "app/page.tsx"
    write(page, read(page).replace("No tables booked yet", "Nothing booked yet"))
    assert run_script(proj, "build-prototype.py", "--approve", "home").returncode == 0
    r = stop(launcher, tmp_path, proj)
    assert r.stdout.strip() == "Plumb: 1 UI file checked, consistent", r.stdout


def test_stop_asks_again_when_only_a_shared_file_changed(launcher, tmp_path, proj, mode):
    """An edit to <screens>/_shared/*.css or *.js reaches every screen: their approvals are stale, so the end-of-turn
    check asks for them again even though no screen file and no UI file changed."""
    _start(launcher, tmp_path, proj)
    write(proj / SCREENS / "_shared/base.css", "[data-screen] h2 { letter-spacing: 0.01em; }\n")
    reason = _block(stop(launcher, tmp_path, proj))
    assert "screen home" in reason and "not approved" in reason and "--approve home" in reason
    assert "update prototype screen" not in reason


def test_stop_no_drift_when_a_shared_file_mirrors_the_code_change(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    page = proj / "app/page.tsx"
    write(page, read(page).replace("No tables booked yet", "Nothing booked yet"))
    write(proj / SCREENS / "_shared/copy.js", 'screen.setAttribute("data-copy", "Nothing booked yet");\n')
    reason = _block(stop(launcher, tmp_path, proj))
    assert "update prototype screen" not in reason  # the prototype changed too, through the shared file
    assert "screen home" in reason and "not approved" in reason and "--approve home" in reason
    for sid in ("home", "booking", "menü"):  # the shared file reaches every built screen: each needs its own yes
        assert f"--approve {sid}" in reason, sid
    for sid in ("home", "booking", "menü"):
        assert run_script(proj, "build-prototype.py", "--approve", sid).returncode == 0
    r = stop(launcher, tmp_path, proj)
    assert r.stdout.strip() == "Plumb: 1 UI file checked, consistent", r.stdout


def test_stop_ignores_other_files_in_the_shared_folder(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    write(proj / SCREENS / "_shared/notes.md", "only .css and .js are shared files\n")
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and "decision" not in r.stdout, r.stdout


def test_stop_reports_a_new_route_without_a_prototype(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    write(proj / "app/billing/page.tsx", BILLING)
    reason = _block(stop(launcher, tmp_path, proj))
    assert "route /billing" in reason and "/plumb:prototype billing" in reason


def test_stop_stands_down_while_a_setup_is_in_progress(launcher, tmp_path, proj):
    """init, create and extract write <root>/.plumb-tmp/setup-in-progress while they run: the half-done state is
    expected, so the end-of-turn check is silent; once the setup ends (the folder is removed), the changes are checked
    against the session's snapshot. Other scratch files in .plumb-tmp/ never turn the check off."""
    _start(launcher, tmp_path, proj)
    write(proj / ".plumb-tmp/answers.json", "{}\n")
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    reason = _block(stop(launcher, tmp_path, proj))  # scratch only: the check runs
    assert "components/widget.tsx" in reason
    write(proj / ".plumb-tmp/setup-in-progress", "create\n")
    write(proj / "components/panel.tsx", f"export const P = () => <p {RAW}>p</p>;\n")
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    assert ".plumb-tmp/setup-in-progress is in the project, so the end-of-turn check stands down" in context(
        session_start(launcher, tmp_path, proj, session="sess-2"))
    shutil.rmtree(proj / ".plumb-tmp")
    reason = _block(stop(launcher, tmp_path, proj))
    assert "components/panel.tsx" in reason


def test_a_setup_marker_older_than_six_hours_is_stale(launcher, tmp_path, proj):
    """Review M8: a marker left by a setup that never finished must not keep the end-of-turn check off for good."""
    _start(launcher, tmp_path, proj)
    marker = proj / ".plumb-tmp/setup-in-progress"
    write(marker, "create\n")
    old = time.time() - 7 * 3600
    os.utime(marker, (old, old))
    write(proj / "components/panel.tsx", f"export const P = () => <p {RAW}>p</p>;\n")
    reason = _block(stop(launcher, tmp_path, proj))  # stale: the check runs again
    assert "components/panel.tsx" in reason
    text = context(session_start(launcher, tmp_path, proj, session="sess-3"))
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(old))
    assert (f"a setup marker from {stamp} is stale — finish /plumb:init or remove .plumb-tmp/" in text), text
    assert "stands down" not in text


def test_a_rewritten_setup_marker_is_fresh_again(launcher, tmp_path, proj):
    """Re-review N2: init, create and extract rewrite the marker at every checkpoint (and on resume), so a long setup
    keeps the stand-down; only an abandoned one goes stale."""
    _start(launcher, tmp_path, proj)
    marker = proj / ".plumb-tmp/setup-in-progress"
    write(marker, "create 2026-10-13\n")
    old = time.time() - 7 * 3600
    os.utime(marker, (old, old))
    write(proj / "components/panel.tsx", f"export const P = () => <p {RAW}>p</p>;\n")
    _block(stop(launcher, tmp_path, proj))  # stale
    write(marker, "create 2026-10-13 checkpoint 9\n")  # the next checkpoint rewrites it
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    assert "stands down" in context(session_start(launcher, tmp_path, proj, session="sess-4"))


def test_session_start_notes_a_routes_entry_without_a_kind(launcher, tmp_path, proj):
    write(proj / "PLUMB.md", read(proj / "PLUMB.md").replace("Routes: app (next-app)", "Routes: app, web/app (next-app)"))
    text = context(session_start(launcher, tmp_path, proj))
    assert ("note: Routes: app has no kind — use one of next-app, next-pages, nuxt, sveltekit, angular, router"
            in text)  # the shared parser's own words (_plumb.parse_routes)
    assert "web/app" not in text
    allowed(write_tool(launcher, tmp_path, proj, "app/billing/page.tsx", BILLING))  # fails open for that entry


@pytest.mark.parametrize("edits", [
    [("Routes: app (next-app)", "Routes: none")],
    [("Routes: app (next-app)\n", ""), ("Platforms: web, ios, android", "Platforms: ios, android")],
    [("Routes: app (next-app)\n", ""), ("Prototype sync: on", "Prototype sync: off")],
], ids=["routes-none", "mobile-only", "sync-off"])
def test_session_start_does_not_nag_where_no_route_check_runs(launcher, tmp_path, proj, edits):
    """Review M2: `Routes: none`, a mobile-only project and Prototype sync off run no route check, so no nagging."""
    text = read(proj / "PLUMB.md")
    for old, new in edits:
        assert old in text
        text = text.replace(old, new)
    write(proj / "PLUMB.md", text)
    out = context(session_start(launcher, tmp_path, proj))
    assert "Routes not recorded" not in out and "Routes:" not in out, out


def test_session_start_reads_a_kind_after_wide_spacing_and_brace_globs(launcher, tmp_path, proj):
    """Review M4: two spaces before the kind keep it; a brace glob's comma does not split the entry."""
    write(proj / "PLUMB.md", read(proj / "PLUMB.md").replace(
        "Routes: app (next-app)", "Routes: app  (next-app), src/**/*.{routes,router}.ts (router)"))
    out = context(session_start(launcher, tmp_path, proj))
    assert "Routes" not in out, out


def test_session_start_route_kinds_are_the_cores():
    spec = importlib.util.spec_from_file_location("plumb_core_kinds", PLUGIN / "assets/skill/scripts/_plumb.py")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    spec = importlib.util.spec_from_file_location("plumb_session_kinds", PLUGIN / "hooks/session_start.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    assert hook.ROUTE_KINDS == core.ROUTE_KINDS


def test_parse_routes_keeps_brace_globs_and_a_kind_after_any_spacing(tmp_path, H):
    spec = importlib.util.spec_from_file_location("plumb_core_m4", PLUGIN / "assets/skill/scripts/_plumb.py")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    assert core.parse_routes("src/**/*.{routes,router}.ts (router)") == ([("src/**/*.{routes,router}.ts", "router")], [])
    rx = core.glob_rx("src/**/*.{routes,router}.ts")  # re-review N1: braces match, as in a shell
    assert rx.match("src/router/a.routes.ts") and rx.match("src/b.router.ts") and not rx.match("src/a.ts")
    assert core.glob_rx("*.{tsx,css}").match("x.css") and core.glob_rx("{app,pages}/**").match("pages/a/b.tsx")
    assert core.split_globs("frontend/src/**, src/{a,b}/** · *.{tsx,css} *.ts") == [
        "frontend/src/**", "src/{a,b}/**", "*.{tsx,css}", "*.ts"]
    assert core.parse_routes("app\t(next-app),  pages   (nuxt)") == ([("app", "next-app"), ("pages", "nuxt")], [])
    write(tmp_path / "PLUMB.md", "Routes: app  (next-app)\nThemes: light-and-dark          (a note)\n")
    keys = core.read_plumb_md(tmp_path / "PLUMB.md")
    assert keys["Routes"] == "app  (next-app)" and keys["Themes"] == "light-and-dark"
    hook_keys = H.plumb_md_keys(read(tmp_path / "PLUMB.md"))
    assert hook_keys["Routes"] == "app  (next-app)" and hook_keys["Themes"] == "light-and-dark"


def test_stop_end_of_turn_check_off_is_silent(launcher, tmp_path, proj):
    set_plumb(proj, stop="off")
    _start(launcher, tmp_path, proj)
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and r.stdout == ""


def test_stop_without_a_snapshot_takes_one_and_stays_silent(launcher, tmp_path, proj):
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    r = stop(launcher, tmp_path, proj, session="late")
    assert r.returncode == 0 and r.stdout == ""
    assert [p.name.endswith("-late.json") for p in snapshots(tmp_path)] == [True]


@pytest.mark.parametrize("stdin", ["", "garbage", "[]"])
def test_stop_garbage_input_is_silent(launcher, tmp_path, proj, stdin):
    r = run_hook(launcher, "stop_check.py", stdin, proj, hook_env(tmp_path))
    assert r.returncode == 0 and r.stdout == ""


def test_stop_fails_open_with_a_broken_plugin_audit(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    plugin = plugin_copy(tmp_path)
    write(plugin / "assets/skill/scripts/audit.py", "raise RuntimeError('x')\n")
    r = stop(launcher, tmp_path, proj, env={"CLAUDE_PLUGIN_ROOT": str(plugin)})
    assert r.returncode == 0 and r.stdout == ""
    assert len(notes(r)) <= 1


def test_stop_without_plumb_md_is_silent(launcher, tmp_path):
    empty = tmp_path / "plain"
    empty.mkdir()
    r = stop(launcher, tmp_path, empty)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


# ---------------------------------------------------------------- hooks.json


def test_hooks_json_runs_every_hook_through_the_launchers():
    hooks = json.loads(read(HOOKS / "hooks.json"))["hooks"]
    assert set(hooks) == {"SessionStart", "PreToolUse", "Stop"}
    assert hooks["PreToolUse"][0]["matcher"] == "Edit|Write|MultiEdit|Bash|PowerShell"
    prefix = 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" '
    for event, script in (("SessionStart", "session_start.py"), ("PreToolUse", "pre_edit.py"), ("Stop", "stop_check.py")):
        (h,) = [h for entry in hooks[event] for h in entry["hooks"]]
        assert h["type"] == "command" and h["command"] == prefix + script
        assert f"& $s {script}; exit $LASTEXITCODE" in h["powershell"]
        assert (HOOKS / script).is_file()


# ---------------------------------------------------------------- in-process: _hooklib parsers


def _targets(H, command: str, cwd: str):
    """The files a shell command writes, as the guard's reader sees them."""
    return list(H.shell_effects(command, cwd).writes)


def _removals(H, command: str, cwd: str):
    return list(H.shell_effects(command, cwd).removals)


@pytest.fixture(scope="module")
def H():
    spec = importlib.util.spec_from_file_location("plumb_hooklib_test", HOOKS / "_hooklib.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plumb_hooklib_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_apply_patch_updates_with_context_and_header(H):
    before = "a\nb\nfunction x() {\n  one\n}\nfunction y() {\n  one\n}\n"
    text = ("*** Begin Patch\n*** Update File: f.tsx\n@@ function y() {\n-  one\n+  two\n*** End Patch\n")
    (change,) = H.parse_patch(text)
    assert change.path == "f.tsx" and change.kind == "update"
    assert change.after(before) == "a\nb\nfunction x() {\n  one\n}\nfunction y() {\n  two\n}\n"


def test_apply_patch_tolerates_trailing_space_and_crlf(H):
    before = "x = 1   \r\ny = 2\r\n"
    (change,) = H.parse_patch("*** Begin Patch\n*** Update File: f.ts\n@@\n x = 1\n-y = 2\n+y = 3\n*** End Patch\n")
    assert change.after(before) == "x = 1   \ny = 3\n"


def test_apply_patch_add_delete_move_and_failure(H):
    changes = H.parse_patch(patch("*** Add File: n.tsx\n+one\n+two\n", "*** Delete File: d.tsx\n",
                                  "*** Update File: m.tsx\n*** Move to: moved.tsx\n@@\n-old\n+new\n"))
    assert [(c.kind, c.path) for c in changes] == [("add", "n.tsx"), ("delete", "d.tsx"), ("update", "m.tsx"),
                                                    ("move", "moved.tsx")]
    assert changes[0].after(None) == "one\ntwo\n"
    assert changes[2].after("nothing matches\n") is None
    assert changes[2].added() == "new" and changes[2].removed() == "old"


@pytest.mark.parametrize("command,targets", [
    ("echo x > a.css", ["a.css"]),
    ("echo x 2>&1 > /dev/null", []),
    ("cat a | tee -a b.css c.css", ["b.css", "c.css"]),
    ("sed -i '' 's/a/b/' x.css y.css", ["x.css", "y.css"]),
    ("cp -r src/a.css 'dest dir/b.css'", ["dest dir/b.css"]),
    ("mv a b", ["b"]),
    ("cd docs && echo x > p.html", ["docs/p.html"]),
    ("Set-Content -Path a.css -Value x", ["a.css"]),
    ("'x' | Out-File -FilePath b.css", ["b.css"]),
    ("Copy-Item a.css -Destination b.css", ["b.css"]),
    ("Copy-Item a.css b.css", ["b.css"]),
    ("cat a.css", []),
    ("git checkout -- a.css", []),
])
def test_shell_write_targets(H, command, targets, tmp_path):
    found = [Path(t) for t in _targets(H, command, str(tmp_path))]
    assert [str(p.relative_to(tmp_path)).replace("\\", "/") for p in found] == targets


# ---------------------------------------------------------------- audit.py --snapshot / --changed


def test_audit_changed_cli(tmp_path, proj):
    snap = tmp_path / "snap.json"
    r = run_script(proj, "audit.py", "--snapshot", str(snap))
    assert r.returncode == 0, r.stderr
    r = run_script(proj, "audit.py", "--changed", str(snap))
    assert r.returncode == 0 and "no UI files changed" in r.stdout, r.stdout + r.stderr
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    r = run_script(proj, "audit.py", "--changed", str(snap), "--json")
    assert r.returncode == 1, r.stderr
    out = json.loads(r.stdout)
    assert out["mode"] == "changed" and out["checked"] == 1
    assert [f["file"] for f in out["findings"] if f["severity"] == "error"] == ["components/widget.tsx"]


def test_audit_changed_counts_a_shared_file_as_a_change_to_every_screen(tmp_path, proj):
    """audit.py --changed, like the stop hook: an edit only to <screens>/_shared/ stales every built screen's approval
    (screen-unapproved); a code change mirrored in a shared file is not screen-drift."""
    snap = tmp_path / "snap.json"
    assert run_script(proj, "audit.py", "--snapshot", str(snap)).returncode == 0
    write(proj / SCREENS / "_shared/base.css", "[data-screen] h2 { letter-spacing: 0.01em; }\n")
    r = run_script(proj, "audit.py", "--changed", str(snap), "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    rules = [f["rule"] for f in json.loads(r.stdout)["findings"]]
    assert "screen-unapproved" in rules and "screen-drift" not in rules, rules
    page = proj / "app/page.tsx"
    write(page, read(page).replace("No tables booked yet", "Nothing booked yet"))
    r = run_script(proj, "audit.py", "--changed", str(snap), "--json")
    rules = [f["rule"] for f in json.loads(r.stdout)["findings"]]
    assert "screen-drift" not in rules and "screen-unapproved" in rules, rules


def test_audit_changed_bad_snapshot_exits_2(tmp_path, proj):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    for target in (bad, tmp_path / "missing.json"):
        r = run_script(proj, "audit.py", "--changed", str(target))
        assert r.returncode == 2 and r.stderr.startswith("error: ") and "\nfix: " in r.stderr, r.stderr
    r = run_script(proj, "audit.py", "--changed", str(bad), "--quick", "app/page.tsx")
    assert r.returncode == 2 and "error: " in r.stderr


def test_plumb_md_parser_matches_the_audits(H, tmp_path):
    """The hooks parse PLUMB.md themselves (no import on the fast path); it must read it exactly as _plumb does."""
    spec = importlib.util.spec_from_file_location("plumb_core_hooktest", PLUGIN / "assets/skill/scripts/_plumb.py")
    core = importlib.util.module_from_spec(spec)
    sys.modules["plumb_core_hooktest"] = core
    spec.loader.exec_module(core)
    samples = [read(PLUGIN / "templates/PLUMB.md"), plumb_md(), plumb_md(role="linked", sync="off"),
               "Key: `x`\r\n```\nIn: fence\n```\n- Bullet: no\n| Table: no |\nNote: value   (a note)\nEmpty:\n"]
    for text in samples:
        path = tmp_path / "PLUMB.md"
        path.write_bytes(text.encode("utf-8"))
        assert H.plumb_md_keys(text) == core.read_plumb_md(path)


# ---------------------------------------------------------------- review hardening: git, temp folder, shell, paths


def _git_project(launcher, tmp_path, proj):
    git_init(proj)
    _start(launcher, tmp_path, proj)
    (snap,) = snapshots(tmp_path)
    return snap


@needs_git
def test_snapshot_head_cannot_inject_git_options(launcher, tmp_path, proj):
    snap = _git_project(launcher, tmp_path, proj)
    pwned = tmp_path / "pwned.txt"
    data = json.loads(read(snap))
    data["head"] = f"--output={pwned}"
    write(snap, json.dumps(data))
    write(proj / "README.md", "# Demo\n\nCommitted.\n")
    git(proj, "commit", "-qam", "next")
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and r.stdout == "", r.stdout
    assert len(notes(r)) <= 1
    assert not pwned.exists()
    cli = run_script(proj, "audit.py", "--changed", str(snap))
    assert cli.returncode == 2 and cli.stderr.startswith("error: ") and "\nfix: " in cli.stderr
    assert not pwned.exists()


@needs_git
def test_git_never_runs_the_repositorys_configured_commands(launcher, tmp_path, proj):
    git_init(proj)
    mark = tmp_path / "git-ran"
    mark.mkdir()
    cmd = "touch '" + str(mark).replace("'", "") + "/{}'; cat"
    for key, name in (("core.fsmonitor", "fsmonitor"), ("filter.plumbx.clean", "clean"),
                      ("filter.plumbx.process", "process"), ("filter.plumbx.smudge", "smudge"),
                      ("diff.plumbx.textconv", "textconv"), ("diff.external", "external"),
                      ("core.pager", "pager"), ("core.hooksPath", "hooks-path")):
        git(proj, "config", key, cmd.format(name))
    safe = ("-c", "core.fsmonitor=false", "-c", "filter.plumbx.clean=cat", "-c", "filter.plumbx.process=",
            "-c", "filter.plumbx.smudge=cat", "-c", f"core.hooksPath={os.devnull}")  # the test's own git calls
    write(proj / ".gitattributes", "*.tsx filter=plumbx diff=plumbx\n*.html filter=plumbx diff=plumbx\n")
    git(proj, *safe, "add", ".gitattributes")
    git(proj, *safe, "commit", "-qm", "attrs")
    _start(launcher, tmp_path, proj)
    page = proj / "app/page.tsx"
    write(page, read(page).replace("No tables booked yet", "Nothing booked yet"))
    write(proj / "README.md", "# Demo\n\nCommitted.\n")
    git(proj, *safe, "commit", "-qam", "next")
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    r = stop(launcher, tmp_path, proj)
    assert "#ff0000" in _block(r)
    assert sorted(p.name for p in mark.iterdir()) == []


def test_temp_folder_that_is_a_symlink_is_never_used(launcher, tmp_path, proj):
    victim = tmp_path / "victim"
    victim.mkdir()
    keep = victim / "important.json"
    keep.write_text("{}", encoding="utf-8")
    old = time.time() - 9 * 24 * 3600
    os.utime(str(keep), (old, old))
    folder = plumb_tmp(tmp_path)
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(str(victim), str(folder), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("requires POSIX: symlinks (or Windows with the right to create them)")
    r = session_start(launcher, tmp_path, proj)
    assert context(r).startswith("Plumb: demo-design-system 1.0.0 · ")
    assert keep.exists() and sorted(p.name for p in victim.iterdir()) == ["important.json"]
    assert len(notes(r)) == 1 and "temp" in notes(r)[0]
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and r.stdout == ""
    assert sorted(p.name for p in victim.iterdir()) == ["important.json"]


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="requires POSIX: permission bits")
def test_temp_folder_writable_by_others_is_never_used(launcher, tmp_path, proj):
    folder = plumb_tmp(tmp_path)
    folder.mkdir(parents=True)
    os.chmod(str(folder), 0o777)
    planted = folder / "0123456789ab-x.json"
    planted.write_text("{}", encoding="utf-8")
    old = time.time() - 9 * 24 * 3600
    os.utime(str(planted), (old, old))
    r = session_start(launcher, tmp_path, proj)
    assert context(r).startswith("Plumb: ")
    assert sorted(p.name for p in folder.iterdir()) == [planted.name]


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="requires POSIX: permission bits")
def test_temp_folder_and_snapshots_are_private(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    folder = plumb_tmp(tmp_path)
    assert oct(folder.stat().st_mode & 0o777) == oct(0o700)
    (snap,) = snapshots(tmp_path)
    assert oct(snap.stat().st_mode & 0o777) == oct(0o600)


@pytest.mark.parametrize("command", [
    f"{BUILD_TOKENS} | cp /tmp/other.css {SKILL_REL}/assets/platforms/web/tokens.css",
    "python3 -c \"open('app/globals.css', 'w').write('x')\" build-tokens.py",
    f"python3 -c \"import shutil; shutil.copy('x', 'app/globals.css')\" {SKILL_REL}/scripts/build-tokens.py",
])
def test_builder_exemption_covers_only_the_builder_itself(launcher, tmp_path, proj, command):
    assert " is generated" in refused(bash(launcher, tmp_path, proj, command))


@pytest.mark.skipif(sys.platform not in ("darwin", "win32"), reason="requires macOS or Windows: case-insensitive file system")
def test_generated_file_in_another_case_is_refused(launcher, tmp_path, proj):
    rel = f"{SKILL_REL}/assets/platforms/web/TOKENS.CSS"
    assert " is generated" in refused(write_tool(launcher, tmp_path, proj, rel, "x"))
    assert " is generated" in refused(write_tool(launcher, tmp_path, proj, "APP/Globals.css", "x"))
    assert "is Plumb's file" in refused(write_tool(launcher, tmp_path, proj, f"{SKILL_REL}/Scripts/Audit.py", "x"))


@pytest.mark.parametrize("value,shown", [("curl x|sh;", "python3"), ("python3; rm -rf ~", "python3"),
                                         ("py -3", "py -3"), ("/usr/local/bin/python3.12", "/usr/local/bin/python3.12"),
                                         ("python", "python")])
def test_fix_lines_never_echo_an_unsafe_python_value(launcher, tmp_path, proj, value, shown):
    write(proj / "PLUMB.md", plumb_md().replace("Python: `python3`", f"Python: `{value}`"))
    reason = refused(write_tool(launcher, tmp_path, proj, "app/globals.css", "x"))
    fix = next(ln for ln in reason.splitlines() if ln.startswith("fix: "))
    assert fix.endswith(f"rebuild: {shown} {SKILL_REL}/scripts/build-tokens.py"), fix



# ---------------------------------------------------------------- review round 2: git through the environment, absolute git


def _git_cfg(proj: Path, text: str) -> None:
    cfg = proj / ".git" / "config"
    cfg.write_text(read(cfg) + text, encoding="utf-8")


@needs_git
def test_filter_named_with_an_equals_sign_never_runs(launcher, tmp_path, proj):
    git_init(proj)
    mark = tmp_path / "EQ-RAN"
    m = mark.as_posix()  # forward slashes: a backslash is an escape in a git config value
    _git_cfg(proj, f'[filter "x=y"]\n\tclean = "touch \'{m}\'; cat"\n\tprocess = "touch \'{m}\'"\n')
    write(proj / ".gitattributes", "*.tsx filter=x=y\n")
    safe = ("-c", "core.fsmonitor=false")  # the filter is emptied through env (a -c key cannot hold "=" on every git)
    env = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "filter.x=y.clean", "GIT_CONFIG_VALUE_0": "cat",
           "GIT_CONFIG_KEY_1": "filter.x=y.process", "GIT_CONFIG_VALUE_1": ""}
    import subprocess as sp
    for args in (["add", ".gitattributes"], ["commit", "-qm", "attrs"]):
        sp.run(["git", *safe, *args], cwd=str(proj), check=True, capture_output=True,
               env={**os.environ, **env, "GIT_CEILING_DIRECTORIES": str(proj.parent)})
    write(proj / "components/eq.tsx", "export const a = 1;\n")
    for args in (["add", "components/eq.tsx"], ["commit", "-qm", "eq"]):
        sp.run(["git", *safe, *args], cwd=str(proj), check=True, capture_output=True,
               env={**os.environ, **env, "GIT_CEILING_DIRECTORIES": str(proj.parent)})
    if mark.exists():
        mark.unlink()
    _start(launcher, tmp_path, proj)
    eq = proj / "components/eq.tsx"
    write(eq, "export const b = 2;\n")  # same size: git must read the content, through the clean filter
    st = eq.stat()
    os.utime(str(eq), (st.st_atime, st.st_mtime + 60))
    stop(launcher, tmp_path, proj)
    assert not mark.exists()
    os.utime(str(eq), (st.st_atime, st.st_mtime + 120))
    sp.run(["git", "status", "--porcelain"], cwd=str(proj), capture_output=True,
           env={**os.environ, "GIT_CEILING_DIRECTORIES": str(proj.parent)})
    assert mark.exists()  # control: a plain git status does run it


@needs_git
def test_lazy_fetch_never_runs_the_promisor_remotes_command(launcher, tmp_path, proj):
    """A partial clone whose blob is missing: reading the old text must not fetch (uploadpack is a command)."""
    import subprocess as sp
    page = proj / "app/page.tsx"
    write(page, read(page).replace("<main>", '<main className="bg-[#abcdef]">'))  # an error from before the session
    git_init(proj)
    git(proj, "config", "uploadpack.allowFilter", "true")
    victim = tmp_path / "victim" / "demo"
    victim.parent.mkdir()
    genv = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    genv.update({"GIT_CEILING_DIRECTORIES": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1"})
    sp.run(["git", "clone", "-q", "--no-local", proj.as_uri(), str(victim)], check=True, capture_output=True, env=genv)
    def unlink(path: Path) -> None:  # git writes its objects read-only; Windows refuses to delete those
        os.chmod(str(path), 0o644)
        path.unlink()

    for pack in list((victim / ".git/objects/pack").glob("*.pack")):
        moved = tmp_path / pack.name
        os.chmod(str(pack), 0o644)
        pack.rename(moved)
        for q in (victim / ".git/objects/pack").glob("*"):
            unlink(q)
        with open(moved, "rb") as fh:
            sp.run(["git", "unpack-objects", "-q"], stdin=fh, cwd=str(victim), check=True, env=genv)
    mark = tmp_path / "LAZY-RAN"
    for key, value in (("core.repositoryformatversion", "1"), ("extensions.partialClone", "origin"),
                       ("remote.origin.promisor", "true"),
                       ("remote.origin.uploadpack", f"touch '{mark}'; git-upload-pack")):
        git(victim, "config", key, value)
    _start(launcher, tmp_path, victim)
    oid = sp.run(["git", "rev-parse", "HEAD:app/page.tsx"], cwd=str(victim), env=genv, capture_output=True,
                 text=True, encoding="utf-8").stdout.strip()
    unlink(victim / ".git/objects" / oid[:2] / oid[2:])
    page = victim / "app/page.tsx"
    write(page, read(page) + "\nexport const c = 'x';\n")
    r = stop(launcher, tmp_path, victim)
    assert r.returncode == 0
    assert not mark.exists()
    assert "#abcdef" not in r.stdout  # the old text is unknown: nothing in the file counts as new


def _shim(tmp_path: Path, name: str, body: str) -> Path:
    import shutil as sh
    real = sh.which("git")
    folder = tmp_path / name
    folder.mkdir()
    script = folder / "git"
    script.write_bytes(("#!/bin/sh\n" + body.replace("REAL", str(real))).encode("utf-8"))
    script.chmod(0o755)
    return folder


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="requires POSIX: sh shims for git")


def _legacy_project(launcher, tmp_path, proj, shim: Path):
    write(proj / "app/legacy.tsx", "export const legacy = '#abcdef';\n")
    write(proj / "components/legacy.tsx", 'export const L = () => <p className="bg-[#abcdef]">x</p>;\n')
    git_init(proj)
    env = {"PATH": str(shim) + os.pathsep + os.environ.get("PATH", "")}
    _start(launcher, tmp_path, proj)
    f = proj / "components/legacy.tsx"
    write(f, read(f) + "export const ok = 1;\n")
    return stop(launcher, tmp_path, proj, env=env)


@needs_git
@posix_only
def test_old_git_without_end_of_options_gives_no_false_block(launcher, tmp_path, proj):
    shim = _shim(tmp_path, "oldgit", 'for a in "$@"; do [ "$a" = "--end-of-options" ] && exit 129; done\n'
                                      'exec REAL "$@"\n')
    r = _legacy_project(launcher, tmp_path, proj, shim)
    assert r.returncode == 0 and r.stdout.strip() == "Plumb: 1 UI file checked, consistent", r.stdout


@needs_git
@posix_only
def test_old_text_that_cannot_be_read_counts_as_not_new(launcher, tmp_path, proj):
    shim = _shim(tmp_path, "brokengit", 'for a in "$@"; do case "$a" in cat-file|show) exit 128;; esac; done\n'
                                        'exec REAL "$@"\n')
    r = _legacy_project(launcher, tmp_path, proj, shim)
    assert r.returncode == 0 and "decision" not in r.stdout, r.stdout


@needs_git
def test_git_planted_in_the_project_is_never_run(launcher, tmp_path, proj):
    git_init(proj)
    mark = tmp_path / "PLANTED-GIT-RAN"
    for name in ("git", "git.exe", "git.cmd", "git.bat"):
        p = proj / name
        if name.endswith((".cmd", ".bat")):
            write(p, f'@echo off\r\necho ran > "{mark}"\r\n', newline="")
        else:
            p.write_bytes(f"#!/bin/sh\ntouch '{mark}'\nexit 1\n".encode("utf-8"))
            p.chmod(0o755)
    path = os.pathsep.join([".", "", str(proj), "bin", os.environ.get("PATH", "")])
    env = {"PATH": path}
    r = session_start(launcher, tmp_path, proj, env=env)
    assert context(r).startswith("Plumb: ")
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    assert "#ff0000" in _block(stop(launcher, tmp_path, proj, env=env))
    assert not mark.exists()


@pytest.mark.parametrize("command", [
    "python3 -c \"open('{d}/a b/tokens.css', 'w').write('x')\"",
    "python3 -c 'open(\"{d}/a b/tokens.css\", \"w\").write(\"x\")'",
    "echo x > \"{d}/a b/tokens.css\"",
    "echo x > '{d}/a b/tokens.css'",
])
def test_shell_paths_with_spaces_are_read_whole(H, command, tmp_path):
    found = _targets(H, command.format(d=tmp_path), str(tmp_path))
    assert os.path.join(str(tmp_path), "a b", "tokens.css") in [os.path.normpath(t) for t in found], found


def test_generated_file_under_a_folder_with_a_space_is_refused(launcher, tmp_path):
    proj = make_project(tmp_path, "With Space")
    assert " is generated" in refused(bash(launcher, tmp_path, proj,
                                           f"python3 -c \"open('{proj}/app/globals.css', 'w').write('x')\""))


# ---------------------------------------------------------------- review round 3: last minors


def _audit_module():
    spec = importlib.util.spec_from_file_location("plumb_audit", PLUGIN / "assets/skill/scripts/audit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plumb_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_windows_git_lookup_takes_only_git_exe(tmp_path, monkeypatch):
    A = _audit_module()
    scripts_only = tmp_path / "scripts-only"
    scripts_only.mkdir()
    for name in ("git.cmd", "git.bat", "git"):
        (scripts_only / name).write_text("x", encoding="utf-8")
        os.chmod(str(scripts_only / name), 0o755)
    real = tmp_path / "real"
    real.mkdir()
    (real / "git.exe").write_text("x", encoding="utf-8")
    os.chmod(str(real / "git.exe"), 0o755)
    monkeypatch.setenv("PATH", os.pathsep.join([str(scripts_only)]))
    assert A.find_executable("git", windows=True) is None
    monkeypatch.setenv("PATH", os.pathsep.join([str(scripts_only), str(real)]))
    assert A.find_executable("git", windows=True) == os.path.realpath(str(real / "git.exe"))


@pytest.mark.parametrize("command", [
    "node -e \"require('fs').writeFileSync('app/globals.css', 'x')\"",
    "node -e \"require('fs').appendFileSync('docs/design/prototype.html', 'x')\"",
    "node -e \"fs.promises.writeFile('docs/design/screens.html', 'x')\"",
    "node -e \"require('fs').createWriteStream('docs/design/specimen.html').end('x')\"",
    "node -e \"require('fs').copyFileSync('/tmp/x.css', 'app/globals.css')\"",
    "bun -e \"await Bun.write('app/globals.css', 'x')\"",
    "deno eval \"Deno.writeTextFileSync('app/globals.css', 'x')\"",
])
def test_node_bun_and_deno_writes_are_refused(launcher, tmp_path, proj, command):
    assert " is generated" in refused(bash(launcher, tmp_path, proj, command))


def test_node_reads_are_allowed(launcher, tmp_path, proj):
    allowed(bash(launcher, tmp_path, proj, "node -e \"console.log(require('fs').readFileSync('app/globals.css', 'utf8'))\""))


@needs_git
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires POSIX: FIFO")
def test_git_that_hangs_on_config_is_cut_short(launcher, tmp_path, proj):
    git_init(proj)
    fifo = tmp_path / "config-fifo"
    os.mkfifo(str(fifo))
    git(proj, "config", "include.path", str(fifo))
    t = time.perf_counter()
    r = session_start(launcher, tmp_path, proj)
    assert context(r).startswith("Plumb: ")
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    r = stop(launcher, tmp_path, proj)
    assert r.returncode == 0
    took = time.perf_counter() - t
    assert took < 12, f"session start + stop took {took:.1f} s with a git that hangs"


def test_payload_with_a_utf8_bom_is_read(H):
    """A launcher that writes the payload through a .NET StreamWriter may put a UTF-8 BOM first; it is still JSON."""
    p = H.read_payload('﻿{"tool_name": "Write", "tool_input": {"file_path": "a.css", "content": "x"}}')
    assert p is not None and p.file_path == "a.css"


# ---------------------------------------------------------------- the Plumb feedback log (~/.plumb/feedback/hooks.md)


def user_home(tmp_path: Path) -> Path:
    """The home folder hook_env gives the hooks (HOME and USERPROFILE): never the real one."""
    return tmp_path / "user-home"


def hooks_log(tmp_path: Path) -> Path:
    return user_home(tmp_path) / ".plumb" / "feedback" / "hooks.md"


def log_lines(tmp_path: Path):
    path = hooks_log(tmp_path)
    return [ln for ln in read(path).splitlines() if ln.startswith("- ")] if path.is_file() else []


def stat_mode(path: Path) -> int:
    import stat as st
    return st.S_IMODE(os.lstat(str(path)).st_mode)


def broken_audit(tmp_path: Path) -> dict:
    plugin = tmp_path / "plugin-copy"
    if not plugin.is_dir():
        plugin = plugin_copy(tmp_path)
        write(plugin / "assets/skill/scripts/audit.py", "def broken(:\n")
    return {"CLAUDE_PLUGIN_ROOT": str(plugin)}


def test_a_crash_that_fails_open_is_logged_privately_outside_the_project(launcher, tmp_path, proj):
    r = edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW, env=broken_audit(tmp_path))
    allowed(r)
    assert len(notes(r)) == 1, "the log adds nothing to what the session sees"
    text = read(hooks_log(tmp_path))
    assert text.startswith("# Plumb hook failures\n") and "Plumb's own mistakes" in text and "/plumb:feedback" in text
    (line,) = log_lines(tmp_path)
    for part in ("pre_edit.py", "crash", "Plumb 1.0.0", "event PreToolUse", "tool Edit", "path app/page.tsx",
                 "exit 0 (failed open)", "Given: cannot load the plugin's audit.py (SyntaxError",
                 "Expected: the plugin's audit.py loads and the design checks run"):
        assert part in line, (part, line)
    assert re.match(r"^- \d{4}-\d{2}-\d{2} \d{2}:\d{2} pre_edit\.py · ", line), line
    assert ("copilot-cli" if r.copilot else "claude-code") in line
    assert not list(proj.rglob("hooks.md")) and not (proj / ".plumb").exists(), "never written into the project"
    if hasattr(os, "getuid"):
        assert stat_mode(user_home(tmp_path) / ".plumb") == 0o700
        assert stat_mode(user_home(tmp_path) / ".plumb" / "feedback") == 0o700
        assert stat_mode(hooks_log(tmp_path)) == 0o600


def test_the_same_failure_is_logged_once_a_day(launcher, tmp_path, proj):
    env = broken_audit(tmp_path)
    for _ in range(2):
        allowed(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW, env=env))
    assert len(log_lines(tmp_path)) == 1
    session_start(launcher, tmp_path, proj, env={**env, "PLUMB_AUDIT_TIMEOUT": "0"})  # another hook, another line
    assert [ln.split(" ", 4)[3] for ln in log_lines(tmp_path)] == ["pre_edit.py", "session_start.py"]


@pytest.mark.parametrize("source, given", [
    ("raise RuntimeError('broken')\n", "Given: audit.py --json crashed (exit 1): RuntimeError: broken"),
    ("def broken(:\n", "Given: audit.py --json crashed (exit 1): SyntaxError"),  # no "Traceback" header
])
def test_session_start_logs_a_crashed_audit(launcher, tmp_path, proj, source, given):
    plugin = plugin_copy(tmp_path)
    write(plugin / "assets/skill/scripts/audit.py", source)
    r = session_start(launcher, tmp_path, proj, env={"CLAUDE_PLUGIN_ROOT": str(plugin)})
    assert "audit not run" in context(r)
    lines = log_lines(tmp_path)
    assert any(given in ln for ln in lines), lines
    assert all("session_start.py" in ln and "event SessionStart" in ln for ln in lines), lines


def test_the_projects_own_broken_tokens_file_is_not_logged(launcher, tmp_path, proj):
    # A PlumbError is an actionable refusal about the project's files: the project's problem, not Plumb's mistake.
    write(proj / SKILL_REL / "assets/tokens/demo.tokens.json", "{ not json")
    allowed(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW))
    assert log_lines(tmp_path) == []


def test_a_working_hook_logs_nothing(launcher, tmp_path, proj):
    refused(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW))
    context(session_start(launcher, tmp_path, proj, env={"PLUMB_AUDIT_TIMEOUT": "0"}))
    assert not (user_home(tmp_path) / ".plumb").exists()


def _symlink(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(str(target), str(link), target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("requires POSIX: symlinks (or Windows with the right to create them)")


@pytest.mark.parametrize("which", [".plumb", ".plumb/feedback"])
def test_a_symlinked_feedback_folder_is_never_used(launcher, tmp_path, proj, which):
    victim = tmp_path / "victim"
    victim.mkdir()
    if which == ".plumb/feedback":
        (user_home(tmp_path) / ".plumb").mkdir(parents=True)
        os.chmod(str(user_home(tmp_path) / ".plumb"), 0o700)
    _symlink(victim, user_home(tmp_path) / which)
    r = edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW, env=broken_audit(tmp_path))
    allowed(r)
    assert len(notes(r)) == 1
    assert list(victim.iterdir()) == [], "nothing written through the symlink"


def test_a_symlinked_hooks_md_is_never_followed(launcher, tmp_path, proj):
    folder = user_home(tmp_path) / ".plumb" / "feedback"
    folder.mkdir(parents=True)
    os.chmod(str(folder.parent), 0o700)
    os.chmod(str(folder), 0o700)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep\n", encoding="utf-8")
    _symlink(victim, folder / "hooks.md")
    allowed(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW, env=broken_audit(tmp_path)))
    assert read(victim) == "keep\n"


def _make_open_folders(tmp_path: Path, mode: int) -> Path:
    """~/.plumb/feedback as the agent's write tool makes it under a umask of 002 (0775), or wider: the user's own."""
    folder = user_home(tmp_path) / ".plumb" / "feedback"
    old = os.umask(0o002)
    try:
        folder.mkdir(parents=True)
    finally:
        os.umask(old)
    os.chmod(str(folder.parent), mode)
    os.chmod(str(folder), mode)
    return folder


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="requires POSIX: permission bits")
@pytest.mark.parametrize("mode", [0o775, 0o777])
def test_your_own_open_feedback_folder_is_made_private_then_used(launcher, tmp_path, proj, mode):
    # Review I1: under umask 002 the agent's first record leaves 0775 folders; the hooks must still log (privately).
    folder = _make_open_folders(tmp_path, mode)
    assert stat_mode(folder) == mode
    allowed(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW, env=broken_audit(tmp_path)))
    assert stat_mode(folder.parent) == 0o700 and stat_mode(folder) == 0o700
    assert len(log_lines(tmp_path)) == 1 and stat_mode(hooks_log(tmp_path)) == 0o600


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="requires POSIX: permission bits")
def test_session_start_makes_an_existing_feedback_folder_private_and_creates_none(launcher, tmp_path, proj):
    folder = _make_open_folders(tmp_path, 0o775)
    record = folder / "2026-10-13-detect-missed-structure-demo.md"
    record.write_text("# detect.py — missed structure\n", encoding="utf-8")
    context(session_start(launcher, tmp_path, proj, env={"PLUMB_AUDIT_TIMEOUT": "0"}))
    assert stat_mode(folder.parent) == 0o700 and stat_mode(folder) == 0o700
    assert sorted(p.name for p in folder.iterdir()) == [record.name], "tightened, nothing written"


def test_secrets_and_paths_in_a_crash_message_never_reach_the_log(launcher, tmp_path, proj):
    # Review I2: exception messages quote the data they choked on; hooks.md keeps the shape, not the data.
    plugin = plugin_copy(tmp_path)
    secret_path = "/home/alice/private/customers.csv" if os.sep == "/" else "C:\\Users\\alice\\private\\customers.csv"
    write(plugin / "assets/skill/scripts/audit.py",
          "raise ValueError(\"could not convert string to float: 'sk-live-SECRET1234567890abcd' in "
          + secret_path.replace("\\", "\\\\") + " token=hunter2hunter2 ghp_0123456789abcdefghijABCDEFGHIJ012345 "
          "AKIAABCDEFGHIJKLMNOP " + "f" * 40 + "\")\n")
    context(session_start(launcher, tmp_path, proj, env={"CLAUDE_PLUGIN_ROOT": str(plugin)}))
    text = read(hooks_log(tmp_path))
    assert log_lines(tmp_path), text
    for leak in ("SECRET", "sk-live", "alice", "private", "hunter2", "ghp_0123", "AKIAABCD", "f" * 40):
        assert leak not in text, (leak, text)
    assert "<redacted>" in text and "customers.csv" in text, "the shape stays: a redacted literal, a base name"


def test_an_unusable_feedback_folder_never_blocks(launcher, tmp_path, proj):
    write(user_home(tmp_path) / ".plumb", "a file, not a folder\n")
    r = edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW, env=broken_audit(tmp_path))
    allowed(r)
    assert len(notes(r)) == 1
    assert read(user_home(tmp_path) / ".plumb") == "a file, not a folder\n"


def test_log_failure_in_process(H, tmp_path, monkeypatch, proj):
    home = tmp_path / "in-process-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setitem(H._LOG_CONTEXT, "project", H.Project(proj))
    monkeypatch.setitem(H._LOG_CONTEXT, "payload", None)
    try:
        raise KeyError("x")
    except KeyError as exc:
        H.log_failure("the checks were skipped (KeyError: 'x')\nsecond line", "the checks run", exc=exc)
    path = home / ".plumb" / "feedback" / "hooks.md"
    (line,) = [ln for ln in read(path).splitlines() if ln.startswith("- ")]
    assert "Given: the checks were skipped (KeyError: 'x') second line · Expected: the checks run" in line
    assert " at test_hooks.py:" in line, "the crash's place, base names only"
    # a long message is cut to one short field; a full log is left alone
    H.log_failure("x" * 5000, "y")
    assert max(len(ln) for ln in read(path).splitlines()) < 1000
    with open(path, "ab") as fh:
        fh.write(b"." * H.FEEDBACK_MAX_BYTES)
    size = path.stat().st_size
    H.log_failure("another", "y")
    assert path.stat().st_size == size
    # a PlumbError is the project's problem: never logged
    path.write_text("# Plumb hook failures\n\n", encoding="utf-8")
    H.log_failure("broken tokens", "y", exc=type("PlumbError", (Exception,), {})("error: x"))
    assert read(path) == "# Plumb hook failures\n\n"


@pytest.fixture
def log_home(H, tmp_path, monkeypatch, proj) -> Path:
    """An in-process log_failure set up for `proj`, writing under its own home; returns hooks.md's path."""
    home = tmp_path / "in-process-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setitem(H._LOG_CONTEXT, "project", H.Project(proj))
    monkeypatch.setitem(H._LOG_CONTEXT, "payload", None)
    return home / ".plumb" / "feedback" / "hooks.md"


def test_redact_keeps_the_shape_and_drops_the_data(H, proj):
    root = os.path.realpath(str(proj))
    outside = "/Users/alice/secret/notes.txt" if os.sep == "/" else "C:\\Users\\alice\\secret\\notes.txt"
    text = (f"could not convert string to float: 'sk-live-SECRET1234567890' at {outside}, "
            f"in {os.path.join(root, 'app', 'page.tsx')}: \"Hello, Ada Lovelace\" KeyError: 'x' "
            "password=hunter2 api_key: abc123def Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.e30.abc "
            "ghp_0123456789abcdefghijABCDEFGHIJ012345 xoxb-123456789012-abcdefghij AKIAABCDEFGHIJKLMNOP "
            + "a" * 48 + " " + "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0123456789== "
            + "No such file: '" + root + "/components/x.tsx'")
    out = H.redact(text, root)
    assert "'components/x.tsx'" in out, "a quoted project path is kept, project-relative"
    for leak in ("SECRET", "sk-live", "alice", "secret/", "Ada", "hunter2", "abc123def", "eyJhbG", "ghp_0123",
                 "xoxb-1234", "AKIAABCD", "a" * 48, "QUJDREVG"):
        assert leak not in out, (leak, out)
    assert "'<redacted>'" in out and "notes.txt" in out, out
    assert "app/page.tsx" in out.replace("\\", "/"), "a path inside the project stays, project-relative"
    assert "KeyError: 'x'" in out, "a short literal (a key name) is kept"
    assert "password=<redacted>" in out and "api_key: <redacted>" in out and "Bearer <redacted>" in out, out


def test_timeouts_are_logged_once_per_project_and_version_crashes_once_a_day(H, log_home):
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 2 * 24 * 3600))
    today = time.strftime("%Y-%m-%d")
    H.log_failure("audit.py --json did not finish within 2 s", "it finishes", category="timeout")
    H.log_failure("the checks were skipped (KeyError)", "they run")
    log_home.write_text(read(log_home).replace(f"- {today} ", f"- {yesterday} "), encoding="utf-8")
    H.log_failure("audit.py --json did not finish within 2 s", "it finishes", category="timeout")
    H.log_failure("the checks were skipped (KeyError)", "they run")
    lines = [ln for ln in read(log_home).splitlines() if ln.startswith("- ")]
    assert sum(" · timeout · " in ln for ln in lines) == 1, lines
    assert sum(" · crash · " in ln for ln in lines) == 2, lines


def test_the_header_is_written_once_when_another_writer_creates_the_file_first(H, log_home, monkeypatch):
    real_link = os.link

    def raced(src, dst, *a, **kw):  # another hook creates hooks.md (header and its line) just before this one
        if not os.path.lexists(dst):
            fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, (H.FEEDBACK_HEADER + "- 2026-01-01 00:00 other line\n").encode("utf-8"))
            os.close(fd)
        return real_link(src, dst, *a, **kw)

    monkeypatch.setattr(H.os, "link", raced)
    H.log_failure("first", "y")
    text = read(log_home)
    assert text.count("# Plumb hook failures") == 1 and text.startswith("# Plumb hook failures")
    lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert len(lines) == 2 and "Given: first" in lines[-1], text
    assert not [p for p in log_home.parent.iterdir() if p.name != "hooks.md"], "no temporary file left"


def _race_writers(tmp_path, proj, home, name, count):
    """`count` separate processes call log_failure at the same instant (one Given each); waits for all of them."""
    go = tmp_path / f"go-{name}"
    script = tmp_path / "writer.py"
    script.write_text(
        "import importlib.util, os, sys, time\n"
        f"spec = importlib.util.spec_from_file_location('h', {str(HOOKS / '_hooklib.py')!r})\n"
        "H = importlib.util.module_from_spec(spec); spec.loader.exec_module(H)\n"
        f"H._LOG_CONTEXT['project'] = H.Project(H.Path({str(proj)!r}))\n"
        "while not os.path.exists(sys.argv[2]): time.sleep(0.001)\n"
        "H.log_failure(sys.argv[1], 'y')\n", encoding="utf-8")
    import subprocess as sp
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    procs = [sp.Popen([sys.executable, str(script), f"{name}-{n:02d}", str(go)], env=env) for n in range(count)]
    time.sleep(1.0)
    go.write_text("", encoding="utf-8")
    assert all(p.wait(timeout=120) == 0 for p in procs)


def test_two_hooks_writing_at_once_give_one_header(tmp_path, proj):
    home = tmp_path / "race-home"
    home.mkdir()
    log = home / ".plumb" / "feedback" / "hooks.md"
    # first round: hooks.md does not exist yet (one header); second round: every writer appends to it at once
    # (Windows emulates O_APPEND with a seek and a write, so unlocked appends there lose lines)
    for name in ("create", "append"):
        _race_writers(tmp_path, proj, home, name, 16)
    text = read(log)
    assert text.startswith("# Plumb hook failures") and text.count("# Plumb hook failures") == 1, text
    given = [ln.rsplit("Given: ", 1)[1].split(" ", 1)[0] for ln in text.splitlines() if ln.startswith("- ")]
    assert sorted(given) == sorted(f"{name}-{n:02d}" for name in ("create", "append") for n in range(16)), text
    body = text.split("\n\n", 2)[2].splitlines()  # after the title and the intro paragraph
    assert len(body) == 32 and all(ln.startswith("- ") and ln.count("Given: ") == 1 for ln in body), text
    assert not [p for p in log.parent.iterdir() if p.name != "hooks.md"], "no temporary or lock file left"


def test_a_hook_never_waits_long_for_the_log_lock(H, log_home):
    H.log_failure("first", "y")
    fd = os.open(str(log_home), os.O_WRONLY | getattr(os, "O_BINARY", 0))
    try:
        assert H._lock_log(fd)  # another hook is appending right now (and never lets go)
        start = time.monotonic()
        H.log_failure("second", "y")  # never raises, never blocks: the line is left out
        took = time.monotonic() - start
        assert took < 1.0, took
        assert "Given: second" not in read(log_home)
    finally:
        H._unlock_log(fd)
        os.close(fd)
    H.log_failure("third", "y")  # the lock is free again
    text = read(log_home)
    assert "Given: first" in text and "Given: third" in text and "Given: second" not in text


def test_the_suite_never_sees_the_real_home():
    import conftest
    real = conftest._REAL_HOME[0]
    assert os.path.realpath(str(Path.home())) != os.path.realpath(real)
    assert os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "browser tests still find the real browser cache"


def test_log_failure_needs_a_plumb_project(H, tmp_path, monkeypatch):
    home = tmp_path / "in-process-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setitem(H._LOG_CONTEXT, "project", None)
    monkeypatch.chdir(tmp_path)
    H.log_failure("x", "y")
    assert not (home / ".plumb").exists()


def test_session_start_points_to_plumb_feedback(launcher, tmp_path, proj):
    text = context(session_start(launcher, tmp_path, proj))
    assert "Plumb mistakes (a Plumb script, hook or skill got it wrong) → /plumb:feedback" in text.splitlines()
    set_plumb(proj, role="linked", skill="../home-repo/.claude/skills/demo-design-system")
    assert "/plumb:feedback" in context(session_start(launcher, tmp_path, proj, session="sess-2"))
