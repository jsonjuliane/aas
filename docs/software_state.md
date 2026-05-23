# SmartShell — Software state vs prototype hardware

## What `src/` does today (Phase 1)

| Module | File | Maps to hardware | Behavior when correctly configured |
|--------|------|------------------|-------------------------------------|
| **Main loop** | `main.py` | All | Polls sensor; logs 3–5g impact-window samples; on validated impact (3–5g + tilt) plays countdown audio then exits. |
| **Sensor** | `sensor_mpu6050.py` | MPU-6050 @ I2C `0x68` | `calibrate()` at start; `evaluate_impact()` uses accel magnitude + baseline tilt. |
| **GPS** | `gps.py` | GPS UART | Reads NMEA from `GPS_SERIAL_PORT` **or** GPIO software UART (pigpio) when port is `None` (default for GPIO20/21 wiring). `get_fix()` parses `$GPGGA`. |
| **GSM** | `gsm_sim800l.py` | SIM800L on `/dev/serial0` | `send_sms_detailed()` via AT commands with retry logic. |
| **Audio** | `audio_mp3.py` | DFPlayer-style on UART | `play_track(N)` → `mp3/000N.mp3` on the SD card (command 0x03); kernel serial **or** pigpio GPIO TX when `MP3_SERIAL_PORT=None` (GPIO19 wiring). MP3 module reserved for future use. |
| **Cancel (button)** | `cancel.py` | GPIO **17** (optional button) | Active-low with internal pull-up. Wire a momentary switch between GPIO17 and GND. |
| **Cancel (voice)** | `voice_cancel.py` | USB mic (e.g. USB Audio Device) | Background Google STT keyword listener; says "cancel" to abort the countdown. Requires internet. Configured in `config.py`. |
| **Buzzer** | `buzzer_hw.py` | GPIO **18** (active-high buzzer) | Countdown tick beeps; each beep is GPIO.setup → drive → GPIO.cleanup. Silence ensured on startup via `buzzer_silence.py`. |
| **Contacts** | `contacts.py` | — | Loads `config/contacts.family.json` (family SMS list + template). |
| **Logging** | `logging_store.py` | — | Appends JSON lines under `logs/`. |
| **Config** | `config.py` | Pin + path constants | Single place for GPIO, baud, serial device paths, voice/buzzer thresholds. |

**Phase 2 (partial):** Biñan geofence + inside/outside in SMS/logs (`src/routing.py`, `config/geofence.binan.json`). Barangay recipient routing not wired yet.

**Phase 4 (not in `src` yet):** responder loop enhancements, watchdogs. **Boot autostart:** use `deploy/smartshell.service.example` + `README.md` now.

---

## If everything matches the prototype wiring

1. **OS:** I2C on; serial console **off** on primary UART; SIM on `/dev/serial0`.  
2. **Dependencies:** `pip install -r requirements.txt` on the Pi (`RPi.GPIO`, `smbus2`, `pyserial`, …).  
   OS-level: `sudo apt install -y flac pigpio python3-pigpio portaudio19-dev`
3. **Config:** `config/contacts.family.json` exists with valid numbers; optional `subject_home_barangay` for future routing.  
4. **Serial paths:** **`GPS_SERIAL_PORT=None`** and **`MP3_SERIAL_PORT=None`** use pigpio GPIO software UART (GPS on GPIO20/21, MP3 TX on GPIO19). If using USB adapters, set to `/dev/ttyUSB*`. Do not point GPS and GSM at the same `ttyS0`.  
5. **Cancel button:** Wire a momentary switch to **GPIO 17** + GND (or change `CANCEL_BUTTON_GPIO`).  
6. **Buzzer:** Wire active-high buzzer I/O pin to **GPIO 18** (Pin 12). Set up boot-time silence service (`deploy/smartshell-buzzer-silence.service.example`).  
7. **Voice cancel:** Requires USB microphone and internet connection. Tuned thresholds: `VOICE_KEYWORD_MIN_RMS = 6500`, `VOICE_SOUND_RMS_THRESHOLD = 10000`. Run `python -m src.mic_test --baseline` to re-tune.

Then run:

```bash
python -m src.main
```

Expected: continuous monitoring; 3–5g candidates are logged with flags; validated impact (with tilt) plays countdown audio (10-second window) then exits after SMS send.

---

## Gaps vs full thesis spec

| Spec | Code status |
|------|-------------|
| Voice "cancel" | **Implemented** — background Google STT keyword listener in `voice_cancel.py`; requires internet and USB mic. |
| Buzzer countdown | **Implemented** — GPIO18 active-high buzzer in `buzzer_hw.py`; tick beeps per second. |
| MP3 countdown audio | Wired (`audio_mp3.py`); DFPlayer serial TX implemented; RX feedback path unreliable on hardware (level-shift issue). Reserved for future fix. |
| Inside/outside Biñan (geofence) | **Implemented** — `routing.py`; SMS `Area:` line + `routing_decision` log. |
| Barangay recipient routing | Documented; **not** wired in `main.py` yet (Phase 2 Step 2–3). |
| Responder loop / incoming-SMS reply | Not implemented (Phase 4). |
| GPIO UART for GPS/MP3 without `/dev/tty*` | Implemented via pigpio software UART; requires `pigpio` + running `pigpiod` service on the Pi. |

---

## CLI flags and Thonny

- `--dry-run`: no I2C/UART/GPIO; useful on a laptop.  
- `--test-alert`: trigger impact action path immediately (countdown + SMS then exit). `--trigger` is a hidden alias.  
- `--core-flow-only`: init + monitor sensor only; skips alert action path.  
- `--disable-sms-send`: run full alert path but skip actual SMS send (bench testing).  
- `--action-cooldown-sec`: debounce consecutive true-collision actions (default from config).  
- `--impact-log-cooldown-sec`: debounce repeated 3–5g impact-window logs (default from config).  
- `python -m src.hardware_check`: full probe; **exit 1** if any `[FAIL]` line.  
- `python -m src.gsm_test`: GSM diagnostics (baud sweep, SIM, signal); optional `--send-sms PHONE "msg"`.  
- `python -m src.gps_test`: GPS NMEA stream test (`--duration-sec`).  
- `python -m src.mic_test --baseline`: measure mic ambient noise; outputs suggested RMS threshold values.  
- `python -m src.mic_test --keyword-test --keyword cancel`: test Google STT keyword detection.  
- `python -m src.mic_stt_oneshot`: one-shot STT test (checks flac, internet, mic).  
- `python -m src.buzzer_diag`: interactive buzzer GPIO scan and polarity test.  
- `python -m src.buzzer_silence`: immediately silence buzzer GPIO (also used by boot service).  
- `python -m src.audio_test --track 1`: play DFPlayer track 1; use `--probe-range N` to test track availability by ear.  
- Normal run: requires Pi + hardware + config as above.  
- Thonny: open `src/main.py` on the Pi; use venv interpreter if you use a venv. For **boot autostart**, use **`systemd`** (`deploy/smartshell.service.example`).
