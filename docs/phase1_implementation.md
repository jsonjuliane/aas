# Phase 1 — Implementation Guide

This document describes the Phase 1 codebase and how to run it.

---

## Module Map

| Module | File | Purpose |
|--------|------|---------|
| Sensor | `src/sensor_mpu6050.py` | MPU-6050 read, calibrate, `evaluate_impact()` |
| GPS | `src/gps.py` | NMEA parse, `get_fix()` |
| GSM | `src/gsm_sim800l.py` | SIM800L `send_sms_detailed()` with retry logic |
| Audio | `src/audio_mp3.py` | DFPlayer `play_track()` (reserved for future use) |
| Cancel (button) | `src/cancel.py` | GPIO button `wait_for_cancel()` — GPIO 17, active-low |
| Cancel (voice) | `src/voice_cancel.py` | Background keyword listener ("cancel"); Vosk offline first, PocketSphinx fallback, Google fallback |
| Buzzer | `src/buzzer_hw.py` | Countdown tick beeps on GPIO 27 |
| Contacts | `src/contacts.py` | Load family contacts, format message |
| Logging | `src/logging_store.py` | `log_event()` |
| Main | `src/main.py` | Entry point, main loop |

---

## Run Modes

| Mode | Command | Use case |
|------|---------|----------|
| Normal | `python -m src.main` | Pi with hardware |
| Dry run | `python -m src.main --dry-run` | Development without hardware |
| Core flow only | `python -m src.main --core-flow-only` | Init + sensor monitoring; skip alert action path |
| Test alert | `python -m src.main --test-alert` | Trigger action path immediately (countdown + SMS then exit) |
| No SMS send | `python -m src.main --test-alert --disable-sms-send` | Full alert path without actually sending SMS |
| Hardware check | `python -m src.hardware_check` | One-shot I2C/GPIO/GSM/GPS/MP3 readiness check (exit 1 on FAIL) |
| GSM isolated test | `python -m src.gsm_test` | Multi-baud AT, SIM/registration/signal; optional `--send-sms` |
| GPS isolated test | `python -m src.gps_test` | Auto baud, NMEA stream, `$GPGGA` fixes (`--duration-sec`) |
| Audio bench test | `python -m src.audio_test --track 1` | Play DFPlayer track 1; use `--probe-range N` to find audible tracks |
| MPU isolated test | `python -m src.mpu_collision_test` | Tap/collision test; JSONL defaults to events + summary (`--log-all-samples` for verbose) |
| Mic baseline | `python -m src.mic_test --baseline` | Measure ambient noise; output suggested RMS threshold values |
| Mic keyword test | `python -m src.mic_test --keyword-test --keyword cancel` | Test keyword detection (prints engine) |
| STT one-shot | `python -m src.mic_stt_oneshot` | Verify flac, internet, mic, transcription end-to-end |
| Buzzer diagnostics | `python -m src.buzzer_diag` | Interactive buzzer polarity scan and GPIO sweep |
| Buzzer silence | `python -m src.buzzer_silence` | Immediately silence buzzer GPIO (also run by boot service) |

Legacy `--trigger` is accepted as an alias for `--test-alert`.

`src.main` also supports debounce tuning: `--post-alert-cooldown-sec` and `--impact-log-cooldown-sec`.

---

## Boot autostart

1. **Main app**: `deploy/smartshell.service.example` — see **Start on boot (`systemd`)** in `README.md`.
2. **Buzzer silence**: `deploy/smartshell-buzzer-silence.service.example` — runs before the main app to drive GPIO 27 LOW at boot. See `docs/features/05_buzzer.md`.

---

## Config

- **contacts**: Copy `config/contacts.family.json.example` → `config/contacts.family.json`
- **Serial / GPIO UART**: Edit `src/config.py` — `SIM800L_UART_DEVICE` stays `/dev/serial0`; `GPS_SERIAL_PORT=None` and `MP3_SERIAL_PORT=None` use pigpio GPIO software UART in current breadboard setup
- **Voice cancel thresholds**: Run `python -m src.mic_test --baseline` and update `VOICE_KEYWORD_MIN_RMS` / `VOICE_SOUND_RMS_THRESHOLD` in `config.py` with the suggested values

---

## Thonny

1. Open project folder in Thonny.
2. Open `src/main.py`.
3. Run (F5). Use `--dry-run` for development without hardware.
