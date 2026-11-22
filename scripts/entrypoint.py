"""Punto de entrada para empaquetado portable (PyInstaller)."""
from __future__ import annotations

import sys

from resonexuz.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
