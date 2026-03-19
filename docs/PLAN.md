# SmartShell — Smart Helmet Accident Alert System (Phased Plan)

The intent is to reach a **working base model first**, then iteratively improve reliability, usability, and safety.

---

## Product goal (from poster)

Build an IoT-based smart helmet system that:
- Detects probable accidents using acceleration + orientation sensing
- Plays a short voice countdown and allows **voice cancel** to prevent false alarms
- Sends SMS alerts containing GPS location to designated contacts
- Provides a way for responders (Barangay rescue center) to message back, triggering a buzzer

---

## Functional requirements (baseline)

1. **Accident detection**: Detect sudden impacts using MPU-6050 (acceleration + rotation/orientation).
2. **Countdown**: Start a **5-second** alert countdown with pre-recorded audio.
3. **Cancel**: Listen for voice command “cancel” during the 5 seconds; if heard, stop alert and resume monitoring.
4. **If not cancelled**: Obtain GPS coordinates and send SMS alerts via SIM800L.
5. **Location routing**: If location is inside Biñan, Laguna → alert **Family + Barangay**; if outside → **Family only**.
6. **Incoming SMS buzzer**: Any incoming text from Barangay rescue center triggers buzzer.
7. **Logging**: Store event data (timestamp, trigger values, location, routing decision).

---

## System flow

### A. Accident detected

- **Initialization**: power on; calibrate sensors; initialize GPS + GSM
- **Monitoring**: continuously read motion data; apply multi-sensor logic
- **Threshold**: acceleration spike (e.g., \( \ge 3g\)–\(5g\)) flags potential accident
- **Validation**: confirm using both acceleration spike + abnormal tilt/orientation
- **Countdown**: play voice alert, start 5-second timer
- **Cancel window**: listen for “cancel”; if none, proceed
- **Send alert**: SMS to registered contacts including GPS coordinates
- **Log event**
- **Buzzer**: sounds when any text is received from Barangay rescue center

### B. False detection (cancelled)

- Trigger threshold from bump/drop/sudden motion → countdown starts → user says “cancel” → recognition succeeds → stop countdown → no SMS → resume monitoring

---

## Hardware + wiring

### Main modules

- **Raspberry Pi Zero W**: main controller (Python)
- **MPU-6050**: accident detection (I2C)
- **GPS module**: coordinates (software serial on GPIO 20/21)
- **SIM800L**: SMS alerts (hardware UART)
- **MP3 player**: pre-recorded countdown audio (software serial on GPIO 19/26)
- **Buzzer**: incoming SMS alert (GPIO 18 via transistor)

### Raspberry Pi Zero W pin mapping (current spec)

| Physical Pin | Function | Component | Connection |
|--------------|----------|-----------|------------|
| Pin 1 | 3.3V Out | MPU-6050 | VCC |
| Pin 2 | 5V In | 5V Buck | Output (+) |
| Pin 3 | I2C SDA | MPU-6050 | SDA |
| Pin 5 | I2C SCL | MPU-6050 | SCL |
| Pin 6 | GND | 5V Buck | Output (-) |
| Pin 8 | UART TX | SIM800L | RXD (hardware serial) |
| Pin 9 | GND | SIM800L | Signal GND |
| Pin 10 | UART RX | SIM800L | TXD (hardware serial) |
| Pin 12 | GPIO 18 | Buzzer | 1kΩ → transistor base |
| Pin 14 | GND | MPU-6050 | GND |
| Pin 30 | GND | MP3 Player | GND |
| Pin 35 | GPIO 19 | MP3 Player | TX (software serial) |
| Pin 37 | GPIO 26 | MP3 Player | RX (via 1kΩ resistor) |
| Pin 34 | GND | GPS Module | GND |
| Pin 38 | GPIO 20 | GPS Module | TX (software serial) |
| Pin 40 | GPIO 21 | GPS Module | RX (software serial) |

**UART usage**: SIM800L uses hardware UART (Pins 8/10). GPS + MP3 use software serial lines on GPIOs as specified.

### Power & regulation (current spec)

