# Collision SMS — final format (Globe / SIM800L)

## What works on Globe prepaid P2P SMS

- ASCII only (`Inside Binan`, not `Biñan`)
- One part, about **130–154 characters**
- **GPS coordinates** — not `https://` map links (carrier blocks URLs; modem may still show `+CMGS` OK)

## Template (`contacts.family.json`)

```text
SMARTSHELL COLLISION ALERT

Rider: {name}
Area: {area}
Home: {home_barangay} | Accident: {accident_barangay}

GPS: {map_url}
```

`{map_url}` is filled as plain coordinates, e.g. `14.3331, 121.0854`.

## Who receives the same text

**Family** and **barangay rescuers** get the **identical SMS body**. Routing only changes **which phone numbers** are called, not the message wording.

### Example (inside Biñan, GPS fix, home Zapote, accident near Sto. Domingo)

**Message (everyone):**

```text
SMARTSHELL COLLISION ALERT

Rider: Juan Dela Cruz
Area: Inside Binan
Home: Zapote | Accident: Sto. Domingo

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

Same template; `Area` may be `Outside Binan` or `Unknown (no GPS)`; `Accident` may be `N/A`. Only **family + home** rescuer phones (no accident barangay rescuer).

## Testing configuration

While testing, all family and barangay phones may be set to one number. Revert before real deployment.

Verify on Pi:

```bash
python -m src.sms_config_check
python -m src.gsm_test --send-alert-sms +639202828660
```
