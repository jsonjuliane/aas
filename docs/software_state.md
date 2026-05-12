# SmartShell — Software state vs prototype hardware

## What `src/` does today (Phase 1)

| Module | File | Maps to hardware | Behavior when correctly configured |
|--------|------|------------------|-------------------------------------|
| **Main loop** | `main.py` | All | Polls sensor; logs 3–5g impact-window samples; on validated impact (3–5g + tilt) plays countdown audio then exits (current phase). |
| **Sensor** | `sensor_mpu6050.py` | MPU-6050 @ I2C `0x68` | `calibrate()` at start; `is_impact_detected()` uses accel magnitude + baseline tilt. |
| **GPS** | `gps.py` | GPS UART | Reads NMEA from `GPS_SERIAL_PORT` **or** GPIO software UART (pigpio) when port is `None` (default for GPIO20/21 wiring). `get_fix()` parses `$GPGGA`. |
| **GSM** | `gsm_sim800l.py` | SIM800L on `/dev/serial0` | `send_sms()` via AT commands. |
| **Audio** | `audio_mp3.py` | DFPlayer-style on UART | `play_track(N)` → `mp3/000N.mp3` on the SD card (command 0x03); kernel serial **or** pigpio GPIO TX when `MP3_SERIAL_PORT=None` (GPIO19 wiring). |
| **Cancel** | `cancel.py` | GPIO **17** (optional button) | Active-low with pull-up. **Not** on the main wiring table — add a button or change pin in `config.py`. |
| **Contacts** | `contacts.py` | — | Loads `config/contacts.family.json` (family SMS list + template). |
| **Logging** | `logging_store.py` | — | Appends JSON lines under `logs/`. |
| **Config** | `config.py` | Pin + path constants | Single place for GPIO, baud, serial device paths. |

**Phase 2 (not in `src` yet):** barangay routing, geofence, `contacts.barangay.json` logic.

**Phase 4 (not in `src` yet):** responder loop enhancements, watchdogs. **Boot autostart:** use `deploy/smartshell.service.example` + `README.md` now.

---

## If everything matches the prototype wiring

1. **OS:** I2C on; serial console **off** on primary UART; SIM on `/dev/serial0`.  
2. **Dependencies:** `pip install -r requirements.txt` on the Pi (`RPi.GPIO`, `smbus2`, `pyserial`, …).  
3. **Config:** `config/contacts.family.json` exists with valid numbers; optional `subject_home_barangay` for future routing.  
4. **Serial paths:** **`GPS_SERIAL_PORT=None`** and **`MP3_SERIAL_PORT=None`** use pigpio GPIO software UART (GPS on GPIO20/21, MP3 TX on GPIO19). If using USB adapters, set to `/dev/ttyUSB*`. Do not point GPS and GSM at the same `ttyS0`.  
5. **Cancel:** Wire a momentary switch to **GPIO 17** + GND or change `CANCEL_BUTTON_GPIO`.  
6. **MP3:** SD card uses **`mp3/0001.mp3`** (etc.); set `MP3_DEFAULT_TRACK` in `config.py`. Keep `MP3_SERIAL_PORT=None` for GPIO soft UART, or `/dev/ttyUSB*` for USB-TTL.
Then run:

```bash
python -m src.main
```

Expected: continuous monitoring; 3–5g candidates are logged with flags; validated impact (with tilt) plays countdown audio and exits.

---

## Gaps vs full thesis spec

| Spec | Code status |
|------|-------------|
| Voice “cancel” | Not implemented (Phase 3); only GPIO button in Phase 1. |
| Location routing (Biñan / home barangay) | Documented in `docs/`; **not** wired in `main.py` yet (Phase 2). |
| Buzzer on barangay SMS reply | Not implemented (Phase 4). |
| GPIO UART for GPS/MP3 without `/dev/tty*` | Implemented via pigpio software UART; requires `pigpio` + running `pigpiod` service on the Pi. |

---

## CLI flags and Thonny

- `--dry-run`: no I2C/UART/GPIO; useful on a laptop.  
- `--test-alert`: trigger impact action path immediately (countdown audio then exit). `--trigger` is a hidden alias.  
- `--action-cooldown-sec`: debounce consecutive true-collision actions (default from config).  
- `--impact-log-cooldown-sec`: debounce repeated 3–5g impact-window logs (default from config).  
- `python -m src.audio_test --track 1`: play DFPlayer track 1; use `--probe-range N` to test track availability by ear.  
- `python -m src.hardware_check`: full probe; **exit 1** if any `[FAIL]` line.  
- `python -m src.gsm_test`: GSM diagnostics (baud sweep, SIM, signal); optional `--send-sms PHONE "msg"`.  
- `python -m src.gps_test`: GPS NMEA stream test (`--duration-sec`).  
- Normal run: requires Pi + hardware + config as above.  
- Thonny: open `src/main.py` on the Pi; use venv interpreter if you use a venv. For **boot autostart**, use **`systemd`** (`deploy/smartshell.service.example`).
