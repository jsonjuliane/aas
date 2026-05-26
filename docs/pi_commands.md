# Raspberry Pi — important commands (SmartShell)

Run these from a terminal on the Pi. **Use the same Python you installed dependencies with** (usually the project venv).

---

## One-time OS packages (Pi)

`shapely` (routing / geofence) needs the GEOS system library. If `routing_test` fails with `libgeos_c.so.1: cannot open shared object file`:

```bash
sudo apt-get update
sudo apt-get install -y libgeos-dev unzip wget
```

Then reinstall Python deps in your venv: `pip install -r requirements.txt`

Offline voice cancel prefers Vosk where supported. Download the small English model once:

```bash
cd ~/AccidentAlertSystem
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p models
wget -O /tmp/vosk-model-small-en-us-0.15.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip /tmp/vosk-model-small-en-us-0.15.zip -d models/
```

Do **not** use `pip install vosk` on Pi if it says no matching distribution. `requirements.txt` uses the official Vosk v0.3.45 `aarch64` / `armv7l` wheels directly.

On `armv6l`, Vosk wheels are unavailable; use PocketSphinx:

```bash
source .venv/bin/activate
pip install pocketsphinx
python - <<'PY'
import pocketsphinx
print("pocketsphinx OK")
PY
```

---

## Project + venv

```bash
cd ~/AccidentAlertSystem
source .venv/bin/activate
python -m src.main --help
```

If you did not use a venv and installed packages system-wide:

```bash
cd ~/AccidentAlertSystem
python3 -m src.main --help
```

**Why `python -m src.main`?** It runs the package entrypoint correctly; `python src/main.py` can work but `-m` is preferred.

---

## Family contacts config

These commands read/write `config/contacts.family.json`. Writes are validated and saved atomically with a `.bak` backup.

```bash
cd ~/AccidentAlertSystem
source .venv/bin/activate

# Read current rider info and emergency contacts
python -m src.contacts_config_store get
python -m src.contacts_config_store list-contacts

# Update rider info
python -m src.contacts_config_store set-rider --name "Juan Dela Cruz" --home "Zapote"

# Contacts are limited to 3 family numbers; update first if all slots are full
python -m src.contacts_config_store update-contact 1 --name "Mom" --phone +639201234567
python -m src.contacts_config_store delete-contact 3
python -m src.contacts_config_store add-contact --name "Mom" --phone 09201234567

# Validate only
python -m src.contacts_config_store validate
```

For practice, copy the file and pass `--path` before the command so the real contacts are untouched:

```bash
cp config/contacts.family.json /tmp/contacts.family.test.json
python -m src.contacts_config_store --path /tmp/contacts.family.test.json update-contact 1 --name "Test" --phone 09201234567
```

The future phone/Bluetooth service will use JSON commands through the same store:

```bash
python -m src.contacts_config_protocol '{"op":"ping"}' --pretty
python -m src.contacts_config_protocol '{"op":"get_config","pin":"000000"}' --pretty
python -m src.contacts_config_protocol '{"op":"set_rider","pin":"000000","rider_name":"Juan Dela Cruz","subject_home_barangay":"Zapote"}' --pretty
python -m src.contacts_config_protocol '{"op":"update_contact","pin":"000000","index":1,"name":"Mom","phone":"09201234567"}' --pretty
python -m src.contacts_config_protocol '{"op":"change_pin","pin":"000000","new_pin":"123456"}' --pretty
```

Default first-link PIN is `000000`. After linking, change it from the app or by command. The saved PIN is stored as a salted hash in `config/link_pin.json` (ignored by git). For temporary testing/admin override only:

```bash
export SMARTSHELL_CONFIG_PIN="123456"
```

---

## BLE GATT phone config server

BLE GATT is the preferred phone-app transport because it works with modern Android/iOS app APIs. It uses the same JSON commands as `contacts_config_protocol`.

Protocol:
- App scans for local name **`SmartShell`** and service UUID **`f2d00001-8b6b-4d5d-9d53-5e77295c1c01`**
- App subscribes to TX notify characteristic **`f2d00003-8b6b-4d5d-9d53-5e77295c1c01`**
- App writes one UTF-8 JSON command ending in newline (`\n`) to RX characteristic **`f2d00002-8b6b-4d5d-9d53-5e77295c1c01`**
- Pi sends one UTF-8 JSON response ending in newline (`\n`) over TX notifications. Reassemble chunks until newline.

