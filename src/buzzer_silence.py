"""
Immediately silence the buzzer GPIO on startup.

Run this once at boot (before the main app) so a floating GPIO does not
leave the buzzer on at power-up.

    python -m src.buzzer_silence           # silence and exit
    python -m src.buzzer_silence --beep    # one confirmation beep, then silence

Normally invoked by smartshell-buzzer-silence.service at early boot.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Silence buzzer GPIO on startup")
    ap.add_argument(
        "--beep",
        action="store_true",
        help="Emit one short confirmation beep before silencing (boot indicator)",
    )
    args = ap.parse_args()

    try:
        import RPi.GPIO as GPIO
    except ImportError:
        print("[buzzer-silence] RPi.GPIO not available — skipping (not on Pi).")
        return 0

    from src.config import BUZZER_ACTIVE_HIGH, BUZZER_BEEP_SEC, BUZZER_GPIO

    off_level = GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH
    on_level = GPIO.HIGH if BUZZER_ACTIVE_HIGH else GPIO.LOW

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(BUZZER_GPIO, GPIO.OUT)

        if args.beep:
            import time
            GPIO.output(BUZZER_GPIO, on_level)
            time.sleep(max(0.05, float(BUZZER_BEEP_SEC)))

        GPIO.output(BUZZER_GPIO, off_level)
        print(f"[buzzer-silence] GPIO{BUZZER_GPIO} set to silent.")
        return 0
    except Exception as e:
        print(f"[buzzer-silence] Failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
