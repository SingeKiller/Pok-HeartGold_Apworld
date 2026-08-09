# rom/__init__.py
#
# ROM access layer (task C13): opening a vanilla Pokemon HeartGold (US) ROM
# (with an early, actionable sanity check -- wrong game/region/corrupted
# file must never surface as an obscure exception three layers deep inside
# `ndspy`), reading/writing individual files inside its NitroFS filesystem,
# and saving the resulting patched ROM back out.
#
# Uses `ndspy` (already a runtime dependency, see requirements.txt and
# docs/architecture.md's "## Spikes" -> Spike 1 -- no new dependency added
# here). `ndspy.rom.NintendoDSRom.save()` fully repacks the ROM container
# (file table, offsets, padding all regenerated), so a saved ROM is never
# byte-identical to the original container even when no file content was
# changed -- only individual NitroFS file contents are guaranteed to
# round-trip exactly (see tests/test_rom_roundtrip.py, which this module's
# own HeartGoldRom class is built to satisfy the same guarantee for).
#
# Category-specific reader/writers for the data tables randomized by
# species.py/__init__.py (items, species/personal, trainers, wild
# encounters, map events) live in dedicated submodules built on top of the
# primitives exposed here: rom/itemdata.py, rom/speciesdata.py,
# rom/trainerdata.py, rom/encounterdata.py, rom/eventdata.py.

from __future__ import annotations

import hashlib
from pathlib import Path

import ndspy.narc
import ndspy.rom


class RomError(Exception):
    """Base class for every error this access layer raises."""


class InvalidRomError(RomError):
    """The supplied file is not usable as a Pokemon HeartGold (US) ROM.

    Covers all three failure modes the task brief calls out explicitly:
    wrong game, wrong region, and a corrupted/truncated file -- each with
    its own actionable message rather than a bare parser traceback.
    """


class NitroFsFileNotFoundError(RomError):
    """The requested NitroFS path does not exist in this ROM."""


# The retail, unmodified Pokemon HeartGold (USA) ROM used throughout this
# project's development (see CLAUDE.md and docs/architecture.md's "##
# Spikes" -> Spike 1, which records the same hash from the real cartridge
# dump).
HEARTGOLD_US_MD5 = "258cea3a62ac0d6eb04b5a0fd764d788"

# Nintendo DS "game code" (idCode) header field for the retail US HeartGold
# cartridge, confirmed against the real ROM (`b"IPKE"`). The 4th character
# ('E') is Nintendo's region-code convention (North America); SoulSilver
# uses a different code entirely (`IPGE`), and other regions use a
# different final letter (e.g. `IPKP` for Europe) -- checking this in
# addition to the MD5 gives a clearer "which part of the header looks wrong"
# diagnostic than an MD5 mismatch alone.
HEARTGOLD_US_ID_CODE = b"IPKE"

# Smallest plausible size for *any* real Nintendo DS ROM (the header alone
# occupies the first 0x4000 bytes); anything smaller than this is definitely
# truncated/corrupted rather than a legitimate ROM of the wrong game.
_MIN_PLAUSIBLE_ROM_SIZE = 0x4000


