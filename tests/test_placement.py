"""Spec section 4: repo layout and stack detection (plugins/plumb/scripts/detect.py)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List

import pytest

# File system calls are slower on Windows CI runners (antivirus scanning, NTFS): this work took 1.45 s there (CI run
# 38891458675) and well under 1 s on macOS and Linux. The budget still catches a deep scan of such a tree.
TIME_BUDGET = 3.0 if os.name == "nt" else 1.0

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/plumb/scripts/detect.py"
FIXTURES = REPO / "tests/fixtures/layouts"

detect = None
if SCRIPT.exists():
    _spec = importlib.util.spec_from_file_location("plumb_detect", SCRIPT)
    detect = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(detect)  # type: ignore[union-attr]


def put(root: Path, rel: str, text: str = "") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


def pkg(root: Path, rel: str, deps: dict, name: str = "x", extra: dict | None = None) -> None:
    doc = {"name": name, "dependencies": deps}
    doc.update(extra or {})
    put(root, rel, json.dumps(doc))


def repo(root: Path) -> None:
    """Make root a repo: a real one when the tool is installed, else a bare marker folder."""
    root.mkdir(parents=True, exist_ok=True)
    if shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(root)], check=True, encoding="utf-8")
    else:
        (root / ".git").mkdir()


def detect_glob(glob: str):
    """The audit's glob reading (from the project root), from the shared core."""
    core = REPO / "plugins/plumb/assets/skill/scripts/_plumb.py"
    spec = importlib.util.spec_from_file_location("plumb_core_for_placement", core)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.glob_rx(glob)


def run(path: Path) -> dict:
    assert detect is not None, "detect.py is missing"
    return detect.detect(path)


def snapshot(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        st = p.stat()
        out[str(p.relative_to(root))] = (st.st_mtime_ns, st.st_size)
    return out


def test_script_exists() -> None:
    assert SCRIPT.exists(), "plugins/plumb/scripts/detect.py is missing"


def test_parent_folder_lists_projects(tmp_path: Path) -> None:
    pkg(tmp_path, "shop/package.json", {"next": "14.0.0", "react": "18"}, "shop")
    repo(tmp_path / "shop")
    put(tmp_path, "api/pyproject.toml", "[project]\ndependencies=['fastapi']\n")
    put(tmp_path, "notes/readme.txt", "hi")
    r = run(tmp_path)
    assert r["layout"] == "parent" and r["proposal"] is None
    kids = {c["name"]: c for c in r["children"]}
    assert set(kids) == {"shop", "api"}
    assert kids["shop"]["has_ui"] is True and kids["shop"]["is_repo"] is True
    assert kids["api"]["has_ui"] is False and kids["api"]["is_repo"] is False


def test_subfolder_uses_repo_root(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"next": "14", "react": "18"}, "caredesk")
    put(tmp_path, "app/page.tsx", "x")
    put(tmp_path, "app/globals.css", '@import "tailwindcss";')
    r = run(tmp_path / "app")
    assert Path(r["root"]).resolve() == tmp_path.resolve()
    assert r["opened"] == "app"
    assert r["layout"] == "frontend"
    assert r["proposal"]["skill_dir"] == ".claude/skills/caredesk-design-system"
    assert r["proposal"]["plumb_md"] == "PLUMB.md"


def test_monorepo_pnpm(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "pnpm-workspace.yaml", "packages:\n  - apps/*\n")
    pkg(tmp_path, "package.json", {}, "caredesk")
    pkg(tmp_path, "apps/web/package.json", {"next": "14", "react": "18", "tailwindcss": "^4.0.0"}, "web")
    put(tmp_path, "apps/web/app/layout.tsx", "x")
    put(tmp_path, "apps/web/app/globals.css", '@import "tailwindcss";\n')
    put(tmp_path, "apps/web/components.json", "{}")
    put(tmp_path, "apps/api/pyproject.toml", "[project]\ndependencies=['fastapi>=0.1']\n")
    r = run(tmp_path / "apps/web")
    assert r["layout"] == "monorepo" and r["monorepo"] == "pnpm-workspace.yaml"
    (ui,) = r["ui_packages"]
    assert ui["path"] == "apps/web" and ui["framework"] == "next"
    assert ui["styling"] == "tailwind-v4" and ui["shadcn"] is True and ui["platforms"] == ["web"]
    assert r["no_ui"] == [{"path": "apps/api", "stack": "fastapi"}]
    assert r["proposal"]["skill_dir"] == ".claude/skills/caredesk-design-system"
    assert r["proposal"]["copies"] == ["apps/web/app/globals.css"]


@pytest.mark.parametrize(
    "marker,files",
    [
        ("turbo.json", {"turbo.json": "{}"}),
        ("nx.json", {"nx.json": "{}"}),
        ("lerna.json", {"lerna.json": "{}"}),
        ("rush.json", {"rush.json": "{}"}),
        ("package.json workspaces", {"package.json": '{"name":"m","workspaces":["apps/*"]}'}),
        ("apps/* + packages/*", {"apps/a/x.txt": "", "packages/b/x.txt": ""}),
        ("frontend/ + backend/", {"frontend/x.txt": "", "backend/x.txt": ""}),
    ],
)
def test_monorepo_markers(tmp_path: Path, marker: str, files: dict) -> None:
    repo(tmp_path)
    for rel, text in files.items():
        put(tmp_path, rel, text)
    r = run(tmp_path)
    assert r["layout"] == "monorepo", marker
    assert r["monorepo"]


