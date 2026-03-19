# Feature: Buzzer (Incoming SMS Alert)

## Overview

The buzzer sounds when an SMS is received from the Barangay Rescue Center, alerting the rider that help has been notified.

## Hardware

| Item | Value |
|------|-------|
| GPIO | 18 (BCM) |
| Wiring | 1kΩ resistor → NPN transistor base → buzzer |
| Power | 5V Buck (buzzer + side) |

## Module Interface

See `docs/phase0_module_boundaries.md` — `buzzer`:

- `beep(duration_sec)` — Single blocking beep
- `beep_pattern(times, on_sec, off_sec)` — Alert pattern (e.g. 3 beeps)

## References

- `docs/PLAN.md`, `src/config.py` — `BUZZER_GPIO`