- **2x 18650 series** → charging board/BMS
- **Main switch** between battery (+) and buck inputs
- **Buck 1 (5V)** → Pi pin 2 (+), MP3 VCC, buzzer (+)
- **Buck 2 (4V)** → SIM800L VCC with **100µF capacitor**
- **LDO (3.3V)** from 5V buck → GPS VCC with **0.1µF (VIN) + 10µF (VOUT) capacitors**
- **Star ground**: battery (-), all buck inputs (-), all modules’ grounds

---

## Repository readiness check (current state)

Right now the repo is **not yet “set up” as a runnable application**:
- `requirements.txt` exists
- `src/` exists but contains only `src/__init__.py`
- There is no `src/main.py` or runnable entrypoint, no configuration templates, and no deployment instructions yet
- A local `.venv/` is present in the repo directory (good for local dev, but should be excluded from version control if you later initialize git)

This plan defines what to add in stages to become a working software base.

---

## Phased delivery plan

### Phase 0 — Definition + environment baseline (no features yet)

**Goal**: lock requirements + interfaces so development is predictable and testable.

- **Deliverables** ✓
  - Finalized module boundaries → `docs/phase0_module_boundaries.md`
  - Config format → `docs/phase0_config_format.md`, `config/*.example`
  - Pi OS checklist → `docs/phase0_os_checklist.md`
  - Per-feature docs → `docs/features/*.md`
  - Pin constants → `src/config.py`

- **Exit criteria**
  - Everyone agrees on pinout + routing rules (Biñan vs outside)
  - Pinout and routing rules agreed

---

### Phase 1 — Working base model (minimum functioning end-to-end) ✓

**Goal**: a reliable loop that detects a trigger, counts down, and can send an SMS with GPS.

- **Deliverables** ✓
  - `src/main.py` runnable in Thonny
  - `src/sensor_mpu6050.py`, `gps.py`, `gsm_sim800l.py`, `audio_mp3.py`, `cancel.py`, `contacts.py`, `logging_store.py`
  - `config/contacts.family.json.example` — copy to `contacts.family.json`
  - `assets/audio/` — countdown audio (see README)
  - `docs/phase1_implementation.md` — run guide

- **Phase outcome (what you can run in Thonny on the Pi)**
  - A single runnable entrypoint script (e.g., `src/main.py`) that you can open in **Thonny on the Raspberry Pi** and press **Run**.
  - It runs end-to-end with real hardware (or with “dry run” flags if a module is disconnected).

- **Scope**
  - MPU-6050 reading + calibration and basic detection (accel + tilt validation)
  - MP3 playback of a fixed pre-recorded countdown prompt
  - **Cancel mechanism (base)**: start with **a GPIO button fallback** (recommended for helmets) while keeping an interface for later voice cancel
  - GPS parsing to obtain coordinates
  - SIM800L: send SMS to **family contacts** with GPS coordinates
  - Event logging to file

- **Deliverables**
  - `src/main.py` runnable in Thonny (Pi)
  - `config/contacts.family.json` (phone numbers + message template variables)
  - `assets/audio/` countdown audio file(s)
  - Minimal “bring-up” scripts (can also be run in Thonny) to test each peripheral independently:
    - MPU-6050 read/calibration test
    - GPS NMEA read/parse test
    - SIM800L AT + SMS send test
    - MP3 play test
    - Buzzer GPIO test
  - “How to run on Pi with Thonny” section completed (below)

- **Not in scope (deferred)**
  - Barangay routing by geofence
  - Voice cancel in real helmet conditions
  - Incoming SMS parsing + buzzer rules beyond “any SMS triggers”

- **Exit criteria (demo)**
  - Simulated impact (or controlled “trigger mode”) reliably starts countdown
  - Cancel within 5 seconds prevents SMS every time
  - No cancel sends SMS with valid coordinates (or “no fix” fallback message) every time
  - Log file records event metadata for each run

---

### Phase 2 — Location-aware routing (Biñan geofence + barangay contacts)

**Goal**: match your requirement: inside Biñan → Family + Barangay; outside → Family only.

- **Phase outcome (still runnable in Thonny)**
  - Same `src/main.py` remains runnable from Thonny on the Pi, now with routing logic enabled.