First test the BLE protocol without Bluetooth hardware:

```bash
cd ~/AccidentAlertSystem
source .venv/bin/activate

printf '%s\n' '{"op":"ping"}' | python -m src.ble_config_server --stdio
printf '%s\n' '{"op":"get_config","pin":"000000"}' | python -m src.ble_config_server --stdio
printf '%s\n' '{"op":"validate","pin":"000000"}' | python -m src.ble_config_server --stdio
```

Test writes on a copy first:

```bash
cp config/contacts.family.json /tmp/contacts.family.ble-test.json
printf '%s\n' '{"op":"set_rider","pin":"000000","rider_name":"BLE Test","subject_home_barangay":"Zapote"}' | python -m src.ble_config_server --stdio --path /tmp/contacts.family.ble-test.json
python -m src.contacts_config_store --path /tmp/contacts.family.ble-test.json get
rm -f /tmp/contacts.family.ble-test.json /tmp/contacts.family.ble-test.json.bak
```

Prepare BLE packages on the Pi:

```bash
sudo apt-get update
sudo apt-get install -y bluetooth bluez rfkill python3-dbus python3-gi
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
```

Run diagnostics:

```bash
python -m src.ble_config_server --diagnose
```

Expected important lines:

```text
[OK] python dbus import
[OK] python gi/GLib import
[OK] bluetooth service active
[OK] adapter powered
[OK] GATT manager available
[OK] LE advertising manager available
```

Start the BLE GATT server:

```bash
python -m src.ble_config_server
```

If the venv cannot import `dbus` / `gi`, use the system Python on the Pi:

```bash
/usr/bin/python3 -m src.ble_config_server --diagnose
/usr/bin/python3 -m src.ble_config_server
```

If BlueZ rejects advertising with a permission error, run once with sudo while testing:

```bash
sudo -E /usr/bin/python3 -m src.ble_config_server
```

Example JSON commands for the app:

```json
{"op":"get_config"}
{"op":"get_config","pin":"000000"}
{"op":"update_contact","pin":"000000","index":1,"name":"Mom","phone":"09201234567"}
{"op":"set_rider","pin":"000000","rider_name":"Juan Dela Cruz","subject_home_barangay":"Zapote"}
{"op":"change_pin","pin":"000000","new_pin":"123456"}
```

---

## Bluetooth RFCOMM phone config server

The Bluetooth server uses the same JSON commands as `contacts_config_protocol`. It starts with RFCOMM / Serial Port style Bluetooth because it is easy to test from an Android Bluetooth terminal app.

First test the server protocol without Bluetooth hardware:

```bash
cd ~/AccidentAlertSystem
source .venv/bin/activate

printf '%s\n' '{"op":"ping"}' | python -m src.bluetooth_config_server --stdio
printf '%s\n' '{"op":"get_config","pin":"000000"}' | python -m src.bluetooth_config_server --stdio
printf '%s\n' '{"op":"validate","pin":"000000"}' | python -m src.bluetooth_config_server --stdio
```

Test writes on a copy first:

```bash
cp config/contacts.family.json /tmp/contacts.family.bt-test.json
printf '%s\n' '{"op":"set_rider","pin":"000000","rider_name":"BT Test","subject_home_barangay":"Zapote"}' | python -m src.bluetooth_config_server --stdio --path /tmp/contacts.family.bt-test.json
python -m src.contacts_config_store --path /tmp/contacts.family.bt-test.json get
rm -f /tmp/contacts.family.bt-test.json /tmp/contacts.family.bt-test.json.bak
```

Prepare Bluetooth on the Pi:

```bash
sudo apt-get update
sudo apt-get install -y bluetooth bluez rfkill
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
```

Make the Pi pairable/discoverable:

```bash
bluetoothctl
power on
agent on
default-agent
pairable on
discoverable on
show
```

In another Pi terminal, run the server:

```bash
cd ~/AccidentAlertSystem
source .venv/bin/activate
python -m src.bluetooth_config_server --channel 1
```

From an Android phone, use a Bluetooth serial terminal app, pair with the Pi, connect to the Serial Port/RFCOMM service, then send one JSON command per line:

