from __future__ import annotations

DATA_BLOCKS_SIZE = 0x80
SUBSTRUCT_SIZE = 0x20

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
    return _SUBSTRUCT_ORDERS[personality % 24]


def calc_checksum(data_blocks: bytes) -> int:
    if len(data_blocks) != DATA_BLOCKS_SIZE:
        raise ValueError(f"data_blocks must be {DATA_BLOCKS_SIZE} bytes, got {len(data_blocks)}")
    total = 0
    for i in range(0, DATA_BLOCKS_SIZE, 2):
        total = (total + int.from_bytes(data_blocks[i : i + 2], "little")) & 0xFFFF
    return total


def _mon_prng_stream(seed: int, word_count: int) -> list[int]:
    words = []
    for _ in range(word_count):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        words.append((seed >> 16) & 0xFFFF)
    return words


def crypt_segment(data: bytes, key: int) -> bytes:
    if len(data) % 2 != 0:
        raise ValueError(f"data length must be even, got {len(data)}")
    keystream = _mon_prng_stream(key, len(data) // 2)
    out = bytearray(len(data))
    for i, word in enumerate(keystream):
        plain = int.from_bytes(data[2 * i : 2 * i + 2], "little")
        out[2 * i : 2 * i + 2] = (plain ^ word).to_bytes(2, "little")
    return bytes(out)


def decrypt_data_blocks(encrypted: bytes, checksum: int) -> bytes:
    return crypt_segment(encrypted, checksum)


def encrypt_data_blocks(plain: bytes) -> tuple[bytes, int]:
    checksum = calc_checksum(plain)
    return crypt_segment(plain, checksum), checksum
