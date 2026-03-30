"""
SmartShell — Main entry point.

Runnable in Thonny on Raspberry Pi. Detects impact, runs countdown,
allows cancel, sends SMS with GPS if not cancelled.

Usage:
    python -m src.main
    python -m src.main --dry-run        # No hardware; simulate for development
    python -m src.main --core-flow-only # Init + monitor impact detection only
    python -m src.main --test-alert     # Run one full alert cycle immediately (bench test)
    python -m src.main --silence-buzzer # Drive buzzer GPIO off, then exit (temp / bring-up)
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
    buzzer_hw,
    cancel,
    contacts,
    gps,
    gsm_sim800l,
    logging_store,
    sensor_mpu6050,
)


def run(
    dry_run: bool = False,
    core_flow_only: bool = False,
    test_alert_immediately: bool = False,
    poll_interval_sec: float = 0.05,
) -> None:
    """
    Main loop: monitor sensor, on impact run countdown → cancel check → SMS.

    Args:
        dry_run: If True, no hardware access; simulate.
        core_flow_only: If True, skip countdown/cancel/GPS/SMS side effects.
        test_alert_immediately: If True, run one full alert cycle on first iteration (bench test).
        poll_interval_sec: Seconds between sensor polls.
    """
    sensor = sensor_mpu6050.SensorMPU6050(dry_run=dry_run)
    gps_mod = gps.GPSModule(dry_run=dry_run)
    gsm_mod = gsm_sim800l.GSMSIM800L(dry_run=dry_run)
    audio_mod = audio_mp3.AudioMP3(dry_run=dry_run)

    try:
        if not dry_run:
            buzzer_hw.silence()
            sensor.calibrate()
            cancel.init()
        gps_mod.open()
        gsm_mod.open()
        audio_mod.open()
        _print_init_status(
            dry_run=dry_run,
            core_flow_only=core_flow_only,
            gps_mod=gps_mod,
            gsm_mod=gsm_mod,
        )

        if dry_run:
            print("SmartShell running in DRY RUN (no hardware). Use Ctrl+C to stop.")
        else:
            print("SmartShell monitoring. Press Ctrl+C to stop.")

        test_alert_done = False
        while True:
            if test_alert_immediately and not test_alert_done:
                test_alert_done = True
                print("[test-alert] Running one full alert cycle (no sensor wait).")
                if core_flow_only:
                    print("[core-flow] Impact path reached. Skipping countdown/GPS/SMS by design.")
                else:
                    _handle_alert(
                        sensor=sensor,
                        gps_mod=gps_mod,
                        gsm_mod=gsm_mod,
                        audio_mod=audio_mod,
                        dry_run=dry_run,
                    )
                continue

            if sensor.is_impact_detected():
                if core_flow_only:
                    print("Impact detected (core-flow). Validation passed; alert side effects skipped.")
                    logging_store.log_event(
                        {
                            "event": "impact_detected_core_flow",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                        }
                    )
                else:
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


def _print_init_status(
    dry_run: bool,
    core_flow_only: bool,
    gps_mod: gps.GPSModule,
    gsm_mod: gsm_sim800l.GSMSIM800L,
) -> None:
    """Print startup status for the top-priority modules."""
    if dry_run:
        print("Startup check (dry-run): sensor/GPS/GSM opens are simulated.")
        return
    gps_ok = gps_mod._ser is not None  # debug visibility for bench bring-up
    gsm_ok = gsm_mod._ser is not None  # debug visibility for bench bring-up
    print(f"Startup check: GPS serial {'OK' if gps_ok else 'NOT OPEN'}")
    print(f"Startup check: GSM serial {'OK' if gsm_ok else 'NOT OPEN'}")
    if core_flow_only:
        print("Mode: core-flow-only (init + monitoring + threshold/validation only).")


def main() -> int:
    """Entry point. Returns 0 on normal exit."""
    ap = argparse.ArgumentParser(description="SmartShell accident alert system")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without hardware (for development)",
    )
    ap.add_argument(
        "--core-flow-only",
        action="store_true",
        help="Run only initialization + monitoring/threshold/validation; skip alert actions",
    )
    ap.add_argument(
        "--test-alert",
        action="store_true",
        help="Run one full alert cycle immediately (countdown, cancel window, SMS path)",
    )
    ap.add_argument(
        "--trigger",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    ap.add_argument(
        "--silence-buzzer",
        action="store_true",
        help="Drive buzzer GPIO to off and exit (bring-up / stuck buzzer)",
    )
    args = ap.parse_args()
    if args.silence_buzzer:
        if buzzer_hw.silence():
            print(
                "Buzzer GPIO driven to silent level (see BUZZER_ACTIVE_HIGH in src/config.py). "
                "If it still sounds, try BUZZER_ACTIVE_HIGH = False."
            )
            return 0
        print(
            "Could not drive buzzer GPIO (not a Raspberry Pi, missing RPi.GPIO, or GPIO error)."
        )
        return 1
    test_now = args.test_alert or args.trigger
    run(
        dry_run=args.dry_run,
        core_flow_only=args.core_flow_only,
        test_alert_immediately=test_now,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
