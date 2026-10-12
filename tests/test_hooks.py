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
import sys
import time
from pathlib import Path

import pytest

from hook_support import (BUILD_PROTOTYPE, BUILD_TOKENS, CI, HOOKS, LAUNCHERS, MAP, PLUGIN, REPO, SCREENS, SKILL_REL,
                          actionable, allowed, context, git, git_init, hook_env, make_project, needs_git, notes, patch,
                          payload, plant_markers, plugin_copy, plumb_md, plumb_tmp, read, refused, run_hook,
                          run_script, set_plumb, write)

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
    found = H.shell_targets(command, str(tmp_path)) + H.shell_removals(command, str(tmp_path))
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
    found = [Path(t) for t in H.shell_removals(command, str(tmp_path))]
    assert [str(p.relative_to(tmp_path)).replace("\\", "/") for p in found] == removed


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


def _best(fn, limit: float, n: int = 12) -> float:
    """The fastest of at least 5 runs, and up to n while none is under the limit: a loaded machine (other test
    processes, CI neighbours) slows single runs down, while the hook's own cost shows in the fastest one."""
    best = float("inf")
    for i in range(n):
        t = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t)
        if i >= 4 and best < limit:
            break
    return best


def test_non_ui_edit_is_fast(launcher, tmp_path, proj):
    limit = 0.6 if CI or launcher == "powershell" else 0.15
    took = _best(lambda: allowed(edit(launcher, tmp_path, proj, "README.md", "Notes.", "More notes.")), limit)
    assert took < limit, f"non-UI edit took {took * 1000:.0f} ms (limit {limit * 1000:.0f} ms)"


def test_ui_edit_is_fast(launcher, tmp_path, proj):
    limit = 3.0 if CI or launcher == "powershell" else 1.0
    took = _best(lambda: refused(edit(launcher, tmp_path, proj, "app/page.tsx", H1, H1_RAW)), limit)
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


def test_stop_reports_a_new_route_without_a_prototype(launcher, tmp_path, proj):
    _start(launcher, tmp_path, proj)
    write(proj / "app/billing/page.tsx", BILLING)
    reason = _block(stop(launcher, tmp_path, proj))
    assert "route /billing" in reason and "/plumb:prototype billing" in reason


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
    found = [Path(t) for t in H.shell_targets(command, str(tmp_path))]
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
    found = H.shell_targets(command.format(d=tmp_path), str(tmp_path))
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
