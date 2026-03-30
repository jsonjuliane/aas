"""
Bench-only hardware probe: connections and basic responses.

Does not run accident detection, countdown, SMS, or routing logic.

Writes human-readable lines to logs/hardware_check.log for WARN/SKIP/FAIL (and session summary).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from src import audio_mp3, buzzer_hw, cancel, gps
from src.config import (
    CANCEL_BUTTON_GPIO,
    GPS_BAUD,
    GPS_RX_GPIO,
    GPS_SERIAL_PORT,
    LOGS_DIR,
    MPU6050_I2C_ADDR,
    MPU6050_I2C_BUS,
    MP3_BAUD,
    MP3_SERIAL_PORT,
    MP3_TX_GPIO,
    SIM800L_BAUD,
    SIM800L_UART_DEVICE,
)

# MPU-6050 WHO_AM_I register; expect 0x68
_MPU_WHO_AM_I = 0x75
_MPU_EXPECT_ID = 0x68

_LOG_NAME = "hardware_check.log"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _log_file_path() -> Path:
    root = _project_root()
    log_dir = root / LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / _LOG_NAME


def _append_log(tag: str, summary: str, detail: str | None = None) -> None:
    """Append one check result to logs/hardware_check.log."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    path = _log_file_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{ts} [{tag}] {summary}\n")
            if detail:
                for line in detail.strip().split("\n"):
                    f.write(f"{ts}      | {line}\n")
    except OSError:
        pass


