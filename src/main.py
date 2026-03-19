"""
SmartShell — Main entry point.

Runnable in Thonny on Raspberry Pi. Detects impact, runs countdown,
allows cancel, sends SMS with GPS if not cancelled.

Usage:
    python -m src.main
    python -m src.main --dry-run   # No hardware; simulate for development
    python -m src.main --trigger   # Force trigger on first poll (for testing)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import COUNTDOWN_SECONDS
from src import (
    audio_mp3,
    cancel,
    contacts,
    gps,
    gsm_sim800l,
    logging_store,
    sensor_mpu6050,
)


def run(
    dry_run: bool = False,
    force_trigger: bool = False,
    poll_interval_sec: float = 0.05,
) -> None:
    """
    Main loop: monitor sensor, on impact run countdown → cancel check → SMS.

    Args:
        dry_run: If True, no hardware access; simulate.
        force_trigger: If True, trigger alert on first poll (for testing).
        poll_interval_sec: Seconds between sensor polls.
    """
    sensor = sensor_mpu6050.SensorMPU6050(dry_run=dry_run)
    gps_mod = gps.GPSModule(dry_run=dry_run)
    gsm_mod = gsm_sim800l.GSMSIM800L(dry_run=dry_run)
    audio_mod = audio_mp3.AudioMP3(dry_run=dry_run)

    try:
        if not dry_run:
            sensor.calibrate()
            cancel.init()
        gps_mod.open()
        gsm_mod.open()
        audio_mod.open()

        if dry_run:
            print("SmartShell running in DRY RUN (no hardware). Use Ctrl+C to stop.")
        else:
            print("SmartShell monitoring. Press Ctrl+C to stop.")

        triggered_once = False
        while True:
            if force_trigger and not triggered_once:
                triggered_once = True
                print("[DRY] Forced trigger for testing.")
                _handle_alert(
                    sensor=sensor,
                    gps_mod=gps_mod,
                    gsm_mod=gsm_mod,
                    audio_mod=audio_mod,
                    dry_run=dry_run,
                )
                continue

            if sensor.is_impact_detected():
                print("Impact detected. Starting countdown...")
                _handle_alert(
                    sensor=sensor,
                    gps_mod=gps_mod,
                    gsm_mod=gsm_mod,
                    audio_mod=audio_mod,
                    dry_run=dry_run,
                )
            time.sleep(poll_interval_sec)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sensor.close()
        gps_mod.close()
        gsm_mod.close()
        audio_mod.close()


def _handle_alert(
    sensor: sensor_mpu6050.SensorMPU6050,
    gps_mod: gps.GPSModule,
    gsm_mod: gsm_sim800l.GSMSIM800L,
    audio_mod: audio_mp3.AudioMP3,
    dry_run: bool,
) -> None:
    """Run countdown, check cancel, send SMS if not cancelled."""
    ax, ay, az = sensor.read_g() if not dry_run else (0.0, 0.0, 0.0)
    try:
        phones, template = contacts.load_family_contacts()
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}")
        return

    # Play countdown audio
    audio_mod.play_track(1)

    # Wait for cancel
    cancelled = cancel.wait_for_cancel(COUNTDOWN_SECONDS, dry_run=dry_run)
    if cancelled:
        print("Alert cancelled by user.")
        logging_store.log_event(
            {
                "event": "alert_cancelled",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "accel_g": {"ax": ax, "ay": ay, "az": az},
            }
        )
        return

    # Get GPS and send SMS
    fix = gps_mod.get_fix(timeout_sec=5.0)
    lat = fix["lat"] if fix else None
    lon = fix["lon"] if fix else None
    msg = contacts.format_message(template, lat, lon)

    for phone in phones:
        ok = gsm_mod.send_sms(phone, msg)
        status = "sent" if ok else "failed"
        print(f"SMS to {phone}: {status}")

    logging_store.log_event(
        {
            "event": "alert_sent",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "accel_g": {"ax": ax, "ay": ay, "az": az},
            "lat": lat,
            "lon": lon,
            "recipients": phones,
            "cancelled": False,
        }
    )


def main() -> int:
    """Entry point. Returns 0 on normal exit."""
    ap = argparse.ArgumentParser(description="SmartShell accident alert system")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without hardware (for development)",
    )
    ap.add_argument(
        "--trigger",
        action="store_true",
        help="Force trigger on first poll (for testing)",
    )
    args = ap.parse_args()
    run(dry_run=args.dry_run, force_trigger=args.trigger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
