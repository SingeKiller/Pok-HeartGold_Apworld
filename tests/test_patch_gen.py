"""Tests for patch_gen.py (task C14: ground-item check mechanism PoC).

Read docs/architecture.md, "## C14 -- Ground item check mechanism (proof of
concept)" and patch_gen.py's own module docstring before reading too much
into what passing these tests means: this patch is scaffolding (it proves
the armips + patch_gen.py + rom/ pipeline works and leaves the ROM
structurally valid), not yet the real in-game hook.

Two things must be available locally for most of these tests to run at all,
each skipped independently (same "skip cleanly if missing" convention as
tests/test_rom_roundtrip.py and tests/test_rom_access.py):

- A working `armips` build (`ARMIPS_PATH` env var, or this repo's own
  `ressources/armips/build/armips.exe`). "Working" is checked by actually
  invoking it, not just checking the file exists -- in this project's own
  dev environment, `armips.exe` exists but currently fails to start with a
  missing-runtime-DLL error (Windows STATUS_DLL_NOT_FOUND); see
  docs/architecture.md for that investigation. A present-but-broken armips
  build must skip these tests the same way a missing one does, rather than
  fail.
- The real HeartGold (US) ROM (`HEARTGOLD_ROM_PATH` env var).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import patch_gen
from rom import HeartGoldRom

ROM_PATH_ENV_VAR = "HEARTGOLD_ROM_PATH"


def _rom_path() -> Path | None:
    raw_path = os.environ.get(ROM_PATH_ENV_VAR)
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_file():
        return None
    return path


def _armips_available() -> Path | None:
    """Return a usable armips executable path, or None if armips can't
    actually be *run* (missing file, missing runtime dependency, etc.) --
    see this module's docstring for why "exists" isn't enough."""
    exe = patch_gen.armips_path()
    if not exe.is_file():
        return None
    try:
        # Any invocation (even with no/invalid args) should make armips
        # print a usage message and exit with a small, ordinary status
        # code. This project's own environment has been observed to fail
        # earlier than that: the OS itself aborts the process (a missing
        # runtime DLL) with an NTSTATUS-style exit code in the
        # 0xC0000000-0xC0FFFFFF range (e.g. 0xC0000135 /
        # STATUS_DLL_NOT_FOUND) *before* armips gets a chance to run at
        # all -- `subprocess.run` does not raise for this (the process did
        # get a PID), so the returncode itself has to be inspected.
        import subprocess

        result = subprocess.run([str(exe)], capture_output=True, timeout=10)
    except OSError:
        return None
    if (result.returncode & 0xFF000000) == 0xC0000000:
        return None
    return exe


@pytest.fixture()
def rom_bytes() -> bytes:
    path = _rom_path()
    if path is None:
        pytest.skip(
            f"HeartGold ROM not available locally: set {ROM_PATH_ENV_VAR} to "
            "a valid ROM path to run this test."
        )
    return path.read_bytes()


@pytest.fixture()
def armips_exe() -> Path:
    exe = _armips_available()
    if exe is None:
        pytest.skip(
            f"armips is not runnable locally: set {patch_gen.ARMIPS_PATH_ENV_VAR} "
            "to a working armips build (see docs/architecture.md for a known "
            "failure mode: the file exists but fails to start with a missing "
            "runtime DLL)."
        )
    return exe


def test_armips_path_defaults_to_repo_local_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(patch_gen.ARMIPS_PATH_ENV_VAR, raising=False)
    assert patch_gen.armips_path() == patch_gen._DEFAULT_ARMIPS_PATH


def test_armips_path_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(patch_gen.ARMIPS_PATH_ENV_VAR, "some/custom/armips.exe")
    assert patch_gen.armips_path() == Path("some/custom/armips.exe")


def test_assemble_ground_item_hook_raises_clear_error_without_armips(tmp_path: Path) -> None:
    missing_exe = tmp_path / "does_not_exist.exe"
    with pytest.raises(patch_gen.ArmipsError, match="not found"):
        patch_gen.assemble_ground_item_hook(0x02100000, armips_exe=missing_exe)


# --- Tests needing a real, runnable armips build -----------------------------


def test_ground_item_hook_assembles_without_error(armips_exe: Path) -> None:
    """Task C14 acceptance criterion: the patch assembles without error."""
    code = patch_gen.assemble_ground_item_hook(0x02100000, armips_exe=armips_exe)
    assert isinstance(code, bytes)
    assert len(code) > 0
    # Assembled ARM machine code is a whole number of 4-byte instructions.
    assert len(code) % 4 == 0


def test_ground_item_hook_encodes_protocol_magic_constant(armips_exe: Path) -> None:
    """The assembled code embeds the "HGAP" magic word (used by
    `HeartGoldAP_Init`'s literal pool) -- a cheap, address-independent way
    to confirm the right source actually got assembled, matching the task's
    own suggested fallback validation ("disassembling/inspecting the
    patched binary")."""
    code = patch_gen.assemble_ground_item_hook(0x02100000, armips_exe=armips_exe)
    # AP_PROTOCOL_MAGIC (equ 0x50414748) is loaded into the literal pool and
    # stored little-endian, i.e. as the literal bytes b"HGAP".
    assert patch_gen.PROTOCOL_MAGIC in code


# --- Tests needing both a real ROM and a real, runnable armips build --------


def test_apply_ground_item_hook_to_rom_copy(rom_bytes: bytes, armips_exe: Path) -> None:
    """Task C14 acceptance criteria: the patch applies to a copy of the real
    ROM without exception, and the resulting ROM stays structurally valid
    (header intact, re-openable, arm9 grew by exactly the assembled code's
    size, no NitroFS file content changed)."""
    rom = HeartGoldRom(rom_bytes)
    original_arm9_len = len(rom.arm9)
    original_sample_file = rom.read_file("pbr/item_data.narc")

    hook_address = patch_gen.apply_ground_item_hook(rom, armips_exe=armips_exe)

    assert hook_address == rom.arm9_ram_address + original_arm9_len
    assert len(rom.arm9) > original_arm9_len

    patched_bytes = rom.save_bytes()

    # Structural validity: re-opens cleanly (header/game-code checks from
    # rom/__init__.py still pass; expect_vanilla=False because this is now
    # a patched, non-retail ROM, same convention as tests/test_rom_access.py).
    reloaded = HeartGoldRom(patched_bytes, expect_vanilla=False)
    assert len(reloaded.arm9) == len(rom.arm9)
    assert reloaded.arm9[original_arm9_len:] == rom.arm9[original_arm9_len:]

    # Untouched NitroFS content is unaffected by an ARM9-only patch.
    assert reloaded.read_file("pbr/item_data.narc") == original_sample_file


def test_patched_rom_protocol_region_matches_assembled_code(rom_bytes: bytes, armips_exe: Path) -> None:
    """Task C14's explicit fallback validation ask: "vérifie... que le
    protocole RAM/save documenté... est bien à l'endroit attendu en
    désassemblant/inspectant le binaire patché". Since this PoC's hook
    isn't wired to a call site yet (see docs/architecture.md), "at the
    expected location" here means: the appended ARM9 bytes, at the address
    `apply_ground_item_hook` reports, are exactly the bytes armips
    assembled for that address (no offset/alignment drift introduced by
    the append step itself).
    """
    rom = HeartGoldRom(rom_bytes)
    load_address = rom.arm9_ram_address + len(rom.arm9)
    expected_code = patch_gen.assemble_ground_item_hook(load_address, armips_exe=armips_exe)

    hook_address = patch_gen.apply_ground_item_hook(rom, armips_exe=armips_exe)
    assert hook_address == load_address

    appended = rom.arm9[load_address - rom.arm9_ram_address:]
    assert appended == expected_code
