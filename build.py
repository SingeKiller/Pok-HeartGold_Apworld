#!/usr/bin/env python3
"""build.py

Pure-Python fallback to build the Pokemon HeartGold `.apworld` on platforms
without `make`/`curl` (e.g. plain Windows). Produces the same result as
`make`: a `<module>.apworld` zip at the repository root, packaged from the
paths whitelisted in `.apignore`, plus `archipelago.json` as the manifest.

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

    See `.apignore` for the format. Directories (trailing "/") are expanded
    recursively to the files they currently contain.
    """
    paths: list[Path] = []
    for raw_line in APIGNORE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith("!/"):
            continue
        rel = line[2:]
        if rel.endswith("/"):
            directory = ROOT / rel
            if directory.is_dir():
                paths.extend(sorted(p for p in directory.rglob("*") if p.is_file()))
        else:
            paths.append(ROOT / rel)
    return paths


def build() -> Path:
    """Build the .apworld and return its path."""
    name = module_name()
    out_path = ROOT / f"{name}.apworld"
    included = 0

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in whitelisted_paths():
            if not path.is_file():
                print(f"warning: skipping missing whitelisted path: {path.relative_to(ROOT)}", file=sys.stderr)
                continue
            arcname = f"{name}/{path.relative_to(ROOT).as_posix()}"
            zf.write(path, arcname)
            included += 1
        zf.writestr(f"{name}/archipelago.json", MANIFEST_PATH.read_text(encoding="utf-8"))

    print(f"built {out_path.name} ({included} file(s))")
    return out_path


if __name__ == "__main__":
    build()
