# Phase 1 — Implementation Guide

This document describes the Phase 1 codebase and how to run it.

---

## Module Map

| Module | File | Purpose |
|--------|------|---------|
| Sensor | `src/sensor_mpu6050.py` | MPU-6050 read, calibrate, `is_impact_detected()` |
| GPS | `src/gps.py` | NMEA parse, `get_fix()` |
| GSM | `src/gsm_sim800l.py` | SIM800L `send_sms()` |
| Audio | `src/audio_mp3.py` | DFPlayer `play_track()` |
| Cancel | `src/cancel.py` | GPIO button `wait_for_cancel()` |
| Contacts | `src/contacts.py` | Load family contacts, format message |
| Logging | `src/logging_store.py` | `log_event()` |
| Main | `src/main.py` | Entry point, main loop |
| Buzzer GPIO | `src/buzzer_hw.py` | Silence at startup; `python -m src.buzzer_test --silence-only`; `python -m src.buzzer_test` (ON then OFF) |

---

## Run Modes

| Mode | Command | Use case |
|------|---------|----------|
| Normal | `python -m src.main` | Pi with hardware |
| Dry run | `python -m src.main --dry-run` | Development without hardware |
| Hardware check | `python -m src.hardware_check` | One-shot I2C/GPIO/GSM/GPS/MP3 readiness check |
| Test alert | `python -m src.main --test-alert` | One full alert cycle immediately (bench) |
| Silence buzzer | `python -m src.buzzer_test --silence-only` | Drive GPIO off, exit (stuck buzzer at boot) |
| Buzzer bench test | `python -m src.buzzer_test` | Buzzer ON briefly then OFF (`--duration-sec` for duration) |
| MPU isolated test | `python -m src.mpu_collision_test` | Tap/collision test; JSONL defaults to events + summary (`--log-all-samples` for verbose) |

Legacy `--trigger` is accepted as an alias for `--test-alert`.

---

## Boot autostart

See `deploy/smartshell.service.example` and **Start on boot (`systemd`)** in `README.md`.

---

## Config

- **contacts**: Copy `config/contacts.family.json.example` → `config/contacts.family.json`
- **Serial / GPIO UART**: Edit `src/config.py` — `SIM800L_UART_DEVICE` stays `/dev/serial0`; `GPS_SERIAL_PORT=None` and `MP3_SERIAL_PORT=None` use pigpio GPIO software UART in current breadboard setup

---

## Thonny

1. Open project folder in Thonny.
2. Open `src/main.py`.
3. Run (F5). Use `--dry-run` for development without hardware.
