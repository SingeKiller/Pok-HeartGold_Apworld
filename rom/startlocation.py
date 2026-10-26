from __future__ import annotations

from rom import HeartGoldRom


_ZONE_EVENT_ELMS_LAB_INDEX = 58
_WARP_TARGET_WORD_INDEX = 91
_WARP_TARGET_BYTE_OFFSET = _WARP_TARGET_WORD_INDEX * 4
_VANILLA_WARP_TARGET = 60

TOWN_MAP_IDS: dict[str, int] = {
    "cherrygrove": 67,
    "violet": 73,
    "azalea": 74,
    "cianwood": 75,
    "goldenrod": 76,
    "olivine": 77,
    "ecruteak": 78,
    "mahogany": 87,
    "blackthorn": 89,
}

_TOWN_ENTRANCE_ANCHORS: dict[str, int] = {}


def write_exit_warp_target(rom: HeartGoldRom, town_key: str) -> None:
    import struct

    from rom import eventdata

    if town_key not in TOWN_MAP_IDS:
        raise ValueError(f"unknown start-location town {town_key!r}, expected one of {sorted(TOWN_MAP_IDS)}")

    entry = bytearray(eventdata.read_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX))
    (current,) = struct.unpack_from("<I", entry, _WARP_TARGET_BYTE_OFFSET)
    if current != _VANILLA_WARP_TARGET:
        raise ValueError(
            f"Elm's Lab zone_event entry's warp-target word is {current}, expected the vanilla "
            f"value {_VANILLA_WARP_TARGET} (MAP_NEW_BARK) -- data_gen may have drifted from "
            "the real ROM, refusing to guess."
        )
    anchor = _TOWN_ENTRANCE_ANCHORS.get(town_key, 0)
    struct.pack_into(
        "<I", entry, _WARP_TARGET_BYTE_OFFSET, TOWN_MAP_IDS[town_key] | (anchor << 16)
    )
    eventdata.write_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX, bytes(entry))


_ELMS_LAB_GREETING_COORD_H_BYTE_OFFSET = 400
_VANILLA_ELMS_LAB_GREETING_COORD_H = 1
_ELMS_LAB_GREETING_COORD_H = 6


def write_elms_lab_greeting_zone_extension(rom: HeartGoldRom) -> None:
    import struct

    from rom import eventdata

    entry = bytearray(eventdata.read_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX))
    (current_h,) = struct.unpack_from("<H", entry, _ELMS_LAB_GREETING_COORD_H_BYTE_OFFSET)
    if current_h != _VANILLA_ELMS_LAB_GREETING_COORD_H:
        raise ValueError(
            f"Elm's Lab zone_event entry's greeting-CoordEvent h is {current_h}, expected the "
            f"vanilla value {_VANILLA_ELMS_LAB_GREETING_COORD_H} -- data_gen may have "
            "drifted from the real ROM, refusing to guess."
        )
    struct.pack_into("<H", entry, _ELMS_LAB_GREETING_COORD_H_BYTE_OFFSET, _ELMS_LAB_GREETING_COORD_H)
    eventdata.write_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX, bytes(entry))


def write_start_location(rom: HeartGoldRom, town_key: str) -> None:
    write_exit_warp_target(rom, town_key)


REVOCATION_RECORD_ROM_OFFSET = 0x170
REVOCATION_RECORD_MAGIC = b"HGSL"
REVOCATION_RECORD_SIZE = 12


def build_revocation_record(warp_target_rom_offset: int) -> bytes:
    import struct

    return REVOCATION_RECORD_MAGIC + struct.pack("<II", warp_target_rom_offset, _VANILLA_WARP_TARGET)


def parse_revocation_record(record: bytes) -> tuple[int, int] | None:
    import struct

    if len(record) != REVOCATION_RECORD_SIZE or not record.startswith(REVOCATION_RECORD_MAGIC):
        return None
    warp_target_rom_offset, vanilla_value = struct.unpack_from("<II", record, len(REVOCATION_RECORD_MAGIC))
    if warp_target_rom_offset == 0:
        return None
    return warp_target_rom_offset, vanilla_value


def stamp_revocation_record(packed: bytearray) -> int:
    import struct

    from rom import eventdata

    offset = eventdata.entry_rom_offset(bytes(packed), _ZONE_EVENT_ELMS_LAB_INDEX) + _WARP_TARGET_BYTE_OFFSET
    (current,) = struct.unpack_from("<I", packed, offset)
    if (current & 0xFFFF) not in set(TOWN_MAP_IDS.values()):
        raise ValueError(
            f"packed ROM offset {offset:#x} holds {current:#x}, whose map id half is not one of this "
            f"option's destination towns {sorted(TOWN_MAP_IDS.values())} -- the computed offset for "
            "Elm's Lab's exit-warp target word does not point at that word, refusing to record it."
        )
    packed[REVOCATION_RECORD_ROM_OFFSET : REVOCATION_RECORD_ROM_OFFSET + REVOCATION_RECORD_SIZE] = (
        build_revocation_record(offset)
    )
    return offset
