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
    "Area: {area}\n"
    "Home barangay: {home_barangay}\n"
    "Date: {date}\n"
    "Google Map: {map_url}"
)


def load_family_contacts() -> tuple[list[str], str, str, str]:
    """
    Load family contacts, message template, rider name, and home barangay.

    Returns:
        Tuple of (phones, message_template, rider_name, subject_home_barangay).
        Placeholders in template: {name}, {area}, {home_barangay}, {date}, {map_url}.

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
    home_barangay = data.get("subject_home_barangay", "Unknown")
    return phones, template, rider_name, home_barangay


def format_message(
    template: str,
    lat: float | None,
    lon: float | None,
    rider_name: str = "Unknown",
    home_barangay: str = "Unknown",
    area: str = "Unknown (no GPS)",
) -> str:
    """
    Format message with rider name, area, home barangay, date, and Google Maps link.

    Args:
        template: Template with {name}, {area}, {home_barangay}, {date}, {map_url}.
        lat: Latitude or None.
        lon: Longitude or None.
        rider_name: Name of the rider/device owner.
        home_barangay: Rider's residence barangay (subject_home_barangay from config).
        area: Inside/outside Biñan label from routing.

    Returns:
        Formatted message string.
    """
    from datetime import datetime

    if lat is not None and lon is not None:
        map_url = f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"
    else:
        map_url = "N/A"
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    all_fields = {
        "name": rider_name,
        "area": area,
        "home_barangay": home_barangay,
        "date": date_str,
        "map_url": map_url,
    }
    used = {key for key in all_fields if f"{{{key}}}" in template}
    return template.format(**{k: all_fields[k] for k in used})
