"""
GPIO buzzer helper for countdown fallback cues.

Uses a simple on/off pin drive via a transistor or active buzzer module.
If silence behaves inverted, set BUZZER_ACTIVE_HIGH=False in src/config.py.
"""

from __future__ import annotations

import time


def _levels() -> tuple[int, int] | None:
    """Return (on_level, off_level) for configured buzzer polarity."""
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        return None

    from src.config import BUZZER_ACTIVE_HIGH

    on = GPIO.HIGH if BUZZER_ACTIVE_HIGH else GPIO.LOW
    off = GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH
    return on, off


def silence() -> bool:
    """Drive buzzer GPIO to the silent level. Returns False if GPIO unavailable."""
    levels = _levels()
    if levels is None:
        return False

    try:
        import RPi.GPIO as GPIO
        from src.config import BUZZER_GPIO

        _on, off = levels
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(BUZZER_GPIO, GPIO.OUT)
        GPIO.output(BUZZER_GPIO, off)
        return True
    except Exception:
        return False


def beep(duration_sec: float = 0.08) -> bool:
    """Drive buzzer ON briefly, then OFF. Returns False if GPIO unavailable."""
    levels = _levels()
    if levels is None:
        return False

    duration_sec = max(0.02, float(duration_sec))
    try:
        import RPi.GPIO as GPIO
        from src.config import BUZZER_GPIO

        on, off = levels
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(BUZZER_GPIO, GPIO.OUT)
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


def countdown_tick_beep(seconds_remaining: int) -> bool:
    """Beep pattern for countdown: short beep per second, longer on final 3s."""
    from src.config import BUZZER_BEEP_SEC, BUZZER_FINAL_BEEP_SEC, BUZZER_COUNTDOWN_ENABLED

    if not BUZZER_COUNTDOWN_ENABLED:
        return False

    sec = int(seconds_remaining)
    if sec <= 3:
        return beep(BUZZER_FINAL_BEEP_SEC)
    return beep(BUZZER_BEEP_SEC)
