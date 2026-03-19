# Phase 0 — Module Boundaries and Interfaces

This document defines the module boundaries and public interfaces for the SmartShell system. Each module has a single responsibility and a well-defined API.

---

## 1. sensor_mpu6050

**Responsibility**: Read MPU-6050 data and detect potential accident (acceleration + orientation).

| Function / Method | Signature | Returns | Notes |
|------------------|-----------|---------|-------|
| `calibrate()` | `() -> None` | — | Run at startup; establish baseline |
| `read_raw()` | `() -> dict` | `{ax, ay, az, gx, gy, gz}` | Raw values |
| `read_g()` | `() -> tuple[float, float, float]` | `(ax_g, ay_g, az_g)` | Acceleration in g |
| `is_impact_detected()` | `() -> bool` | True if threshold exceeded | Uses accel + tilt validation |

**Dependencies**: `smbus2`, `src.config`

---

## 2. gps

**Responsibility**: Obtain current GPS coordinates via software serial.

| Function / Method | Signature | Returns | Notes |
|------------------|-----------|---------|-------|
| `open()` | `() -> None` | — | Open serial; call before use |
| `close()` | `() -> None` | — | Release serial |
| `get_fix()` | `() -> dict \| None` | `{lat, lon, alt?, timestamp?}` or None | None if no fix |
| `read_nmea_line()` | `() -> str \| None` | Raw NMEA line | Low-level; for debugging |

**Dependencies**: `serial`, `src.config`

---

## 3. gsm_sim800l

**Responsibility**: Send SMS via SIM800L (hardware UART).

| Function / Method | Signature | Returns | Notes |
|------------------|-----------|---------|-------|
| `open()` | `() -> None` | — | Open UART; init module |
| `close()` | `() -> None` | — | Release UART |
| `send_sms(phone: str, text: str)` | `(str, str) -> bool` | True if sent | AT+CMGS |
| `check_signal()` | `() -> int` | 0–31 (CSQ) | Optional health check |

**Dependencies**: `serial`, `src.config`

---

## 4. audio_mp3

**Responsibility**: Play pre-recorded countdown audio via MP3 module.

| Function / Method | Signature | Returns | Notes |
|------------------|-----------|---------|-------|
| `open()` | `() -> None` | — | Open serial to MP3 module |
| `close()` | `() -> None` | — | Release serial |
| `play_track(track_num: int)` | `(int) -> None` | — | 1-based track index |
| `stop()` | `() -> None` | — | Stop playback |

**Dependencies**: `serial`, `src.config`

---

## 5. buzzer

**Responsibility**: Sound buzzer (e.g. on incoming SMS from rescue center).

| Function / Method | Signature | Returns | Notes |
|------------------|-----------|---------|-------|
| `beep(duration_sec: float)` | `(float) -> None` | — | Blocking beep |
| `beep_pattern(times: int, on_sec: float, off_sec: float)` | `(int, float, float) -> None` | — | Alert pattern |

**Dependencies**: `RPi.GPIO` (or equivalent), `src.config`

---

## 6. cancel

**Responsibility**: Detect user cancellation during countdown (button or voice).

| Function / Method | Signature | Returns | Notes |
|------------------|-----------|---------|-------|
| `wait_for_cancel(timeout_sec: float)` | `(float) -> bool` | True if cancelled | Blocks; polls button / listens for voice |
| `init()` | `() -> None` | — | Setup GPIO / mic |

**Dependencies**: `src.config`; optionally `RPi.GPIO`, `SpeechRecognition`

---

## 7. routing

**Responsibility**: Determine alert recipients from GPS (Phase 2).

| Function / Method | Signature | Returns | Notes |
|------------------|-----------|---------|-------|
| `get_recipients(lat: float \| None, lon: float \| None)` | `(float?, float?) -> list[str]` | Phone numbers | Family + barangay if inside Biñan |
| `load_config()` | `() -> None` | — | Load contacts + geofence |

**Dependencies**: `shapely`, `src.config`, config JSON files

---

## 8. logging_store

**Responsibility**: Persist event data (time, acceleration, location, routing).

| Function / Method | Signature | Returns | Notes |
|------------------|-----------|---------|-------|
| `log_event(data: dict)` | `(dict) -> None` | — | Append to log file |
| `get_log_path()` | `() -> str` | Path to current log | For debugging |

**Dependencies**: `src.config`, filesystem

---

## Data Flow (High Level)

```
sensor_mpu6050.is_impact_detected()
    → audio_mp3.play_track() + cancel.wait_for_cancel()
    → if not cancelled: gps.get_fix() → routing.get_recipients() → gsm_sim800l.send_sms()
    → logging_store.log_event()
```
