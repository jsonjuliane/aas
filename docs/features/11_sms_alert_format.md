# Collision SMS — final format (Globe / SIM800L)

## What works on Globe prepaid P2P SMS

- ASCII only (`Inside Binan`, not `Biñan`)
- One part, about **130–154 characters**
- **GPS coordinates** — not `https://` map links (carrier blocks URLs; modem may still show `+CMGS` OK)

## Template (`contacts.family.json`)

```text
SMARTSHELL COLLISION ALERT

Rider: {name}
Home: {home_barangay}
Accident: {accident_barangay}

GPS: {map_url}
```

`{map_url}` is filled as plain coordinates, e.g. `14.3331, 121.0854`.

## ``Accident:`` field (address)

Same `(lat, lon)` as ``GPS:``. Fallback order:

1. **Street/area** — Nominatim reverse geocode (with retries)
2. **Barangay polygon** — name from `barangay_boundaries.binan.json` (inside Biñan)
3. **Nearest barangay** — `Near {name} (approx)` from `barangay_centroids.binan.json`
4. **Coordinates** — same numbers as ``GPS:`` (outside Biñan or no barangay match)
5. **`N/A`** — only when there is no GPS fix

All **24** Biñan barangays are in the centroid/boundary configs; rescuer phones in `contacts.barangay.json`.

## Who receives the same text

**Family** and **barangay rescuers** get the **identical SMS body**. Routing only changes **which phone numbers** are called, not the message wording.

### Example (inside Biñan, GPS fix, home Zapote, accident near Sto. Domingo)

**Message (everyone):**

```text
SMARTSHELL COLLISION ALERT

Rider: Juan Dela Cruz
Home: Zapote
Accident: Sto. Domingo

GPS: 14.3331, 121.0854
```

**Family** (`contacts.family.json`): each listed contact is sent this message (priority order).

**Barangay** (`contacts.barangay.json`): rescuer numbers are added by routing:

| Role | When | Barangay |
|------|------|----------|
| Home rescuer | Always (if phone configured) | `subject_home_barangay` (e.g. Zapote) |
| Accident rescuer | Inside Biñan + GPS | Nearest centroid (e.g. Sto. Domingo) |

Duplicate numbers are sent **once** per alert.

### Example (outside Biñan or no GPS)

Same template; `Accident` may be `N/A` only when no GPS fix exists. Only **family + home** rescuer phones (no accident barangay rescuer).

## Testing configuration

While testing, all family and barangay phones may be set to one number. Revert before real deployment.

Verify on Pi:

```bash
python -m src.sms_config_check
python -m src.gsm_test --send-alert-sms +639202828660
```
