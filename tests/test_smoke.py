"""Smoke tests for the HeartGold APWorld tooling (task C0).

The Archipelago world package itself (`__init__.py`, `items.py`, etc.) does
not exist yet at this stage; once it does, this module should also assert
that it imports cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

import build

ROOT = Path(__file__).resolve().parent.parent


def test_build_module_imports() -> None:
    """The build script must import cleanly; it's the packaging entry point."""
    assert hasattr(build, "build")


def test_archipelago_json_is_valid() -> None:
    manifest = json.loads((ROOT / "archipelago.json").read_text(encoding="utf-8"))
    assert manifest["game"] == "Pokemon HeartGold"
    assert "minimum_ap_version" in manifest


def test_module_name_matches_game() -> None:
    assert build.module_name() == "pokemon_heartgold"
