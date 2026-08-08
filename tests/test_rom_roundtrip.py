"""NitroFS round-trip test for the Pokemon HeartGold (US) ROM (Spike 1).

This does NOT assert that re-saving the whole ROM through `ndspy` reproduces
an MD5-identical file. It can't: `ndspy.rom.NintendoDSRom.save()` fully
repacks the ROM container (file table, alignment/padding, offsets), so the
rebuilt `.nds` is a different size than the original even when no file
content was changed (verified in the Spike 1 PoC: 134,217,728 bytes in vs.
126,645,960 bytes out, with the byte streams already diverging inside the
header at offset 0x80 -- see docs/architecture.md, "## Spikes").

What *does* need to hold -- and what this test actually asserts -- is the
property our future ROM patcher depends on: extracting a file from the
NitroFS, writing it back unchanged, saving the ROM, and reloading it must
round-trip that file's bytes exactly, with no corruption. That's the
"round-trip without corruption" guarantee this spike set out to verify.

The ROM is a legally-dumped, user-supplied file that is never committed to
this repository. The path is taken from the HEARTGOLD_ROM_PATH environment
variable; if it isn't set (e.g. in CI) or doesn't point at a real file, the
test is skipped rather than failed.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

ndspy_rom = pytest.importorskip("ndspy.rom")

ROM_PATH_ENV_VAR = "HEARTGOLD_ROM_PATH"

# A small, well-known NitroFS file to round-trip. Present in the retail
# HeartGold (US) ROM at this path (confirmed against the actual ROM in the
# Spike 1 PoC).
SAMPLE_NITROFS_PATH = "pbr/item_data.narc"


def _rom_path() -> Path | None:
    raw_path = os.environ.get(ROM_PATH_ENV_VAR)
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_file():
        return None
    return path


@pytest.fixture()
def rom_bytes() -> bytes:
    path = _rom_path()
    if path is None:
        pytest.skip(
            f"HeartGold ROM not available locally: set {ROM_PATH_ENV_VAR} to "
            "a valid ROM path to run this test."
        )
    return path.read_bytes()


def test_nitrofs_file_roundtrips_without_corruption(rom_bytes: bytes) -> None:
    """Extract a file, write it back unchanged, save, reload, and compare.

    This is the property that matters for our future patcher: whatever we
    read out of the NitroFS and write back must come back byte-identical
    after a save/reload cycle.
    """
    rom = ndspy_rom.NintendoDSRom(rom_bytes)

    original_file = bytes(rom.getFileByName(SAMPLE_NITROFS_PATH))
    original_md5 = hashlib.md5(original_file).hexdigest()

    rom.setFileByName(SAMPLE_NITROFS_PATH, original_file)
    rebuilt_bytes = rom.save()

    reloaded_rom = ndspy_rom.NintendoDSRom(rebuilt_bytes)
    roundtripped_file = bytes(reloaded_rom.getFileByName(SAMPLE_NITROFS_PATH))
    roundtripped_md5 = hashlib.md5(roundtripped_file).hexdigest()

    assert roundtripped_md5 == original_md5
    assert roundtripped_file == original_file


def test_nitrofs_file_table_is_preserved_by_rebuild(rom_bytes: bytes) -> None:
    """A full rebuild must keep the same set of files (nothing dropped/added)."""
    rom = ndspy_rom.NintendoDSRom(rom_bytes)
    original_file_count = len(rom.files)

    rebuilt_bytes = rom.save()
    reloaded_rom = ndspy_rom.NintendoDSRom(rebuilt_bytes)

    assert len(reloaded_rom.files) == original_file_count
