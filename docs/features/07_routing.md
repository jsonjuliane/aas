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

## References

- `docs/phase0_config_format.md`
- `docs/PLAN.md` — Phase 2 scope