def test_monorepo_frontend_backend_siblings(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "frontend/package.json", {"vue": "3"}, "fe")
    put(tmp_path, "frontend/src/index.css", "")
    put(tmp_path, "backend/go.mod", "module x\n")
    r = run(tmp_path)
    assert r["layout"] == "monorepo"
    assert [u["path"] for u in r["ui_packages"]] == ["frontend"]
    assert r["ui_packages"][0]["framework"] == "vue"
    assert r["no_ui"] == [{"path": "backend", "stack": "go"}]


def _monorepo_app(root: Path, pages: int = 20, components: int = 90) -> List[str]:
    """A monorepo like the live test's: Next.js 16 + Tailwind v4 + shadcn in frontend/ (src/ layout), Python in
    backend/, no package.json or next.config at the repo root. Returns the UI files written (repo-relative)."""
    repo(root)
    pkg(root, "frontend/package.json", {"next": "16.0.0", "react": "19", "tailwindcss": "4", "next-themes": "0.4"},
        "frontend")
    put(root, "frontend/components.json", "{}")
    put(root, "frontend/next.config.ts", "export default {};\n")
    put(root, "frontend/src/app/globals.css", '@import "tailwindcss";\n')
    put(root, "backend/pyproject.toml", "[project]\ndependencies=['fastapi']\n")
    put(root, "backend/app/main.py", "app = None\n")
    files = ["frontend/src/app/layout.tsx", "frontend/src/app/page.tsx"]
    files += [f"frontend/src/app/p{i}/page.tsx" for i in range(pages)]
    files += [f"frontend/src/components/ui/c{i}.tsx" for i in range(components)]
    for f in files:
        put(root, f, "export default function X() { return null; }\n")
    return files


def test_monorepo_ui_files_and_routes_are_relative_to_the_repo_root(tmp_path: Path) -> None:
    """Live test 2: detect proposed app/**, src/**, components/** for a UI package in frontend/, which matched 0 of
    its 113 files (the audit reads the globs from the repo root). Now the guess names frontend/src/**, it covers
    every UI file detect counted, and the routes guess names frontend/src/app; both are labelled as guesses."""
    files = _monorepo_app(tmp_path)
    r = run(tmp_path)
    assert r["layout"] == "monorepo"
    (ui,) = r["ui_packages"]
    assert ui["path"] == "frontend" and ui["files"] == len(files) == 112
    value = r["proposal"]["ui_files"]
    assert value == "frontend/src/** · *.tsx *.jsx *.vue *.svelte *.css"
    left, _, right = value.partition(" · ")
    dirs = [detect_glob(d) for d in left.split(", ")]
    names = [detect_glob(n) for n in right.split()]
    matched = [f for f in files + ["frontend/src/app/globals.css"]
               if any(d.match(f) for d in dirs) and any(n.match(f.rsplit("/", 1)[-1]) for n in names)]
    assert len(matched) == len(files) + 1
    assert r["proposal"]["routes"] == "frontend/src/app (next-app)"
    text = detect.human(r)
    assert "  UI files   frontend/src/** · *.tsx *.jsx *.vue *.svelte *.css   (a guess" in text
    assert "  Routes     frontend/src/app (next-app)   (a guess" in text


def test_routes_guesses_for_each_stack(tmp_path: Path) -> None:
    cases = [
        ("sk", {"svelte": "5", "@sveltejs/kit": "2"}, ["src/routes/+page.svelte"], "src/routes (sveltekit)"),
        ("nx", {"nuxt": "3", "vue": "3"}, ["pages/index.vue"], "pages (nuxt)"),
        ("vr", {"vue": "3", "vue-router": "4"}, ["src/router/index.ts", "src/App.vue"], "src/router/index.ts (router)"),
        ("ng", {"@angular/core": "17"}, ["src/app/app.routes.ts", "src/app/app.component.ts"],
         "src/app/app.routes.ts (angular)"),
        ("np", {"next": "14"}, ["pages/index.tsx"], "pages (next-pages)"),
        ("re", {"react": "18"}, ["src/App.tsx"], None),
    ]
    for name, deps, files, want in cases:
        root = tmp_path / name
        repo(root)
        pkg(root, "package.json", deps)
        for f in files:
            put(root, f, "x")
        assert run(root)["proposal"]["routes"] == want, name


def test_separate_frontend_repo(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"@angular/core": "17"}, "My App")
    put(tmp_path, "src/styles.scss", "")
    put(tmp_path, "tailwind.config.js", "module.exports={}")
    r = run(tmp_path)
    assert r["layout"] == "frontend"
    assert r["ui_packages"][0]["framework"] == "angular"
    assert r["ui_packages"][0]["styling"] == "tailwind-v3"
    assert r["proposal"]["skill_dir"] == ".claude/skills/my-app-design-system"
    assert r["proposal"]["copies"] == ["src/styles.scss"]


def test_backend_only(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "requirements.txt", "Django==5\n")
    r = run(tmp_path)
    assert r["layout"] == "backend" and r["ui_packages"] == []
    assert r["no_ui"] == [{"path": ".", "stack": "django"}]
    assert r["proposal"]["copies"] == []


@pytest.mark.parametrize(
    "files,stack",
    [
        ({"go.mod": "module x"}, "go"),
        ({"pom.xml": "<project/>"}, "java"),
        ({"build.gradle": "plugins { id 'java' }"}, "java"),
        ({"Cargo.toml": "[package]"}, "rust"),
        ({"Gemfile": "gem 'rails'"}, "rails"),
        ({"pyproject.toml": "dependencies = ['flask']"}, "flask"),
    ],
)
def test_backend_markers(tmp_path: Path, files: dict, stack: str) -> None:
    repo(tmp_path)
    for k, v in files.items():
        put(tmp_path, k, v)
    r = run(tmp_path)
    assert r["layout"] == "backend" and r["no_ui"][0]["stack"] == stack


