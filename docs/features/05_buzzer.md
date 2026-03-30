# Feature: Buzzer (GPIO alert)

## Overview

**Phase 4 (planned):** the buzzer sounds when an SMS is received from the Barangay Rescue Center, alerting the rider that help has been notified.

**Phase 1 (now):** the prototype harness uses the same GPIO for a **transistor-driven buzzer**. A **floating GPIO** after power-up often leaves the buzzer **on continuously** until software drives the pin. SmartShell sets the **silent** level at normal startup (`src/buzzer_hw.py`). For a one-shot fix:

```bash
python -m src.main --silence-buzzer
```

If the buzzer still stays on, set `BUZZER_ACTIVE_HIGH = False` in `src/config.py` (inverted driver).

## Hardware

| Item | Value |
|------|-------|
| GPIO | 18 (BCM) |
| Wiring | 1kΩ resistor → NPN transistor base → buzzer |
| Power | 5V Buck (buzzer + side) |

## Module Interface

**Current:** `src/buzzer_hw.py` — `silence()` drives the line off.

**Future** (`docs/phase0_module_boundaries.md` — `buzzer`):

- `beep(duration_sec)` — Single blocking beep
- `beep_pattern(times, on_sec, off_sec)` — Alert pattern (e.g. 3 beeps)

## References

- `docs/PLAN.md`, `src/config.py` — `BUZZER_GPIO`, `BUZZER_ACTIVE_HIGH`
- `README.md` — buzzer at power-on, systemd (helmet autostart)
