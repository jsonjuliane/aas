"""
SmartShell — Event logging for accident alerts.

Persists event data (timestamp, acceleration, location, routing).
See docs/features/08_logging.md.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from src.config import LOGS_DIR


def _project_root() -> Path:
    """Project root (parent of src/)."""
    return Path(__file__).resolve().parent.parent


def _ensure_log_dir() -> Path:
    """Ensure logs directory exists; return path."""
    root = _project_root()
    log_dir = root / LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _log_filename() -> Path:
    """Current log file path (one file per day)."""
    log_dir = _ensure_log_dir()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return log_dir / f"events_{today}.jsonl"


def log_event(data: dict) -> None:
    """
    Append event to log file (JSON Lines format).

    Args:
        data: Event dict (e.g. timestamp, accel, lat, lon, cancelled, recipients).
    """
    path = _log_filename()
    line = json.dumps(data, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def get_log_path() -> str:
    """Return path to current log file for debugging."""
    return str(_log_filename())
