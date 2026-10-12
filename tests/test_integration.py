"""End to end on three sample apps (tests/fixtures/apps/): a Next.js + Tailwind v4 app, an Angular app (SCSS) and a
SwiftUI app. No npm, no Xcode project, no network: only Plumb's own scripts.

For each app: detect.py's first guess, scaffold.py with the confirmed answers, build-tokens.py (light and dark), audit.py
catching every deliberate violation by its named rule and exiting 0 once the fixes are applied, build-prototype.py with a
screen per route, and the hooks run as the CLIs run them (run.sh with real payload samples): session start, the edit
check, the guard, prototype first and the end-of-turn check. The SwiftUI theme and views are type-checked with swiftc in
test_swift_typecheck.py (macOS only); Compose output is checked structurally in test_build_tokens_mobile.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hook_support import (LAUNCHERS, actionable, allowed, context, hook_env, payload, refused, run_hook)
from sample_apps import (APPS, DOCS, SCREENS, WEB_APPS, App, audit, copy_app, detect, errors, fix, ok, project,
                         prototype, read, scaffold, skill_script, write)


@pytest.fixture(params=list(APPS))
def app(request) -> App:
    return APPS[request.param]


@pytest.fixture(params=WEB_APPS)
def web_app(request) -> App:
    return APPS[request.param]


# ---------------------------------------------------------------- detect, scaffold, build, audit, fix, prototype


def test_detect_first_guess_matches_each_app(app, tmp_path):
    found = detect(copy_app(app, tmp_path / app.slug))
    assert found["layout"] == "frontend"
    (ui,) = found["ui_packages"]
    assert (ui["path"], ui["framework"], ui["styling"], ui["platforms"]) == (".", app.framework, app.styling,
                                                                            app.platforms)
    assert ui["files"] == app.files
    assert found["proposal"]["skill_dir"] == app.skill
    assert found["proposal"]["copies"] == app.copies
    assert found["proposal"]["platforms"] == app.platforms
    # only Angular needs its own UI files (component files, not every .ts); the others keep scaffold.py's default
    assert found["proposal"]["ui_files"] == (app.ui_files if app.framework == "angular" else None)


def test_swiftui_app_without_a_package_file_is_found_and_audited(tmp_path):
    app = APPS["swiftui"]
    proj = copy_app(app, tmp_path / app.slug)
    (proj / "Package.swift").unlink()
    found = detect(proj)
    (ui,) = found["ui_packages"]
    assert (ui["path"], ui["framework"], ui["platforms"], ui["files"]) == ("SampleHabits", "swiftui", ["ios"], 3)
    assert found["confidence"] == "low" and found["proposal"]["skill_dir"] == app.skill
    scaffold(proj, app, found)
    code, report = audit(proj, app)
    assert code == 1
    assert sorted((f["file"], f["rule"]) for f in errors(report)) == sorted((r, rule) for r, rule, _ in app.violations)


def test_full_flow_finds_every_violation_then_passes_after_the_fixes(app, tmp_path):
    proj = copy_app(app, tmp_path / app.slug)
    found = detect(proj)
    out = scaffold(proj, app, found).stdout
    assert "wrote: PLUMB.md" in out and f"wrote: {app.tokens}" in out
    plumb = read(proj / "PLUMB.md")
    # no ui_files answer is passed: the stack-aware default must cover the violations (Angular: component files)
    assert f"Design system: `{app.skill}/`" in plumb and f"\nUI files: {app.ui_files}\n" in plumb
    ok(skill_script(proj, app, "build-tokens.py", "--check"))

    code, report = audit(proj, app)
    assert code == 1
    got = sorted((f["file"], f["rule"]) for f in errors(report))
    assert got == sorted((rel, rule) for rel, rule, _ in app.violations), json.dumps(errors(report), indent=1)
    for rel, rule, text in app.violations:
        hits = [f for f in errors(report) if f["file"] == rel and f["rule"] == rule and text in f["message"]]
        assert hits, (rel, rule, text)
        assert all(h["fix"] for h in hits), hits

    fix(proj, app)
    code, report = audit(proj, app)
    assert code == 0 and errors(report) == [], json.dumps(errors(report), indent=1)
    assert [f["rule"] for f in report["findings"] if f["severity"] == "warn"].count("no-prototype") == 1

    prototype(proj, app)
    ok(skill_script(proj, app, "build-prototype.py", "--check"))
    code, report = audit(proj, app)
    assert code == 0 and errors(report) == [], json.dumps(errors(report), indent=1)
    assert "no-prototype" not in {f["rule"] for f in report["findings"]}
    ok(skill_script(proj, app, "build-tokens.py", "--check"))


STOCK_NEXT = Path(__file__).resolve().parent / "fixtures/apps/next-tailwind-stock"


def test_a_stock_create_next_app_stylesheet_ends_with_audit_exit_0(tmp_path):
    """create on a stock Next.js app: its globals.css sets --color-background, --color-foreground, --font-sans and
    --font-mono in its own @theme inline block (block-override). The documented step: build-tokens.py --overrides lists
    them with the token each maps onto, the user says yes, --overrides --apply moves them, the rebuild and the audit
    pass."""
    app = APPS["next-tailwind"]
    proj = copy_app(app, tmp_path / "stock" / app.slug)
    for rel in ("app/globals.css", "app/layout.tsx"):
        write(proj / rel, read(STOCK_NEXT / rel))
    fix(proj, app)
    scaffold(proj, app, detect(proj), {"fonts": {"sans": "Geist", "mono": "Geist Mono"}})
    prototype(proj, app)
    code, report = audit(proj, app)
    assert code == 1
    overrides = sorted(f["message"].split()[0] for f in errors(report) if f["rule"] == "block-override")
    assert overrides == ["--color-background", "--color-foreground", "--font-mono", "--font-sans"]
    assert all(f["file"] == "app/globals.css" for f in errors(report)), errors(report)

    data = json.loads(ok(skill_script(proj, app, "build-tokens.py", "--overrides")).stdout)
    (copy,) = data["copies"]
    kinds = {o["name"]: (o["kind"], o["token"], o["token_change"]) for o in copy["overrides"]}
    assert kinds["--color-background"] == ("token", "color.background", None)
    assert kinds["--color-foreground"][:2] == ("new-name", "color.foreground")
    assert kinds["--font-sans"][2] == {"prepend": "font.sans", "family": "var(--font-geist-sans)"}
    assert kinds["--font-mono"][2] == {"prepend": "font.mono", "family": "var(--font-geist-mono)"}
    assert copy["by_hand"] == []

    out = ok(skill_script(proj, app, "build-tokens.py", "--overrides", "--apply")).stdout
    assert "wrote app/globals.css" in out
    ok(skill_script(proj, app, "build-tokens.py"))
    code, report = audit(proj, app)
    assert code == 0, errors(report)
    css = read(proj / "app/globals.css")
    assert "@theme inline" not in css and "#ffffff" not in css.split("/* plumb:end */")[1]
    tokens = json.loads(read(proj / app.tokens))
    assert tokens["font"]["sans"]["$value"][:2] == ["var(--font-geist-sans)", "Geist"]
    assert "--color-foreground: var(--color-on-surface);" in css  # text-foreground in layout.tsx is a token now
    ok(skill_script(proj, app, "build-tokens.py", "--check"))


SHADCN_NEXT = Path(__file__).resolve().parent / "fixtures/apps/next-tailwind-shadcn"


def test_a_stock_shadcn_stylesheet_leaves_only_real_findings_after_one_ok(tmp_path):
    """create on a Next.js + shadcn (new-york) app: 41 variables in its own @theme inline block, oklch values in :root
    and .dark. After one --overrides --apply, nothing in globals.css is reported: what the audit still says (if
    anything) is about the app's own code, the /plumb:audit fix flow."""
    app = APPS["next-tailwind"]
    proj = copy_app(app, tmp_path / "shadcn" / app.slug)
    for path in sorted(SHADCN_NEXT.rglob("*")):
        if path.is_file():
            write(proj / path.relative_to(SHADCN_NEXT), read(path))
    fix(proj, app)
    scaffold(proj, app, detect(proj))
    prototype(proj, app)
    code, report = audit(proj, app)
    assert code == 1
    assert any(f["rule"] == "block-override" for f in errors(report))
    data = json.loads(ok(skill_script(proj, app, "build-tokens.py", "--overrides")).stdout)
    assert len(data["copies"][0]["overrides"]) == 38 and data["copies"][0]["by_hand"] == []
    ok(skill_script(proj, app, "build-tokens.py", "--overrides", "--apply"))
    ok(skill_script(proj, app, "build-tokens.py"))
    code, report = audit(proj, app)
    left = [f for f in report["findings"] if f["file"] == "app/globals.css" or f["rule"] in ("block-override", "raw-colour")]
    assert left == [], left
    assert code == 0, errors(report)  # this sample app has no findings of its own left
    tokens = json.loads(read(proj / app.tokens))
    assert tokens["radius"]["xl"] == {"$value": "14px"} and tokens["color"]["sidebar-accent"] == {"$value": "{color.sunk}"}
    ok(skill_script(proj, app, "build-tokens.py", "--check"))


