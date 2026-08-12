# rom/__init__.py
#
# ROM access layer (task C13): opening a vanilla Pokemon HeartGold (US) ROM
# (with an early, actionable sanity check -- wrong game/region/corrupted
# file must never surface as an obscure exception three layers deep inside
# `apnds`), reading/writing individual files inside its NitroFS filesystem,
# and saving the resulting patched ROM back out.
#
# Uses `apnds` (MIT, vendored directly in this repository under /apnds/ --
# see /apnds_version.txt and .apignore -- so the built `.apworld` needs no
# separate runtime install; this replaces the earlier `ndspy`-based
# implementation, which could not be bundled the same way since `ndspy` is
# GPLv3, see docs/architecture.md's "## Spikes" -> Spike 1 for that
# original design). `apnds.rom.Rom.to_bytes()` fully repacks the ROM
# container (file table, offsets, padding all regenerated), so a saved ROM
# is never byte-identical to the original container even when no file
# content was changed -- only individual NitroFS file contents are
# guaranteed to round-trip exactly (see tests/test_rom_roundtrip.py, which
# this module's own HeartGoldRom class is built to satisfy the same
# guarantee for).
#
# Category-specific reader/writers for the data tables randomized by
# species.py/__init__.py (items, species/personal, trainers, wild
# encounters, map events) live in dedicated submodules built on top of the
# primitives exposed here: rom/itemdata.py, rom/speciesdata.py,
# rom/trainerdata.py, rom/encounterdata.py, rom/eventdata.py.

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import apnds.narc
import apnds.rom
from apnds.code import get_start_info_offset
from apnds.lz import compress_code, decompress_code


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


# The retail, unmodified Pokemon HeartGold (USA) ROM used throughout most
# of this project's development (see CLAUDE.md and docs/architecture.md's
# "## Spikes" -> Spike 1, which records the same hash from the real
# cartridge dump).
HEARTGOLD_US_MD5 = "258cea3a62ac0d6eb04b5a0fd764d788"
HEARTGOLD_US_ID_CODE = b"IPKE"

# The retail, unmodified Pokemon SoulSilver (USA) ROM -- HeartGold's sister
# version. Live-verified (2026-08-11, see docs/architecture.md's SoulSilver
# support section): despite the different MD5/id code, its decompressed
# ARM9 image is byte-for-byte the *same length* as HeartGold's (1,122,040
# bytes), every NitroFS numbered path this project reads/writes has the
# exact same sub-file count, and the hidden_item table sits at the exact
# same RAM address (`rom/hiddenitemdata.py`'s `ARM9_TABLE_RAM_ADDRESS`) --
# strong evidence the two versions share the same underlying build/layout,
# differing only in game-specific *content* (version-exclusive Pokemon,
# etc.), not in any offset this project depends on.
SOULSILVER_US_MD5 = "8a6c8888bed9e1dce952f840351b73f2"
SOULSILVER_US_ID_CODE = b"IPGE"

# md5 -> version name, and version name -> expected header id code.
# `version` is exposed on `HeartGoldRom` instances (see the `version`
# attribute) for the rare case calling code actually needs to know which
# game it's holding -- most of this project's rom/*.py access layer
# doesn't, by design (see the class docstring below).
_VERSION_BY_MD5: dict[str, str] = {
    HEARTGOLD_US_MD5: "heartgold",
    SOULSILVER_US_MD5: "soulsilver",
}
_ID_CODE_BY_VERSION: dict[str, bytes] = {
    "heartgold": HEARTGOLD_US_ID_CODE,
    "soulsilver": SOULSILVER_US_ID_CODE,
}

# Smallest plausible size for *any* real Nintendo DS ROM (the header alone
# occupies the first 0x4000 bytes); anything smaller than this is definitely
# truncated/corrupted rather than a legitimate ROM of the wrong game.
_MIN_PLAUSIBLE_ROM_SIZE = 0x4000


