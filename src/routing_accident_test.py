"""
Bench test for SMS ``Accident:`` resolver modes (geocode, polygon, centroid, auto).

Prints resolver output and full collision SMS body per mode (does not send SMS).

Run from project root (needs shapely + config; geocode modes need internet):

  python -m src.routing_accident_test --mode all --lat 14.2989841 --lon 121.0597082
  python -m src.routing_accident_test --mode geocode --lat 14.2989841 --lon 121.0597082
  python -m src.routing_accident_test --mode polygon --lat 14.2989841 --lon 121.0597082
  python -m src.routing_accident_test --mode centroid --lat 14.2989841 --lon 121.0597082
  python -m src.routing_accident_test --mode coordinates --lat 14.2989841 --lon 121.0597082
  python -m src.routing_accident_test --mode auto --lat 14.2989841 --lon 121.0597082
  python -m src.routing_accident_test --no-sms-preview --mode auto --lat 14.3331 --lon 121.0854
"""

from __future__ import annotations

import argparse
import textwrap

from src import contacts
from src.routing import (
    area_label,
    classify_location,
    get_recipients,
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


def _resolve_coordinates(
    ap: argparse.ArgumentParser,
    *,
    preset: str | None,
    lat: float | None,
    lon: float | None,
    positional: list[float],
) -> tuple[float, float, str | None]:
    """Return (lat, lon, optional header note). Precedence: --lat/--lon, positional LAT LON, --preset, default."""
    if lat is not None or lon is not None:
        if lat is None or lon is None:
            ap.error("--lat and --lon must be given together")
        if preset:
            ap.error("Use either --preset or --lat/--lon, not both")
        if positional:
            ap.error("Use either trailing LAT LON or --lat/--lon, not both")
        return float(lat), float(lon), None

    if positional:
        if len(positional) != 2:
            ap.error("trailing coordinates must be exactly LAT and LON (two numbers)")
        if preset:
            ap.error("Use either --preset or trailing LAT LON, not both")
        return float(positional[0]), float(positional[1]), None

    if preset:
        plat, plon, note = PRESETS[preset]
        return plat, plon, f"Preset: {preset} — {note}"

    plat, plon, note = PRESETS["langkiwa"]
    return plat, plon, f"Default preset: langkiwa — {note}"


def _print_sms_preview(
    lat: float,
    lon: float,
    accident_label: str,
    *,
    home_barangay: str,
    template: str,
    rider_name: str,
) -> None:
    """Print full collision SMS body (same template as production; not sent)."""
    area = area_label(classify_location(lat, lon))
    try:
        route = get_recipients(
            lat,
            lon,
            family_phones=["+639000000000"],
            home_barangay=home_barangay,
        )
        notified = str(route.get("notified", ""))
    except Exception as e:
        notified = f"(routing error: {e})"
    body = contacts.format_alert_message(
        template=template,
        lat=lat,
        lon=lon,
        rider_name=rider_name,
        home_barangay=home_barangay,
        area=area,
        accident_barangay=accident_label,
        notified=notified,
    )
    print("  --- SMS preview (not sent) ---")
    for line in body.splitlines():
        print(f"    {line}")
    print(f"  ({len(body)} chars)")


def _print_mode_result(
    lat: float,
    lon: float,
    mode: str,
    *,
    sms_preview: bool,
    home_barangay: str,
    template: str,
    rider_name: str,
) -> None:
    label, details = resolve_accident_sms_address_mode(lat, lon, mode=mode)  # type: ignore[arg-type]
    print(f"  [{mode:11}] Accident: {label!r}")
    print(
        f"             source={details.get('source')} "
        f"address={details.get('address')!r} "
        f"barangay={details.get('barangay')!r} "
        f"method={details.get('barangay_method')}"
    )
    if sms_preview:
        _print_sms_preview(
            lat,
            lon,
            label,
            home_barangay=home_barangay,
            template=template,
            rider_name=rider_name,
        )
    print()


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
    mode_help = textwrap.dedent(
        """
        Modes (single resolver or compare all):
          geocode     — Nominatim street/area only (internet)
          polygon     — barangay_boundaries.binan.json cell name only
          centroid    — nearest of 24 centroids: Near {name} (approx)
          coordinates — lat, lon string only (same style as GPS: line)
          auto        — production chain: geocode → polygon → centroid → coordinates
          all         — run every mode above at the same lat/lon
        """
    ).strip()
    ap = argparse.ArgumentParser(
        description="Test Accident SMS address resolvers; prints full SMS preview (not sent).",
        epilog=mode_help,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--mode",
        choices=[*MODES, "all"],
        default="all",
        help="Resolver to exercise (default: all). See epilog for mode list.",
    )
    ap.add_argument(
        "--sms-preview",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print full collision SMS body per mode (default: on; does not send)",
    )
    ap.add_argument(
        "--home-barangay",
        default="Zapote",
        help="Home barangay in SMS template (default: Zapote)",
    )
    ap.add_argument("--preset", choices=sorted(PRESETS.keys()), help="Named test coordinates")
    ap.add_argument("--lat", type=float, metavar="LAT", help="Latitude (WGS84); requires --lon")
    ap.add_argument("--lon", type=float, metavar="LON", help="Longitude (WGS84); requires --lat")
    ap.add_argument(
        "coords",
        nargs="*",
        type=float,
        metavar=("LAT", "LON"),
        help="Optional trailing LAT LON (e.g. --mode all 14.2989841 121.0597082)",
    )
    args = ap.parse_args()

    lat, lon, note = _resolve_coordinates(
        ap,
        preset=args.preset,
        lat=args.lat,
        lon=args.lon,
        positional=list(args.coords),
    )
    if note:
        print(f"{note}\n")

    try:
        _phones, template, rider_name, _cfg_home = contacts.load_family_contacts()
    except Exception as e:
        print(f"contacts load failed: {e}")
        return 1
    home_barangay = str(args.home_barangay)
    sms_preview = bool(args.sms_preview)

    _print_context(lat, lon)
    if sms_preview:
        print("SMS preview uses contacts.family.json template (not sent via GSM).\n")

    preview_kw = {
        "sms_preview": sms_preview,
        "home_barangay": home_barangay,
        "template": template,
        "rider_name": rider_name,
    }

    if args.mode == "all":
        print("Modes (production auto: geocode → polygon → centroid → coordinates):")
        for mode in MODES:
            _print_mode_result(lat, lon, mode, **preview_kw)
        auto_label, auto_details = resolve_accident_sms_address_mode(lat, lon, mode="auto")
        print(f"→ Production (auto) picks: {auto_label!r}  [source={auto_details.get('source')}]")
    else:
        print(f"Single mode: {args.mode}")
        _print_mode_result(lat, lon, args.mode, **preview_kw)

    print("\nDoes not send SMS. To send a real test: python -m src.gsm_test --send-alert-sms +63...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
