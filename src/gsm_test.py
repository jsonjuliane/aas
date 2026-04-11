"""
Isolated SIM800L GSM diagnostic (multi-baud AT, SIM, registration, signal).

Run on Raspberry Pi:
    python -m src.gsm_test
    python -m src.gsm_test --send-sms +639171234567 "Test message"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Ensure project root on path
_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from src.config import SIM800L_BAUD, SIM800L_UART_DEVICE
from src.gsm_sim800l import send_at

try:
    import serial as serial_mod
except ImportError:
    serial_mod = None  # type: ignore[misc, assignment]


def _print_ok(msg: str) -> None:
    print(f"[{'OK':5}] {msg}")


def _print_warn(msg: str, detail: str | None = None) -> None:
    print(f"[{'WARN':5}] {msg}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"       → {line}")


def _print_fail(msg: str, detail: str | None = None) -> None:
    print(f"[{'FAIL':5}] {msg}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"       → {line}")


def _baud_candidates() -> list[int]:
    out: list[int] = []
    for b in (SIM800L_BAUD, 9600, 38400, 115200):
        bi = int(b)
        if bi not in out:
            out.append(bi)
    return out


def _open_serial_at_baud(dev: str, baud: int):
    if serial_mod is None:
        raise ImportError("pyserial")
    return serial_mod.Serial(dev, baud, timeout=0.5)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Isolated SIM800L GSM diagnostic (AT, SIM, network, signal)"
    )
    ap.add_argument(
        "--send-sms",
        nargs=2,
        metavar=("PHONE", "MESSAGE"),
        default=None,
        help="After diagnostics, send one test SMS (text mode)",
    )
    args = ap.parse_args()

    dev = SIM800L_UART_DEVICE
    print("SmartShell — GSM isolated test\n")

    if serial_mod is None:
        _print_fail("pyserial not installed", "pip install pyserial in your venv.")
        return 1

    if not os.path.exists(dev):
        _print_fail(f"Device missing: {dev}", "Enable UART; check raspi-config serial.")
        return 1

    ser = None
    working_baud: int | None = None
    last_raw = ""

    for baud in _baud_candidates():
        try:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
            ser = _open_serial_at_baud(dev, baud)
            resp = send_at(ser, "AT", timeout=2.0)
            last_raw = resp[:200] if resp else ""
            if "OK" in resp:
                working_baud = baud
                break
        except OSError as e:
            _print_warn(f"Open failed @ {baud}: {e}", "")
            continue

    if ser is None or working_baud is None:
        _print_fail(
            "No OK response to AT across baud rates",
            f"Tried: {_baud_candidates()}. Last raw (truncated): {last_raw!r}\n"
            "Check TX/RX (crossed), power, VDD, common GND.",
        )
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        return 1

    _print_ok(f"GSM AT OK ({dev} @ {working_baud})")

    try:
        send_at(ser, "ATE0", timeout=1.0)
        send_at(ser, "AT+CMGF=1", timeout=2.0)

        r = send_at(ser, "AT+CPIN?", timeout=2.0)
        snippet = r.replace("\r", " ").strip()[:120]
        if "READY" in r:
            _print_ok(f"SIM: {snippet}")
        elif "SIM PIN" in r or "PIN" in r:
            _print_warn(f"SIM needs PIN: {snippet}", "Enter PIN with AT+CPIN=\"xxxx\" or unlock SIM.")
        else:
            _print_warn(f"SIM state: {snippet}", "Insert SIM or check slot.")

        r = send_at(ser, "AT+CREG?", timeout=2.0)
        _print_ok(f"Registration: {r.replace(chr(13), ' ').strip()[:100]}")

        r = send_at(ser, "AT+CSQ", timeout=2.0)
        _print_ok(f"Signal: {r.replace(chr(13), ' ').strip()[:100]}")

        r = send_at(ser, "AT+COPS?", timeout=3.0)
        _print_ok(f"Operator: {r.replace(chr(13), ' ').strip()[:120]}")

        if args.send_sms:
            phone, message = args.send_sms[0], args.send_sms[1]
            r = send_at(ser, "AT+CMGF=1", timeout=2.0)
            if "OK" not in r:
                _print_fail("Could not set text mode (AT+CMGF=1)")
                return 1
            r = send_at(ser, f'AT+CMGS="{phone}"', timeout=5.0)
            if ">" not in r:
                _print_fail("No SMS prompt (>)", repr(r[:200]))
                return 1
            time.sleep(0.2)
            ser.write((message + "\x1a").encode())
            r = send_at(ser, "", timeout=30.0)
            if "OK" in r:
                _print_ok(f"SMS sent to {phone}")
            else:
                _print_warn("SMS send unclear", repr(r[:300]))
                return 1

    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    print("\n[DONE] GSM test complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
