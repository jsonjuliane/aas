# Phase 0 — Configuration Format

This document defines the JSON configuration formats used by the SmartShell system. All config files live under `config/`.

---

## contacts.family.json

**Purpose**: Family/emergency contacts to receive SMS alerts. Always notified regardless of location.

| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Schema version (currently 1) |
| `contacts` | array | List of contact objects |
| `contacts[].name` | string | Human-readable label |
| `contacts[].phone` | string | E.164 format (e.g. `+639171234567`) |
| `contacts[].priority` | int | Order for sending (1 = first) |
| `message_template` | string | SMS body. Placeholders: `{lat}`, `{lon}`, `{timestamp}` |
| `subject_home_barangay` | string | Barangay where the rider lives (for routing when outside Biñan or no GPS fix) |

**Example**: See `config/contacts.family.json.example`.

**Security**: Do **not** commit `contacts.family.json` (contains real phone numbers). Use `.gitignore` or keep it outside the repo.

---

## contacts.barangay.json

**Purpose**: Barangay rescuer contacts. Maps barangay name → rescuer phone. Used for: accident-location barangay (when inside Biñan) and subject's home barangay (always, when configured).

| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Schema version (currently 1) |
| `barangays` | array | Barangay → rescuer mapping |
| `barangays[].name` | string | Barangay name (must match geofence lookup) |
| `barangays[].rescuer_phone` | string | E.164 format |
| `default_rescuer_phone` | string | Fallback if GPS→barangay lookup fails |

**Example**: See `config/contacts.barangay.json.example`.

---

## geofence.binan.json (Phase 2)

**Purpose**: Polygon boundary for "inside Biñan, Laguna". Used for routing: inside → Family + accident barangay + home barangay; outside → Family + home barangay.

| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Schema version |
| `boundary` | array | List of `[lon, lat]` coordinates (GeoJSON ring) |
| `name` | string | Human-readable label |

**Note**: Implemented in Phase 2. Template to be added when routing is implemented.
