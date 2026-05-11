from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH_ENTRIES = [
    ROOT / "services" / "control-plane",
    ROOT / "packages" / "platform_sdk",
    ROOT / "packages" / "platform_cli",
]

for entry in PYTHONPATH_ENTRIES:
    entry_str = str(entry)
    if entry_str not in sys.path:
        sys.path.insert(0, entry_str)
