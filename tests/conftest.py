"""Shared pytest fixtures + sys.path wiring.

Tests are run from the repo root; the FastAPI app lives at ./app and is imported as if that
were the process working directory (matches the Dockerfile's `uvicorn main:app`).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
