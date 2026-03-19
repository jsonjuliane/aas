# SmartShell — Smart Helmet Accident Alert System

SmartShell is a Raspberry Pi Zero W–based smart helmet that detects probable accidents and sends SMS alerts with GPS location, with a short cancellation window to prevent false alarms.

For the phased plan, see `docs/PLAN.md`.

---

## Hardware integration guide (Raspberry Pi Zero W)

### Modules (as specified)

- **Raspberry Pi Zero W** (main controller)
- **MPU-6050** (accelerometer/gyroscope via I2C)
- **SIM800L** (GSM/SMS via hardware UART)
- **GPS module** (UART via GPIO 20/21 software serial as currently planned)
- **MP3 player module** (UART via GPIO 19/26 software serial as currently planned)
- **Buzzer + transistor + 1kΩ resistor** (GPIO 18)
- **Power**: 2×18650 (series) + charging board/BMS + buck converters (5V and ~4V) + LDO 3.3V for GPS (per wiring spec)

### Wiring

| Pi Physical Pin | Function | Module | Wire to |
|---|---|---|---|
| 1 | 3.3V | MPU-6050 | VCC |
| 2 | 5V | 5V buck output | +5V |
| 3 | SDA1 | MPU-6050 | SDA |
| 5 | SCL1 | MPU-6050 | SCL |
| 6 | GND | 5V buck output | GND |
| 8 | UART TXD0 | SIM800L | RXD |
| 9 | GND | SIM800L | GND |
| 10 | UART RXD0 | SIM800L | TXD |
| 12 | GPIO18 | buzzer driver | 1kΩ → transistor base |
| 14 | GND | MPU-6050 | GND |
| 30 | GND | MP3 player | GND |
| 35 | GPIO19 | MP3 player | TX |
| 37 | GPIO26 | MP3 player | RX (via 1kΩ) |
| 34 | GND | GPS | GND |
| 38 | GPIO20 | GPS | TX |
| 40 | GPIO21 | GPS | RX |

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

### 3) Audio output (for MP3 countdown)

Decide how you will output audio from the Pi:
- HDMI audio (not typical in helmets)
- USB sound card
- I2S DAC / amplifier

For helmet builds, a small USB sound card or I2S DAC is often simplest. Confirm you can play a WAV/MP3 from the Pi before integrating the rest.

---

## Software prerequisites (when you start implementing)

This repo already includes `requirements.txt`. Expect additional system packages on Raspberry Pi OS.

### Likely OS packages you’ll need

- `python3-venv`, `python3-pip`
- `portaudio` development headers if you use `pyaudio` (voice cancel)

Example (may vary by OS version):

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip portaudio19-dev
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

The app will monitor the sensor. On impact, it runs a 5-second countdown; press the cancel button (GPIO 17) to abort, or let it send SMS with GPS location.

### Run from Terminal

From Terminal (with venv activated):

```bash
python -m src.main              # Normal (with hardware)
python -m src.main --dry-run     # Simulate without hardware
python -m src.main --trigger     # Force alert on first poll (for testing)
```

---

## Deployment recommendation (Phase 4)

For a helmet device, plan to run the program as a `systemd` service so it:
- starts on boot
- restarts on crash
- logs cleanly

This is intentionally deferred until Phase 4 in `docs/PLAN.md`, but you can prepare for it early.

---

## What’s in this repo today

- `src/main.py`: runnable entrypoint (Phase 1)
- `docs/PLAN.md`: phased plan and wiring
- `docs/features/`: per-feature documentation

