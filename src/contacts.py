"""
SmartShell — Contact configuration loader.

Loads family and barangay rescuer contacts from config JSON.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

from src.config import (
    CONFIG_DIR,
    CONTACTS_BARANGAY_FILE,
    CONTACTS_FAMILY_FILE,
    PROJECT_ROOT,
    SMS_ALERT_TARGET_MAX_CHARS,
    SMS_SINGLE_PART_MAX_CHARS,
    SMS_SPLIT_PART_MAX_CHARS,
)


_DEFAULT_TEMPLATE = (
    "SMARTSHELL UPDATE: COLLISION DETECTED\n"
    "Name: {name}\n"
    "Area: {area}\n"
    "Home barangay: {home_barangay}\n"
    "Accident barangay: {accident_barangay}\n"
    "Notified: {notified}\n"
    "Date: {date}\n"
    "Google Map: {map_url}"
)


def load_family_contacts() -> tuple[list[str], str, str, str]:
    """
    Load family contacts, message template, rider name, and home barangay.

    Returns:
        Tuple of (phones, message_template, rider_name, subject_home_barangay).
        Placeholders: {name}, {area}, {home_barangay}, {accident_barangay}, {notified}, {date}, {map_url}.

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
    accident_barangay: str | None = None,
    notified: str = "",
    *,
    map_precision: int = 6,
    sms_plain_coords: bool = False,
) -> str:
    """
    Format message with rider name, area, barangays, notified summary, date, and map link.

    Args:
        template: Template with optional placeholders (see module default).
        accident_barangay: SMS Accident line (reverse-geocoded street/area, or coordinates).
        notified: Summary of recipient groups from routing.
        sms_plain_coords: If True, {map_url} is "lat, lon" only (Globe often blocks https URLs).
    """
    from datetime import datetime

    if lat is not None and lon is not None:
        prec = max(0, min(8, int(map_precision)))
        if sms_plain_coords:
            map_url = f"{lat:.{prec}f}, {lon:.{prec}f}"
        else:
            map_url = f"https://maps.google.com/?q={lat:.{prec}f},{lon:.{prec}f}"
    else:
        map_url = "N/A"
    if accident_barangay:
        accident_label = accident_barangay
    elif lat is not None and lon is not None:
        from src.config import SMS_ACCIDENT_COORD_PRECISION

        prec = max(0, min(8, int(SMS_ACCIDENT_COORD_PRECISION)))
        accident_label = f"{lat:.{prec}f}, {lon:.{prec}f}"
    elif area.startswith("Inside"):
        accident_label = "Unknown"
    else:
        accident_label = "N/A"
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    all_fields = {
        "name": rider_name,
        "area": area,
        "home_barangay": home_barangay,
        "accident_barangay": accident_label,
        "notified": notified or "N/A",
        "date": date_str,
        "map_url": map_url,
    }
    used = {key for key in all_fields if f"{{{key}}}" in template}
    return template.format(**{k: all_fields[k] for k in used})


# Production collision SMS (GSM 7-bit, single-part, no https URL — Globe blocks map links).
# Placeholders: {name} {area} {home_barangay} {accident_barangay} {map_url} (lat, lon only).
FINAL_SMS_ALERT_TEMPLATE = (
    "SMARTSHELL COLLISION ALERT\n"
    "\n"
    "Rider: {name}\n"
    "Area: {area}\n"
    "Home: {home_barangay} | Accident: {accident_barangay}\n"
    "\n"
    "GPS: {map_url}"
)
_FORMAL_ALERT_TEMPLATE = FINAL_SMS_ALERT_TEMPLATE

# GSM 7-bit cannot encode e.g. n-tilde in "Binan"; UCS-2 often fails on prepaid SIMs.
_SMS_CHAR_REPLACEMENTS: dict[str, str] = {
    "ñ": "n",
    "Ñ": "N",
    "á": "a",
    "é": "e",
    "í": "i",
    "ó": "o",
    "ú": "u",
    "Á": "A",
    "É": "E",
    "Í": "I",
    "Ó": "O",
    "Ú": "U",
}


def sms_safe_for_gsm7(text: str) -> str:
    """
    Keep only GSM-friendly ASCII (printable + newlines).

    Replaces common accented letters explicitly (never uses bytes encode/replace,
    which can garble on some handsets). "Biñan" -> "Binan".
    """
    normalized = unicodedata.normalize("NFKC", text)
    out: list[str] = []
    for ch in normalized:
        if ch in _SMS_CHAR_REPLACEMENTS:
            out.append(_SMS_CHAR_REPLACEMENTS[ch])
            continue
        if ch in "\r\n":
            out.append("\n")
            continue
        if ch == "\t":
            out.append(" ")
            continue
        code = ord(ch)
        if 32 <= code <= 126:
            out.append(ch)
    return "".join(out)