@pytest.mark.parametrize(
    "deps,fw",
    [
        ({"next": "14", "react": "18"}, "next"),
        ({"react": "18", "react-dom": "18"}, "react"),
        ({"vue": "3"}, "vue"),
        ({"svelte": "4"}, "svelte"),
        ({"@sveltejs/kit": "2"}, "svelte"),
        ({"@angular/core": "17"}, "angular"),
    ],
)
def test_frameworks(tmp_path: Path, deps: dict, fw: str) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", deps)
    assert run(tmp_path)["ui_packages"][0]["framework"] == fw


def test_plain_html(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "index.html", "<html></html>")
    put(tmp_path, "css/site.css", "body{}")
    r = run(tmp_path)
    (ui,) = r["ui_packages"]
    assert ui["framework"] == "html" and ui["styling"] == "css"
    assert r["proposal"]["copies"] == ["css/site.css"]


def test_tailwind_v3_vs_v4(tmp_path: Path) -> None:
    v3, v4, v4b = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for d in (v3, v4, v4b):
        repo(d)
        pkg(d, "package.json", {"react": "18", "vite": "5"})
        put(d, "src/index.css", "")
    put(v3, "tailwind.config.ts", "export default {}")
    put(v3, "src/index.css", "@tailwind base;")
    put(v4, "src/index.css", '@import "tailwindcss";\r\n')
    pkg(v4b, "package.json", {"react": "18", "@tailwindcss/vite": "^4"})
    assert run(v3)["ui_packages"][0]["styling"] == "tailwind-v3"
    assert run(v4)["ui_packages"][0]["styling"] == "tailwind-v4"
    assert run(v4b)["ui_packages"][0]["styling"] == "tailwind-v4"
    assert run(v4)["proposal"]["copies"] == ["src/index.css"]


def test_next_pages_router(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"next": "13", "react": "18"})
    put(tmp_path, "pages/index.tsx", "x")
    assert run(tmp_path)["proposal"]["copies"] == ["styles/globals.css"]


def test_swiftui_and_compose(tmp_path: Path) -> None:
    ios, droid = tmp_path / "ios", tmp_path / "droid"
    repo(ios)
    repo(droid)
    put(ios, "App.xcodeproj/project.pbxproj", "")
    put(ios, "App/ContentView.swift", "import SwiftUI\nstruct V: View {}")
    put(droid, "app/build.gradle.kts", 'android {}\nimplementation("androidx.compose.ui:ui")')
    ri, rd = run(ios), run(droid)
    assert ri["ui_packages"][0]["framework"] == "swiftui" and ri["ui_packages"][0]["platforms"] == ["ios"]
    assert rd["ui_packages"][0]["framework"] == "compose" and rd["ui_packages"][0]["platforms"] == ["android"]
    assert rd["layout"] == "frontend" and rd["no_ui"] == []


def test_swift_package(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "Package.swift", "// swift-tools-version:5.9")
    put(tmp_path, "Sources/A/V.swift", "import SwiftUI")
    assert run(tmp_path)["ui_packages"][0]["framework"] == "swiftui"


def test_existing_plumb_md_and_linked(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"react": "18"})
    (tmp_path / "PLUMB.md").write_bytes(
        b"<!-- plumb v1.0.0 -->\r\n# Plumb\r\n\r\nDesign system: `../web/.claude/skills/x-design-system/`\r\nRole: linked\r\n"
    )
    r = run(tmp_path)
    assert r["existing"]["plumb_md"] is True
    assert r["existing"]["skill"] == "../web/.claude/skills/x-design-system/"
    assert r["existing"]["role"] == "linked"


def test_no_existing(tmp_path: Path) -> None:
    repo(tmp_path)
    r = run(tmp_path)
    assert r["existing"] == {"plumb_md": False, "skill": None, "role": None}


def test_unicode_names(tmp_path: Path) -> None:
    root = tmp_path / "Café Ünïcode"
    repo(root)
    pkg(root, "package.json", {"react": "18"}, "")
    put(root, "src/日本語/App.tsx", "x")
    r = run(root)
    assert r["proposal"]["skill_dir"] == ".claude/skills/cafe-unicode-design-system"
    pkg(tmp_path, "Zoë/package.json", {"vue": "3"})
    assert "Zoë" in {c["name"] for c in run(tmp_path)["children"]}


def test_windows_style_input_and_crlf(tmp_path: Path) -> None:
    repo(tmp_path)
    (tmp_path / "package.json").write_bytes(b'{\r\n "name": "crlf-app",\r\n "dependencies": {"react": "18"}\r\n}\r\n')
    put(tmp_path, "src/index.css", "")
    r = run(tmp_path)
    assert "\\" not in json.dumps(r["proposal"]) and "\\" not in r["ui_packages"][0]["path"]
    assert r["proposal"]["skill_dir"] == ".claude/skills/crlf-app-design-system"
    assert detect.normalize_cwd("C:\\Users\\me\\proj") in ("C:\\Users\\me\\proj", "C:/Users/me/proj")


def test_no_tool_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").mkdir()
    pkg(tmp_path, "package.json", {"react": "18"}, "nogit")
    put(tmp_path, "src/deep/er/x.tsx", "x")
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    r = run(tmp_path / "src/deep")
    assert r["git"] is False
    assert Path(r["root"]).resolve() == tmp_path.resolve()
    assert r["layout"] == "frontend"


def test_excluded_dirs_skipped(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"react": "18"})
    pkg(tmp_path, "node_modules/foo/package.json", {"vue": "3"})
    pkg(tmp_path, ".next/x/package.json", {"vue": "3"})
    assert [u["path"] for u in run(tmp_path)["ui_packages"]] == ["."]


