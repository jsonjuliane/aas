"""
Unit tests for GSM alert policy — run: python -m src.gsm_alert_test
"""

from __future__ import annotations

from src.gsm_alert import is_usable_csq, not_ready_reason, probe_csq, probe_sms_ready
from src.contacts import format_alert_message, message_parts_for_delivery, split_message_for_sms
from src.gsm_sim800l import _cmgs_submit_ok, _cmgs_submit_timeout_sec


def _check(name: str, ok: bool) -> None:
    tag = "OK" if ok else "FAIL"
    print(f"[{tag}] {name}")
    if not ok:
        raise SystemExit(1)


def main() -> int:
    _check("usable csq 10", is_usable_csq(10))
    _check("weak csq 5", not is_usable_csq(5))
    _check("unknown csq 99", not is_usable_csq(99))
    _check("probe csq parse", probe_csq({"csq": 12}) == 12)
    _check("probe csq missing", probe_csq({}) == 99)

    ready_probe = {
        "ok_at": True,
        "sim_ready": True,
        "network_registered": True,
        "text_mode_ok": True,
        "csq": 10,
    }
    _check("ready probe", probe_sms_ready(ready_probe))

    weak = dict(ready_probe)
    weak["csq"] = 3
    _check("weak probe not ready", not probe_sms_ready(weak))
    _check("weak reason", "signal_too_weak" in not_ready_reason(weak))

    no_net = dict(ready_probe)
    no_net["network_registered"] = False
    _check("no net reason", not_ready_reason(no_net) == "network_not_registered")

    _check("cmgs ok response", _cmgs_submit_ok("+CMGS: 12\r\n\r\nOK\r\n"))
    _check("cms error not ok", not _cmgs_submit_ok("+CMS ERROR: 500\r\n"))
    _check("long sms timeout", _cmgs_submit_timeout_sec("x" * 280) >= 20.0)

    long_tpl = "SMARTSHELL UPDATE: COLLISION DETECTED\nName: {name}\nArea: {area}\n" * 3
    compact = format_alert_message(
        long_tpl,
        14.33,
        121.08,
        rider_name="Juan Dela Cruz",
        home_barangay="Zapote",
        area="Inside Biñan",
        accident_barangay="Sto. Domingo",
    )
    _check("compact alert fits one part", len(compact) <= 160)
    parts = message_parts_for_delivery("x" * 200)
    _check("split long body", len(parts) >= 2)
    _check("split parts fit limit", all(len(p) <= 160 for p in split_message_for_sms("x" * 200)))

    print("All gsm_alert policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