```json
{"op":"get_config"}
{"op":"get_config","pin":"000000"}
{"op":"update_contact","pin":"000000","index":1,"name":"Mom","phone":"09201234567"}
{"op":"set_rider","pin":"000000","rider_name":"Juan Dela Cruz","subject_home_barangay":"Zapote"}
{"op":"change_pin","pin":"000000","new_pin":"123456"}
```

If channel `1` is busy, stop the server and try another channel:

```bash
python -m src.bluetooth_config_server --channel 3
```

Note: iOS does not generally expose classic RFCOMM/SPP to normal apps; for iPhone support we should implement BLE GATT after this RFCOMM proof-of-concept works.

---

## SMS deploy checklist (after `git pull`)

Use this after updating code so the Pi does **not** keep the old `SMARTSHELL UPDATE` template (causes `BiA@an` and failed delivery).

```bash
cd ~/AccidentAlertSystem
git pull
source .venv/bin/activate

# 1) Config must say COLLISION ALERT (not UPDATE). If needed, copy example then re-edit phones:
grep message_template config/contacts.family.json
# Should include: SMARTSHELL COLLISION ALERT and GPS: (coords only, not https URL)

# 2) Verify sample body is ASCII, ~154 chars, 1 SMS part:
python -m src.sms_config_check

# 3) Send one real-format alert to your phone (no [SSnn] tag):
python -m src.sms_config_check --send-test +639XXXXXXXXX
# Or: python -m src.gsm_test --send-alert-sms +639XXXXXXXXX

# 4) Full collision test (optional):
python -m src.main --test-alert --test-lat-lng 14.333 121.085 --disable-sms-send
python -m src.main --test-alert --test-lat-lng 14.333 121.085 --test-accident-mode geocode
python -m src.main --test-alert --test-lat-lng 14.333 121.085 --test-accident-mode polygon
python -m src.main --test-alert --test-lat-lng 14.333 121.085 --test-accident-mode centroid
python -m src.main --test-alert --test-lat-lng 14.333 121.085 --test-accident-mode coordinates
```

---

## Run modes (same interpreter as above)

```bash
# Main app
python -m src.main                              # Normal run (hardware required)
python -m src.main --dry-run                    # No hardware; simulate
python -m src.main --core-flow-only             # Sensor monitoring only; skip alert action
python -m src.main --test-alert                 # Full alert cycle immediately (bench test)
python -m src.main --test-alert --disable-sms-send  # Full alert without sending SMS
python -m src.main --test-alert --test-lat 14.299 --test-lon 121.060 --disable-sms-send  # Spoof GPS (e.g. Langkiwa)

# Routing / geofence (no hardware; needs shapely + libgeos-dev)
python -m src.routing_test                      # Quick inside/outside + recipient samples
python -m src.routing_accident_test --mode all --lat 14.2989841 --lon 121.0597082   # SMS preview per mode (not sent)
python -m src.routing_accident_test --mode geocode --lat 14.2989841 --lon 121.0597082
python -m src.routing_accident_test --mode polygon --lat 14.2989841 --lon 121.0597082
python -m src.routing_accident_test --mode centroid --lat 14.2989841 --lon 121.0597082
python -m src.routing_accident_test --mode coordinates --lat 14.2989841 --lon 121.0597082
python -m src.routing_accident_test --mode auto --lat 14.2989841 --lon 121.0597082
python -m src.routing_accident_test --no-sms-preview --mode auto --lat 14.3331 --lon 121.0854
python -m src.routing_matrix_test               # All 7 barangay centroids + outside + no GPS
python -m src.routing_matrix_test --sms-preview # Same + print SMS body per scenario

# Phone config transport
python -m src.ble_config_server --diagnose       # Check BLE/BlueZ GATT prerequisites
python -m src.ble_config_server                  # BLE GATT config server for the app
python -m src.bluetooth_config_server --channel 1  # Classic Bluetooth RFCOMM fallback/debug server

# Hardware diagnostics
python -m src.hardware_check                    # Full hardware probe (exit 1 on any FAIL)
python -m src.gsm_test                          # GSM: baud sweep, SIM, signal
python -m src.sms_config_check                     # Verify contacts.family.json + sample alert length
python -m src.sms_config_check --send-test +639XXXXXXXXX  # Check then send one production alert
python -m src.gsm_test --send-test-sms +639XXXXXXXXX  # Short "Test text" via alert send path
python -m src.gsm_test --send-alert-sms +639XXXXXXXXX   # Production-format alert (no [SSnn] tag)
python -m src.gsm_test --send-map-url-test +639XXXXXXXXX  # Bench: "Google Map: https://..." only
python -m src.gsm_test --send-map-url-test +639XXXXXXXXX --map-url-style google_search
python -m src.gsm_sms_matrix_test --list              # SMS delivery diagnostic cases
python -m src.gsm_sms_matrix_test --phone +639XXXXXXXXX --dry-run
python -m src.gsm_sms_matrix_test --phone +639XXXXXXXXX --confirm  # Sends [SS01]..[SS21] (12s apart)
python -m src.gsm_alert_test                    # GSM policy checks (no hardware)
python -m src.gps_test                          # GPS: NMEA stream, $GPGGA fixes
python -m src.mpu_collision_test                # MPU: tap/collision JSONL test

# Audio / MP3 (module reserved for future use)
python -m src.audio_test --track 1              # Play DFPlayer track 1
python -m src.mp3_diag                          # Full MP3-TF-16P bench diagnostic

# Buzzer
python -m src.buzzer_diag                       # Interactive polarity scan and GPIO sweep
python -m src.buzzer_silence                    # Immediately silence GPIO 18
python -m src.buzzer_silence --beep             # One beep then silence
python -m src.buzzer_silence --verify           # Print current GPIO state

# Microphone / voice cancel
python -m src.mic_test --baseline               # Measure ambient noise; suggests threshold values
python -m src.mic_test --keyword-test --keyword cancel  # Test production-style keyword cancel
python -m src.mic_test --sphinx-oneshot --keyword cancel # One-shot offline PocketSphinx check
python -m src.mic_stt_oneshot                   # One-shot Google STT fallback check
```

