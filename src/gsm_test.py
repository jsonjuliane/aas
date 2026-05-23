"""
Isolated SIM800L GSM diagnostic (multi-baud AT, SIM, registration, signal).

Run on Raspberry Pi:
    python -m src.gsm_test
    python -m src.gsm_test --send-sms +639171234567 "Test message"
    python -m src.gsm_test --send-alert-sms +639568504890
    python -m src.gsm_test --send-test-sms +639568504890
    python -m src.gsm_test --send-sms +639568504890 --message-file /tmp/alert.txt
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

from src.config import GSM_BENCH_TEST_TEXT, SIM800L_BAUD, SIM800L_UART_DEVICE
from src import gsm_alert
from src.gsm_sim800l import GSMSIM800L, send_at

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
        nargs="+",
        metavar=("PHONE", "MESSAGE"),
        default=None,
        help="After diagnostics, send one SMS (use --message-file to avoid shell quoting issues)",
    )
    ap.add_argument(
        "--message-file",
        type=Path,
        default=None,
        help="SMS body from file (with --send-sms PHONE only)",
    )
    ap.add_argument(
        "--send-alert-sms",
        metavar="PHONE",
        default=None,
        help="Send full collision alert body from contacts.family.json (sample inside-Biñan GPS)",
    )
    ap.add_argument(
        "--send-test-sms",
        metavar="PHONE",
        default=None,
        help=f'Send short bench SMS (default text: "{GSM_BENCH_TEST_TEXT}") via alert send path',
    )
    ap.add_argument(
        "--test-text",
        default=None,
        help=f'Override bench SMS body (with --send-test-sms; default "{GSM_BENCH_TEST_TEXT}")',
    )
    args = ap.parse_args()

    send_modes = sum(
        1
        for x in (args.send_sms, args.send_alert_sms, args.send_test_sms)
        if x is not None
    )
    if send_modes > 1:
        ap.error("Use only one of: --send-sms, --send-alert-sms, --send-test-sms")
    if args.message_file and (not args.send_sms or len(args.send_sms) != 1):
        ap.error("--message-file requires exactly: --send-sms PHONE")
    if args.test_text and not args.send_test_sms:
        ap.error("--test-text requires --send-test-sms")

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

        send_phone: str | None = None
        send_message: str | None = None
        if args.send_test_sms:
            send_phone = str(args.send_test_sms)
            send_message = str(args.test_text if args.test_text is not None else GSM_BENCH_TEST_TEXT)
            print(f'[INFO ] Bench test SMS: {len(send_message)} chars, body="{send_message}"')
        elif args.send_alert_sms:
            from src import contacts

            _, tpl, rider, home = contacts.load_family_contacts()
            send_phone = str(args.send_alert_sms)
            send_message = contacts.format_alert_message(
                tpl,
                14.333122,
                121.085377,
                rider,
                home,
                area="Inside Biñan",
                accident_barangay="Sto. Domingo",
                notified="family (3), home: Zapote, accident: Sto. Domingo",
            )
            parts = contacts.message_parts_for_delivery(send_message)
            print(
                f"[INFO ] Alert body: {len(send_message)} chars, "
                f"{len(parts)} SMS part(s) to send"
            )
            print("--- message ---")
            print(send_message)
            print("--- end ---")
        elif args.send_sms:
            if args.message_file:
                send_phone = args.send_sms[0]
                send_message = args.message_file.read_text(encoding="utf-8")
            elif len(args.send_sms) >= 2:
                send_phone = args.send_sms[0]
                send_message = " ".join(args.send_sms[1:])
            else:
                _print_fail("--send-sms needs PHONE and MESSAGE, or PHONE with --message-file")
                return 1
            print(f"[INFO ] Message length: {len(send_message)} chars")

        if send_phone and send_message is not None:
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            modem = GSMSIM800L()
            modem.open()
            if modem._ser is None:  # noqa: SLF001 — bench test needs open serial
                _print_fail("Could not open GSM serial for SMS send")
                return 1
            out, _attempts = gsm_alert.send_sms_with_retries(
                modem=modem, phone=send_phone, message=send_message
            )
            modem.close()
            raw = str(out.get("final_submit_response_raw", ""))
            if bool(out.get("ok")):
                parts_note = ""
                if int(out.get("parts_total", 1)) > 1:
                    parts_note = f", parts={out.get('parts_sent')}/{out.get('parts_total')}"
                _print_ok(
                    f"SMS sent to {send_phone} "
                    f"(reason={out.get('reason')}, CSQ={out.get('signal_strength')}{parts_note})"
                )
                if raw.strip():
                    snippet = raw.replace("\r", " ").strip()[:200]
                    print(f"       modem: {snippet}")
            else:
                _print_fail(
                    f"SMS failed to {send_phone}: {out.get('reason')} "
                    f"(cms={out.get('cms_error_code')})",
                    repr(raw[:400]),
                )
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