def test_never_writes(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "apps/web/package.json", {"next": "14"})
    put(tmp_path, "apps/web/app/globals.css", "")
    put(tmp_path, "turbo.json", "{}")
    time.sleep(0.01)
    before = snapshot(tmp_path)
    run(tmp_path)
    run(tmp_path / "apps/web")
    subprocess.run(
        [sys.executable, str(SCRIPT), "--cwd", str(tmp_path), "--json"],
        check=True, capture_output=True, encoding="utf-8",
    )
    assert snapshot(tmp_path) == before


def test_fast_on_large_tree(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"next": "14", "react": "18"})
    for i in range(20):
        for j in range(20):
            d = tmp_path / "src" / f"d{i}" / f"s{j}"
            d.mkdir(parents=True)
            for k in range(50):
                (d / f"f{k}.tsx").write_text("x", encoding="utf-8")
    for i in range(30):
        (tmp_path / "node_modules" / f"p{i}").mkdir(parents=True)
        (tmp_path / "node_modules" / f"p{i}" / "package.json").write_text("{}", encoding="utf-8")
    t = time.perf_counter()
    r = run(tmp_path)
    assert time.perf_counter() - t < TIME_BUDGET
    assert r["ui_packages"][0]["framework"] == "next"


def test_cli_json_and_human(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"react": "18"}, "cli-app")
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--cwd", str(tmp_path), "--json"],
        capture_output=True, encoding="utf-8", env=env, check=True,
    ).stdout
    data = json.loads(out)
    assert set(data) >= {"root", "layout", "ui_packages", "no_ui", "children", "git", "existing", "proposal"}
    human = subprocess.run(
        [sys.executable, str(SCRIPT), "--cwd", str(tmp_path)],
        capture_output=True, encoding="utf-8", env=env, check=True,
    ).stdout
    assert "Plumb found:" in human and "cli-app-design-system" in human


def test_bad_cwd_exits_2(tmp_path: Path) -> None:
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--cwd", str(tmp_path / "nope")],
        capture_output=True, encoding="utf-8",
    )
    assert p.returncode == 2 and p.stderr.startswith("error:") and "fix:" in p.stderr
    assert "Traceback" not in p.stderr


@pytest.mark.parametrize(
    "name", ["parent", "subfolder", "monorepo-pnpm", "monorepo-front-back", "frontend", "backend", "linked"]
)
def test_static_fixture_layouts(name: str, tmp_path: Path) -> None:
    src = FIXTURES / name
    assert src.is_dir(), f"missing fixture {name}"
    dst = tmp_path / name
    shutil.copytree(src, dst)
    repo(dst / "shop" if name == "parent" else dst)
    expected = json.loads((dst / "expected.json").read_text(encoding="utf-8"))
    cwd = dst / expected.pop("cwd", ".")
    r = run(cwd)
    for key, val in expected.items():
        if isinstance(val, dict):
            assert {k: r[key][k] for k in val} == val, key
        else:
            assert r[key] == val, key


def test_react_native_is_unsupported(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"expo": "51", "react": "18", "react-native": "0.74"})
    r = run(tmp_path)
    (ui,) = r["ui_packages"]
    assert ui["framework"] == "react-native" and ui["platforms"] == ["ios", "android"]
    assert ui["supported"] is False and "later release" in ui["note"] and ui["global_css"] is None
    assert r["proposal"]["copies"] == []
    assert r["confidence"] == "medium"


def test_guessed_vs_detected_copy_path_and_confidence(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        repo(d)
        pkg(d, "package.json", {"react": "18", "vite": "5"})
    put(a, "src/index.css", "")
    ra, rb = run(a), run(b)
    assert ra["ui_packages"][0]["global_css"] == {"path": "src/index.css", "exists": True}
    assert rb["ui_packages"][0]["global_css"] == {"path": "src/index.css", "exists": False}
    assert ra["confidence"] == "high" and ra["reasons"] == []
    assert rb["confidence"] == "low" and any("guess" in x for x in rb["reasons"])


def test_confidence_low_without_markers(tmp_path: Path) -> None:
    repo(tmp_path)
    r = run(tmp_path)
    assert r["confidence"] == "low" and r["reasons"]


def test_slug_transliteration(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"react": "18"}, "@x/Ünï Cødé")
    assert run(tmp_path)["proposal"]["skill_dir"] == ".claude/skills/uni-code-design-system"
    assert detect.kebab("Straße Æon Łódź Þor Ðin Đa ı") == "strasse-aeon-lodz-thor-din-da-i"


def test_backend_plus_ui_without_markers_is_mixed(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "requirements.txt", "django\n")
    pkg(tmp_path, "client/package.json", {"react": "18"})
    put(tmp_path, "client/src/index.css", "")
    r = run(tmp_path)
    assert r["layout"] == "mixed" and r["confidence"] == "medium"
    assert [u["path"] for u in r["ui_packages"]] == ["client"]
    assert r["no_ui"][0]["stack"] == "django"


def test_parent_git_flags(tmp_path: Path) -> None:
    pkg(tmp_path, "shop/package.json", {"react": "18"})
    r = run(tmp_path)
    assert r["layout"] == "parent" and r["git"] is False and r["in_repo"] is False
    assert r["git_available"] is (shutil.which("git") is not None)


# Not inside git (git is optional): the opened folder is the project when it has markers, a new project when empty.


