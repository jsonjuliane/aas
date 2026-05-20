"""
SmartShell — Contact configuration loader.

Loads family and barangay contacts from config JSON.
Phase 1: family only. Phase 2: add barangay routing.
"""

from __future__ import annotations

import json
from src.config import CONFIG_DIR, CONTACTS_FAMILY_FILE, PROJECT_ROOT


_DEFAULT_TEMPLATE = (
    "SMARTSHELL UPDATE: COLLISION DETECTED\n"
    "Name: {name}\n"
    "Date: {date}\n"
    "Google Map: {map_url}"
)


def load_family_contacts() -> tuple[list[str], str, str]:
    """
    Load family contacts, message template, and rider name.

    Returns:
        Tuple of (list of phone numbers in priority order, message_template, rider_name).
        Placeholders in template: {name}, {date}, {map_url}.

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
    template = data.get("message_template", _DEFAULT_TEMPLATE)
    rider_name = data.get("rider_name", "Unknown")
    return phones, template, rider_name


def format_message(
    template: str,
    lat: float | None,
    lon: float | None,
    rider_name: str = "Unknown",
) -> str:
    """
    Format message with rider name, date, and Google Maps link.

    Args:
        template: Template with {name}, {date}, {map_url}.
        lat: Latitude or None.
        lon: Longitude or None.
        rider_name: Name of the rider/device owner.

    Returns:
        Formatted message string.
    """
    from datetime import datetime

    if lat is not None and lon is not None:
        map_url = f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"
    else:
        map_url = "N/A"
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    return template.format(name=rider_name, date=date_str, map_url=map_url)
