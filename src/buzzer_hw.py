"""
GPIO buzzer line (prototype harness).

Phase 1: drive the pin to a known “off” state so a floating GPIO 18 does not
leave the transistor/buzzer on at power-up. Phase 4 will add SMS-driven beeps.

If silence does the opposite (buzzer stays on), set BUZZER_ACTIVE_HIGH = False
in src/config.py (inverted driver).
"""

from __future__ import annotations

import time


def silence() -> bool:
    """Drive buzzer GPIO to the silent level. Returns False if GPIO is unavailable."""
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        return False
    from src.config import BUZZER_ACTIVE_HIGH, BUZZER_GPIO

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(BUZZER_GPIO, GPIO.OUT)
        off = GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH
        GPIO.output(BUZZER_GPIO, off)
    except Exception:
        return False
    return True


def test_beep(duration_sec: float = 1.0) -> bool:
    """
    Drive buzzer ON for duration_sec, then OFF (bench test).

    Uses BUZZER_ACTIVE_HIGH: HIGH = on for typical NPN driver.
    """
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        return False
    from src.config import BUZZER_ACTIVE_HIGH, BUZZER_GPIO

    duration_sec = max(0.05, float(duration_sec))
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(BUZZER_GPIO, GPIO.OUT)
        on = GPIO.HIGH if BUZZER_ACTIVE_HIGH else GPIO.LOW
        off = GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH
        GPIO.output(BUZZER_GPIO, on)
        time.sleep(duration_sec)
        GPIO.output(BUZZER_GPIO, off)
        return True
    except Exception:
        try:
            silence()
        except Exception:
            pass
        return False