def test_non_git_project_folder_is_the_project(tmp_path: Path) -> None:
    pkg(tmp_path, "package.json", {"next": "14", "react": "18"}, "loose-app")
    put(tmp_path, "app/globals.css", '@import "tailwindcss";\n')
    put(tmp_path, "app/page.tsx", "x")
    r = run(tmp_path)
    assert r["layout"] == "frontend" and r["git"] is False and r["in_repo"] is False
    assert Path(r["root"]).resolve() == tmp_path.resolve() and r["opened"] == "."
    assert r["ui_packages"][0]["framework"] == "next" and r["ui_packages"][0]["styling"] == "tailwind-v4"
    assert r["proposal"]["skill_dir"] == ".claude/skills/loose-app-design-system"
    assert r["proposal"]["copies"] == ["app/globals.css"] and r["children"] == []
    assert r["confidence"] == "medium" and any("not a git repo" in x for x in r["reasons"])


def test_non_git_monorepo_and_backend(tmp_path: Path) -> None:
    mono, api = tmp_path / "mono", tmp_path / "api"
    put(mono, "turbo.json", "{}")
    pkg(mono, "apps/web/package.json", {"react": "18"})
    put(api, "pyproject.toml", "[project]\ndependencies=['fastapi']\n")
    assert run(mono)["layout"] == "monorepo"
    assert run(api)["layout"] == "backend"


def test_empty_folder_is_a_new_project(tmp_path: Path) -> None:
    new = tmp_path / "Fresh Idea"
    put(new, ".DS_Store", "x")
    r = run(new)
    assert r["layout"] == "new" and r["git"] is False and r["in_repo"] is False
    assert r["ui_packages"] == [] and r["no_ui"] == [] and r["children"] == []
    assert r["proposal"]["skill_dir"] == ".claude/skills/fresh-idea-design-system" and r["proposal"]["copies"] == []
    assert any("new project" in x for x in r["reasons"])
    human = detect.human(r)
    assert "new project" in human and "OK, or change something?" in human


def test_folder_without_markers_or_marked_children_is_a_single_project(tmp_path: Path) -> None:
    put(tmp_path, "notes/readme.txt", "hi")
    put(tmp_path, "sketch.md", "hi")
    r = run(tmp_path)
    assert r["layout"] == "single" and Path(r["root"]).resolve() == tmp_path.resolve()
    assert r["confidence"] == "low"


def test_non_git_desktop_with_nested_projects_is_a_parent(tmp_path: Path) -> None:
    """~/Desktop with Projects/{acme (git), shop, blog} and OldProjects/api: never a project rooted at the Desktop."""
    desk = tmp_path / "Desktop"
    repo(desk / "Projects/acme")
    put(desk / "Projects/acme", "turbo.json", "{}")
    pkg(desk / "Projects/acme", "apps/web/package.json", {"next": "14"})
    pkg(desk, "Projects/shop/package.json", {"react": "18"}, "shop")
    pkg(desk, "Projects/blog/package.json", {"astro": "4"}, "blog")
    put(desk, "Saved Pages/article/index.html", "<html></html>")  # a stray page is not a project
    put(desk, "OldProjects/api/pyproject.toml", "[project]\ndependencies=['fastapi']\n")
    put(desk, "notes.txt", "hi")
    r = run(desk)
    assert r["layout"] == "parent" and r["proposal"] is None
    kids = {c["path"]: c for c in r["children"]}
    assert set(kids) == {"Projects/acme", "Projects/shop", "Projects/blog", "OldProjects/api"}
    assert kids["Projects/acme"]["is_repo"] is True and kids["Projects/shop"]["is_repo"] is False
    assert kids["Projects/shop"]["has_ui"] is True and kids["OldProjects/api"]["has_ui"] is False
    human = detect.human(r)
    assert "Projects/acme" in human and "OldProjects/api" in human


def test_non_git_folder_with_markers_and_nested_repos_is_a_parent(tmp_path: Path) -> None:
    put(tmp_path, "index.html", "<html></html>")
    repo(tmp_path / "work/site")
    pkg(tmp_path, "work/site/package.json", {"react": "18"})
    r = run(tmp_path)
    assert r["layout"] == "parent" and [c["path"] for c in r["children"]] == ["work/site"]


@pytest.mark.parametrize("vendored", ["app/vendor/lib", "third_party/x", "external/y", "node_modules/z",
                                      "Pods/p", ".venv/src/q", "dist/w"])
def test_vendored_repos_do_not_make_a_parent(tmp_path: Path, vendored: str) -> None:
    pkg(tmp_path, "package.json", {"react": "18"}, "q")
    pkg(tmp_path, "app/package.json", {"react": "18"})
    repo(tmp_path / vendored)
    pkg(tmp_path, vendored + "/package.json", {"left-pad": "1"})
    r = run(tmp_path)
    assert r["layout"] != "parent" and Path(r["root"]).resolve() == tmp_path.resolve()
    assert r["proposal"]["skill_dir"] == ".claude/skills/q-design-system"


def test_vendored_folders_are_not_listed_under_a_parent(tmp_path: Path) -> None:
    repo(tmp_path / "Projects/acme")
    repo(tmp_path / "Projects/vendor/other")
    r = run(tmp_path)
    assert r["layout"] == "parent" and [c["path"] for c in r["children"]] == ["Projects/acme"]


def test_non_git_monorepo_with_markers_is_still_a_monorepo(tmp_path: Path) -> None:
    put(tmp_path, "pnpm-workspace.yaml", "packages: ['apps/*']\n")
    pkg(tmp_path, "apps/web/package.json", {"next": "14"})
    pkg(tmp_path, "apps/admin/package.json", {"react": "18"})
    put(tmp_path, "services/api/go.mod", "module api\n")
    r = run(tmp_path)
    assert r["layout"] == "monorepo" and r["in_repo"] is False and r["enclosing"] is None
    assert sorted(u["path"] for u in r["ui_packages"]) == ["apps/admin", "apps/web"]


