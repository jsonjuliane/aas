"""
Unit tests for GSM alert policy — run: python -m src.gsm_alert_test
"""

from __future__ import annotations

from src.gsm_alert import is_usable_csq, not_ready_reason, probe_csq, probe_sms_ready


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

    print("All gsm_alert policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
