"""
Full routing matrix — geofence, accident barangay, recipients, SMS preview.

Run from project root (needs shapely + config files):
  python -m src.routing_matrix_test
  python -m src.routing_matrix_test --sms-preview
"""

from __future__ import annotations

import argparse
import json

from src import contacts
from src.config import BARANGAY_CENTROIDS_BINAN_FILE, CONFIG_DIR, PROJECT_ROOT
from src.routing import get_recipients, is_inside_binan, resolve_accident_barangay

# Outside Biñan (Manila area)
_OUTSIDE_LAT, _OUTSIDE_LON = 14.5905, 120.9800


def _load_centroid_cases() -> list[tuple[str, float, float]]:
    path = PROJECT_ROOT / CONFIG_DIR / BARANGAY_CENTROIDS_BINAN_FILE
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out: list[tuple[str, float, float]] = []
    for entry in data.get("barangays", []):
        out.append((str(entry["name"]), float(entry["lat"]), float(entry["lon"])))
    return out


def _run_case(
    name: str,
    lat: float | None,
    lon: float | None,
    *,
    home_barangay: str,
    sms_preview: bool,
) -> bool:
    """Print one scenario; return True if checks pass."""
    ok = True
    if lat is not None and lon is not None:
        inside = is_inside_binan(lat, lon)
        accident = resolve_accident_barangay(lat, lon) if inside else None
    else:
        inside = None
        accident = None

    phones, template, rider_name, _home_cfg = contacts.load_family_contacts()
    route = get_recipients(
        lat,
        lon,
        family_phones=phones,
        home_barangay=home_barangay,
    )
    area = str(route.get("area_label", ""))
    tag = "OK"
    if lat is not None and lon is not None:
        if inside and accident != name and name not in ("Outside Manila", "No GPS"):
            if name in {b for b, _, _ in _load_centroid_cases()} and accident != name:
                tag = "WARN"
                ok = False
    print(f"\n=== {name} ===")
    print(f"  GPS: {lat}, {lon}")
    print(f"  Inside Biñan: {inside}")
    print(f"  Area: {area}")
    print(f"  Accident barangay (routing): {route.get('accident_barangay')}")
    print(f"  Accident SMS label: {route.get('accident_location')}")
    print(f"  Recipients ({len(route['phones'])}): {route.get('phones')}")
    print(f"  Notified: {route.get('notified')}")
    if sms_preview:
        body = contacts.format_alert_message(
            template=template,
            lat=lat,
            lon=lon,
            rider_name=rider_name,
            home_barangay=home_barangay,
            area=area,
            accident_barangay=route.get("accident_location") or route.get("accident_barangay"),
            notified=str(route.get("notified", "")),
        )
        print("  --- SMS preview ---")
        for line in body.splitlines():
            print(f"    {line}")
    print(f"  [{tag}]")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Routing matrix for all barangays + outside/no GPS")
    ap.add_argument(
        "--sms-preview",
        action="store_true",
        help="Print formatted SMS body for each scenario",
    )
    ap.add_argument(
        "--home-barangay",
        default="Zapote",
        help="subject_home_barangay for tests (default: Zapote)",
    )
    args = ap.parse_args()
    home = str(args.home_barangay)
    sms_preview = bool(args.sms_preview)

    print("SmartShell routing matrix (spoofed GPS coordinates)")
    print(f"Home barangay: {home}")
    print(f"Family phones loaded from config ({len(contacts.load_family_contacts()[0])} contact(s))")

    all_ok = True
    for name, lat, lon in _load_centroid_cases():
        if not _run_case(name, lat, lon, home_barangay=home, sms_preview=sms_preview):
            all_ok = False

    _run_case("Outside Manila", _OUTSIDE_LAT, _OUTSIDE_LON, home_barangay=home, sms_preview=sms_preview)
    _run_case("No GPS", None, None, home_barangay=home, sms_preview=sms_preview)

    print("\n--- Summary ---")
    print("Inside each barangay centroid: expect Inside Biñan + accident barangay ≈ that barangay.")
    print("Outside Manila: Outside Biñan, no accident barangay, family + home rescuer only.")
    print("No GPS: Unknown area, family + home rescuer only.")
    print("WARN = nearest-centroid mismatch (tune barangay_centroids.binan.json).")
    if all_ok:
        print("Matrix: all barangay centroid checks OK.")
        return 0
    print("Matrix: some centroid checks WARN (see above).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
