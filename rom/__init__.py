# rom/__init__.py
#
# ROM access layer: opening a vanilla Pokemon HeartGold (US) ROM (with an
# early, actionable sanity check for wrong game/region/corrupted file),
# reading/writing individual files inside its NitroFS filesystem, and
# saving the resulting patched ROM back out.
#
# Uses apnds (MIT, vendored under /apnds/, no separate runtime install
# needed) -- replaces an earlier ndspy-based implementation (GPLv3,
# couldn't be bundled the same way). apnds.rom.Rom.to_bytes() fully
# repacks the ROM container, so a saved ROM is never byte-identical to
# the original even when no content changed -- only individual NitroFS
# file contents are guaranteed to round-trip exactly.
#
# Category-specific reader/writers for randomized data tables live in
# dedicated submodules built on the primitives here: rom/itemdata.py,
# rom/speciesdata.py, rom/trainerdata.py, rom/encounterdata.py,
# rom/eventdata.py.

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
    """The supplied file is not usable as a Pokemon HeartGold (US) ROM:
    wrong game, wrong region, or a corrupted/truncated file."""


class NitroFsFileNotFoundError(RomError):
    """The requested NitroFS path does not exist in this ROM."""


HEARTGOLD_US_MD5 = "258cea3a62ac0d6eb04b5a0fd764d788"
HEARTGOLD_US_ID_CODE = b"IPKE"

