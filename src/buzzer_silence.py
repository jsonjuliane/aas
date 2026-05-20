"""
Immediately silence the buzzer GPIO on startup.

    python -m src.buzzer_silence           # silence and exit
    python -m src.buzzer_silence --beep    # one short beep then silence
    python -m src.buzzer_silence --verify  # print current GPIO state

Normally invoked by smartshell-buzzer-silence.service at early boot.
"""

from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser(description="Silence buzzer GPIO on startup")
    ap.add_argument("--beep", action="store_true", help="One short beep before silencing")
    ap.add_argument("--verify", action="store_true", help="Print current GPIO state and exit")
    args = ap.parse_args()

    try:
        import RPi.GPIO as GPIO
    except ImportError:
        print("[buzzer-silence] RPi.GPIO not available — skipping (not on Pi).")
        return 0

    from src.config import BUZZER_ACTIVE_HIGH, BUZZER_BEEP_SEC, BUZZER_GPIO

    on_level  = GPIO.HIGH if BUZZER_ACTIVE_HIGH else GPIO.LOW
    off_level = GPIO.LOW  if BUZZER_ACTIVE_HIGH else GPIO.HIGH

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(BUZZER_GPIO, GPIO.OUT)

    if args.verify:
        state = GPIO.input(BUZZER_GPIO)
        print(f"[buzzer-silence] GPIO{BUZZER_GPIO} reads: {'HIGH' if state else 'LOW'}")
        GPIO.cleanup()
        return 0

    try:
        if args.beep:
            GPIO.output(BUZZER_GPIO, on_level)
            time.sleep(max(0.05, float(BUZZER_BEEP_SEC)))

        GPIO.output(BUZZER_GPIO, off_level)
        level_name = "LOW" if off_level == GPIO.LOW else "HIGH"
        print(f"[buzzer-silence] GPIO{BUZZER_GPIO} set to {level_name} (silent).")
        return 0
    except Exception as e:
        print(f"[buzzer-silence] Failed: {e}", file=sys.stderr)
        return 1
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
