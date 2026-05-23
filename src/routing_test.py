"""
Bench test for Biñan geofence — run: python -m src.routing_test
"""

from __future__ import annotations

from src.routing import area_label, classify_location, is_inside_binan


def _check(name: str, lat: float, lon: float, expect_inside: bool) -> None:
    inside = is_inside_binan(lat, lon)
    cls = classify_location(lat, lon)
    label = area_label(cls)
    ok = inside == expect_inside
    tag = "OK" if ok else "FAIL"
    print(f"[{tag}] {name}: ({lat}, {lon}) -> {label} (inside={inside})")
    if not ok:
        raise SystemExit(1)


def main() -> int:
    # Biñan city center (OSM / public listings)
    _check("Biñan center", 14.34267, 121.08071, True)
    # Langkiwa barangay (user barangay list)
    _check("Langkiwa", 14.2965, 121.0649, True)
    # Manila City Hall area — outside Laguna geofence
    _check("Manila", 14.5905, 120.9800, False)
    # No coordinates
    cls = classify_location(None, None)
    print(f"[OK] No GPS: {area_label(cls)} (class={cls})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