def test_non_git_package_reports_its_enclosing_monorepo(tmp_path: Path) -> None:
    put(tmp_path, "turbo.json", "{}")
    pkg(tmp_path, "apps/web/package.json", {"next": "14"})
    r = run(tmp_path / "apps/web")
    enc = r["enclosing"]
    assert enc is not None and Path(enc["root"]).resolve() == tmp_path.resolve()
    assert enc["markers"] == ["turbo.json"] and enc["plumb_md"] is False
    assert r["confidence"] == "low" and any("enclosing" in x for x in r["reasons"])
    put(tmp_path, "PLUMB.md", "Design system: `.claude/skills/x-design-system/`\nRole: home\n")
    enc = run(tmp_path / "apps/web")["enclosing"]
    assert enc["plumb_md"] is True


def test_human_block_names_the_root(tmp_path: Path) -> None:
    pkg(tmp_path, "package.json", {"react": "18"}, "loose")
    out = detect.human(run(tmp_path))
    assert "at the repo root" not in out and "in " + Path(run(tmp_path)["root"]).as_posix() in out


def test_in_repo_flag(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"react": "18"})
    r = run(tmp_path)
    assert r["in_repo"] is True and "not a git repo" not in " ".join(r["reasons"])


def test_parent_listing_does_not_deep_scan(tmp_path: Path) -> None:
    for i in range(30):
        pkg(tmp_path, f"p{i}/package.json", {"react": "18"})
        for j in range(30):
            put(tmp_path, f"p{i}/src/d{j}/f.tsx", "x")
    t = time.perf_counter()
    r = run(tmp_path)
    assert time.perf_counter() - t < TIME_BUDGET
    assert len(r["children"]) == 30 and all(c["has_ui"] for c in r["children"])


def test_plain_html_with_inline_style(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "index.html", "<html><style>body{margin:0}</style></html>")
    r = run(tmp_path)
    assert r["ui_packages"][0]["framework"] == "html"
    assert r["ui_packages"][0]["global_css"]["exists"] is False


def test_existing_skill_uses_shared_reader(tmp_path: Path) -> None:
    repo(tmp_path)
    (tmp_path / "PLUMB.md").write_bytes(b"Design system: `.claude/skills/a-design-system/`   (home)\nRole: home\n")
    assert run(tmp_path)["existing"]["skill"] == ".claude/skills/a-design-system/"


# ---------------------------------------------------------------- stack-aware UI files (Angular, SwiftUI)

ANGULAR_UI_FILES = ("src/** · *.component.ts *.component.html *.component.scss *.component.css *.routes.ts "
                    "*routing.module.ts styles.scss styles.css")


_AUDIT: list = []


