"""
Bench-only hardware probe: connections and basic responses.

Does not run accident detection, countdown, SMS, or routing logic.
"""

from __future__ import annotations

import os
import time

from src import buzzer_hw, cancel
from src.config import (
    CANCEL_BUTTON_GPIO,
    GPS_BAUD,
    GPS_SERIAL_PORT,
    MPU6050_I2C_ADDR,
    MPU6050_I2C_BUS,
    MP3_BAUD,
    MP3_SERIAL_PORT,
    SIM800L_BAUD,
    SIM800L_UART_DEVICE,
)

# MPU-6050 WHO_AM_I register; expect 0x68
_MPU_WHO_AM_I = 0x75
_MPU_EXPECT_ID = 0x68


def _line(tag: str, msg: str) -> None:
    print(f"[{tag:5}] {msg}")


def run_hardware_check(dry_run: bool = False) -> int:
    """
    Print a structured report. Returns 0 always (informational).
    """
    print("SmartShell — hardware check (connections only, no alert logic)\n")

    if dry_run:
        _line("SKIP", "dry-run: no I2C/GPIO/serial probes")
        return 0

    # --- I2C device node ---
    i2c_dev = f"/dev/i2c-{MPU6050_I2C_BUS}"
    if os.path.exists(i2c_dev):
        _line("OK", f"I2C device present: {i2c_dev}")
    else:
        _line("FAIL", f"I2C device missing: {i2c_dev} (enable I2C in raspi-config)")
        print()
        return 0

    # --- MPU-6050 WHO_AM_I ---
    try:
        import smbus2

        bus = smbus2.SMBus(MPU6050_I2C_BUS)
        try:
            chip_id = bus.read_byte_data(MPU6050_I2C_ADDR, _MPU_WHO_AM_I)
            if chip_id == _MPU_EXPECT_ID:
                _line("OK", f"MPU-6050 @ 0x{MPU6050_I2C_ADDR:02x} WHO_AM_I=0x{chip_id:02x}")
            else:
                _line(
                    "WARN",
                    f"Device @ 0x{MPU6050_I2C_ADDR:02x} WHO_AM_I=0x{chip_id:02x} (expected 0x{_MPU_EXPECT_ID:02x})",
                )
        finally:
            bus.close()
    except OSError as e:
        _line("FAIL", f"MPU-6050 I2C read failed: {e}")
    except ImportError:
        _line("FAIL", "smbus2 not installed")

    # --- Buzzer GPIO ---
    if buzzer_hw.silence():
        _line("OK", "Buzzer GPIO driven to silent level")
    else:
        _line("WARN", "Buzzer GPIO not set (not a Pi or RPi.GPIO error)")

    # --- Cancel button GPIO init ---
    try:
        cancel.init()
        _line("OK", f"Cancel GPIO {CANCEL_BUTTON_GPIO} init OK (optional button)")
    except Exception as e:
        _line("WARN", f"Cancel GPIO init: {e}")

    # --- GSM: open + AT ---
    _check_gsm_at()

    # --- GPS serial ---
    _check_gps_serial()

    # --- MP3 serial ---
    _check_mp3_serial()

    # --- /dev/serial0 target (info) ---
    if os.path.exists("/dev/serial0"):
        try:
            target = os.path.realpath("/dev/serial0")
            _line("INFO", f"/dev/serial0 -> {target}")
        except OSError:
            _line("INFO", "/dev/serial0 exists (could not resolve)")

    print()
    _line("DONE", "End of hardware check (no monitoring loop started)")
    return 0


def _check_gsm_at() -> None:
    dev = SIM800L_UART_DEVICE
    try:
        import serial

        from src.gsm_sim800l import _send_at
    except ImportError:
        _line("FAIL", "pyserial missing; cannot probe GSM")
        return

    if not os.path.exists(dev):
        _line("FAIL", f"GSM device missing: {dev}")
        return

    ser = None
    try:
        ser = serial.Serial(dev, SIM800L_BAUD, timeout=0.5)
    except OSError as e:
        _line("FAIL", f"GSM serial open failed ({dev}): {e}")
        return

    try:
        resp = _send_at(ser, "AT", timeout=2.0)
        snippet = repr(resp[:120]) if len(resp) > 120 else repr(resp)
        if "OK" in resp:
            _line("OK", f"GSM AT OK ({dev} @ {SIM800L_BAUD})")
        else:
            _line(
                "WARN",
                f"GSM port open but no OK in AT response (check power/TX/RX). Raw: {snippet}",
            )
    except OSError as e:
        _line("FAIL", f"GSM AT I/O error: {e}")
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


def _check_gps_serial() -> None:
    port = GPS_SERIAL_PORT
    if not port:
        _line("SKIP", "GPS: GPS_SERIAL_PORT not set in config.py")
        return
    if not os.path.exists(port):
        _line("FAIL", f"GPS serial device missing: {port}")
        return

    try:
        import serial
    except ImportError:
        _line("FAIL", "pyserial missing; cannot probe GPS")
        return

    try:
        ser = serial.Serial(port, GPS_BAUD, timeout=0.3)
    except OSError as e:
        _line("FAIL", f"GPS serial open failed ({port}): {e}")
        return

    try:
        deadline = time.monotonic() + 2.0
        got = ""
        while time.monotonic() < deadline:
            if ser.in_waiting:
                chunk = ser.read(ser.in_waiting).decode("ascii", errors="replace")
                got += chunk
                if "$" in got:
                    line = [x for x in got.split("\n") if x.strip().startswith("$")]
                    sample = line[0][:60] if line else got[:60]
                    _line("OK", f"GPS NMEA-like data on {port}: {sample!r}…")
                    return
            time.sleep(0.05)
        _line(
            "WARN",
            f"GPS port opened ({port}) but no NMEA in 2s (antenna/sky/fix or wrong port)",
        )
    finally:
        try:
            ser.close()
        except Exception:
            pass


def _check_mp3_serial() -> None:
    port = MP3_SERIAL_PORT
    if not port:
        _line("SKIP", "MP3: MP3_SERIAL_PORT not set in config.py")
        return
    if not os.path.exists(port):
        _line("FAIL", f"MP3 serial device missing: {port}")
        return

    try:
        import serial
    except ImportError:
        _line("FAIL", "pyserial missing; cannot probe MP3")
        return

    try:
        ser = serial.Serial(port, MP3_BAUD, timeout=0.3)
        ser.close()
        _line("OK", f"MP3 serial port opened ({port} @ {MP3_BAUD}) — DFPlayer not commanded")
    except OSError as e:
        _line("FAIL", f"MP3 serial open failed ({port}): {e}")
