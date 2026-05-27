"""
Reverse geocoding for collision SMS (OpenStreetMap Nominatim).

Used for the ``Accident:`` SMS field when REVERSE_GEOCODE_ENABLED is True.
Requires internet on the Pi at alert time.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import time

from src.config import (
    REVERSE_GEOCODE_RETRY_COUNT,
    REVERSE_GEOCODE_RETRY_DELAY_SEC,
    REVERSE_GEOCODE_TIMEOUT_SEC,
    SMS_ACCIDENT_ADDRESS_MAX_CHARS,
)
from src.contacts import sms_safe_for_gsm7

_NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "SmartShellAccidentAlert/1.0 (thesis prototype; collision SMS only)"


def geocode_debug_enabled() -> bool:
    """True when SMARTSHELL_DEBUG_GEOCODE=1 (or true/yes)."""
    return os.environ.get("SMARTSHELL_DEBUG_GEOCODE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _geocode_debug(msg: str) -> None:
    if geocode_debug_enabled():
        print(f"[geocode] {msg}")


def _short_label_from_address(address: dict[str, object]) -> str:
    """Build a compact but detailed street-level label from Nominatim parts."""

    def _pick(*keys: str) -> str:
        for key in keys:
            val = address.get(key)
            if val:
                text = str(val).strip()
                if text:
                    return text
        return ""

    house_num = _pick("house_number")
    building = _pick("building", "amenity")
    road = _pick("road", "pedestrian", "footway", "residential")
    local = _pick("neighbourhood", "suburb", "village", "city_district")
    city = _pick("city", "municipality", "town")

    parts: list[str] = []
    street = ""
    if house_num and road:
        street = f"{house_num} {road}"
    elif road:
        street = road
    elif house_num and building:
        street = f"{house_num} {building}"
    elif building:
        street = building
    if street:
        parts.append(street)
    if local and local not in parts:
        parts.append(local)
    elif city and city not in parts:
        parts.append(city)

    if len(parts) < 2 and building and building not in parts:
        parts.append(building)
    if len(parts) < 2 and city and city not in parts:
        parts.append(city)

    return ", ".join(parts[:2])


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
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        _geocode_debug(f"Nominatim request failed: {type(e).__name__}: {e}")
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


def reverse_geocode_short_address_with_retries(
    lat: float,
    lon: float,
    *,
    timeout_sec: float | None = None,
    max_len: int | None = None,
    retry_count: int | None = None,
    retry_delay_sec: float | None = None,
) -> str | None:
    """
    Call :func:`reverse_geocode_short_address` with bounded retries on failure.

    Respects Nominatim etiquette (low volume; identify via User-Agent).
    """
    attempts = max(1, int(retry_count if retry_count is not None else REVERSE_GEOCODE_RETRY_COUNT))
    delay = max(0.0, float(retry_delay_sec if retry_delay_sec is not None else REVERSE_GEOCODE_RETRY_DELAY_SEC))
    per_try_timeout = float(timeout_sec if timeout_sec is not None else REVERSE_GEOCODE_TIMEOUT_SEC)
    last: str | None = None
    _geocode_debug(
        f"reverse geocode lat={float(lat):.6f} lon={float(lon):.6f} "
        f"attempts={attempts} timeout={per_try_timeout}s"
    )
    for idx in range(attempts):
        _geocode_debug(f"attempt {idx + 1}/{attempts}")
        last = reverse_geocode_short_address(
            float(lat),
            float(lon),
            timeout_sec=per_try_timeout,
            max_len=max_len,
        )
        if last:
            _geocode_debug(f"ok label={last!r}")
            return last
        if idx < attempts - 1 and delay > 0:
            time.sleep(delay)
    _geocode_debug("no label (exhausted retries or empty Nominatim response)")
    return last
