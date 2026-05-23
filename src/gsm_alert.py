"""
SmartShell — GSM readiness and SMS send policy for collision alerts.

Encapsulates wait-for-signal, pre-send checks, and signal-aware retries.
See docs/features/03_gsm_sim800l.md.
"""

from __future__ import annotations

import time

from src import gsm_sim800l, hardware_check
from src.config import (
    GSM_MIN_CSQ_TO_SEND,
    GSM_SEND_RETRY_BACKOFF_SEC,
    GSM_SEND_RETRY_COUNT,
    GSM_SEND_RETRY_SIGNAL_WAIT_SEC,
    GSM_WAIT_POLL_SEC,
    GSM_WAIT_REGISTER_SEC,
    SMS_INTER_PART_DELAY_SEC,
)
from src.contacts import message_parts_for_delivery


def probe_csq(probe: dict[str, object]) -> int:
    """Extract CSQ from a hardware_check probe dict; 99 if missing/invalid."""
    csq = probe.get("csq")
    try:
        return int(csq) if csq is not None else 99
    except (TypeError, ValueError):
        return 99


def is_usable_csq(csq: int, *, min_csq: int | None = None) -> bool:
    """True when CSQ is a valid reading at or above the send threshold."""
    floor = int(GSM_MIN_CSQ_TO_SEND if min_csq is None else min_csq)
    return csq != 99 and csq >= floor


def probe_sms_ready(probe: dict[str, object], *, min_csq: int | None = None) -> bool:
    """
    True when modem probe reports ready to attempt SMS.

    Requires AT OK, SIM ready, network registered, text mode, and usable CSQ.
    """
    if not bool(probe.get("ok_at")):
        return False
    if not bool(probe.get("sim_ready")):
        return False
    if not bool(probe.get("network_registered")):
        return False
    if not bool(probe.get("text_mode_ok", True)):
        return False
    return is_usable_csq(probe_csq(probe), min_csq=min_csq)


def not_ready_reason(probe: dict[str, object]) -> str:
    """Short reason string when probe_sms_ready is False."""
    if not bool(probe.get("ok_at")):
        return "modem_no_at_response"
    if not bool(probe.get("sim_ready")):
        return "sim_not_ready"
    if not bool(probe.get("network_registered")):
        return "network_not_registered"
    if not bool(probe.get("text_mode_ok", True)):
        return "text_mode_failed"
    csq = probe_csq(probe)
    if not is_usable_csq(csq):
        return f"signal_too_weak:CSQ={csq},need>={int(GSM_MIN_CSQ_TO_SEND)}"
    return "unknown_not_ready"


def wait_for_gsm_ready(*, dry_run: bool = False) -> dict[str, object]:
    """
    Wait up to GSM_WAIT_REGISTER_SEC for registration and usable CSQ.

    Returns last hardware_check probe (may still be not ready on timeout).
    """
    if dry_run:
        return {
            "ok_at": True,
            "sms_ready": True,
            "sim_ready": True,
            "network_registered": True,
            "text_mode_ok": True,
            "detail": "dry_run",
            "csq": 99,
        }
    timeout_sec = max(1.0, float(GSM_WAIT_REGISTER_SEC))
    poll_sec = max(0.2, float(GSM_WAIT_POLL_SEC))
    min_csq = int(GSM_MIN_CSQ_TO_SEND)
    t_end = time.monotonic() + timeout_sec
    started = False
    last_probe: dict[str, object] = {}
    while time.monotonic() < t_end:
        probe = hardware_check.probe_gsm_readiness()
        last_probe = probe
        csq_val = probe_csq(probe)
        if probe_sms_ready(probe):
            print(f"GSM wait ready: {probe.get('detail')}")
            return probe
        if not started:
            print(
                f"GSM wait: waiting up to {timeout_sec:.0f}s for SMS readiness "
                f"(registered + CSQ>={min_csq})..."
            )
            started = True
        time.sleep(poll_sec)
    if last_probe:
        last_probe = dict(last_probe)
        last_probe["sms_ready"] = probe_sms_ready(last_probe)
    return last_probe if last_probe else {
        "ok_at": False,
        "sms_ready": False,
        "detail": "gsm_wait_no_probe",
        "csq": None,
    }


