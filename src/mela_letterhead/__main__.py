"""Entry point for ``python -m mela_letterhead``.

Useful from a clone with no install: activate the virtual environment and run
``python -m mela_letterhead build`` from the repository root.
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
