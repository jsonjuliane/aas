"""
SMS delivery matrix — send labeled test messages to find what the carrier delivers.

Each message starts with [SSnn] so you can note which IDs arrived.

Run on Raspberry Pi (project root, venv):
  python -m src.gsm_sms_matrix_test --list
  python -m src.gsm_sms_matrix_test --phone +639202828660 --dry-run
  python -m src.gsm_sms_matrix_test --phone +639202828660 --confirm
  python -m src.gsm_sms_matrix_test --phone +639202828660 --confirm --only 01,05,12
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src import contacts, gsm_alert, gsm_sim800l
from src.config import GSM_BENCH_TEST_TEXT, LOGS_DIR, PROJECT_ROOT


@dataclass(frozen=True)
class SmsMatrixCase:
    case_id: str
    name: str
    body: str
    note: str = ""


def _tag(case_id: str, text: str) -> str:
    return f"[SS{case_id}] {text}"


def _ascii_block(case_id: str, total_len: int, *, fill: str = "X") -> str:
    """Build a tagged message of exactly total_len characters (if possible)."""
    prefix = _tag(case_id, "")
    need = max(0, total_len - len(prefix))
    return prefix + (fill * need)[:need]


def build_matrix_cases() -> list[SmsMatrixCase]:
    """All bench scenarios (ASCII unless noted)."""
    sample_lat, sample_lon = 14.333122, 121.085377
    try:
        _, tpl, rider, home = contacts.load_family_contacts()
        alert_body = contacts.format_alert_message(
            tpl,
            sample_lat,
            sample_lon,
            rider,
            home,
            area="Inside Biñan",
            accident_barangay="Sto. Domingo",
            notified="family (3), home: Zapote",
        )
    except Exception as e:
        alert_body = _tag("12", f"alert format failed: {e}")

    formal_static = (
        "SMARTSHELL COLLISION ALERT\n\n"
        "Rider: Juan Dela Cruz\n"
        "Area: Inside Binan\n"
        "Home: Zapote | Accident: Sto. Domingo\n\n"
        "GPS: 14.3331, 121.0854"
    )

    cases: list[SmsMatrixCase] = [
        SmsMatrixCase("01", "short bench (9 chars)", _tag("01", GSM_BENCH_TEST_TEXT)),
        SmsMatrixCase("02", "30 chars ASCII", _ascii_block("02", 30)),
        SmsMatrixCase("03", "50 chars ASCII", _ascii_block("03", 50)),
        SmsMatrixCase("04", "80 chars ASCII", _ascii_block("04", 80)),
        SmsMatrixCase("05", "100 chars ASCII", _ascii_block("05", 100)),
        SmsMatrixCase("06", "120 chars ASCII", _ascii_block("06", 120)),
        SmsMatrixCase("07", "160 chars ASCII (GSM-7 1-part max)", _ascii_block("07", 160)),
        SmsMatrixCase(
            "08",
            "161 chars ASCII (over 1-part GSM-7)",
            _ascii_block("08", 161),
            note="May split or fail delivery",
        ),
        SmsMatrixCase(
            "09",
            "200 chars ASCII",
            _ascii_block("09", 200),
            note="Likely 2+ parts",
        ),
        SmsMatrixCase(
            "10",
            "newlines only (short)",
            _tag("10", "Line A\nLine B\nLine C"),
        ),
        SmsMatrixCase(
            "11",
            "newlines paragraph (medium)",
            _tag("11", "Header\n\nBody line 1\nBody line 2\n\nFooter"),
        ),
        SmsMatrixCase(
            "12",
            "Google Map URL (legacy)",
            _tag(
                "12",
                contacts.format_google_map_test_sms(14.333122, 121.085377, style="legacy"),
            ),
            note="Globe P2P often blocks https; modem +CMGS may still OK",
        ),
        SmsMatrixCase(
            "22",
            "GPS coords only (no URL)",
            _tag("22", "GPS: 14.333122, 121.085377"),
            note="Production map line format",
        ),
        SmsMatrixCase(
            "13",
            "Inside Binan (ASCII n)",
            _tag("13", "Area test: Inside Binan"),
        ),
        SmsMatrixCase(
            "14",
            "Biñan raw UTF-8 (non-GSM)",
            _tag("14", "Area test: Inside Biñan"),
            note="Contains n-tilde; may force UCS-2",
        ),
        SmsMatrixCase(
            "15",
            "formal static paragraph",
            _tag("15", formal_static),
            note=f"{len(formal_static)} chars in body after tag",
        ),
        SmsMatrixCase(
            "16",
            "live format_alert_message()",
            _tag("16", alert_body),
            note=f"{len(alert_body)} chars after tag; production formatter",
        ),
        SmsMatrixCase(
            "17",
            "colon pipe special chars",
            _tag("17", "Home: Zapote | Accident: Sto. Domingo"),
        ),
        SmsMatrixCase(
            "18",
            "digits coords only",
            _tag("18", "GPS 14.333122, 121.085377"),
        ),
        SmsMatrixCase(
            "19",
            "SMARTSHELL keyword",
            _tag("19", "SMARTSHELL COLLISION ALERT test"),
        ),
        SmsMatrixCase(
            "20",
            "split part 1/2 manual",
            _tag("20", "(1/2) First half of split test. " + "Y" * 80),
        ),
        SmsMatrixCase(
            "21",
            "split part 2/2 manual",
            _tag("21", "(2/2) Second half. Map 14.333,121.085"),
        ),
    ]
    return cases


def _non_ascii_chars(text: str) -> list[str]:
    return [c for c in text if ord(c) > 127]


def _print_case_table(case_list: list[SmsMatrixCase]) -> None:
    print(f"{'ID':<4} {'Len':>4}  {'Non-ASCII':<10}  Name")
    print("-" * 72)
    for c in case_list:
        body = c.body
        na = _non_ascii_chars(body)
        na_s = ",".join(na) if na else "-"
        print(f"{c.case_id:<4} {len(body):>4}  {na_s:<10}  {c.name}")
        if c.note:
            print(f"     note: {c.note}")


def _parse_only(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {p.strip().zfill(2) for p in raw.split(",") if p.strip()}


def _filter_cases(
    case_list: list[SmsMatrixCase],
    *,
    only: set[str] | None,
    skip: set[str] | None,
) -> list[SmsMatrixCase]:
    out: list[SmsMatrixCase] = []
    for c in case_list:
        if only is not None and c.case_id not in only:
            continue
        if skip is not None and c.case_id in skip:
            continue
        out.append(c)
    return out


def _log_result(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def run_matrix(
    phone: str,
    *,
    dry_run: bool = False,
    delay_sec: float = 12.0,
    only: set[str] | None = None,
    skip: set[str] | None = None,
    log_file: Path | None = None,
) -> int:
    case_list = _filter_cases(build_matrix_cases(), only=only, skip=skip)
    if not case_list:
        print("No cases selected.")
        return 1

    print(f"SmartShell SMS matrix → {phone}")
    print(f"Cases: {len(case_list)}, delay between sends: {delay_sec:.1f}s\n")
    _print_case_table(case_list)
    print()

    if dry_run:
        print("[DRY-RUN] No SMS sent. Use --confirm to send.")
        for c in case_list:
            print(f"\n--- SS{c.case_id} ({len(c.body)} chars) ---")
            print(c.body)
        return 0

    modem = gsm_sim800l.GSMSIM800L()
    modem.open()
    if modem._ser is None:  # noqa: SLF001
        print("[FAIL] Could not open GSM serial.")
        return 1

    results: list[dict] = []
    try:
        for idx, c in enumerate(case_list):
            print(f"\n[{idx + 1}/{len(case_list)}] SS{c.case_id}: {c.name} ({len(c.body)} chars)")
            out, attempts = gsm_alert.send_sms_with_retries(
                modem=modem, phone=phone, message=c.body
            )
            ok = bool(out.get("ok"))
            raw = str(out.get("final_submit_response_raw", ""))[:200]
            record = {
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "case_id": c.case_id,
                "name": c.name,
                "phone": phone,
                "len": len(c.body),
                "ok": ok,
                "reason": out.get("reason"),
                "cms_error_code": out.get("cms_error_code"),
                "attempts": attempts,
                "modem_snippet": raw.replace("\r", " ").strip(),
            }
            results.append(record)
            tag = "OK" if ok else "FAIL"
            print(f"  [{tag}] reason={out.get('reason')} cms={out.get('cms_error_code')}")
            if raw.strip():
                print(f"       modem: {raw.replace(chr(13), ' ').strip()[:160]}")
            if log_file:
                _log_result(log_file, record)

            if idx < len(case_list) - 1:
                print(f"  Waiting {delay_sec:.1f}s before next...")
                time.sleep(max(0.0, delay_sec))
    finally:
        modem.close()

    print("\n" + "=" * 72)
    print("SUMMARY — note which [SSnn] tags arrived on your phone:")
    print("=" * 72)
    for r in results:
        mark = "OK" if r["ok"] else "FAIL"
        print(f"  [SS{r['case_id']}] {mark:4}  len={r['len']:3}  {r['name']}")
    print("\nReply with the SS IDs you received (e.g. 01,07,13) to narrow the cause.")
    if log_file:
        print(f"Log: {log_file}")
    return 0 if all(r["ok"] for r in results) else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Send labeled SMS test matrix to diagnose delivery (Globe/SIM800)"
    )
    ap.add_argument("--phone", metavar="NUMBER", help="Destination E.164 or 09...")
    ap.add_argument("--list", action="store_true", help="List cases and exit")
    ap.add_argument("--dry-run", action="store_true", help="Print bodies only, no send")
    ap.add_argument(
        "--confirm",
        action="store_true",
        help="Required with --phone to actually send (avoids accidental spam)",
    )
    ap.add_argument(
        "--delay-sec",
        type=float,
        default=12.0,
        help="Pause between sends (default 12)",
    )
    ap.add_argument(
        "--only",
        metavar="IDS",
        help="Comma-separated case IDs, e.g. 01,07,16",
    )
    ap.add_argument("--skip", metavar="IDS", help="Comma-separated case IDs to skip")
    ap.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Append JSON lines per send (default logs/gsm_sms_matrix.jsonl)",
    )
    args = ap.parse_args()

    if args.list or not args.phone:
        cases = build_matrix_cases()
        print("SmartShell SMS matrix cases\n")
        _print_case_table(cases)
        if not args.phone and not args.list:
            print("\nUse --phone +639... --dry-run or --confirm to run.")
        return 0

    if not args.dry_run and not args.confirm:
        print("Refusing to send without --confirm (use --dry-run to preview).")
        return 1

    log_path = args.log
    if log_path is None and args.confirm and not args.dry_run:
        log_path = PROJECT_ROOT / LOGS_DIR / "gsm_sms_matrix.jsonl"

    return run_matrix(
        args.phone,
        dry_run=args.dry_run,
        delay_sec=args.delay_sec,
        only=_parse_only(args.only),
        skip=_parse_only(args.skip),
        log_file=log_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
