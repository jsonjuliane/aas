# SmartShell — Prototype hardware

This document matches the **physical prototype** (breadboard / harness): Raspberry Pi Zero W with GSM, IMU, GPS, MP3 + speaker, buzzer, and battery-backed DC rails.

---

## Bill of materials (as built)

| Item | Role |
|------|------|
| **Raspberry Pi Zero W** | Main computer; runs Python; Wi‑Fi / Bluetooth |
| **MPU-6050** (blue breakout) | Accelerometer + gyro — accident / motion detection (I2C) |
| **GSM module** (e.g. SIM800L-class) | SMS over cellular; external antenna |
| **GPS module** + **patch/ceramic antenna** | NMEA position (UART to Pi) |
| **MP3 player module** (e.g. DFPlayer Mini) + **speaker** | Pre-recorded countdown / prompts (UART); **not** the Pi’s HDMI audio |
| **Buzzer** | Alert tone (GPIO, typically via transistor + resistor) |
| **DC–DC converters** (“buck” modules) | 5 V for Pi / MP3 / buzzer rail; ~4 V for GSM; optional 3.3 V LDO branch for GPS per design |
| **2× 18650** + **holder** + **charge/BMS** (if present) | Main battery power |

---

## Pi Zero W — user-facing connectors

- **Mini HDMI** — monitor (video only; Pi still needs separate USB power).
- **microSD** — Raspberry Pi OS and project files.
- **PWR IN** micro USB — **power only** (use for 5 V supply during bench test).
- **USB** micro USB (OTG) — keyboard / hub with **USB OTG adapter** (not the power port).

---

## GPIO / wiring (software expects this mapping)

Same as `README.md` / `src/config.py`:

| Phys pin | BCM | Signal | Module |
|---------|-----|--------|--------|
| 1 | — | 3.3 V | MPU-6050 VCC |
| 2 | — | 5 V in | From 5 V buck |
| 3 | 2 | SDA | MPU-6050 |
| 5 | 3 | SCL | MPU-6050 |
| 6 | — | GND | Common ground |
| 8 | 14 | TXD0 | SIM800L RXD |
| 9 | — | GND | SIM800L |
| 10 | 15 | RXD0 | SIM800L TXD |
| 12 | 18 | GPIO | Buzzer (via driver) |
| 14 | — | GND | MPU-6050 |
| 30 | — | GND | MP3 GND |
| 35 | 19 | GPIO | MP3 TX (Pi → module RX) |
| 37 | 26 | GPIO | MP3 RX (Pi ← module TX, 1 kΩ as per schematic) |
| 34 | — | GND | GPS GND |
| 38 | 20 | GPIO | GPS RX (Pi ← module TX) |
| 40 | 21 | GPIO | GPS TX (Pi → module RX) |

**Power:** Star ground; **100 µF** (or as designed) at SIM800L; GPS supply per LDO notes in `README.md`.

**Buzzer at power-on:** Until the Pi drives **GPIO 18**, the pin may **float** and hold an NPN transistor **on**, so the buzzer can sound continuously. SmartShell calls `buzzer_hw.silence()` at startup; you can also run `python -m src.buzzer_test --silence-only`. If it stays on, try `BUZZER_ACTIVE_HIGH = False` in `src/config.py` (inverted driver).

---

## Do we need both GPS and GSM?

**Yes** for the full product: GPS for coordinates in the SMS, GSM to send the SMS. They are already used **one after the other in software** (`main.py`: after countdown, **get GPS fix**, then **send SMS**). That **time order** does not remove a **hardware** rule:

- **SIM800L** is on the Pi’s **hardware UART** (GPIO **14/15** → usually **`/dev/serial0` → `/dev/ttyS0`**).
- **GPS** on the breadboard is on **GPIO 20/21** — **different pins** than the SIM800L UART. It is **not** the same wire as `ttyS0`, so you must **not** point `GPS_SERIAL_PORT` at `/dev/ttyS0` unless your **physical** GPS is actually on that UART (it usually is not on this harness).

So you **do** use both modules; the limit was **mis-configuring GPS as `ttyS0`**, which is already the GSM UART. **Alternating “open GPS then open GSM” on the same `/dev/ttyS0`** only works if **one** device is electrically on those pins — you cannot attach **both** SIM800L and GPS to the **same** TX/RX pair without extra hardware (mux). Your schematic uses **separate** pins for GPS vs GSM, so the fix is **correct serial backend per pin group** (hardware UART for GSM; GPIO UART / USB GPS for GPS — see code roadmap), not toggling one `/dev` between two wired modules on different GPIOs.

---

## MP3 / DFPlayer and “USB-TTL”

- **DFPlayer Mini** is controlled by a **serial UART** (9600 baud), **not** by Pi HDMI/USB audio. The **speaker** plugs into the **DFPlayer’s** audio output, **not** into the Pi’s 3.5 mm or USB sound.

- A **USB-TTL adapter** (also **USB–serial**, FTDI/CP2102/CH340 dongle) is **not** a microphone. It is a **small USB device**: one end **USB into the Pi**, the other end **TX / RX / GND** wires to **DFPlayer RX / TX / GND** so Linux exposes something like **`/dev/ttyUSB0`**. That matches what `MP3_SERIAL_PORT` expects when you use **`/dev/ttyUSB0`**.

- If you **do not** have a USB-TTL dongle, you can still wire DFPlayer to **GPIO 19/26** on the breadboard, but the **current** Python code expects a **`/dev/tty*`** for `audio_mp3` — GPIO bit-bang on 19/26 would need extra code (e.g. pigpio) or a different wiring strategy. Until then, set **`MP3_SERIAL_PORT = None`** and **`python -m src.hardware_check`** will **SKIP** MP3 serial (not a “missing microphone”).

---

## Software serial note

GPS and MP3 use **GPIO UART** in the wiring plan. The current Python code opens **kernel serial devices** (`/dev/serial0`, `/dev/ttyUSB*`) where applicable. If your image maps a hardware UART to GPS, set `GPS_SERIAL_PORT` in `src/config.py`. For true GPIO UART on 20/21 without a `/dev/tty*`, a lower-level driver (e.g. pigpio) would be needed — document any change on the prototype.

---

## Related docs

- `README.md` — integration, Pi OS checklist, Thonny steps  
- `docs/PLAN.md` — phases and requirements  
- `docs/software_state.md` — what `src/` implements vs this hardware  
