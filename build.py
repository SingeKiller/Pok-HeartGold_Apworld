#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APIGNORE_PATH = ROOT / ".apignore"
MANIFEST_PATH = ROOT / "archipelago.json"


MODULE_NAME = "poke_hgss"


def module_name() -> str:
    return MODULE_NAME


def whitelisted_paths() -> list[Path]:
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


_COMPATIBLE_VERSION = 7


def build() -> Path:
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
                continue
            arcname = f"{name}/{path.relative_to(ROOT).as_posix()}"
            zf.write(path, arcname)
            included += 1
        zf.writestr(f"{name}/archipelago.json", json.dumps(manifest, indent=2))
        included += 1

    print(f"built {out_path.name} ({included} file(s))")
    return out_path


if __name__ == "__main__":
    build()
