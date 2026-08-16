# rom/pokemon_crypto.py
#
# Gen3/4 Pokemon save-data encryption (src/pokemon.c's MonEncryptSegment/
# MonDecryptSegment/CalcMonChecksum/GetSubstruct) -- the standard, publicly
# documented algorithm (same one PKHeX and every other Gen3/4 save editor
# implements), confirmed against this project's own decomp source
# 2026-08-16 while investigating the start-location randomizer's "write a
# starter directly into the party" requirement.
#
# BoxPokemon.dataBlocks is 4 substructures of 0x20 (32) bytes each --
# Growth/Attacks/EVsCondition/Miscellaneous -- stored in one of 24 possible
# orders selected by personality % 24 (GetSubstruct's own 24-entry table,
# decomp shows a 32-entry table but only indices 0-23 are ever selected).
# The whole 0x80-byte block is a single XOR stream cipher keyed by the
# checksum (a plain 16-bit sum over the unencrypted data, taken before
# encrypting). PartyPokemon's own extra fields (current HP, stats, etc.)
# are a SEPARATE, smaller encrypted segment keyed by personality instead --
# see save_layout.py/client.py's own notes on PartyPokemon.hp being
# deliberately OUTSIDE this encrypted region (a plain mirror field).
#
# Pure Python, no BizHawk/Archipelago imports -- mirrors save_layout.py's
# own convention.

from __future__ import annotations

DATA_BLOCKS_SIZE = 0x80  # 4 x 0x20-byte substructures
SUBSTRUCT_SIZE = 0x20

# GetSubstruct's own table (src/pokemon.c) -- personality % 24 selects one
# of these; each entry is the byte offset (within dataBlocks) of the
# Growth/Attacks/EVsCondition/Miscellaneous block, in that fixed order.
_SUBSTRUCT_ORDERS: tuple[tuple[int, int, int, int], ...] = (
    (0x00, 0x20, 0x40, 0x60),
    (0x00, 0x20, 0x60, 0x40),
    (0x00, 0x40, 0x20, 0x60),
    (0x00, 0x60, 0x20, 0x40),
    (0x00, 0x40, 0x60, 0x20),
    (0x00, 0x60, 0x40, 0x20),
    (0x20, 0x00, 0x40, 0x60),
    (0x20, 0x00, 0x60, 0x40),
    (0x40, 0x00, 0x20, 0x60),
    (0x60, 0x00, 0x20, 0x40),
    (0x40, 0x00, 0x60, 0x20),
    (0x60, 0x00, 0x40, 0x20),
    (0x20, 0x40, 0x00, 0x60),
    (0x20, 0x60, 0x00, 0x40),
    (0x40, 0x20, 0x00, 0x60),
    (0x60, 0x20, 0x00, 0x40),
    (0x40, 0x60, 0x00, 0x20),
    (0x60, 0x40, 0x00, 0x20),
    (0x20, 0x40, 0x60, 0x00),
    (0x20, 0x60, 0x40, 0x00),
    (0x40, 0x20, 0x60, 0x00),
    (0x60, 0x20, 0x40, 0x00),
    (0x40, 0x60, 0x20, 0x00),
    (0x60, 0x40, 0x20, 0x00),
)


def substruct_order(personality: int) -> tuple[int, int, int, int]:
    """Byte offsets (within dataBlocks) of the Growth/Attacks/
    EVsCondition/Miscellaneous blocks, in that order, for this
    personality value."""
    return _SUBSTRUCT_ORDERS[personality % 24]


def calc_checksum(data_blocks: bytes) -> int:
    """CalcMonChecksum: a plain 16-bit sum over the (unencrypted)
    dataBlocks, truncated to u16. `data_blocks` must be exactly
    DATA_BLOCKS_SIZE bytes."""
    if len(data_blocks) != DATA_BLOCKS_SIZE:
        raise ValueError(f"data_blocks must be {DATA_BLOCKS_SIZE} bytes, got {len(data_blocks)}")
    total = 0
    for i in range(0, DATA_BLOCKS_SIZE, 2):
        total = (total + int.from_bytes(data_blocks[i : i + 2], "little")) & 0xFFFF
    return total


def _mon_prng_stream(seed: int, word_count: int) -> list[int]:
    """The standard Gen3/4 Pokemon-data LCG (0x41C64E6D / 0x6073, same
    constants as the game's own general-purpose RNG): each step advances
    the seed and yields the upper 16 bits as the next XOR keystream word."""
    words = []
    for _ in range(word_count):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        words.append((seed >> 16) & 0xFFFF)
    return words


def crypt_segment(data: bytes, key: int) -> bytes:
    """MonEncryptSegment/MonDecryptSegment: both directions are the exact
    same XOR-stream-cipher operation (that's why the decomp's two
    differently-named functions share one real implementation) -- calling
    this twice with the same key on its own output returns the original
    bytes. `data` length must be a multiple of 2."""
    if len(data) % 2 != 0:
        raise ValueError(f"data length must be even, got {len(data)}")
    keystream = _mon_prng_stream(key, len(data) // 2)
    out = bytearray(len(data))
    for i, word in enumerate(keystream):
        plain = int.from_bytes(data[2 * i : 2 * i + 2], "little")
        out[2 * i : 2 * i + 2] = (plain ^ word).to_bytes(2, "little")
    return bytes(out)


def decrypt_data_blocks(encrypted: bytes, checksum: int) -> bytes:
    """BoxPokemon.dataBlocks: keyed by the BoxPokemon's own (already
    known, stored-unencrypted) checksum field."""
    return crypt_segment(encrypted, checksum)


def encrypt_data_blocks(plain: bytes) -> tuple[bytes, int]:
    """Computes the checksum over the plain (unshuffled-order-agnostic --
    checksum is taken over whatever order was chosen) data, then encrypts
    with it as the key. Returns (encrypted_bytes, checksum) -- checksum
    must be stored in BoxPokemon.checksum alongside the encrypted data."""
    checksum = calc_checksum(plain)
    return crypt_segment(plain, checksum), checksum