- **`--core-flow-only`**: init + sensor monitoring / threshold / validation; logs core-flow impact events and skips alert action.
- **`python -m src.hardware_check`**: one-shot I2C / GPIO / GSM (multi-baud AT + SIM/signal if OK) / GPS / MP3 probes. Exit code **1** if any line is **`[FAIL]`**, else **0**. **WARN / SKIP / FAIL / INFO** lines include indented **causes**; entries are appended to **`logs/hardware_check.log`** on the Pi.
- **`python -m src.gsm_test`**: deeper GSM bench (baud sweep, `AT+CPIN?`, `AT+CREG?`, `AT+CSQ`, `AT+COPS?`). Optional: `--send-test-sms PHONE` (short `"Test text"`), `--send-alert-sms PHONE`, or `--send-sms PHONE "message"`.
- **`python -m src.gps_test`**: auto-detect baud, stream NMEA for `--duration-sec` (default 30), print `$GPGGA` fixes.
- **`python -m src.audio_test --track 1`**: play DFPlayer track 1 (`mp3/0001.mp3` layout). Use `--probe-range N` to test multiple tracks.
- **`python -m src.mp3_diag`**: full **MP3-TF-16P** bench (reset 0x0C, TF select, volume, queries, `play_track`, optional `01/001` fallback). Same as `python -m src.audio_test --mp3tf16p-diag`.
- **`python -m src.mic_test --baseline`**: measures ambient mic noise; prints `Suggested VOICE_SOUND_RMS_THRESHOLD` and `Suggested VOICE_KEYWORD_MIN_RMS` — update `config.py` with those values.
- **`python -m src.mic_test --keyword-test --keyword cancel`**: uses the production keyword path: ambient calibration first, then keyword-only listening for `cancel`.
- **`python -m src.mic_test --sphinx-oneshot --keyword cancel`**: captures one phrase, prints what PocketSphinx heard, then checks whether the offline keyword mode matched `cancel`.
- **`python -m src.mic_stt_oneshot`**: quick end-to-end check for Google fallback speech recognition (verifies `flac` install, internet, mic, and transcription).
- **`python -m src.mpu_collision_test`**: isolated MPU tap/collision JSONL test (see `--help`).

---

## I2C (MPU-6050)

Enable once: `sudo raspi-config` → Interface Options → **I2C** → Enable → reboot.

```bash
ls /dev/i2c-1
sudo apt-get install -y i2c-tools
sudo i2cdetect -y 1
```

Expect address **`68`** for MPU-6050. If `/dev/i2c-1` is missing, I2C is off or Pi not rebooted.

