# rom/worldsignature.py
#
# A 4-byte tag stamped into every ROM this world patches, so the BizHawk
# client only attaches to ROMs produced by this world (v0.2.5).
#
# Before this, client.py's validate_rom only checked the retail game code
# at 0x0C (IPKE/IPGE), so it claimed any HeartGold/SoulSilver ROM: an
# unpatched one, or one patched by ljtpetersen's hgss_archipelago world,
# which can be installed next to this one since the rename. Archipelago's
# BizHawk client hands a ROM to the first handler whose validate_rom says
# yes, so both worlds must recognize only their own ROMs.
#
# Location: the last 4 bytes of the cartridge header's reserved 0x170-0x17F
# range. 0x170-0x17B already hold rom/startlocation.py's revocation record
# (see its section 4 for why this range is safe: outside the header CRC,
# never read by the game or melonDS). Unlike that record, the signature is
# stamped unconditionally.

WORLD_SIGNATURE_ROM_OFFSET = 0x17C
WORLD_SIGNATURE = b"PKHS"  # Poke_HGSS
WORLD_SIGNATURE_SIZE = len(WORLD_SIGNATURE)


def stamp_world_signature(packed: bytearray) -> None:
    """Write WORLD_SIGNATURE into an already-packed ROM image, in place."""
    packed[WORLD_SIGNATURE_ROM_OFFSET : WORLD_SIGNATURE_ROM_OFFSET + WORLD_SIGNATURE_SIZE] = WORLD_SIGNATURE


# Slot auth (v0.2.5): 16 bytes identifying the slot this ROM was patched
# for, so client.py's set_auth can log in without asking for a slot name
# (same scheme as Pokemon Emerald: __init__.py registers the bytes, base64
# encoded, as an extra connect name in modify_multidata).
#
# Location: 0x180-0x18F. Zero on both retail ROMs, outside the header CRC
# (0x000-0x15D), and the start of the DSi extended header, which is only
# read for DSi titles (unit code bit 1); HGSS is unit code 0. The NTR
# reserved range 0x170-0x17F is already full (revocation record +
# signature above). All zero means "no auth": the client then asks for the
# slot name as before.
SLOT_AUTH_ROM_OFFSET = 0x180
SLOT_AUTH_SIZE = 16


def stamp_slot_auth(packed: bytearray, auth: bytes) -> None:
    """Write the 16-byte slot auth into an already-packed ROM image."""
    if len(auth) != SLOT_AUTH_SIZE:
        raise ValueError(f"slot auth must be {SLOT_AUTH_SIZE} bytes, got {len(auth)}")
    packed[SLOT_AUTH_ROM_OFFSET : SLOT_AUTH_ROM_OFFSET + SLOT_AUTH_SIZE] = auth


def has_world_signature(header_bytes: bytes) -> bool:
    """True if a WORLD_SIGNATURE_SIZE-byte read at WORLD_SIGNATURE_ROM_OFFSET
    is this world's signature."""
    return bytes(header_bytes) == WORLD_SIGNATURE
