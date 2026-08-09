#!/usr/bin/env python3
"""patch_gen.py

Task C14 -- ground-item check mechanism proof of concept. Assembles
`patches/ground_item_hook.s` with `armips` and applies the result to a
Pokemon HeartGold (US) ROM via `rom/`'s append-only ARM9 access
(`HeartGoldRom.append_to_arm9`, see that module for the safety rationale).

Read docs/architecture.md, "## C14 -- Ground item check mechanism (proof of
concept)" before relying on this for anything beyond what it actually is:
this patch is scaffolding that proves the armips + patch_gen.py + rom/
pipeline works end-to-end (assembles real ARM code, appends it to the ARM9
binary without touching the DS secure area, leaves the ROM structurally
valid) -- it does **not** yet hook any real in-game call site (that hook
point's ROM address could not be safely determined in this task's session;
see docs/architecture.md for the full investigation and why). The two
functions this patch adds (`HeartGoldAP_Init`,
`HeartGoldAP_RecordGroundItemCheck`) are present in the patched ROM's ARM9
binary but are not called from anywhere yet.

`armips` is not on `PATH` in this project's dev environment (see
docs/architecture.md, "## ROM code injection strategy"); its path is read
from the `ARMIPS_PATH` environment variable, following the same convention
already used for `ARCHIPELAGO_PATH` (tests/conftest.py) and
`HEARTGOLD_ROM_PATH` (tests/test_rom_roundtrip.py, tests/test_rom_access.py),
falling back to this repository's own local build,
`ressources/armips/build/armips.exe`.

Usage:
    python patch_gen.py --rom <path to vanilla HeartGold (US) .nds> --out <output .nds>
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rom import HeartGoldRom

ROOT = Path(__file__).resolve().parent
PATCH_SOURCE = ROOT / "patches" / "ground_item_hook.s"

ARMIPS_PATH_ENV_VAR = "ARMIPS_PATH"
_DEFAULT_ARMIPS_PATH = ROOT / "ressources" / "armips" / "build" / "armips.exe"

# Fixed EWRAM scratch address for the AP protocol struct -- see
# patches/ground_item_hook.s's header comment and docs/architecture.md for
# the struct layout and why this address was chosen (near-top-of-EWRAM
# convention, same idea as ljtpetersen/platinum_archipelago's own
# `AP_STRUCT_PTR_ADDRESS`).
PROTOCOL_ADDRESS = 0x023FF800
PROTOCOL_STRUCT_SIZE = 0x14
PROTOCOL_MAGIC = b"HGAP"


class ArmipsError(Exception):
    """`armips` could not be run, or reported an assembly error."""


def armips_path() -> Path:
    """Resolve the `armips` executable path: `ARMIPS_PATH` env var if set,
    else this repository's own local build (see this module's docstring)."""
    raw = os.environ.get(ARMIPS_PATH_ENV_VAR)
    return Path(raw) if raw else _DEFAULT_ARMIPS_PATH


def assemble_ground_item_hook(hook_load_address: int, *, armips_exe: Path | None = None,
                               protocol_address: int = PROTOCOL_ADDRESS) -> bytes:
    """Render `patches/ground_item_hook.s` for the given load address and
    assemble it with `armips`. Returns the raw assembled machine code
    bytes (a flat binary, no headers) -- the caller decides where in the
    ROM those bytes end up (see `apply_ground_item_hook` below)."""
    exe = armips_exe or armips_path()
    if not exe.is_file():
        raise ArmipsError(
            f"armips executable not found at {exe} -- set {ARMIPS_PATH_ENV_VAR} to "
            "a valid armips build (see docs/architecture.md, '## ROM code "
            "injection strategy')."
        )

    source = PATCH_SOURCE.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="heartgold_patch_gen_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        output_path = tmp_path / "ground_item_hook.bin"
        rendered = (
            source
            .replace("__OUTPUT_PATH__", output_path.as_posix())
            .replace("__HOOK_LOAD_ADDRESS__", f"0x{hook_load_address:08X}")
            .replace("__PROTOCOL_ADDRESS__", f"0x{protocol_address:08X}")
        )
        source_path = tmp_path / "ground_item_hook.s"
        source_path.write_text(rendered, encoding="utf-8")

        try:
            result = subprocess.run(
                [str(exe), str(source_path)],
                cwd=tmp_path,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise ArmipsError(f"could not run armips ({exe}): {exc}") from exc

        if result.returncode != 0:
            raise ArmipsError(
                f"armips failed (exit code {result.returncode}) assembling "
                f"{PATCH_SOURCE.name}:\n{result.stdout}\n{result.stderr}"
            )
        if not output_path.is_file():
            raise ArmipsError(
                f"armips exited successfully but produced no output at {output_path} "
                f"-- stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return output_path.read_bytes()


def apply_ground_item_hook(rom: HeartGoldRom, *, armips_exe: Path | None = None,
                            protocol_address: int = PROTOCOL_ADDRESS) -> int:
    """Assemble and append the ground-item hook scaffolding (see this
    module's docstring for exactly what that is and isn't) to `rom`'s ARM9
    binary in place. Returns the RAM address the appended code now lives
    at.

    Does not wire up any call site -- see docs/architecture.md and
    patches/ground_item_hook.s for why."""
    load_address = rom.arm9_ram_address + len(rom.arm9)
    code = assemble_ground_item_hook(
        load_address, armips_exe=armips_exe, protocol_address=protocol_address
    )
    actual_address = rom.append_to_arm9(code)
    assert actual_address == load_address, (
        f"ARM9 binary changed length between computing the load address "
        f"({load_address:#x}) and appending to it ({actual_address:#x}) -- "
        "this should never happen for a single-threaded, single-call use."
    )
    return actual_address


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble and apply the C14 ground-item hook scaffolding to a HeartGold (US) ROM copy."
    )
    parser.add_argument("--rom", required=True, help="Path to a vanilla Pokemon HeartGold (US) ROM.")
    parser.add_argument("--out", required=True, help="Path to write the patched ROM to.")
    parser.add_argument("--armips", default=None, help=f"Override {ARMIPS_PATH_ENV_VAR}/the default armips path.")
    args = parser.parse_args(argv)

    rom = HeartGoldRom.open(args.rom)
    hook_address = apply_ground_item_hook(
        rom, armips_exe=Path(args.armips) if args.armips else None
    )
    rom.save(args.out)
    print(
        f"Patched ROM written to {args.out} -- ground_item_hook scaffolding "
        f"appended at ARM9 address 0x{hook_address:08X} (not yet hooked to "
        "any call site; see docs/architecture.md)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