---

## Serial / GPS vs GSM

Check what the OS exposes:

```bash
ls -l /dev/serial0 /dev/ttyS0 /dev/ttyAMA0 2>/dev/null
```

Typical: **`/dev/serial0` → `ttyS0`** (hardware UART on GPIO 14/15) — good for **SIM800L** when `src/config.py` has `SIM800L_UART_DEVICE = "/dev/serial0"`.

**Conflict:** **GSM** uses **`/dev/serial0`** (usually **`ttyS0`**). Do **not** point `GPS_SERIAL_PORT` to that same UART.  
For breadboard wiring, defaults are now:
- `GPS_SERIAL_PORT = None` → use **pigpio GPIO software UART** on GPS pins (RX GPIO20)
- `MP3_SERIAL_PORT = None` → use **pigpio GPIO software UART TX** on MP3 TX pin (GPIO19)
If you prefer USB adapters, set `GPS_SERIAL_PORT` / `MP3_SERIAL_PORT` to `/dev/ttyUSB*`.

Permissions:

```bash
groups
sudo usermod -aG gpio,dialout $USER
```

Log out and back in (or reboot) after `usermod`.

### If you still get `Permission denied` on `/dev/serial0`

`/dev/serial0` is usually a symlink to `/dev/ttyS0`. Check the **real** device:

```bash
ls -l /dev/serial0
readlink -f /dev/serial0
ls -l $(readlink -f /dev/serial0)
```

**Example — broken state (before fix):** only root can open `ttyS0` (mode **600**). Being in **`dialout`** does not help yet.

```text
lrwxrwxrwx 1 root root 5 ... /dev/serial0 -> ttyS0
/dev/ttyS0
crw------- 1 root root 4, 64 ... /dev/ttyS0
```

`python3 -c "import serial; ... Serial('/dev/serial0'...)"` may then fail with:

```text
PermissionError: [Errno 13] Permission denied: '/dev/serial0'
```

**Fix (persistent):** on the Pi, install a udev rule so `ttyS0` is **`root:dialout`** and mode **660** (run once):

```bash
echo 'SUBSYSTEM=="tty", KERNEL=="ttyS0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-ttyS0-dialout.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo reboot
```

After reboot, confirm (same commands as above):

```bash
ls -l /dev/serial0
readlink -f /dev/serial0
ls -l /dev/ttyS0
```

**Example — fixed state (after rule + reboot):** group **`dialout`**, mode **`crw-rw----`**:

```text
lrwxrwxrwx 1 root root 5 ... /dev/serial0 -> ttyS0
/dev/ttyS0
crw-rw---- 1 root dialout 4, 64 ... /dev/ttyS0
```

Exact major/minor (`4, 64`) and timestamps may differ; the important part is **`rw-rw----`**, **`root`**, **`dialout`**.

### If `/dev/ttyS0` is still `crw------- root root` after reboot

The rule file may not match your kernel/udev, or another rule may run later and reset permissions.

**1. Confirm the rule exists and reload:**

```bash
cat /etc/udev/rules.d/99-ttyS0-dialout.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
ls -l /dev/ttyS0
```

**2. See what udev knows about the device:**

```bash
udevadm info -q all -n /dev/ttyS0
```

**3. Try an alternative rule** (replace the file, reload, trigger, check again — reboot if needed):

```bash
echo 'KERNEL=="ttyS0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-ttyS0-dialout.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
ls -l /dev/ttyS0
```

If still `600`, try adding **`ACTION=="add"`** at the start of the line (some systems need it).

**4. Check for conflicting rules:**

```bash
grep -r ttyS0 /etc/udev/rules.d/ /lib/udev/rules.d/ 2>/dev/null
```

**5. Last-resort (until udev behaves):** after each boot, fix permissions once (not ideal for production):

```bash
sudo chmod 660 /dev/ttyS0
sudo chgrp dialout /dev/ttyS0
ls -l /dev/ttyS0
```

You can automate that with a small **`systemd` oneshot** or **`@reboot` cron** if you must — prefer fixing the udev rule long-term.

**Note:** On some Pi images the UART device is **`ttyAMA0`** instead of **`ttyS0`**. If `readlink -f /dev/serial0` shows **`/dev/ttyAMA0`**, duplicate the rule with `KERNEL=="ttyAMA0"` (or adjust the symlink target in `/boot/firmware/config.txt` / UART overlay docs).

