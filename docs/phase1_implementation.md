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
| Buzzer GPIO | `src/buzzer_hw.py` | Silence buzzer line at startup; `--silence-buzzer` |

---

## Run Modes

| Mode | Command | Use case |
|------|---------|----------|
| Normal | `python -m src.main` | Pi with hardware |
| Dry run | `python -m src.main --dry-run` | Development without hardware |
| Test alert | `python -m src.main --test-alert` | One full alert cycle immediately (bench) |
| Silence buzzer | `python -m src.main --silence-buzzer` | Drive GPIO off, exit (stuck buzzer at boot) |

Legacy `--trigger` is accepted as an alias for `--test-alert`.

---

## Boot autostart

See `deploy/smartshell.service.example` and **Start on boot (`systemd`)** in `README.md`.

---

## Config

- **contacts**: Copy `config/contacts.family.json.example` → `config/contacts.family.json`
- **Serial ports**: Edit `src/config.py` — `GPS_SERIAL_PORT`, `MP3_SERIAL_PORT` (only one can use `/dev/ttyS0` at a time)

---

## Thonny

1. Open project folder in Thonny.
2. Open `src/main.py`.
3. Run (F5). Use `--dry-run` for development without hardware.
