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
