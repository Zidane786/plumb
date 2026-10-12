"""The three sample apps under tests/fixtures/apps/, taken through Plumb end to end (test_integration.py,
test_swift_typecheck.py).

Each app is a tiny source tree with deliberate design-system violations. setup() does what /plumb:init and
/plumb:create do with the user's confirmed answers, without npm, Xcode or a network: copy the app to a temp folder,
detect.py (a first guess, confirmed here by the APPS table), scaffold.py with an answers file (placement, UI files,
copies, icons), build-tokens.py. fix() applies the fixes the audit names (token classes, CSS variables, theme values).
prototype() writes one screen file per route and maps and approves each with build-prototype.py.

Built stages are cached per test run and copied for each test, as hook_support.py does.
"""

from __future__ import annotations

import atexit
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "plumb"
APPS_DIR = REPO / "tests" / "fixtures" / "apps"
DETECT = PLUGIN / "scripts" / "detect.py"
SCAFFOLD = PLUGIN / "scripts" / "scaffold.py"
DOCS = "docs/design"
SCREENS = f"{DOCS}/prototype/screens"

ICONS = [
    {"concept": "home", "lucide": "house", "sfSymbol": "house", "materialSymbol": "home"},
    {"concept": "settings", "lucide": "settings", "sfSymbol": "gearshape", "materialSymbol": "settings"},
]


@dataclass
class Screen:
    id: str
    title: str
    route: str
    files: List[str]
    states: Dict[str, str]  # state -> inner HTML

    def html(self, order: int) -> str:
        body = "".join(f'  <div data-state="{s}">\n    {inner}\n  </div>\n' for s, inner in self.states.items())
        return (f'<section data-screen="{self.id}" data-title="{self.title}" data-order="{order}">\n'
                f'{body}</section>\n')


@dataclass
class App:
    folder: str              # tests/fixtures/apps/<folder>
    slug: str                # the project name detect.py proposes (package.json name, else the folder name)
    name: str                # the product name passed to scaffold.py
    framework: str
    styling: str
    platforms: List[str]
    copies: List[str]        # generated copies of the web theme in the app
    ui_files: str            # PLUMB.md UI files, as the user confirms them at init
    # (file, rule, text the finding's message names): every error the first audit must report, nothing else
    violations: List[Tuple[str, str, str]]
    # (file, old, new): the fixes, as an agent applies them from the audit's fix lines
    fixes: List[Tuple[str, str, str]]
    screens: List[Screen]
    theme: str = ""          # the generated theme the guard protects (relative to the skill folder)

    @property
    def skill(self) -> str:
        return f".claude/skills/{self.slug}-design-system"

    @property
    def tokens(self) -> str:
        return f"{self.skill}/assets/tokens/{self.slug}.tokens.json"


NEXT = App(
    folder="next-tailwind", slug="sample-tasks", name="Sample Tasks", framework="next", styling="tailwind-v4",
    platforms=["web"], copies=["app/globals.css"], ui_files="app/**, components/** · *.tsx *.css",
    violations=[
        ("components/task-card.tsx", "raw-colour", "#1f7a8c"),
        ("components/task-card.tsx", "arbitrary-value", "rounded-[6px]"),
        ("components/task-card.tsx", "arbitrary-value", "text-[15px]"),
        ("components/task-card.tsx", "palette-colour", "bg-blue-500"),
        ("components/status-badge.tsx", "raw-colour", "#c0392b"),
        ("components/status-badge.tsx", "inline-style", "color"),
        ("components/status-badge.tsx", "arbitrary-value", "duration-[250ms]"),
        ("components/status-badge.tsx", "outline-none", "outline-none"),
    ],
    fixes=[
        ("components/task-card.tsx", "bg-[#1f7a8c] p-4 rounded-[6px]", "bg-surface p-4 rounded-md"),
        ("components/task-card.tsx", 'className="text-[15px]"', 'className="text-sm"'),
        ("components/task-card.tsx", 'className="bg-blue-500"', 'className="bg-primary text-on-primary"'),
        ("components/status-badge.tsx",
         'className="outline-none transition-colors duration-[250ms]" style={{ color: "#c0392b" }}',
         'className="text-danger transition-colors duration-200"'),
    ],
    screens=[
        Screen("home", "Today’s tasks", "/", ["app/page.tsx", "components/**"], {
            "ready": "<h1>Today’s tasks</h1>\n    <ul><li>Order supplies <span>Open</span></li></ul>",
            "empty": "<p>No tasks yet</p>",
        }),
        Screen("settings", "Settings", "/settings", ["app/settings/**"], {
            "ready": '<h1>Settings</h1>\n    <button type="button">Save</button>',
        }),
    ],
    theme="assets/platforms/web/tokens.css",
)

