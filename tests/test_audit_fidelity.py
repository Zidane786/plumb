"""audit.py prototype fidelity: screens.json and the screen files against the routes and the code.

Two fixture projects (tests/fixtures/projects/fidelity/next and .../angular) hold a clean baseline: every route has a
screen, every screen is built, approved and in step with its source files (screens.json was written by
build-prototype.py --map and --approve). Each test copies one into a folder with a non-ASCII name, breaks one thing, and
checks that the one rule reports it at the right file:line with the right severity, and that the baseline (the passing
case) reports nothing. Both projects use Unicode screen ids (menü, réglages).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import time
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "plugins/plumb/assets/skill/scripts"
TEMPLATES = REPO / "plugins/plumb/assets/skill/templates"
WEB_TEMPLATES = REPO / "plugins/plumb/assets/skill/assets/platforms/web"
FIXTURES = REPO / "tests/fixtures/projects/fidelity"
SKILL_REL = ".claude/skills/demo-design-system"
SCREENS = "docs/design/prototype/screens"
MAP = "docs/design/prototype/screens.json"
BP_CMD = f"python3 {SKILL_REL}/scripts/build-prototype.py"

FIDELITY = {"route-not-prototyped": "error", "screen-drift": "error", "screen-unapproved": "error",
            "screen-not-built": "warn", "state-missing-in-code": "warn", "synced-from-code": "warn",
            "copy-missing-in-code": "suggest", "missing-state": "suggest", "no-prototype": "warn",
            "component-missing-in-code": "suggest"}
FRAMEWORKS = ("next", "angular")
UNICODE_ID = {"next": "menü", "angular": "réglages"}


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A = _load("plumb_audit", "audit.py")


# ---------------------------------------------------------------- helpers


def write(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def make_project(tmp: Path, fw: str, crlf: bool = False) -> Path:
    dest = tmp / "Café Ünïcode" / fw
    for src in sorted((FIXTURES / fw).rglob("*")):
        if src.is_file():
            write(dest / src.relative_to(FIXTURES / fw), read(src), "\r\n" if crlf else "\n")
    scripts = dest / SKILL_REL / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ("_plumb.py", "audit.py", "build-tokens.py", "build-prototype.py"):
        shutil.copy(SCRIPTS / name, scripts / name)
    return dest


def add_prototype_tooling(project: Path) -> None:
    """Tokens and templates, so build-prototype.py itself can run in the project (--approve, --synced)."""
    skill = project / SKILL_REL
    shutil.copytree(TEMPLATES, skill / "templates", dirs_exist_ok=True)
    write(skill / "assets/tokens/demo.tokens.json", read(REPO / "tests/fixtures/pages/tokens.json"))
    write(skill / "assets/platforms/web/tokens.css.template", read(WEB_TEMPLATES / "tokens.css.template.tailwind-v4"))


def run(project: Path, *args: str, script: str = "audit.py"):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CEILING_DIRECTORIES": str(project.parent), "USER": "tester"})
    return subprocess.run([sys.executable, str(project / SKILL_REL / "scripts" / script), *args], cwd=str(project),
                          capture_output=True, text=True, encoding="utf-8", env=env)


def audit(project: Path, *args: str) -> dict:
    r = run(project, "--json", *args)
    assert r.returncode in (0, 1), r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    out = json.loads(r.stdout)
    out["_code"], out["_stderr"] = r.returncode, r.stderr
    return out


def fidelity(out: dict, rule: str = None) -> list:
    return [f for f in out["findings"] if f["rule"] in FIDELITY and (rule is None or f["rule"] == rule)]


def where(out: dict, rule: str) -> list:
    return sorted((f["file"], f["line"]) for f in fidelity(out, rule))


def line_of(path: Path, needle: str) -> int:
    for i, line in enumerate(read(path).splitlines(), 1):
        if needle in line:
            return i
    raise AssertionError(f"{needle!r} not in {path}")


def edit(path: Path, old: str, new: str) -> None:
    text = read(path)
    assert old in text, (old, path)
    write(path, text.replace(old, new, 1))


def edit_map(project: Path, sid: str, **changes) -> None:
    data = json.loads(read(project / MAP))
    for s in data["screens"]:
        if s["id"] == sid:
            s.update(changes)
    write(project / MAP, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def screen_file(project: Path, sid: str) -> Path:
    return project / SCREENS / f"{sid}.html"


def screen_rel(sid: str) -> str:
    return f"{SCREENS}/{sid}.html"


def section_line(project: Path, sid: str) -> int:
    return line_of(screen_file(project, sid), "data-screen=")


def assert_shape(findings: list) -> None:
    for f in findings:
        assert f["severity"] == FIDELITY[f["rule"]] or f["rule"] in ("route-not-prototyped", "screen-drift",
                                                                      "screen-unapproved"), f
        assert f["message"] and f["fix"], f


# ---------------------------------------------------------------- the rule table


def test_fidelity_rules_are_cross_rules_in_the_one_table() -> None:
    rules = {r.id: r for r in A.RULES}
    for rule_id, severity in FIDELITY.items():
        assert rule_id in rules, rule_id
        assert rules[rule_id].kind == "cross" and rules[rule_id].severity == severity, rule_id
        assert rules[rule_id].message and rules[rule_id].fix
    for rule_id in ("copy-missing-in-code", "missing-state", "component-missing-in-code"):
        assert rules[rule_id].why and rules[rule_id].weight >= 1


# ---------------------------------------------------------------- the passing case: the clean baseline


@pytest.mark.parametrize("crlf", [False, True], ids=["lf", "crlf"])
@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_clean_baseline_reports_no_fidelity_finding(fw: str, crlf: bool, tmp_path: Path) -> None:
    project = make_project(tmp_path, fw, crlf=crlf)
    out = audit(project)
    assert fidelity(out) == [], [(f["rule"], f["file"], f["line"], f["message"]) for f in fidelity(out)]
    assert "build-prototype" not in out["_stderr"]


def test_no_prototype_with_sync_on_is_one_notice_on_the_plumb_md_line(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    shutil.rmtree(project / "docs")
    write(project / "app/billing/page.tsx", "export default function Billing() {\n  return <h1>Billing</h1>;\n}\n")
    out = audit(project)
    assert [(f["rule"], f["file"], f["line"], f["severity"]) for f in fidelity(out)] == [
        ("no-prototype", "PLUMB.md", line_of(project / "PLUMB.md", "Prototype sync:"), "warn")]
    f = fidelity(out)[0]
    assert f["message"].startswith("no prototype yet: run /plumb:extract or /plumb:prototype")
    assert "Prototype sync: off" in f["fix"]
    assert out["_code"] == 0


@pytest.mark.parametrize("plumb_md", ["sync off", "no sync line"])
def test_no_prototype_with_sync_off_is_silent(plumb_md: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    shutil.rmtree(project / "docs")
    if plumb_md == "sync off":
        edit(project / "PLUMB.md", "Prototype sync: on", "Prototype sync: off")
    else:
        write(project / "PLUMB.md", "Project: demo\n")
    write(project / "app/billing/page.tsx", NEW_PAGE)
    out = audit(project)
    assert fidelity(out) == []
    assert out["_code"] == 0


# ---------------------------------------------------------------- screen-not-built


@pytest.mark.parametrize("fw,gone", [("next", "app/menu"), ("angular", "src/app/settings")])
def test_screen_whose_route_files_are_gone_is_not_built(fw: str, gone: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, fw)
    shutil.rmtree(project / gone)
    sid = UNICODE_ID[fw]
    out = audit(project)
    assert where(out, "screen-not-built") == [(screen_rel(sid), section_line(project, sid))]
    f = fidelity(out, "screen-not-built")[0]
    assert f["severity"] == "warn" and sid in f["message"]
    assert f"{BP_CMD} --map {sid}" in f["fix"]
    assert_shape(fidelity(out))
    assert where(out, "screen-drift") == []  # nothing built yet: not drift
    assert out["_code"] == (1 if any(f["severity"] == "error" for f in out["findings"]) else 0)


def test_new_screen_file_with_no_map_entry_is_to_build(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(screen_file(project, "billing"), '<section data-screen="billing" data-title="Billing">\n'
                                           '  <div data-state="ready"><h1>Billing</h1></div>\n</section>\n')
    out = audit(project)
    assert where(out, "screen-not-built") == [(screen_rel("billing"), 1)]
    f = fidelity(out, "screen-not-built")[0]
    assert "no route" in f["message"]
    assert f"{BP_CMD} --map billing --route=" in f["fix"]


# ---------------------------------------------------------------- route-not-prototyped


NEW_PAGE = "export default function BillingPage() {\n  return <h1>Billing</h1>;\n}\n"


@pytest.mark.parametrize("sync,severity", [("on", "error"), ("off", "warn")])
def test_next_page_with_no_screen_is_not_prototyped(sync: str, severity: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit(project / "PLUMB.md", "Prototype sync: on", f"Prototype sync: {sync}")
    write(project / "app/(shop)/billing/page.tsx", NEW_PAGE)
    out = audit(project)
    assert where(out, "route-not-prototyped") == [("app/(shop)/billing/page.tsx", 1)]
    f = fidelity(out, "route-not-prototyped")[0]
    assert f["severity"] == severity
    assert "/billing" in f["message"] and "not prototyped" in f["message"]
    assert "/plumb:prototype billing" in f["fix"] and f"{BP_CMD} --map billing --route=/billing" in f["fix"]
    assert out["_code"] == (1 if severity == "error" else 0)


def test_dynamic_route_is_quoted_in_the_fix(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(project / "app/invoices/[invoiceId]/page.tsx", NEW_PAGE)
    out = audit(project)
    f = fidelity(out, "route-not-prototyped")[0]
    assert (f["file"], f["line"]) == ("app/invoices/[invoiceId]/page.tsx", 1)
    assert '--route="/invoices/[invoiceId]" --files "app/invoices/[invoiceId]/page.tsx"' in f["fix"]
    assert "/plumb:prototype invoices" in f["fix"]


def test_no_prototype_sync_line_means_warn(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(project / "PLUMB.md", "Project: demo\nRoutes: app (next-app)\n")
    write(project / "app/billing/page.tsx", NEW_PAGE)
    out = audit(project)
    assert [f["severity"] for f in fidelity(out, "route-not-prototyped")] == ["warn"]


def test_routes_not_recorded_skips_route_not_prototyped_with_a_note(tmp_path: Path) -> None:
    """Scripts never guess the app's layout: with no `Routes:` in PLUMB.md (a project set up before it existed) the
    rule is skipped and the audit says why, instead of reading next.config.* or package.json."""
    project = make_project(tmp_path, "next")
    edit(project / "PLUMB.md", "Routes: app (next-app)\n", "")
    write(project / "app/billing/page.tsx", NEW_PAGE)
    out = audit(project)
    assert fidelity(out, "route-not-prototyped") == []
    assert "note: Routes not recorded: run /plumb:init to record them" in out["_stderr"]
    edit(project / "PLUMB.md", "Platforms: web\n", "Platforms: web\nRoutes: app (next-app)\n")
    out = audit(project)
    assert where(out, "route-not-prototyped") == [("app/billing/page.tsx", 1)]
    assert "Routes not recorded" not in out["_stderr"]


def test_monorepo_frontend_page_is_not_prototyped(tmp_path: Path) -> None:
    """The live-test monorepo: the design system at the repo root, Next.js only in frontend/ (its own package.json and
    next.config), Python in backend/. The recorded root finds the new page; UI files are repo-relative."""
    project = make_project(tmp_path, "next")
    for name in list((project / "app").rglob("*")) + [project / "next.config.mjs"]:
        if name.is_file():
            dest = project / "frontend/src" / name.relative_to(project) if name.suffix != ".mjs" else project / "frontend" / name.name
            write(dest, read(name))
            name.unlink()
    shutil.rmtree(project / "app")
    write(project / "backend/main.py", "print('api')\n")
    write(project / "frontend/package.json", '{"dependencies": {"next": "16.0.0"}}\n')
    for p in (project / "docs/design/prototype/screens.json",):
        write(p, read(p).replace('"app/', '"frontend/src/app/'))
    edit(project / "PLUMB.md", "Routes: app (next-app)\n", "Routes: frontend/src/app (next-app)\n")
    write(project / "frontend/src/app/usage-reports/page.tsx", NEW_PAGE)
    out = audit(project)
    assert where(out, "route-not-prototyped") == [("frontend/src/app/usage-reports/page.tsx", 1)]


@pytest.mark.parametrize("sync,severity", [("on", "error"), ("off", "warn")])
def test_angular_route_with_no_screen_is_not_prototyped(sync: str, severity: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, "angular")
    edit(project / "PLUMB.md", "Prototype sync: on", f"Prototype sync: {sync}")
    routes = project / "src/app/app.routes.ts"
    edit(routes, "import { BookingComponent }", "import { BillingComponent } from './billing/billing.component';\n"
                                                "import { BookingComponent }")
    edit(routes, "  { path: '**'", "  { path: 'billing', component: BillingComponent },\n  { path: '**'")
    write(project / "src/app/billing/billing.component.ts",
          "import { Component } from '@angular/core';\n\n@Component({ selector: 'app-billing', standalone: true, "
          "template: '<h1>Billing</h1>' })\nexport class BillingComponent {}\n")
    out = audit(project)
    assert where(out, "route-not-prototyped") == [("src/app/app.routes.ts", line_of(routes, "path: 'billing'"))]
    f = fidelity(out, "route-not-prototyped")[0]
    assert f["severity"] == severity
    assert "/billing" in f["message"] and "src/app/billing/billing.component.ts" in f["message"]


def test_a_route_mapped_by_route_name_alone_is_prototyped(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(project / "app/bookings/[id]/page.tsx", NEW_PAGE)
    write(screen_file(project, "booking-details"), '<section data-screen="booking-details" data-title="Booking">\n'
                                                   '  <div data-state="ready"><p>Booking</p></div>\n</section>\n')
    data = json.loads(read(project / MAP))
    data["screens"].append({"id": "booking-details", "title": "Booking", "states": ["ready"], "route": "/bookings/:id",
                            "files": [], "files_hash": None, "approved": None, "synced_from_code": False,
                            "status": "to-build"})
    write(project / MAP, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    out = audit(project)
    assert where(out, "route-not-prototyped") == []


# ---------------------------------------------------------------- screen-drift


@pytest.mark.parametrize("fw,sid,source", [("next", "booking", "components/booking-form.tsx"),
                                           ("angular", "home", "src/app/home/home.component.ts"),
                                           ("next", "menü", "app/menu/page.tsx")])
def test_source_changed_after_approval_is_drift(fw: str, sid: str, source: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, fw)
    write(project / source, read(project / source) + "\nexport const changed = true;\n")
    out = audit(project)
    assert where(out, "screen-drift") == [(screen_rel(sid), section_line(project, sid))]
    f = fidelity(out, "screen-drift")[0]
    assert f["severity"] == "error"
    assert f"update prototype screen {sid}" in f["message"] or f"update prototype screen {sid}" in f["fix"]
    assert f"{BP_CMD} --approve {sid}" in f["fix"]
    assert out["_code"] == 1
    assert where(out, "screen-unapproved") == []


def test_crlf_only_change_is_not_drift(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    path = project / "components/booking-form.tsx"
    write(path, read(path), "\r\n")
    assert where(audit(project), "screen-drift") == []


def test_approving_again_clears_the_drift(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    add_prototype_tooling(project)
    write(project / "components/booking-form.tsx", read(project / "components/booking-form.tsx") + "\n// reviewed\n")
    out = audit(project)
    assert where(out, "screen-drift")
    r = run(project, "--approve", "booking", script="build-prototype.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert where(audit(project), "screen-drift") == []


def test_built_screen_with_no_source_baseline_is_a_drift_warning(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit_map(project, "booking", files_hash=None)
    out = audit(project)
    found = fidelity(out, "screen-drift")
    assert [(f["file"], f["severity"]) for f in found] == [(screen_rel("booking"), "warn")]
    assert "baseline" in found[0]["message"] and f"--approve booking" in found[0]["fix"]


# ---------------------------------------------------------------- screen-unapproved


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_screen_file_changed_after_approval_is_unapproved(fw: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, fw)
    sid = UNICODE_ID[fw]
    path = screen_file(project, sid)
    edit(path, "<div data-state=\"ready\">", "<div data-state=\"ready\">\n    <p>New line</p>")
    out = audit(project)
    assert where(out, "screen-unapproved") == [(screen_rel(sid), section_line(project, sid))]
    f = fidelity(out, "screen-unapproved")[0]
    assert f["severity"] == "error" and "fixture" in f["message"] and "2026-10-12" in f["message"]
    assert f"{BP_CMD} --approve {sid}" in f["fix"]
    assert where(out, "screen-drift") == []
    assert out["_code"] == 1


@pytest.mark.parametrize("fw,gone", [("next", "app/menu"), ("angular", "src/app/settings")])
def test_screen_changed_after_approval_but_not_built_is_a_warning(fw: str, gone: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, fw)
    sid = UNICODE_ID[fw]
    shutil.rmtree(project / gone)
    edit(screen_file(project, sid), "<div data-state=\"ready\">", "<div data-state=\"ready\">\n    <p>New line</p>")
    out = audit(project)
    found = fidelity(out, "screen-unapproved")
    assert [(f["file"], f["line"], f["severity"]) for f in found] == [(screen_rel(sid), section_line(project, sid), "warn")]
    assert "awaiting approval again: don't build from it yet" in found[0]["message"]
    assert f"{BP_CMD} --approve {sid}" in found[0]["fix"]


def test_never_approved_screen_with_changed_code_is_unapproved(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit_map(project, "booking", approved=None)
    write(project / "components/booking-form.tsx", read(project / "components/booking-form.tsx") + "\n// more\n")
    out = audit(project)
    assert where(out, "screen-unapproved") == [(screen_rel("booking"), section_line(project, "booking"))]
    assert "never approved" in fidelity(out, "screen-unapproved")[0]["message"]
    assert where(out, "screen-drift") == []


def test_never_approved_screen_with_unchanged_code_is_not_reported(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit_map(project, "booking", approved=None)
    assert where(audit(project), "screen-unapproved") == []


# ---------------------------------------------------------------- state-missing-in-code


def test_next_empty_state_missing_in_code(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    page = project / "app/page.tsx"
    edit(page, 'import { EmptyState } from "@/components/empty-state";\n', "")
    edit(page, '  if (tables.length === 0) {\n    return <EmptyState title="No tables booked yet" />;\n  }\n', "")
    out = audit(project)
    path = screen_file(project, "home")
    assert where(out, "state-missing-in-code") == [(screen_rel("home"), line_of(path, 'data-state="empty"'))]
    f = fidelity(out, "state-missing-in-code")[0]
    assert f["severity"] == "warn" and "empty" in f["message"] and "app/page.tsx" in f["message"]


def test_next_loading_state_missing_in_code(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    form = project / "components/booking-form.tsx"
    edit(form, "{status === \"saving\" ? <Spinner /> : \"Confirm booking\"}", "Confirm booking")
    edit(form, 'import { Spinner } from "@/components/ui/spinner";\n', "")
    write(form, read(form).replace('"saving"', '"sent"'))
    out = audit(project)
    path = screen_file(project, "booking")
    assert where(out, "state-missing-in-code") == [(screen_rel("booking"), line_of(path, 'data-state="loading"'))]


@pytest.mark.parametrize("special", ["app/loading.tsx", "app/(shop)/loading.tsx", "app/(shop)/booking/loading.tsx"])
def test_next_loadingtsx_beside_or_above_the_page_handles_loading(special: str, tmp_path: Path) -> None:
    """booking's own files lose every loading branch; Next.js shows loading.tsx from the page's folder or any folder
    above it up to app/, so that file is the loading state."""
    project = make_project(tmp_path, "next")
    form = project / "components/booking-form.tsx"
    edit(form, "{status === \"saving\" ? <Spinner /> : \"Confirm booking\"}", "Confirm booking")
    edit(form, 'import { Spinner } from "@/components/ui/spinner";\n', "")
    write(form, read(form).replace('"saving"', '"sent"'))
    assert where(audit(project), "state-missing-in-code")  # the failing case first
    write(project / special, 'export default function Loading() {\n  return <TableList.Skeleton />;\n}\n')
    assert where(audit(project), "state-missing-in-code") == []


def test_next_error_tsx_handles_the_error_state_of_a_page_mapped_alone(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit_map(project, "booking", files=["app/(shop)/booking/page.tsx"], files_hash=None)
    out = audit(project)
    states = [f["message"].split()[1] for f in fidelity(out, "state-missing-in-code")]
    assert "error" in states
    write(project / "app/(shop)/booking/error.tsx", '"use client";\nexport default function Failed() {\n'
                                                    '  return <p>We could not save the booking</p>;\n}\n')
    states = [f["message"].split()[1] for f in fidelity(audit(project), "state-missing-in-code")]
    assert "error" not in states and "loading" in states


def test_state_families_and_synonyms() -> None:
    assert A.state_handled("no-results", "if (items.length === 0) return null;")
    assert A.state_handled("no-data", "<EmptyState />")
    assert A.state_handled("empty-search", "const isEmpty = true;")
    assert A.state_handled("not-found", "if (isError) return <ErrorState />;")
    assert A.state_handled("not-found", "notFound();")
    assert A.state_handled("timeout", "{status === 'error' && <Retry />}")
    assert not A.state_handled("timeout", "return <Table />;")
    assert not A.state_handled("no-results", "return <Table rows={rows} />;")


def test_angular_empty_state_missing_in_template(tmp_path: Path) -> None:
    project = make_project(tmp_path, "angular")
    edit(project / "src/app/home/home.component.html",
         '} @else if (tables().length === 0) {\n  <app-empty-state title="No tables booked yet" />\n', "")
    edit(project / "src/app/home/home.component.ts", "import { EmptyStateComponent } from '../shared/empty-state.component';\n", "")
    edit(project / "src/app/home/home.component.ts", "imports: [EmptyStateComponent, SkeletonComponent]",
         "imports: [SkeletonComponent]")
    out = audit(project)
    path = screen_file(project, "home")
    assert where(out, "state-missing-in-code") == [(screen_rel("home"), line_of(path, 'data-state="empty"'))]


def test_angular_template_url_is_followed_for_states(tmp_path: Path) -> None:
    """booking is mapped to its .ts only; the states live in the templateUrl file."""
    project = make_project(tmp_path, "angular")
    assert where(audit(project), "state-missing-in-code") == []
    template = project / "src/app/booking/booking.component.html"
    edit(template, '  <ng-container *ngTemplateOutlet="errorTpl" />\n', '  <p role="alert">Try again</p>\n')
    edit(template, '<ng-template #errorTpl><p role="alert">We could not save the booking</p></ng-template>\n', "")
    out = audit(project)
    path = screen_file(project, "booking")
    assert where(out, "state-missing-in-code") == [(screen_rel("booking"), line_of(path, 'data-state="error"'))]


def test_angular_unicode_screen_error_state_missing(tmp_path: Path) -> None:
    project = make_project(tmp_path, "angular")
    path = project / "src/app/settings/settings.component.ts"
    edit(path, "    @if (saveFailed) {\n      <p role=\"alert\">Les réglages n’ont pas été enregistrés</p>\n    }\n", "")
    write(path, read(path).replace("saveFailed", "dirty"))
    out = audit(project)
    sid = "réglages"
    assert where(out, "state-missing-in-code") == [(screen_rel(sid), line_of(screen_file(project, sid), 'data-state="error"'))]


# ---------------------------------------------------------------- copy-missing-in-code


@pytest.mark.parametrize("fw,source,old,new", [
    ("next", "components/booking-form.tsx", '"Confirm booking"', '"Book now"'),
    ("angular", "src/app/booking/booking.component.html", ">Confirm booking<", ">Book now<"),
])
def test_button_label_missing_in_code(fw: str, source: str, old: str, new: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, fw)
    edit(project / source, old, new)
    out = audit(project)
    path = screen_file(project, "booking")
    assert where(out, "copy-missing-in-code") == [(screen_rel("booking"), line_of(path, "Confirm booking"))]
    f = fidelity(out, "copy-missing-in-code")[0]
    assert f["severity"] == "suggest" and "Confirm booking" in f["message"]


def test_unicode_heading_missing_in_code(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit(project / "app/menu/page.tsx", "<h1>Menü du jour</h1>", "<h1>Menu of the day</h1>")
    out = audit(project)
    sid = "menü"
    assert where(out, "copy-missing-in-code") == [(screen_rel(sid), line_of(screen_file(project, sid), "<h1>Menü du jour"))]


def test_copy_in_other_states_is_not_required(tmp_path: Path) -> None:
    """Only the default (first) state and the shared content are compared: the loading button says Saving…"""
    project = make_project(tmp_path, "next")
    assert "Saving" not in read(project / "components/booking-form.tsx")
    assert where(audit(project), "copy-missing-in-code") == []


# ---------------------------------------------------------------- synced-from-code


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_synced_from_code_is_listed_to_confirm(fw: str, tmp_path: Path) -> None:
    project = make_project(tmp_path, fw)
    sid = UNICODE_ID[fw]
    edit_map(project, sid, synced_from_code=True, approved=None)
    out = audit(project)
    assert where(out, "synced-from-code") == [(screen_rel(sid), section_line(project, sid))]
    f = fidelity(out, "synced-from-code")[0]
    assert f["severity"] == "warn" and "confirm" in (f["message"] + f["fix"]).lower()
    assert f"{BP_CMD} --approve {sid}" in f["fix"]
    assert f["fix"].startswith("ask the user: ") and "Only after their yes to that screen" in f["fix"]
    assert out["_code"] == 0
    assert where(out, "screen-unapproved") == [] and where(out, "screen-drift") == []


def test_synced_screen_whose_code_changed_since_is_drift(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit_map(project, "booking", synced_from_code=True, approved=None)
    write(project / "components/booking-form.tsx", read(project / "components/booking-form.tsx") + "\n// more\n")
    out = audit(project)
    assert where(out, "screen-drift") == [(screen_rel("booking"), section_line(project, "booking"))]


# ---------------------------------------------------------------- missing-state (ux.md)


UX_TEMPLATE = REPO / "plugins/plumb/assets/skill/references/ux.md.tmpl"


def filled_ux(lines: str) -> str:
    """The real ux.md template with its "### States per screen" lines filled in."""
    text = read(UX_TEMPLATE)
    marker = "a screen not listed is not checked.\n"
    assert marker in text
    return text.replace(marker, marker + "\n" + lines, 1)


def test_ux_template_states_table_is_the_catalogue_and_lists_no_screen() -> None:
    ux = A.ux_states(read(UX_TEMPLATE))
    assert ux.catalogue == ["loading", "empty", "error", "success", "disabled", "long-text", "zero-and-one", "offline"]
    assert ux.per_screen == {} and ux.exempt == {}
    assert A.UX_PER_SCREEN in read(UX_TEMPLATE)


def test_ux_states_per_screen_lines_table_and_exemptions() -> None:
    text = filled_ux("- booking: loading, error, success (after saving), offline\n- `Menü`: empty\n"
                     "- settings: none (a static form)\n\n| Screen | States |\n|---|---|\n| home | loading, empty |\n"
                     "| ticket | none: printed only |\n")
    ux = A.ux_states(text)
    assert ux.per_screen == {"booking": ["loading", "error", "success", "offline"], "menü": ["empty"], "settings": [],
                             "home": ["loading", "empty"], "ticket": []}
    assert ux.exempt == {"settings": "a static form", "ticket": "printed only"}
    assert len(ux.catalogue) == 8


def test_template_ux_md_gives_no_missing_state(tmp_path: Path) -> None:
    """The template's "every screen has all that apply" catalogue is not a requirement: no noise."""
    project = make_project(tmp_path, "next")
    write(project / SKILL_REL / "references/ux.md", read(UX_TEMPLATE))
    assert where(audit(project), "missing-state") == []


