"""
GPIO buzzer helper for countdown fallback cues.

Each function sets up the pin, drives it, then calls GPIO.cleanup() — matching
the approach confirmed working in buzzer_silence.py. Cleanup returns the pin to
input mode; the buzzer module's internal pull keeps it silent between beeps.

If buzzer behavior is inverted, set BUZZER_ACTIVE_HIGH=False in src/config.py.
"""

from __future__ import annotations

import time


def _gpio_setup() -> tuple | None:
    """
    Return (GPIO, pin, on_level, off_level) or None if RPi.GPIO unavailable.
    """
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        return None

    from src.config import BUZZER_ACTIVE_HIGH, BUZZER_GPIO

    on  = GPIO.HIGH if BUZZER_ACTIVE_HIGH else GPIO.LOW
    off = GPIO.LOW  if BUZZER_ACTIVE_HIGH else GPIO.HIGH

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(BUZZER_GPIO, GPIO.OUT)

    return GPIO, BUZZER_GPIO, on, off


def silence() -> bool:
    """
    Drive buzzer to silent level then cleanup.
    Same pattern as buzzer_silence.py which is confirmed working.
    """
    result = _gpio_setup()
    if result is None:
        return False

    GPIO, pin, _on, off = result
    try:
        GPIO.output(pin, off)
        return True
    except Exception:
        return False
    finally:
        GPIO.cleanup(pin)


def beep(duration_sec: float = 0.08) -> bool:
    """
    Beep once: ON for duration_sec then OFF, then cleanup.
    """
    result = _gpio_setup()
    if result is None:
        return False

    GPIO, pin, on, off = result
    duration_sec = max(0.02, float(duration_sec))
    try:
        GPIO.output(pin, on)
        time.sleep(duration_sec)
        GPIO.output(pin, off)
        return True
    except Exception:
        return False
    finally:
        GPIO.cleanup(pin)


def monitoring_ready_beeps() -> bool:
    """
    Short triple beep to signal impact monitoring is active (startup or after alert).
    """
    from src.config import (
        BUZZER_MONITOR_READY_BEEP_SEC,
        BUZZER_MONITOR_READY_COUNT,
        BUZZER_MONITOR_READY_ENABLED,
        BUZZER_MONITOR_READY_GAP_SEC,
    )

    if not BUZZER_MONITOR_READY_ENABLED:
        return False
    count = max(1, int(BUZZER_MONITOR_READY_COUNT))
    beep_sec = max(0.02, float(BUZZER_MONITOR_READY_BEEP_SEC))
    gap_sec = max(0.02, float(BUZZER_MONITOR_READY_GAP_SEC))
    ok = True
    for i in range(count):
        if not beep(beep_sec):
            ok = False
        if i < count - 1:
            time.sleep(gap_sec)
    return ok


def countdown_tick_beep(seconds_remaining: int) -> bool:
    """
    One beep per countdown second.
    Short beep for seconds > 3; slightly longer for final 3 seconds.
    """
    from src.config import BUZZER_BEEP_SEC, BUZZER_COUNTDOWN_ENABLED, BUZZER_FINAL_BEEP_SEC

    if not BUZZER_COUNTDOWN_ENABLED:
        return False

    if int(seconds_remaining) <= 3:
        return beep(BUZZER_FINAL_BEEP_SEC)
    return beep(BUZZER_BEEP_SEC)
