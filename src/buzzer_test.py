"""
Isolated buzzer bench test.

Run on Raspberry Pi:
    python -m src.buzzer_test
"""

from __future__ import annotations

import argparse

from src import buzzer_hw


def main() -> int:
    ap = argparse.ArgumentParser(description="Isolated buzzer bench test")
    ap.add_argument(
        "--silence-only",
        action="store_true",
        help="Drive buzzer GPIO to OFF and exit",
    )
    ap.add_argument(
        "--duration-sec",
        type=float,
        default=1.0,
        help="How long buzzer stays ON before turning OFF (default 1.0)",
    )
    args = ap.parse_args()

    if args.silence_only:
        if buzzer_hw.silence():
            print(
                "Buzzer GPIO driven to silent level "
                "(see BUZZER_ACTIVE_HIGH in src/config.py if inverted)."
            )
            return 0
        print("Buzzer silence failed (not a Raspberry Pi, missing RPi.GPIO, or GPIO error).")
        return 1

    if buzzer_hw.test_beep(duration_sec=args.duration_sec):
        print(
            f"Buzzer test: ON for {args.duration_sec}s then OFF "
            "(see BUZZER_ACTIVE_HIGH in src/config.py if inverted)."
        )
        return 0

    print("Buzzer test failed (not a Raspberry Pi, missing RPi.GPIO, or GPIO error).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
