"""
GPIO buzzer line (prototype harness).

Phase 1: drive the pin to a known “off” state so a floating GPIO 18 does not
leave the transistor/buzzer on at power-up. Phase 4 will add SMS-driven beeps.

If silence does the opposite (buzzer stays on), set BUZZER_ACTIVE_HIGH = False
in src/config.py (inverted driver).
"""

from __future__ import annotations


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
