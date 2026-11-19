#!/usr/bin/env python3

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


def _map_sources() -> Path:
    override = os.environ.get("HGSS_MAP_SOURCES")
    if override:
        return Path(override)
    found = sorted(ROOT.glob("ressources/*/*/include/constants/maps.h"))
    return found[0].parents[2] if found else ROOT / "ressources"


SOURCES = _map_sources()
MAPS_H = SOURCES / "include/constants/maps.h"
PACK_VERSION = "0.2.7"

OUTDOOR_CODE = re.compile(r"^(R\d\d|T\d\d|W\d\d)$")

LANGS = ("fr", "en")
I18N_FR = STATIC / "i18n_fr.json"
HM_NAMES = ["Cut", "Fly", "Surf", "Strength", "Whirlpool", "Rock Smash", "Waterfall", "Rock Climb"]
BADGE_ORDER = [
    "zephyr", "hive", "plain", "fog", "storm", "mineral", "glacier", "rising",
    "boulder", "cascade", "thunder", "rainbow", "soul", "marsh", "volcano", "earth",
]
LEADERS = {
    "en": ["Falkner", "Bugsy", "Whitney", "Morty", "Chuck", "Jasmine", "Pryce", "Clair",
           "Brock", "Misty", "Lt. Surge", "Erika", "Janine", "Sabrina", "Blaine", "Blue"],
    "fr": ["Albert", "Hector", "Blanche", "Mortimer", "Chuck", "Jasmine", "Frédo", "Sandra",
           "Pierre", "Ondine", "Major Bob", "Erika", "Jeannine", "Morgane", "Auguste", "Blue"],
}
EXTRA_KEY_ITEMS = [
    "old_rod", "good_rod", "super_rod", "dowsing_mchn", "bicycle",
    "rainbow_wing", "silver_wing", "clear_bell", "tidal_bell", "apricorn_box",
]
OPTION_TOGGLES = [
    "opt_dexsanity", "opt_kanto", "opt_trainersanity", "opt_legendarysanity", "opt_shopsanity", "opt_bicycle",
    "opt_game_corner_prizes", "opt_apricorn_trees", "opt_bug_contest",
    "opt_power_plant_tm", "opt_soulsilver", "opt_heartgold",
]
SECTION_TYPES = {"ground_item", "hidden_item", "hm_tm", "npc_gift", "badge", "trainer", "static_pokemon", "shop_item",
                 "game_corner_prize", "apricorn_tree", "bug_contest"}
TYPE_OPTIONS = {
    "trainer": "opt_trainersanity", "static_pokemon": "opt_legendarysanity", "shop_item": "opt_shopsanity",
    "game_corner_prize": "opt_game_corner_prizes", "apricorn_tree": "opt_apricorn_trees",
    "bug_contest": "opt_bug_contest",
}
APRICORN_COLORS = {
    "Black": ("noire", "Black"), "Red": ("rouge", "Red"), "Blue": ("bleue", "Blue"), "Yellow": ("jaune", "Yellow"),
    "Green": ("verte", "Green"), "Pink": ("rose", "Pink"), "White": ("blanche", "White"),
}
NOT_A_TOWN = {"T29", "T31"}
DEX_PAGES = [(1, 151), (152, 251), (252, 386), (387, 493)]
UI = {
    "en": {
        "variant": "English", "goal": "Goal", "unknown": "?", "e4": "Elite Four", "red": "Red",
        "badges_goal": "{n} badges", "key_items": "Key items", "badges": "Badges", "leaders": "Gym leaders",
        "hms": "HMs", "towns": "Towns", "dungeons": "Caves and towers", "routes": "Routes",
        "pokedex": "Pokedex", "trainers": "Trainers", "hidden": "hidden", "badge": "{b} Badge",
        "trainers_of": "{a} - trainers", "tm": "TM", "hm": "HM", "shop_item": "Shop item {n}",
        "prize": "Prize {n}", "apricorn_tree": "{c} Apricorn Tree",
        "bug_contest": "Bug-Catching Contest (participation)", "prize_counter": "Prize counter",
        "goal_pokedex": "Pokedex", "goal_legendary": "Legendary hunt",
    },
    "fr": {
        "variant": "Français", "goal": "Objectif", "unknown": "?", "e4": "Conseil 4", "red": "Red",
        "badges_goal": "{n} badges", "key_items": "Objets clés", "badges": "Badges", "leaders": "Champions d'arène",
        "hms": "CS", "towns": "Villes", "dungeons": "Grottes et tours", "routes": "Routes",
        "pokedex": "Pokédex", "trainers": "Dresseurs", "hidden": "caché", "badge": "Badge {b}",
        "trainers_of": "{a} - dresseurs", "tm": "CT", "hm": "CS", "shop_item": "Objet en boutique {n}",
        "prize": "Lot {n}", "apricorn_tree": "Arbre à Noigrume {c}",
        "bug_contest": "Concours de capture d'insectes (participation)", "prize_counter": "Comptoir des lots",
        "goal_pokedex": "Pokédex", "goal_legendary": "Chasse aux légendaires",
    },
}


def location_gates(key: str, data: dict, loc_mod) -> dict:
    from data.rules import HM_BADGES, HM_ITEMS

    gates = {}
    items = list(loc_mod._ITEM_GATED_LOCATIONS.get(key, ()))
    regions = list(loc_mod.REGION_GATED_LOCATIONS.get(key, ()))
    if data["type"] == loc_mod.APRICORN_TREE_LOCATION_TYPE:
        items = [loc_mod.APRICORN_BOX_ITEM_KEY]
        for move in loc_mod.APRICORN_TREE_FIELD_MOVES.get(key, ()):
            items += [HM_ITEMS[move], f"badge_{HM_BADGES[move]}"]
        regions += list(loc_mod.APRICORN_TREE_EXTRA_REGIONS.get(key, ()))
    if items:
        gates["items"] = items
    if regions:
        gates["regions"] = regions
    if key in loc_mod.EVENT_GATED_LOCATIONS:
        gates["events"] = list(loc_mod.EVENT_GATED_LOCATIONS[key])
    if key in loc_mod.POWER_PLANT_GATED_LOCATION_KEYS:
        gates["power_plant"] = True
    if key in loc_mod._COIN_CASE_FREE_PRIZES:
        gates["johto_free"] = True
    return gates


def _setup_imports() -> None:
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    sys.path.insert(0, str(ROOT))
    archipelago = Path(os.environ.get("ARCHIPELAGO_PATH", ROOT.parent / "archipelago"))
    sys.path.insert(1, str(archipelago))


def pretty(key: str) -> str:
    return key.replace("_", " ").title()


