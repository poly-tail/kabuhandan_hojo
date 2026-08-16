"""Application package for kabuhandan_hojo."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["__version__"]

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if _SRC_DIR.exists():
    src_path = str(_SRC_DIR)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

__version__ = "0.1.0"