# HeartGold's sister version. Live-verified: despite the different MD5/id
# code, its decompressed ARM9 image is byte-for-byte the same length as
# HeartGold's (1,122,040 bytes), every NitroFS numbered path this project
# reads/writes has the same sub-file count, and the hidden_item table
# sits at the same RAM address -- the two versions share the same
# underlying build/layout, differing only in content.
SOULSILVER_US_MD5 = "8a6c8888bed9e1dce952f840351b73f2"
SOULSILVER_US_ID_CODE = b"IPGE"

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
    """Thin wrapper around apnds.rom.Rom for a Pokemon HeartGold/SoulSilver
    (US) ROM: validates the ROM once at load time so every later NitroFS
    read/write can assume it's working with a known, supported game.
    Accepts either version -- despite the name, this class is not
    HeartGold-specific; every rom/*.py access layer built on it reads/
    writes generically by NitroFS path/offset.

    `expect_vanilla` (default True) gates the exact-MD5 check: the ROM the
    user supplies must be one of the two unmodified retail dumps. Once
    this project has patched and repacked a ROM, the result is no longer
    byte-identical to the original container-wise; re-wrapping that
    already-patched output must pass `expect_vanilla=False` to skip the
    MD5 check while keeping the game-code + size sanity checks. `version`
    is then unknown (None) -- there's no MD5 to look it up by."""

    # The 12-byte "nitrocode" trailer some ROM tools append to the ARM9
    # binary after the compressed code: signature (4 bytes) + the file
    # offset of DSStartParams relative to the ARM9 load address (4 bytes)
    # + a reserved word (always 0 on both real ROMs). apnds treats this as
    # opaque pass-through data; ndspy's .arm9 never included it, so every
    # caller of this class's own arm9 property is written against the
    # without-footer convention. `_split_arm9_footer` keeps that
    # convention intact on top of apnds's footer-inclusive representation.
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
        """Split self._rom.arm9 into (body, footer), where footer is the
        12-byte nitrocode trailer or b"" if this ROM doesn't have one."""
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
        filesystem path."""
        rom_path = Path(path)
        if not rom_path.is_file():
            raise InvalidRomError(f"ROM file not found: {rom_path}")
        return cls(rom_path.read_bytes(), expect_vanilla=expect_vanilla)

    # -- Raw NitroFS file access ---------------------------------------------

    @staticmethod
    def _normalize_nitrofs_path(nitrofs_path: str) -> str:
        """apnds.rom.Rom.files keys every path with a leading slash;
        callers here pass bare paths (ndspy convention), so normalize."""
        return "/" + nitrofs_path.lstrip("/")

    def read_file(self, nitrofs_path: str) -> bytes:
        """Read a raw file from the ROM's NitroFS filesystem by its data
        path (e.g. "pbr/item_data.narc", or a numbered path like
        "a/0/1/7")."""
        try:
            return bytes(self._rom.files[self._normalize_nitrofs_path(nitrofs_path)])
        except KeyError as exc:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            ) from exc

    def write_file(self, nitrofs_path: str, data: bytes) -> None:
        """Replace a raw file in the ROM's NitroFS filesystem. The path
        must already exist -- this layer never adds new NitroFS files,
        only replaces existing ones (apnds.rom.Rom.files is a plain dict
        that would otherwise silently create a new entry)."""
        key = self._normalize_nitrofs_path(nitrofs_path)
        if key not in self._rom.files:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            )
        self._rom.files[key] = bytes(data)

    # -- NARC convenience -----------------------------------------------------

    def read_narc(self, nitrofs_path: str) -> apnds.narc.Narc:
        """Read a NitroFS file and parse it as a NARC archive (items,
        species, trainers, encounters, ... are NARC containers holding
        one sub-file per entry)."""
        return apnds.narc.Narc.from_bytes(self.read_file(nitrofs_path))

    def write_narc(self, nitrofs_path: str, narc: apnds.narc.Narc) -> None:
        """Serialize a NARC archive and write it back to the given NitroFS
        path."""
        self.write_file(nitrofs_path, narc.to_bytes())

    # -- ARM9 static binary access ---------------------------------------
    #
    # Narrow, append-only access to the ARM9 executable itself, distinct
    # from the NitroFS data-table access above. See NOTES.md for the
    # secure-area checksum risk analysis this design is built around --
    # short version: the first 0x4000 bytes are the DS "secure area",
    # checksummed by the cartridge/BIOS, which apnds never recomputes on
    # save. append_to_arm9() only ever appends after the current end (far
    # past 0x4000), so the secure area is never touched and the existing
    # checksum stays valid.
    #
    # apnds.rom.Rom.arm9 also includes a 12-byte "nitrocode" trailer some
    # ROMs carry after the packed ARM9 code -- ndspy's .arm9 never
    # included it, so arm9/append_to_arm9/write_main_code_regions all
    # route through _split_arm9_footer to keep excluding it.

    @property
    def arm9(self) -> bytes:
        """The raw ARM9 executable currently packed in this ROM (read-only
        snapshot; mutate via append_to_arm9(), never in place). Excludes
        the 12-byte nitrocode trailer if present."""
        body, _footer = self._split_arm9_footer()
        return body

    @property
    def arm9_ram_address(self) -> int:
        """The RAM address the ARM9 binary's first byte is loaded at."""
        return self._rom.header.get_le(apnds.rom.HeaderField.ARM9_LOADADDR)

    @property
    def arm9_entry_address(self) -> int:
        """The RAM address ARM9 execution starts at after the BIOS/secure
        area handoff. Not currently used as a patch target (hooking the
        entry point directly would mean editing secure-area bytes)."""
        return self._rom.header.get_le(apnds.rom.HeaderField.ARM9_ENTRYPOINT)

    def append_to_arm9(self, data: bytes) -> int:
        """Append `data` to the end of the ARM9 binary and return the RAM
        address it now lives at. `data` is appended right after the ARM9
        body and before the 12-byte nitrocode trailer, if present -- the
        trailer's own offset word points inside the never-moved secure
        area, so it's carried through unchanged."""
        body, footer = self._split_arm9_footer()
        target_address = self.arm9_ram_address + len(body)
        self._rom.arm9 = body + bytes(data) + footer
        return target_address

    # -- ARM9 overlay access -----------------------------------------------
    #
    # Unlike the main ARM9 binary above (append-only, due to the DS
    # secure-area checksum), an overlay is a plain NitroFS file with its
    # own independent per-overlay compression flag and no DS-wide checksum
    # concern -- so in-place edits are safe here with respect to boot
    # integrity. This does not make editing compiled code/data inside an
    # overlay low-risk in general: an overlay mixes real ARM machine code
    # with constant data, so a wrong offset can corrupt an instruction,
    # not just misplace a value.

    def _find_overlay(self, overlay_id: int) -> apnds.rom.Overlay:
        for overlay in self._rom.arm9_overlays:
            if overlay.id == overlay_id:
                return overlay
        raise ValueError(f"overlay {overlay_id} not found in the ARM9 overlay table")

    def read_overlay(self, overlay_id: int) -> bytes:
        """Return one ARM9 overlay's data, decompressed if needed. Uses
        apnds.lz.decompress_code -- the same "backward code" algorithm
        read_main_code_decompressed uses for the main ARM9 image, NOT
        plain LZ10 (used for e.g. graphics assets) -- confirmed
        empirically against a real ROM overlay: LZ10's decompress raises
        on this data outright, decompress_code round-trips it exactly."""
        overlay = self._find_overlay(overlay_id)
        if not overlay.is_compressed():
            return bytes(overlay.data)
        decompressed, _rem = decompress_code(overlay.data, overlay.compressed_size)
        return decompressed

    def write_overlay(self, overlay_id: int, data: bytes) -> None:
        """Replace one ARM9 overlay's data in place, re-compressing first
        if the overlay was originally compressed (preserving its existing
        compressed/uncompressed state). apnds.rom.construct_overlay_table
        regenerates the whole overlay table from each Overlay object's own
        fields at Rom.to_bytes() time, so updating .data/.compressed_size
        here is sufficient -- no separate table patch needed."""
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

    # -- ARM9 main-image decompressed access ------------------------------
    #
    # `arm9` above is the ARM9 binary exactly as packed in the ROM --
    # LZ-compressed beyond the first 0x4000-byte secure area. Static ARM9
    # data (e.g. the hidden_item table) can only be located/read against
    # the decompressed image. See NOTES.md for the full derivation and
    # the SDK_COMPRESSED_STATIC_END boot-time bug this section's write
    # path guards against (a stale value there corrupted the engine's own
    # self-decompression and produced a white screen on boot).
    _MODULE_PARAMS_ARM9_RAM_ADDRESS = 0x02000BA0
    _COMPRESSED_STATIC_END_FIELD_OFFSET = 0x14  # within ModuleParams
    _ARM9_HEADER_LEN = 0x4000  # the DS secure area, kept verbatim/uncompressed

    def read_main_code_decompressed(self) -> bytes:
        """Return the ARM9 main binary fully decompressed. Uses
        apnds.lz.decompress_code."""
        body = self.arm9
        decompressed, _rem = decompress_code(body, len(body))
        return decompressed

    def _compressed_static_end_file_offset(self) -> int:
        """File offset (into read_main_code_decompressed()'s output) of
        the SDK_COMPRESSED_STATIC_END field write_main_code_regions
        keeps in sync."""
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
        """Regenerate the 12-byte nitrocode trailer for a freshly
        recompressed ARM9 image, given the previous footer (possibly b""
        if this ROM never had one). Recomputes the offset word via
        apnds.code.get_start_info_offset rather than blindly copying the
        old footer through -- confirmed empirically to reproduce the
        exact original footer byte-for-byte on a no-op edit, since the
        DSStartParams structure it points at sits inside the never-
        edited secure area. The trailing reserved word is carried
        through unchanged (always observed as 0 on both real ROMs)."""
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
        """Overwrite len(data) bytes at offset within the decompressed
        ARM9 main image (never resizes), then recompresses and replaces
        the ROM's packed ARM9 binary. Thin single-edit wrapper over
        write_main_code_regions -- batch many edits into one call instead
        of many single calls when possible: each call decompresses/
        recompresses the full ~1.1 MB image (225 individual calls took
        ~34 minutes; one batched pass is seconds)."""
        self.write_main_code_regions([(offset, data)])

    def write_main_code_regions(self, edits: list[tuple[int, bytes]]) -> None:
        """Apply every (offset, data) edit to the decompressed ARM9 main
        image in a single decompress/recompress pass (each offset must be
        at or past 0x4000 -- the DS secure area is never a valid target),
        then keeps SDK_COMPRESSED_STATIC_END in sync with the new
        compressed length and replaces the ROM's packed ARM9 binary.

        Two compress_code() calls total, not a fixed-point loop:
        SDK_COMPRESSED_STATIC_END sits inside the verbatim, never-
        compressed data[:0x4000] prefix, so editing it cannot change the
        compressed portion's length -- pass 2 is guaranteed to reproduce
        pass 1's exact length."""
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
        # is already present (stale) -- only used to learn the new
        # compressed length (or that this write falls back to
        # uncompressed).
        provisional, was_compressed = self._compress_main_code(bytes(decompressed))
        new_compressed_static_end = self.arm9_ram_address + len(provisional) if was_compressed else 0

        field_offset = self._compressed_static_end_file_offset()
        struct.pack_into("<I", decompressed, field_offset, new_compressed_static_end)

        # Pass 2: recompress with the now-correct field value.
        recompressed, _was_compressed = self._compress_main_code(bytes(decompressed))

        _old_body, old_footer = self._split_arm9_footer()
        if old_footer:
            new_footer = self._regenerate_arm9_footer(bytes(decompressed), old_footer)
        else:
            new_footer = b""
        self._rom.arm9 = recompressed + new_footer

    # -- Output -----------------------------------------------------------------

    def save_bytes(self) -> bytes:
        """Repack the (patched) ROM container and return its bytes. apnds
        fully repacks the container on save, so the output is never
        byte-identical to the input even for unmodified files -- only
        individual NitroFS file contents round-trip exactly.
        fill_tail=False pads to the next alignment boundary, not all the
        way to the cartridge's power-of-2 capacity."""
        return self._rom.to_bytes(fill_tail=False)

    def save(self, path: str | Path) -> None:
        """Repack the (patched) ROM and write it to `path`."""
        Path(path).write_bytes(self.save_bytes())