def lua(value, indent: int = 0) -> str:
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
    import rules as rules_mod
    from items import HEARTGOLD_ITEM_ID_BASE

    fr = json.loads(I18N_FR.read_text(encoding="utf-8"))
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "scripts").mkdir(parents=True)
    for path in (STATIC / "scripts").glob("*.lua"):
        shutil.copy(path, OUT / "scripts" / path.name)

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
        if data["type"] in SECTION_TYPES and key not in loc_mod.ROCKET_TRAINER_KEYS:
            areas[area_key(data["region"])].append(key)
    kanto_regions = set(reg_mod.KANTO_REGION_KEYS)
    kanto_codes = {code for code, keys in areas.items() if all(LOCATIONS[k]["region"] in kanto_regions for k in keys)}

    def area_name(code: str, lang: str) -> str:
        if lang == "fr" and code in fr["areas"]:
            return fr["areas"][code]
        return en_names[code]

    def row_label(code: str, lang: str) -> str:
        name = area_name(code, lang)
        return name if name == en_names[code] or code[0] in "RW" else f"{name} ({en_names[code]})"

    def category(code: str) -> str:
        if code.startswith("T") and code not in NOT_A_TOWN:
            return "towns"
        if code[0] in "RW":
            return "routes"
        return "dungeons"

    def sub_place(key: str, lang: str) -> str:
        return sub_place_of(LOCATIONS[key]["region"], lang)

    def place_rest(region: str) -> str:
        base = en_names[area_key(region)].lower().replace(" ", "_").replace(".", "").replace("'", "")
        rest = region.split(base, 1)[1].strip("_") if base in region else region
        return "" if rest == base else rest

    def sub_place_of(region: str, lang: str) -> str:
        rest = place_rest(region)
        if not rest:
            return ""
        if rest == "prize_corner":
            return PLACE_NAMES["prize_corner"][LANGS.index(lang)]
        if lang == "fr" and rest in fr["sub"]:
            return fr["sub"][rest]
        if lang == "fr" and fr["words"].get(rest):
            return fr["words"][rest]
        if lang == "fr":
            text = rest.replace("rock_smash", "rocksmash").replace("rock_climb", "rockclimb")
            words = {**fr["words"], "rocksmash": "Éclate-Roc", "rockclimb": "Escalade"}
            parts = [words.get(w, w.upper() if re.fullmatch(r"b?\d+f", w) else w) for w in text.split("_")]
            return " ".join(p for p in parts if p)
        return "Game Corner" if rest == "game_corner_jp" else pretty(rest)

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
        elif kind == "shop_item":
            name = UI[lang]["shop_item"].format(n=key.rsplit("_", 1)[1])
        elif kind == "game_corner_prize":
            name = UI[lang]["prize"].format(n=key.rsplit("_", 1)[1])
        elif kind == "apricorn_tree":
            color = data["label"].rsplit(" - ", 1)[1].split(" ")[0]
            shades = APRICORN_COLORS.get(color, (color.lower(), color))
            name = UI[lang]["apricorn_tree"].format(c=shades[LANGS.index(lang)])
        elif kind == "bug_contest":
            name = UI[lang]["bug_contest"]
        elif data.get("original_item") in ("rainbow_wing", "silver_wing"):
            name = f"{item_name('rainbow_wing', lang)} / {item_name('silver_wing', lang)}"
        elif kind == "npc_gift" and lang == "en" and " - " in data.get("label", ""):
            name = data["label"].split(" - ", 1)[1]
        else:
            name = item_name(data["original_item"], lang)
            if kind == "hidden_item":
                name += f" ({UI[lang]['hidden']})"
        where = sub_place(key, lang)
        return f"{name} - {where}" if where else name

    def plan_label(key: str, lang: str) -> str:
        name, where = section_name(key, lang), sub_place(key, lang)
        return name[: -len(where) - 3] if where and name.endswith(f" - {where}") else name

    def visibility_of(key: str) -> list[str]:
        data = LOCATIONS[key]
        rules = []
        if data["type"] in TYPE_OPTIONS:
            rules.append(TYPE_OPTIONS[data["type"]])
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

    town_codes = sorted(c for c in code_regions if re.fullmatch(r"T\d\d", c) and c not in NOT_A_TOWN)
    plan_area = {}
    for code, keys in code_regions.items():
        if code.startswith("S:"):
            continue
        owners = sorted({area_key(k) for k in keys})
        plan_area[code] = next((o for o in owners if o in town_codes), code if code in owners else owners[0])
    area_plans = defaultdict(list)
    for code in sorted(plan_area):
        area_plans[plan_area[code]].append(code)
    for area, codes in area_plans.items():
        codes.sort(key=lambda c: (c != area, c))

    def plan_name(code: str, lang: str) -> str:
        area = plan_area[code]
        if code == area:
            return area_name(code, lang)
        region = min(code_regions[code], key=len)
        fixed = PLACE_NAMES.get(place_rest(region))
        if fixed:
            return fixed[LANGS.index(lang)]
        sub = sub_place_of(region, lang)
        if area.startswith("S:") and sub:
            return f"{area_name(area, lang)} {sub}"
        return sub or area_name(area, lang)

    plan_places = {code: {lang: (lambda n: n[:1].upper() + n[1:])(plan_name(code, lang)) for lang in LANGS} for code in plan_area}

    def npc_label(keys, sprite):
        badges = [k for k in keys if LOCATIONS[k]["type"] == "badge"]
        if badges:
            return {lang: LEADERS[lang][badge_locations.index(badges[0])] for lang in LANGS}
        if any(LOCATIONS[k]["type"] == "shop_item" for k in keys):
            return npc_name("SPRITE_SHOPM1")
        if any(LOCATIONS[k]["type"] == "game_corner_prize" for k in keys):
            return {lang: UI[lang]["prize_counter"] for lang in LANGS}
        return npc_name(sprite)

    area_names = {area: {lang: area_name(area, lang) if area in en_names else plan_name(area, lang) for lang in LANGS}
                  for area in set(plan_area.values())}
    detail, overworld, world = _detail_maps(location_ids, code_regions, plan_places, npc_label, plan_area, area_names)
    npc_towns = [{"town": town, "region": "kanto" if all(k in kanto_regions for k in code_regions[town]) else "johto",
                  "name": {lang: area_name(town, lang) for lang in LANGS},
                  "plans": [code for code in area_plans[town] if code in detail]}
                 for town in town_codes] if detail else []
    web_area_plans = {area: [c for c in codes if c in detail] for area, codes in area_plans.items()} if detail else {}
    web_area_plans = {area: codes for area, codes in web_area_plans.items() if codes}
    detail = detail or {}
    key_of_id = {code: key for key, code in location_ids.items()}
    if detail or world:
        _poptracker_images(detail, world)

    def plan_region(area: str) -> str:
        if area in kanto_codes:
            return "kanto"
        regions = code_regions.get(area, [])
        return "kanto" if regions and all(r in kanto_regions for r in regions) else "johto"

    plan_sections_by_lang = {}
    follow_tabs_by_lang = {}
    for lang in LANGS:
        ui = UI[lang]
        root = OUT / lang
        for sub in ("items", "maps", "layouts", "locations", "images/items", "images/maps"):
            (root / sub).mkdir(parents=True, exist_ok=True)

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
                "sections": [{"name": label, "item_count": 1, "access_rules": [f"$dex|{location_ids[key]}"],
                              "hosted_item": f"reveal_{location_ids[key]}"}],
                "map_locations": [{"map": page, "ref": (None, len(column) - 1)}],
            })
            location_sections[location_ids[key]] = f"@{name}/{label}"

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
        by_name = {location["name"]: location for location in locations_json}
        if world:
            maps_json.append({"name": "world", "img": "images/world.png", "location_size": 18,
                              "location_border_thickness": 3})
            for code in areas:
                at = _world_pin(world, code)
                if at is None:
                    continue
                for name, shift in ((area_name(code, lang), 0), (ui["trainers_of"].format(a=area_name(code, lang)), 14)):
                    if name in by_name:
                        by_name[name]["map_locations"].append({"map": "world", "x": at[0] + shift, "y": at[1]})
        plan_sections, follow_tabs, used_names = {}, {}, set(by_name)
        tile = PLAN_PIXELS_PER_TILE * POP_PLAN_SCALE
        for code, plan in detail.items():
            map_name = f"plan_{code}"
            maps_json.append({"name": map_name, "img": f"images/plans/{code}.png", "location_size": 14,
                              "location_border_thickness": 2})
            title = plan_places[code][lang].replace("/", "-")
            for spot in plan["checks"]:
                keys = [key_of_id[i] for i in spot["ids"] if i in key_of_id and i in location_sections]
                if not keys:
                    continue
                npc = (spot.get("npc") or {}).get(lang)
                base = f"{title} - {npc or plan_label(keys[0], lang)}".replace("/", "-")
                name, n = base, 2
                while name in used_names:
                    name, n = f"{base} #{n}", n + 1
                used_names.add(name)
                sections, labels = [], set()
                for key in keys:
                    label = plan_label(key, lang).replace("/", "-")
                    first, k = label, 2
                    while label in labels:
                        label, k = f"{first} #{k}", k + 1
                    labels.add(label)
                    section = {"name": label, "item_count": 1, "access_rules": [f"$loc|{key}"],
                               "hosted_item": f"reveal_{location_ids[key]}"}
                    rules = visibility_of(key)
                    if rules:
                        section["visibility_rules"] = [",".join(rules)]
                    sections.append(section)
                    plan_sections[location_ids[key]] = f"@{name}/{label}"
                locations_json.append({"name": name, "sections": sections, "map_locations": [
                    {"map": map_name, "x": round((spot["x"] + 0.5) * tile), "y": round((spot["y"] + 0.5) * tile)}]})
        plan_sections_by_lang[lang] = plan_sections
        (root / "maps/maps.json").write_text(json.dumps(maps_json, indent=1, ensure_ascii=False), encoding="utf-8")
        (root / "locations/locations.json").write_text(
            json.dumps(locations_json, indent=1, ensure_ascii=False), encoding="utf-8")
        sections_by_lang[lang] = location_sections

        _draw_item_icons(root, tracked + leader_codes, lambda code: tile_text(code, lang))
        goal_stages = [f"{ui['goal']} : {ui['unknown']}", f"{ui['goal']} : {ui['e4']}",
                       f"{ui['goal']} : {ui['red']}"] + [
            f"{ui['goal']} : {ui['badges_goal'].format(n=n)}" for n in range(1, 17)] + [
            f"{ui['goal']} : {ui['goal_pokedex']}", f"{ui['goal']} : {ui['goal_legendary']}"]
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

        def grid(title, codes, per_row=16):
            return [{"type": "text", "text": title, "margin": "4,6,4,1"},
                    {"type": "itemgrid", "item_margin": "2", "item_width": 54, "item_height": 45,
                     "h_alignment": "left",
                     "rows": [codes[i:i + per_row] for i in range(0, len(codes), per_row)]}]

        header = {
            "type": "array", "orientation": "vertical", "margin": "6,4",
            "content": [{"type": "item", "item": "goal", "width": 260, "height": 38, "h_alignment": "left"}]
            + grid(ui["key_items"], key_codes) + grid(ui["badges"], badge_codes)
            + grid(ui["leaders"], leader_codes) + grid(ui["hms"], hm_codes),
        }

        def map_tab(title, page):
            return {"title": title, "content": {"type": "map", "maps": [page]}}

        def region_tab(region, title):
            cats = []
            for cat in ("towns", "routes", "dungeons"):
                area_tabs = []
                for area in sorted((a for a in web_area_plans if plan_region(a) == region and category(a) == cat), key=order):
                    plans = web_area_plans[area]
                    area_title = area_name(area, lang) if area in en_names else plan_places[area][lang]
                    for plan in plans:
                        follow_tabs[plan] = [title, ui[cat], area_title, plan_places[plan][lang]]
                    if len(plans) == 1:
                        area_tabs.append(map_tab(area_title, f"plan_{plans[0]}"))
                    else:
                        area_tabs.append({"title": area_title, "content": {"type": "tabbed", "tabs": [
                            map_tab(plan_places[plan][lang], f"plan_{plan}") for plan in plans]}})
                if area_tabs:
                    cats.append({"title": ui[cat], "content": {"type": "tabbed", "tabs": area_tabs}})
            if not cats:
                return map_tab(title, region)
            return {"title": title, "content": {"type": "tabbed", "tabs": [map_tab(POP_TABS[lang]["overview"], region)] + cats}}

        main_tabs = {"type": "tabbed", "tabs": ([map_tab(POP_TABS[lang]["world"], "world")] if world else []) + [
            region_tab("johto", "Johto"),
            region_tab("kanto", "Kanto"),
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
        follow_tabs_by_lang[lang] = follow_tabs
        (root / "layouts/broadcast.json").write_text(json.dumps(broadcast_layout, indent=1, ensure_ascii=False),
                                                     encoding="utf-8")

    def add_gates(key, entry):
        entry.update(location_gates(key, LOCATIONS[key], loc_mod))
        return entry

    events = {}
    for key, data in LOCATIONS.items():
        if data["type"] == "event":
            events[data["event"]] = add_gates(key, {"region": data["region"], "ss_region": data.get("soulsilver_region")})
    lua_locations = {}
    for key, data in LOCATIONS.items():
        if data["type"] not in SECTION_TYPES:
            continue
        entry = {"type": data["type"], "region": data["region"]}
        if "soulsilver_region" in data:
            entry["ss_region"] = data["soulsilver_region"]
        lua_locations[key] = add_gates(key, entry)
    data_lua = {
        "regions": {key: list(region["exits"]) for key, region in REGIONS.items()},
        "exit_rules": {f"{src}>{dst}": _exit_rule_data(src, dst, r) for (src, dst), r in EXIT_RULES.items()},
        "events": events,
        "locations": lua_locations,
        "conditional": CONDITIONAL_CHECKS,
        "magnet_train_dropped_regions": {k: True for k in sorted(loc_mod.MAGNET_TRAIN_DROPPED_GATE_REGIONS)},
        "johto_only_excluded_hg": {k: True for k in sorted(reg_mod.johto_only_excluded_region_keys(False))},
        "johto_only_excluded_ss": {k: True for k in sorted(reg_mod.johto_only_excluded_region_keys(True))},
        "dark_entries": {f"{src}>{dst}": True for src, region in REGIONS.items() for dst in region["exits"]
                         if dst in REGIONS and rules_mod.is_dark_entry(src, dst)},
        "location_sections_by_lang": sections_by_lang,
        "plan_sections_by_lang": plan_sections_by_lang,
        "item_codes": {HEARTGOLD_ITEM_ID_BASE + ITEMS[c]["id"]: c for c in tracked},
        "tracked_items": tracked,
        "leaders": leader_codes,
        "leader_locations": {location_ids[k]: leader_codes[i] for i, k in enumerate(badge_locations)},
        "dexsanity_ids": [location_ids[k] for k in dex_keys],
    }
    (OUT / "scripts/data.lua").write_text(
        "-- Generated by tracker_gen.py, do not edit.\nDATA = " + lua(data_lua) + "\n", encoding="utf-8"
    )

    plan_of_id = {map_id: code for code, plan in detail.items() for map_id in plan.get("ids", [])}
    follow_lua = {
        "key": POSITION_KEY,
        "overworld": {"w": overworld["w"], "h": overworld["h"], "ids": list(overworld["ids"])} if overworld else None,
        "is_overworld": {map_id: True for map_id in sorted(set(overworld["ids"]))} if overworld else {},
        "plan_of_id": dict(sorted(plan_of_id.items())),
        "tabs_by_lang": follow_tabs_by_lang,
    }
    (OUT / "scripts/follow.lua").write_text("FOLLOW = " + lua(follow_lua) + "\n", encoding="utf-8")

    def check_entry(key):
        return {"key": key, "type": LOCATIONS[key]["type"], "vis": visibility_of(key),
                "name": {lang: section_name(key, lang) for lang in LANGS}}


    from data.encounters import ENCOUNTERS_HEARTGOLD
    from species import species_encounter_sources

    dex_id_of = {LOCATIONS[k]["species"]: location_ids[k] for k in dex_keys}
    dex_area = defaultdict(set)
    for species_key, sources in species_encounter_sources(ENCOUNTERS_HEARTGOLD).items():
        if species_key not in dex_id_of:
            continue
        for source in sources:
            for region, _items, _extra in loc_mod.dexsanity_source_requirements(species_key, source):
                if region in REGIONS:
                    dex_area[area_key(region)].add(dex_id_of[species_key])

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
                                           "johto_only_excluded_hg", "johto_only_excluded_ss", "dark_entries",
                                           "magnet_train_dropped_regions", "conditional")},
        "conditional": CONDITIONAL_CHECKS,
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
        "detail": detail,
        "npc_towns": npc_towns,
        "area_plans": web_area_plans,
        "plan_area": {code: plan_area[code] for code in (detail or {})},
        "overworld": overworld,
        "worlds": [
            {"key": "johto_kanto", "name": {"fr": "Johto et Kanto", "en": "Johto and Kanto"}, "hidden": False, "map": world},
        ],
        "position_key": POSITION_KEY,
        "region_area": {key: area_key(key) for key in REGIONS},
        "dex_area": {area: sorted(ids) for area, ids in sorted(dex_area.items())},
        "icons": _web_icons({code: ITEMS[code]["id"] for code in tracked if code in ITEMS}),
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


