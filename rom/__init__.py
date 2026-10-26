from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import apnds.narc
import apnds.rom
from apnds.code import get_start_info_offset
from apnds.lz import compress_code, decompress_code


class RomError(Exception):
    pass


class InvalidRomError(RomError):
    pass


class NitroFsFileNotFoundError(RomError):
    pass


HEARTGOLD_US_MD5 = "258cea3a62ac0d6eb04b5a0fd764d788"
HEARTGOLD_US_ID_CODE = b"IPKE"

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

_MIN_PLAUSIBLE_ROM_SIZE = 0x4000

_RETAIL_ROM_SIZE = 0x8000000
_USED_SIZE_OFFSET = 0x80
_VERSION_BY_USED_MD5: dict[str, str] = {
    "4dc7993a7db6858b43da83be434ba673": "heartgold",
    "380e7441c09c938cdcc8bd28546037e2": "soulsilver",
}
_GAME_NAMES = {b"IPK": "HeartGold", b"IPG": "SoulSilver"}
_REGION_NAMES = {
    ord("E"): "USA", ord("P"): "Europe", ord("J"): "Japan", ord("K"): "Korea", ord("D"): "Germany",
    ord("F"): "France", ord("I"): "Italy", ord("S"): "Spain",
}


def identify_rom(data: bytes) -> tuple[str | None, bytes]:
    version = _VERSION_BY_MD5.get(hashlib.md5(data).hexdigest())
    if version is not None:
        return version, data
    if _MIN_PLAUSIBLE_ROM_SIZE <= len(data) <= _RETAIL_ROM_SIZE:
        (used,) = struct.unpack_from("<I", data, _USED_SIZE_OFFSET)
        if _MIN_PLAUSIBLE_ROM_SIZE <= used <= len(data) and not data[used:].strip(b"\xff"):
            version = _VERSION_BY_USED_MD5.get(hashlib.md5(data[:used]).hexdigest())
            if version is not None:
                return version, data[:used] + b"\xff" * (_RETAIL_ROM_SIZE - used)
    return None, data


def describe_rom(data: bytes) -> str:
    if len(data) < 0x10:
        return "not a Nintendo DS ROM"
    code = bytes(data[0x0C:0x10])
    game = _GAME_NAMES.get(code[:3])
    printable = code.decode("ascii", "replace")
    if game is None:
        return f"not Pokemon HeartGold or SoulSilver (game code {printable})"
    region = _REGION_NAMES.get(code[3], "unknown region")
    return f"Pokemon {game} ({region}, game code {printable})"