**Non-root AT test** (should open without `PermissionError` once fixed):

```bash
python3 -c "import serial; s=serial.Serial('/dev/serial0',9600,timeout=1); s.write(b'AT\r\n'); print(s.read(200))"
```

**One-shot test as root** (confirms wiring vs permissions if non-root still fails):

```bash
sudo python3 -c "import serial; s=serial.Serial('/dev/serial0',9600,timeout=1); s.write(b'AT\r\n'); print(s.read(200))"
```

---

## Quick GSM (AT) sanity check

Module powered, ground common with Pi, TX/RX crossed correctly, baud **9600** in code:

```bash
python3 -c "import serial; s=serial.Serial('/dev/serial0',9600,timeout=1); s.write(b'AT\r\n'); print(s.read(200))"
```

You want **`OK`** in the response. If `serial0` opens but SmartShell shows **GSM NOT OPEN**, the code requires **`OK`** from `AT` during `open()` — fix power, wiring, or baud.

### pigpio service (required for GPIO software UART)

For GPS/MP3 on GPIO pins (no USB serial adapter), install and start `pigpiod`:

```bash
sudo apt-get update
sudo apt-get install -y pigpio python3-pigpio
sudo systemctl enable --now pigpiod
systemctl status pigpiod --no-pager
```

If `python -m src.hardware_check` says GPS/MP3 open failed in GPIO mode, check this service first.

---

## Troubleshoot GSM and GPS

Run a full report:

```bash
python -m src.hardware_check
```

### GSM (SIM800L on `/dev/serial0`)

| Symptom | What to check |
|--------|----------------|
| `Permission denied` | User in **`dialout`**, **`/dev/ttyS0`** is **`crw-rw---- root dialout`** (udev rule + `udevadm trigger` if needed). |
| Port opens, only see your own `AT\r\n` echo, no **`OK`** | **TX/RX swap**, **GND** common, **power** to module (buck + cap), not a **Pi TX–RX short** (loopback). |
| `Input/output error` on write | Supply sag, bad wiring, or UART/console conflict — **disable serial login** in `raspi-config`, reboot. |
| `OK` sometimes then fails | Typical **brownout** — improve SIM800L supply and wiring. |

### GPS

| Symptom | What to check |
|--------|----------------|
| **`GPS_SERIAL_PORT` is `None`** (default) | This is expected for breadboard mode — code uses **pigpio** software UART on GPS GPIO pins. Ensure `pigpiod` service is running. |
| Check says port missing | Wrong path — run `ls /dev/ttyUSB*` after plugging USB GPS. |
| Port opens, no NMEA in 2s | **Antenna**, sky view, **cold start** (wait longer), wrong baud (9600 in `config.py`), or GPS TX not reaching Pi RX. |

### MP3 (`MP3_SERIAL_PORT`)

| Symptom | What to check |
|--------|----------------|
| `MP3_SERIAL_PORT` is `None` (default) | Breadboard mode — code sends DFPlayer commands via **pigpio** on GPIO19. Ensure `pigpiod` service is running. |
| Want USB adapter instead | Set `MP3_SERIAL_PORT` to `/dev/ttyUSB*` and verify with `ls /dev/ttyUSB*`. |

---

## Boot service (optional)

See `deploy/smartshell.service.example` and **Start on boot (`systemd`)** in `README.md`.

### Buzzer silence service (recommended if buzzer wired)

GPIO 18 floats HIGH at boot, which turns on an active-high buzzer before Python starts. Install a oneshot service to silence it early:

```bash
sudo cp deploy/smartshell-buzzer-silence.service.example /etc/systemd/system/smartshell-buzzer-silence.service
sudo nano /etc/systemd/system/smartshell-buzzer-silence.service   # fix User / paths
sudo systemctl daemon-reload
sudo systemctl enable smartshell-buzzer-silence.service
sudo systemctl start smartshell-buzzer-silence.service
sudo systemctl status smartshell-buzzer-silence.service
```

Test manually:

```bash
python -m src.buzzer_silence            # drive GPIO 18 low (silent)
python -m src.buzzer_silence --verify   # print current GPIO state
```

---

## Related docs

- `README.md` — full setup
- `docs/hardware.md` — wiring
- `docs/software_state.md` — what each module expects