def test_ux_md_state_missing_from_a_listed_screen_is_a_suggestion(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(project / SKILL_REL / "references/ux.md",
          filled_ux("- booking: loading, error, success, offline\n- Menü: empty, loading\n- home: none (a summary)\n"))
    out = audit(project)
    got = {f["file"]: f for f in fidelity(out, "missing-state")}
    assert sorted(got) == [screen_rel("booking"), screen_rel("menü")]
    assert "has no offline state," in got[screen_rel("booking")]["message"]
    assert "has no loading state," in got[screen_rel("menü")]["message"]
    for f in got.values():
        assert f["severity"] == "suggest" and f["line"] == section_line(project, Path(f["file"]).stem)
        assert "references/ux.md" in f["message"] and "### States per screen" in f["fix"]
        assert "none (reason)" in f["fix"]
    assert out["_code"] == 0


def test_ux_md_exemption_clears_the_suggestion(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(project / SKILL_REL / "references/ux.md", filled_ux("- booking: none (offline is handled app-wide)\n"))
    assert where(audit(project), "missing-state") == []


# ---------------------------------------------------------------- component-missing-in-code


def test_components_named_by_the_screen_are_looked_for_in_code(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    path = screen_file(project, "home")
    edit(path, "    <ul>\n", '    <ul data-component="TableList">\n')
    edit(path, '    <p>No tables booked yet</p>', '    <div data-component="empty-state"><p>No tables booked yet</p></div>\n'
                                                  '    <div data-component="DatePicker"></div>')
    out = audit(project)
    assert where(out, "component-missing-in-code") == [(screen_rel("home"), line_of(path, "DatePicker"))]
    f = fidelity(out, "component-missing-in-code")[0]
    assert f["severity"] == "suggest" and "DatePicker" in f["message"] and "app/page.tsx" in f["message"]
    assert f"{BP_CMD} --approve home" in f["fix"]


def test_screen_without_data_component_is_not_compared(tmp_path: Path) -> None:
    project = make_project(tmp_path, "angular")
    assert "data-component" not in read(screen_file(project, "booking"))
    assert where(audit(project), "component-missing-in-code") == []


# ---------------------------------------------------------------- bad input


def test_broken_screens_json_exits_2_naming_the_file(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(project / MAP, "{ not json\n")
    r = run(project)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "error: " in r.stderr and "\nfix: " in r.stderr and MAP in r.stderr
    assert "Traceback" not in r.stderr


def test_screen_file_with_no_state_exits_2_naming_the_file(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(screen_file(project, "home"), '<section data-screen="home" data-title="Home">\n  <p>Hi</p>\n</section>\n')
    r = run(project)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "home.html" in r.stderr and "data-state" in r.stderr and "\nfix: " in r.stderr
    assert "Traceback" not in r.stderr


def test_unsafe_glob_in_screens_json_exits_2(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit_map(project, "booking", files=["../outside/**"])
    r = run(project)
    assert r.returncode == 2 and "error: " in r.stderr and "\nfix: " in r.stderr, r.stderr


def test_an_unexpected_failure_names_the_screen_file(tmp_path: Path, monkeypatch, capsys) -> None:
    project = make_project(tmp_path, "next")

    def broken(self, s):
        raise KeyError("files")

    monkeypatch.setattr(A.Fidelity, "code_changed", broken)
    code = A.main(["--json", "--root", str(project / SKILL_REL)])
    err = capsys.readouterr().err
    assert code == 2, err
    assert "error: the prototype fidelity check failed on docs/design/prototype/screens/" in err
    assert "unexpected token structure" not in err and "\nfix: " in err


def test_missing_build_prototype_skips_with_a_note(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    (project / SKILL_REL / "scripts/build-prototype.py").unlink()
    write(project / "app/billing/page.tsx", NEW_PAGE)
    out = audit(project)
    assert fidelity(out) == []
    assert "build-prototype.py" in out["_stderr"] and "skipped" in out["_stderr"]


# ---------------------------------------------------------------- PATHS


def test_paths_limit_routes_to_the_audited_files_but_screens_are_all_checked(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    write(project / "app/billing/page.tsx", NEW_PAGE)
    write(project / "components/booking-form.tsx", read(project / "components/booking-form.tsx") + "\n// changed\n")
    out = audit(project, "app/menu")
    assert where(out, "route-not-prototyped") == []  # app/billing was not audited
    assert where(out, "screen-drift") == [(screen_rel("booking"), section_line(project, "booking"))]
    out = audit(project, "app/billing")
    assert where(out, "route-not-prototyped") == [("app/billing/page.tsx", 1)]
    assert where(out, "screen-drift") == [(screen_rel("booking"), section_line(project, "booking"))]


# ---------------------------------------------------------------- route discovery (pure)


def routes(tmp_path: Path, files: dict, recorded: str = "") -> list:
    """The routes discover_routes finds in files, reading only PLUMB.md's `Routes:` value (recorded)."""
    for name, text in files.items():
        write(tmp_path / name, text)
    roots = A.route_roots({"Routes": recorded})
    found = A.discover_routes(tmp_path, [(name, text) for name, text in files.items()], roots)
    return sorted((r.route, r.file, r.line, r.source) for r in found)


def test_next_app_router_routes(tmp_path: Path) -> None:
    files = {
        "app/page.tsx": "", "app/layout.tsx": "", "app/(marketing)/about/page.tsx": "",
        "src/app/blog/[slug]/page.jsx": "", "app/_private/secret/page.tsx": "", "app/@modal/login/page.tsx": "",
        "app/api/route.ts": "", "app/settings/loading.tsx": "",
    }
    write(tmp_path / "next/next.config.js", "module.exports = {};\n")  # a Next project, but nothing recorded
    assert routes(tmp_path / "next", files) == []
    assert routes(tmp_path / "next", files, "(not recorded yet)") == []
    assert routes(tmp_path / "next", files, "none") == []
    assert routes(tmp_path / "rec", files, "app (next-app), src/app (next-app)") == [
        ("/", "app/page.tsx", 1, "app/page.tsx"),
        ("/about", "app/(marketing)/about/page.tsx", 1, "app/(marketing)/about/page.tsx"),
        ("/blog/[slug]", "src/app/blog/[slug]/page.jsx", 1, "src/app/blog/[slug]/page.jsx"),
        ("/login", "app/@modal/login/page.tsx", 1, "app/@modal/login/page.tsx"),
    ]


def test_monorepo_frontend_routes_come_from_the_recorded_root(tmp_path: Path) -> None:
    """A monorepo: Next.js in frontend/ (no next.config or next dependency at the repo root), Python in backend/."""
    files = {"frontend/src/app/page.tsx": "", "frontend/src/app/usage-reports/page.tsx": "",
             "frontend/src/app/(dash)/keys/[id]/page.tsx": "", "backend/app/page.py": "", "app/page.tsx": ""}
    assert routes(tmp_path, files) == []
    assert [r[0] for r in routes(tmp_path, files, "frontend/src/app (next-app)")] == [
        "/", "/keys/[id]", "/usage-reports"]


def test_next_pages_router_routes_only_when_recorded(tmp_path: Path) -> None:
    files = {"pages/index.tsx": "", "pages/bookings/[id].tsx": "", "pages/_app.tsx": "", "pages/_document.tsx": "",
             "pages/api/hello.ts": "", "pages/settings/index.jsx": ""}
    assert routes(tmp_path / "plain", files) == []
    assert [r[0] for r in routes(tmp_path / "next", files, "pages (next-pages)")] == ["/", "/bookings/[id]", "/settings"]


def test_sveltekit_and_nuxt_file_routes(tmp_path: Path) -> None:
    files = {"src/routes/+page.svelte": "", "src/routes/(app)/settings/+page.svelte": "",
             "src/routes/+layout.svelte": "", "pages/about.vue": "", "pages/index.vue": ""}
    assert [r[0] for r in routes(tmp_path / "nuxt", files, "src/routes (sveltekit), pages (nuxt)")] == ["/", "/", "/about",
                                                                                           "/settings"]
    assert [r[0] for r in routes(tmp_path / "svelte", files, "src/routes (sveltekit)")] == ["/", "/settings"]


def test_routes_setting_parses_paths_kinds_and_problems() -> None:
    parse = A.P.parse_routes
    assert parse("") == (None, []) and parse(None) == (None, [])
    assert parse("(not recorded yet: /plumb:init records them)") == (None, [])
    assert parse("none") == ([], [])
    assert parse("./frontend/src/app/ (next-app), src\\app\\app.routes.ts (angular), web/src/routes (sveltekit), "
                 "src/router/index.ts (router), site/pages (nuxt), old/pages (next-pages)") == (
        [("frontend/src/app", "next-app"), ("src/app/app.routes.ts", "angular"), ("web/src/routes", "sveltekit"),
         ("src/router/index.ts", "router"), ("site/pages", "nuxt"), ("old/pages", "next-pages")], [])
    # the kind is never guessed from the folder name
    roots, problems = parse("frontend/src/app, ../x/app (next-app), /abs/app (next-app), frontend/pages (remix), "
                            "web/app (next-app)")
    assert roots == [("web/app", "next-app")]
    assert problems[0] == ("Routes: frontend/src/app has no kind \u2014 use one of next-app, next-pages, nuxt, "
                           "sveltekit, angular, router, as frontend/src/app (<kind>)")
    assert "not a path inside the project" in problems[1] and "not a path inside the project" in problems[2]
    assert problems[3].startswith("Routes: frontend/pages has the unknown kind (remix)")


def test_an_entry_without_a_kind_is_skipped_with_a_note(tmp_path: Path) -> None:
    project = make_project(tmp_path, "next")
    edit(project / "PLUMB.md", "Routes: app (next-app)", "Routes: app")
    write(project / "app/billing/page.tsx", NEW_PAGE)
    out = audit(project)
    assert fidelity(out, "route-not-prototyped") == []
    assert "note: Routes: app has no kind" in out["_stderr"]


def test_plain_vue_app_with_components_in_src_pages_has_no_route_findings(tmp_path: Path) -> None:
    """A Vue + vue-router app keeps page components in src/pages/; only the router config declares routes."""
    project = tmp_path / "Vue Café"
    write(project / "PLUMB.md", "Project: vue\nRoutes: src/router/index.ts (router)\n\n## Prototype\nPrototype sync: on\n")
    write(project / "package.json", '{"dependencies": {"vue": "^3.4.0", "vue-router": "^4.3.0"}}\n')
    write(project / "src/pages/HomePage.vue", "<template>\n  <h1>Home</h1>\n</template>\n")
    write(project / "src/pages/AboutPage.vue", "<template>\n  <h1>About</h1>\n</template>\n")
    write(project / "src/router/index.ts",
          "import { createRouter } from 'vue-router';\nimport HomePage from '../pages/HomePage.vue';\n"
          "import AboutPage from '../pages/AboutPage.vue';\n\nexport default createRouter({\n  routes: [\n"
          "    { path: '/', component: HomePage },\n    { path: '/about', component: AboutPage },\n  ],\n});\n")
    for sid, title in (("home", "Home"), ("about", "About")):
        write(project / SCREENS / f"{sid}.html",
              f'<section data-screen="{sid}" data-title="{title}">\n  <div data-state="ready"><h1>{title}</h1></div>\n'
              f'</section>\n')
    write(project / MAP, json.dumps({"version": 1, "screens": [
        {"id": "home", "title": "Home", "states": ["ready"], "route": "/", "files": ["src/pages/HomePage.vue"],
         "files_hash": None, "approved": None, "synced_from_code": False, "status": "built"},
        {"id": "about", "title": "About", "states": ["ready"], "route": "/about", "files": ["src/pages/AboutPage.vue"],
         "files_hash": None, "approved": None, "synced_from_code": False, "status": "built"}]}, indent=2) + "\n")
    scripts = project / SKILL_REL / "scripts"
    scripts.mkdir(parents=True)
    for name in ("_plumb.py", "audit.py", "build-tokens.py", "build-prototype.py"):
        shutil.copy(SCRIPTS / name, scripts / name)
    assert routes(tmp_path / "plain-vue", {"src/pages/HomePage.vue": ""}, "src/router/index.ts (router)") == []
    out = audit(project)
    assert where(out, "route-not-prototyped") == [], fidelity(out)
    write(project / "src/pages/Settings.vue", "<template>\n  <h1>Settings</h1>\n</template>\n")
    assert where(audit(project), "route-not-prototyped") == []  # a component, not a route


def test_vue_router_routes(tmp_path: Path) -> None:
    write(tmp_path / "src/views/AboutView.vue", "<template><h1>About</h1></template>\n")
    write(tmp_path / "src/views/HomeView.vue", "<template><h1>Home</h1></template>\n")
    text = ("import { createRouter } from 'vue-router';\nimport HomeView from '../views/HomeView.vue';\n\n"
            "export default createRouter({\n  routes: [\n    { path: '/', name: 'home', component: HomeView },\n"
            "    { path: '/about', component: () => import('../views/AboutView.vue') },\n  ],\n});\n")
    assert routes(tmp_path, {"src/router/index.ts": text}) == []  # not recorded: no guessing
    assert routes(tmp_path, {"src/router/index.ts": text}, "src/router/index.ts (router)") == [
        ("/", "src/router/index.ts", 6, "src/views/HomeView.vue"),
        ("/about", "src/router/index.ts", 7, "src/views/AboutView.vue"),
    ]


def test_angular_routes_nested_lazy_and_redirects(tmp_path: Path) -> None:
    project = FIXTURES / "angular"
    text = read(project / "src/app/app.routes.ts")
    found = sorted((r.route, r.file, r.line, r.source) for r in A.discover_routes(project, [("src/app/app.routes.ts", text)],
                                                                         A.route_roots({"Routes": "src/app/*.routes.ts (angular)"})))
    assert found == [
        ("/", "src/app/app.routes.ts", 6, "src/app/home/home.component.ts"),
        ("/account/settings", "src/app/app.routes.ts", 12, "src/app/settings/settings.component.ts"),
        ("/booking", "src/app/app.routes.ts", 7, "src/app/booking/booking.component.ts"),
    ]


def test_a_large_routes_file_is_read_in_linear_time(tmp_path: Path) -> None:
    """4x the routes takes about 4x the time (quadratic would be 16x): self-scaling, so slow machines do not fail it."""
    def timed(n: int) -> float:
        body = "".join(f"  {{ path: 'page-{i}', component: Page{i}Component, data: {{ title: 'Page {i}' }} }},\n"
                       for i in range(n))
        text = (f"import {{ Routes }} from '@angular/router';\nimport {{ Page0Component }} from './pages/page-0';\n"
                f"export const routes: Routes = [\n{body}];\n")
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            found = A.discover_routes(tmp_path, [("src/app/app.routes.ts", text)],
                                      [("src/app/app.routes.ts", "angular")])
            best = min(best, time.perf_counter() - start)
        assert len(found) == n and found[-1].route == f"/page-{n - 1}" and found[-1].line == n + 3
        return best

    small, big = timed(500), timed(2000)
    assert big < max(small, 0.01) * 9, (small, big)


def test_same_route_ignores_param_style_and_trailing_slash() -> None:
    assert A.same_route("/bookings/:id", "/bookings/[id]")
    assert A.same_route("/bookings/[bookingId]/", "/bookings/:id")
    assert A.same_route("/", "")
    assert not A.same_route("/bookings", "/booking")