def _emit(
    tag: str,
    summary: str,
    detail: str | None = None,
    *,
    log: bool = True,
) -> None:
    """Print to stdout; optional detail lines; log WARN/SKIP/FAIL/INFO for debugging."""
    print(f"[{tag:5}] {summary}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"       → {line}")
    if log and tag in ("WARN", "SKIP", "FAIL", "INFO"):
        _append_log(tag, summary, detail)


def run_hardware_check(dry_run: bool = False) -> int:
    """
    Print a structured report. Returns 0 always (informational).
    """
    print("SmartShell — hardware check (connections only, no alert logic)\n")

    if dry_run:
        _emit("SKIP", "dry-run: no I2C/GPIO/serial probes", "Run without --dry-run on the Pi for real probes.")
        return 0

    path = _log_file_path()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{ts} [----] === hardware-check session start ===\n")
    except OSError:
        pass

    # --- I2C device node ---
    i2c_dev = f"/dev/i2c-{MPU6050_I2C_BUS}"
    if os.path.exists(i2c_dev):
        print(f"[{'OK':5}] I2C device present: {i2c_dev}")
    else:
        _emit(
            "FAIL",
            f"I2C device missing: {i2c_dev}",
            "Enable I2C in raspi-config (Interface Options → I2C), reboot, verify with ls /dev/i2c-1.",
        )
        print()
        print(f"       Log: {path}")
        return 0

    # --- MPU-6050 WHO_AM_I ---
    try:
        import smbus2

        bus = smbus2.SMBus(MPU6050_I2C_BUS)
        try:
            chip_id = bus.read_byte_data(MPU6050_I2C_ADDR, _MPU_WHO_AM_I)
            if chip_id == _MPU_EXPECT_ID:
                print(
                    f"[{'OK':5}] MPU-6050 @ 0x{MPU6050_I2C_ADDR:02x} WHO_AM_I=0x{chip_id:02x}"
                )
            else:
                _emit(
                    "WARN",
                    f"Device @ 0x{MPU6050_I2C_ADDR:02x} WHO_AM_I=0x{chip_id:02x} (expected 0x{_MPU_EXPECT_ID:02x})",
                    "Wrong chip at I2C address, bad wiring, or sensor fault.",
                )
        finally:
            bus.close()
    except OSError as e:
        _emit(
            "FAIL",
            f"MPU-6050 I2C read failed: {e}",
            "Check SDA/SCL, pull-ups, 3.3 V, and i2cdetect -y 1.",
        )
    except ImportError:
        _emit("FAIL", "smbus2 not installed", "pip install smbus2 in your venv.")

    # --- Buzzer GPIO ---
    if buzzer_hw.silence():
        print(f"[{'OK':5}] Buzzer GPIO driven to silent level")
    else:
        _emit(
            "WARN",
            "Buzzer GPIO not set (not a Pi or RPi.GPIO error)",
            "Expected on non-Pi dev machines; on Pi, check gpio group and BUZZER_ACTIVE_HIGH.",
        )

    # --- Cancel button GPIO init ---
    try:
        cancel.init()
        print(f"[{'OK':5}] Cancel GPIO {CANCEL_BUTTON_GPIO} init OK (optional button)")
    except Exception as e:
        _emit("WARN", f"Cancel GPIO init failed: {e}", "Optional wiring; safe to ignore if no button.")

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
            _emit(
                "INFO",
                f"/dev/serial0 -> {target}",
                "GSM uses SIM800L_UART_DEVICE; same physical UART as this symlink target.",
                log=True,
            )
        except OSError:
            _emit("INFO", "/dev/serial0 exists (could not resolve)", log=True)

    print()
    print(f"[{'DONE':5}] End of hardware check (no monitoring loop started)")
    print(f"       → Debug log (WARN/SKIP/FAIL/INFO): {path}")
    ts_end = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{ts_end} [----] === hardware-check session end ===\n")
    except OSError:
        pass
    return 0


def _check_gsm_at() -> None:
    dev = SIM800L_UART_DEVICE
    try:
        import serial

        from src.gsm_sim800l import _send_at
    except ImportError:
        _emit("FAIL", "pyserial missing; cannot probe GSM", "pip install pyserial in your venv.")
        return

    if not os.path.exists(dev):
        _emit(
            "FAIL",
            f"GSM device missing: {dev}",
            "UART not enabled or wrong path; check ls -l /dev/serial0 and raspi-config serial.",
        )
        return

    ser = None
    try:
        ser = serial.Serial(dev, SIM800L_BAUD, timeout=0.5)
    except OSError as e:
        _emit(
            "FAIL",
            f"GSM serial open failed ({dev}): {e}",
            "Permission: user in dialout, /dev/ttyS0 group dialout mode 660. Or port busy.",
        )
        return

    try:
        resp = _send_at(ser, "AT", timeout=2.0)
        snippet = repr(resp[:160]) if len(resp) > 160 else repr(resp)
        if "OK" in resp:
            print(f"[{'OK':5}] GSM AT OK ({dev} @ {SIM800L_BAUD})")
        else:
            _emit(
                "WARN",
                f"GSM port open but no OK in AT response. Raw: {snippet}",
                "Common: TX/RX swap or floating; Pi TX/RX shorted (echo only). "
                "Power/GND to SIM800L, 100 µF at VCC, common ground. "
                "If only your bytes echo back, module is not replying AT.",
            )
    except OSError as e:
        _emit(
            "FAIL",
            f"GSM AT I/O error: {e}",
            "Kernel EIO: brownout, bad wiring, or UART driver state — reboot after fixing supply.",
        )
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


def _check_gps_serial() -> None:
    gps_mod = gps.GPSModule(dry_run=False)
    gps_mod.open()
    try:
        using_port = GPS_SERIAL_PORT if GPS_SERIAL_PORT else f"GPIO soft UART RX{GPS_RX_GPIO}"
        if gps_mod._ser is None and gps_mod._pi is None:
            _emit(
                "FAIL",
                f"GPS open failed ({using_port})",
                "If using GPIO mode, install pigpio and start pigpiod. "
                "If using /dev/tty*, check device path and permissions.",
            )
            return
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            line = gps_mod.read_nmea_line()
            if line and line.startswith("$"):
                sample = line[:60]
                print(f"[{'OK':5}] GPS NMEA-like data on {using_port}: {sample!r}…")
                return
            time.sleep(0.05)
        _emit(
            "WARN",
            f"GPS opened ({using_port}) but no NMEA starting with $ within 2s",
            "Antenna outdoors, cold start (wait longer), wrong baud in config, "
            "or GPS TX not connected to Pi RX.",
        )
    finally:
        gps_mod.close()


def _check_mp3_serial() -> None:
    mp3_mod = audio_mp3.AudioMP3(dry_run=False)
    mp3_mod.open()
    try:
        using = MP3_SERIAL_PORT if MP3_SERIAL_PORT else f"GPIO soft UART TX{MP3_TX_GPIO}"
        if mp3_mod._ser is None and mp3_mod._pi is None:
            _emit(
                "FAIL",
                f"MP3 open failed ({using})",
                "If using GPIO mode, install pigpio and start pigpiod. "
                "If using /dev/tty*, check device path and permissions.",
            )
            return
        print(f"[{'OK':5}] MP3 transport ready ({using} @ {MP3_BAUD})")
    finally:
        mp3_mod.close()
