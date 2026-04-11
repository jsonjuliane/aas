"""
SmartShell — SIM800L GSM module for SMS alerts.

Sends SMS to emergency contacts via hardware UART.
See docs/features/03_gsm_sim800l.md.
"""

from __future__ import annotations

import time
from typing import Any

from src.config import SIM800L_BAUD, SIM800L_UART_DEVICE


def send_at(ser: Any, cmd: str, timeout: float = 2.0) -> str:
    """Send AT command and return response (newline-terminated commands)."""
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    deadline = time.monotonic() + timeout
    buf: list[str] = []
    while time.monotonic() < deadline:
        if ser.in_waiting:
            buf.append(ser.read(ser.in_waiting).decode("ascii", errors="replace"))
        time.sleep(0.05)
    return "".join(buf)


# Backward-compatible alias
_send_at = send_at


class GSMSIM800L:
    """
    SIM800L GSM module interface for sending SMS.

    Uses hardware UART (primary serial). Configure SIM800L_UART_DEVICE in config.
    """

    def __init__(self, device: str | None = None, dry_run: bool = False) -> None:
        """
        Initialize GSM module.

        Args:
            device: UART device path. Uses config default if None.
            dry_run: If True, send_sms() logs but does not send.
        """
        self._device = device if device is not None else SIM800L_UART_DEVICE
        self._dry_run = dry_run
        self._ser: Any = None

    def open(self) -> None:
        """Open UART connection and verify module responds. Silently fails if unavailable."""
        if self._dry_run:
            return
        try:
            import serial

            self._ser = serial.Serial(self._device, SIM800L_BAUD, timeout=0.5)
            r = send_at(self._ser, "AT")
            if "OK" not in r:
                self._ser.close()
                self._ser = None
                return
            # Disable command echo for cleaner responses on subsequent commands.
            send_at(self._ser, "ATE0", timeout=1.0)
        except (ImportError, OSError):
            self._ser = None

    def close(self) -> None:
        """Close UART connection."""
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def send_sms(self, phone: str, text: str) -> bool:
        """
        Send SMS to the given phone number.

        Args:
            phone: E.164 format (e.g. +639171234567).
            text: Message body.

        Returns:
            True if sent successfully, False otherwise.
        """
        if self._dry_run:
            return True  # Pretend success for dry run
        if self._ser is None:
            self.open()
        if self._ser is None:
            return False
        try:
            r = send_at(self._ser, "AT+CMGF=1", timeout=2.0)
            if "OK" not in r:
                return False
            r = send_at(self._ser, f'AT+CMGS="{phone}"', timeout=3.0)
            if ">" not in r:
                return False
            time.sleep(0.2)
            self._ser.write((text + "\x1a").encode())
            r = send_at(self._ser, "", timeout=15.0)
            return "OK" in r
        except Exception:
            return False

    def check_signal(self) -> int:
        """
        Get signal quality (0–31).

        Returns:
            CSQ value; 99 if unavailable.
        """
        if self._dry_run or self._ser is None:
            return 99
        r = send_at(self._ser, "AT+CSQ")
        for line in r.splitlines():
            if "+CSQ:" in line:
                try:
                    parts = line.split(":")
                    val = int(parts[1].strip().split(",")[0])
                    return min(31, max(0, val))
                except (ValueError, IndexError):
                    pass
        return 99
