"""
SmartShell — Location routing (Phase 2).

Geofence check for inside vs outside Biñan, Laguna.
See docs/features/07_routing.md.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from src import contacts
import math

from src.config import (
    BARANGAY_CENTROIDS_BINAN_FILE,
    CONFIG_DIR,
    GEOFENCE_BINAN_FILE,
    PROJECT_ROOT,
)

LocationClass = Literal["inside_binan", "outside_binan", "unknown"]

_AREA_LABELS: dict[LocationClass, str] = {
    "inside_binan": "Inside Biñan",
    "outside_binan": "Outside Biñan",
    "unknown": "Unknown (no GPS)",
}


@lru_cache(maxsize=1)
def _load_boundary_ring() -> list[tuple[float, float]]:
    """Load geofence polygon as list of (lon, lat) from config."""
    path = PROJECT_ROOT / CONFIG_DIR / GEOFENCE_BINAN_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Geofence file not found: {path}. "
            f"Add {GEOFENCE_BINAN_FILE} under {CONFIG_DIR}/."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    boundary = data.get("boundary")
    if not boundary or len(boundary) < 4:
        raise ValueError(f"Invalid boundary in {path}: need at least 4 points")
    ring: list[tuple[float, float]] = []
    for pt in boundary:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            raise ValueError(f"Invalid boundary point in {path}: {pt!r}")
        ring.append((float(pt[0]), float(pt[1])))
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


@lru_cache(maxsize=1)
def _binan_polygon():
    from shapely.geometry import Point, Polygon

    return Polygon(_load_boundary_ring())


def is_inside_binan(lat: float, lon: float) -> bool:
    """
    Return True if (lat, lon) is inside the Biñan city boundary polygon.

    Args:
        lat: WGS84 latitude.
        lon: WGS84 longitude.
    """
    from shapely.geometry import Point

    point = Point(lon, lat)  # shapely x=lon, y=lat
    return bool(_binan_polygon().contains(point))


def classify_location(lat: float | None, lon: float | None) -> LocationClass:
    """
    Classify accident location for routing.

    Returns:
        inside_binan, outside_binan, or unknown when coordinates are missing.
    """
    if lat is None or lon is None:
        return "unknown"
    if is_inside_binan(lat, lon):
        return "inside_binan"
    return "outside_binan"


def area_label(location_class: LocationClass) -> str:
    """Human-readable area string for SMS and logs."""
    return _AREA_LABELS[location_class]


@lru_cache(maxsize=1)
def _load_barangay_centroids() -> list[tuple[str, float, float]]:
    """Load (canonical name, lat, lon) reference points for accident barangay lookup."""
    path = PROJECT_ROOT / CONFIG_DIR / BARANGAY_CENTROIDS_BINAN_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Barangay centroids not found: {path}. "
            f"Copy {BARANGAY_CENTROIDS_BINAN_FILE}.example to {BARANGAY_CENTROIDS_BINAN_FILE}."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("barangays", [])
    if not entries:
        raise ValueError(f"No barangays in {path}")
    out: list[tuple[str, float, float]] = []
    for entry in entries:
        name = entry.get("name")
        lat = entry.get("lat")
        lon = entry.get("lon")
        if not name or lat is None or lon is None:
            raise ValueError(f"Invalid centroid entry: {entry!r}")
        out.append((str(name), float(lat), float(lon)))
    return out


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def resolve_accident_barangay(lat: float, lon: float) -> str | None:
    """
    Resolve accident barangay name from GPS when inside Biñan.

    Uses nearest reference centroid from barangay_centroids.binan.json.
    Returns None when coordinates are outside Biñan.
    """
    if not is_inside_binan(lat, lon):
        return None
    centroids = _load_barangay_centroids()
    best_name: str | None = None
    best_dist = float("inf")
    for name, clat, clon in centroids:
        dist = _haversine_m(lat, lon, clat, clon)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def _build_notified_summary(
    *,
    family_count: int,
    home_barangay: str,
    home_rescuer_matched: bool,
    accident_barangay: str | None,
    accident_rescuer_matched: bool,
    location_class: LocationClass,
) -> str:
    """Human-readable summary of who was targeted for SMS."""
    parts = [f"family ({family_count})"]
    if home_rescuer_matched:
        parts.append(f"home: {home_barangay}")
    if location_class == "inside_binan" and accident_barangay and accident_rescuer_matched:
        parts.append(f"accident: {accident_barangay}")
    elif location_class == "inside_binan" and accident_barangay:
        parts.append(f"accident: {accident_barangay} (no rescuer phone)")
    return ", ".join(parts)


def _dedupe_phones_preserve_order(phones: list[str]) -> list[str]:
    """Remove duplicate numbers while keeping first occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    for phone in phones:
        if phone in seen:
            continue
        seen.add(phone)
        out.append(phone)
    return out


