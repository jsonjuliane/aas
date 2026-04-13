# SmartShell — Software state vs prototype hardware

## What `src/` does today (Phase 1)

| Module | File | Maps to hardware | Behavior when correctly configured |
|--------|------|------------------|-------------------------------------|
| **Main loop** | `main.py` | All | Polls sensor; logs 3–5g impact-window samples; on validated impact (3–5g + tilt) plays countdown audio then exits (current phase). |
| **Sensor** | `sensor_mpu6050.py` | MPU-6050 @ I2C `0x68` | `calibrate()` at start; `is_impact_detected()` uses accel magnitude + baseline tilt. |
| **GPS** | `gps.py` | GPS UART | Reads NMEA from `GPS_SERIAL_PORT` **or** GPIO software UART (pigpio) when port is `None` (default for GPIO20/21 wiring). `get_fix()` parses `$GPGGA`. |
| **GSM** | `gsm_sim800l.py` | SIM800L on `/dev/serial0` | `send_sms()` via AT commands. |
| **Audio** | `audio_mp3.py` | DFPlayer-style on UART | `play_track(1)` sends serial frame via kernel serial port **or** pigpio GPIO TX when `MP3_SERIAL_PORT=None` (default for GPIO19 wiring). |
| **Cancel** | `cancel.py` | GPIO **17** (optional button) | Active-low with pull-up. **Not** on the main wiring table — add a button or change pin in `config.py`. |
| **Contacts** | `contacts.py` | — | Loads `config/contacts.family.json` (family SMS list + template). |
| **Logging** | `logging_store.py` | — | Appends JSON lines under `logs/`. |
| **Config** | `config.py` | Pin + path constants | Single place for GPIO, baud, serial device paths. |
| **Buzzer GPIO** | `buzzer_hw.py` | Buzzer driver (GPIO 18) | At normal startup, drives line to **silent** so a floating pin does not hold the buzzer on. `python -m src.buzzer_test --silence-only` exits after silent; `python -m src.buzzer_test` turns ON then OFF for a bench check. |

**Phase 2 (not in `src` yet):** barangay routing, geofence, `contacts.barangay.json` logic.

**Phase 4 (not in `src` yet):** incoming SMS → buzzer patterns, watchdogs. **Boot autostart:** use `deploy/smartshell.service.example` + `README.md` now.

---

## If everything matches the prototype wiring

1. **OS:** I2C on; serial console **off** on primary UART; SIM on `/dev/serial0`.  
2. **Dependencies:** `pip install -r requirements.txt` on the Pi (`RPi.GPIO`, `smbus2`, `pyserial`, …).  
3. **Config:** `config/contacts.family.json` exists with valid numbers; optional `subject_home_barangay` for future routing.  
4. **Serial paths:** **`GPS_SERIAL_PORT=None`** and **`MP3_SERIAL_PORT=None`** use pigpio GPIO software UART (GPS on GPIO20/21, MP3 TX on GPIO19). If using USB adapters, set to `/dev/ttyUSB*`. Do not point GPS and GSM at the same `ttyS0`.  
5. **Cancel:** Wire a momentary switch to **GPIO 17** + GND or change `CANCEL_BUTTON_GPIO`.  
6. **MP3:** SD card in DFPlayer with track `001`; USB-TTL path must match `MP3_SERIAL_PORT`.  
7. **Buzzer:** If it screams at power-up until the app runs, use `python -m src.buzzer_test --silence-only` or flip `BUZZER_ACTIVE_HIGH` in `config.py` — see `README.md` / `docs/hardware.md`.

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
- `python -m src.buzzer_test --silence-only`: drive buzzer GPIO off and exit (bring-up).  
- `python -m src.buzzer_test` / `--duration-sec`: buzzer ON for a short time then OFF (bench).  
- `python -m src.audio_test --track 1`: play DFPlayer track 1; use `--probe-range N` to test track availability by ear.  
- `python -m src.hardware_check`: full probe; **exit 1** if any `[FAIL]` line.  
- `python -m src.gsm_test`: GSM diagnostics (baud sweep, SIM, signal); optional `--send-sms PHONE "msg"`.  
- `python -m src.gps_test`: GPS NMEA stream test (`--duration-sec`).  
- Normal run: requires Pi + hardware + config as above.  
- Thonny: open `src/main.py` on the Pi; use venv interpreter if you use a venv. For **boot autostart**, use **`systemd`** (`deploy/smartshell.service.example`).
