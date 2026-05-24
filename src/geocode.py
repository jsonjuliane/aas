"""
Reverse geocoding for collision SMS (OpenStreetMap Nominatim).

Used for the ``Accident:`` SMS field when REVERSE_GEOCODE_ENABLED is True.
Requires internet on the Pi at alert time.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from src.config import SMS_ACCIDENT_ADDRESS_MAX_CHARS
from src.contacts import sms_safe_for_gsm7

_NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "SmartShellAccidentAlert/1.0 (thesis prototype; collision SMS only)"


def _short_label_from_address(address: dict[str, object]) -> str:
    """Build a compact street/area label from Nominatim address parts."""
    parts: list[str] = []
    for key in (
        "road",
        "pedestrian",
        "footway",
        "residential",
        "neighbourhood",
        "suburb",
        "village",
        "city_district",
        "city",
        "municipality",
        "town",
    ):
        val = address.get(key)
        if not val:
            continue
        text = str(val).strip()
        if text and text not in parts:
            parts.append(text)
        if len(parts) >= 2:
            break
    return ", ".join(parts)


def reverse_geocode_short_address(
    lat: float,
    lon: float,
    *,
    timeout_sec: float = 5.0,
    max_len: int | None = None,
) -> str | None:
    """
    Return a short GSM-safe street/area label for (lat, lon), or None on failure.

    Uses OSM Nominatim (free; respect 1 req/s and identify via User-Agent).
    """
    limit = max(16, int(max_len if max_len is not None else SMS_ACCIDENT_ADDRESS_MAX_CHARS))
    params = urllib.parse.urlencode(
        {
            "lat": f"{float(lat):.6f}",
            "lon": f"{float(lon):.6f}",
            "format": "jsonv2",
            "addressdetails": "1",
            "zoom": "18",
        }
    )
    url = f"{_NOMINATIM_REVERSE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=max(1.0, float(timeout_sec))) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    address = data.get("address")
    label = ""
    if isinstance(address, dict):
        label = _short_label_from_address(address)
    if not label:
        display = data.get("display_name")
        if isinstance(display, str):
            label = display.split(",")[0].strip()
            if "," in display:
                label = ", ".join(p.strip() for p in display.split(",")[:2])

    label = sms_safe_for_gsm7(label.strip())
    if not label:
        return None
    if len(label) > limit:
        label = label[: max(0, limit - 3)].rstrip() + "..."
    return label
