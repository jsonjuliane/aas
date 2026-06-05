# SmartShell — Smart Helmet Accident Alert System

SmartShell is a Raspberry Pi Zero W–based smart helmet that detects probable accidents and sends SMS alerts with GPS location, with a short cancellation window to prevent false alarms.

For the phased plan, see `docs/PLAN.md`. **Prototype hardware** (BOM, pins, power): `docs/hardware.md`. **What the code does vs that hardware**: `docs/software_state.md`. **Pi terminal commands** (venv, I2C, serial checks, run modes): `docs/pi_commands.md`.

---

## Hardware integration guide (Raspberry Pi Zero W)

### Modules (as specified)

- **Raspberry Pi Zero W** (main controller)
- **MPU-6050** (accelerometer/gyroscope via I2C)
- **SIM800L** (GSM/SMS via hardware UART)
- **GPS module** (UART via GPIO 20/21 software serial as currently planned)
- **MP3 player module** (UART via GPIO 19/26 software serial as currently planned)
- **Power**: 2×18650 (series) + charging board/BMS + buck converters (5V and ~4V) + LDO 3.3V for GPS (per wiring spec)

### Wiring

| Pi Physical Pin | BCM | Function | Module | Wire to |
|---|---|---|---|---|
| 1 | — | 3.3V | MPU-6050 | VCC |
| 2 | — | 5V | 5V buck output | +5V |
| 3 | 2 | SDA1 | MPU-6050 | SDA |
| 5 | 3 | SCL1 | MPU-6050 | SCL |
| 6 | — | GND | 5V buck output | GND |
| 8 | 14 | UART TXD0 | SIM800L | RXD |
| 9 | — | GND | SIM800L | GND |
| 10 | 15 | UART RXD0 | SIM800L | TXD |
| 11 | 17 | GPIO | Cancel button | Other leg to GND |
| 13 | 27 | GPIO | Buzzer I/O | Active-high; VCC to 5V rail |
| 14 | — | GND | MPU-6050 | GND |
| 30 | — | GND | MP3 player | GND |
| 35 | 19 | GPIO | MP3 player | TX (Pi → module RX) |
| 37 | 26 | GPIO | MP3 player | RX (via 1kΩ) |
| 34 | — | GND | GPS | GND |
| 38 | 20 | GPIO | GPS | RX (Pi ← GPS TX) |
| 40 | 21 | GPIO | GPS | TX (Pi → GPS RX) |

**Important**: Use a **star ground** (common ground) across battery (-), both bucks, Pi ground, and all modules.

### Power notes (critical)

- **SIM800L** draws high current bursts; ensure:
  - A dedicated ~4V supply (buck converter) as planned
  - A **100µF capacitor** close to SIM800L VCC/GND
  - Solid wiring and shared ground with the Pi
- GPS supply per plan uses an LDO 3.3V with capacitors (0.1µF on VIN, 10µF on VOUT).

---

## Raspberry Pi OS configuration checklist

### 1) Enable I2C (MPU-6050)

- Enable I2C using `raspi-config` (Interface Options → I2C → Enable).
- Reboot.
- Verify the device is present (typical address `0x68`):

```bash
sudo apt-get update
sudo apt-get install -y i2c-tools
sudo i2cdetect -y 1
```

### 2) Enable serial for SIM800L (hardware UART)

You want UART enabled for the SIM800L, and you must **disable the serial login shell**.

- In `raspi-config`:
  - Interface Options → Serial
  - Disable login shell over serial
  - Enable serial hardware
- Reboot.

Typical device path is `/dev/serial0` (preferred) or `/dev/ttyAMA0` depending on Pi OS and overlays.

### 3) Countdown audio (DFPlayer + speaker)

The prototype uses an **MP3 player module** (e.g. DFPlayer Mini) on **UART** (GPIO 19/26 per wiring table), driving a **small speaker** — not the Pi’s HDMI or USB audio.

