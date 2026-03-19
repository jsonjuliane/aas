# Feature: Location-Based Routing (Phase 2)

## Overview

Alert recipients depend on rider location:

- **Inside Biñan, Laguna** → Family + Barangay rescuer (by location)
- **Outside Biñan** → Family only
- **No GPS fix** → Family only (fallback)

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
