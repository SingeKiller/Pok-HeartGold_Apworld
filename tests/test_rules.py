"""Tests for the region-exit access rules data_gen pipeline (task C6).

Regenerates `data/` (via `python data_gen.py`) and checks:
  - no `data/rules.py` `EXIT_RULES` entry references a region/item/badge that
    doesn't actually exist elsewhere in the generated `data/` package;
  - a handful of witness rules (Cut at Ilex Forest, Surf on the Whirl
    Islands/Kanto water routes, the S.S. Ticket) match the decomp evidence
    documented in `data_gen/rules.toml`;
  - most importantly (see this task's brief): the region graph
    (`data.regions.REGIONS` `exits` + `data.rules.EXIT_RULES`) stays
    connected with a full inventory -- every item in `data.items.ITEMS` and
    every badge in `data.rules.BADGES` owned at once must be enough to reach
    every region reachable at all from the game's start (New Bark Town),
    since `data_gen/rules.toml` only ever adds restrictions on top of
    `data_gen/regions.toml`'s raw exits, never removes one.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_gen_rules import Requirement, is_satisfied  # noqa: E402

START_REGION = "new_bark"

# Pre-existing gap in data_gen/regions.toml's raw graph (inherited from
# tasks C4/C5, *not* introduced or fixable by this task's data_gen/rules.toml
# -- rules.toml can only restrict an existing exit, never add a missing
# one). goldenrod_magnet_train_station_2f/saffron_magnet_train_station_2f
# (the *post*-Machine-Part-repair platform rooms, decomp map codes
# T25R0502/T11R0602) are each only reachable from the *other* city's own
# post-repair "2f" room (the hand-patched cutscene-warp pair documented in
# data_gen/regions.toml's header) -- neither has any exit back to its own
# city's "2f_empty" pre-repair room or "1f", so this 2-node pair is
# disconnected from the rest of the graph entirely, confirmed by running
# the same reachability search below with data.rules.EXIT_RULES ignored
# entirely (i.e. on the raw graph alone). Documented here rather than
# silently special-cased or hidden, per this task's brief -- flagged to the
# Planner as a probable C4/C5 regions.toml follow-up (the "1f -> 2f" static
# zone_event warp likely only exists at runtime, gated behind the same
# repair flag, and wasn't captured by C4/C5's static-warp extraction pass).
KNOWN_PRE_EXISTING_UNREACHABLE_REGIONS = {
    "goldenrod_magnet_train_station_2f",
    "saffron_magnet_train_station_2f",
}


@pytest.fixture(scope="module")
def generated():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    regions_mod = importlib.import_module("data.regions")
    items_mod = importlib.import_module("data.items")
    rules_mod = importlib.import_module("data.rules")
    for mod in (regions_mod, items_mod, rules_mod):
        importlib.reload(mod)
    yield regions_mod, items_mod, rules_mod
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="module")
def regions(generated):
    return generated[0].REGIONS


@pytest.fixture(scope="module")
def items(generated):
    return generated[1].ITEMS


@pytest.fixture(scope="module")
def rules(generated):
    return generated[2]


def _requirement_from_dict(raw: dict) -> Requirement:
    return Requirement(items=tuple(raw["items"]), badges=tuple(raw["badges"]))


# --- reference integrity -------------------------------------------------


def test_exit_rule_regions_exist(regions, rules) -> None:
    for src, dst in rules.EXIT_RULES:
        assert src in regions, f"EXIT_RULES references unknown region {src!r}"
        assert dst in regions, f"EXIT_RULES references unknown region {dst!r}"


def test_exit_rule_regions_are_real_exits(regions, rules) -> None:
    """Every gated (src, dst) pair must actually be an exit in
    data.regions.REGIONS -- data_gen/rules.toml must only ever restrict an
    existing connection, never invent a new one."""
    for src, dst in rules.EXIT_RULES:
        assert dst in regions[src]["exits"], f"{src} -> {dst} is gated but not a real exit"


def test_exit_rule_items_exist(items, rules) -> None:
    for (src, dst), requirement in rules.EXIT_RULES.items():
        for item in requirement["items"]:
            assert item in items, f"{src} -> {dst} requires unknown item {item!r}"


def test_exit_rule_badges_exist(rules) -> None:
    for (src, dst), requirement in rules.EXIT_RULES.items():
        for badge in requirement["badges"]:
            assert badge in rules.BADGES, f"{src} -> {dst} requires unknown badge {badge!r}"


def test_hm_badges_and_items_are_consistent(rules) -> None:
    """Every data_gen/rules.toml [hm_badges]/[hm_items] value must resolve:
    hm_badges values are badge keys (in BADGES), hm_items values are
    data_gen/items.toml item keys."""
    for hm, badge in rules.HM_BADGES.items():
        assert badge in rules.BADGES, f"hm_badges[{hm!r}] references unknown badge {badge!r}"
    assert set(rules.HM_BADGES) <= set(rules.HM_ITEMS), "every gated HM must have a matching hm_items entry"


def test_exit_rule_pairs_are_bidirectional_unless_documented(regions, rules) -> None:
    """Every (src, dst) in EXIT_RULES should have a (dst, src) counterpart
    with the same requirement, *except* the one documented one-way gate
    (Tohjo Falls' hidden room, see data_gen/rules.toml)."""
    one_way_exceptions = {("tohjo_falls", "tohjo_falls_hidden_room")}
    for (src, dst), requirement in rules.EXIT_RULES.items():
        if (src, dst) in one_way_exceptions:
            continue
        assert (dst, src) in rules.EXIT_RULES, f"{src} -> {dst} has no reverse rule"
        assert rules.EXIT_RULES[(dst, src)] == requirement


# --- witness rules (cross-checked directly against the decomp) -----------


def test_ilex_forest_cut_witness(rules) -> None:
    req = rules.EXIT_RULES[("ilex_forest", "route_34_ilex_forest_gatehouse")]
    assert req["items"] == ["hm01"]
    assert req["badges"] == ["hive"]


def test_whirl_islands_surf_witness(rules) -> None:
    req = rules.EXIT_RULES[("route_41", "whirl_islands_1f")]
    assert req["items"] == ["hm03"]
    assert req["badges"] == ["fog"]


def test_ss_ticket_witness(rules) -> None:
    req = rules.EXIT_RULES[("ss_aqua_olivine_port_interior", "ss_aqua_olivine_port_exterior")]
    assert req["items"] == ["s_s_ticket"]
    assert req["badges"] == []


def test_tohjo_falls_one_way_witness(rules) -> None:
    assert ("tohjo_falls", "tohjo_falls_hidden_room") in rules.EXIT_RULES
    assert ("tohjo_falls_hidden_room", "tohjo_falls") not in rules.EXIT_RULES


# --- the big one: connectivity with a full inventory ----------------------


def _reachable_regions(regions, rules, owned_items, owned_badges) -> set[str]:
    """BFS over data.regions.REGIONS `exits`, gating any (src, dst) that has
    an data.rules.EXIT_RULES entry by whether `owned_items`/`owned_badges`
    satisfy it. Exits that point at a region not defined in `regions` at all
    (out-of-v1-scope dangling references, e.g. the Safari Zone -- see
    data_gen/regions.toml's header) are simply not followed, same as any
    other real player would find a dead end there."""
    visited = {START_REGION}
    frontier = [START_REGION]
    while frontier:
        current = frontier.pop()
        for target in regions[current]["exits"]:
            if target not in regions or target in visited:
                continue
            raw_requirement = rules.EXIT_RULES.get((current, target))
            if raw_requirement is not None:
                requirement = _requirement_from_dict(raw_requirement)
                if not is_satisfied(requirement, owned_items, owned_badges):
                    continue
            visited.add(target)
            frontier.append(target)
    return visited


def test_graph_connected_with_full_inventory(regions, items, rules) -> None:
    """The single most important property of this task (see its brief):
    with every item and every badge in hand, every region reachable at all
    from New Bark Town via data.regions.REGIONS `exits` must still be
    reachable once data.rules.EXIT_RULES's gates are applied -- since
    data_gen/rules.toml only ever restricts an existing exit, never removes
    one, gating cannot shrink the reachable set versus the ungated graph.
    """
    full_items = set(items)
    full_badges = set(rules.BADGES)

    reachable_ungated = _reachable_regions(regions, rules, set(), set())
    # Sanity: an empty inventory must not already reach every region --
    # otherwise this test would be vacuous (no gate would ever matter).
    assert len(reachable_ungated) < len(regions), (
        "expected at least one region to be unreachable without any item/badge; "
        "if this now fails, either a real vanilla gate is missing from "
        "data_gen/rules.toml, or every gate in it has become redundant"
    )

    reachable_full = _reachable_regions(regions, rules, full_items, full_badges)

    # This is the graph-theoretic property that actually matters: gating can
    # never make a *previously reachable* region unreachable now that we own
    # everything.
    assert reachable_ungated <= reachable_full

    unreachable = set(regions) - reachable_full - KNOWN_PRE_EXISTING_UNREACHABLE_REGIONS
    assert not unreachable, (
        "the following regions are unreachable from New Bark Town even with "
        f"a full inventory (see this task's known-out-of-scope regions in "
        f"data_gen/regions.toml's header for expected exceptions): {sorted(unreachable)}"
    )
    # The known pre-existing gap itself must not have grown -- if this ever
    # fails, either the C4/C5 raw-graph gap above was fixed upstream (great:
    # shrink KNOWN_PRE_EXISTING_UNREACHABLE_REGIONS to match) or a new,
    # previously-unseen disconnection appeared and must be investigated.
    assert set(regions) - reachable_full == KNOWN_PRE_EXISTING_UNREACHABLE_REGIONS