- On the DFPlayer SD card, use folder **`mp3/`** with files **`0001.mp3`**, **`0002.mp3`**, … (see `src/config.py` `MP3_DEFAULT_TRACK` and `src/audio_mp3.py`).
- Keep `MP3_SERIAL_PORT=None` in `src/config.py` for GPIO soft-serial wiring (GPIO 19/26).  
  If you move MP3 to USB-TTL, set `MP3_SERIAL_PORT` to the matching `/dev/ttyUSB*`.

---

## Software prerequisites (when you start implementing)

This repo already includes `requirements.txt`. Expect additional system packages on Raspberry Pi OS.

### Likely OS packages you’ll need

- `python3-venv`, `python3-pip`
- `portaudio` development headers — needed by `pyaudio` (voice cancel / mic test)
- `pigpio` — GPIO software UART for GPS/MP3 on breadboard GPIO pins
- `flac` — needed by Google Speech-to-Text (voice keyword cancel)
- `libgeos-dev` — GEOS C library for `shapely` (Biñan geofence / `routing_test`)

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip portaudio19-dev pigpio python3-pigpio flac libgeos-dev
sudo systemctl enable --now pigpiod
```

### Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Run in Thonny (Windows → Raspberry Pi)

Follow these steps to clone on Windows, transfer to the Pi, and run in Thonny with hardware.

### 1. Clone on Windows

1. Install [Git for Windows](https://git-scm.com/download/win) if needed.
2. Open **Command Prompt** or **PowerShell**.
3. Navigate to the folder where you want the project (e.g. `cd C:\Users\YourName\Documents`).
4. Clone the repo:
   ```cmd
   git clone https://github.com/YOUR_USERNAME/AccidentAlertSystem.git
   cd AccidentAlertSystem
   ```

### 2. Transfer to the Raspberry Pi

Copy the `AccidentAlertSystem` folder to the Pi. Options:

- **USB drive**: Copy the folder to a USB stick, plug into the Pi, copy to the Pi (e.g. `~/AccidentAlertSystem`).
- **Network share**: If the Pi is on the same network, use Samba/Windows share or `scp` from WSL.
- **Clone directly on Pi**: If the Pi has internet, open Terminal on the Pi and run the same `git clone` command there. Skip step 1.

### 3. Configure Raspberry Pi OS (one-time)

On the Pi, complete `docs/phase0_os_checklist.md`:

- Enable I2C (raspi-config → Interface Options → I2C).
- Enable serial for SIM800L (raspi-config → Serial → disable login shell, enable hardware).
- Reboot after each change.

### 4. Install dependencies on the Pi

Open **Terminal** on the Pi:

```bash
cd ~/AccidentAlertSystem
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `RPi.GPIO` or `pyaudio` fail to build, install system packages first:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip portaudio19-dev
```

### 5. Set up contacts config

```bash
cp config/contacts.family.json.example config/contacts.family.json
```

Edit `config/contacts.family.json` and add real emergency phone numbers (E.164 format, e.g. `+639171234567`).

### 6. Run in Thonny on the Pi

1. Open **Thonny** on the Raspberry Pi (Menu → Programming → Thonny).
2. **File → Open** → browse to `AccidentAlertSystem/src/main.py`.
3. **Run → Configure interpreter** → ensure **Raspberry Pi** or **Python 3** is selected.  
   - If using the venv: **Tools → Options → Interpreter** → choose **Alternative Python 3** → browse to `AccidentAlertSystem/.venv/bin/python3`.
4. Press **F5** or **Run** to start.

The app monitors the sensor. On validated impact (3–5g + tilt), it starts a 10-second countdown with buzzer beeps, allows cancellation (GPIO button or voice "cancel"), then attempts GPS fix + GSM SMS alert, and exits.

### Run from Terminal

From Terminal (with venv activated):

```bash
python -m src.main                               # Normal (with hardware)
python -m src.main --dry-run                     # Simulate without hardware
python -m src.main --test-alert                  # Full alert cycle immediately (bench test)
python -m src.main --test-alert --disable-sms-send  # Alert without sending SMS
python -m src.main --core-flow-only              # Sensor monitoring only; no alert action
python -m src.hardware_check                     # One-shot hardware probe (exit 1 if any FAIL)
python -m src.gsm_test                           # GSM: multi-baud AT, SIM, registration, signal
python -m src.gps_test                           # GPS: auto baud, NMEA stream, $GPGGA fixes
python -m src.audio_test --track 1               # Play DFPlayer track 1 (mp3/0001.mp3 layout)
python -m src.mp3_diag                           # Full MP3-TF-16P diagnostic (reset, play, queries)
python -m src.mic_test --baseline                # Measure ambient noise; suggest RMS thresholds
python -m src.mic_test --keyword-test --keyword cancel  # Test Google STT keyword detection
python -m src.mic_stt_oneshot                    # One-shot STT check (flac, internet, mic)
python -m src.buzzer_diag                        # Buzzer polarity scan and GPIO sweep
python -m src.buzzer_silence                     # Silence buzzer GPIO immediately
python -m src.mpu_collision_test                 # Isolated MPU tap/collision test (JSONL)
```

`--trigger` still works as a hidden alias for `--test-alert` (same behavior).

---

## Start on boot (`systemd`)

Thonny and manual `python -m src.main` are for development. On the helmet, use **systemd** so SmartShell **starts when the Pi boots** and **restarts after a crash**.

### Main app service

1. Copy the example unit and **edit** `User`, `WorkingDirectory`, and `ExecStart` to match your Pi username and project path:

   ```bash
   sudo cp deploy/smartshell.service.example /etc/systemd/system/smartshell.service
   sudo nano /etc/systemd/system/smartshell.service
   ```

2. Ensure the service user is in **`gpio`** and **`dialout`** (serial):  
   `sudo usermod -aG gpio,dialout $USER` then log out and back in.

3. Enable and start:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now smartshell.service
   sudo systemctl status smartshell.service
   ```