def test_token_aware_fix_lines_name_the_token(tmp_path):
    proj = project(APPS["next-tailwind"], "built", tmp_path)
    _, report = audit(proj, APPS["next-tailwind"])
    fixes = {f["message"]: f["fix"] for f in errors(report)}
    assert fixes["arbitrary design value rounded-[6px]"].startswith("rounded-sm (radius.sm = 4px)")
    assert fixes["arbitrary design value duration-[250ms]"].startswith("duration-200 (motion.duration.mid = 200ms)")
    assert fixes["raw colour #c0392b"].startswith("var(--color-danger) (color.danger = ")


def test_every_screen_is_in_the_prototype_and_the_map(app, tmp_path):
    proj = project(app, "ready", tmp_path)
    doc = json.loads(read(proj / DOCS / "prototype/screens.json"))
    by_id = {s["id"]: s for s in doc["screens"]}
    assert set(by_id) == {s.id for s in app.screens}
    for screen in app.screens:
        entry = by_id[screen.id]
        assert entry["route"] == screen.route and entry["files"] == screen.files
        assert entry["status"] == "built" and entry["approved"] and entry["states"] == list(screen.states)
    page = read(proj / DOCS / "prototype.html")
    catalogue = read(proj / DOCS / "screens.html")
    for screen in app.screens:
        assert f'data-screen="{screen.id}"' in page and f'data-screen="{screen.id}"' in catalogue
    assert "/* plumb:tokens */" in page