ANGULAR = App(
    folder="angular", slug="sample-notes", name="Sample Notes", framework="angular", styling="css",
    platforms=["web"], copies=["src/styles.scss"], ui_files="src/** · *.ts *.html *.scss *.css",
    violations=[
        ("src/app/notes/notes.component.scss", "off-scale-type", "15px"),
        ("src/app/notes/notes.component.scss", "raw-colour", "#1f7a8c"),
        ("src/app/notes/notes.component.scss", "off-scale-radius", "5px"),
        ("src/app/settings/settings.component.scss", "off-token-duration", "250ms"),
        ("src/app/settings/settings.component.scss", "off-token-easing", "ease-in-out"),
        ("src/app/settings/settings.component.scss", "outline-none", "outline: none"),
    ],
    fixes=[
        ("src/app/notes/notes.component.scss", "font-size: 15px;", "font-size: var(--text-sm);"),
        ("src/app/notes/notes.component.scss", "color: #1f7a8c;", "color: var(--color-primary);"),
        ("src/app/notes/notes.component.scss", "border-radius: 5px;", "border-radius: var(--radius-sm);"),
        ("src/app/settings/settings.component.scss", "background-color 250ms ease-in-out",
         "background-color var(--duration-mid) var(--ease-out)"),
        ("src/app/settings/settings.component.scss", ".save:focus {\n  outline: none;",
         ".save:focus-visible {\n  outline: 2px solid var(--color-primary);"),
    ],
    screens=[
        Screen("notes", "Notes", "/", ["src/app/notes/**"], {
            "ready": '<h1>Notes</h1>\n    <ul><li>Buy stamps</li></ul>',
            "empty": "<p>No notes yet</p>",
        }),
        Screen("settings", "Settings", "/settings", ["src/app/settings/**"], {
            "ready": '<h1>Settings</h1>\n    <button type="button">Save</button>',
        }),
    ],
    theme="assets/platforms/web/tokens.css",
)

SWIFTUI = App(
    folder="swiftui", slug="sample-habits", name="Sample Habits", framework="swiftui", styling="css",
    platforms=["ios"], copies=[], ui_files="SampleHabits/** · *.swift",
    violations=[
        ("SampleHabits/HabitListView.swift", "swift-font-size", ".system(size: 15)"),
        ("SampleHabits/HabitListView.swift", "swift-raw-colour", "Color(red: 0.12, green: 0.48, blue: 0.55)"),
        ("SampleHabits/SettingsView.swift", "swift-corner-radius", "cornerRadius: 6"),
    ],
    fixes=[
        ("SampleHabits/HabitListView.swift", ".font(.system(size: 15))", ".sampleHabitsText(SampleHabitsType.sm)"),
        ("SampleHabits/HabitListView.swift", ".foregroundStyle(Color(red: 0.12, green: 0.48, blue: 0.55))",
         ".foregroundStyle(SampleHabitsColor.onSurface)"),
        ("SampleHabits/SettingsView.swift", ".background(Color.accentColor)",
         ".foregroundStyle(SampleHabitsColor.onPrimary)\n                .background(SampleHabitsColor.primary)"),
        ("SampleHabits/SettingsView.swift", "RoundedRectangle(cornerRadius: 6)",
         "RoundedRectangle(cornerRadius: SampleHabitsRadius.md)"),
        # theme values beyond the violations: the icon map's SF Symbols instead of literal names
        ("SampleHabits/App.swift", 'Label("Habits", systemImage: "house")',
         'Label { Text("Habits") } icon: { SampleHabitsIcon.home.image }'),
        ("SampleHabits/App.swift", 'Label("Settings", systemImage: "gearshape")',
         'Label { Text("Settings") } icon: { SampleHabitsIcon.settings.image }'),
    ],
    screens=[
        Screen("habits", "Habits", "/habits", ["SampleHabits/HabitListView.swift"], {
            "ready": "<h1>Habits</h1>\n    <ul><li>Walk</li><li>Read</li></ul>",
        }),
        Screen("settings", "Settings", "/settings", ["SampleHabits/SettingsView.swift"], {
            "ready": '<h1>Settings</h1>\n    <button type="button">Save</button>',
        }),
    ],
    theme="assets/platforms/mobile/ios/SampleHabitsTheme.swift",
)

APPS: Dict[str, App] = {a.folder: a for a in (NEXT, ANGULAR, SWIFTUI)}
WEB_APPS = [NEXT.folder, ANGULAR.folder]


# ---------------------------------------------------------------- running things


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _env() -> Dict[str, str]:
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "USER": "tester", "USERNAME": "tester", "GIT_CONFIG_NOSYSTEM": "1"})
    return env