class HeartGoldRom:
    """Thin wrapper around `apnds.rom.Rom` for a Pokemon
    HeartGold/SoulSilver (US) ROM: validates the ROM once at load time so
    every later NitroFS read/write can assume it is working with a known,
    supported game. Accepts *either* version (see `_KNOWN_ROMS` above) --
    despite the name, this class is not HeartGold-specific; every
    `rom/*.py` access layer built on it reads/writes generically by
    NitroFS path/offset, never assuming version-specific content.

    `expect_vanilla` (default `True`) gates the exact-MD5 check: the very
    first ROM this project ever touches -- the one the user supplies -- must
    be one of the two unmodified retail dumps, so `HeartGoldRom.open()`/
    `__init__` enforce that by default. Once *this* project has patched
    that ROM and repacked it (`save_bytes()`), the result is -- by design,
    see docs/architecture.md "## Spikes" Spike 1 -- no longer byte-
    identical to the original, even container-wise; re-wrapping that
    already-patched output (e.g. to verify a further edit, or to chain
    more patches) must therefore pass `expect_vanilla=False` to skip the
    MD5 check while still keeping the game-code + size sanity checks
    (still guards against accidentally feeding in a wrong/corrupted file
    at any later step). `expect_vanilla=False` also means `version` is
    unknown (`None`) -- there's no MD5 to look it up by."""

    # The 12-byte "nitrocode" trailer some ROM tools append to the ARM9
    # binary after the (compressed) code -- signature (4 bytes) + the file
    # offset of the code's `DSStartParams` structure, relative to the ARM9
    # load address (4 bytes) + a reserved word, always 0 on both real ROMs
    # this project has been live-verified against (2026-08-11). `apnds`
    # itself treats this as fully opaque pass-through data (see
    # `apnds/rom.py`'s `Rom.from_bytes`/`to_bytes`: it only ever checks the
    # 4-byte signature to decide whether to fold these 12 bytes into
    # `Rom.arm9`, never parses or regenerates the other 8 bytes) -- but
    # `ndspy`'s `.arm9` never included it in the first place, so every
    # caller of this class's own `arm9` property (`patch_gen.py`'s ground-
    # item hook load-address calculation, `append_to_arm9` below, this
    # class's `write_main_code_regions`) is written against the *without-
    # footer* convention. `_split_arm9_footer` below (paired with plain
    # `body + ... + footer` concatenation at each of `arm9`'s mutators)
    # keeps that convention intact on top of `apnds`'s footer-inclusive
    # representation. See this class's ARM9 sections further down for how
    # the offset word is regenerated (not just carried through blindly)
    # after every recompression.
    _NITROCODE_FOOTER_SIGNATURE = bytes.fromhex("2106C0DE")
    _NITROCODE_FOOTER_SIZE = 12

    def __init__(self, data: bytes, *, expect_vanilla: bool = True) -> None:
        self.version: str | None = self._validate_size_and_hash(data, expect_vanilla=expect_vanilla)
        try:
            self._rom = apnds.rom.Rom.from_bytes(data)
        except Exception as exc:  # apnds itself raises assorted exception types
            raise InvalidRomError(
                "Could not parse this file as a Nintendo DS ROM (.nds) even "
                "though its size (and, if checked, MD5) looked right -- the "
                "file is likely corrupted."
            ) from exc
        self._validate_game_code()

    def _split_arm9_footer(self) -> tuple[bytes, bytes]:
        """Split `self._rom.arm9` (as `apnds` represents it -- see the
        docstring above `_NITROCODE_FOOTER_SIGNATURE`) into `(body,
        footer)`, where `body` is exactly what `ndspy`'s (and this class's
        own public) `arm9` property used to return, and `footer` is either
        the 12-byte nitrocode trailer or `b""` if this ROM doesn't have
        one."""
        raw = bytes(self._rom.arm9)
        footer_start = len(raw) - self._NITROCODE_FOOTER_SIZE
        if len(raw) > self._NITROCODE_FOOTER_SIZE and raw[footer_start : footer_start + 4] == self._NITROCODE_FOOTER_SIGNATURE:
            return raw[:footer_start], raw[footer_start:]
        return raw, b""

    @staticmethod
    def _validate_size_and_hash(data: bytes, *, expect_vanilla: bool) -> str | None:
        if len(data) < _MIN_PLAUSIBLE_ROM_SIZE:
            raise InvalidRomError(
                f"File is only {len(data)} bytes -- too small to be a "
                "Nintendo DS ROM. It is likely truncated or corrupted."
            )
        if not expect_vanilla:
            return None
        digest = hashlib.md5(data).hexdigest()
        version = _VERSION_BY_MD5.get(digest)
        if version is None:
            expected = ", ".join(sorted(_VERSION_BY_MD5))
            raise InvalidRomError(
                "This does not look like a retail Pokemon HeartGold/SoulSilver "
                f"(USA) ROM: expected one of [{expected}], got {digest}. Make "
                "sure the ROM path points at an unmodified US HeartGold or "
                "SoulSilver dump -- not another region or revision, and not "
                "an already-patched ROM."
            )
        return version

    def _validate_game_code(self) -> None:
        id_code = bytes(self._rom.header[apnds.rom.HeaderField.SERIAL])
        if self.version is not None:
            expected_id_code = _ID_CODE_BY_VERSION[self.version]
            if id_code != expected_id_code:
                raise InvalidRomError(
                    f"ROM header game code is {id_code!r}, expected "
                    f"{expected_id_code!r} (Pokemon {self.version.title()}, USA). "
                    "This ROM passed the MD5 check but has an unexpected "
                    "header, which should not happen for a genuine retail dump."
                )
            return
        # expect_vanilla=False (already-patched ROM, no MD5 to check) --
        # still confirm it's *a* known game code, just not which MD5.
        if id_code not in _ID_CODE_BY_VERSION.values():
            raise InvalidRomError(
                f"ROM header game code is {id_code!r}, expected one of "
                f"{sorted(_ID_CODE_BY_VERSION.values())!r} (Pokemon HeartGold/SoulSilver, USA)."
            )

    @classmethod
    def open(cls, path: str | Path, *, expect_vanilla: bool = True) -> HeartGoldRom:
        """Open and validate a HeartGold/SoulSilver (US) ROM from a
        filesystem path. See this class's own docstring for what
        `expect_vanilla` gates."""
        rom_path = Path(path)
        if not rom_path.is_file():
            raise InvalidRomError(f"ROM file not found: {rom_path}")
        return cls(rom_path.read_bytes(), expect_vanilla=expect_vanilla)

    # -- Raw NitroFS file access ---------------------------------------------

    @staticmethod
    def _normalize_nitrofs_path(nitrofs_path: str) -> str:
        """`apnds.rom.Rom.files` keys every path with a leading slash
        (`"/pbr/item_data.narc"`) -- unlike `ndspy`'s `getFileByName`/
        `setFileByName`, which take the path bare (`"pbr/item_data.narc"`).
        Every path this class's own callers pass in follows the `ndspy`
        convention (no leading slash), so normalize it here rather than
        pushing that detail out to every `rom/*.py` submodule."""
        return "/" + nitrofs_path.lstrip("/")

    def read_file(self, nitrofs_path: str) -> bytes:
        """Read a raw file from the ROM's NitroFS filesystem by its data
        path (e.g. `"pbr/item_data.narc"`, or a numbered path like
        `"a/0/1/7"` -- see rom/itemdata.py and friends for why some of this
        ROM's real data tables only exist under such numbered paths)."""
        try:
            return bytes(self._rom.files[self._normalize_nitrofs_path(nitrofs_path)])
        except KeyError as exc:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            ) from exc

    def write_file(self, nitrofs_path: str, data: bytes) -> None:
        """Replace a raw file in the ROM's NitroFS filesystem by its data
        path. The path must already exist (this layer never adds new
        NitroFS files, only replaces existing ones) -- enforced here since
        `apnds.rom.Rom.files` is a plain dict that would otherwise silently
        create a new entry under a not-quite-matching normalized key rather
        than overwrite the existing one (see this class's `_normalize_
        nitrofs_path`, and tests/test_rom_access.py's own file-count
        regression coverage for this exact pitfall)."""
        key = self._normalize_nitrofs_path(nitrofs_path)
        if key not in self._rom.files:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            )
        self._rom.files[key] = bytes(data)

    # -- NARC convenience -----------------------------------------------------

    def read_narc(self, nitrofs_path: str) -> apnds.narc.Narc:
        """Read a NitroFS file and parse it as a NARC archive (most of the
        game-data tables this project cares about -- items, species,
        trainers, encounters -- are themselves NARC containers holding one
        sub-file per entry)."""
        return apnds.narc.Narc.from_bytes(self.read_file(nitrofs_path))

    def write_narc(self, nitrofs_path: str, narc: apnds.narc.Narc) -> None:
        """Serialize a NARC archive and write it back to the given NitroFS
        path."""
        self.write_file(nitrofs_path, narc.to_bytes())

    # -- ARM9 static binary access (task C14) ---------------------------------
    #
    # Narrow, append-only access to the ARM9 executable itself -- distinct
    # from the NitroFS data-table access above. Added for C14 (ground-item
    # check mechanism PoC): `patch_gen.py` needs a *safe* place to inject an
    # assembled armips patch. See docs/architecture.md, "## C14 -- Ground
    # item check mechanism (proof of concept)" for the full risk analysis
    # this design is built around; the short version:
    #
    # - The first 0x4000 bytes of the ARM9 binary are the Nintendo DS
    #   "secure area", which the retail cartridge/BIOS validates against a
    #   CRC (`secureAreaChecksum`/`SECURECRC` in the ROM header). `apnds`
    #   reads that checksum but does **not** recompute it on `to_bytes()`
    #   (confirmed by reading `apnds/rom.py`'s `Rom.to_bytes`: `header` is
    #   built from a copy of the *original* header bytes, and `SECURECRC`
    #   is never one of the fields it overwrites -- same round-tripped-
    #   verbatim behaviour `ndspy` had, which this note used to describe).
    #   Any edit that changes bytes *within* the secure area would
    #   therefore leave a stale/incorrect checksum in the saved ROM -- a
    #   real risk of failing to boot on strict emulators or real hardware.
    # - `append_to_arm9()` below only ever *appends* bytes after the
    #   existing ARM9 binary's current end. Since the ARM9 binary is far
    #   larger than 0x4000 bytes, this never touches the secure area, so the
    #   existing (stale-but-still-correct-for-the-untouched-bytes) checksum
    #   remains valid for everything the checksum actually covers.
    # - This layer deliberately exposes no way to overwrite *existing* ARM9
    #   bytes (unlike `write_file`/`write_narc` above, which replace
    #   existing NitroFS file contents) -- only appending new bytes at the
    #   tail is offered, since that is the one operation this project has
    #   verified does not touch the checksummed region.
    #
    # `apnds.rom.Rom.arm9` additionally includes a 12-byte "nitrocode"
    # trailer some ROMs (including both real HeartGold/SoulSilver dumps
    # this project targets) carry right after the packed ARM9 code -- see
    # `_NITROCODE_FOOTER_SIGNATURE`'s own docstring above for what it is.
    # `ndspy`'s `.arm9` never included it, so `arm9`/`append_to_arm9`/
    # `write_main_code_regions` below all route through `_split_arm9_footer`
    # to keep excluding it, preserving every existing caller's contract
    # (`patch_gen.py`'s `rom.arm9_ram_address + len(rom.arm9)` load-address
    # calculation in particular -- see that module's own `apply_ground_
    # item_hook`).

    @property
    def arm9(self) -> bytes:
        """The raw ARM9 executable currently packed in this ROM (read-only
        snapshot; mutate via `append_to_arm9()`, never in place). Excludes
        the 12-byte nitrocode trailer if present -- see this section's own
        docstring."""
        body, _footer = self._split_arm9_footer()
        return body

    @property
    def arm9_ram_address(self) -> int:
        """The RAM address the ARM9 binary's first byte is loaded at
        (`ARM9_LOADADDR` in the ROM header)."""
        return self._rom.header.get_le(apnds.rom.HeaderField.ARM9_LOADADDR)

    @property
    def arm9_entry_address(self) -> int:
        """The RAM address ARM9 execution starts at after the BIOS/secure
        area handoff (`ARM9_ENTRYPOINT` in the ROM header). Exposed for
        documentation/introspection; **not** currently used as a patch
        target by this layer (see this section's docstring -- hooking the
        entry point directly would mean editing secure-area bytes)."""
        return self._rom.header.get_le(apnds.rom.HeaderField.ARM9_ENTRYPOINT)

    def append_to_arm9(self, data: bytes) -> int:
        """Append `data` to the end of the ARM9 binary and return the RAM
        address it now lives at (i.e. the address to assemble/link the
        appended code against). See this section's docstring for why this
        is append-only and why that keeps the DS secure-area checksum
        valid. `data` is appended right after the ARM9 body and before the
        12-byte nitrocode trailer, if this ROM has one -- the trailer's own
        offset word does not need updating for this (it points inside the
        never-moved secure area, see `_NITROCODE_FOOTER_SIGNATURE`'s own
        docstring), so it is carried through unchanged."""
        body, footer = self._split_arm9_footer()
        target_address = self.arm9_ram_address + len(body)
        self._rom.arm9 = body + bytes(data) + footer
        return target_address

    # -- ARM9 overlay access (task M4.5) ---------------------------------------
    #
    # Unlike the main ARM9 binary above (append-only, see that section's own
    # docstring for why: the DS secure-area checksum), an overlay is a plain
    # NitroFS file referenced by the ARM9 overlay table (`arm9OverlayTable`),
    # with its own independent per-overlay compression flag and no DS-wide
    # checksum concern -- so in-place edits (not just appends) are safe here
    # *with respect to boot integrity*. This does **not** make editing
    # compiled code/data inside an overlay low-risk in general: unlike the
    # NitroFS data tables `read_narc`/`write_narc` above operate on, an
    # overlay mixes real ARM machine code with whatever constant data the
    # compiler placed alongside it -- a wrong offset can corrupt an
    # instruction, not just misplace a value. Every caller of `write_overlay`
    # is expected to have independently, precisely located the exact bytes
    # it means to change (see e.g. rom/starterdata.py's own docstring for
    # how that was done for the one caller that exists as of this writing).

    def _find_overlay(self, overlay_id: int) -> apnds.rom.Overlay:
        for overlay in self._rom.arm9_overlays:
            if overlay.id == overlay_id:
                return overlay
        raise ValueError(f"overlay {overlay_id} not found in the ARM9 overlay table")

    def read_overlay(self, overlay_id: int) -> bytes:
        """Return one ARM9 overlay's data, decompressed if needed.

        Uses `apnds.lz.decompress_code` -- the same "backward code"
        compression algorithm `read_main_code_decompressed` below uses for
        the main ARM9 image, *not* the plain LZ10 `apnds.lz.decompress`/
        `compress` pair (used for e.g. graphics assets). Confirmed
        empirically against a real ROM overlay (2026-08-11): LZ10's
        `decompress` raises on this data outright (wrong format), while
        `decompress_code` round-trips it byte-for-byte -- this is a
        different underlying algorithm than the plain-LZ10 approach
        `ndspy.codeCompression.compress(data, isArm9=False)` used, not just
        a different API for the same one."""
        overlay = self._find_overlay(overlay_id)
        if not overlay.is_compressed():
            return bytes(overlay.data)
        decompressed, _rem = decompress_code(overlay.data, overlay.compressed_size)
        return decompressed

    def write_overlay(self, overlay_id: int, data: bytes) -> None:
        """Replace one ARM9 overlay's data in place, re-compressing first
        if the overlay was originally compressed (preserving its existing
        compressed/uncompressed state -- never changes that flag).

        Unlike the old `ndspy`-based implementation (which had to hand-
        patch `arm9OverlayTable`'s own 32-byte record for this overlay
        after every recompression, since recompressing essentially never
        reproduces the exact original byte count -- see this class's git
        history for that now-removed `_patch_overlay_table_compressed_
        size`), `apnds.rom.construct_overlay_table` regenerates the whole
        ARM9 overlay table from every `apnds.rom.Overlay` object's own
        fields at `Rom.to_bytes()` time, so updating this overlay's
        `.data`/`.compressed_size` in place here is sufficient -- no
        separate table patch needed."""
        overlay = self._find_overlay(overlay_id)
        current = self.read_overlay(overlay_id)
        if len(data) != len(current):
            raise ValueError(
                f"overlay {overlay_id} is {len(current)} bytes, got "
                f"{len(data)} replacement bytes -- this layer never resizes "
                "an overlay, only replaces its contents."
            )
        if overlay.is_compressed():
            payload = compress_code(bytes(data))
            if payload is None:
                raise RomError(
                    f"overlay {overlay_id}: apnds.lz.compress_code returned "
                    "None (it could not compress this data to anything "
                    "smaller than the input) -- this layer refuses to "
                    "silently fall back to writing an uncompressed payload, "
                    "since the overlay's own compressed flag would then no "
                    "longer match its actual contents."
                )
            if len(payload) > overlay.ram_size:
                raise ValueError(
                    f"overlay {overlay_id}: recompressed to {len(payload)} bytes, "
                    f"which exceeds its {overlay.ram_size}-byte RAM allocation -- "
                    "the DS overlay loader would read past the end of its buffer."
                )
            overlay.data = payload
            overlay.compressed_size = len(payload)
        else:
            overlay.data = bytes(data)

    # -- ARM9 main-image decompressed access (task M4.5, hidden_item) -----------
    #
    # `arm9` above (and `ndspy`'s own `NintendoDSRom.arm9`) is the ARM9
    # binary exactly as packed in the ROM -- for HeartGold (and apparently
    # every retail HGSS ROM) that packed form is itself LZ-compressed
    # beyond the first 0x4000-byte secure area (`ndspy.codeCompression`'s
    # `isArm9=True` mode: secure area stored raw, everything after it
    # compressed). This was discovered the hard way during the hidden_item
    # investigation (task M4.5): every blind byte-pattern search against
    # `arm9` directly found nothing, because it was searching compressed
    # bytes for an uncompressed pattern -- decompressing `rom.arm9`
    # (762,644 -> 1,122,040 bytes here, confirmed byte-for-byte identical
    # between `ndspy.codeCompression.decompress` and `apnds.lz.
    # decompress_code` for both real ROMs, 2026-08-11) is required before
    # any content search/read against static ARM9 data can work.
    # `sHiddenItemParam` (`src/data/fieldmap/hidden_items.h`'s static
    # table, read by `GetHiddenItemParams`/`script_manager.c`) was located
    # this way: live BizHawk memory-write breakpoints + a manual
    # instruction trace pinpointed its RAM address as 0x020FA558 (an
    # exact, live-verified byte match against the decomp's own table,
    # all 231 entries), which is offset 0xFA558 into this decompressed
    # image (`0x020FA558 - arm9RamAddress`).
    #
    # Writing back: decompress, patch the target bytes (must stay entirely
    # past the 0x4000-byte secure area -- see `arm9` section's own
    # docstring for why touching that region is unsafe), recompress (the
    # first 0x4000 bytes -- the secure area -- kept verbatim by this
    # class's own code, then `apnds.lz.compress_code` applied only to
    # everything after; confirmed via a decompress->recompress->decompress
    # round trip producing byte-identical output, including with zero
    # edits applied -- see tests/test_hidden_item_substitution.py), and
    # replace `self._rom.arm9` wholesale (plus the 12-byte nitrocode
    # trailer, regenerated -- see `write_main_code_regions` itself) --
    # `apnds` recomputes the ROM header's own size field from this on
    # `to_bytes()`, same as every other mutable property here.
    #
    # *** CORRECTION (2026-08-11, root cause of the hidden_item white-
    # screen bug -- see docs/architecture.md) ***: the paragraph above is
    # incomplete. Recompressing to a size *different* from vanilla (which
    # any real edit does, LZ output size depends on content) leaves a
    # stale value in `SDK_COMPRESSED_STATIC_END` -- one word, at ARM9 RAM
    # address `_start_ModuleParams + 0x14` (`lib/asm/crt0.s` in the
    # decomp: `_start_ModuleParams: .word ...; .word 0 ; SDK_COMPRESSED_
    # STATIC_END`), itself at a *fixed* address (`_start_ModuleParams` is
    # `0x02000BA0` in every HeartGold (US) ROM -- no ASLR, static .rodata).
    # `crt0.s`'s own boot sequence (`_start`, before `NitroMain` ever
    # runs) reads this field and passes it as the *end address* argument
    # to `MIi_UncompressBackward`, which decompresses the whole static
    # region backward from there. Live-verified against the real vanilla
    # ROM (2026-08-11): the stored field value equals exactly
    # `arm9RamAddress + len(<packed/compressed ARM9 bytes>)` -- i.e. it
    # marks where the compressed blob ends in RAM once loaded. This class's
    # own recompression keeps `data[:0x4000]` (the secure area, where this
    # field lives) as a verbatim, untouched prefix (see `write_main_code_
    # regions` below: it never runs `data[:0x4000]` through `apnds.lz.
    # compress_code`, only `data[0x4000:]`) -- so nothing here has any idea
    # this field's value needs to track the *new* compressed length unless
    # explicitly told to; before this fix existed, the field silently kept
    # pointing at the *vanilla* compressed length after any real edit. At
    # boot, `MIi_UncompressBackward` then starts reading the compression
    # header from the wrong address (off by exactly the size delta -- 364
    # bytes for the real 225-location hidden_item case, confirmed by
    # direct calculation against the real ROM), decompressing garbage into
    # the engine's core static RAM before `NitroMain` ever runs -- a white
    # screen, with no in-game error possible since nothing valid has
    # executed yet.
    #
    # Fixed here by patching this one field (and *only* this field --
    # this layer still refuses arbitrary secure-area writes, see `offset
    # < 0x4000` below) after every recompression. Two `compress_code()`
    # calls total, not a fixed-point loop: `SDK_COMPRESSED_STATIC_END` sits
    # inside the verbatim, never-compressed `data[:0x4000]` prefix, so
    # editing it cannot change the length of the *compressed* portion --
    # the second pass is therefore guaranteed (not just likely) to produce
    # the exact same total length as the first, confirmed both by this
    # reasoning and empirically (second-pass length matched first-pass
    # length on the real 225-location case, live-verified 2026-08-11 with
    # `ndspy`, and re-verified 2026-08-11 with `apnds`).
    #
    # Deliberately still unresolved here: this field write technically
    # falls inside the DS "secure area" whose checksum (`secureAreaChecksum`
    # in the ROM header) `apnds` never recomputes on save either (see `arm9`
    # section's own docstring) -- unlike `SDK_COMPRESSED_STATIC_END`'s
    # algorithm and exact byte range (fully confirmed above), the secure-
    # area checksum's precise algorithm was NOT successfully reverse-
    # engineered offline (a plain CRC-16 over `arm9[:0x4000]`, the
    # algorithm `apnds` already uses for the ROM header's own logo/header
    # checksums -- see `apnds/rom.py`'s `crc16`, applied to `HEADERCRC` --
    # does not reproduce the real ROM's stored `SECURECRC` value -- the
    # real algorithm needs the original DS secure-area KEY1 encryption
    # scheme, which this project does not implement). In practice this is
    # very unlikely to matter for this project's actual target platform
    # (BizHawk, an emulator -- real NDS hardware/flashcarts are the only
    # things known to validate this legacy anti-piracy checksum, and
    # `secureAreaDisable` is all-zero in the real vanilla ROM so it isn't
    # even pre-bypassed there either), but this has NOT been empirically
    # confirmed on BizHawk specifically -- a single live boot test of a
    # ROM with this fix applied is still the one remaining unknown before
    # trusting hidden_item substitution at scale again.
    _MODULE_PARAMS_ARM9_RAM_ADDRESS = 0x02000BA0
    _COMPRESSED_STATIC_END_FIELD_OFFSET = 0x14  # within ModuleParams
    _ARM9_HEADER_LEN = 0x4000  # the DS secure area, kept verbatim/uncompressed

    def read_main_code_decompressed(self) -> bytes:
        """Return the ARM9 main binary fully decompressed (see this
        section's own docstring for why this differs from the raw `arm9`
        property).

        Uses `apnds.lz.decompress_code` -- confirmed byte-for-byte
        identical to `ndspy.codeCompression.decompress(rom.arm9)` for both
        real ROMs (2026-08-11). `arm9` already excludes the 12-byte
        nitrocode trailer (see that property's own docstring), and that
        trailer plays no role in this algorithm (it is `decompress_code`'s
        own `rem` return value when called against the footer-inclusive
        buffer -- passing just `arm9` and `len(arm9)` as `compressed_top`
        is equivalent and simpler, since nothing here needs `rem`)."""
        body = self.arm9
        decompressed, _rem = decompress_code(body, len(body))
        return decompressed

    def _compressed_static_end_file_offset(self) -> int:
        """File offset (into `read_main_code_decompressed()`'s output) of
        the `SDK_COMPRESSED_STATIC_END` field this class's own
        `write_main_code_region` keeps in sync -- see that method's (and
        this section's) docstring for what this field is and why."""
        field_ram_address = self._MODULE_PARAMS_ARM9_RAM_ADDRESS + self._COMPRESSED_STATIC_END_FIELD_OFFSET
        return field_ram_address - self.arm9_ram_address

    def _compress_main_code(self, decompressed: bytes) -> tuple[bytes, bool]:
        """Recompress a full decompressed ARM9 main image back to its
        packed form: the first `_ARM9_HEADER_LEN` (0x4000) bytes -- the DS
        secure area -- copied through completely verbatim/uncompressed
        (same convention `ndspy.codeCompression.compress(isArm9=True)`
        used internally), everything after run through `apnds.lz.
        compress_code`, the "backward code" compression algorithm (same
        one `read_main_code_decompressed`/overlay handling use -- *not*
        plain LZ10).

        Returns `(packed_bytes, was_compressed)`. `compress_code` can
        return `None` (rare -- only if it cannot shrink the post-secure-
        area data at all); rather than hard-failing the whole patch, this
        falls back to writing the region through *uncompressed*
        (`was_compressed=False`), matching `crt0.s`'s own boot sequence:
        `_start` (`lib/asm/crt0.s`) unconditionally calls
        `MIi_UncompressBackward` with `SDK_COMPRESSED_STATIC_END` as its
        one argument, and `MIi_UncompressBackward` itself opens with `cmp
        r0, #0; beq <return>` -- a value of exactly 0 there is a real,
        clean no-op boot path (verified directly against the decomp
        source, 2026-08-11, community-suggested), not a guess. The caller
        (`write_main_code_regions`) is responsible for writing 0 into that
        field instead of a computed end-address when `was_compressed` is
        `False`."""
        header = bytes(decompressed[: self._ARM9_HEADER_LEN])
        tail = compress_code(bytes(decompressed[self._ARM9_HEADER_LEN :]))
        if tail is None:
            return header + bytes(decompressed[self._ARM9_HEADER_LEN :]), False
        return header + tail, True

    def _regenerate_arm9_footer(self, decompressed: bytes, old_footer: bytes) -> bytes:
        """Regenerate the 12-byte nitrocode trailer (see
        `_NITROCODE_FOOTER_SIGNATURE`'s own docstring) for a freshly
        recompressed ARM9 image, given the *previous* footer (`old_footer`,
        possibly `b""` if this ROM never had one).

        Recomputes the offset word via `apnds.code.get_start_info_offset`
        (the same signature-search apnds itself uses to locate this
        structure) rather than blindly copying the old footer's bytes
        through -- confirmed empirically (2026-08-11, both real ROMs) that
        this reproduces the exact original footer byte-for-byte on a
        no-op edit (decompress -> recompress with no changes -> compare),
        which is expected: the `DSStartParams` structure this offset
        points at sits inside the never-edited, never-recompressed secure
        area (`0xBA0 < 0x4000` on both ROMs), so its offset cannot change
        as a result of any edit this class allows (`write_main_code_
        regions` refuses edits before 0x4000). The trailing reserved word
        is carried through from `old_footer` unchanged (always observed as
        0 on both real ROMs; not known to be derived from ARM9 content, so
        there is nothing to recompute it from)."""
        offset = get_start_info_offset(decompressed, self.arm9_ram_address, self.arm9_entry_address)
        if offset is None:
            raise RomError(
                "apnds.code.get_start_info_offset could not locate the "
                "DSStartParams structure in the recompressed ARM9 image -- "
                "cannot regenerate the 12-byte nitrocode trailer this ROM "
                "had before this edit."
            )
        _old_offset, reserved_word = struct.unpack_from("<II", old_footer, 4)
        return self._NITROCODE_FOOTER_SIGNATURE + struct.pack("<II", offset, reserved_word)

    def write_main_code_region(self, offset: int, data: bytes) -> None:
        """Overwrite `len(data)` bytes at `offset` within the decompressed
        ARM9 main image (never resizes), then recompresses and replaces
        the ROM's packed ARM9 binary. Thin single-edit wrapper over
        `write_main_code_regions` -- see that method's docstring (and this
        section's own docstring) for the `SDK_COMPRESSED_STATIC_END`
        bookkeeping this does, and for why batching many edits into one
        `write_main_code_regions` call instead of many `write_main_code_
        region` calls matters (task M4.5/hidden_item -- each call
        decompresses/recompresses the full ~1.1 MB image; 225 individual
        calls, one per hidden_item location, took ~34 minutes)."""
        self.write_main_code_regions([(offset, data)])

    def write_main_code_regions(self, edits: list[tuple[int, bytes]]) -> None:
        """Apply every `(offset, data)` edit in `edits` to the decompressed
        ARM9 main image in a single decompress/recompress pass (each
        `offset`/`offset + len(data)` must be at or past 0x4000, same rule
        and same reason as `write_main_code_region` -- the DS secure area
        is never a valid target for *caller-supplied* edits through this
        method), then keeps `SDK_COMPRESSED_STATIC_END` in sync with the
        new compressed length (see this section's own docstring for what
        that field is and what silently corrupted the game's boot-time
        decompression before this was added) and replaces the ROM's
        packed ARM9 binary.

        Two `compress_code()` calls total, not one per edit and not a
        fixed-point loop: `SDK_COMPRESSED_STATIC_END` sits inside the
        verbatim, never-compressed `data[:0x4000]` prefix this class's own
        `_compress_main_code` always copies through unchanged, so editing
        it cannot change the length of the *compressed* portion -- the
        second pass is therefore guaranteed to reproduce the first pass's
        exact length (see this section's own docstring for the fuller
        reasoning and live verification)."""
        decompressed = bytearray(self.read_main_code_decompressed())
        for offset, data in edits:
            if offset < 0x4000:
                raise ValueError(
                    f"offset {offset:#x} is inside the first 0x4000 bytes (the DS secure area) -- "
                    "this layer refuses to touch it, see this module's ARM9 docstrings for why."
                )
            if offset + len(data) > len(decompressed):
                raise ValueError(
                    f"write of {len(data)} bytes at offset {offset:#x} runs past the decompressed "
                    f"ARM9 image's own size ({len(decompressed):#x})."
                )
            decompressed[offset : offset + len(data)] = data

        # Pass 1: compress with whatever SDK_COMPRESSED_STATIC_END value
        # is already present (stale, from the source ROM) -- only used to
        # learn the new compressed length (or, on the rare `compress_code`
        # failure, that this write falls back to uncompressed -- see
        # `_compress_main_code`'s own docstring). `compress_code`'s
        # success/failure is deterministic for identical input bytes, and
        # the field write below only ever touches the never-compressed
        # header, so pass 2 is guaranteed to make the same compressed-vs-
        # uncompressed choice as pass 1.
        provisional, was_compressed = self._compress_main_code(bytes(decompressed))
        new_compressed_static_end = self.arm9_ram_address + len(provisional) if was_compressed else 0

        field_offset = self._compressed_static_end_file_offset()
        struct.pack_into("<I", decompressed, field_offset, new_compressed_static_end)

        # Pass 2: recompress with the now-correct field value. Guaranteed
        # (not just expected) to match pass 1's length -- see this
        # method's own docstring for why the field's location (inside the
        # verbatim, never-compressed secure-area prefix) makes this safe
        # rather than requiring a fixed-point loop.
        recompressed, _was_compressed = self._compress_main_code(bytes(decompressed))

        _old_body, old_footer = self._split_arm9_footer()
        if old_footer:
            new_footer = self._regenerate_arm9_footer(bytes(decompressed), old_footer)
        else:
            new_footer = b""
        self._rom.arm9 = recompressed + new_footer

    # -- Output -----------------------------------------------------------------

    def save_bytes(self) -> bytes:
        """Repack the (patched) ROM container and return its bytes.

        Note: `apnds` fully repacks the ROM container on save (same as
        `ndspy` before it), so the output is never byte-identical to the
        input, even for completely unmodified files (see
        docs/architecture.md, "## Spikes", Spike 1). Individual NitroFS
        file contents round-trip exactly; the container framing (file
        table, offsets, padding) does not.

        `fill_tail=False`: pads only to the next `apnds.rom.Rom.
        rom_alignment` boundary, not all the way out to the cartridge's
        power-of-2 capacity (`fill_tail=True` would pad to 134,217,728
        bytes -- 128 MiB -- vs. the ~126.6 MB this produces, matching the
        order of magnitude `ndspy.rom.NintendoDSRom.save()` produced and
        that this project's own BizHawk testing has been done against)."""
        return self._rom.to_bytes(fill_tail=False)

    def save(self, path: str | Path) -> None:
        """Repack the (patched) ROM and write it to `path`."""
        Path(path).write_bytes(self.save_bytes())