def wait_for_usable_csq(
    modem: gsm_sim800l.GSMSIM800L,
    *,
    min_csq: int | None = None,
    timeout_sec: float | None = None,
    poll_sec: float | None = None,
) -> tuple[int, bool]:
    """
    Poll modem CSQ until usable or timeout.

    Returns:
        (last_csq, ready) where ready means CSQ is usable for send.
    """
    floor = int(GSM_MIN_CSQ_TO_SEND if min_csq is None else min_csq)
    timeout = max(0.0, float(GSM_SEND_RETRY_SIGNAL_WAIT_SEC if timeout_sec is None else timeout_sec))
    poll = max(0.2, float(GSM_WAIT_POLL_SEC if poll_sec is None else poll_sec))
    if timeout <= 0:
        csq = int(modem.check_signal())
        return csq, is_usable_csq(csq, min_csq=floor)

    t_end = time.monotonic() + timeout
    last_csq = 99
    while time.monotonic() < t_end:
        last_csq = int(modem.check_signal())
        if is_usable_csq(last_csq, min_csq=floor):
            return last_csq, True
        time.sleep(poll)
    return last_csq, is_usable_csq(last_csq, min_csq=floor)


def send_sms_with_retries(
    modem: gsm_sim800l.GSMSIM800L,
    phone: str,
    message: str,
    *,
    dry_run: bool = False,
) -> tuple[dict[str, object], int]:
    """
    Send SMS with bounded retries, backoff, and signal-aware re-attempts.

    Before each attempt, ensures CSQ >= GSM_MIN_CSQ_TO_SEND (waits up to
    GSM_SEND_RETRY_SIGNAL_WAIT_SEC). Skips further retries if signal stays weak.
    """
    retries = max(1, int(GSM_SEND_RETRY_COUNT))
    backoff = max(0.0, float(GSM_SEND_RETRY_BACKOFF_SEC))
    min_csq = int(GSM_MIN_CSQ_TO_SEND)
    last: dict[str, object] = {
        "ok": False,
        "reason": "no_attempt",
        "signal_strength": 99,
        "cmgs_response_raw": "",
        "final_submit_response_raw": "",
        "cms_error_code": None,
    }

    for idx in range(retries):
        csq, ready = wait_for_usable_csq(modem, min_csq=min_csq)
        if not dry_run and not ready:
            last = {
                "ok": False,
                "reason": f"weak_signal_before_attempt:CSQ={csq},need>={min_csq}",
                "signal_strength": csq,
                "cmgs_response_raw": "",
                "final_submit_response_raw": "",
                "cms_error_code": None,
            }
            return last, idx + 1

        parts = message_parts_for_delivery(message)
        last = {
            "ok": False,
            "reason": "no_attempt",
            "signal_strength": csq,
            "cmgs_response_raw": "",
            "final_submit_response_raw": "",
            "cms_error_code": None,
            "parts_sent": 0,
            "parts_total": len(parts),
        }
        for part_idx, part_text in enumerate(parts):
            if part_idx > 0 and not dry_run:
                time.sleep(max(0.0, float(SMS_INTER_PART_DELAY_SEC)))
            out = modem.send_sms_detailed(phone=phone, text=part_text)
            last = {
                "ok": bool(out.get("ok", False)),
                "reason": str(out.get("reason", "unknown")),
                "signal_strength": int(out.get("signal_strength", csq)),
                "cmgs_response_raw": str(out.get("cmgs_response_raw", "")),
                "final_submit_response_raw": str(out.get("final_submit_response_raw", "")),
                "cms_error_code": out.get("cms_error_code"),
                "parts_sent": part_idx + 1 if bool(out.get("ok", False)) else part_idx,
                "parts_total": len(parts),
            }
            if not bool(last["ok"]):
                last["reason"] = f"part_{part_idx + 1}_of_{len(parts)}:{last['reason']}"
                break
        if bool(last["ok"]):
            if len(parts) > 1:
                last["reason"] = f"ok_split_{len(parts)}_parts"
            return last, idx + 1

        if idx >= (retries - 1):
            break

        failed_csq = int(last["signal_strength"])
        print(
            f"GSM SMS retry: attempt {idx + 1} failed ({last['reason']}), "
            f"CSQ={failed_csq}; waiting for signal (need >={min_csq})..."
        )
        retry_csq, retry_ready = wait_for_usable_csq(modem, min_csq=min_csq)
        if not dry_run and not retry_ready:
            last["reason"] = (
                f"weak_signal_retry_aborted:CSQ={retry_csq},need>={min_csq},"
                f"after={last['reason']}"
            )
            last["signal_strength"] = retry_csq
            return last, idx + 1
        if retry_ready and retry_csq > failed_csq:
            print(f"GSM signal improved: CSQ {failed_csq} -> {retry_csq}.")
        time.sleep(backoff)

    return last, retries
