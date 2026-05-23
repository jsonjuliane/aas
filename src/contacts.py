"""
SmartShell — Contact configuration loader.

Loads family and barangay contacts from config JSON.
Loads family and barangay rescuer contacts from config JSON.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from src.config import (
    CONFIG_DIR,
    CONTACTS_BARANGAY_FILE,
    CONTACTS_FAMILY_FILE,
    PROJECT_ROOT,
)


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
        normalize_phone(str(c["phone"]))
        for c in sorted(contacts, key=lambda x: x.get("priority", 999))
    ]
    template = data.get("message_template", _DEFAULT_TEMPLATE)
    rider_name = data.get("rider_name", "Unknown")
    home_barangay = data.get("subject_home_barangay", "Unknown")
    return phones, template, rider_name, home_barangay


def normalize_phone(phone: str) -> str:
    """Normalize Philippine mobile numbers to E.164 (+63...)."""
    s = phone.strip().replace(" ", "").replace("-", "")
    if s.startswith("+63"):
        return s
    if s.startswith("63") and len(s) >= 12:
        return "+" + s
    if s.startswith("09") and len(s) == 11:
        return "+63" + s[1:]
    if s.startswith("9") and len(s) == 10:
        return "+63" + s
    return s


def normalize_barangay_key(name: str) -> str:
    """Normalize barangay name for lookup (case-insensitive, optional prefixes)."""
    s = name.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace(".", "")
    for prefix in ("barangay ", "brgy ", "brgy. "):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    if s.startswith("sto "):
        s = "santo " + s[4:]
    return s.strip()


@lru_cache(maxsize=1)
def load_barangay_contacts() -> tuple[dict[str, str], str | None]:
    """
    Load barangay name → rescuer phone map and optional default rescuer.

    Returns:
        Tuple of (normalized_name -> E.164 phone, default_rescuer_phone or None).

    Raises:
        FileNotFoundError: If barangay contacts file not found.
        ValueError: If config invalid.
    """
    path = PROJECT_ROOT / CONFIG_DIR / CONTACTS_BARANGAY_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Barangay contacts not found: {path}. "
            f"Copy {CONTACTS_BARANGAY_FILE}.example to {CONTACTS_BARANGAY_FILE}."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    barangays = data.get("barangays", [])
    if not barangays:
        raise ValueError("No barangays in config")
    by_name: dict[str, str] = {}
    for entry in barangays:
        name = entry.get("name")
        phone = entry.get("rescuer_phone")
        if not name or not phone:
            raise ValueError(f"Invalid barangay entry: {entry!r}")
        key = normalize_barangay_key(str(name))
        by_name[key] = normalize_phone(str(phone))
    default_raw = data.get("default_rescuer_phone")
    default_phone = normalize_phone(str(default_raw)) if default_raw else None
    return by_name, default_phone


def lookup_rescuer_phone(
    barangay_name: str,
    barangay_map: dict[str, str],
    *,
    use_default: bool = False,
    default_phone: str | None = None,
) -> str | None:
    """Resolve rescuer phone for a barangay name."""
    key = normalize_barangay_key(barangay_name)
    phone = barangay_map.get(key)
    if phone:
        return phone
    if use_default and default_phone:
        return default_phone
    return None


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
