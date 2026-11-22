"""Punto de entrada de ResoNexuz (`python -m resonexuz`)."""
from __future__ import annotations

import sys

from .main import run_cli


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    sys.exit(main())
