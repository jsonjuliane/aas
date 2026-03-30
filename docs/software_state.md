# SmartShell — Software state vs prototype hardware

## What `src/` does today (Phase 1)

| Module | File | Maps to hardware | Behavior when correctly configured |
|--------|------|------------------|-------------------------------------|
| **Main loop** | `main.py` | All | Polls sensor; on impact → countdown → cancel window → GPS + SMS + log. |
| **Sensor** | `sensor_mpu6050.py` | MPU-6050 @ I2C `0x68` | `calibrate()` at start; `is_impact_detected()` uses accel magnitude + baseline tilt. |
| **GPS** | `gps.py` | GPS UART | Reads NMEA from `GPS_SERIAL_PORT` (default **`None`** — set e.g. `/dev/ttyUSB0` for USB GPS). `get_fix()` parses `$GPGGA`. |
| **GSM** | `gsm_sim800l.py` | SIM800L on `/dev/serial0` | `send_sms()` via AT commands. |
| **Audio** | `audio_mp3.py` | DFPlayer-style on UART | `play_track(1)` sends serial frame; default **`MP3_SERIAL_PORT`** is **`/dev/ttyUSB0`** for USB-TTL bench wiring, or **`None`** if unused. |
| **Cancel** | `cancel.py` | GPIO **17** (optional button) | Active-low with pull-up. **Not** on the main wiring table — add a button or change pin in `config.py`. |
| **Contacts** | `contacts.py` | — | Loads `config/contacts.family.json` (family SMS list + template). |
| **Logging** | `logging_store.py` | — | Appends JSON lines under `logs/`. |
| **Config** | `config.py` | Pin + path constants | Single place for GPIO, baud, serial device paths. |
| **Buzzer GPIO** | `buzzer_hw.py` | Buzzer driver (GPIO 18) | At normal startup, drives line to **silent** so a floating pin does not hold the buzzer on. `--silence-buzzer` does the same and exits. |

**Phase 2 (not in `src` yet):** barangay routing, geofence, `contacts.barangay.json` logic.

**Phase 4 (not in `src` yet):** incoming SMS → buzzer patterns, watchdogs. **Boot autostart:** use `deploy/smartshell.service.example` + `README.md` now.

---

## If everything matches the prototype wiring

1. **OS:** I2C on; serial console **off** on primary UART; SIM on `/dev/serial0`.  
2. **Dependencies:** `pip install -r requirements.txt` on the Pi (`RPi.GPIO`, `smbus2`, `pyserial`, …).  
3. **Config:** `config/contacts.family.json` exists with valid numbers; optional `subject_home_barangay` for future routing.  
4. **Serial paths:** **`GPS_SERIAL_PORT`**: `None` unless USB GPS (or other `/dev/tty*`). **`MP3_SERIAL_PORT`**: `/dev/ttyUSB0` if DFPlayer via USB-TTL, else `None`. Do not point GPS and GSM at the same `ttyS0` unless one module uses that UART.  
5. **Cancel:** Wire a momentary switch to **GPIO 17** + GND or change `CANCEL_BUTTON_GPIO`.  
6. **MP3:** SD card in DFPlayer with track `001`; USB-TTL path must match `MP3_SERIAL_PORT`.  
7. **Buzzer:** If it screams at power-up until the app runs, use `python -m src.main --silence-buzzer` or flip `BUZZER_ACTIVE_HIGH` in `config.py` — see `README.md` / `docs/hardware.md`.

Then run:

```bash
python -m src.main
```

Expected: continuous monitoring; real impacts trip the flow; SMS goes out if not cancelled and GSM/GPS work.

---

## Gaps vs full thesis spec

| Spec | Code status |
|------|-------------|
| Voice “cancel” | Not implemented (Phase 3); only GPIO button in Phase 1. |
| Location routing (Biñan / home barangay) | Documented in `docs/`; **not** wired in `main.py` yet (Phase 2). |
| Buzzer on barangay SMS reply | Not implemented (Phase 4). |
| GPIO UART for GPS/MP3 without `/dev/tty*` | May need extra library or device tree — see `docs/hardware.md`. |

---

## CLI flags and Thonny

- `--dry-run`: no I2C/UART/GPIO; useful on a laptop.  
- `--test-alert`: one immediate full alert cycle (bench test). `--trigger` is a hidden alias.  
- `--silence-buzzer`: drive buzzer GPIO off and exit (bring-up).  
- Normal run: requires Pi + hardware + config as above.  
- Thonny: open `src/main.py` on the Pi; use venv interpreter if you use a venv. For **boot autostart**, use **`systemd`** (`deploy/smartshell.service.example`).
