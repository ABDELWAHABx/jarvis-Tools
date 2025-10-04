#!/usr/bin/env python3
"""Run the Tools API and an in-process worker."""
from __future__ import annotations

from app.runtime.cli import main
from app.runtime.preflight import prepare_environment


if __name__ == "__main__":
    prepare_environment()
    main()
