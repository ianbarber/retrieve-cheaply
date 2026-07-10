"""Portable discovery for external tools used by the experiment harnesses."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def find_pyrefly() -> str:
    """Resolve Pyrefly from configuration, PATH, or a repository-local venv."""
    configured = os.environ.get("STREAMS_PYREFLY") or os.environ.get("PYREFLY_BIN")
    candidates = [configured, shutil.which("pyrefly")]
    if os.name == "nt":
        candidates.append(ROOT / ".venv" / "Scripts" / "pyrefly.exe")
    else:
        candidates.extend([
            ROOT / ".venv" / "bin" / "pyrefly",
            ROOT / ".venv-streams" / "bin" / "pyrefly",
            Path(sys.prefix) / "bin" / "pyrefly",
        ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise FileNotFoundError(
        "pyrefly was not found; install the dev dependencies or set STREAMS_PYREFLY"
    )


def pyrefly_or_name() -> str:
    """Return a useful executable name without failing at import time."""
    try:
        return find_pyrefly()
    except FileNotFoundError:
        return "pyrefly"
