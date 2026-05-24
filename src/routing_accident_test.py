"""
Bench test for SMS ``Accident:`` resolver modes (geocode, polygon, centroid, auto).

Run from project root (needs shapely + config; geocode modes need internet):

  python -m src.routing_accident_test
  python -m src.routing_accident_test --preset langkiwa
  python -m src.routing_accident_test --mode geocode --lat 14.3331 --lon 121.0854
  python -m src.routing_accident_test --mode all --preset langkiwa
"""

from __future__ import annotations

import argparse
import sys

from src.routing import (
    area_label,
    classify_location,
    is_inside_binan,
    resolve_accident_barangay,
    resolve_accident_sms_address_mode,
)

# Named sample points (lat, lon).
PRESETS: dict[str, tuple[float, float, str]] = {
    "langkiwa": (14.2989841, 121.0597082, "Inside Biñan — Langkiwa centroid (polygon expected)"),
    "binan-center": (14.34267, 121.08071, "Inside Biñan — city center"),
    "delapaz": (14.3489723, 121.0849198, "Inside Biñan — Delapaz centroid"),
    "outside-manila": (14.5905, 120.98, "Outside Biñan — Manila area"),
}

MODES = ("geocode", "polygon", "centroid", "coordinates", "auto")


def _print_mode_result(lat: float, lon: float, mode: str) -> None:
    label, details = resolve_accident_sms_address_mode(lat, lon, mode=mode)  # type: ignore[arg-type]
    print(f"  [{mode:11}] Accident: {label!r}")
    print(
        f"             source={details.get('source')} "
        f"address={details.get('address')!r} "
        f"barangay={details.get('barangay')!r} "
        f"method={details.get('barangay_method')}"
    )


def _print_context(lat: float, lon: float) -> None:
    inside = is_inside_binan(lat, lon)
    cls = classify_location(lat, lon)
    brgy, method = resolve_accident_barangay(lat, lon)
    print(f"Coordinates: ({lat}, {lon})")
    print(f"Inside Biñan geofence: {inside}")
    print(f"Area (SMS): {area_label(cls)}")
    print(f"Routing barangay (production): {brgy} ({method})")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Test Accident SMS address: geocode, polygon, nearest centroid, auto chain."
    )
    ap.add_argument(
        "--mode",
        choices=[*MODES, "all"],
        default="all",
        help="Resolver to exercise (default: all modes for comparison)",
    )
    ap.add_argument("--preset", choices=sorted(PRESETS.keys()), help="Named test coordinates")
    ap.add_argument("--lat", type=float, help="Latitude (WGS84)")
    ap.add_argument("--lon", type=float, help="Longitude (WGS84)")
    args = ap.parse_args()

    if args.preset:
        lat, lon, note = PRESETS[args.preset]
        print(f"Preset: {args.preset} — {note}\n")
    elif args.lat is not None and args.lon is not None:
        lat, lon = float(args.lat), float(args.lon)
    else:
        lat, lon, note = PRESETS["langkiwa"]
        print(f"Default preset: langkiwa — {note}\n")

    _print_context(lat, lon)

    if args.mode == "all":
        print("Modes (production auto uses first success: geocode → polygon → centroid → coordinates):")
        for mode in MODES:
            _print_mode_result(lat, lon, mode)
        print()
        auto_label, auto_details = resolve_accident_sms_address_mode(lat, lon, mode="auto")
        print(f"→ SMS would use (auto): {auto_label!r}  [source={auto_details.get('source')}]")
    else:
        print(f"Single mode: {args.mode}")
        _print_mode_result(lat, lon, args.mode)

    print(
        "\nNotes:"
        "\n  geocode   — needs internet (Nominatim)"
        "\n  polygon   — barangay_boundaries.binan.json only; N/A if outside cell"
        "\n  centroid  — nearest of 24 centroids; label includes (approx)"
        "\n  auto      — same chain as collision SMS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
