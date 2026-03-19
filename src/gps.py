"""
SmartShell — GPS module for location via NMEA serial.

Obtains current coordinates for inclusion in SMS alerts.
See docs/features/02_gps.md.
"""

from __future__ import annotations

import time
from typing import Any

from src.config import GPS_BAUD, GPS_SERIAL_PORT


def _parse_gpgga(line: str) -> dict | None:
    """Parse $GPGGA for lat, lon, fix quality. Returns None if invalid."""
    if not line.startswith("$GPGGA"):
        return None
    parts = line.split(",")
    if len(parts) < 10:
        return None
    try:
        lat_raw = parts[2]
        lat_ns = parts[3]
        lon_raw = parts[4]
        lon_ew = parts[5]
        fix = int(parts[6]) if parts[6] else 0
        if not lat_raw or not lon_raw:
            return None
        lat_deg = float(lat_raw[:2])
        lat_min = float(lat_raw[2:])
        lat = lat_deg + lat_min / 60.0
        if lat_ns == "S":
            lat = -lat
        lon_deg = float(lon_raw[:3])
        lon_min = float(lon_raw[3:])
        lon = lon_deg + lon_min / 60.0
        if lon_ew == "W":
            lon = -lon
        return {"lat": lat, "lon": lon, "fix": fix}
    except (ValueError, IndexError):
        return None


class GPSModule:
    """
    GPS module interface for obtaining coordinates.

    Uses serial port for NMEA input. Configure GPS_SERIAL_PORT in config.
    """

    def __init__(self, port: str | None = None, dry_run: bool = False) -> None:
        """
        Initialize GPS module.

        Args:
            port: Serial device path (e.g. /dev/ttyS0). Uses config default if None.
            dry_run: If True, get_fix() returns None without opening serial.
        """
        self._port = port if port is not None else GPS_SERIAL_PORT
        self._dry_run = dry_run
        self._ser: Any = None

    def open(self) -> None:
        """Open serial connection to GPS module. Silently fails if port unavailable."""
        if self._dry_run or not self._port:
            return
        try:
            import serial

            self._ser = serial.Serial(self._port, GPS_BAUD, timeout=0.5)
        except (ImportError, OSError):
            self._ser = None

    def close(self) -> None:
        """Close serial connection."""
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def get_fix(self, timeout_sec: float = 5.0) -> dict | None:
        """
        Get current GPS fix (lat, lon).

        Reads NMEA until a valid $GPGGA with fix is found.

        Args:
            timeout_sec: Max seconds to wait for fix.

        Returns:
            Dict with lat, lon, optionally alt, timestamp. None if no fix.
        """
        if self._dry_run or not self._port:
            return None
        if self._ser is None:
            self.open()
        if self._ser is None:
            return None
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            line = self._ser.readline().decode("ascii", errors="ignore").strip()
            if line and line.startswith("$"):
                parsed = _parse_gpgga(line)
                if parsed and parsed.get("fix", 0) in (1, 2):
                    return {
                        "lat": parsed["lat"],
                        "lon": parsed["lon"],
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                    }
        return None

    def read_nmea_line(self) -> str | None:
        """Read one raw NMEA line. For debugging."""
        if self._dry_run or self._ser is None:
            return None
        line = self._ser.readline().decode("ascii", errors="ignore").strip()
        return line if line else None