def format_alert_message(
    template: str,
    lat: float | None,
    lon: float | None,
    rider_name: str = "Unknown",
    home_barangay: str = "Unknown",
    area: str = "Unknown (no GPS)",
    accident_barangay: str | None = None,
    notified: str = "",
    *,
    max_chars: int | None = None,
) -> str:
    """
    Format collision SMS for reliable single-part GSM 7-bit delivery.

    All fields are ASCII-sanitized (e.g. Biñan -> Binan). Prefers the config
    template when it fits one part; otherwise the formal paragraph layout.
    """
    limit = int(SMS_ALERT_TARGET_MAX_CHARS if max_chars is None else max_chars)
    safe_name = sms_safe_for_gsm7(rider_name)
    safe_area = sms_safe_for_gsm7(area)
    safe_home = sms_safe_for_gsm7(home_barangay)
    safe_accident = sms_safe_for_gsm7(accident_barangay or "")

    def _build(tpl: str, *, map_precision: int = 4) -> str:
        return sms_safe_for_gsm7(
            format_message(
                tpl,
                lat,
                lon,
                rider_name=safe_name,
                home_barangay=safe_home,
                area=safe_area,
                accident_barangay=safe_accident or None,
                notified=sms_safe_for_gsm7(notified),
                map_precision=map_precision,
                sms_plain_coords=True,
            )
        )

    for tpl, prec in ((template, 4), (_FORMAL_ALERT_TEMPLATE, 4), (_FORMAL_ALERT_TEMPLATE, 3)):
        body = _build(tpl, map_precision=prec)
        if len(body) <= limit:
            return body

    if lat is not None and lon is not None:
        short_map = f"{lat:.4f}, {lon:.4f}"
    else:
        short_map = "N/A"
    body = (
        "SMARTSHELL COLLISION ALERT\n\n"
        f"Rider: {safe_name[:28]}\n"
        f"Area: {safe_area[:28]}\n"
        f"Home: {safe_home[:14]} | Accident: {(safe_accident or 'N/A')[:14]}\n\n"
        f"GPS: {short_map}"
    )
    if len(body) > limit:
        body = body[: limit - 3] + "..."
    return body


def split_message_for_sms(
    text: str,
    *,
    max_chars: int | None = None,
) -> list[str]:
    """
    Split text into separate single-part SMS bodies (not modem concat).

    Use when the carrier accepts +CMGS but does not deliver long/concat messages.
    """
    limit = int(SMS_SPLIT_PART_MAX_CHARS if max_chars is None else max_chars)
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = limit
        if " " in remaining[:cut]:
            cut = remaining[:cut].rfind(" ") or cut
        elif "\n" in remaining[:cut]:
            cut = remaining[:cut].rfind("\n") or cut
        chunk = remaining[:cut].strip()
        if not chunk:
            chunk = remaining[:limit]
            cut = limit
        chunks.append(chunk)
        remaining = remaining[cut:].strip()

    total = len(chunks)
    if total == 1:
        return chunks
    return [f"({i}/{total}) {part}" for i, part in enumerate(chunks, start=1)]


def message_parts_for_delivery(text: str) -> list[str]:
    """One or more SMS bodies, each intended to fit a single GSM part."""
    if len(text) <= SMS_SINGLE_PART_MAX_CHARS:
        return [text]
    return split_message_for_sms(text)


def google_map_url(
    lat: float,
    lon: float,
    *,
    style: str = "legacy",
    map_precision: int = 6,
) -> str:
    """
    Build a Google Maps HTTPS URL for bench tests.

    Styles:
        legacy — https://maps.google.com/?q=lat,lon (short; blocked on Globe P2P SMS)
        google_search — official Maps URL API search form
        google_com — https://www.google.com/maps?q=lat,lon
    """
    prec = max(0, min(8, int(map_precision)))
    lat_s = f"{lat:.{prec}f}"
    lon_s = f"{lon:.{prec}f}"
    key = style.strip().lower()
    if key == "google_search":
        return (
            f"https://www.google.com/maps/search/?api=1&query={lat_s}%2C{lon_s}"
        )
    if key in ("google_com", "www"):
        return f"https://www.google.com/maps?q={lat_s},{lon_s}"
    return f"https://maps.google.com/?q={lat_s},{lon_s}"


def format_google_map_test_sms(
    lat: float,
    lon: float,
    *,
    style: str = "legacy",
    label: str = "Google Map",
    custom_url: str | None = None,
) -> str:
    """
    Bench-only body: ``Google Map: <url>`` (original label style).

    Production alerts use plain ``GPS: lat, lon`` because Globe often drops P2P SMS
    that contain https links (modem may still return +CMGS OK).
    """
    if custom_url is not None:
        url = custom_url.strip()
    else:
        url = google_map_url(lat, lon, style=style)
    return sms_safe_for_gsm7(f"{label}: {url}")
