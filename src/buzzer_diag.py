"""
Buzzer GPIO diagnostic — run this to find correct pin and polarity.

Run on Raspberry Pi (venv active):

    python -m src.buzzer_diag              # test configured GPIO18
    python -m src.buzzer_diag --pin 18     # explicit pin
    python -m src.buzzer_diag --scan       # sweep all safe GPIO pins (hear which beeps)
"""

from __future__ import annotations

import argparse
import time

# Safe GPIO pins to sweep (BCM) — excludes UART, I2C, SPI, ID pins and project-reserved ones.
_SAFE_SCAN_PINS = [4, 5, 6, 12, 13, 16, 18, 22, 23, 24, 25, 27]

# Project-reserved (shown in warning but not blocked from --pin test)
_PROJECT_PINS = {
    14: "GSM TX", 15: "GSM RX",
    17: "cancel button", 18: "buzzer",
    19: "MP3 TX", 20: "GPS RX", 21: "GPS TX", 26: "MP3 RX",
    2: "MPU SDA", 3: "MPU SCL",
}


def _try_import_gpio():
    try:
        import RPi.GPIO as GPIO
        return GPIO
    except ImportError:
        print("[FAIL] RPi.GPIO not installed (not on Pi or venv missing RPi.GPIO).")
        return None


def _level_label(level: int) -> str:
    return "HIGH (3.3 V)" if level else "LOW  (0 V)"


def test_pin(pin: int, hold_sec: float) -> None:
    GPIO = _try_import_gpio()
    if GPIO is None:
        return

    reserved = _PROJECT_PINS.get(pin)
    if reserved and reserved != "buzzer":
        print(f"[WARN] BCM {pin} is used by '{reserved}' in this project — testing anyway.")

    print(f"\n{'='*50}")
    print(f"Buzzer GPIO diagnostic — BCM {pin} (physical pin varies by Pi model)")
    print(f"{'='*50}")

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(pin, GPIO.OUT)

    for level, label in [(GPIO.HIGH, "HIGH"), (GPIO.LOW, "LOW")]:
        print(f"\n[TEST] Setting BCM {pin} → {label} ({_level_label(level)}) for {hold_sec:.1f}s...")
        GPIO.output(pin, level)
        for remaining in range(int(hold_sec), 0, -1):
            print(f"       {remaining}s remaining — is buzzer ON or OFF?")
            time.sleep(1)
        current = GPIO.input(pin)
        print(f"       Done. Pin reads back: {_level_label(current)}")

    print(f"\n[INFO] Test complete for BCM {pin}.")
    print("[INFO] Which state silenced the buzzer?")
    print("        HIGH → BUZZER_ACTIVE_HIGH = False  (set LOW to silence)")
    print("        LOW  → BUZZER_ACTIVE_HIGH = True   (set HIGH to silence)")
    print("        Neither → wrong pin or wiring issue")

    GPIO.cleanup()


def scan_pins(hold_sec: float) -> None:
    GPIO = _try_import_gpio()
    if GPIO is None:
        return

    print(f"\n[INFO] Scanning {len(_SAFE_SCAN_PINS)} safe GPIO pins — listen for buzzer on each.")
    print("[INFO] Each pin is set HIGH then LOW for a moment.\n")

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    results: list[tuple[int, str]] = []

    for pin in _SAFE_SCAN_PINS:
        label = _PROJECT_PINS.get(pin, "")
        reserved_note = f" [{label}]" if label else ""
        print(f"[SCAN] BCM {pin}{reserved_note} — HIGH {hold_sec:.1f}s then LOW {hold_sec:.1f}s")
        try:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)
            time.sleep(hold_sec)
            GPIO.output(pin, GPIO.LOW)
            time.sleep(hold_sec)
            results.append((pin, "tested"))
        except Exception as e:
            results.append((pin, f"error: {e}"))
            print(f"       Error: {e}")

    GPIO.cleanup()

    print(f"\n[DONE] Scan complete. Pins tested:")
    for pin, status in results:
        print(f"  BCM {pin}: {status}")
    print("\n[INFO] Note which pin number caused the buzzer to respond — use that as BUZZER_GPIO.")


def polarity_check(pin: int) -> None:
    """Quick interactive polarity check — hold each state until user presses Enter."""
    GPIO = _try_import_gpio()
    if GPIO is None:
        return

    print(f"\n[INFO] Interactive polarity check on BCM {pin}.")
    print("[INFO] We'll hold each state until you press Enter.\n")

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(pin, GPIO.OUT)

    GPIO.output(pin, GPIO.HIGH)
    input(f"[?] BCM {pin} = HIGH — buzzer ON or OFF? (press Enter to continue):")

    GPIO.output(pin, GPIO.LOW)
    input(f"[?] BCM {pin} = LOW  — buzzer ON or OFF? (press Enter to continue):")

    GPIO.cleanup()
    print("\n[INFO] Result:")
    print("  If buzzer OFF at HIGH → BUZZER_ACTIVE_HIGH = False")
    print("  If buzzer OFF at LOW  → BUZZER_ACTIVE_HIGH = True")


def project_config_check() -> None:
    print("\n[INFO] Current project buzzer config (src/config.py):")
    try:
        from src.config import BUZZER_ACTIVE_HIGH, BUZZER_BEEP_SEC, BUZZER_COUNTDOWN_ENABLED, BUZZER_GPIO
        print(f"  BUZZER_GPIO            = {BUZZER_GPIO}  (BCM {BUZZER_GPIO})")
        print(f"  BUZZER_ACTIVE_HIGH     = {BUZZER_ACTIVE_HIGH}")
        print(f"  BUZZER_COUNTDOWN_ENABLED = {BUZZER_COUNTDOWN_ENABLED}")
        print(f"  BUZZER_BEEP_SEC        = {BUZZER_BEEP_SEC}")
        silence_level = "LOW" if BUZZER_ACTIVE_HIGH else "HIGH"
        on_level = "HIGH" if BUZZER_ACTIVE_HIGH else "LOW"
        print(f"  → silence = {silence_level}, beep = {on_level}")
    except Exception as e:
        print(f"  [FAIL] Could not read config: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Buzzer GPIO diagnostic")
    ap.add_argument("--pin", type=int, default=18, help="BCM GPIO pin to test (default 18)")
    ap.add_argument("--hold-sec", type=float, default=3.0, help="Seconds to hold each state")
    ap.add_argument("--scan", action="store_true", help="Sweep all safe GPIO pins to find buzzer pin")
    ap.add_argument("--interactive", action="store_true", help="Hold each state until Enter is pressed")
    args = ap.parse_args()

    project_config_check()

    if args.scan:
        scan_pins(hold_sec=max(0.5, args.hold_sec))
    elif args.interactive:
        polarity_check(args.pin)
    else:
        test_pin(args.pin, hold_sec=max(1.0, args.hold_sec))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