4. Follow logs: `journalctl -u smartshell.service -f`

### Buzzer silence service (required if buzzer is wired)

GPIO 27 floats HIGH at boot, turning on the buzzer before Python starts. Install a oneshot service that runs earlier:

```bash
sudo cp deploy/smartshell-buzzer-silence.service.example \
        /etc/systemd/system/smartshell-buzzer-silence.service
sudo nano /etc/systemd/system/smartshell-buzzer-silence.service   # fix User / paths
sudo systemctl daemon-reload
sudo systemctl enable smartshell-buzzer-silence.service
sudo systemctl start smartshell-buzzer-silence.service
sudo systemctl status smartshell-buzzer-silence.service
```

Full product hardening (watchdogs, incoming-SMS responder loop) stays in later phases; see `docs/PLAN.md`.

---

## What’s in this repo today

- `src/main.py` — runnable entrypoint (Phase 1): impact detection → countdown → cancel window → GPS + SMS
- `src/voice_cancel.py` — background Google STT keyword cancel (“cancel” to abort countdown)
- `src/buzzer_hw.py` — countdown tick beeps on GPIO 27
- `src/buzzer_silence.py` — boot-time GPIO 27 silence script
- `src/cancel.py` — GPIO 17 cancel button
- `deploy/smartshell.service.example` — `systemd` unit for main app boot autostart
- `deploy/smartshell-buzzer-silence.service.example` — `systemd` oneshot for buzzer silence at boot
- `docs/PLAN.md` — phased plan and wiring
- `docs/hardware.md` — prototype BOM, pins, power (matches physical build)
- `docs/software_state.md` — module map, serial/GPS notes, Phase 2+ gaps
- `docs/features/` — per-feature documentation (buzzer, voice cancel, cancel mechanism, etc.)

