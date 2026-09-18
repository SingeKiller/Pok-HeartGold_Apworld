#!/usr/bin/env python3
"""tracker_gen.py

Builds the PopTracker pack for Pokemon HGSS Singe from this world's own data
(data/, regenerated first) into build/poptracker/, and zips it as
poke_hgss_poptracker.zip at the repository root.

The web tracker's map tab is drawn from the game's own overworld data, so
it needs a vanilla HeartGold (US) ROM (HEARTGOLD_ROM_PATH) and the decomp's
map constants (ressources/Decomposition); without them the page has no map.

One variant per language (fr, en; names from tracker/i18n_fr.json), each
with its own folder: PopTracker reads ./<variant>/<file> before ./<file>.
The places, Pokedex and trainers are lists drawn as map images, one pin
per row. Archipelago must be importable (ARCHIPELAGO_PATH, default
../archipelago) because locations.py uses it.

Usage:
    python tracker_gen.py
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import unicodedata
import zipfile
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "build" / "poptracker"
STATIC = ROOT / "tracker"
ZIP_PATH = ROOT / "poke_hgss_poptracker.zip"
WEB_PATH = ROOT / "poke_hgss_tracker.html"
MAPS_H = ROOT / "ressources/Decomposition/pokeheartgold/include/constants/maps.h"
PACK_VERSION = "0.1.0"

OUTDOOR_CODE = re.compile(r"^(R\d\d|T\d\d|W\d\d)$")

LANGS = ("fr", "en")
I18N_FR = STATIC / "i18n_fr.json"
HM_NAMES = ["Cut", "Fly", "Surf", "Strength", "Whirlpool", "Rock Smash", "Waterfall", "Rock Climb"]
BADGE_ORDER = [
    "zephyr", "hive", "plain", "fog", "storm", "mineral", "glacier", "rising",
    "boulder", "cascade", "thunder", "rainbow", "soul", "marsh", "volcano", "earth",
]
# Gym leaders in BADGE_ORDER; each one lights up when its badge check is done.
LEADERS = {
    "en": ["Falkner", "Bugsy", "Whitney", "Morty", "Chuck", "Jasmine", "Pryce", "Clair",
           "Brock", "Misty", "Lt. Surge", "Erika", "Janine", "Sabrina", "Blaine", "Blue"],
    "fr": ["Albert", "Hector", "Blanche", "Mortimer", "Chuck", "Jasmine", "Frédo", "Sandra",
           "Pierre", "Ondine", "Major Bob", "Erika", "Jeannine", "Morgane", "Auguste", "Blue"],
}
# Shown in the grid even when no logic rule reads them.
EXTRA_KEY_ITEMS = [
    "old_rod", "good_rod", "super_rod", "dowsing_mchn", "bicycle",
    "rainbow_wing", "silver_wing", "clear_bell", "tidal_bell",
]
OPTION_TOGGLES = [
    "opt_dexsanity", "opt_kanto", "opt_trainersanity", "opt_legendarysanity", "opt_bicycle",
    "opt_power_plant_tm", "opt_soulsilver", "opt_heartgold",
]
SECTION_TYPES = {"ground_item", "hidden_item", "hm_tm", "npc_gift", "badge", "trainer", "static_pokemon"}
# Outdoor maps listed with the caves and towers rather than the towns.
NOT_A_TOWN = {"T29", "T31"}
DEX_PAGES = [(1, 151), (152, 251), (252, 386), (387, 493)]
UI = {
    "en": {
        "variant": "English", "goal": "Goal", "unknown": "?", "e4": "Elite Four", "red": "Red",
        "badges_goal": "{n} badges", "key_items": "Key items", "badges": "Badges", "leaders": "Gym leaders",
        "hms": "HMs", "towns": "Towns", "dungeons": "Caves and towers", "routes": "Routes",
        "pokedex": "Pokedex", "trainers": "Trainers", "hidden": "hidden", "badge": "{b} Badge",
        "trainers_of": "{a} - trainers", "tm": "TM", "hm": "HM",
    },
    "fr": {
        "variant": "Français", "goal": "Objectif", "unknown": "?", "e4": "Conseil 4", "red": "Red",
        "badges_goal": "{n} badges", "key_items": "Objets clés", "badges": "Badges", "leaders": "Champions d'arène",
        "hms": "CS", "towns": "Villes", "dungeons": "Grottes et tours", "routes": "Routes",
        "pokedex": "Pokédex", "trainers": "Dresseurs", "hidden": "caché", "badge": "Badge {b}",
        "trainers_of": "{a} - dresseurs", "tm": "CT", "hm": "CS",
    },
}


def _setup_imports() -> None:
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    sys.path.insert(0, str(ROOT))
    archipelago = Path(os.environ.get("ARCHIPELAGO_PATH", ROOT.parent / "archipelago"))
    sys.path.insert(1, str(archipelago))


def pretty(key: str) -> str:
    return key.replace("_", " ").title()


def lua(value, indent: int = 0) -> str:
    """Python value -> Lua literal."""
    pad = "  " * indent
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "{" + ", ".join(lua(v, indent) for v in value) + "}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        parts = []
        for k, v in value.items():
            key = f"[{k}]" if isinstance(k, int) else f"[{json.dumps(k, ensure_ascii=False)}]"
            parts.append(f"{pad}  {key} = {lua(v, indent + 1)},")
        return "{\n" + "\n".join(parts) + f"\n{pad}}}"
    raise TypeError(type(value))


def build() -> Path:
    _setup_imports()
    from data.items import ITEMS
    from data.locations import LOCATIONS
    from data.regions import REGIONS
    from data.rules import EXIT_RULES

    import locations as loc_mod
    import regions as reg_mod
    from items import HEARTGOLD_ITEM_ID_BASE

    fr = json.loads(I18N_FR.read_text(encoding="utf-8"))
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "scripts").mkdir(parents=True)
    for path in (STATIC / "scripts").glob("*.lua"):
        shutil.copy(path, OUT / "scripts" / path.name)

    # -- tracked items ------------------------------------------------------
    rule_items = {code for rule in EXIT_RULES.values() for code in rule["items"]}
    gate_items = {code for codes in loc_mod._ITEM_GATED_LOCATIONS.values() for code in codes}
    hm_codes = [f"hm0{i}" for i in range(1, 9)]
    badge_codes = [f"badge_{b}" for b in BADGE_ORDER]
    key_codes = sorted((rule_items | gate_items | set(EXTRA_KEY_ITEMS)) - set(hm_codes) - set(badge_codes))
    tracked = hm_codes + badge_codes + key_codes
    leader_codes = [f"leader_{b}" for b in BADGE_ORDER]
    badge_locations = sorted((k for k, d in LOCATIONS.items() if d["type"] == "badge"),
                             key=lambda k: BADGE_ORDER.index(LOCATIONS[k]["original_item"][6:]))

    def item_name(code: str, lang: str) -> str:
        if re.fullmatch(r"(tm|hm)\d\d", code):
            return UI[lang][code[:2]] + code[2:]
        if code in badge_codes:
            badge = code[6:]
            return UI[lang]["badge"].format(b=fr["badges"][badge] if lang == "fr" else badge.title())
        if lang == "fr" and code in fr["items"]:
            return fr["items"][code]
        return ITEMS[code]["label"].replace("_", " ").title()

    def tile_text(code: str, lang: str) -> str:
        if code in hm_codes:
            return (fr["hms"] if lang == "fr" else HM_NAMES)[int(code[-1]) - 1]
        if code in badge_codes:
            return fr["badges"][code[6:]] if lang == "fr" else code[6:].title()
        if code in leader_codes:
            return LEADERS[lang][leader_codes.index(code)]
        return item_name(code, lang)

    # -- areas --------------------------------------------------------------
    def parent_area(region: str) -> str:
        seen, queue = {region}, deque([region])
        while queue:
            current = queue.popleft()
            if OUTDOOR_CODE.match(REGIONS[current]["map_code"]):
                return REGIONS[current]["map_code"]
            for nxt in REGIONS[current]["exits"]:
                if nxt in REGIONS and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return REGIONS[region]["map_code"]

    def area_key(region: str) -> str:
        """Towns and routes: their outdoor map code. Caves, towers, forests
        and the S.S. Aqua: one "site" per map family (D36*, P01*)."""
        code = REGIONS[region]["map_code"]
        if code[0] in "DP":
            return "S:" + code[:3]
        return parent_area(region)

    code_regions = defaultdict(list)
    for key, region in REGIONS.items():
        code_regions[region["map_code"]].append(key)
        if region["map_code"][0] in "DP":
            code_regions["S:" + region["map_code"][:3]].append(key)
    en_names = {code: SITE_NAMES.get(code) or (_site_name(keys) if code.startswith("S:") else pretty(min(keys, key=len)))
                for code, keys in code_regions.items()}

    areas = defaultdict(list)
    for key, data in LOCATIONS.items():
        if data["type"] in SECTION_TYPES:
            areas[area_key(data["region"])].append(key)
    kanto_regions = set(reg_mod.KANTO_REGION_KEYS)
    kanto_codes = {code for code, keys in areas.items() if all(LOCATIONS[k]["region"] in kanto_regions for k in keys)}

    def area_name(code: str, lang: str) -> str:
        if lang == "fr" and code in fr["areas"]:
            return fr["areas"][code]
        return en_names[code]

    def row_label(code: str, lang: str) -> str:
        """List row: "Azuria (Cerulean)" in French, the name alone in English
        or when both are the same (routes)."""
        name = area_name(code, lang)
        return name if name == en_names[code] or code[0] in "RW" else f"{name} ({en_names[code]})"

    def category(code: str) -> str:
        if code.startswith("T") and code not in NOT_A_TOWN:
            return "towns"
        if code[0] in "RW":
            return "routes"
        return "dungeons"

    def sub_place(key: str, lang: str) -> str:
        """Where inside its area a check is, e.g. "gym" or "b2f"."""
        region = LOCATIONS[key]["region"]
        base = en_names[area_key(region)].lower().replace(" ", "_").replace(".", "").replace("'", "")
        rest = region.split(base, 1)[1].strip("_") if base in region else region
        if not rest or rest == base:
            return ""
        if lang == "fr" and rest in fr["sub"]:
            return fr["sub"][rest]
        return pretty(rest)

    def trainer_class(data) -> str:
        label = data["label"].lower().replace(" ", "_").replace(".", "_")
        cls = data["trainer"]
        return cls[: -len(label) - 1] if cls.endswith("_" + label) else re.sub(r"_\d+$", "", cls)

    def section_name(key: str, lang: str) -> str:
        data = LOCATIONS[key]
        kind = data["type"]
        if kind == "trainer":
            cls = trainer_class(data)
            if lang == "fr":
                match = max((c for c in fr["classes"] if cls == c or cls.startswith(c + "_")), key=len, default=None)
                cls_name = fr["classes"][match] if match else pretty(cls)
            else:
                cls_name = pretty(re.sub(r"_(gs|m|f)$", "", cls))
            name = f"{cls_name} {data['label']}"
        elif kind == "badge":
            index = badge_locations.index(key)
            name = f"{item_name(badge_codes[index], lang)} ({LEADERS[lang][index]})"
        elif kind == "static_pokemon":
            name = data["label"].split(" - ", 1)[-1]
        elif data.get("original_item") in ("rainbow_wing", "silver_wing"):
            # HeartGold and SoulSilver hand the two wings out at swapped spots.
            name = f"{item_name('rainbow_wing', lang)} / {item_name('silver_wing', lang)}"
        elif kind == "npc_gift" and lang == "en" and " - " in data.get("label", ""):
            name = data["label"].split(" - ", 1)[1]
        else:
            name = item_name(data["original_item"], lang)
            if kind == "hidden_item":
                name += f" ({UI[lang]['hidden']})"
        where = sub_place(key, lang)
        return f"{name} - {where}" if where else name

    def visibility_of(key: str) -> list[str]:
        data = LOCATIONS[key]
        rules = []
        if data["type"] == "trainer":
            rules.append("opt_trainersanity")
        if data["type"] == "static_pokemon":
            rules.append("opt_legendarysanity")
        if key == "goldenrod_bike_shop_bicycle":
            rules.append("opt_bicycle")
        if key in loc_mod.POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS:
            rules.append("opt_power_plant_tm")
        if data["region"] in kanto_regions:
            rules.append("opt_kanto")
        return rules

    location_ids = loc_mod.create_location_label_to_code_map()
    dex_keys = sorted((k for k, d in LOCATIONS.items() if d["type"] == "dexsanity"),
                      key=lambda k: fr["dex_numbers"][LOCATIONS[k]["species"]])
    sections_by_lang = {}

    for lang in LANGS:
        ui = UI[lang]
        root = OUT / lang
        for sub in ("items", "maps", "layouts", "locations", "images/items", "images/maps"):
            (root / sub).mkdir(parents=True, exist_ok=True)

        # page -> {column title (None: untitled) -> [(name, check count)]}
        locations_json, location_sections, pages = [], {}, defaultdict(dict)

        def add_location(name, keys, map_locations, visibility=None):
            used, sections = set(), []
            for key in keys:
                label = section_name(key, lang).replace("/", "-")
                base, n = label, 2
                while label in used:
                    label, n = f"{base} #{n}", n + 1
                used.add(label)
                section = {"name": label, "item_count": 1, "access_rules": [f"$loc|{key}"],
                           "hosted_item": f"reveal_{location_ids[key]}"}
                rules = visibility_of(key)
                if rules:
                    section["visibility_rules"] = [",".join(rules)]
                sections.append(section)
                location_sections[location_ids[key]] = f"@{name}/{label}"
            location = {"name": name, "sections": sections, "map_locations": map_locations}
            if visibility:
                location["visibility_rules"] = visibility
            locations_json.append(location)

        def order(code):
            number = re.match(r"^[RW](\d+)$", code)
            if number:
                return int(number.group(1)), ""
            plain = unicodedata.normalize("NFKD", area_name(code, lang)).encode("ascii", "ignore").decode()
            return 0, plain.lower()

        for region in ("johto", "kanto"):
            for cat in ("towns", "dungeons", "routes"):
                pages[region][ui[cat]] = []
        for code in sorted(areas, key=order):
            region = "kanto" if code in kanto_codes else "johto"
            visibility = ["opt_kanto"] if code in kanto_codes else None
            by_type = lambda k: (LOCATIONS[k]["type"], section_name(k, lang))
            items_keys = sorted((k for k in areas[code] if LOCATIONS[k]["type"] != "trainer"), key=by_type)
            trainer_keys = sorted((k for k in areas[code] if LOCATIONS[k]["type"] == "trainer"), key=by_type)
            if items_keys:
                column = pages[region].setdefault(ui[category(code)], [])
                column.append((row_label(code, lang), len(items_keys)))
                map_locations = [{"map": region, "ref": (ui[category(code)], len(column) - 1)}]
                add_location(area_name(code, lang), items_keys, map_locations, visibility)
            if trainer_keys:
                page = f"trainers_{region}"
                column = pages[page].setdefault(None, [])
                column.append((row_label(code, lang), len(trainer_keys)))
                name = ui["trainers_of"].format(a=area_name(code, lang))
                add_location(name, trainer_keys, [{"map": page, "ref": (None, len(column) - 1)}],
                             ["opt_trainersanity,opt_kanto" if visibility else "opt_trainersanity"])
        for key in dex_keys:
            species = LOCATIONS[key]["species"]
            number = fr["dex_numbers"][species]
            page = next(f"dex_{i + 1}" for i, (lo, hi) in enumerate(DEX_PAGES) if lo <= number <= hi)
            label = fr["species"][species] if lang == "fr" else LOCATIONS[key]["label"].split(": ", 1)[-1]
            name = f"#{number:03d} {label}"
            column = pages[page].setdefault(None, [])
            column.append((name, None))
            locations_json.append({
                "name": name, "visibility_rules": ["opt_dexsanity"],
                "sections": [{"name": label, "item_count": 1, "access_rules": ["$dex"],
                              "hosted_item": f"reveal_{location_ids[key]}"}],
                "map_locations": [{"map": page, "ref": (None, len(column) - 1)}],
            })
            location_sections[location_ids[key]] = f"@{name}/{label}"

        # Each list page is a map: columns of rows, the pin left of each name.
        maps_json = []
        for page, columns in pages.items():
            spots = _draw_list_page(columns, root / f"images/maps/{page}.png", page.startswith("dex_"))
            maps_json.append({"name": page, "img": f"images/maps/{page}.png", "location_size": 16,
                              "location_border_thickness": 2})
            for location in locations_json:
                for map_location in location["map_locations"]:
                    if map_location.get("map") == page and "ref" in map_location:
                        x, y = spots[map_location.pop("ref")]
                        map_location.update({"x": x, "y": y})
        (root / "maps/maps.json").write_text(json.dumps(maps_json, indent=1, ensure_ascii=False), encoding="utf-8")
        (root / "locations/locations.json").write_text(
            json.dumps(locations_json, indent=1, ensure_ascii=False), encoding="utf-8")
        sections_by_lang[lang] = location_sections

        # -- items ------------------------------------------------------------
        _draw_item_icons(root, tracked + leader_codes, lambda code: tile_text(code, lang))
        goal_stages = [f"{ui['goal']} : {ui['unknown']}", f"{ui['goal']} : {ui['e4']}",
                       f"{ui['goal']} : {ui['red']}"] + [
            f"{ui['goal']} : {ui['badges_goal'].format(n=n)}" for n in range(1, 17)]
        _draw_goal_stages(root, goal_stages)
        _draw_reveal_icon(root)
        items_json = [
            {"name": item_name(code, lang), "type": "toggle", "img": f"images/items/{code}.png",
             "disabled_img": f"images/items/{code}_off.png", "codes": code}
            for code in tracked
        ] + [
            {"name": LEADERS[lang][i], "type": "toggle", "img": f"images/items/{code}.png",
             "disabled_img": f"images/items/{code}_off.png", "codes": code}
            for i, code in enumerate(leader_codes)
        ] + [
            {"name": ui["goal"], "type": "progressive", "allow_disabled": False, "codes": "goal",
             "stages": [{"name": text, "img": f"images/items/goal_{i}.png", "codes": f"goal_{i}"}
                        for i, text in enumerate(goal_stages)]},
        ] + [
            {"name": code, "type": "toggle", "img": "images/items/blank.png", "codes": code}
            for code in OPTION_TOGGLES
        ] + [
            {"name": "?", "type": "toggle", "img": "images/items/reveal.png", "codes": f"reveal_{location_id}",
             "overlay_font_size": 8, "overlay_background": "#C0000000", "overlay_align": "left"}
            for location_id in sorted(location_sections)
        ]
        (root / "items/items.json").write_text(json.dumps(items_json, indent=1, ensure_ascii=False), encoding="utf-8")

        # -- layouts ------------------------------------------------------------
        def grid(title, codes, per_row=16):
            return [{"type": "text", "text": title, "margin": "4,6,4,1"},
                    {"type": "itemgrid", "item_margin": "2", "item_width": 54, "item_height": 45,
                     "h_alignment": "left",
                     "rows": [codes[i:i + per_row] for i in range(0, len(codes), per_row)]}]

        # Everything the player owns across the top, the check pages below.
        header = {
            "type": "array", "orientation": "vertical", "margin": "6,4",
            "content": [{"type": "item", "item": "goal", "width": 260, "height": 38, "h_alignment": "left"}]
            + grid(ui["key_items"], key_codes) + grid(ui["badges"], badge_codes)
            + grid(ui["leaders"], leader_codes) + grid(ui["hms"], hm_codes),
        }

        def map_tab(title, page):
            return {"title": title, "content": {"type": "map", "maps": [page]}}

        main_tabs = {"type": "tabbed", "tabs": [
            map_tab("Johto", "johto"),
            map_tab("Kanto", "kanto"),
            {"title": ui["pokedex"], "content": {"type": "tabbed", "tabs": [
                map_tab(f"{lo}-{hi}", f"dex_{i + 1}") for i, (lo, hi) in enumerate(DEX_PAGES)]}},
            {"title": ui["trainers"], "content": {"type": "tabbed", "tabs": [
                map_tab("Johto", "trainers_johto"), map_tab("Kanto", "trainers_kanto")]}},
        ]}
        tracker_layout = {
            "shared_item_grid": header,
            "tracker_default": {
                "type": "container", "background": "#1b1d22",
                "content": {"type": "dock", "dropshadow": True, "content": [
                    {"type": "dock", "dock": "top", "h_alignment": "stretch",
                     "content": [{"type": "layout", "key": "shared_item_grid"}]},
                    main_tabs,
                ]},
            },
        }
        broadcast_layout = {
            "tracker_broadcast": {"type": "array", "orientation": "horizontal",
                                  "content": [{"type": "layout", "key": "shared_item_grid"}]},
        }
        (root / "layouts/tracker.json").write_text(json.dumps(tracker_layout, indent=1, ensure_ascii=False),
                                                   encoding="utf-8")
        (root / "layouts/broadcast.json").write_text(json.dumps(broadcast_layout, indent=1, ensure_ascii=False),
                                                     encoding="utf-8")

    # -- logic data ------------------------------------------------------------
    events = {}
    for data in LOCATIONS.values():
        if data["type"] == "event":
            events[data["event"]] = {"region": data["region"], "ss_region": data.get("soulsilver_region")}
    lua_locations = {}
    for key, data in LOCATIONS.items():
        if data["type"] not in SECTION_TYPES:
            continue
        entry = {"type": data["type"], "region": data["region"]}
        if "soulsilver_region" in data:
            entry["ss_region"] = data["soulsilver_region"]
        if key in loc_mod._ITEM_GATED_LOCATIONS:
            entry["items"] = list(loc_mod._ITEM_GATED_LOCATIONS[key])
        elif key in loc_mod.REGION_GATED_LOCATIONS:
            entry["regions"] = list(loc_mod.REGION_GATED_LOCATIONS[key])
        elif key in loc_mod.EVENT_GATED_LOCATIONS:
            entry["events"] = list(loc_mod.EVENT_GATED_LOCATIONS[key])
        elif key in loc_mod.POWER_PLANT_GATED_LOCATION_KEYS:
            entry["power_plant"] = True
        lua_locations[key] = entry
    data_lua = {
        "regions": {key: list(region["exits"]) for key, region in REGIONS.items()},
        "exit_rules": {
            f"{src}>{dst}": {"items": list(r["items"]), "badges": list(r["badges"]), "events": list(r["events"])}
            for (src, dst), r in EXIT_RULES.items()
        },
        "events": events,
        "locations": lua_locations,
        "johto_only_excluded_hg": {k: True for k in sorted(reg_mod.johto_only_excluded_region_keys(False))},
        "johto_only_excluded_ss": {k: True for k in sorted(reg_mod.johto_only_excluded_region_keys(True))},
        "location_sections_by_lang": sections_by_lang,
        "item_codes": {HEARTGOLD_ITEM_ID_BASE + ITEMS[c]["id"]: c for c in tracked},
        "tracked_items": tracked,
        "leaders": leader_codes,
        "leader_locations": {location_ids[k]: leader_codes[i] for i, k in enumerate(badge_locations)},
        "dexsanity_ids": [location_ids[k] for k in dex_keys],
    }
    (OUT / "scripts/data.lua").write_text(
        "-- Generated by tracker_gen.py, do not edit.\nDATA = " + lua(data_lua) + "\n", encoding="utf-8"
    )

    # -- web tracker ---------------------------------------------------------------
    def check_entry(key):
        return {"key": key, "type": LOCATIONS[key]["type"], "vis": visibility_of(key),
                "name": {lang: section_name(key, lang) for lang in LANGS}}

    web_areas, web_checks = [], {}
    for code in sorted(areas):
        number = re.match(r"^[RW](\d+)$", code)
        entry = {"code": code, "region": "kanto" if code in kanto_codes else "johto", "cat": category(code),
                 "order": int(number.group(1)) if number else 0,
                 "name": {lang: area_name(code, lang) for lang in LANGS}, "en": en_names[code],
                 "checks": [], "trainers": []}
        for key in sorted(areas[code], key=lambda k: (LOCATIONS[k]["type"], section_name(k, "en"))):
            entry["trainers" if LOCATIONS[key]["type"] == "trainer" else "checks"].append(location_ids[key])
            web_checks[location_ids[key]] = check_entry(key)
        web_areas.append(entry)
    web = {
        "logic": {k: data_lua[k] for k in ("regions", "exit_rules", "events", "locations",
                                           "johto_only_excluded_hg", "johto_only_excluded_ss")},
        "item_codes": data_lua["item_codes"],
        "hms": hm_codes, "badges": badge_codes, "keys": key_codes, "leaders": leader_codes,
        "leader_locations": data_lua["leader_locations"],
        "labels": {lang: {code: tile_text(code, lang) for code in tracked + leader_codes} for lang in LANGS},
        "areas": web_areas,
        "checks": web_checks,
        "dex": [{"id": location_ids[k], "num": fr["dex_numbers"][LOCATIONS[k]["species"]],
                 "name": {"fr": fr["species"][LOCATIONS[k]["species"]],
                          "en": LOCATIONS[k]["label"].split(": ", 1)[-1]}} for k in dex_keys],
        "ui": UI,
        "map": _web_map(areas, code_regions, parent_area),
    }
    template = (STATIC / "web" / "tracker.html").read_text(encoding="utf-8")
    page = template.replace("/*__LOGIC__*/", (STATIC / "web" / "logic.js").read_text(encoding="utf-8")).replace(
        "/*__DATA__*/null", json.dumps(web, ensure_ascii=False, separators=(",", ":")))
    WEB_PATH.write_text(page, encoding="utf-8")

    manifest = {
        "name": "Pokemon HGSS Singe",
        "game_name": "Pokemon HGSS Singe",
        "package_uid": "poke_hgss_singe",
        "package_version": PACK_VERSION,
        "platform": "nds",
        "author": "SingeKiller",
        "variants": {lang: {"display_name": UI[lang]["variant"], "flags": ["ap", "aphintgame"]} for lang in LANGS},
        "min_poptracker_version": "0.26.2",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(OUT).as_posix())
    print(f"built {ZIP_PATH.name}: {len(sections_by_lang['en'])} checks, variants {', '.join(LANGS)}")
    return ZIP_PATH


# -- images -----------------------------------------------------------------


def _font(size: int):
    from PIL import ImageFont

    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(draw, text: str, width: int, size: int):
    """Largest font (down to 10px) at which text fits width, else truncated."""
    while size > 10 and draw.textlength(text, font=_font(size)) > width:
        size -= 1
    font = _font(size)
    while draw.textlength(text, font=font) > width and len(text) > 2:
        text = text[:-2] + "."
    return text, font


def _wrap(draw, text: str, width: int, height: int, size: int, minimum: int = 9):
    """Greedy word wrap (also after "-" and "'") at the largest font size,
    down to minimum, whose lines fit the box."""
    parts = re.findall(r"[^ '’-]+['’-]?", text)
    while True:
        font, lines = _font(size), []
        for part in parts:
            if lines:
                glue = "" if lines[-1].endswith(("-", "'", "’")) else " "
                if draw.textlength(lines[-1] + glue + part, font=font) <= width:
                    lines[-1] += glue + part
                    continue
            lines.append(part)
        widest = max(draw.textlength(line, font=font) for line in lines)
        if (widest <= width and len(lines) * (size + 2) <= height) or size <= minimum:
            return lines, size
        size -= 1


def _draw_list_page(columns, dest, dex: bool) -> dict:
    """A list page as a map image: titled columns of rows (a long column
    wraps into several), a pin spot left of each name. The canvas always
    holds a full column of rows, so short lists keep the same row size.
    Returns {(column title, row index): pin centre}."""
    from PIL import Image, ImageDraw

    row_h, col_w, per_col, size = (24, 200, 30, 14) if dex else (28, 300, 24, 15)
    titled = any(title for title in columns)
    top = 40 if titled else 8
    blocks = []
    for title, rows in columns.items():
        for start in range(0, max(1, len(rows)), per_col):
            blocks.append((title if start == 0 else None, title, rows[start:start + per_col], start))
    img = Image.new("RGB", (len(blocks) * col_w + 10, top + per_col * row_h + 8), (27, 29, 34))
    draw = ImageDraw.Draw(img)
    spots = {}
    for col, (heading, title, rows, start) in enumerate(blocks):
        x0 = col * col_w + 8
        if heading:
            draw.text((x0 + 6, 22), heading, font=_font(18), fill=(250, 199, 117), anchor="lm")
            draw.line((x0 + 4, 34, x0 + col_w - 10, 34), fill=(80, 84, 94), width=1)
        for row, (name, count) in enumerate(rows):
            y = top + row * row_h + row_h // 2
            if row % 2:
                draw.rectangle((x0, y - row_h // 2, x0 + col_w - 6, y + row_h // 2 - 1), fill=(34, 37, 43))
            spots[(title, start + row)] = (x0 + 14, y)
            right = x0 + col_w - 12
            if count is not None:
                draw.text((right, y), str(count), font=_font(13), fill=(140, 145, 155), anchor="rm")
                right -= 26
            text, font = _fit(draw, name, right - (x0 + 28), size)
            draw.text((x0 + 28, y), text, font=font, fill=(235, 235, 235), anchor="lm")
    img.save(dest)
    return spots


def _draw_item_icons(root, codes, text_of) -> None:
    """Header tiles: a dark tile with the name, green when owned (img) and
    grey when not (disabled_img), drawn at 2x the grid's 60x50 cell."""
    from PIL import Image, ImageDraw

    styles = {
        "": ((31, 58, 18), (59, 109, 17), (151, 196, 89)),
        "_off": ((36, 38, 44), (62, 65, 72), (136, 135, 128)),
    }
    for code in codes:
        for suffix, (fill, border, ink) in styles.items():
            img = Image.new("RGBA", (120, 100), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle((2, 2, 117, 97), radius=14, fill=fill, outline=border, width=3)
            lines, size = _wrap(draw, text_of(code), 106, 84, 30, minimum=20)
            lines = [_fit(draw, line, 106, size)[0] for line in lines[:3]]
            draw.multiline_text((60, 50), "\n".join(lines), font=_font(size), fill=ink, anchor="mm",
                                align="center", spacing=2)
            img.save(root / "images/items" / f"{code}{suffix}.png")
    Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(root / "images/items/blank.png")


def _draw_goal_stages(root, texts) -> None:
    from PIL import Image, ImageDraw

    for index, text in enumerate(texts):
        img = Image.new("RGBA", (520, 76), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((2, 2, 517, 73), radius=14, fill=(99, 56, 6), outline=(239, 159, 39), width=3)
        fitted, font = _fit(draw, text, 480, 34)
        draw.text((260, 38), fitted, font=font, fill=(250, 199, 117), anchor="mm")
        img.save(root / "images/items" / f"goal_{index}.png")


def _draw_reveal_icon(root) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 59, 59), fill=(90, 96, 110), outline=(255, 255, 255), width=3)
    draw.text((32, 32), "?", font=_font(36), fill=(255, 255, 255), anchor="mm")
    img.save(root / "images/items/reveal.png")


