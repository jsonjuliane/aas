"""
SmartShell — Contact configuration loader.

Loads family and barangay contacts from config JSON.
Phase 1: family only. Phase 2: add barangay routing.
"""

from __future__ import annotations

import json
from src.config import CONFIG_DIR, CONTACTS_FAMILY_FILE, PROJECT_ROOT


def load_family_contacts() -> tuple[list[str], str]:
    """
    Load family contacts and message template.

    Returns:
        Tuple of (list of phone numbers in priority order, message_template).
        Placeholders in template: {lat}, {lon}, {timestamp}.

    Raises:
        FileNotFoundError: If contacts file not found.
        ValueError: If config invalid.
    """
    path = PROJECT_ROOT / CONFIG_DIR / CONTACTS_FAMILY_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Contacts file not found: {path}. "
            f"Copy {CONTACTS_FAMILY_FILE}.example to {CONTACTS_FAMILY_FILE} and edit."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    contacts = data.get("contacts", [])
    if not contacts:
        raise ValueError("No contacts in config")
    phones = [
        c["phone"]
        for c in sorted(contacts, key=lambda x: x.get("priority", 999))
    ]
    template = data.get(
        "message_template",
        "ALERT: Possible accident. Location: {lat}, {lon} at {timestamp}.",
    )
    return phones, template


def format_message(template: str, lat: float | None, lon: float | None) -> str:
    """
    Format message with lat, lon, timestamp.

    Args:
        template: Template with {lat}, {lon}, {timestamp}.
        lat: Latitude or None.
        lon: Longitude or None.

    Returns:
        Formatted message string.
    """
    from datetime import datetime

    lat_str = f"{lat:.6f}" if lat is not None else "N/A"
    lon_str = f"{lon:.6f}" if lon is not None else "N/A"
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    return template.format(lat=lat_str, lon=lon_str, timestamp=ts)