def py(project: Path, script: Path, *args: str) -> subprocess.CompletedProcess:
    env = _env()
    env["GIT_CEILING_DIRECTORIES"] = str(project.parent)
    return subprocess.run([sys.executable, str(script), *args], cwd=str(project), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=180)


def skill_script(project: Path, app: App, name: str, *args: str) -> subprocess.CompletedProcess:
    return py(project, project / app.skill / "scripts" / name, *args)


def ok(r: subprocess.CompletedProcess) -> subprocess.CompletedProcess:
    assert r.returncode == 0, (r.returncode, r.stdout[-4000:], r.stderr[-4000:])
    assert "Traceback" not in r.stderr, r.stderr
    return r


def audit(project: Path, app: App, *args: str) -> Tuple[int, dict]:
    r = skill_script(project, app, "audit.py", "--json", *args)
    assert r.returncode in (0, 1), (r.returncode, r.stdout[-4000:], r.stderr[-4000:])
    return r.returncode, json.loads(r.stdout)


def errors(report: dict) -> List[dict]:
    return [f for f in report["findings"] if f["severity"] == "error"]


def detect(project: Path) -> dict:
    return json.loads(ok(py(project, DETECT, "--cwd", str(project), "--json")).stdout)


def copy_app(app: App, dest: Path) -> Path:
    shutil.copytree(str(APPS_DIR / app.folder), str(dest))
    return dest


LABELS = {("next", "tailwind-v4"): "Next.js · Tailwind v4", ("angular", "css"): "Angular · CSS",
          ("swiftui", "css"): "SwiftUI"}


def answers(app: App) -> dict:
    return {"description": f"{app.name}: a sample app for Plumb's integration tests", "direction": "Calm",
            "ui_files": app.ui_files, "web_copies": app.copies, "icons": ICONS,
            "ui_packages": f". ({LABELS[(app.framework, app.styling)]})"}


def scaffold(project: Path, app: App, found: dict) -> subprocess.CompletedProcess:
    """scaffold.py with the placement detect.py proposed (the user confirmed it) and the answers file, then the build."""
    proposal = found["proposal"]
    tmp = Path(tempfile.mkdtemp(prefix="plumb-answers-"))
    try:
        path = tmp / "answers.json"
        write(path, json.dumps(answers(app), ensure_ascii=False))
        r = ok(py(project, SCAFFOLD, "--project-root", str(project), "--name", app.name, "--skill-dir",
                  proposal["skill_dir"], "--platforms", ",".join(proposal["platforms"]), "--styling", app.styling,
                  "--answers", str(path)))
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)
    ok(skill_script(project, app, "build-tokens.py"))
    return r


def fix(project: Path, app: App) -> None:
    for rel, old, new in app.fixes:
        path = project / rel
        text = read(path)
        assert text.count(old) == 1, (rel, old)
        write(path, text.replace(old, new))


def prototype(project: Path, app: App) -> None:
    """One screen file per route, mapped to its source files and approved (what /plumb:extract records)."""
    for order, screen in enumerate(app.screens, 1):
        write(project / SCREENS / f"{screen.id}.html", screen.html(order))
    for screen in app.screens:
        ok(skill_script(project, app, "build-prototype.py", "--map", screen.id, "--route", screen.route,
                        "--files", *screen.files))
        ok(skill_script(project, app, "build-prototype.py", "--approve", screen.id))


# ---------------------------------------------------------------- cached stages

_CACHE: Dict[Tuple[str, str], Path] = {}
_ROOT: List[Path] = []


def _root() -> Path:
    if not _ROOT:
        tmp = Path(tempfile.mkdtemp(prefix="plumb-apps-"))
        atexit.register(shutil.rmtree, str(tmp), True)
        _ROOT.append(tmp)
    return _ROOT[0]


def _stage(app: App, stage: str) -> Path:
    key = (app.folder, stage)
    if key in _CACHE:
        return _CACHE[key]
    dest = _root() / stage / app.slug
    if stage == "built":
        copy_app(app, dest)
        scaffold(dest, app, detect(dest))
    elif stage == "ready":
        shutil.copytree(str(_stage(app, "built")), str(dest))
        fix(dest, app)
        prototype(dest, app)
    else:
        raise ValueError(stage)
    _CACHE[key] = dest
    return dest


def project(app: App, stage: str, tmp_path: Path, name: Optional[str] = None) -> Path:
    """A fresh copy of the app at a stage: "built" (scaffolded and built, violations in place) or "ready" (fixed and
    prototyped: audit exits 0). The copy is tmp_path/<name>/<slug>, so its folder name stays the project name."""
    dest = tmp_path / (name or "work") / app.slug
    shutil.copytree(str(_stage(app, stage)), str(dest))
    return dest
