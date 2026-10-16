"""The marketplace and plugin manifests carry the agreed identity."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load(rel: str) -> dict:
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def test_marketplace_lists_one_plugin_plumb() -> None:
    m = load(".claude-plugin/marketplace.json")
    assert m["name"] == "plumb"
    assert [(p["name"], p["source"]) for p in m["plugins"]] == [("plumb", "./plugins/plumb")]


def test_plugin_manifest() -> None:
    p = load("plugins/plumb/.claude-plugin/plugin.json")
    assert p["name"] == "plumb"
    assert p["version"] == "1.0.0"
    assert p["author"]["name"] == "Zidane786"
    assert p["homepage"] == "https://github.com/Zidane786/plumb"
    assert p["repository"] == "https://github.com/Zidane786/plumb"
    assert "design-system" in p["keywords"]


def test_every_hard_coded_version_is_the_plugins() -> None:
    """A release bumps plugin.json; every other place that names the version must follow it (AGENTS.md "Releasing a
    version", step 1), or new projects are stamped with the old one."""
    import re

    plugin = REPO / "plugins/plumb"
    version = json.loads((plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    places = {
        "assets/skill/scripts/_plumb.py": r'^PLUMB_VERSION = "([\d.]+)"',
        "scripts/scaffold.py": r'^PLUMB_VERSION = "([\d.]+)"',
        "assets/skill/SKILL.md.tmpl": r'^\s*plumb: "([\d.]+)"',
        "assets/skill/design.md.tmpl": r"created with Plumb ([\d.]+)",
        "templates/PLUMB.md": r"^<!-- plumb v([\d.]+) ",
    }
    for rel, pattern in places.items():
        found = re.findall(pattern, (plugin / rel).read_text(encoding="utf-8"), re.M)
        assert found and set(found) == {version}, (rel, found, version)
    created = re.findall(r"created with Plumb ([\d.]+)", (plugin / "templates/PLUMB.md").read_text(encoding="utf-8"))
    assert created and set(created) == {version}
