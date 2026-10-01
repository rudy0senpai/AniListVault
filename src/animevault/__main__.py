"""Allow running the package directly: ``python -m animevault``."""

from __future__ import annotations

import sys

from animevault.cli import main

if __name__ == "__main__":
    sys.exit(main())
