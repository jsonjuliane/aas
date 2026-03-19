# SmartShell — Smart Helmet Accident Alert System

This repository currently contains **planning + hardware wiring specifications** for a Raspberry Pi Zero W–based smart helmet that can detect probable accidents and send SMS alerts with GPS location, with a short cancellation window to prevent false alarms.

For the phased development plan, see `docs/PLAN.md`.

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

### Wiring (from `docs/Connections.xlsx`)

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

## Deployment recommendation (when you have runnable code)

For a helmet device, plan to run the program as a `systemd` service so it:
- starts on boot
- restarts on crash
- logs cleanly

This is intentionally deferred until Phase 4 in `docs/PLAN.md`, but you can prepare for it early.

---

## What’s in this repo today

- `docs/PLAN.md`: phased plan aligned to your flow + wiring specs
- `docs/Flow.docx`, `docs/Connections.xlsx`, `docs/smartshell.jpg`: source documentation
- `requirements.txt`: initial Python dependency list (no application code yet)

