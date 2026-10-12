"""GitHub Copilot CLI support for Plumb's hooks: the same hooks.json, scripts and launchers as Claude Code.

Copilot CLI loads the plugin's Claude-format hooks.json and sends Claude-style hook input, with these differences, each
pinned here (the shapes Slate pinned with Copilot CLI 1.0.94; payload samples in tests/fixtures/hooks/copilot/):

- its edit tool sends tool_input as apply_patch text ("*** Update File: <path>") instead of {file_path}: the hunks are
  applied to the current file to get the text after the edit; when they don't apply, only the added lines are checked;
- its own camelCase input (toolName / toolArgs, toolArgs a JSON string or an object, or raw patch text);
- str_replace-style ({path, old_str, new_str}) and create-style ({path, file_text}) edit input;
- an exit-2 refusal reaches the model only as "hook exited with code 2", so under Copilot (COPILOT_CLI set, patch text or
  camelCase input) a refusal is {"permissionDecision": "deny", ...} on stdout, flat and in hookSpecificOutput, exit 0;
- SessionStart plain stdout never reaches the model; {"additionalContext": ...} does;
- Stop: whether a plugin's Stop hook reaches Copilot's agentStop and can make it continue is verified live (spec §17);
  the hook answers Copilot with the same {"decision": "block", "reason": ...} JSON as Claude Code.

Every case runs through the launchers (run.sh; run.cmd through PowerShell on Windows).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from hook_support import (HOOKS, LAUNCHERS, MAP, POWERSHELL, PLUGIN, SCREENS, SKILL_REL, WINDOWS, actionable, allowed,
                          denied, hook_env, make_project, patch, payload, read, refused, run_hook, write)

pytestmark = pytest.mark.skipif(not LAUNCHERS, reason="no hook launcher (sh or PowerShell) on this machine")

RAW = 'className="bg-[#ff0000]"'
H1 = "<h1>Today&apos;s tables</h1>"


@pytest.fixture(params=LAUNCHERS)
def launcher(request) -> str:
    return request.param


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    return make_project(tmp_path)


def pre(launcher, tmp_path, proj, name, copilot=True, stringify=None, **values):
    values.setdefault("CWD", str(proj))
    return run_hook(launcher, "pre_edit.py", payload("copilot", name, stringify=stringify, **values), proj,
                    hook_env(tmp_path, copilot))


def update(path: str, old: str, new: str, context: str = "") -> str:
    ctx = f" {context}\n" if context else ""
    return f"*** Update File: {path}\n@@\n{ctx}-{old}\n+{new}\n"


# ---------------------------------------------------------------- apply_patch text


def test_patch_adding_a_raw_colour_is_denied_with_the_reason(launcher, tmp_path, proj):
    body = patch(update(str(proj / "app/page.tsx"), f"      {H1}", f"      <h1 {RAW}>Today&apos;s tables</h1>"))
    reason = denied(pre(launcher, tmp_path, proj, "apply_patch", PATCH=body))
    assert reason.startswith("Plumb edit check: this edit adds 1 design-system error to app/page.tsx")
    assert "#ff0000" in reason
    actionable(reason)


def test_patch_with_a_relative_path_resolves_against_cwd(launcher, tmp_path, proj):
    body = patch(update("app/page.tsx", f"      {H1}", f"      <h1 {RAW}>Today&apos;s tables</h1>"))
    assert "#ff0000" in denied(pre(launcher, tmp_path, proj, "apply_patch", PATCH=body))


def test_patch_keeping_old_values_is_allowed(launcher, tmp_path, proj):
    write(proj / "components/legacy.tsx", f"export const Legacy = () => (\n  <div {RAW}>\n    old copy\n  </div>\n);\n")
    body = patch(update("components/legacy.tsx", "    old copy", "    new copy", context=f"  <div {RAW}>"))
    r = pre(launcher, tmp_path, proj, "apply_patch", PATCH=body)
    assert r.returncode == 0 and r.stdout == "", r.stdout


def test_patch_that_does_not_apply_checks_only_added_lines(launcher, tmp_path, proj):
    write(proj / "components/legacy.tsx", f"export const Legacy = () => <div {RAW}>x</div>;\n")
    stale = patch(update("components/legacy.tsx", "this line is not in the file", '<p className="text-[#00ff00]">y</p>'))
    reason = denied(pre(launcher, tmp_path, proj, "apply_patch", PATCH=stale))
    assert "#00ff00" in reason and "#ff0000" not in reason
    stale_clean = patch(update("components/legacy.tsx", "this line is not in the file", "<p>plain</p>"))
    allowed(pre(launcher, tmp_path, proj, "apply_patch", PATCH=stale_clean))


def test_patch_adding_a_new_route_is_denied_prototype_first(launcher, tmp_path, proj):
    body = patch("*** Add File: app/billing/page.tsx\n+export default function Billing() {\n+  return <h1>Billing</h1>;\n+}\n")
    reason = denied(pre(launcher, tmp_path, proj, "apply_patch", PATCH=body))
    assert "error: app/billing/page.tsx is a new screen with no approved prototype" in reason
    assert "fix: /plumb:prototype billing" in reason


@pytest.mark.parametrize("header", ["Update File", "Add File", "Delete File"])
def test_patch_touching_a_generated_file_is_denied(launcher, tmp_path, proj, header):
    body = patch(f"*** {header}: {proj / 'app/globals.css'}\n@@\n-a\n+b\n")
    reason = denied(pre(launcher, tmp_path, proj, "apply_patch", PATCH=body))
    assert reason.startswith("error: app/globals.css is generated")


def test_patch_moving_a_file_onto_a_generated_file_is_denied(launcher, tmp_path, proj):
    body = patch(f"*** Update File: notes.css\n*** Move to: {MAP}\n@@\n-a\n+b\n")
    assert denied(pre(launcher, tmp_path, proj, "apply_patch", PATCH=body)).startswith(f"error: {MAP} is generated")


def test_multi_file_patch_is_denied_when_any_file_is_guarded(launcher, tmp_path, proj):
    body = patch("*** Add File: notes.txt\n+hi\n", f"*** Update File: {SKILL_REL}/scripts/audit.py\n@@\n-a\n+b\n")
    assert "is Plumb's file; upgrades replace it" in denied(pre(launcher, tmp_path, proj, "apply_patch", PATCH=body))


def test_patch_of_other_files_is_allowed_silently(launcher, tmp_path, proj):
    body = patch("*** Add File: notes.txt\n+hi\n", "*** Update File: README.md\n@@\n-Notes.\n+More notes.\n")
    r = pre(launcher, tmp_path, proj, "apply_patch", PATCH=body)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_patch_without_copilot_env_is_still_answered_in_copilots_dialect(launcher, tmp_path, proj):
    body = patch(f"*** Update File: {SKILL_REL}/assets/platforms/web/tokens.css\n@@\n-a\n+b\n")
    assert " is generated" in denied(pre(launcher, tmp_path, proj, "apply_patch", copilot=False, PATCH=body))


def test_camel_case_input_with_raw_patch_text(launcher, tmp_path, proj):
    body = patch(update("app/page.tsx", f"      {H1}", f"      <h1 {RAW}>Today&apos;s tables</h1>"))
    assert "#ff0000" in denied(pre(launcher, tmp_path, proj, "apply_patch_camel", copilot=False, PATCH=body))


# ---------------------------------------------------------------- path-style edit tools and camelCase args


def test_str_replace_input_is_checked(launcher, tmp_path, proj):
    reason = denied(pre(launcher, tmp_path, proj, "str_replace", FILE=str(proj / "app/page.tsx"), OLD=H1,
                        NEW=f"<h1 {RAW}>Today&apos;s tables</h1>"))
    assert "#ff0000" in reason
    allowed(pre(launcher, tmp_path, proj, "str_replace", FILE=str(proj / "app/page.tsx"), OLD=H1, NEW="<h1>Tables</h1>"))


def test_create_input_is_checked(launcher, tmp_path, proj):
    reason = denied(pre(launcher, tmp_path, proj, "create", FILE="app/billing/page.tsx", CONTENT="export default () => null;\n"))
    assert "fix: /plumb:prototype billing" in reason
    assert " is generated" in denied(pre(launcher, tmp_path, proj, "create", FILE="docs/design/prototype.html", CONTENT="x"))


@pytest.mark.parametrize("stringify", [None, "toolArgs"])
def test_camel_case_tool_args_object_or_json_string(launcher, tmp_path, proj, stringify):
    r = pre(launcher, tmp_path, proj, "edit_camel", copilot=False, stringify=stringify, FILE=str(proj / "app/page.tsx"),
            OLD=H1, NEW=f"<h1 {RAW}>Today&apos;s tables</h1>")
    assert "#ff0000" in denied(r)
    r = pre(launcher, tmp_path, proj, "edit_camel", copilot=False, stringify=stringify,
            FILE=str(proj / SKILL_REL / "templates/player.js"), OLD="a", NEW="b")
    assert "is Plumb's file" in denied(r)


# ---------------------------------------------------------------- shell commands


def test_shell_write_is_denied_with_the_reason(launcher, tmp_path, proj):
    reason = denied(pre(launcher, tmp_path, proj, "bash", COMMAND="sed -i 's/a/b/' app/globals.css"))
    assert reason.startswith("error: app/globals.css is generated")
    actionable(reason)
    assert " is generated" in denied(pre(launcher, tmp_path, proj, "bash_camel", copilot=False,
                                         COMMAND="echo x > docs/design/screens.html"))


@pytest.mark.parametrize("command", ["Set-Content docs/design/specimen.html 'x'",
                                     "'{}' | Out-File -FilePath docs\\design\\prototype\\screens.json"])
def test_powershell_writes_are_denied(launcher, tmp_path, proj, command):
    assert " is generated" in denied(pre(launcher, tmp_path, proj, "powershell", COMMAND=command))


def test_powershell_build_and_reads_are_allowed(launcher, tmp_path, proj):
    for command in (f"py -3 {SKILL_REL}\\scripts\\build-tokens.py", "Get-Content app/globals.css"):
        allowed(pre(launcher, tmp_path, proj, "powershell", COMMAND=command))


def test_claude_code_refusals_are_unchanged(launcher, tmp_path, proj):
    r = run_hook(launcher, "pre_edit.py", payload("claude", "write", CWD=str(proj), FILE=str(proj / "app/globals.css"),
                                                  CONTENT="x"), proj, hook_env(tmp_path, copilot=False))
    assert refused(r).startswith("error: app/globals.css is generated")


def test_copilot_without_plumb_md_is_never_blocked(launcher, tmp_path, proj):
    (proj / "PLUMB.md").unlink()
    body = patch(f"*** Update File: {SKILL_REL}/scripts/audit.py\n@@\n-a\n+b\n")
    r = pre(launcher, tmp_path, proj, "apply_patch", PATCH=body)
    assert r.returncode == 0 and r.stdout == ""


# ---------------------------------------------------------------- session start and stop


def test_session_start_gives_copilot_additional_context(launcher, tmp_path, proj):
    r = run_hook(launcher, "session_start.py", payload("copilot", "session_start", CWD=str(proj)), proj,
                 hook_env(tmp_path, copilot=True))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert list(out) == ["additionalContext"]
    assert out["additionalContext"].startswith("Plumb: demo-design-system 1.0.0 · tokens up to date · ")


def test_session_start_for_claude_code_is_plain_text(launcher, tmp_path, proj):
    r = run_hook(launcher, "session_start.py", payload("claude", "session_start", CWD=str(proj)), proj,
                 hook_env(tmp_path, copilot=False))
    if launcher == "sh":  # Claude Code runs the sh command; the powershell one is Copilot CLI's
        assert r.stdout.startswith("Plumb: demo-design-system 1.0.0 · ")


def test_session_start_without_plumb_md_is_silent_in_copilot(launcher, tmp_path):
    r = run_hook(launcher, "session_start.py", payload("copilot", "session_start", CWD=str(tmp_path)), tmp_path,
                 hook_env(tmp_path, copilot=True))
    assert r.returncode == 0 and r.stdout == ""


def test_stop_in_copilot_blocks_with_the_same_json(launcher, tmp_path, proj):
    env = hook_env(tmp_path, copilot=True)
    run_hook(launcher, "session_start.py", payload("copilot", "session_start", CWD=str(proj)), proj, env)
    write(proj / "components/widget.tsx", f"export const W = () => <p {RAW}>w</p>;\n")
    r = run_hook(launcher, "stop_check.py", payload("copilot", "stop", CWD=str(proj)), proj, env)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["decision"] == "block" and "#ff0000" in out["reason"]
    # Copilot sends no stop_hook_active: the second stop only reports
    r = run_hook(launcher, "stop_check.py", payload("copilot", "stop", CWD=str(proj)), proj, env)
    assert "decision" not in json.loads(r.stdout)


# ---------------------------------------------------------------- hooks.json and run.cmd for both tools


def _hook_entries():
    hooks = json.loads(read(HOOKS / "hooks.json"))["hooks"]
    return {event: [h for entry in entries for h in entry["hooks"]] for event, entries in hooks.items()}


def test_every_hook_has_a_windows_powershell_command():
    expected = {"SessionStart": "session_start.py", "PreToolUse": "pre_edit.py", "Stop": "stop_check.py"}
    entries = _hook_entries()
    assert set(entries) == set(expected)
    for event, script in expected.items():
        for h in entries[event]:
            ps = h["powershell"]
            assert '$s = "$env:CLAUDE_PLUGIN_ROOT\\hooks\\run.cmd"' in ps
            assert f"& $s {script}; exit $LASTEXITCODE" in ps
            assert ps.rstrip().endswith("exit 0")  # a missing launcher never blocks a tool call (Copilot fails closed)
            assert isinstance(h.get("timeout"), int) and h["timeout"] > 0


def test_matcher_covers_edits_and_both_shells():
    hooks = json.loads(read(HOOKS / "hooks.json"))["hooks"]
    assert set(hooks["PreToolUse"][0]["matcher"].split("|")) == {"Edit", "Write", "MultiEdit", "Bash", "PowerShell"}


def test_run_cmd_has_crlf_endings_and_tries_each_python():
    raw = (HOOKS / "run.cmd").read_bytes()
    text = raw.decode("utf-8")
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n")  # cmd.exe labels need CRLF
    for py in ("py -3", "python", "python3"):
        assert f'{py} -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" <nul' in text
    assert 'set "PLUMB_PYTHON=py -3"' in text
    # cmd.exe must not find py/python in the current directory (the project) before PATH
    lines = text.splitlines()
    first_lookup = next(i for i, ln in enumerate(lines) if ln.startswith(("py ", "python")))
    assert any(ln.strip() == 'set "NoDefaultCurrentDirectoryInExePath=1"' for ln in lines[:first_lookup])
    assert "exit /b 0" in text and "slate" not in text.lower()


windows_only = pytest.mark.skipif(not WINDOWS, reason="runs the real PowerShell/cmd launcher")


@windows_only
def test_windows_powershell_hook_without_plugin_root_never_blocks(tmp_path):
    (h,) = _hook_entries()["PreToolUse"]
    env = hook_env(tmp_path, copilot=True)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    import subprocess
    r = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", h["powershell"]], input="{}",
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(tmp_path),
                       timeout=60)
    assert r.returncode == 0


@windows_only
def test_windows_launcher_never_runs_a_python_planted_in_the_project(tmp_path):
    proj = make_project(tmp_path)
    marker = tmp_path / "planted-ran"
    for name in ("py.bat", "py.cmd", "python.bat", "python.cmd", "python3.bat", "python3.cmd"):
        write(proj / name, f"@echo off\r\necho ran > \"{marker}\"\r\n", newline="")
    r = run_hook("powershell", "pre_edit.py", payload("copilot", "bash", CWD=str(proj), COMMAND="echo hi"), proj,
                 hook_env(tmp_path, copilot=True))
    assert r.returncode == 0
    assert not marker.exists()
