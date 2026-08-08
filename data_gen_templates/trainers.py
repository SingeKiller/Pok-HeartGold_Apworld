# data_gen_templates/trainers.py
#
# Turns `data_gen/trainers.toml` into `data/trainers.py` (task C7b). Follows
# the same load_toml -> dict-literal-repr pattern as `generate_items` in
# `data_gen_templates/items.py`. See `data_gen/trainers.toml`'s header for
# the source/extraction notes (trainers.json/trainers.h cross-reference,
# battle_type/ai_flags/double_battle semantics, and the "messages" flavor
# text left out of scope).

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from . import GENERATED_FILE_HEADER, load_toml

_VALID_BATTLE_TYPES = {"mon", "mon_moves", "mon_item", "mon_item_moves"}


def _build_party_mon(
    trainer_key: str,
    index: int,
    mon: Mapping[str, Any],
    species_keys: set[str],
    move_keys: set[str],
    item_keys: set[str],
) -> dict[str, Any]:
    species = mon["species"]
    if species not in species_keys:
        print(
            f"warning: data_gen/trainers.toml: {trainer_key}.party[{index}] "
            f"references unknown species {species!r}; keeping as-is.",
            file=sys.stderr,
        )

    built: dict[str, Any] = {
        "species": species,
        "level": mon["level"],
        "difficulty": mon["difficulty"],
        "capsule": mon["capsule"],
    }
    if "gender_override" in mon:
        built["gender_override"] = mon["gender_override"]
    if "ability_override" in mon:
        built["ability_override"] = mon["ability_override"]

    held_item = mon.get("held_item")
    if held_item is not None:
        if held_item not in item_keys:
            print(
                f"warning: data_gen/trainers.toml: {trainer_key}.party[{index}]"
                f".held_item references unknown item {held_item!r}; keeping "
                "as-is.",
                file=sys.stderr,
            )
        built["held_item"] = held_item

    moves = mon.get("moves")
    if moves is not None:
        resolved_moves = []
        for move in moves:
            if move not in move_keys:
                print(
                    f"warning: data_gen/trainers.toml: {trainer_key}."
                    f"party[{index}].moves references unknown move {move!r}; "
                    "skipping.",
                    file=sys.stderr,
                )
                continue
            resolved_moves.append(move)
        built["moves"] = tuple(resolved_moves)

    return built


def _build_trainer(
    key: str,
    entry: Mapping[str, Any],
    species_keys: set[str],
    move_keys: set[str],
    item_keys: set[str],
) -> dict[str, Any]:
    battle_type = entry["battle_type"]
    if battle_type not in _VALID_BATTLE_TYPES:
        print(
            f"warning: data_gen/trainers.toml: {key}.battle_type is "
            f"{battle_type!r}, expected one of {sorted(_VALID_BATTLE_TYPES)}; "
            "keeping as-is.",
            file=sys.stderr,
        )

    usable_items = []
    for item in entry.get("usable_items", []):
        if item not in item_keys:
            print(
                f"warning: data_gen/trainers.toml: {key}.usable_items "
                f"references unknown item {item!r}; skipping.",
                file=sys.stderr,
            )
            continue
        usable_items.append(item)

    party = tuple(
        _build_party_mon(key, index, mon, species_keys, move_keys, item_keys)
        for index, mon in enumerate(entry.get("party", []))
    )

    return {
        "id": entry["id"],
        "trainer_class": entry["trainer_class"],
        "label": entry["label"],
        "battle_type": battle_type,
        "double_battle": entry["double_battle"],
        "ai_flags": entry["ai_flags"],
        "usable_items": tuple(usable_items),
        "party": party,
    }


def generate_trainers() -> str:
    """Build the contents of `data/trainers.py` from
    `data_gen/trainers.toml`."""
    trainers_toml = load_toml("trainers")
    species_keys = set(load_toml("species"))
    move_keys = {k for k in load_toml("moves") if k != "tm_hm"}
    item_keys = set(load_toml("items"))

    trainers: dict[str, dict[str, Any]] = {}
    seen_ids: dict[int, str] = {}
    for key, entry in trainers_toml.items():
        trainer = _build_trainer(key, entry, species_keys, move_keys, item_keys)

        # Defensive: same spirit as data_gen_templates/items.py -- guard
        # against a future hand-edit of data_gen/trainers.toml introducing a
        # duplicate numeric id (the trainers.h TRAINER_* index space is
        # gapless/collision-free by construction, see data_gen/trainers.toml's
        # header, but data_gen sources are hand-editable).
        existing = seen_ids.get(trainer["id"])
        if existing is not None:
            print(
                f"warning: data_gen/trainers.toml: {key}.id={trainer['id']!r} "
                f"duplicates {existing}.id; both will be kept in "
                "data/trainers.py.",
                file=sys.stderr,
            )
        else:
            seen_ids[trainer["id"]] = key

        trainers[key] = trainer

    lines = [GENERATED_FILE_HEADER, "\n", "TRAINERS = {\n"]
    for key, trainer in trainers.items():
        lines.append(f"    {key!r}: {trainer!r},\n")
    lines.append("}\n")
    return "".join(lines)