def _font(size: int):
    from PIL import ImageFont

    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(draw, text: str, width: int, size: int):
    while size > 10 and draw.textlength(text, font=_font(size)) > width:
        size -= 1
    font = _font(size)
    while draw.textlength(text, font=font) > width and len(text) > 2:
        text = text[:-2] + "."
    return text, font


def _wrap(draw, text: str, width: int, height: int, size: int, minimum: int = 9):
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


CONDITIONAL_CHECKS = {
    "route_39_moomoo_farm_house_tm83": {"fr": "7 Baies Oran", "en": "7 Oran Berries"},
    "route_39_moomoo_farm_stable_seal_case": {"fr": "7 Baies Oran", "en": "7 Oran Berries"},
}

SITE_NAMES = {"S:D23": "Radio Tower", "S:D35": "Rocket HQ", "S:P01": "S.S. Aqua", "S:D37": "Underground"}


MAP_UNIT = 16
PGMAP_C = SOURCES / "src/application/pokegear/map/pokegear_map.c"


def _pokegear_cells():
    consts = {}
    for line in MAPS_H.read_text().splitlines():
        m = re.match(r"#define (MAP_\w+)\s+\d+\s+//\s+MAP_(\w+)", line)
        if m:
            consts[m.group(1)] = m.group(2)
    table = PGMAP_C.read_text()
    table = table[table.index("sLocationSpecs[PGMAP_NUM_LOCATIONS]"):]
    cells = defaultdict(list)
    for const, x, y, w, h in re.findall(
        r"\.mapId = (MAP_\w+),\s*\.x = (\d+),\s*\.y = (\d+),\s*\.width = (\d+),\s*\.height = (\d+)", table
    ):
        code = consts.get(const)
        if code:
            cells[code] += [(int(x) + i, int(y) + j) for i in range(int(w)) for j in range(int(h))]
    return cells


