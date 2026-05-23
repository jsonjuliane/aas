# Feature: Buzzer Countdown

## Overview

An **active-high piezo buzzer** wired to GPIO 18 provides audible countdown cues during the alert window. Each second of the 10-second countdown fires one beep; the final 3 seconds use a slightly longer beep to signal urgency.

The buzzer can be used alongside or instead of MP3 audio — it requires no serial module or SD card.

---

## Hardware

| Item | Value |
|------|-------|
| GPIO | 18 (configurable via `BUZZER_GPIO`) — Pi physical pin 12 |
| Buzzer type | Active-high (sounds at HIGH, silent at LOW) |
| VCC | 5 V rail |
| GND | Common ground |

**Wiring:**  
- Buzzer VCC → 5 V rail  
- Buzzer I/O → GPIO 18 (Pin 12)  
- Buzzer GND → common GND

---

## Boot-time silencing

GPIO 18 floats HIGH at boot before any Python code runs, which would turn on the buzzer. A dedicated oneshot service drives it LOW before the main app starts:

```bash
# Install and enable the boot-silence service
sudo cp deploy/smartshell-buzzer-silence.service.example \
        /etc/systemd/system/smartshell-buzzer-silence.service
sudo nano /etc/systemd/system/smartshell-buzzer-silence.service   # fix User / paths
sudo systemctl daemon-reload
sudo systemctl enable smartshell-buzzer-silence.service
```

Test manually before enabling:

```bash
python -m src.buzzer_silence
```

---

## Module Interface (`src/buzzer_hw.py`)

Each function does its own GPIO setup, drives the pin, then calls `GPIO.cleanup(pin)` — this ensures the pin is released after each operation and stays silent between beeps.

| Function | Purpose |
|----------|---------|
| `silence()` | Drive pin to silent level and cleanup |
| `beep(duration_sec)` | One beep: ON → sleep → OFF → cleanup |
| `countdown_tick_beep(seconds_remaining)` | Short beep for sec > 3; longer for final 3 seconds |
| `monitoring_ready_beeps()` | Triple quick beep when monitoring starts or resumes after alert |

---

## Config (`src/config.py`)

| Constant | Default | Purpose |
|----------|---------|---------|
| `BUZZER_GPIO` | `18` | BCM GPIO for buzzer |
| `BUZZER_ACTIVE_HIGH` | `True` | Buzzer sounds at HIGH (confirmed via `buzzer_diag`) |
| `BUZZER_COUNTDOWN_ENABLED` | `True` | Enable tick beeps during countdown |
| `BUZZER_BEEP_SEC` | `0.08` | Beep duration for seconds > 3 |
| `BUZZER_FINAL_BEEP_SEC` | `0.16` | Beep duration for final 3 seconds |
| `BUZZER_MONITOR_READY_ENABLED` | `True` | Triple beep on monitoring start/resume |
| `BUZZER_MONITOR_READY_COUNT` | `3` | Number of ready beeps |
| `BUZZER_MONITOR_READY_BEEP_SEC` | `0.06` | Each ready beep length |
| `BUZZER_MONITOR_READY_GAP_SEC` | `0.10` | Pause between ready beeps |

---

## Bench test

```bash
# Interactive polarity scan + GPIO sweep
python -m src.buzzer_diag

# Immediately silence (test the boot-silence logic)
python -m src.buzzer_silence

# One beep then silence
python -m src.buzzer_silence --beep
```

---

## References

- `src/buzzer_hw.py` — countdown beep functions
- `src/buzzer_silence.py` — boot-time silence script
- `deploy/smartshell-buzzer-silence.service.example` — systemd oneshot
- `src/config.py` — `BUZZER_*` constants