def test_a_route_with_no_screen_is_an_error_with_prototype_sync_on(web_app, tmp_path):
    proj = project(web_app, "ready", tmp_path)
    (proj / SCREENS / "settings.html").unlink()
    doc_path = proj / DOCS / "prototype/screens.json"
    doc = json.loads(read(doc_path))
    doc["screens"] = [s for s in doc["screens"] if s["id"] != "settings"]
    write(doc_path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    ok(skill_script(proj, web_app, "build-prototype.py"))
    code, report = audit(proj, web_app)
    assert code == 1
    (only,) = errors(report)
    assert only["rule"] == "route-not-prototyped"
    assert only["message"].startswith("route /settings ") and " is not prototyped: " in only["message"], only


def test_a_changed_screen_source_is_screen_drift(app, tmp_path):
    proj = project(app, "ready", tmp_path)
    ((rel, (old, new)),) = SYNC_MISS[app.folder]
    write(proj / rel, read(proj / rel).replace(old, new))
    code, report = audit(proj, app)
    assert code == 1
    assert [(f["rule"], f["file"]) for f in errors(report)] == [("screen-drift", f"{SCREENS}/settings.html")]


# ---------------------------------------------------------------- light and dark


def _colour_tokens(doc: dict) -> dict:
    return {k: v for k, v in doc["color"].items() if not k.startswith("$")}


def test_every_colour_has_a_dark_value_in_tokens_and_themes(app, tmp_path):
    proj = project(app, "ready", tmp_path)
    doc = json.loads(read(proj / app.tokens))
    colours = _colour_tokens(doc)
    assert colours
    aliases = {k for k, v in colours.items() if str(v["$value"]).startswith("{")}
    for name, tok in colours.items():
        if name not in aliases:
            assert tok["$extensions"]["plumb"]["dark"], name
    if "web" in app.platforms:
        copy = read(proj / app.copies[0])
        start = "/* plumb:start \u2014 GENERATED by Plumb, do not edit inside */\n"
        css = copy.split(start, 1)[1].split("/* plumb:end */", 1)[0]  # Plumb's block in the project's stylesheet
        theme = read(proj / app.skill / "assets/platforms/web/tokens.css")
        if '@import "tailwindcss"' in copy.split(start, 1)[0]:  # the app's stylesheet imports Tailwind itself
            theme = theme.replace('@import "tailwindcss";\n\n', "", 1)
        assert css == theme
        light, dark = css.split("\n.dark {", 1)
        dark = dark.split("}", 1)[0]
        for name in colours:
            assert f"--color-{name}:" in light, name
            if name not in aliases:
                assert f"--color-{name}:" in dark, name
    if "ios" in app.platforms:
        swift = read(proj / app.skill / app.theme)
        lines = [ln for ln in swift.splitlines() if "public static let" in ln and "Color(sampleHabitsLight:" in ln]
        assert len(lines) == len(colours)
        assert all(re.search(r", dark: 0x[0-9A-F]{6}", ln) for ln in lines), lines
    block = read(proj / app.skill / "references/dark-mode.md").split("<!-- plumb:contrast:start -->")[1]
    block = block.split("<!-- plumb:contrast:end -->")[0]
    assert "| Pair | Light | Dark | Need | Result |" in block and ", 0 failing." in block
    assert not [ln for ln in block.splitlines() if ln.rstrip().endswith("| fail |")]


def test_a_colour_without_a_dark_value_fails_until_it_gets_one(app, tmp_path):
    proj = project(app, "ready", tmp_path)
    path = proj / app.tokens
    original = read(path)
    doc = json.loads(original)
    del doc["color"]["primary"]["$extensions"]["plumb"]["dark"]
    write(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    ok(skill_script(proj, app, "build-tokens.py"))
    code, report = audit(proj, app)
    assert code == 1
    rules = [f["rule"] for f in errors(report)]
    (missing,) = [f for f in errors(report) if f["rule"] == "missing-dark-value"]
    assert missing["message"].startswith("color.primary has no dark value"), missing
    # the dark theme falls back to the light value, and the contrast check measures it in dark
    assert set(rules) == {"missing-dark-value", "contrast"}, rules
    assert all("dark" in f["message"] for f in errors(report) if f["rule"] == "contrast"), errors(report)
    write(path, original)
    ok(skill_script(proj, app, "build-tokens.py"))
    code, report = audit(proj, app)
    assert code == 0, json.dumps(errors(report), indent=1)


# ---------------------------------------------------------------- hooks, run as the CLIs run them

# (file, old, new, text the refusal names): an edit that adds a raw colour, in each app's own language
BAD_EDIT = {
    "next-tailwind": ("components/task-card.tsx", 'className="text-sm"', 'className="text-sm text-[#ff0000]"', "#ff0000"),
    "angular": ("src/app/notes/notes.component.scss", "color: var(--color-primary);", "color: #ff0000;", "#ff0000"),
    "swiftui": ("SampleHabits/HabitListView.swift", ".foregroundStyle(SampleHabitsColor.onSurface)",
                ".foregroundStyle(Color(red: 1, green: 0, blue: 0))", "Color(red: 1, green: 0, blue: 0)"),
}
# (file, old, new): an edit that stays on the tokens
GOOD_EDIT = {
    "next-tailwind": ("components/task-card.tsx", 'className="text-sm"', 'className="text-xs"'),
    "angular": ("src/app/notes/notes.component.scss", "color: var(--color-primary);", "color: var(--color-danger);"),
    "swiftui": ("SampleHabits/HabitListView.swift", "SampleHabitsColor.onSurface)", "SampleHabitsColor.onSurfaceMuted)"),
}
# a UI file outside every screen's source files, and a clean change to it
NEUTRAL = {
    "next-tailwind": ("app/layout.tsx", 'title: "Tasks"', 'title: "Sample tasks"'),
    "angular": ("src/app/app.routes.ts", "{ path: '**', redirectTo: '' },", "{ path: '**', redirectTo: '' }, // fallback"),
    "swiftui": ("SampleHabits/App.swift", "WindowGroup {", "WindowGroup { // the only window"),
}
# a clean change to the settings screen's source code (the prototype screen is left as it was)
SYNC_MISS = {
    "next-tailwind": [("app/settings/page.tsx", (">Save<", ">Save changes<"))],
    "angular": [("src/app/settings/settings.component.ts", (">Save<", ">Save changes<"))],
    "swiftui": [("SampleHabits/SettingsView.swift", ('Button("Save")', 'Button("Save changes")'))],
}


@pytest.fixture(params=LAUNCHERS)
def launcher(request) -> str:
    return request.param


def _pre(launcher, tmp_path, proj, name: str, copilot: bool = False, tool: str = "claude", **values):
    values.setdefault("CWD", str(proj))
    return run_hook(launcher, "pre_edit.py", payload(tool, name, **values), proj, hook_env(tmp_path, copilot))


def _start(launcher, tmp_path, proj):
    return run_hook(launcher, "session_start.py", payload("claude", "session_start", CWD=str(proj)), proj,
                    hook_env(tmp_path))


def _stop(launcher, tmp_path, proj, active=False):
    return run_hook(launcher, "stop_check.py", payload("claude", "stop", CWD=str(proj), ACTIVE=active), proj,
                    hook_env(tmp_path))


def test_session_start_reports_the_design_system(launcher, app, tmp_path):
    proj = project(app, "ready", tmp_path)
    first = context(_start(launcher, tmp_path, proj)).splitlines()[0]
    assert re.match(rf"^Plumb: {app.slug}-design-system \S+ · tokens up to date · \d+ audit issues? · "
                    r"read the skill before UI changes$", first), first


@pytest.mark.parametrize("dialect", ["claude", "copilot"])
def test_edit_check_refuses_a_raw_colour_and_allows_a_token(launcher, app, tmp_path, dialect):
    proj = project(app, "ready", tmp_path)
    rel, old, new, needle = BAD_EDIT[app.folder]
    name, copilot = ("edit", False) if dialect == "claude" else ("str_replace", True)
    reason = refused(_pre(launcher, tmp_path, proj, name, copilot, dialect, FILE=str(proj / rel), OLD=old, NEW=new))
    assert reason.strip().splitlines()[0] == f"Plumb edit check: this edit adds 1 design-system error to {rel}"
    assert needle in reason
    actionable(reason)
    rel, old, new = GOOD_EDIT[app.folder]
    allowed(_pre(launcher, tmp_path, proj, name, copilot, dialect, FILE=str(proj / rel), OLD=old, NEW=new))


def test_guard_refuses_hand_edits_to_the_generated_theme(launcher, app, tmp_path):
    proj = project(app, "ready", tmp_path)
    targets = list(app.copies) + [f"{app.skill}/{app.theme}", f"{DOCS}/prototype.html"]
    for rel in targets:
        reason = refused(_pre(launcher, tmp_path, proj, "write", FILE=str(proj / rel), CONTENT="/* by hand */\n"))
        assert reason.startswith(f"error: {rel} is generated"), reason
        actionable(reason)
    # running the generator is how the theme changes
    allowed(_pre(launcher, tmp_path, proj, "bash", COMMAND=f"python3 {app.skill}/scripts/build-tokens.py"))


def test_prototype_first_refuses_a_new_route_without_a_screen(launcher, web_app, tmp_path):
    proj = project(web_app, "ready", tmp_path)
    if web_app.folder == "next-tailwind":
        rel = "app/billing/page.tsx"
        r = _pre(launcher, tmp_path, proj, "write", FILE=str(proj / rel),
                 CONTENT="export default function Billing() {\n  return <main><h1>Billing</h1></main>;\n}\n")
    else:
        rel = "src/app/app.routes.ts"
        billing = ("  {\n    path: 'billing',\n    loadComponent: () => import('./billing/billing.component')"
                   ".then((m) => m.BillingComponent),\n  },\n")
        r = _pre(launcher, tmp_path, proj, "edit", FILE=str(proj / rel), OLD="  { path: '**', redirectTo: '' },",
                 NEW=billing + "  { path: '**', redirectTo: '' },")
    reason = refused(r)
    assert f"error: {rel}" in reason and "fix: /plumb:prototype billing" in reason
    actionable(reason)


def _block(r) -> str:
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["decision"] == "block", out
    return out["reason"]


def test_end_of_turn_check_blocks_once_on_a_new_violation(launcher, app, tmp_path):
    proj = project(app, "ready", tmp_path)
    assert _start(launcher, tmp_path, proj).returncode == 0
    rel, old, new, needle = BAD_EDIT[app.folder]
    write(proj / rel, read(proj / rel).replace(old, new))
    reason = _block(_stop(launcher, tmp_path, proj))
    assert reason.startswith("Plumb end-of-turn check: ") and f"error: {rel} line " in reason and needle in reason
    actionable(reason)
    again = _stop(launcher, tmp_path, proj, active=True)
    assert again.returncode == 0 and again.stdout == ""  # never blocks twice; the same summary is not repeated


def test_end_of_turn_check_is_one_line_when_consistent(launcher, app, tmp_path):
    proj = project(app, "ready", tmp_path)
    assert _start(launcher, tmp_path, proj).returncode == 0
    rel, old, new = NEUTRAL[app.folder]
    write(proj / rel, read(proj / rel).replace(old, new))
    r = _stop(launcher, tmp_path, proj)
    assert r.returncode == 0 and r.stdout.strip() == "Plumb: 1 UI file checked, consistent", (r.stdout, r.stderr)


def test_end_of_turn_check_stops_on_a_screen_changed_without_its_prototype(launcher, app, tmp_path):
    proj = project(app, "ready", tmp_path)
    assert _start(launcher, tmp_path, proj).returncode == 0
    ((rel, (old, new)),) = SYNC_MISS[app.folder]
    write(proj / rel, read(proj / rel).replace(old, new))
    reason = _block(_stop(launcher, tmp_path, proj))
    assert "update prototype screen settings" in reason and "--approve settings" in reason


# ---------------------------------------------------------------- the prototype in a browser (headless)


@pytest.fixture(scope="module")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("requires Playwright")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


_SHOWN = """(id) => [...document.querySelectorAll('#pp-frame > [data-screen="' + id + '"]')]
    .filter(s => !s.hidden && s.offsetParent !== null)
    .map(s => [...s.querySelectorAll('[data-state]')].filter(e => e.offsetParent !== null).map(e => e.dataset.state))"""


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_screen_and_state_renders_in_the_prototype(browser, app, tmp_path, scheme):
    proj = project(app, "ready", tmp_path)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme=scheme)
    page = ctx.new_page()
    problems: list = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(str(e)))
    page.on("request", lambda req: problems.append(req.url)
            if not req.url.startswith(("file:", "data:", "about:")) else None)
    try:
        page.goto((proj / DOCS / "prototype.html").resolve().as_uri())
        page.wait_for_load_state("load")
        assert page.evaluate("document.documentElement.dataset.theme") == scheme
        primary = json.loads(read(proj / app.tokens))["color"]["primary"]
        expected = primary["$extensions"]["plumb"]["dark"] if scheme == "dark" else primary["$value"]
        value = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--color-primary').trim()")
        assert value.lower() == expected.lower(), (value, expected)
        for screen in app.screens:
            page.click(f'.pp-nav [data-nav="{screen.id}"]')
            for state in screen.states:
                if len(screen.states) > 1:
                    page.click(f'[data-states-for="{screen.id}"] [data-set-state="{state}"]')
                shown = page.evaluate(_SHOWN, screen.id)
                assert shown == [[state]], (screen.id, state, shown)
        assert problems == [], problems
    finally:
        ctx.close()
