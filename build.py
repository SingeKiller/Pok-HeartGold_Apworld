#!/usr/bin/env python3
"""build.py

Pure-Python fallback to build the Pokemon HGSS `.apworld` on platforms
without `make` (e.g. plain Windows). Produces a `<module>.apworld` zip at
the repository root, packaged from the paths whitelisted in `.apignore`,
plus `archipelago.json` as the manifest.

For a real release, prefer Archipelago's own "Build APWorlds" launcher
component instead (drop this repo into a local Archipelago checkout's
`worlds/` folder first) -- it stamps manifest fields (`compatible_version`)
this script just copies through verbatim from `archipelago.json`. This
script exists for CI (no full Archipelago checkout available there) and
quick local builds without installing one.

Usage:
    python build.py
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APIGNORE_PATH = ROOT / ".apignore"
MANIFEST_PATH = ROOT / "archipelago.json"


def module_name() -> str:
    """Derive the apworld module/folder name from archipelago.json's "game"."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return manifest["game"].lower().replace(" ", "_").replace("&", "and")


def whitelisted_paths() -> list[Path]:
    """Parse `.apignore` and return the repo-relative paths to include.
    Directories (trailing "/") are expanded recursively. Raises
    RuntimeError if a whitelisted directory doesn't exist at all (e.g.
    data/ deleted by a stale test run -- see NOTES.md)."""
    paths: list[Path] = []
    for raw_line in APIGNORE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith("!/"):
            continue
        rel = line[2:]
        if rel.endswith("/"):
            directory = ROOT / rel
            if not directory.is_dir():
                raise RuntimeError(
                    f"whitelisted directory {rel!r} does not exist at {directory} -- "
                    "the built .apworld would silently be missing it entirely. "
                    "If this is data/, run `python data_gen.py` first."
                )
            paths.extend(
                sorted(
                    p
                    for p in directory.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
                )
            )
        else:
            paths.append(ROOT / rel)
    return paths


# Stamped at build time, not hand-authored in source -- see NOTES.md for
# why archipelago.json itself omits it.
_COMPATIBLE_VERSION = 7


def build() -> Path:
    """Build the .apworld and return its path."""
    name = module_name()
    out_path = ROOT / f"{name}.apworld"
    included = 0

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["compatible_version"] = _COMPATIBLE_VERSION

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in whitelisted_paths():
            if not path.is_file():
                print(f"warning: skipping missing whitelisted path: {path.relative_to(ROOT)}", file=sys.stderr)
                continue
            if path == MANIFEST_PATH:
                continue  # written below, with compatible_version stamped in
            arcname = f"{name}/{path.relative_to(ROOT).as_posix()}"
            zf.write(path, arcname)
            included += 1
        zf.writestr(f"{name}/archipelago.json", json.dumps(manifest, indent=2))
        included += 1

    print(f"built {out_path.name} ({included} file(s))")
    return out_path


if __name__ == "__main__":
    build()
