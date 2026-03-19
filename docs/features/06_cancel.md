# Feature: Cancel Mechanism

## Overview

During the 5-second countdown, the rider can cancel the alert to prevent a false alarm. Phase 1 uses a **GPIO button**; Phase 3 adds **voice command** ("cancel").

## Hardware (Phase 1 — Button)

| Item | Value |
|------|-------|
| GPIO | 17 (configurable) |
| Wiring | Button between GPIO and GND (internal pull-up) |

## Module Interface

See `docs/phase0_module_boundaries.md` — `cancel`:

- `init()` — Setup GPIO / microphone
- `wait_for_cancel(timeout_sec)` — Blocks; returns True if cancel detected

## Flow

1. Impact detected → countdown starts
2. `wait_for_cancel(5.0)` runs
3. If True → stop alert, resume monitoring
4. If False (timeout) → proceed to send SMS

## Phase 3 (Voice)

- Microphone + speech recognition
- Keyword: "cancel"
- Consider offline keyword spotting for reliability in helmet (wind, noise)

## Implementation (Phase 1)

- **File**: `src/cancel.py`
- **Functions**: `init()` at startup; `wait_for_cancel(timeout_sec, dry_run)` blocks until button or timeout.
- **GPIO**: `CANCEL_BUTTON_GPIO` (default 17) in `src/config.py`.

## References

- `docs/PLAN.md` — False Detection Flow
- `src/config.py` — `CANCEL_BUTTON_GPIO`, `COUNTDOWN_SECONDS`