def _web_map(areas, code_regions, parent_area):
    if not MAPS_H.is_file() or not PGMAP_C.is_file():
        print("no map sources: the web tracker gets no map")
        return None
    from PIL import Image, ImageDraw, ImageFilter

    spec = _pokegear_cells()
    area_cells = {}
    for code in areas:
        if code.startswith("S:"):
            family = code[2:]
            area_cells[code] = sorted({c for key, cells in spec.items() if key[:3] == family for c in cells})
        else:
            area_cells[code] = spec.get(code, [])
    width = max(x for cells in spec.values() for x, _ in cells) + 3
    height = max(y for cells in spec.values() for _, y in cells) + 3

    islands = {"T09", "D11R0101", "D40R0101", "P01R0301"}
    mainland = [c for key, cells in spec.items() if key[:1] != "W" and key not in islands for c in cells]
    sea_cells = [c for key, cells in spec.items() if key[:1] == "W" for c in cells]
    island_cells = [c for key in islands for c in spec.get(key, []) if key != "P01R0301"]
    roads = [c for key, cells in spec.items() if key[:1] in "TR" for c in cells]
    lowest = defaultdict(lambda: -1)
    for cx, cy in mainland:
        lowest[cx] = max(lowest[cx], cy)
    xs = sorted(lowest)
    coast = {x: max(lowest[n] for n in (x - 1, x, x + 1) if n in lowest) for x in range(xs[0], xs[-1] + 1)}
    scale = 8

    def raster(cells, grow):
        layer = Image.new("L", (width * scale, height * scale), 0)
        draw = ImageDraw.Draw(layer)
        for cx, cy in cells:
            draw.rectangle((cx * scale - grow, cy * scale - grow, (cx + 1) * scale + grow, (cy + 1) * scale + grow),
                           fill=255)
        return layer

    def smooth(layer, blur):
        layer = layer.resize((width * MAP_UNIT * 2, height * MAP_UNIT * 2), Image.BILINEAR)
        return layer.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: 255 if v > 128 else 0)

    def land_mask(grow, blur):
        layer = raster([(x, y) for x, bottom in coast.items() for y in range(0, bottom + 1)], grow)
        layer.paste(255, mask=raster(mainland, grow))
        layer.paste(0, mask=raster({(x, y2) for x, y in sea_cells for y2 in range(y, height)}, 0))
        layer.paste(255, mask=raster(island_cells, grow - 3))
        return smooth(layer, blur)

    img = Image.new("RGB", (width * MAP_UNIT * 2, height * MAP_UNIT * 2), (72, 152, 216))
    img.paste((121, 100, 64), mask=land_mask(5, 9))
    img.paste((216, 172, 104), mask=land_mask(3, 9))
    img.paste((144, 196, 104), mask=smooth(raster(roads, 2), 6))
    buffer = io.BytesIO()
    img.convert("P", palette=Image.ADAPTIVE, colors=16).save(buffer, "PNG", optimize=True)

    def centre(cell):
        return [cell[0] * MAP_UNIT + MAP_UNIT / 2, cell[1] * MAP_UNIT + MAP_UNIT / 2]

    owner = {}
    for code, cells in area_cells.items():
        if code[:1] in "TRW":
            for cell in cells:
                owner.setdefault(cell, code)
    shapes = {}
    for code in areas:
        cells = area_cells.get(code, [])
        if code.startswith("T") and cells:
            xs, ys = [c[0] for c in cells], [c[1] for c in cells]
            pad = MAP_UNIT * 0.18
            shapes[code] = {"kind": "town", "rect": [min(xs) * MAP_UNIT + pad, min(ys) * MAP_UNIT + pad,
                                                     (max(xs) - min(xs) + 1) * MAP_UNIT - 2 * pad,
                                                     (max(ys) - min(ys) + 1) * MAP_UNIT - 2 * pad]}
        elif code[0] in "RW" and cells:
            segments = []
            steps = ((1, 0), (0, 1), (-1, 0), (0, -1))
            own = set(cells)
            starts = [c for c in cells if any(owner.get((c[0] + dx, c[1] + dy)) not in (None, code) for dx, dy in steps)]
            seen = {(starts or cells)[0]}
            queue = deque(seen)
            while queue:
                cx, cy = queue.popleft()
                for dx, dy in steps:
                    nxt = (cx + dx, cy + dy)
                    if nxt in own and nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
                        segments.append(centre((cx, cy)) + centre(nxt))
            for cx, cy in cells:
                for dx, dy in steps:
                    other = owner.get((cx + dx, cy + dy))
                    if other is not None and other != code:
                        a, b = centre((cx, cy)), centre((cx + dx, cy + dy))
                        segments.append(a + [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])
            if not segments:
                x, y = centre(cells[0])
                segments.append([x - 4, y, x + 4, y])
            shapes[code] = {"kind": "route", "segs": segments}
        else:
            own = [c for c in cells if c not in owner]
            ring = 0.0
            if not own:
                parent = parent_area(code_regions[code][0])
                own = area_cells.get(parent) or cells
                if own:
                    xs, ys = [c[0] for c in own], [c[1] for c in own]
                    ring = max(max(xs) - min(xs) + 1, max(ys) - min(ys) + 1) * MAP_UNIT / 2 + MAP_UNIT * 0.1
            if own:
                points = [centre(c) for c in own]
                shapes[code] = {"kind": "site", "at": [sum(p[0] for p in points) / len(points),
                                                       sum(p[1] for p in points) / len(points)], "ring": ring}
    spots = defaultdict(list)
    for code, shape in shapes.items():
        if shape["kind"] == "site":
            spots[tuple(round(v) for v in shape["at"])].append(code)
    for (x, y), codes in spots.items():
        for i, code in enumerate(sorted(codes)):
            ring = shapes[code].pop("ring") or (5 if len(codes) > 1 else 0)
            angle = 2 * math.pi * i / max(len(codes), 1) - 0.8
            shapes[code]["at"] = [round(x + ring * math.cos(angle), 1), round(y + ring * math.sin(angle), 1)]
    return {"w": width * MAP_UNIT, "h": height * MAP_UNIT, "shapes": shapes,
            "bg": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")}


POSITION_KEY = "pokemon_hgss_singe_position_{team}_{slot}"
DETAIL_GIFT_OBJECTS = {
    "new_bark_elms_lab_1f_everstone": "obj_T20R0101_doctor",
    "new_bark_elms_lab_1f_s_s_ticket": "obj_T20R0101_doctor",
    "new_bark_elms_lab_1f_potion": "obj_T20R0101_assistantm",
    "cianwood_hm02": "obj_T24_middlewoman1_2",
    "route_30_mr_pokemon_house_mystery_egg": "obj_R30R0201_gsgentleman",
    "route_31_violet_gatehouse_vs_recorder": "obj_R31R0101_var_1",
    "ruins_of_alph_underground_hall_unown_report": "obj_D24R0205_gsassistantm",
    "goldenrod_tunnel_1f_fashion_case": "obj_D37R0101_var_1",
    "dragons_den_shrine_badge": "obj_D44R0103_chourou",
    "route_10_power_plant_broken_tm57": "obj_R10R0201_gsbigman",
}
NPC_CHECK_TYPES = ("npc_gift", "hm_tm", "badge", "trainer", "shop_item", "static_pokemon", "game_corner_prize")
NPC_NAMES = {
    "SHOPM1": ("Vendeur", "Clerk"),
    "DOCTOR": ("Prof. Orme", "Prof. Elm"),
    "OOKIDO": ("Prof. Chen", "Prof. Oak"),
    "ASSISTANTM": ("Assistant", "Lab Aide"),
    "GSASSISTANTM": ("Assistant", "Lab Aide"),
    "BABYBOY1": ("Petit garçon", "Little boy"),
    "GSBABYBOY1": ("Petit garçon", "Little boy"),
    "GSBABYGIRL1": ("Petite fille", "Little girl"),
    "CAPTAIN": ("Capitaine", "Captain"),
    "CHOUROU": ("Sage", "Elder"),
    "COUNTERM": ("Garde", "Guard"),
    "DANCER": ("Fille en kimono", "Kimono Girl"),
    "FISHING": ("Pêcheur", "Fisherman"),
    "GSBIGMAN": ("Monsieur", "Man"),
    "GSBOY1": ("Garçon", "Boy"),
    "GSBOY2": ("Garçon", "Boy"),
    "GSFIGHTER": ("Karatéka", "Black Belt"),
    "GSGENTLEMAN": ("Gentleman", "Gentleman"),
    "GSGIRL1": ("Fille", "Girl"),
    "GSMAN1": ("Homme", "Man"),
    "GSMAN3": ("Homme", "Man"),
    "GSMIDDLEMAN1": ("Monsieur", "Man"),
    "GSOLDMAN1": ("Vieil homme", "Old man"),
    "GSOLDWOMAN1": ("Vieille dame", "Old woman"),
    "GSWOMAN1": ("Femme", "Woman"),
    "GSWOMAN2": ("Femme", "Woman"),
    "MIDDLEWOMAN1": ("Dame", "Woman"),
    "KURUMI": ("DJ Mary", "DJ Mary"),
    "PICNICGIRL": ("Pique-niqueuse", "Picnicker"),
    "POLICEMAN": ("Policier", "Policeman"),
    "RGYARADOSU": ("Léviator rouge", "Red Gyarados"),
    "RKANBUM": ("Admin Rocket", "Rocket Executive"),
    "SUIT": ("Homme en costume", "Man in suit"),
    "SUNGLASSES": ("Homme à lunettes", "Man in sunglasses"),
    "USOKKY": ("Simularbre", "Sudowoodo"),
}
PLACE_NAMES = {
    "bell_tower_barrier_station": ("Poste de la Tour Carillon", "Bell Tower Barrier Station"),
    "bell_tower_barrier_station_corridor": ("Couloir du poste de la Tour Carillon", "Bell Tower Barrier Station Corridor"),
    "bellsprout_onyx_trade_house": ("Maison de l'échange Chétiflor-Onix", "Bellsprout-Onix Trade House"),
    "bike_maniac_house": ("Maison du fan de vélo", "Bike Maniac's House"),
    "bills_house": ("Maison de Léo", "Bill's House"),
    "cafe": ("Café", "Café"),
    "camerons_house": ("Maison de Cameron", "Cameron's House"),
    "central_house": ("Maison centrale", "Central House"),
    "condominiums_1f": ("Résidence 1F", "Condominiums 1F"),
    "condominiums_2f": ("Résidence 2F", "Condominiums 2F"),
    "condominiums_left_elevator": ("Résidence, ascenseur gauche", "Condominiums Left Elevator"),
    "condominiums_right_elevator": ("Résidence, ascenseur droit", "Condominiums Right Elevator"),
    "condominiums_roof": ("Résidence, toit", "Condominiums Roof"),
    "copycat_house_1f": ("Maison de Copieuse 1F", "Copycat's House 1F"),
    "copycat_house_2f": ("Maison de Copieuse 2F", "Copycat's House 2F"),
    "department_store_1f": ("Centre Commercial 1F", "Department Store 1F"),
    "department_store_2f": ("Centre Commercial 2F", "Department Store 2F"),
    "department_store_3f": ("Centre Commercial 3F", "Department Store 3F"),
    "department_store_4f": ("Centre Commercial 4F", "Department Store 4F"),
    "department_store_5f": ("Centre Commercial 5F", "Department Store 5F"),
    "department_store_6f": ("Centre Commercial 6F", "Department Store 6F"),
    "department_store_elevator": ("Centre Commercial, ascenseur", "Department Store Elevator"),
    "department_store_roof": ("Centre Commercial, toit", "Department Store Roof"),
    "east_house": ("Maison est", "East House"),
    "north_house": ("Maison nord", "North House"),
    "northeast_house": ("Maison nord-est", "Northeast House"),
    "northwest_house": ("Maison nord-ouest", "Northwest House"),
    "south_house": ("Maison sud", "South House"),
    "southeast_house": ("Maison sud-est", "Southeast House"),
    "southwest_house": ("Maison sud-ouest", "Southwest House"),
    "west_house": ("Maison ouest", "West House"),
    "elms_lab_1f": ("Labo d'Orme", "Elm's Lab"),
    "elms_lab_2f": ("Labo d'Orme 2F", "Elm's Lab 2F"),
    "fighting_dojo": ("Dojo Karaté", "Fighting Dojo"),
    "fishing_dude_house": ("Maison du pêcheur", "Fishing Dude's House"),
    "friendship_checker_house": ("Maison de l'amitié", "Friendship Checker's House"),
    "global_terminal_1f": ("Centre Mondial d'Échanges 1F", "Global Terminal 1F"),
    "global_terminal_2f": ("Centre Mondial d'Échanges 2F", "Global Terminal 2F"),
    "global_terminal_3f": ("Centre Mondial d'Échanges 3F", "Global Terminal 3F"),
    "guide_gent_house": ("Maison du guide", "Guide Gent's House"),
    "gym_room_1": ("Arène salle 1", "Gym Room 1"),
    "house_of_memories": ("Maison des souvenirs", "House of Memories"),
    "kirks_house": ("Maison de Kirk", "Kirk's House"),
    "kurt_house": ("Maison de Fargas", "Kurt's House"),
    "magnet_train_station_1f": ("Gare du Magnétrain", "Magnet Train Station"),
    "move_tutor_house": ("Maison du maître des capacités", "Move Tutor's House"),
    "mr_psychic_house": ("Maison de M. Psy", "Mr. Psychic's House"),
    "museum_of_science": ("Musée des Sciences", "Museum of Science"),
    "name_rater": ("Maison du juge des surnoms", "Name Rater's House"),
    "name_rater_house": ("Maison du juge des surnoms", "Name Rater's House"),
    "pal_park_entrance": ("Entrée du Parc des Amis", "Pal Park Entrance"),
    "player_house_1f": ("Maison du joueur 1F", "Player's House 1F"),
    "player_house_2f": ("Maison du joueur 2F", "Player's House 2F"),
    "pokecenter_1f": ("Centre Pokémon", "Pokémon Center"),
    "pokecenter_2f": ("Centre Pokémon 2F", "Pokémon Center 2F"),
    "pokecenter_b1f": ("Centre Pokémon B1F", "Pokémon Center B1F"),
    "pokemart": ("Boutique Pokémon", "Poké Mart"),
    "pokemon_league_entrance": ("Ligue Pokémon, entrée", "Pokémon League Entrance"),
    "pokemon_league_will_room": ("Ligue Pokémon, salle de Clément", "Pokémon League, Will's Room"),
    "pokemon_league_koga_room": ("Ligue Pokémon, salle de Koga", "Pokémon League, Koga's Room"),
    "pokemon_league_bruno_room": ("Ligue Pokémon, salle d'Aldo", "Pokémon League, Bruno's Room"),
    "pokemon_league_karen_room": ("Ligue Pokémon, salle de Marion", "Pokémon League, Karen's Room"),
    "pokemon_league_lance_room": ("Ligue Pokémon, salle de Peter", "Pokémon League, Lance's Room"),
    "pokemon_league_hall_of_fame": ("Ligue Pokémon, Panthéon", "Hall of Fame"),
    "pokemon_school": ("École Pokémon", "Pokémon School"),
    "prize_corner": ("Comptoir des lots", "Prize Corner"),
    "radio_station": ("Station de radio", "Radio Station"),
    "restaurant": ("Restaurant", "Restaurant"),
    "rival_house_1f": ("Maison du rival 1F", "Rival's House 1F"),
    "rival_house_2f": ("Maison du rival 2F", "Rival's House 2F"),
    "route_16_house": ("Route 16, maison", "Route 16 House"),
    "route_18_gatehouse": ("Route 18, poste de garde", "Route 18 Gatehouse"),
    "route_2_viridian_forest_north_gatehouse": ("Route 2, poste de garde nord de la Forêt de Jade", "Route 2 Viridian Forest North Gatehouse"),
    "safari_zone_warden_house": ("Maison du gardien du Parc Safari", "Safari Zone Warden's House"),
    "silph_co_elevator": ("Sylphe SARL, ascenseur", "Silph Co. Elevator"),
    "silph_co_hq": ("Sylphe SARL", "Silph Co. HQ"),
    "silph_co_rotom_room": ("Sylphe SARL, salle de Motisma", "Silph Co. Rotom Room"),
    "town_blues_house_1f": ("Maison de Blue 1F", "Blue's House 1F"),
    "town_blues_house_2f": ("Maison de Blue 2F", "Blue's House 2F"),
    "town_reds_house_1f": ("Maison de Red 1F", "Red's House 1F"),
    "town_reds_house_2f": ("Maison de Red 2F", "Red's House 2F"),
    "town_oaks_lab": ("Labo du Prof. Chen", "Prof. Oak's Lab"),
    "trainer_house_1f": ("Maison des Dresseurs 1F", "Trainer House 1F"),
    "trainer_house_b1f": ("Maison des Dresseurs B1F", "Trainer House B1F"),
    "volunteer_pokemon_house": ("Maison des bénévoles Pokémon", "Volunteer Pokémon House"),
}
ZONE_EVENTS = SOURCES / "files/fielddata/eventdata/zone_event"
MAP_HEADERS = SOURCES / "src/data/map_headers.h"
SCR_SEQ = SOURCES / "files/fielddata/script/scr_seq"
FLAGS_H = SOURCES / "include/constants/flags.h"
EVENT_KINDS = ("objects", "bgs", "coords")


def npc_name(sprite) -> dict:
    base = re.sub(r"_\d+$", "", (sprite or "").removeprefix("SPRITE_"))
    leader = re.fullmatch(r"GSLEADER(\d+)", base)
    if leader and 1 <= int(leader.group(1)) <= len(LEADERS["en"]):
        return {lang: LEADERS[lang][int(leader.group(1)) - 1] for lang in LANGS}
    fr_name, en_name = NPC_NAMES.get(base, ("PNJ", "NPC") if sprite else ("Événement", "Event"))
    return {"fr": fr_name, "en": en_name}


def _script_labels(path):
    labels, order = {}, []
    current = None
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.split("//")[0].rstrip()
        if not line.strip():
            continue
        head = re.match(r"^(\w+):$", line)
        if head:
            current = head.group(1)
            labels[current] = []
            order.append(current)
        elif current and line[0] in " \t":
            labels[current].append(line.strip())
    return labels, order


def _script_lines(labels, order, start):
    seen, stack, out = set(), [start], []
    while stack:
        label = stack.pop()
        if label in seen or label not in labels:
            continue
        seen.add(label)
        ended = False
        for line in labels[label]:
            out.append(line)
            stack.extend(tok for tok in re.findall(r"\b(_\w+|scr_seq_\w+)\b", line) if tok in labels)
            if line.split()[0] in ("End", "GoTo", "Return"):
                ended = True
                break
        if not ended and order.index(label) + 1 < len(order):
            stack.append(order[order.index(label) + 1])
    return out


def _words(line):
    return line.replace(",", " ").split()


class _MapEvents:
    def __init__(self):
        headers = MAP_HEADERS.read_text()
        self.files = {}
        pattern = r"\.scriptsBank = NARC_scr_seq_scr_seq_(\d+)_(\w+?)_bin,.*?\.eventsBank = NARC_zone_event_(\d+)_(\w+?)_bin"
        for m in re.finditer(pattern, headers, re.S):
            self.files.setdefault(m.group(4), (f"scr_seq_{m.group(1)}_{m.group(2)}.s", f"{m.group(3)}_{m.group(4)}.json"))
        self.flags = defaultdict(set)
        for line in FLAGS_H.read_text().splitlines():
            m = re.match(r"#define (FLAG_\w+)\s+(0x[0-9A-Fa-f]+|\d+)\b", line)
            if m:
                self.flags[int(m.group(2), 0)].add(m.group(1))
        self.cache = {}

    def events(self, code):
        if code not in self.cache:
            self.cache[code] = None
            if code in self.files:
                script_file, event_file = self.files[code]
                labels, order = _script_labels(SCR_SEQ / script_file)
                raw = json.loads((ZONE_EVENTS / event_file).read_text())
                entries = []
                for kind in EVENT_KINDS:
                    for event in raw.get(kind, []):
                        sid = event.get("scriptId")
                        lines = []
                        if isinstance(sid, str):
                            m = re.match(r"_EV_(scr_seq_\w+?_\d+) \+ 1", sid)
                            lines = _script_lines(labels, order, m.group(1)) if m else [sid]
                        entries.append((kind, event, lines))
                self.cache[code] = (raw, entries)
        return self.cache[code]

    def npc(self, code, key, data, flag):
        loaded = self.events(code)
        if loaded is None:
            return None
        raw, entries = loaded
        if key in DETAIL_GIFT_OBJECTS:
            return next((e for e in raw.get("objects", []) if e["id"] == DETAIL_GIFT_OBJECTS[key]), None)
        kind = data["type"]
        if kind == "trainer":
            name = "TRAINER_" + data["trainer"].upper()

            def test(event, lines):
                return any(name in _words(line) or line == f"std_trainer({name})" for line in lines)
        elif kind == "badge":
            badge = "BADGE_" + data["original_item"][6:].upper()

            def test(event, lines):
                return any(_words(line)[:2] == ["GiveBadge", badge] for line in lines)
        elif kind == "shop_item":
            def test(event, lines):
                return "SHOPM" in str(event.get("spriteId", ""))
        elif kind == "static_pokemon":
            def test(event, lines):
                return any(_words(line)[0] == "WildBattle" for line in lines)
        elif kind == "game_corner_prize":
            def test(event, lines):
                costs = {int(_words(line)[1]) for line in lines if _words(line)[0] == "TakeCoins"}
                return {2000, 4000, 6000} <= costs
        else:
            names = self.flags.get(flag, set()) if flag is not None else set()

            def test(event, lines):
                return any(_words(line)[0] == "SetFlag" and _words(line)[1:2] and _words(line)[1] in names for line in lines)
        found = [(EVENT_KINDS.index(k), len(lines), n, event) for n, (k, event, lines) in enumerate(entries) if test(event, lines)]
        if not found and data.get("original_item") and kind not in ("trainer", "badge", "shop_item", "static_pokemon", "game_corner_prize"):
            item = "ITEM_" + data["original_item"].upper()
            give = ("GiveItemNoCheck", "GoToIfNoItemSpace", "SetVar")
            found = [(EVENT_KINDS.index(k), len(lines), n, event) for n, (k, event, lines) in enumerate(entries)
                     if any(_words(line)[0] in give and item in _words(line) for line in lines)]
        return min(found, key=lambda f: f[:3])[3] if found else None


PLAN_PIXELS_PER_TILE = 8
POP_PLAN_SCALE = 2
POP_TABS = {"fr": {"world": "Monde", "overview": "Région"}, "en": {"world": "World", "overview": "Region"}}
POP_DOOR_FILL = (63, 208, 255)
POP_DOOR_DARK = (10, 12, 16)
POP_DOOR_LINE = (6, 34, 46)
POP_DOOR_TEXT = (11, 26, 36)
WORLD_PIXELS_PER_TILE = 2
WORLD_QUALITY = 88
GX_PARAMS = {
    0x00: 0, 0x10: 1, 0x11: 0, 0x12: 1, 0x13: 1, 0x14: 1, 0x15: 0, 0x16: 16, 0x17: 12, 0x18: 16,
    0x19: 12, 0x1A: 9, 0x1B: 3, 0x1C: 3, 0x20: 1, 0x21: 1, 0x22: 1, 0x23: 2, 0x24: 1, 0x25: 1,
    0x26: 1, 0x27: 1, 0x28: 1, 0x29: 1, 0x2A: 1, 0x2B: 1, 0x30: 1, 0x31: 1, 0x32: 1, 0x33: 1,
    0x34: 32, 0x40: 1, 0x41: 0, 0x50: 1, 0x60: 1, 0x70: 3, 0x71: 2, 0x72: 1,
}


def _s10(v):
    v &= 0x3FF
    return v - 0x400 if v & 0x200 else v


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def _nns_dict(blob, at):
    count = blob[at + 1]
    data_at = at + struct.unpack_from("<H", blob, at + 6)[0]
    size = struct.unpack_from("<H", blob, data_at)[0]
    names_at = data_at + 4 + count * size
    return [(blob[names_at + i * 16:names_at + i * 16 + 16].split(b"\0")[0].decode("ascii", "ignore"),
             blob[data_at + 4 + i * size:data_at + 4 + (i + 1) * size]) for i in range(count)]


class _Model:
    def __init__(self, blob):
        self.blob = blob
        mdl0 = struct.unpack_from("<I", blob, 16)[0]
        model = mdl0 + struct.unpack_from("<I", _nns_dict(blob, mdl0 + 8)[0][1], 0)[0]
        _size, sbc, mat, shp, _env = struct.unpack_from("<5I", blob, model)
        self.scale = struct.unpack_from("<i", blob, model + 28)[0] / 4096
        self.shapes = []
        for _name, entry in _nns_dict(blob, model + shp):
            shape = model + shp + struct.unpack_from("<I", entry, 0)[0]
            offset, size = struct.unpack_from("<II", blob, shape + 8)
            self.shapes.append((shape + offset, size))
        msec = model + mat
        tex_dict, pal_dict = struct.unpack_from("<HH", blob, msec)
        head = struct.Struct("<HHIIIIIIHHHHii")
        self.materials = []
        for _name, entry in _nns_dict(blob, msec + 4):
            at = msec + struct.unpack_from("<I", entry, 0)[0]
            fields = head.unpack_from(blob, at)
            poly, teximg, flag = fields[4], fields[6], fields[9]
            cur = at + head.size
            ss, st, ts, tt = 1.0, 1.0, 0.0, 0.0
            if flag & 1:
                if not flag & 2:
                    ss, st = (v / 4096 for v in struct.unpack_from("<ii", blob, cur))
                    cur += 8
                if not flag & 4:
                    cur += 4
                if not flag & 8:
                    ts, tt = (v / 4096 for v in struct.unpack_from("<ii", blob, cur))
            self.materials.append({"poly": poly, "teximg": teximg, "ss": ss, "st": st, "ts": ts, "tt": tt,
                                   "tex": None, "pal": None})
        for key, offset in (("tex", tex_dict), ("pal", pal_dict)):
            for name, entry in _nns_dict(blob, msec + offset):
                list_at, count = struct.unpack_from("<HB", entry, 0)
                for i in range(count):
                    index = blob[msec + list_at + i]
                    if index < len(self.materials):
                        self.materials[index][key] = name
        self.draws = []
        at, current = model + sbc, 0
        while at < msec:
            op = blob[at]
            cmd = op & 0x1F
            if cmd == 0x01:
                break
            if cmd == 0x04:
                current = blob[at + 1]
            elif cmd == 0x05:
                self.draws.append((current, blob[at + 1]))
            step = {0x00: 1, 0x02: 3, 0x03: 2, 0x04: 2, 0x05: 2, 0x0B: 1, 0x0C: 3, 0x0D: 3}.get(cmd)
            if cmd == 0x06:
                step = 4 + {0x00: 0, 0x20: 1, 0x40: 1, 0x60: 2}[op & 0x60]
            elif cmd in (0x07, 0x08):
                step = 2 + bool(op & 0x40) + bool(op & 0x20)
            elif cmd == 0x09:
                step = 3 + blob[at + 2] * 2
            if step is None:
                break
            at += step

    def triangles(self, shape):
        start, size = self.shapes[shape]
        blob, scale = self.blob, self.scale / 4096
        at, end = start, start + size
        vtx, tc, prim, strip, tris = [0, 0, 0], (0.0, 0.0), None, [], []
        while at + 4 <= end:
            cmds = blob[at:at + 4]
            at += 4
            for cmd in cmds:
                count = GX_PARAMS.get(cmd, 0)
                params = struct.unpack_from(f"<{count}I", blob, at) if count else ()
                at += 4 * count
                if cmd == 0x40:
                    prim, strip = params[0] & 3, []
                    continue
                if cmd == 0x22:
                    tc = (_s16(params[0]) / 16, _s16(params[0] >> 16) / 16)
                    continue
                if cmd == 0x23:
                    vtx = [_s16(params[0]), _s16(params[0] >> 16), _s16(params[1])]
                elif cmd == 0x24:
                    vtx = [_s10(params[0]) << 6, _s10(params[0] >> 10) << 6, _s10(params[0] >> 20) << 6]
                elif cmd == 0x25:
                    vtx = [_s16(params[0]), _s16(params[0] >> 16), vtx[2]]
                elif cmd == 0x26:
                    vtx = [_s16(params[0]), vtx[1], _s16(params[0] >> 16)]
                elif cmd == 0x27:
                    vtx = [vtx[0], _s16(params[0]), _s16(params[0] >> 16)]
                elif cmd == 0x28:
                    vtx = [vtx[0] + _s10(params[0]) / 8, vtx[1] + _s10(params[0] >> 10) / 8, vtx[2] + _s10(params[0] >> 20) / 8]
                else:
                    continue
                strip.append((vtx[0] * scale, vtx[1] * scale, vtx[2] * scale, tc[0], tc[1]))
                n = len(strip)
                if prim == 0 and n % 3 == 0:
                    tris.append(strip[-3:])
                elif prim == 1 and n % 4 == 0:
                    tris += [[strip[-4], strip[-3], strip[-2]], [strip[-4], strip[-2], strip[-1]]]
                elif prim == 2 and n >= 3:
                    tris.append(strip[-3:])
                elif prim == 3 and n >= 4 and n % 2 == 0:
                    tris += [[strip[-4], strip[-3], strip[-1]], [strip[-4], strip[-1], strip[-2]]]
        return tris


def _bgr555(values):
    import numpy as np

    v = np.asarray(values, dtype=np.uint32)
    return np.stack([(v & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v >> 10 & 31) * 255 // 31], axis=-1).astype(np.uint8)


def _decode_texture(texture, palette):
    import numpy as np

    fmt, w, h = int(texture.format), texture.width, texture.height
    n = w * h
    raw = np.frombuffer(bytes(texture.data1), dtype=np.uint8)
    colors = [c.r | c.g << 5 | c.b << 10 for c in palette.colors] if palette is not None else []
    pal = _bgr555(colors or [0])
    alpha = np.full(n, 255, dtype=np.uint8)
    if fmt == 7:
        v = np.frombuffer(bytes(texture.data1)[:n * 2], dtype="<u2")
        return np.dstack([_bgr555(v).reshape(h, w, 3), np.where(v & 0x8000, 255, 0).astype(np.uint8).reshape(h, w)])
    if fmt == 5:
        blocks = np.frombuffer(bytes(texture.data1), dtype="<u4")
        info = np.frombuffer(bytes(texture.data2), dtype="<u2")
        out = np.zeros((h, w, 4), dtype=np.uint8)
        for bi in range(min(len(blocks), (w // 4) * (h // 4))):
            word, extra = int(blocks[bi]), int(info[bi]) if bi < len(info) else 0
            base, mode = (extra & 0x3FFF) * 2, extra >> 14
            pick = [pal[min(base + i, len(pal) - 1)].astype(np.int32) for i in range(4)]
            c0, c1 = pick[0], pick[1]
            if mode == 0:
                cs, al = [c0, c1, pick[2], c0], [255, 255, 255, 0]
            elif mode == 1:
                cs, al = [c0, c1, (c0 + c1) // 2, c0], [255, 255, 255, 0]
            elif mode == 2:
                cs, al = pick, [255] * 4
            else:
                cs, al = [c0, c1, (c0 * 5 + c1 * 3) // 8, (c0 * 3 + c1 * 5) // 8], [255] * 4
            by, bx = (bi // (w // 4)) * 4, (bi % (w // 4)) * 4
            for i in range(16):
                k = word >> (i * 2) & 3
                out[by + i // 4, bx + i % 4] = (*cs[k], al[k])
        return out
    if fmt == 1:
        idx, alpha = raw[:n] & 31, ((raw[:n] >> 5) * 255 // 7).astype(np.uint8)
    elif fmt == 6:
        idx, alpha = raw[:n] & 7, ((raw[:n] >> 3) * 255 // 31).astype(np.uint8)
    elif fmt == 2:
        idx = np.stack([raw & 3, raw >> 2 & 3, raw >> 4 & 3, raw >> 6 & 3], axis=-1).reshape(-1)[:n]
    elif fmt == 3:
        idx = np.stack([raw & 15, raw >> 4], axis=-1).reshape(-1)[:n]
    else:
        idx = raw[:n]
    idx = np.minimum(idx.astype(np.int64), len(pal) - 1)
    if fmt in (2, 3, 4) and texture.isColor0Transparent:
        alpha = np.where(idx == 0, 0, 255).astype(np.uint8)
    return np.dstack([pal[idx].reshape(h, w, 3), alpha.reshape(h, w)])


class _TexSet:
    def __init__(self, blob):
        import ndspy.texture

        self.textures, self.palettes, self.cache = {}, {}, {}
        if blob[:4] == b"BTX0":
            nsbtx = ndspy.texture.NSBTX(blob)
            self.textures, self.palettes = dict(nsbtx.textures), dict(nsbtx.palettes)

    def image(self, tex, pal):
        if (tex, pal) not in self.cache:
            texture = self.textures.get(tex)
            try:
                self.cache[(tex, pal)] = None if texture is None else _decode_texture(texture, self.palettes.get(pal))
            except (ValueError, IndexError):
                self.cache[(tex, pal)] = None
        return self.cache[(tex, pal)]


class _Canvas:
    def __init__(self, width, height):
        import numpy as np

        self.np = np
        self.rgb = np.zeros((height, width, 3), dtype=np.uint8)
        self.rgb[:] = (24, 24, 28)
        self.depth = np.full((height, width), -1e9, dtype=np.float32)

    def wrap(self, v, size, repeat, flip):
        i = self.np.floor(v).astype(self.np.int64)
        if repeat and flip:
            period = i % (2 * size)
            return self.np.where(period < size, period, 2 * size - 1 - period)
        return i % size if repeat else self.np.clip(i, 0, size - 1)

    def draw(self, tri, image, mat):
        np = self.np
        h, w = self.depth.shape
        (x0, y0, d0, s0, t0), (x1, y1, d1, s1, t1), (x2, y2, d2, s2, t2) = tri
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-6:
            return
        minx, maxx = max(int(math.floor(min(x0, x1, x2))), 0), min(int(math.ceil(max(x0, x1, x2))), w - 1)
        miny, maxy = max(int(math.floor(min(y0, y1, y2))), 0), min(int(math.ceil(max(y0, y1, y2))), h - 1)
        if minx > maxx or miny > maxy:
            return
        px, py = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        a = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) / area
        b = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) / area
        c = 1 - a - b
        depth = a * d0 + b * d1 + c * d2
        region = self.depth[miny:maxy + 1, minx:maxx + 1]
        mask = (a >= -1e-4) & (b >= -1e-4) & (c >= -1e-4) & (depth >= region - 0.01)
        if not mask.any():
            return
        if image is None:
            color = np.empty(px.shape + (4,), dtype=np.uint8)
            color[:] = (70, 70, 78, 255)
        else:
            th, tw = image.shape[:2]
            teximg = mat["teximg"]
            s = self.wrap((a * s0 + b * s1 + c * s2) * mat["ss"] + mat["ts"], tw, teximg >> 16 & 1, teximg >> 18 & 1)
            t = self.wrap((a * t0 + b * t1 + c * t2) * mat["st"] + mat["tt"], th, teximg >> 17 & 1, teximg >> 19 & 1)
            color = image[t, s]
            mask &= color[..., 3] >= 128
        self.rgb[miny:maxy + 1, minx:maxx + 1][mask] = color[..., :3][mask]
        region[mask] = depth[mask]

    def model(self, model, texset, transform):
        for mat_id, shape in model.draws:
            if shape >= len(model.shapes) or mat_id >= len(model.materials):
                continue
            mat = model.materials[mat_id]
            if not mat["poly"] >> 16 & 31:
                continue
            image = texset.image(mat["tex"], mat["pal"]) if mat["tex"] else None
            for tri in model.triangles(shape):
                self.draw([transform(v) for v in tri], image, mat)


class _PlanRenderer:
    def __init__(self, rom):
        self.rom = rom
        self.lands = rom.read_narc("a/0/6/5").files
        self.areas = rom.read_narc("a/0/4/2").files
        self.map_tex = rom.read_narc("a/0/4/4").files
        self.prop_tex = rom.read_narc("a/0/7/0").files
        self.archives = {1: rom.read_narc("a/0/4/0").files, 0: rom.read_narc("a/1/4/8").files}
        self.textures, self.models = {}, {}

    def texset(self, kind, index):
        if (kind, index) not in self.textures:
            files = self.map_tex if kind == "map" else self.prop_tex
            self.textures[(kind, index)] = _TexSet(bytes(files[index]) if index < len(files) else b"")
        return self.textures[(kind, index)]

    def prop(self, field, index):
        if (field, index) not in self.models:
            files = self.archives[field]
            try:
                self.models[(field, index)] = _Model(bytes(files[index])) if index < len(files) else None
            except (struct.error, IndexError, KeyError):
                self.models[(field, index)] = None
        return self.models[(field, index)]

    def render(self, chunks, x0, y0, x1, y1, pixels=PLAN_PIXELS_PER_TILE, quality=None):
        from PIL import Image

        k = pixels / 16
        canvas = _Canvas((x1 - x0 + 1) * pixels, (y1 - y0 + 1) * pixels)
        for cx, cy, land_id, area_id in chunks:
            if cx * 32 > x1 or cx * 32 + 31 < x0 or cy * 32 > y1 or cy * 32 + 31 < y0:
                continue
            list_id, tex_id, _unk, field, _flag = struct.unpack_from("<3HBB", bytes(self.areas[area_id]), 0)
            field = 1 if field else 0
            map_tex, prop_tex = self.texset("map", tex_id), self.texset("prop", list_id)
            land = bytes(self.lands[land_id])
            sizes = struct.unpack_from("<4I", land, 0)
            props_at = 0x14 + struct.unpack_from("<H", land, 0x12)[0] + sizes[0]
            model_at = props_at + sizes[1]
            bx, bz = (cx * 32 + 16 - x0) * 16, (cy * 32 + 16 - y0) * 16
            try:
                terrain = _Model(land[model_at:model_at + sizes[2]])
            except (struct.error, IndexError, KeyError):
                continue
            canvas.model(terrain, map_tex, lambda v: ((bx + v[0]) * k, (bz + v[2]) * k, v[1], v[3], v[4]))
            for i in range(sizes[1] // 48):
                entry = struct.unpack_from("<I3i3i3i", land, props_at + i * 48)
                model = self.prop(field, entry[0])
                if model is None:
                    continue
                px, py, pz = (v / 4096 for v in entry[1:4])
                sx, sy, sz = (v / 4096 or 1 for v in entry[7:10])
                angle = entry[5] / 65536 * 2 * math.pi
                ca, sa = math.cos(angle), math.sin(angle)

                def place(v, px=px, py=py, pz=pz, sx=sx, sy=sy, sz=sz, ca=ca, sa=sa, bx=bx, bz=bz):
                    x, y, z = v[0] * sx, v[1] * sy, v[2] * sz
                    return ((bx + px + x * ca + z * sa) * k, (bz + pz - x * sa + z * ca) * k, py + y, v[3], v[4])
                canvas.model(model, prop_tex, place)
        buffer = io.BytesIO()
        if quality is None:
            Image.fromarray(canvas.rgb).save(buffer, "WEBP", lossless=True)
        else:
            Image.fromarray(canvas.rgb).save(buffer, "WEBP", quality=quality, method=6)
        return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _detail_maps(location_ids, code_regions, places, npc_label, plan_area=None, area_names=None):
    rom_path = os.environ.get("HEARTGOLD_ROM_PATH")
    if not rom_path or not MAP_HEADERS.is_file() or not places:
        return None, None, None
    from data.locations import LOCATIONS
    from location_flags import flag_id_for_location
    from rom import HeartGoldRom
    from rom.apricorntreedata import TREE_POSITIONS

    rom = HeartGoldRom.open(rom_path)
    matrices = rom.read_narc("a/0/4/1").files
    land = rom.read_narc("a/0/6/5").files
    consts = {}
    for line in MAPS_H.read_text().splitlines():
        m = re.match(r"#define (MAP_\w+)\s+(\d+)\s+//\s+MAP_(\w+)", line)
        if m:
            consts[m.group(1)] = (int(m.group(2)), m.group(3))
    code_of_const = {const: code for const, (_, code) in consts.items()}
    code_of_id = {num: code for num, code in consts.values()}
    headers_src = MAP_HEADERS.read_text()
    events = _MapEvents()
    renderer = _PlanRenderer(rom)

    def matrix(index):
        raw = bytes(matrices[index])
        w, h, has_headers, has_alt, name_len = raw[0], raw[1], raw[2], raw[3], raw[4]
        cursor = 5 + name_len
        heads = None
        if has_headers:
            heads = struct.unpack_from(f"<{w * h}H", raw, cursor)
            cursor += w * h * 2
        if has_alt:
            cursor += w * h
        return w, h, heads, struct.unpack_from(f"<{w * h}H", raw, cursor)

    def chunk(model):
        raw = bytes(land[model])
        return struct.unpack_from("<1024H", raw, 0x14 + struct.unpack_from("<H", raw, 0x12)[0])

    area_of_id = {}
    for const, (num, _code) in consts.items():
        at = headers_src.find(f"[{const}] = {{")
        found = re.search(r"\.areaDataBank = (\d+)", headers_src[at:at + 2000]) if at >= 0 else None
        if found:
            area_of_id[num] = int(found.group(1))
    ow_w, ow_h, ow_heads, ow_models = matrix(0)
    overworld_chunks = [(cx, cy, ow_models[cy * ow_w + cx], area_of_id.get(ow_heads[cy * ow_w + cx], 0))
                        for cy in range(ow_h) for cx in range(ow_w) if ow_models[cy * ow_w + cx] != 0xFFFF]

    def tiles_of(code):
        const = next(c for c, (_, k) in consts.items() if k == code)
        block = headers_src[headers_src.index(f"[{const}] = {{"):]
        index = int(re.search(r"map_matrix_(\d+)_", block).group(1))
        area = int(re.search(r"\.areaDataBank = (\d+)", block).group(1))
        w, h, heads, models = matrix(index)
        out, chunks = {}, []
        for cy in range(h):
            for cx in range(w):
                if models[cy * w + cx] == 0xFFFF:
                    continue
                if index == 0 and code_of_id.get(heads[cy * w + cx]) != code:
                    continue
                chunks.append((cx, cy, models[cy * w + cx], area))
                for i, t in enumerate(chunk(models[cy * w + cx])):
                    out[(cx * 32 + i % 32, cy * 32 + i // 32)] = t
        return out, (overworld_chunks if index == 0 else chunks), index == 0

    ids_of = defaultdict(list)
    for num, code in code_of_id.items():
        ids_of[code].append(num)
    plans = {}
    for code, name in places.items():
        loaded = events.events(code)
        if loaded is None:
            continue
        raw = loaded[0]
        tiles, chunks, overworld = tiles_of(code)
        warps = [(w["x"], w["z"], code_of_const.get(w["header"])) for w in raw.get("warps", [])]
        warp_at = {(x, z) for x, z, _ in warps}
        reached = set(warp_at)
        queue = deque(warp_at)
        while queue:
            x, y = queue.popleft()
            for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                t = tiles.get(nxt)
                if nxt not in reached and t is not None and (not t & 0x8000 or nxt in warp_at):
                    reached.add(nxt)
                    queue.append(nxt)
        if overworld or not reached:
            reached = set(tiles)
        spots, npcs = {}, {}
        for key, data in LOCATIONS.items():
            if key not in location_ids or data["region"] not in code_regions.get(code, ()):
                continue
            npc = None
            if data["type"] == "apricorn_tree":
                spot = TREE_POSITIONS[data["id"]]
            elif data["type"] == "bug_contest":
                if not warps:
                    continue
                spot = (warps[0][0], warps[0][1] - 1)
            elif key in DETAIL_GIFT_OBJECTS or ("x" not in data and data["type"] in NPC_CHECK_TYPES):
                npc = events.npc(code, key, data, flag_id_for_location(key))
                if npc is None:
                    continue
                spot = (npc["x"], npc["z"])
            elif "x" in data and "z" in data:
                spot = (data["x"], data["z"])
            else:
                continue
            entry = spots.setdefault(spot, {"ids": [], "npc": None})
            entry["ids"].append(location_ids[key])
            if npc is not None and data["type"] != "trainer":
                group = npcs.setdefault(spot, {"keys": [], "sprite": npc.get("spriteId")})
                group["keys"].append(key)
        for spot, group in npcs.items():
            spots[spot]["npc"] = npc_label(group["keys"], group["sprite"])
        points = reached | set(spots)
        if not points:
            continue
        x0, x1 = min(p[0] for p in points) - 1, max(p[0] for p in points) + 1
        y0, y1 = min(p[1] for p in points) - 1, max(p[1] for p in points) + 1
        plans[code] = {
            "name": name, "w": x1 - x0 + 1, "h": y1 - y0 + 1, "x0": x0, "y0": y0, "ids": sorted(ids_of[code]),
            "img": renderer.render(chunks, x0, y0, x1, y1),
            "warps": [{"x": x - x0, "y": z - y0, "to": to} for x, z, to in warps],
            "checks": [{"x": x - x0, "y": z - y0, "ids": entry["ids"], **({"npc": entry["npc"]} if entry["npc"] else {})}
                       for (x, z), entry in spots.items()],
            "npcs": [{"name": spots[spot]["npc"], "ids": [location_ids[k] for k in group["keys"]]}
                     for spot, group in npcs.items()],
        }
    world = _world_map(renderer, events, overworld_chunks, ow_w, ow_heads, code_of_id, code_of_const, places,
                       plan_area or {}, area_names or {})
    return plans, {"w": ow_w, "h": ow_h, "ids": list(ow_heads)}, world


def _data_image(uri: str):
    from PIL import Image

    return Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))


def _exit_rule_data(src: str, dst: str, requirement: dict) -> dict:
    import rules as rules_mod

    count = rules_mod.COUNT_RULES.get((src, dst))
    if count is not None and count.get("waived_events"):
        rest = requirement
    else:
        rest, count = rules_mod.counted_requirement(src, dst, requirement)
    entry = {"items": list(rest["items"]), "badges": list(rest["badges"]), "events": list(rest["events"])}
    if count is not None:
        entry["count"] = {
            "option": count["option"], "default": count["default"],
            "badges": list(count.get("badges", ())), "events": list(count.get("events", ())),
        }
        if count.get("waived_events"):
            entry["count"]["waived_events"] = list(count["waived_events"])
    return entry


def _poptracker_images(detail, world) -> None:
    from PIL import Image, ImageDraw

    tile = PLAN_PIXELS_PER_TILE * POP_PLAN_SCALE
    font = _font(int(tile * 0.72))
    folder = OUT / "images/plans"
    folder.mkdir(parents=True, exist_ok=True)
    for code, plan in detail.items():
        image = _data_image(plan["img"]).convert("RGB")
        image = image.resize((image.width * POP_PLAN_SCALE, image.height * POP_PLAN_SCALE), Image.NEAREST)
        draw = ImageDraw.Draw(image)
        doors = []
        for warp in plan["warps"]:
            target = warp.get("to") or ""
            if target not in doors:
                doors.append(target)
            cx, cy, r = (warp["x"] + 0.5) * tile, (warp["y"] + 0.5) * tile, tile * 0.62
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=POP_DOOR_FILL if target else POP_DOOR_DARK,
                         outline=POP_DOOR_LINE if target else POP_DOOR_FILL, width=2)
            draw.text((cx, cy), str(doors.index(target) + 1), fill=POP_DOOR_TEXT if target else POP_DOOR_FILL,
                      font=font, anchor="mm")
        image.save(folder / f"{code}.png", optimize=True)
    if world:
        _data_image(world["img"]).convert("RGB").save(OUT / "images/world.png", optimize=True)


def _world_pin(world, code):
    area = world["areas"].get(code)
    if area and area["cells"]:
        x = sum(cell[0] + 16 for cell in area["cells"]) / len(area["cells"])
        y = sum(cell[1] + 16 for cell in area["cells"]) / len(area["cells"])
        return round(x * WORLD_PIXELS_PER_TILE), round(y * WORLD_PIXELS_PER_TILE)
    site = world["sites"].get(code)
    if site:
        return round((site["at"][0] + 0.5) * WORLD_PIXELS_PER_TILE), round((site["at"][1] + 0.5) * WORLD_PIXELS_PER_TILE)
    return None


def _world_map(renderer, events, chunks, width, heads, code_of_id, code_of_const, places, plan_area, area_names):
    cells = {(cx, cy): code_of_id.get(heads[cy * width + cx]) for cx, cy, _land, _area in chunks}
    cells = {cell: code for cell, code in cells.items() if code}
    cx0, cx1 = min(c[0] for c in cells), max(c[0] for c in cells)
    cy0, cy1 = min(c[1] for c in cells), max(c[1] for c in cells)
    x0, y0 = cx0 * 32, cy0 * 32
    image = renderer.render(chunks, x0, y0, cx1 * 32 + 31, cy1 * 32 + 31, pixels=WORLD_PIXELS_PER_TILE, quality=WORLD_QUALITY)
    areas = {}
    for (cx, cy), code in sorted(cells.items()):
        entry = areas.setdefault(code, {"cells": [], "name": places.get(code, {"fr": code, "en": code})})
        entry["cells"].append([(cx - cx0) * 32, (cy - cy0) * 32])
    edges = []
    for (cx, cy), code in cells.items():
        for dx, dy, segment in ((1, 0, (32, 0, 32, 32)), (0, 1, (0, 32, 32, 32)), (-1, 0, (0, 0, 0, 32)), (0, -1, (0, 0, 32, 0))):
            other = cells.get((cx + dx, cy + dy))
            if other != code and (other is None or (dx, dy) in ((1, 0), (0, 1))):
                bx, by = (cx - cx0) * 32, (cy - cy0) * 32
                edges.append([bx + segment[0], by + segment[1], bx + segment[2], by + segment[3]])
    sites = {}
    for code in sorted(set(cells.values())):
        loaded = events.events(code)
        if loaded is None:
            continue
        for warp in loaded[0].get("warps", []):
            target = code_of_const.get(warp["header"])
            area = plan_area.get(target)
            if not area or area in cells.values() or area in sites:
                continue
            sites[area] = {"at": [warp["x"] - x0, warp["z"] - y0], "name": area_names.get(area, {"fr": area, "en": area})}
    return {"w": (cx1 - cx0 + 1) * 32, "h": (cy1 - cy0 + 1) * 32, "x0": x0, "y0": y0, "img": image, "areas": areas,
            "edges": edges, "sites": sites}


LEADER_CLASSES = (66, 67, 70, 72, 75, 74, 73, 76, 98, 103, 104, 105, 106, 107, 108, 110)
ITEM_C = SOURCES / "src/item.c"
ITEMS_H = SOURCES / "include/constants/items.h"


def _nitro_palette(raw, base=0, count=16):
    raw = bytes(raw)
    c = raw.index(b"TTLP")
    _, _, size, off = struct.unpack_from("<IIII", raw, c + 8)
    words = struct.unpack_from(f"<{size // 2}H", raw, c + 8 + off)[base:base + count]
    return [((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31) for v in words]


def _nitro_tiles(raw, first_tile, tiles_wide, tiles_high, palette):
    from PIL import Image

    raw = bytes(raw)
    c = raw.index(b"RAHC")
    size, off = struct.unpack_from("<II", raw, c + 24)
    data = raw[c + 8 + off: c + 8 + off + size]
    img = Image.new("RGBA", (tiles_wide * 8, tiles_high * 8))
    px = img.load()
    for t in range(tiles_wide * tiles_high):
        start = (first_tile + t) * 32
        for i in range(32):
            b = data[start + i]
            for k, v in enumerate((b & 15, b >> 4)):
                if v:
                    px[(t % tiles_wide) * 8 + (i % 4) * 2 + k, (t // tiles_wide) * 8 + i // 4] = palette[v] + (255,)
    return img


def _web_icons(item_ids):
    rom_path = os.environ.get("HEARTGOLD_ROM_PATH")
    if not rom_path or not ITEM_C.is_file():
        return None
    from rom import HeartGoldRom

    rom = HeartGoldRom.open(rom_path)
    icons = {}

    def uri(img):
        buffer = io.BytesIO()
        img.save(buffer, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    numbers = {m.group(1): int(m.group(2)) for m in re.finditer(r"#define (ITEM_\w+)\s+(\d+)", ITEMS_H.read_text())}
    table = {}
    for const, ncgr, nclr in re.findall(
        r"\[(ITEM_\w+)\] = \{ NARC_item_data_\d+_bin, NARC_item_icon_item_icon_(\d+)_NCGR, NARC_item_icon_item_icon_(\d+)_NCLR",
        ITEM_C.read_text(),
    ):
        if const in numbers:
            table[numbers[const]] = (int(ncgr), int(nclr))
    item_narc = rom.read_narc("a/0/1/8").files
    for code, item_id in item_ids.items():
        if item_id in table:
            ncgr, nclr = table[item_id]
            icons[code] = uri(_nitro_tiles(item_narc[ncgr], 0, 4, 4, _nitro_palette(item_narc[nclr])))

    card = rom.read_narc("a/0/4/9").files
    for index, badge in enumerate(BADGE_ORDER):
        shades = _nitro_palette(card[index], 16, 16)
        gold = []
        for r, g, b in shades:
            lum = (r * 299 + g * 587 + b * 114) / 255000
            gold.append((int(70 + 185 * lum), int(45 + 180 * lum), int(10 + 120 * lum)))
        icons[f"badge_{badge}"] = uri(_nitro_tiles(card[46], index * 12 * 16, 4, 4, gold))

    pictures = rom.read_narc("a/0/5/8").files
    for badge, trainer_class in zip(BADGE_ORDER, LEADER_CLASSES):
        palette = _nitro_palette(pictures[trainer_class * 5 + 1])
        icons[f"leader_{badge}"] = uri(_nitro_tiles(pictures[trainer_class * 5], 0, 8, 8, palette))
    return icons


def _site_name(region_keys) -> str:
    name = min(region_keys, key=len)
    name = re.sub(r"_(b?\d+f.*|entrance.*|outside|room.*|chamber.*|route_\d+_side|lower.*|upper.*)$", "", name)
    return pretty(name)


if __name__ == "__main__":
    build()
