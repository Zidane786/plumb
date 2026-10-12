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

import pytest

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
    assert time.perf_counter() - t < 1.0
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
    assert time.perf_counter() - t < 1.0
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
