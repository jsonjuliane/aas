# Feature: GPS Location

## Overview

The GPS module provides real-time coordinates for inclusion in SMS alerts. Uses software serial on GPIO 20/21: Pin 38 (GPIO 20) = RX, Pin 40 (GPIO 21) = TX.

## Hardware

| Item | Value |
|------|-------|
| Interface | UART (software serial) |
| Pi Pins | Pin 38 = GPIO 20 (Pi RX ← GPS TX); Pin 40 = GPIO 21 (Pi TX → GPS RX); GND = Pin 34 |
| Baud | 9600 |
| Protocol | NMEA (e.g. $GPGGA, $GPRMC) |

## Software Serial Note

Raspberry Pi does not expose GPIO as standard serial ports. Production implementation requires either:

- Bit-banging UART on GPIO (e.g. via `pigpio` or custom code), or
- Using a USB-GPS or secondary hardware UART for bench testing

## Module Interface

See `docs/phase0_module_boundaries.md` — `gps`:

- `open()` / `close()` — Serial lifecycle
- `get_fix()` — Returns `{lat, lon}` or None if no fix

## Implementation (Phase 1)

- **File**: `src/gps.py`
- **Class**: `GPSModule(port=None, dry_run=False)`
- **Usage**: `gps.open()`; `fix = gps.get_fix(timeout_sec=5.0)`; returns `{lat, lon}` or None.
- **Config**: `GPS_SERIAL_PORT` in `src/config.py` (e.g. **`None`** on breadboard GPIO-only; **`/dev/ttyUSB0`** for USB GPS).

## References

- NMEA 0183 specification
- `docs/PLAN.md`, `src/config.py` — `GPS_TX_GPIO`, `GPS_RX_GPIO`, `GPS_BAUD`
