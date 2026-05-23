"""
Verify family SMS config for Globe/SIM800 single-part delivery.

Run on the Pi after git pull:
  python -m src.sms_config_check
  python -m src.sms_config_check --send-test +639568504890
"""

from __future__ import annotations

import argparse
import sys

from src import contacts, gsm_alert, gsm_sim800l
from src.config import SMS_ALERT_TARGET_MAX_CHARS, SMS_SINGLE_PART_MAX_CHARS

_DEPRECATED_MARKERS = (
    "SMARTSHELL UPDATE",
    "{notified}",
    "https://maps.google.com",
    "Accident barangay:",
)
_EXPECTED_MARKERS = (
    "SMARTSHELL COLLISION ALERT",
    "Rider:",
    "{area}",
    "GPS:",
)


def check_sms_config(*, sample_lat: float = 14.333122, sample_lon: float = 121.085377) -> list[str]:
    """
    Return list of problem strings (empty if OK).
    """
    issues: list[str] = []
    try:
        phones, template, rider, home = contacts.load_family_contacts()
    except Exception as e:
        return [f"contacts_load_failed: {e}"]

    if not phones:
        issues.append("no_family_phones")

    for marker in _DEPRECATED_MARKERS:
        if marker in template:
            issues.append(f"deprecated_template_marker:{marker!r}")

    missing = [m for m in _EXPECTED_MARKERS if m not in template]
    if missing:
        issues.append(f"template_missing_markers:{','.join(missing)}")

    body = contacts.format_alert_message(
        template,
        sample_lat,
        sample_lon,
        rider,
        home,
        area="Inside Biñan",
        accident_barangay="Sto. Domingo",
        notified="family (3), home: Zapote",
    )
    parts = contacts.message_parts_for_delivery(body)
    non_ascii = [c for c in body if ord(c) > 127]

    if non_ascii:
        issues.append(f"non_ascii_in_body:{non_ascii!r}")
    if len(body) > SMS_SINGLE_PART_MAX_CHARS:
        issues.append(f"body_too_long:{len(body)}>{SMS_SINGLE_PART_MAX_CHARS}")
    elif len(body) > SMS_ALERT_TARGET_MAX_CHARS:
        issues.append(
            f"body_over_target:{len(body)}>{SMS_ALERT_TARGET_MAX_CHARS} (may still send 1 part)"
        )
    if len(parts) > 1:
        issues.append(f"would_split_into:{len(parts)}_parts")

    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify collision SMS config on this Pi")
    ap.add_argument(
        "--send-test",
        metavar="PHONE",
        help="After checks, send one production-format alert (no [SSnn] tag)",
    )
    args = ap.parse_args()

    print("SmartShell — SMS config check\n")
    try:
        phones, template, rider, home = contacts.load_family_contacts()
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1

    body = contacts.format_alert_message(
        template,
        14.333122,
        121.085377,
        rider,
        home,
        area="Inside Biñan",
        accident_barangay="Sto. Domingo",
    )
    parts = contacts.message_parts_for_delivery(body)

    print(f"[OK]   Family contacts: {len(phones)}")
    print(f"[OK]   Rider: {rider} | Home barangay: {home}")
    print(f"[INFO] Template starts: {template[:48].replace(chr(10), ' ')}...")
    print(f"[INFO] Sample alert: {len(body)} chars, {len(parts)} SMS part(s)")
    print(f"[INFO] Limits: target<={SMS_ALERT_TARGET_MAX_CHARS}, max<={SMS_SINGLE_PART_MAX_CHARS}")
    print("--- sample body ---")
    print(body)
    print("--- end ---")

    issues = check_sms_config()
    if issues:
        print("\n[WARN] Issues:")
        for item in issues:
            print(f"       - {item}")
        if any("deprecated" in i or "too_long" in i or "would_split" in i for i in issues):
            print("\n[FAIL] Fix config/contacts.family.json (see config/contacts.family.json.example).")
            return 1
    else:
        print("\n[OK]   SMS config looks good for single-part GSM delivery.")

    if args.send_test:
        print(f"\n[INFO] Sending production-format alert to {args.send_test}...")
        modem = gsm_sim800l.GSMSIM800L()
        modem.open()
        if modem._ser is None:  # noqa: SLF001
            print("[FAIL] GSM serial not open.")
            return 1
        out, _ = gsm_alert.send_sms_with_retries(
            modem=modem, phone=args.send_test, message=body
        )
        modem.close()
        ok = bool(out.get("ok"))
        print(
            f"[{'OK' if ok else 'FAIL'}] send reason={out.get('reason')} "
            f"parts={out.get('parts_total', 1)}"
        )
        return 0 if ok else 1

    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