SITE_NAMES = {"S:D23": "Radio Tower", "S:D35": "Rocket HQ", "S:P01": "S.S. Aqua", "S:D37": "Underground"}


MAP_UNIT = 16  # map units per 32x32-tile chunk


def _web_map(areas, code_regions, parent_area):
    """Pokegear-style map for the web tracker, laid out from the overworld
    matrix (matrix 0, both regions side by side): land and sea behind, and
    each area's shape on top: towns as boxes,
    routes as road segments between chunk centres, caves and towers as dots
    next to the outdoor map they open onto. None without a ROM."""
    rom_path = os.environ.get("HEARTGOLD_ROM_PATH")
    if not rom_path or not MAPS_H.is_file():
        print("no HEARTGOLD_ROM_PATH: the web tracker gets no map")
        return None
    from PIL import Image, ImageDraw, ImageFilter

    from rom import HeartGoldRom

    rom = HeartGoldRom.open(rom_path)
    matrix = bytes(rom.read_narc("a/0/4/1").files[0])
    width, height = matrix[0], matrix[1]
    cursor = 5 + matrix[4]
    headers = struct.unpack_from(f"<{width * height}H", matrix, cursor)
    cursor += width * height * 2
    if matrix[3]:
        cursor += width * height
    models = struct.unpack_from(f"<{width * height}H", matrix, cursor)
    code_by_id = {}
    for line in MAPS_H.read_text().splitlines():
        m = re.match(r"#define MAP_\w+\s+(\d+)\s+//\s+MAP_(\w+)", line)
        if m:
            code_by_id[int(m.group(1))] = m.group(2)

    chunks = defaultdict(list)
    for cz in range(height):
        for cx in range(width):
            if models[cz * width + cx] != 0xFFFF:
                chunks[code_by_id.get(headers[cz * width + cx], "")].append((cx, cz))

    # Background: land wherever a town, route or site sits (sea routes
    # excepted), grown and rounded off like the Pokegear's coastline, with
    # greener lowland right under the roads and towns.
    scale = 8
    def mask(cells, grow, blur):
        layer = Image.new("L", (width * scale, height * scale), 0)
        draw = ImageDraw.Draw(layer)
        for cx, cz in cells:
            draw.rectangle((cx * scale - grow, cz * scale - grow, (cx + 1) * scale + grow, (cz + 1) * scale + grow),
                           fill=255)
        layer = layer.resize((width * MAP_UNIT * 2, height * MAP_UNIT * 2), Image.BILINEAR)
        return layer.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: 255 if v > 128 else 0)

    land_cells = [c for code, cells in chunks.items() if code not in ("EVERYWHERE", "") and not code.startswith("W")
                  for c in cells]
    road_cells = [c for code, cells in chunks.items() if code[:1] in "TR" for c in cells]
    img = Image.new("RGB", (width * MAP_UNIT * 2, height * MAP_UNIT * 2), (72, 152, 216))
    img.paste((121, 100, 64), mask=mask(land_cells, 7, 9))
    img.paste((216, 172, 104), mask=mask(land_cells, 5, 9))
    img.paste((144, 196, 104), mask=mask(road_cells, 1, 7))
    buffer = io.BytesIO()
    img.convert("P", palette=Image.ADAPTIVE, colors=16).save(buffer, "PNG", optimize=True)

    def centre(cell):
        return [cell[0] * MAP_UNIT + MAP_UNIT / 2, cell[1] * MAP_UNIT + MAP_UNIT / 2]

    owner = {cell: code for code, cells in chunks.items() for cell in cells}
    shapes = {}
    for code in areas:
        cells = chunks.get(code) or chunks.get(code[2:] if code.startswith("S:") else "", [])
        if code.startswith("T") and cells:
            xs, zs = [c[0] for c in cells], [c[1] for c in cells]
            pad = MAP_UNIT * 0.22
            shapes[code] = {"kind": "town", "rect": [min(xs) * MAP_UNIT + pad, min(zs) * MAP_UNIT + pad,
                                                     (max(xs) - min(xs) + 1) * MAP_UNIT - 2 * pad,
                                                     (max(zs) - min(zs) + 1) * MAP_UNIT - 2 * pad]}
        elif code[0] in "RW" and cells:
            segments = []
            for cx, cz in cells:
                for nx, nz in ((cx + 1, cz), (cx, cz + 1), (cx - 1, cz), (cx, cz - 1)):
                    other = owner.get((nx, nz), "EVERYWHERE")
                    if other == code and (nx, nz) > (cx, cz):
                        segments.append(centre((cx, cz)) + centre((nx, nz)))
                    elif other != code and other != "EVERYWHERE" and other[:1] in "TRW":
                        a, b = centre((cx, cz)), centre((nx, nz))
                        segments.append(a + [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])
            if not segments:
                x, y = centre(cells[0])
                segments.append([x - 4, y, x + 4, y])
            shapes[code] = {"kind": "route", "segs": segments}
        else:
            ring = 0.0
            if not cells:
                # An interior: next to the outdoor map it opens onto.
                cells = chunks.get(parent_area(code_regions[code][0]), [])
                if cells:
                    xs, zs = [c[0] for c in cells], [c[1] for c in cells]
                    ring = max(max(xs) - min(xs), max(zs) - min(zs)) * MAP_UNIT / 2 + MAP_UNIT * 0.55
            if cells:
                xs, zs = zip(*(centre(c) for c in cells))
                shapes[code] = {"kind": "site", "at": [sum(xs) / len(xs), sum(zs) / len(zs)], "ring": ring}
    # Dots around the same outdoor map share its ring, spread out on it.
    spots = defaultdict(list)
    for code, shape in shapes.items():
        if shape["kind"] == "site":
            spots[tuple(round(v) for v in shape["at"])].append(code)
    for (x, y), codes in spots.items():
        for i, code in enumerate(sorted(codes)):
            ring = shapes[code].pop("ring") or (7 if len(codes) > 1 else 0)
            angle = 2 * math.pi * i / max(len(codes), 1) - 0.8
            shapes[code]["at"] = [round(x + ring * math.cos(angle), 1), round(y + ring * math.sin(angle), 1)]
    return {"w": width * MAP_UNIT, "h": height * MAP_UNIT, "shapes": shapes,
            "bg": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")}


def _site_name(region_keys) -> str:
    """Readable name for a cave/tower/forest family of regions."""
    name = min(region_keys, key=len)
    name = re.sub(r"_(b?\d+f.*|entrance.*|outside|room.*|chamber.*|route_\d+_side|lower.*|upper.*)$", "", name)
    return pretty(name)


if __name__ == "__main__":
    build()
