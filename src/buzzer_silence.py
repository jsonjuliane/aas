"""
Immediately silence the buzzer GPIO on startup.

Uses Linux sysfs GPIO so the pin state persists after this process exits
(RPi.GPIO resets pins on exit which would turn the buzzer back on).

Run this once at boot (before the main app):

    python -m src.buzzer_silence           # silence and exit
    python -m src.buzzer_silence --beep    # one short beep, then silence
    python -m src.buzzer_silence --verify  # print current GPIO state

Normally invoked by smartshell-buzzer-silence.service at early boot.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _sysfs_gpio_dir(pin: int) -> Path:
    return Path(f"/sys/class/gpio/gpio{pin}")


def _sysfs_write(path: Path, value: str) -> None:
    path.write_text(value)


def _export_pin(pin: int) -> bool:
    gpio_dir = _sysfs_gpio_dir(pin)
    if not gpio_dir.exists():
        try:
            Path("/sys/class/gpio/export").write_text(str(pin))
            deadline = time.monotonic() + 1.0
            while not gpio_dir.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
        except PermissionError:
            print(
                f"[buzzer-silence] Permission denied on /sys/class/gpio/export.\n"
                f"                 Run as root or add user to 'gpio' group.",
                file=sys.stderr,
            )
            return False
        except OSError as e:
            if e.errno == 22:
                # EINVAL: pin already exported/claimed by another driver (e.g. pigpiod, PWM).
                # The sysfs directory may still be usable; try to continue.
                pass
            else:
                print(f"[buzzer-silence] Export failed: {e}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"[buzzer-silence] Export failed: {e}", file=sys.stderr)
            return False
    # Even if export returned EINVAL, directory may exist; fall through to RPi.GPIO fallback.
    return True  # attempt direction/value write regardless


def silence_via_sysfs(pin: int, silent_level: int) -> bool:
    """
    Set GPIO pin to output and drive to silent_level (0=LOW, 1=HIGH).
    State persists after process exits.
    """
    _export_pin(pin)  # best-effort; continue even on EINVAL

    gpio_dir = _sysfs_gpio_dir(pin)
    if gpio_dir.exists():
        try:
            _sysfs_write(gpio_dir / "direction", "out")
            _sysfs_write(gpio_dir / "value", str(silent_level))
            return True
        except Exception as e:
            print(f"[buzzer-silence] sysfs write failed: {e}", file=sys.stderr)

    # Fallback 1: raspi-gpio CLI (pre-installed on Pi OS Bullseye+)
    if _silence_via_raspi_gpio(pin, silent_level):
        return True

    # Fallback 2: RPi.GPIO (pin resets on exit but better than nothing)
    return _silence_via_rpigpio(pin, silent_level)


def _silence_via_raspi_gpio(pin: int, silent_level: int) -> bool:
    """Use raspi-gpio CLI to set pin output level (state persists)."""
    import shutil, subprocess
    if not shutil.which("raspi-gpio"):
        return False
    level_str = "dh" if silent_level else "dl"  # drive high / drive low
    try:
        result = subprocess.run(
            ["raspi-gpio", "set", str(pin), "op", level_str],
            capture_output=True, timeout=3,
        )
        if result.returncode == 0:
            print(f"[buzzer-silence] raspi-gpio: GPIO{pin} set to {'HIGH' if silent_level else 'LOW'}.")
            return True
    except Exception:
        pass
    return False


def _silence_via_rpigpio(pin: int, silent_level: int) -> bool:
    """Last-resort RPi.GPIO (note: pin resets on process exit)."""
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH if silent_level else GPIO.LOW)
        print(
            f"[buzzer-silence] RPi.GPIO: GPIO{pin} set. "
            "(Note: pin resets when this process exits — add pull-down resistor for permanent fix.)"
        )
        return True
    except Exception as e:
        print(f"[buzzer-silence] RPi.GPIO fallback failed: {e}", file=sys.stderr)
        return False


def beep_via_sysfs(pin: int, on_level: int, silent_level: int, duration_sec: float) -> bool:
    _export_pin(pin)
    gpio_dir = _sysfs_gpio_dir(pin)
    if gpio_dir.exists():
        try:
            _sysfs_write(gpio_dir / "direction", "out")
            _sysfs_write(gpio_dir / "value", str(on_level))
            time.sleep(max(0.05, duration_sec))
            _sysfs_write(gpio_dir / "value", str(silent_level))
            return True
        except Exception as e:
            print(f"[buzzer-silence] beep failed: {e}", file=sys.stderr)
    # fallback: RPi.GPIO beep
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH if on_level else GPIO.LOW)
        time.sleep(max(0.05, duration_sec))
        GPIO.output(pin, GPIO.HIGH if silent_level else GPIO.LOW)
        return True
    except Exception as e:
        print(f"[buzzer-silence] beep fallback failed: {e}", file=sys.stderr)
        return False


def verify_state(pin: int) -> None:
    gpio_dir = _sysfs_gpio_dir(pin)
    if not gpio_dir.exists():
        print(f"[buzzer-silence] GPIO{pin} not exported (not yet set by this tool).")
        return
    try:
        direction = (gpio_dir / "direction").read_text().strip()
        value = (gpio_dir / "value").read_text().strip()
        level = "HIGH" if value == "1" else "LOW"
        print(f"[buzzer-silence] GPIO{pin}: direction={direction} value={value} ({level})")
    except Exception as e:
        print(f"[buzzer-silence] Could not read state: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Silence buzzer GPIO (sysfs, persists after exit)")
    ap.add_argument("--beep", action="store_true", help="One short beep before silencing")
    ap.add_argument("--verify", action="store_true", help="Print current GPIO state and exit")
    args = ap.parse_args()

    from src.config import BUZZER_ACTIVE_HIGH, BUZZER_BEEP_SEC, BUZZER_GPIO

    # BUZZER_ACTIVE_HIGH=True means: HIGH=on, LOW=silent
    silent_level = 0 if BUZZER_ACTIVE_HIGH else 1  # 0=LOW, 1=HIGH
    on_level = 1 if BUZZER_ACTIVE_HIGH else 0

    if args.verify:
        verify_state(BUZZER_GPIO)
        return 0

    if args.beep:
        ok = beep_via_sysfs(BUZZER_GPIO, on_level, silent_level, BUZZER_BEEP_SEC)
        if not ok:
            return 1
    else:
        ok = silence_via_sysfs(BUZZER_GPIO, silent_level)
        if not ok:
            return 1

    level_name = "LOW" if silent_level == 0 else "HIGH"
    print(f"[buzzer-silence] GPIO{BUZZER_GPIO} → {level_name} (silent). State persists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