def _audit():
    """audit.py, loaded once (registered in sys.modules first: its dataclasses look the module up)."""
    if not _AUDIT:
        spec = importlib.util.spec_from_file_location("plumb_audit_for_placement",
                                                      REPO / "plugins/plumb/assets/skill/scripts/audit.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["plumb_audit_for_placement"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _AUDIT.append(mod)
    return _AUDIT[0]


def _covered(ui_files: str, rel: str) -> bool:
    """Whether the audit (and so the hooks) would check rel with PLUMB.md `UI files: <ui_files>`: its own matcher."""
    root = Path("/plumb-project")
    wanted = _audit().ui_matcher(root, root / ".claude/skills/x-design-system", {"UI files": ui_files})
    return wanted(root / rel)


def _angular(root: Path, suffix: bool = True) -> None:
    pkg(root, "package.json", {"@angular/core": "18", "@angular/router": "18"}, "notes")
    put(root, "angular.json", "{}")
    put(root, "src/styles.scss", "body { margin: 0; }")
    put(root, "src/main.ts", "bootstrapApplication(App);")
    put(root, "src/index.html", "<app-root></app-root>")
    put(root, "src/app/app.routes.ts", "export const routes = [];")
    put(root, "src/app/data.service.ts", "export class DataService {}")
    if suffix:
        put(root, "src/app/notes/notes.component.ts", "@Component({templateUrl: './notes.component.html'})")
        put(root, "src/app/notes/notes.component.html", "<h1>Notes</h1>")
        put(root, "src/app/notes/notes.component.scss", ".t { color: red; }")
        put(root, "src/app/notes/notes.component.spec.ts", "describe('x', () => {});")
        put(root, "src/app/settings/settings.component.ts", "@Component({template: '<h1>S</h1>'})")
    else:  # Angular 20 file names: no .component suffix
        put(root, "src/app/app.ts", "@Component({templateUrl: './app.html'})")
        put(root, "src/app/app.html", "<h1>Notes</h1>")
        put(root, "src/app/app.css", "h1 { color: red; }")


def test_angular_ui_files_cover_components_not_services(tmp_path: Path) -> None:
    repo(tmp_path)
    _angular(tmp_path)
    r = run(tmp_path)
    (ui,) = r["ui_packages"]
    assert ui["framework"] == "angular"
    assert ui["ui_files"] == ANGULAR_UI_FILES
    assert r["proposal"]["ui_files"] == ANGULAR_UI_FILES
    # an honest count: the component templates, classes and styles (and index.html), not services, main.ts or specs
    assert ui["files"] == 5
    for rel in ("src/app/notes/notes.component.ts", "src/app/notes/notes.component.html",
                "src/app/notes/notes.component.scss", "src/app/settings/settings.component.ts",
                "src/app/app.routes.ts", "src/styles.scss"):
        assert _covered(ui["ui_files"], rel), rel
    for rel in ("src/app/data.service.ts", "src/main.ts", "src/index.html", "e2e/notes.component.ts"):
        assert not _covered(ui["ui_files"], rel), rel
    assert "UI files   " + ANGULAR_UI_FILES in detect.human(r)


def test_angular_without_the_component_suffix_covers_every_source_file(tmp_path: Path) -> None:
    repo(tmp_path)
    _angular(tmp_path, suffix=False)
    r = run(tmp_path)
    (ui,) = r["ui_packages"]
    assert ui["ui_files"] == "src/** · *.ts *.html *.scss *.css"
    assert ui["files"] == 4  # index.html, app.html, and app.ts and app.css (paired by name); not main.ts or services
    assert any("without the .component suffix" in reason for reason in r["reasons"])
    assert _covered(ui["ui_files"], "src/app/app.ts") and _covered(ui["ui_files"], "src/app/app.css")


def test_angular_package_in_a_monorepo_gets_its_own_folder(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "pnpm-workspace.yaml", "packages: ['apps/*']")
    _angular(tmp_path / "apps/web")
    r = run(tmp_path)
    (ui,) = r["ui_packages"]
    assert ui["path"] == "apps/web"
    assert ui["ui_files"] == ANGULAR_UI_FILES.replace("src/**", "apps/web/src/**")
    assert r["proposal"]["ui_files"] == ui["ui_files"]
    assert _covered(ui["ui_files"], "apps/web/src/app/notes/notes.component.scss")


@pytest.mark.parametrize("deps,files", [
    ({"next": "15", "react": "19"}, ["app/page.tsx"]),
    ({"react": "18"}, ["src/App.tsx"]),
    ({"vue": "3"}, ["src/App.vue"]),
    ({"svelte": "5"}, ["src/App.svelte"]),
])
def test_other_web_stacks_keep_the_platform_default(tmp_path: Path, deps: dict, files: list) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", deps)
    for f in files:
        put(tmp_path, f, "x")
    put(tmp_path, "src/util.component.ts", "x")  # not Angular: never counted
    put(tmp_path, "src/util.component.scss", "x")
    r = run(tmp_path)
    assert r["proposal"]["ui_files"] is None
    assert all(u["ui_files"] is None for u in r["ui_packages"])
    assert r["ui_packages"][0]["files"] == len(files)
    # the placement block still shows the UI files line: the platform default PLUMB.md will get
    assert "  UI files   " + detect.PLATFORM_UI_FILES["web"] + "   (a guess" in detect.human(r)


def test_placement_block_shows_ui_files_and_what_happens_to_an_existing_stylesheet(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"next": "15", "react": "19", "tailwindcss": "4"}, "frontdesk")
    put(tmp_path, "app/page.tsx", "export default () => null;\n")
    put(tmp_path, "app/globals.css", '@import "tailwindcss";\nbody { margin: 0; }\n')
    r = run(tmp_path)
    text = detect.human(r)
    copy = r["proposal"]["copies"][0]
    assert copy == "app/globals.css"
    assert "  generated copy → app/globals.css   (Plumb's marked block of the token CSS)\n" in text
    assert "  app/globals.css exists: Plumb will add a marked block; the rest stays yours\n" in text
    assert "  UI files   " in text
    lines = text.splitlines()
    assert lines.index("I'll create:") < lines.index("  app/globals.css exists: Plumb will add a marked block; the rest stays yours")
    put(tmp_path, "app/globals.css", "/* plumb:start x */\n/* plumb:end */\nbody {}\n")
    assert "app/globals.css exists with Plumb's block: the build updates only the block" in detect.human(run(tmp_path))
    (tmp_path / "app/globals.css").unlink()
    assert "exists" not in detect.human(run(tmp_path)).split("I'll create:", 1)[1]


def test_scaffold_and_detect_share_the_platform_ui_files() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("scaffold_ui_files", REPO / "plugins/plumb/scripts/scaffold.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.PLATFORM_UI_FILES == detect.PLATFORM_UI_FILES


def test_swiftui_sources_without_a_package_or_xcode_project(tmp_path: Path) -> None:
    put(tmp_path, "Habits/App.swift", "import SwiftUI\n@main struct A: App { var body: some Scene { WindowGroup {} } }")
    put(tmp_path, "Habits/Views/List.swift", "import SwiftUI\nstruct L: View { var body: some View { Text(\"x\") } }")
    put(tmp_path, "Habits/Model.swift", "struct Habit {}")
    r = run(tmp_path)
    assert r["layout"] == "frontend"
    (ui,) = r["ui_packages"]
    assert (ui["path"], ui["framework"], ui["platforms"], ui["files"]) == ("Habits", "swiftui", ["ios"], 3)
    assert r["proposal"]["platforms"] == ["ios"] and r["proposal"]["copies"] == []
    assert r["confidence"] == "low"
    assert any("without Package.swift or an Xcode project" in reason for reason in r["reasons"])


def test_swiftui_sources_in_a_git_repo_without_markers(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "App/ContentView.swift", "import SwiftUI\nstruct V: View { var body: some View { Text(\"x\") } }")
    r = run(tmp_path)
    assert [(u["path"], u["framework"]) for u in r["ui_packages"]] == [("App", "swiftui")]
    assert r["confidence"] == "low"


def test_swift_files_without_swiftui_are_not_a_ui(tmp_path: Path) -> None:
    put(tmp_path, "Tool/main.swift", "import Foundation\nprint(1)")
    r = run(tmp_path)
    assert r["ui_packages"] == [] and r["layout"] == "single"


WEB_DIRS = "app/**, src/**, components/**"
WEB_NAMES = "*.tsx *.jsx *.vue *.svelte *.css"


def test_web_and_ios_side_by_side_cover_the_ios_folder(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"next": "15", "react": "19"})
    put(tmp_path, "app/page.tsx", "x")
    put(tmp_path, "ios/App.xcodeproj/project.pbxproj", "")
    put(tmp_path, "ios/App/ContentView.swift", "import SwiftUI\nstruct V: View {}")
    r = run(tmp_path)
    assert sorted(u["framework"] for u in r["ui_packages"]) == ["next", "swiftui"]
    assert r["proposal"]["ui_files"] == f"{WEB_DIRS}, ios/** · {WEB_NAMES} *.swift"
    for rel in ("ios/App/ContentView.swift", "app/page.tsx", "components/card.tsx"):
        assert _covered(r["proposal"]["ui_files"], rel), rel
    assert not _covered(r["proposal"]["ui_files"], "scripts/tool.swift")


