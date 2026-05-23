"""
SmartShell — Location routing (Phase 2).

Geofence check for inside vs outside Biñan, Laguna.
See docs/features/07_routing.md.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from src.config import CONFIG_DIR, GEOFENCE_BINAN_FILE, PROJECT_ROOT

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


def routing_decision(lat: float | None, lon: float | None) -> dict[str, object]:
    """
    Build routing decision payload for logging and SMS.

    Keys: location_class, area_label, inside_binan (bool | None), lat, lon.
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
