# Feature: Cancel Mechanism

## Overview

During the **10-second countdown**, the rider can cancel the alert to prevent a false alarm using either:

1. **GPIO button** (physical cancel) — GPIO 17, active-low
2. **Voice keyword** ("cancel") — Google STT via USB microphone; requires internet

If neither cancels within the window, the system proceeds to send SMS.  
After the alert cycle completes (send or cancel), the process exits.

---

## Hardware — Button

| Item | Value |
|------|-------|
| GPIO | 17 (configurable via `CANCEL_BUTTON_GPIO`) |
| Wiring | Momentary switch between GPIO 17 and GND (internal pull-up enabled) |

---

## Hardware — Voice Keyword

| Item | Value |
|------|-------|
| Mic | USB Audio Device (e.g. USB dongle mic) |
| Keyword | "cancel" (configurable via `--voice-cancel-keyword`) |
| Requires | Internet connection for Google STT; `flac` system package |

---

## Module Interface

**Button** (`src/cancel.py`):

- `init()` — Setup GPIO with pull-up. Call once at startup.
- `wait_for_cancel(timeout_sec, dry_run)` — Blocks; returns True if button pressed before timeout.

**Voice** (`src/voice_cancel.py`):

- `open_keyword_session(device_index, keyword)` — Opens mic, calibrates ambient noise, returns a session.
- `start_background_keyword_listen(session)` — Launches background STT thread.
- `close_keyword_session(session)` — Stops listener and releases mic.

---

## Flow

1. Impact detected → countdown starts (10 seconds)
2. In parallel: GPIO button poll + voice keyword background listener
3. If button pressed or "cancel" heard → alert cancelled, process exits
4. If timeout → proceed to GPS fix + SMS send, then process exits

---

## Bench tests

```bash
# Measure ambient mic noise and get suggested config thresholds
python -m src.mic_test --baseline

# Test "cancel" keyword detection (15-second window)
python -m src.mic_test --keyword-test --keyword cancel

# One-shot Google STT check (flac + internet + mic)
python -m src.mic_stt_oneshot
```

---

## Config (`src/config.py`)

| Constant | Default | Purpose |
|----------|---------|---------|
| `CANCEL_BUTTON_GPIO` | `17` | BCM GPIO for cancel button |
| `COUNTDOWN_SECONDS` | `10` | Alert cancel window duration |
| `VOICE_CANCEL_KEYWORD_ENABLED` | `True` | Enable Google STT keyword cancel |
| `VOICE_CANCEL_SOUND_ENABLED` | `False` | Enable RMS-level cancel (louder than threshold) |
| `VOICE_KEYWORD_MIN_RMS` | `6500` | Minimum RMS to attempt STT (skip quiet frames) |
| `VOICE_KEYWORD_PHRASE_SEC` | `2.0` | Max seconds per utterance |
| `VOICE_AMBIENT_CALIBRATION_SEC` | `1.0` | Ambient noise calibration time |

---

## References

- `docs/PLAN.md` — False Detection Flow
- `docs/features/09_voice_cancel.md` — Voice cancel deep-dive
- `src/config.py` — `CANCEL_BUTTON_GPIO`, `COUNTDOWN_SECONDS`, `VOICE_*`