class HeartGoldRom:
    _NITROCODE_FOOTER_SIGNATURE = bytes.fromhex("2106C0DE")
    _NITROCODE_FOOTER_SIZE = 12

    def __init__(self, data: bytes, *, expect_vanilla: bool = True) -> None:
        self.version: str | None
        self.version, data = self._validate_size_and_hash(data, expect_vanilla=expect_vanilla)
        try:
            self._rom = apnds.rom.Rom.from_bytes(data)
        except Exception as exc:
            raise InvalidRomError(
                "Could not parse this file as a Nintendo DS ROM (.nds) even "
                "though its size (and, if checked, MD5) looked right -- the "
                "file is likely corrupted."
            ) from exc
        self._validate_game_code()

    def _split_arm9_footer(self) -> tuple[bytes, bytes]:
        raw = bytes(self._rom.arm9)
        footer_start = len(raw) - self._NITROCODE_FOOTER_SIZE
        if len(raw) > self._NITROCODE_FOOTER_SIZE and raw[footer_start : footer_start + 4] == self._NITROCODE_FOOTER_SIGNATURE:
            return raw[:footer_start], raw[footer_start:]
        return raw, b""

    @staticmethod
    def _validate_size_and_hash(data: bytes, *, expect_vanilla: bool) -> tuple[str | None, bytes]:
        if len(data) < _MIN_PLAUSIBLE_ROM_SIZE:
            raise InvalidRomError(
                f"File is only {len(data)} bytes -- too small to be a "
                "Nintendo DS ROM. It is likely truncated or corrupted."
            )
        if not expect_vanilla:
            return None, data
        version, data = identify_rom(data)
        if version is None:
            raise InvalidRomError(
                f"This ROM is {describe_rom(data)}, or a modified dump: an "
                "unmodified Pokemon HeartGold or SoulSilver (USA) ROM is needed "
                "(game code IPKE or IPGE). Other regions and already-patched "
                "ROMs do not work."
            )
        return version, data

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
        if id_code not in _ID_CODE_BY_VERSION.values():
            raise InvalidRomError(
                f"ROM header game code is {id_code!r}, expected one of "
                f"{sorted(_ID_CODE_BY_VERSION.values())!r} (Pokemon HeartGold/SoulSilver, USA)."
            )

    @classmethod
    def open(cls, path: str | Path, *, expect_vanilla: bool = True) -> HeartGoldRom:
        rom_path = Path(path)
        if not rom_path.is_file():
            raise InvalidRomError(f"ROM file not found: {rom_path}")
        return cls(rom_path.read_bytes(), expect_vanilla=expect_vanilla)

    @staticmethod
    def _normalize_nitrofs_path(nitrofs_path: str) -> str:
        return "/" + nitrofs_path.lstrip("/")

    def read_file(self, nitrofs_path: str) -> bytes:
        try:
            return bytes(self._rom.files[self._normalize_nitrofs_path(nitrofs_path)])
        except KeyError as exc:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            ) from exc

    def write_file(self, nitrofs_path: str, data: bytes) -> None:
        key = self._normalize_nitrofs_path(nitrofs_path)
        if key not in self._rom.files:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            )
        self._rom.files[key] = bytes(data)

    def read_narc(self, nitrofs_path: str) -> apnds.narc.Narc:
        return apnds.narc.Narc.from_bytes(self.read_file(nitrofs_path))

    def write_narc(self, nitrofs_path: str, narc: apnds.narc.Narc) -> None:
        self.write_file(nitrofs_path, narc.to_bytes())

    @staticmethod
    def nitrofs_file_span(packed: bytes, nitrofs_path: str) -> tuple[int, int]:
        key = HeartGoldRom._normalize_nitrofs_path(nitrofs_path)
        header = apnds.rom.Header(packed[: apnds.rom.HeaderField.ENTIRE_HEADER])
        fntb = header.get_rom_region(
            packed, apnds.rom.HeaderField.FNTB_ROMOFFSET, apnds.rom.HeaderField.FNTB_BSIZE
        )
        file_id = apnds.rom.get_filename_id_map(fntb).get(key)
        if file_id is None:
            raise NitroFsFileNotFoundError(
                f"NitroFS file not found: {nitrofs_path!r}. This path "
                "either does not exist in this ROM or is misspelled."
            )
        fatb = header.get_rom_region(
            packed, apnds.rom.HeaderField.FATB_ROMOFFSET, apnds.rom.HeaderField.FATB_BSIZE
        )
        start, end = struct.unpack_from("<II", fatb, file_id * 8)
        return start, end

    @staticmethod
    def narc_subfile_span(narc_data: bytes, index: int) -> tuple[int, int]:
        magic, _bom, _version, _size, header_size = struct.unpack_from("<IHHIH", narc_data, 0)
        if magic != apnds.narc.HEADER_MAGIC:
            raise RomError("data is not a valid NARC: header magic does not match")
        fatb_position = header_size
        if narc_data[fatb_position : fatb_position + 4] != b"BTAF":
            raise RomError("data is not a valid NARC: FATB magic does not match")
        fatb_length, entry_count = struct.unpack_from("<2I", narc_data, fatb_position + 4)
        if not 0 <= index < entry_count:
            raise ValueError(f"NARC sub-file index {index} out of range (archive has {entry_count} entries)")
        fntb_position = fatb_position + fatb_length
        if narc_data[fntb_position : fntb_position + 4] != b"BTNF":
            raise RomError("data is not a valid NARC: FNTB magic does not match")
        (fntb_length,) = struct.unpack_from("<I", narc_data, fntb_position + 4)
        fimg_position = fntb_position + fntb_length
        if narc_data[fimg_position : fimg_position + 4] != b"GMIF":
            raise RomError("data is not a valid NARC: FIMG magic does not match")
        image_base = fimg_position + 8
        start, end = struct.unpack_from("<2I", narc_data, fatb_position + 12 + index * 8)
        return image_base + start, image_base + end

    @property
    def arm9(self) -> bytes:
        body, _footer = self._split_arm9_footer()
        return body

    @property
    def arm9_ram_address(self) -> int:
        return self._rom.header.get_le(apnds.rom.HeaderField.ARM9_LOADADDR)

    @property
    def arm9_entry_address(self) -> int:
        return self._rom.header.get_le(apnds.rom.HeaderField.ARM9_ENTRYPOINT)

    def append_to_arm9(self, data: bytes) -> int:
        body, footer = self._split_arm9_footer()
        target_address = self.arm9_ram_address + len(body)
        self._rom.arm9 = body + bytes(data) + footer
        return target_address

    def _find_overlay(self, overlay_id: int) -> apnds.rom.Overlay:
        for overlay in self._rom.arm9_overlays:
            if overlay.id == overlay_id:
                return overlay
        raise ValueError(f"overlay {overlay_id} not found in the ARM9 overlay table")

    def read_overlay(self, overlay_id: int) -> bytes:
        overlay = self._find_overlay(overlay_id)
        if not overlay.is_compressed():
            return bytes(overlay.data)
        decompressed, _rem = decompress_code(overlay.data, overlay.compressed_size)
        return decompressed

    def write_overlay(self, overlay_id: int, data: bytes) -> None:
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

    _MODULE_PARAMS_ARM9_RAM_ADDRESS = 0x02000BA0
    _COMPRESSED_STATIC_END_FIELD_OFFSET = 0x14
    _ARM9_HEADER_LEN = 0x4000

    def read_main_code_decompressed(self) -> bytes:
        body = self.arm9
        decompressed, _rem = decompress_code(body, len(body))
        return decompressed

    def _compressed_static_end_file_offset(self) -> int:
        field_ram_address = self._MODULE_PARAMS_ARM9_RAM_ADDRESS + self._COMPRESSED_STATIC_END_FIELD_OFFSET
        return field_ram_address - self.arm9_ram_address

    def _compress_main_code(self, decompressed: bytes) -> tuple[bytes, bool]:
        header = bytes(decompressed[: self._ARM9_HEADER_LEN])
        tail = compress_code(bytes(decompressed[self._ARM9_HEADER_LEN :]))
        if tail is None:
            return header + bytes(decompressed[self._ARM9_HEADER_LEN :]), False
        return header + tail, True

    def _regenerate_arm9_footer(self, decompressed: bytes, old_footer: bytes) -> bytes:
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
        self.write_main_code_regions([(offset, data)])

    def write_main_code_regions(self, edits: list[tuple[int, bytes]]) -> None:
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

        provisional, was_compressed = self._compress_main_code(bytes(decompressed))
        new_compressed_static_end = self.arm9_ram_address + len(provisional) if was_compressed else 0

        field_offset = self._compressed_static_end_file_offset()
        struct.pack_into("<I", decompressed, field_offset, new_compressed_static_end)

        recompressed, _was_compressed = self._compress_main_code(bytes(decompressed))

        _old_body, old_footer = self._split_arm9_footer()
        if old_footer:
            new_footer = self._regenerate_arm9_footer(bytes(decompressed), old_footer)
        else:
            new_footer = b""
        self._rom.arm9 = recompressed + new_footer

    def save_bytes(self) -> bytes:
        return self._rom.to_bytes(fill_tail=False)

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.save_bytes())