def test_web_and_android_side_by_side_cover_the_android_module(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"react": "18"})
    put(tmp_path, "src/App.tsx", "x")
    put(tmp_path, "android/app/build.gradle.kts", 'android {}\nimplementation("androidx.compose.ui:ui")')
    r = run(tmp_path)
    assert r["proposal"]["ui_files"] == f"{WEB_DIRS}, android/app/** · {WEB_NAMES} *.kt"
    assert _covered(r["proposal"]["ui_files"], "android/app/src/main/java/a/Home.kt")


def test_pure_mobile_keeps_the_platform_default(tmp_path: Path) -> None:
    repo(tmp_path)
    put(tmp_path, "App.xcodeproj/project.pbxproj", "")
    put(tmp_path, "App/ContentView.swift", "import SwiftUI\nstruct V: View {}")
    assert run(tmp_path)["proposal"]["ui_files"] is None


def test_files_of_a_backend_package_are_not_counted_for_the_ui_above(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"next": "15", "react": "19"})
    put(tmp_path, "app/page.tsx", "x")
    pkg(tmp_path, "server/package.json", {"express": "4"})
    put(tmp_path, "server/public/index.html", "<p>api</p>")
    r = run(tmp_path)
    assert r["no_ui"] == [{"path": "server", "stack": "express"}]
    assert [u["files"] for u in r["ui_packages"]] == [1]


WIDE = "src/** · *.ts *.html *.scss *.css"


def test_angular_mixing_suffixed_and_angular_20_names_covers_both(tmp_path: Path) -> None:
    repo(tmp_path)
    _angular(tmp_path)
    put(tmp_path, "src/app/billing/billing.ts", "@Component({templateUrl: './billing.html'})")
    put(tmp_path, "src/app/billing/billing.html", "<h1>Billing</h1>")
    r = run(tmp_path)
    (ui,) = r["ui_packages"]
    assert ui["ui_files"] == WIDE
    assert ui["files"] == 7
    assert _covered(ui["ui_files"], "src/app/billing/billing.ts")
    assert _covered(ui["ui_files"], "src/app/notes/notes.component.scss")
    assert any("without the .component suffix" in reason for reason in r["reasons"])


def test_angular_inline_template_component_without_suffix_is_covered(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"@angular/core": "20"}, "notes")
    put(tmp_path, "src/main.ts", "bootstrapApplication(App);")
    put(tmp_path, "src/app/app.ts", "import { Component } from '@angular/core';\n@Component({template: '<h1>Hi</h1>'})\n"
                                    "export class App {}\n")
    put(tmp_path, "src/app/data.ts", "export class Data {}")
    r = run(tmp_path)
    (ui,) = r["ui_packages"]
    assert ui["ui_files"] == WIDE
    assert ui["files"] == 1  # app.ts (an @Component), not main.ts or data.ts


def test_angular_workspace_projects_use_their_source_roots(tmp_path: Path) -> None:
    repo(tmp_path)
    pkg(tmp_path, "package.json", {"@angular/core": "18"}, "suite")
    put(tmp_path, "angular.json", json.dumps({"version": 1, "projects": {
        "shop": {"root": "projects/shop", "sourceRoot": "projects/shop/src"},
        "admin": {"root": "projects/admin", "sourceRoot": "projects/admin/src"},
        "lib": {"root": "projects/lib"},
    }}))
    put(tmp_path, "projects/shop/src/app/cart/cart.component.ts", "@Component({})")
    put(tmp_path, "projects/admin/src/app/users/users.component.html", "<h1>Users</h1>")
    r = run(tmp_path)
    (ui,) = r["ui_packages"]
    assert ui["ui_files"] == ANGULAR_UI_FILES.replace("src/**", "projects/shop/src/**, projects/admin/src/**")
    assert _covered(ui["ui_files"], "projects/shop/src/app/cart/cart.component.ts")
    assert _covered(ui["ui_files"], "projects/admin/src/app/users/users.component.html")


@pytest.mark.parametrize("text", ["{ // a comment\n}", "not json", "[]", '{"projects": {"a": {"sourceRoot": 3}}}',
                                  '{"projects": {"a": {"sourceRoot": "../outside"}}}',
                                  '{"projects": {"a": {"sourceRoot": "/abs/src"}}}',
                                  '{"projects": {"a": {"sourceRoot": "C:/abs/src"}}}'])
def test_angular_json_that_cannot_be_read_falls_back_to_src(tmp_path: Path, text: str) -> None:
    repo(tmp_path)
    _angular(tmp_path)
    put(tmp_path, "angular.json", text)
    assert run(tmp_path)["ui_packages"][0]["ui_files"] == ANGULAR_UI_FILES
