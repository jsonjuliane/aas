# Feature: Location-Based Routing (Phase 2)

## Overview

Alert recipients depend on rider location:

- **Inside Biñan, Laguna** → Family + Barangay where accident happened + Barangay where subject lives
- **Outside Biñan** → Family + Barangay where subject lives
- **No GPS fix** → Family + Barangay where subject lives (fallback)

The subject's home barangay is configured in contacts (rider's residence).

## Config Files

| File | Purpose |
|------|---------|
| `contacts.family.json` | Family contacts (always notified) |
| `contacts.barangay.json` | Barangay → rescuer mapping |
| `geofence.binan.json` | Polygon boundary for Biñan |

## Module Interface

See `docs/phase0_module_boundaries.md` — `routing`:

- `load_config()` — Load contacts + geofence
- `get_recipients(lat, lon)` — Returns list of phone numbers

## Geofencing

Use `shapely` to test point-in-polygon. Boundary coordinates in `geofence.binan.json` as GeoJSON-style ring `[[lon, lat], ...]`.

## Accident location in SMS (``Accident:`` field)

`resolve_accident_sms_address()` fallback order: **geocode** → **barangay polygon** → **nearest centroid** (`Near … (approx)`) → **coordinates** → `N/A` (no GPS only).

Configs list all **24** Biñan barangays. Regenerate polygons: `python scripts/generate_barangay_boundaries.py`.

Bench each resolver mode: `python -m src.routing_accident_test --mode all --preset langkiwa`

## Accident barangay (routing, inside Biñan)

1. **Polygon** — point inside `barangay_boundaries.binan.json` (Voronoi cells clipped to city geofence).
2. **Fallback** — nearest point in `barangay_centroids.binan.json` if no polygon matches.

Regenerate polygons: `python scripts/generate_barangay_boundaries.py` (needs `shapely`).

Recipient list uses the resolved barangay name → `contacts.barangay.json`. SMS includes combined `{accident_barangay}` and `{notified}`.

## References

- `docs/phase0_config_format.md`
- `docs/PLAN.md` — Phase 2 scope
