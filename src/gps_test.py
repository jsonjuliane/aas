"""
Isolated GPS NMEA stream test (auto baud, readable fix output).

Run on Raspberry Pi:
    python -m src.gps_test
    python -m src.gps_test --duration-sec 120
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from src.config import GPS_BAUD, GPS_RX_GPIO, GPS_SERIAL_PORT
from src.gps import _parse_gpgga


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def _print_fix(lat: float, lon: float, fix_type: int) -> None:
    print("\nCurrent GPS Coordinates")
    print(f"  Latitude : {lat:.6f}")
    print(f"  Longitude: {lon:.6f}")
    print(f"  Fix type : {fix_type}")


def _baud_candidates() -> list[int]:
    out: list[int] = []
    for b in (GPS_BAUD, 9600, 38400, 115200):
        bi = int(b)
        if bi not in out:
            out.append(bi)
    return out


def _find_baud_kernel(port: str, bauds: list[int]) -> tuple[int | None, object | None]:
    try:
        import serial
    except ImportError:
        return None, None
    for baud in bauds:
        ser = None
        got_dollar = False
        try:
            ser = serial.Serial(port, baud, timeout=0.3)
            deadline = time.monotonic() + 1.5
            buf = ""
            while time.monotonic() < deadline:
                chunk = ser.read(256)
                if chunk:
                    buf += chunk.decode("ascii", errors="ignore")
                    if "$" in buf:
                        got_dollar = True
                        return baud, ser
                time.sleep(0.05)
        except (OSError, ValueError):
            pass
        finally:
            if ser is not None and not got_dollar:
                try:
                    ser.close()
                except Exception:
                    pass
    return None, None


def _find_baud_pigpio(bauds: list[int]) -> tuple[int | None, object | None]:
    try:
        import pigpio
    except ImportError:
        return None, None
    pi = pigpio.pi()
    if not getattr(pi, "connected", False):
        try:
            pi.stop()
        except Exception:
            pass
        return None, None
    try:
        for baud in bauds:
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
                        return baud, pi
                time.sleep(0.05)
            try:
                pi.bb_serial_read_close(GPS_RX_GPIO)
            except Exception:
                pass
    except Exception:
        pass
    try:
        pi.bb_serial_read_close(GPS_RX_GPIO)
    except Exception:
        pass
    try:
        pi.stop()
    except Exception:
        pass
    return None, None


def _stream_kernel(ser: object, duration_sec: float, baud: int) -> int:
    """Read NMEA lines; return exit code (0 ok)."""
    lines = 0
    fixes = 0
    last_fix: dict | None = None
    t_end = time.monotonic() + duration_sec
    buf = ""
    _print_header("GPS stream")
    print(f"Source   : kernel serial")
    print(f"Baud     : {baud}")
    print(f"Duration : {duration_sec:.0f}s")
    print("Status   : listening for NMEA sentences...\n")
    while time.monotonic() < t_end:
        try:
            chunk = ser.read(512)  # type: ignore[attr-defined]
        except Exception:
            break
        if chunk:
            buf += chunk.decode("ascii", errors="ignore")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip("\r").strip()
            if not line:
                continue
            lines += 1
            if line.startswith("$"):
                print(f"NMEA: {line[:100]}")
                parsed = _parse_gpgga(line)
                if parsed and parsed.get("fix", 0) in (1, 2):
                    fixes += 1
                    last_fix = {"lat": parsed["lat"], "lon": parsed["lon"]}
                    _print_fix(parsed["lat"], parsed["lon"], int(parsed.get("fix", 0)))
        else:
            time.sleep(0.02)
    try:
        ser.close()  # type: ignore[attr-defined]
    except Exception:
        pass
    _print_header("GPS summary")
    print(f"Baud used          : {baud}")
    print(f"NMEA lines received: {lines}")
    print(f"Valid fixes found  : {fixes}")
    if last_fix:
        print(f"Last latitude      : {last_fix['lat']:.6f}")
        print(f"Last longitude     : {last_fix['lon']:.6f}")
    else:
        print("Last coordinates   : none")
    return 0


def _stream_pigpio(pi: object, baud: int, duration_sec: float) -> int:
    lines = 0
    fixes = 0
    last_fix: dict | None = None
    buf = ""
    t_end = time.monotonic() + duration_sec
    _print_header("GPS stream")
    print(f"Source   : GPIO soft UART RX{GPS_RX_GPIO}")
    print(f"Baud     : {baud}")
    print(f"Duration : {duration_sec:.0f}s")
    print("Status   : listening for NMEA sentences...\n")
    while time.monotonic() < t_end:
        try:
            count, data = pi.bb_serial_read(GPS_RX_GPIO)  # type: ignore[attr-defined]
        except Exception:
            break
        if count > 0 and data:
            buf += data.decode("ascii", errors="ignore")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip("\r").strip()
            if not line:
                continue
            lines += 1
            if line.startswith("$"):
                print(f"NMEA: {line[:100]}")
                parsed = _parse_gpgga(line)
                if parsed and parsed.get("fix", 0) in (1, 2):
                    fixes += 1
                    last_fix = {"lat": parsed["lat"], "lon": parsed["lon"]}
                    _print_fix(parsed["lat"], parsed["lon"], int(parsed.get("fix", 0)))
        time.sleep(0.02)
    try:
        pi.bb_serial_read_close(GPS_RX_GPIO)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        pi.stop()  # type: ignore[attr-defined]
    except Exception:
        pass
    _print_header("GPS summary")
    print(f"Baud used          : {baud}")
    print(f"NMEA lines received: {lines}")
    print(f"Valid fixes found  : {fixes}")
    if last_fix:
        print(f"Last latitude      : {last_fix['lat']:.6f}")
        print(f"Last longitude     : {last_fix['lon']:.6f}")
    else:
        print("Last coordinates   : none")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Isolated GPS NMEA stream test (auto baud, $GPGGA fixes)"
    )
    ap.add_argument(
        "--duration-sec",
        type=float,
        default=30.0,
        help="How long to read NMEA (default 30)",
    )
    args = ap.parse_args()
    duration = max(1.0, float(args.duration_sec))

    bauds = _baud_candidates()
    using = GPS_SERIAL_PORT if GPS_SERIAL_PORT else f"GPIO soft UART RX{GPS_RX_GPIO}"

    _print_header("SmartShell GPS isolated test")
    print(f"Target interface: {using}")
    print(f"Baud candidates : {bauds}")

    if GPS_SERIAL_PORT:
        baud, ser = _find_baud_kernel(GPS_SERIAL_PORT, bauds)
        if baud is None or ser is None:
            _print_header("GPS result")
            print("No NMEA data detected.")
            print(f"Interface: {GPS_SERIAL_PORT}")
            print(f"Tried    : {bauds}")
            print("Check TX wiring, power/ground, antenna open sky, and protocol mode.")
            return 1
        return _stream_kernel(ser, duration, baud)

    baud, pi = _find_baud_pigpio(bauds)
    if baud is None or pi is None:
        _print_header("GPS result")
        print("No NMEA data detected.")
        print(f"Interface: GPIO soft UART RX{GPS_RX_GPIO}")
        print(f"Tried    : {bauds}")
        print("Check pigpiod, GPS TX→GPIO20, power/ground, and antenna open sky.")
        return 1
    return _stream_pigpio(pi, baud, duration)


if __name__ == "__main__":
    raise SystemExit(main())
