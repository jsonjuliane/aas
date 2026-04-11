"""
Bench-only hardware probe: connections and basic responses.

Does not run accident detection, countdown, SMS, or routing logic.

Writes human-readable lines to logs/hardware_check.log for WARN/SKIP/FAIL (and session summary).
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from src import audio_mp3, buzzer_hw, cancel
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
    PROJECT_ROOT,
    SIM800L_BAUD,
    SIM800L_UART_DEVICE,
)

# MPU-6050 WHO_AM_I register; expect 0x68
_MPU_WHO_AM_I = 0x75
_MPU_EXPECT_ID = 0x68

_LOG_NAME = "hardware_check.log"

# Incremented on each [FAIL] line (for exit code).
_hardware_check_failures = 0


def _log_file_path() -> Path:
    root = PROJECT_ROOT
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
    global _hardware_check_failures
    print(f"[{tag:5}] {summary}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"       → {line}")
    if tag == "FAIL":
        _hardware_check_failures += 1
    if log and tag in ("WARN", "SKIP", "FAIL", "INFO"):
        _append_log(tag, summary, detail)


def run_hardware_check(dry_run: bool = False) -> int:
    """
    Print a structured report.

    Returns:
        0 if no FAIL lines; 1 if any check reported FAIL (I2C, pyserial, probes, etc.).
    """
    global _hardware_check_failures
    _hardware_check_failures = 0
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
        return 1 if _hardware_check_failures else 0

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
    return 1 if _hardware_check_failures else 0


def _gsm_baud_candidates() -> list[int]:
    out: list[int] = []
    for b in (SIM800L_BAUD, 9600, 38400, 115200):
        bi = int(b)
        if bi not in out:
            out.append(bi)
    return out


def _check_gsm_at() -> None:
    dev = SIM800L_UART_DEVICE
    try:
        import serial

        from src.gsm_sim800l import send_at
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
    working_baud: int | None = None
    last_snippet = ""

    for baud in _gsm_baud_candidates():
        try:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
            ser = serial.Serial(dev, baud, timeout=0.5)
            resp = send_at(ser, "AT", timeout=2.0)
            last_snippet = repr(resp[:160]) if len(resp) > 160 else repr(resp)
            if "OK" in resp:
                working_baud = baud
                break
        except OSError:
            continue

    if ser is None or working_baud is None:
        _emit(
            "WARN",
            f"GSM no OK to AT across bauds {_gsm_baud_candidates()}. Last raw: {last_snippet}",
            "TX/RX crossed to Pi pins 8/10; power 2A+ peaks; 470–1000µF at module VCC; common GND; VDD 3.3V if required.",
        )
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        return

    try:
        print(f"[{'OK':5}] GSM AT OK ({dev} @ {working_baud})")
        send_at(ser, "ATE0", timeout=1.0)
        pin_r = send_at(ser, "AT+CPIN?", timeout=2.0)
        pin_line = pin_r.replace("\r", " ").strip().split("\n")[-1][:100]
        print(f"[{'OK':5}] GSM SIM: {pin_line}")
        csq_r = send_at(ser, "AT+CSQ", timeout=2.0)
        csq_line = csq_r.replace("\r", " ").strip().split("\n")[-1][:100]
        print(f"[{'OK':5}] GSM signal: {csq_line}")
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
    using_port = GPS_SERIAL_PORT if GPS_SERIAL_PORT else f"GPIO soft UART RX{GPS_RX_GPIO}"

    # Try a few common GPS UART baud rates. Start with configured GPS_BAUD.
    baud_candidates: list[int] = []
    for b in (GPS_BAUD, 9600, 38400, 115200):
        if int(b) not in baud_candidates:
            baud_candidates.append(int(b))

    if GPS_SERIAL_PORT:
        # Kernel serial mode: probe by opening the port at different bauds.
        try:
            import serial
        except ImportError:
            _emit("FAIL", "pyserial missing; cannot probe GPS kernel serial", "pip install pyserial in your venv.")
            return

        for baud in baud_candidates:
            ser = None
            try:
                ser = serial.Serial(GPS_SERIAL_PORT, baud, timeout=0.3)
                deadline = time.monotonic() + 1.5
                buf = ""
                while time.monotonic() < deadline:
                    chunk = ser.read(256)
                    if chunk:
                        buf += chunk.decode("ascii", errors="ignore")
                        if "$" in buf:
                            # Extract first $... line fragment for display.
                            idx = buf.find("$")
                            sample = buf[idx : idx + 60].replace("\r", "").replace("\n", " ")
                            print(
                                f"[{'OK':5}] GPS data on {using_port} @ {baud}: {sample!r}…"
                            )
                            return
                    time.sleep(0.05)
            except (OSError, ValueError):
                continue
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

        _emit(
            "WARN",
            f"GPS opened ({using_port}) but no data starting with $ across bauds {baud_candidates}",
            "Antenna outdoors, cold start (wait longer), wrong baud/protocol (NMEA disabled), "
            "or GPS TX not connected to Pi RX.",
        )
        return

    # GPIO soft UART mode (pigpio): probe by opening bb serial read at different bauds.
    try:
        import pigpio
    except ImportError:
        _emit(
            "FAIL",
            f"GPS open failed ({using_port})",
            "pigpio not installed. Install pigpio + start pigpiod for GPIO UART mode.",
        )
        return

    pi = pigpio.pi()
    if not getattr(pi, "connected", False):
        _emit(
            "FAIL",
            f"GPS open failed ({using_port})",
            "pigpiod not reachable. Start with: sudo systemctl enable --now pigpiod",
        )
        return

    try:
        for baud in baud_candidates:
            # Close any previous bb session on this pin before opening at a new baud.
            try:
                pi.bb_serial_read_close(GPS_RX_GPIO)
            except Exception:
                pass
            try:
                pi.bb_serial_read_open(GPS_RX_GPIO, baud, 8)
            except Exception:
                continue

            deadline = time.monotonic() + 1.5
            buf = ""
            while time.monotonic() < deadline:
                try:
                    count, data = pi.bb_serial_read(GPS_RX_GPIO)
                except Exception:
                    break
                if count > 0 and data:
                    buf += data.decode("ascii", errors="ignore")
                    if "$" in buf:
                        idx = buf.find("$")
                        sample = buf[idx : idx + 60].replace("\r", "").replace("\n", " ")
                        print(
                            f"[{'OK':5}] GPS data on {using_port} @ {baud}: {sample!r}…"
                        )
                        return
                time.sleep(0.05)

        _emit(
            "WARN",
            f"GPS opened ({using_port}) but no data starting with $ across bauds {baud_candidates}",
            "Antenna outdoors, cold start (wait longer), wrong baud/protocol (NMEA disabled), "
            "or GPS TX not connected to Pi RX.",
        )
    finally:
        try:
            pi.bb_serial_read_close(GPS_RX_GPIO)
        except Exception:
            pass
        try:
            pi.stop()
        except Exception:
            pass


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


def main() -> int:
    ap = argparse.ArgumentParser(description="SmartShell isolated hardware connectivity check")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print dry-run guidance without touching I2C/GPIO/serial",
    )
    args = ap.parse_args()
    return run_hardware_check(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