- **Scope**
  - Geofencing for “inside Biñan, Laguna” (polygon boundary or equivalent)
  - Routing logic for alert recipients based on location
  - Barangay lookup: GPS → barangay → rescuer contact (data-driven mapping file)
  - Message templates (include location + routing info)

- **Deliverables**
  - `config/contacts.barangay.json` (barangay → rescuer numbers)
  - `config/geofence.binan.json` (or equivalent boundary file)
  - Routing tests with known coordinates (inside/outside + no-fix behavior)

- **Exit criteria**
  - With test coordinates, routing chooses correct recipients in all cases:
    - inside Biñan
    - outside Biñan
    - GPS unavailable (fallback behavior documented)

---

## How you will run it on the Raspberry Pi using Thonny (Phases 1–2)

Once Phase 1 is implemented, running is intentionally simple:

1. Open the project folder on the Pi.
2. Open `src/main.py` in Thonny.
3. Select the Pi’s Python interpreter (default in Thonny on Raspberry Pi OS).
4. Press **Run**.

**Notes**
- If dependencies are missing, install them on the Pi using:
  - Thonny: Tools → Manage packages… (install items from `requirements.txt`)
  - or Terminal: `python3 -m pip install -r requirements.txt`
- Hardware interfaces (I2C/UART/audio) must be enabled in Raspberry Pi OS per `README.md`.

### Phase 3 — Voice cancellation (usable in helmet conditions)

**Goal**: implement “cancel” voice command robustly under noise/wind.

- **Options to evaluate**
  - Offline keyword spotting (preferred) vs cloud speech recognition (less reliable without internet)
  - Microphone placement + noise suppression strategy

- **Scope**
  - Voice command pipeline and tuning
  - A/B testing against button fallback
  - Safety: define confidence thresholds and require repetition if needed (e.g., “cancel cancel”)

- **Exit criteria**
  - Voice cancel succeeds under realistic riding/helmet noise in controlled tests
  - False positives (random “cancel”) below agreed threshold

---

### Phase 4 — Responder loop + robustness hardening

**Goal**: reliable long-running device behavior and responder feedback loop.

- **Scope**
  - Incoming SMS monitoring from Barangay rescue center; buzzer signaling rules
  - Process supervision (auto-start on boot, auto-restart on crash)
  - Watchdogs for GPS/GSM health, backoff/retry strategies
  - Power resilience (brownouts, SIM800L current spikes)
  - Data retention policy for logs

- **Exit criteria**
  - Runs unattended for extended periods (e.g., hours) without manual intervention
  - Survives module resets / intermittent GPS / GSM hiccups gracefully

---

## Proposed (future) repo structure

When you start implementation, keep it simple and Pi-friendly:

```
AccidentAlertSystem/
├── docs/
│   └── PLAN.md
├── src/
│   ├── main.py
│   ├── config.py
│   ├── sensor_mpu6050.py
│   ├── gps.py
│   ├── gsm_sim800l.py
│   ├── audio_mp3.py
│   ├── cancel.py
│   ├── routing.py
│   ├── buzzer.py
│   └── logging_store.py
├── config/
│   ├── contacts.family.json
│   └── contacts.barangay.json
├── assets/
│   └── audio/
└── requirements.txt
```

---

## Key risks / constraints (Pi Zero W + helmet context)

- **Voice in a helmet** is hard: wind + engine noise causes missed cancels and false positives.
- **SIM800L power spikes**: needs proper supply + capacitors and common ground to avoid random resets.
- **GPS cold start**: first fix may be slow; define clear fallback behavior (send “no fix yet”).
- **Software serial on Pi** can be fragile under load; keep CPU usage low and avoid heavy DSP.

---

## Acceptance tests (what “working” means)

- **Accident trigger**: controlled test causes countdown reliably, without random triggers at rest.
- **Cancel**: cancel within 5 seconds reliably stops the alert sequence.
- **Alert**: no cancel sends SMS with:
  - timestamp
  - coordinates (or explicit “GPS not available”)
  - routing decision (family only vs family+barangay once Phase 2 is complete)
- **Incoming SMS**: any SMS from rescue center triggers buzzer (and is logged).