class HeartGoldRom:
    """Thin wrapper around `ndspy.rom.NintendoDSRom` for a Pokemon
    HeartGold (US) ROM: validates the ROM once at load time so every later
    NitroFS read/write can assume it is working with the right game.

    `expect_vanilla` (default `True`) gates the exact-MD5 check: the very
    first ROM this project ever touches -- the one the user supplies -- must
    be the unmodified retail dump, so `HeartGoldRom.open()`/`__init__`
    enforce that by default. Once *this* project has patched that ROM and
    repacked it (`save_bytes()`), the result is -- by design, see
    docs/architecture.md "## Spikes" Spike 1 -- no longer byte-identical to
    the original, even container-wise; re-wrapping that already-patched
    output (e.g. to verify a further edit, or to chain more patches) must
    therefore pass `expect_vanilla=False` to skip the MD5 check while still
    keeping the game-code + size sanity checks (still guards against
    accidentally feeding in a wrong/corrupted file at any later step)."""

    def __init__(self, data: bytes, *, expect_vanilla: bool = True) -> None:
        self._validate_size_and_hash(data, expect_vanilla=expect_vanilla)
        try:
            self._rom = ndspy.rom.NintendoDSRom(data)
        except Exception as exc:  # ndspy itself raises assorted exception types
            raise InvalidRomError(
                "Could not parse this file as a Nintendo DS ROM (.nds) even "
                "though its size (and, if checked, MD5) looked right -- the "
                "file is likely corrupted."
            ) from exc
        self._validate_game_code()

    @staticmethod
    def _validate_size_and_hash(data: bytes, *, expect_vanilla: bool) -> None:
        if len(data) < _MIN_PLAUSIBLE_ROM_SIZE:
            raise InvalidRomError(
                f"File is only {len(data)} bytes -- too small to be a "
                "Nintendo DS ROM. It is likely truncated or corrupted."
            )
        if not expect_vanilla:
            return
        digest = hashlib.md5(data).hexdigest()
        if digest != HEARTGOLD_US_MD5:
            raise InvalidRomError(
                "This does not look like the retail Pokemon HeartGold (USA) "
                f"ROM: expected MD5 {HEARTGOLD_US_MD5}, got {digest}. Make "
                "sure the ROM path points at an unmodified US HeartGold "
                "dump -- not SoulSilver, not another region or revision, "
                "and not an already-patched ROM."
            )

    def _validate_game_code(self) -> None:
        id_code = bytes(self._rom.idCode)
        if id_code != HEARTGOLD_US_ID_CODE:
            raise InvalidRomError(
                f"ROM header game code is {id_code!r}, expected "
                f"{HEARTGOLD_US_ID_CODE!r} (Pokemon HeartGold, USA). This "
                "ROM passed the MD5 check but has an unexpected header, "
                "which should not happen for a genuine retail dump."
            )

    @classmethod
    def open(cls, path: str | Path, *, expect_vanilla: bool = True) -> HeartGoldRom:
        """Open and validate a HeartGold (US) ROM from a filesystem path.
        See this class's own docstring for what `expect_vanilla` gates."""
        rom_path = Path(path)
        if not rom_path.is_file():
            raise InvalidRomError(f"ROM file not found: {rom_path}")
        return cls(rom_path.read_bytes(), expect_vanilla=expect_vanilla)

    # -- Raw NitroFS file access ---------------------------------------------

    def read_file(self, nitrofs_path: str) -> bytes:
        """Read a raw file from the ROM's NitroFS filesystem by its data
        path (e.g. `"pbr/item_data.narc"`, or a numbered path like
        `"a/0/1/7"` -- see rom/itemdata.py and friends for why some of this
        ROM's real data tables only exist under such numbered paths)."""
        try:
            return bytes(self._rom.getFileByName(nitrofs_path))
        except ValueError as exc:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            ) from exc

    def write_file(self, nitrofs_path: str, data: bytes) -> None:
        """Replace a raw file in the ROM's NitroFS filesystem by its data
        path. The path must already exist (this layer never adds new
        NitroFS files, only replaces existing ones)."""
        try:
            self._rom.setFileByName(nitrofs_path, data)
        except ValueError as exc:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            ) from exc

    # -- NARC convenience -----------------------------------------------------

    def read_narc(self, nitrofs_path: str) -> ndspy.narc.NARC:
        """Read a NitroFS file and parse it as a NARC archive (most of the
        game-data tables this project cares about -- items, species,
        trainers, encounters -- are themselves NARC containers holding one
        sub-file per entry)."""
        return ndspy.narc.NARC(self.read_file(nitrofs_path))

    def write_narc(self, nitrofs_path: str, narc: ndspy.narc.NARC) -> None:
        """Serialize a NARC archive and write it back to the given NitroFS
        path."""
        self.write_file(nitrofs_path, narc.save())

    # -- Output -----------------------------------------------------------------

    def save_bytes(self) -> bytes:
        """Repack the (patched) ROM container and return its bytes.

        Note: `ndspy` fully repacks the ROM container on save, so the
        output is never byte-identical to the input, even for completely
        unmodified files (see docs/architecture.md, "## Spikes", Spike 1).
        Individual NitroFS file contents round-trip exactly; the container
        framing (file table, offsets, padding) does not.
        """
        return self._rom.save()

    def save(self, path: str | Path) -> None:
        """Repack the (patched) ROM and write it to `path`."""
        Path(path).write_bytes(self.save_bytes())
