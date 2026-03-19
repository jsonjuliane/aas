"""
SmartShell — Cancel mechanism during countdown.

Phase 1: GPIO button. Phase 3 will add voice command.
See docs/features/06_cancel.md.
"""

from __future__ import annotations

import time

from src.config import CANCEL_BUTTON_GPIO


def init() -> None:
    """Initialize cancel mechanism (GPIO button). Call once at startup."""
    try:
        import RPi.GPIO as GPIO

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(CANCEL_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    except (ImportError, RuntimeError):
        pass  # Not on Pi or GPIO unavailable


def wait_for_cancel(timeout_sec: float, dry_run: bool = False) -> bool:
    """
    Block until cancel button pressed or timeout.

    Polls GPIO button. Returns True if cancel detected, False on timeout.

    Args:
        timeout_sec: Max seconds to wait.
        dry_run: If True, always returns False (no hardware).

    Returns:
        True if user cancelled, False if timeout.
    """
    if dry_run:
        time.sleep(min(0.5, timeout_sec))  # Brief pause for demo
        return False
    try:
        import RPi.GPIO as GPIO

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if GPIO.input(CANCEL_BUTTON_GPIO) == GPIO.LOW:
                return True  # Button pressed (active low with pull-up)
            time.sleep(0.05)
        return False
    except (ImportError, RuntimeError):
        return False
