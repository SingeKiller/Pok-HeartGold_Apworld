WORLD_SIGNATURE_ROM_OFFSET = 0x17C
WORLD_SIGNATURE = b"PKHS"
WORLD_SIGNATURE_SIZE = len(WORLD_SIGNATURE)


def stamp_world_signature(packed: bytearray) -> None:
    packed[WORLD_SIGNATURE_ROM_OFFSET : WORLD_SIGNATURE_ROM_OFFSET + WORLD_SIGNATURE_SIZE] = WORLD_SIGNATURE


SLOT_AUTH_ROM_OFFSET = 0x180
SLOT_AUTH_SIZE = 16


def stamp_slot_auth(packed: bytearray, auth: bytes) -> None:
    if len(auth) != SLOT_AUTH_SIZE:
        raise ValueError(f"slot auth must be {SLOT_AUTH_SIZE} bytes, got {len(auth)}")
    packed[SLOT_AUTH_ROM_OFFSET : SLOT_AUTH_ROM_OFFSET + SLOT_AUTH_SIZE] = auth


DEATHLINK_SCRIPTS_ROM_OFFSET = 0x190
DEATHLINK_SCRIPTS_TAG = b"PKDL"


def stamp_deathlink_scripts(packed: bytearray) -> None:
    end = DEATHLINK_SCRIPTS_ROM_OFFSET + len(DEATHLINK_SCRIPTS_TAG)
    packed[DEATHLINK_SCRIPTS_ROM_OFFSET:end] = DEATHLINK_SCRIPTS_TAG


def has_world_signature(header_bytes: bytes) -> bool:
    return bytes(header_bytes) == WORLD_SIGNATURE
