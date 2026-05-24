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

When GPS is available and `REVERSE_GEOCODE_ENABLED` is True, `resolve_accident_location_label()` calls
Nominatim (internet) for a short **street/area address**. If that fails, inside Biñan falls back to the
nearest barangay name from `barangay_centroids.binan.json`.

**Rescuer phone routing** still uses nearest centroid → `contacts.barangay.json` (not the street string).

## Accident barangay (routing, inside Biñan)

When GPS is inside the city boundary, `resolve_accident_barangay()` picks the nearest reference point in `barangay_centroids.binan.json` (OSM/Nominatim centroids). Recipient list adds that barangay's rescuer phone from `contacts.barangay.json`. SMS includes `{accident_barangay}` and `{notified}`.

## References

- `docs/phase0_config_format.md`
- `docs/PLAN.md` — Phase 2 scope
