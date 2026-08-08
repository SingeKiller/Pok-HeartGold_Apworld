"""Shared pytest setup for the HeartGold APWorld test suite.

Adds the repository root to `sys.path` so root-level modules
(`items.py`/`locations.py`/`regions.py`/`rules.py`, `data_gen_rules.py`,
...) import as top-level modules -- matching the flat package layout
Archipelago itself requires (see docs/architecture.md) -- and adds a local
Archipelago checkout to `sys.path` so this project's world-structure
modules can `import BaseClasses` exactly as they would once actually
loaded by Archipelago.

The Archipelago checkout path is read from the `ARCHIPELAGO_PATH`
environment variable, falling back to the path documented in CLAUDE.md for
this project's own dev machine. If `BaseClasses` (or one of its own
transitive runtime dependencies -- PyYAML, colorama, etc.; these are
Archipelago's own dependencies, not this project's, see requirements.txt's
docstring) still isn't importable, tests needing it skip cleanly via
`pytest.importorskip("BaseClasses")`, the same "skip rather than fail when
a local-only resource is missing" convention already used by
tests/test_rom_roundtrip.py for HEARTGOLD_ROM_PATH.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_ARCHIPELAGO_PATH_ENV_VAR = "ARCHIPELAGO_PATH"
_DEFAULT_ARCHIPELAGO_PATH = r"E:\Users\Olivier\Desktop\projet\archipelago"

_archipelago_path = os.environ.get(_ARCHIPELAGO_PATH_ENV_VAR, _DEFAULT_ARCHIPELAGO_PATH)
if _archipelago_path and Path(_archipelago_path).is_dir() and _archipelago_path not in sys.path:
    sys.path.insert(0, _archipelago_path)