def get_recipients(
    lat: float | None,
    lon: float | None,
    *,
    family_phones: list[str],
    home_barangay: str,
) -> dict[str, object]:
    """
    Build alert recipient list (E.164 phones, family first).

    Rules:
      - Always: family contacts (priority order)
      - Always when matched: home barangay rescuer
      - Inside Biñan + GPS: add accident barangay rescuer (nearest centroid)
      - Outside Biñan / no GPS: family + home only

    Returns:
        Dict with phones, routing metadata for logs and SMS placeholders.
    """
    location_class = classify_location(lat, lon)
    barangay_map, default_phone = contacts.load_barangay_contacts()
    home_rescuer = contacts.lookup_rescuer_phone(
        home_barangay,
        barangay_map,
        use_default=False,
        default_phone=default_phone,
    )

    accident_barangay: str | None = None
    accident_rescuer: str | None = None
    accident_rescuer_matched = False
    if location_class == "inside_binan" and lat is not None and lon is not None:
        accident_barangay = resolve_accident_barangay(lat, lon)
        if accident_barangay:
            accident_rescuer = contacts.lookup_rescuer_phone(
                accident_barangay,
                barangay_map,
                use_default=True,
                default_phone=default_phone,
            )
            accident_rescuer_matched = accident_rescuer is not None

    phones: list[str] = list(family_phones)
    if home_rescuer:
        phones.append(home_rescuer)
    if accident_rescuer:
        phones.append(accident_rescuer)
    phones = _dedupe_phones_preserve_order(phones)

    notified = _build_notified_summary(
        family_count=len(family_phones),
        home_barangay=home_barangay,
        home_rescuer_matched=home_rescuer is not None,
        accident_barangay=accident_barangay,
        accident_rescuer_matched=accident_rescuer_matched,
        location_class=location_class,
    )

    return {
        "location_class": location_class,
        "area_label": area_label(location_class),
        "inside_binan": None
        if location_class == "unknown"
        else location_class == "inside_binan",
        "lat": lat,
        "lon": lon,
        "phones": phones,
        "family_count": len(family_phones),
        "home_barangay": home_barangay,
        "home_rescuer_phone": home_rescuer,
        "home_rescuer_matched": home_rescuer is not None,
        "accident_barangay": accident_barangay,
        "accident_rescuer_phone": accident_rescuer,
        "accident_rescuer_matched": accident_rescuer_matched,
        "notified": notified,
    }


def routing_decision(lat: float | None, lon: float | None) -> dict[str, object]:
    """
    Build geofence-only routing payload (location class and area label).

    For full recipient list use get_recipients().
    """
    location_class = classify_location(lat, lon)
    inside: bool | None
    if location_class == "unknown":
        inside = None
    else:
        inside = location_class == "inside_binan"
    return {
        "location_class": location_class,
        "area_label": area_label(location_class),
        "inside_binan": inside,
        "lat": lat,
        "lon": lon,
    }
