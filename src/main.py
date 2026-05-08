"""
SmartShell — Main entry point.

Runnable in Thonny on Raspberry Pi. Detects impact, runs countdown,
plays countdown audio, then exits.

Usage:
    python -m src.main
    python -m src.main --dry-run        # No hardware; simulate for development
    python -m src.main --core-flow-only # Init + monitor impact detection only
    python -m src.main --test-alert     # Run one full alert cycle immediately (bench test)
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

from src.config import (
    ACTION_COOLDOWN_SEC,
    COUNTDOWN_SECONDS,
    GPS_COLLISION_FIX_TIMEOUT_SEC,
    IMPACT_LOG_COOLDOWN_SEC,
    MP3_DEFAULT_FILE,
    MP3_DEFAULT_FOLDER,
    MP3_FOLDER_SCAN_MAX,
)
from src import (
    audio_mp3,
    contacts,
    gps,
    gsm_sim800l,
    hardware_check,
    logging_store,
    sensor_mpu6050,
)


def run(
    dry_run: bool = False,
    core_flow_only: bool = False,
    test_alert_immediately: bool = False,
    poll_interval_sec: float = 0.05,
    action_cooldown_sec: float = ACTION_COOLDOWN_SEC,
    impact_log_cooldown_sec: float = IMPACT_LOG_COOLDOWN_SEC,
) -> None:
    """
    Main loop: monitor sensor, on impact play countdown audio then exit.

    Args:
        dry_run: If True, no hardware access; simulate.
        core_flow_only: If True, skip countdown/cancel/GPS/SMS side effects.
        test_alert_immediately: If True, run one full alert cycle on first iteration (bench test).
        poll_interval_sec: Seconds between sensor polls.
    """
    sensor = sensor_mpu6050.SensorMPU6050(dry_run=dry_run)
    audio_mod = audio_mp3.AudioMP3(dry_run=dry_run)

    try:
        if not dry_run:
            sensor.calibrate()
        audio_mod.open()
        _print_init_status(
            dry_run=dry_run,
            core_flow_only=core_flow_only,
            audio_mod=audio_mod,
        )

        if dry_run:
            print("Simulation mode is running. Press Ctrl+C to stop.")
        else:
            print("Monitoring for impact events. Press Ctrl+C to stop.")

        test_alert_done = False
        last_action_at = -1e9
        last_impact_log_at = -1e9
        while True:
            if test_alert_immediately and not test_alert_done:
                test_alert_done = True
                print("[test-alert] Bench mode: triggering the countdown flow now.")
                if core_flow_only:
                    print("[core-flow] Test trigger reached. Action audio is skipped in this mode.")
                else:
                    _handle_alert(
                        sensor=sensor,
                        audio_mod=audio_mod,
                        dry_run=dry_run,
                    )
                return

            eval_data = sensor.evaluate_impact()
            now = time.monotonic()

            # Collision-test-like logging in main:
            # log only when impact is in 3..5g window, with explicit tilt/action booleans.
            if bool(eval_data["impact_window_hit"]):
                if (now - last_impact_log_at) >= max(0.0, impact_log_cooldown_sec):
                    logging_store.log_event(
                        {
                            "event": "impact_window_hit_main",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                            "metrics": {
                                "accel_mag_g": eval_data["accel_mag_g"],
                                "tilt_delta_g": eval_data["tilt_delta_g"],
                            },
                            "thresholds": eval_data["thresholds"],
                            "flags": {
                                "impact_window_hit": bool(eval_data["impact_window_hit"]),
                                "tilt_hit": bool(eval_data["tilt_hit"]),
                                "actual_collision": bool(eval_data["actual_collision"]),
                                # Action decision for this sample is set below.
                                "action_collision": False,
                            },
                            "accel_g": eval_data["accel_g"],
                            "gyro_dps": eval_data["gyro_dps"],
                        }
                    )
                    last_impact_log_at = now

            actual_collision = bool(eval_data["actual_collision"])
            in_action_cooldown = (now - last_action_at) < max(0.0, action_cooldown_sec)
            action_collision = actual_collision and (not in_action_cooldown) and (not core_flow_only)

            if actual_collision and in_action_cooldown:
                continue

            if actual_collision:
                last_action_at = now
                if core_flow_only:
                    print("Impact was validated. Core-flow mode keeps this as monitoring-only.")
                    logging_store.log_event(
                        {
                            "event": "impact_detected_core_flow",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                            "metrics": {
                                "accel_mag_g": eval_data["accel_mag_g"],
                                "tilt_delta_g": eval_data["tilt_delta_g"],
                            },
                            "thresholds": eval_data["thresholds"],
                            "flags": {
                                "impact_window_hit": bool(eval_data["impact_window_hit"]),
                                "tilt_hit": bool(eval_data["tilt_hit"]),
                                "actual_collision": actual_collision,
                                "action_collision": False,
                            },
                            "accel_g": eval_data["accel_g"],
                            "gyro_dps": eval_data["gyro_dps"],
                        }
                    )
                else:
                    print("Collision conditions met. Playing countdown audio now.")
                    logging_store.log_event(
                        {
                            "event": "impact_action_triggered",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                            "metrics": {
                                "accel_mag_g": eval_data["accel_mag_g"],
                                "tilt_delta_g": eval_data["tilt_delta_g"],
                            },
                            "thresholds": eval_data["thresholds"],
                            "flags": {
                                "impact_window_hit": bool(eval_data["impact_window_hit"]),
                                "tilt_hit": bool(eval_data["tilt_hit"]),
                                "actual_collision": actual_collision,
                                "action_collision": action_collision,
                            },
                            "accel_g": eval_data["accel_g"],
                            "gyro_dps": eval_data["gyro_dps"],
                        }
                    )
                    _handle_alert(
                        sensor=sensor,
                        audio_mod=audio_mod,
                        dry_run=dry_run,
                    )
                    return
            time.sleep(poll_interval_sec)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sensor.close()
        audio_mod.close()


def _handle_alert(
    sensor: sensor_mpu6050.SensorMPU6050,
    audio_mod: audio_mp3.AudioMP3,
    dry_run: bool,
) -> None:
    """Play countdown audio and log event for this phase."""
    ax, ay, az = sensor.read_g() if not dry_run else (0.0, 0.0, 0.0)
    location = _resolve_collision_location(dry_run=dry_run)
    folder_num, file_num, selection_reason = _select_countdown_audio(audio_mod=audio_mod, dry_run=dry_run)

    # Play countdown audio from folder-based DFPlayer layout.
    # Example: SD:/001/001.mp3 when folder=1 file=1.
    audio_mod.play_folder_track(folder_num, file_num)
    print(f"Countdown audio selected: {folder_num:03d}/{file_num:03d}.mp3 ({selection_reason})")
    waited = audio_mod.wait_for_playback_end(timeout_sec=max(1.0, float(COUNTDOWN_SECONDS) + 20.0))
    if waited is True:
        print("Countdown audio completed (detected from DFPlayer status).")
    elif waited is False:
        print(
            f"Countdown completion not detected before timeout; "
            f"using fallback window {COUNTDOWN_SECONDS}s."
        )
        time.sleep(max(0.0, float(COUNTDOWN_SECONDS)))
        audio_mod.stop()
    else:
        print(
            f"DFPlayer feedback unavailable; using fallback window {COUNTDOWN_SECONDS}s "
            "(wire DFPlayer TX->Pi RX for completion detection)."
        )
        time.sleep(max(0.0, float(COUNTDOWN_SECONDS)))
        audio_mod.stop()
    print("Countdown window complete. Exiting run.")
    if location is not None:
        print(
            f"Collision location: {location['lat']:.6f}, {location['lon']:.6f} "
            f"(fix timestamp {location['timestamp']})"
        )
    else:
        print("Collision location: unavailable (no GPS fix during timeout).")

    logging_store.log_event(
        {
            "event": "alert_countdown_played",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "accel_g": {"ax": ax, "ay": ay, "az": az},
            "countdown_seconds": COUNTDOWN_SECONDS,
            "audio_selected": {
                "folder": folder_num,
                "file": file_num,
                "reason": selection_reason,
            },
            "collision_location": location,
        }
    )
    _send_alert_sms(location=location, dry_run=dry_run)


def _resolve_collision_location(dry_run: bool) -> dict | None:
    """Attempt GPS fix at collision time for logging."""
    if dry_run:
        return {
            "lat": 0.0,
            "lon": 0.0,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "source": "dry_run",
        }
    gps_mod = gps.GPSModule(dry_run=False)
    try:
        gps_mod.open()
        fix = gps_mod.get_fix(timeout_sec=GPS_COLLISION_FIX_TIMEOUT_SEC)
        if not fix:
            return None
        return {
            "lat": float(fix["lat"]),
            "lon": float(fix["lon"]),
            "timestamp": str(fix.get("timestamp", "")),
            "source": "gps",
        }
    except Exception:
        return None
    finally:
        gps_mod.close()


def _select_countdown_audio(audio_mod: audio_mp3.AudioMP3, dry_run: bool) -> tuple[int, int, str]:
    """
    Select countdown audio target.

    Strategy:
      1) If dry-run: use configured default.
      2) If DFPlayer feedback is available, scan folder 1..MP3_FOLDER_SCAN_MAX and pick first with files.
      3) Fallback to configured default when feedback is unavailable.
    """
    fallback = (int(MP3_DEFAULT_FOLDER), int(MP3_DEFAULT_FILE), "default config")
    if dry_run:
        return fallback
    folder_upper = max(1, int(MP3_FOLDER_SCAN_MAX))
    for folder in range(1, folder_upper + 1):
        count = audio_mod.query_folder_file_count(folder, timeout_sec=0.45)
        if count is None:
            return (fallback[0], fallback[1], "feedback unavailable; fallback default")
        if count > 0:
            return (folder, 1, f"first non-empty folder found (files={count})")
    return (fallback[0], fallback[1], "no non-empty folder found; fallback default")


def _send_alert_sms(location: dict | None, dry_run: bool) -> None:
    """Send SMS alerts and log success/failure with reasons."""
    try:
        phones, template = contacts.load_family_contacts()
    except Exception as e:
        reason = f"contacts_load_failed:{e}"
        print(f"GSM SMS skipped: {reason}")
        logging_store.log_event(
            {
                "event": "sms_alert_failed",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "reason": reason,
            }
        )
        return

    gsm_probe = hardware_check.probe_gsm_readiness()
    if not dry_run and (not bool(gsm_probe.get("ok_at"))):
        reason = f"gsm_not_ready:{gsm_probe.get('detail')}"
        print(f"GSM SMS failed: {reason}")
        logging_store.log_event(
            {
                "event": "sms_alert_failed",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "reason": reason,
                "gsm_probe": gsm_probe,
            }
        )
        return

    lat = float(location["lat"]) if location and location.get("lat") is not None else None
    lon = float(location["lon"]) if location and location.get("lon") is not None else None
    message = contacts.format_message(template=template, lat=lat, lon=lon)

    modem = gsm_sim800l.GSMSIM800L(dry_run=dry_run)
    sent = 0
    failed: list[dict[str, str]] = []
    try:
        modem.open()
        for phone in phones:
            ok, reason = modem.send_sms_with_reason(phone=phone, text=message)
            if ok:
                sent += 1
            else:
                failed.append({"phone": phone, "reason": reason})
    finally:
        modem.close()

    if sent > 0:
        print(f"GSM SMS success: sent to {sent}/{len(phones)} contact(s).")
        if failed:
            print(f"GSM SMS partial failure details: {failed}")
        logging_store.log_event(
            {
                "event": "sms_alert_sent",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "sent_count": sent,
                "total_contacts": len(phones),
                "failed": failed,
            }
        )
    else:
        reason = failed[0]["reason"] if failed else "unknown_send_failure"
        print(f"GSM SMS failed: no messages sent (reason: {reason})")
        logging_store.log_event(
            {
                "event": "sms_alert_failed",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "reason": reason,
                "failed": failed,
                "total_contacts": len(phones),
            }
        )


def _print_init_status(
    dry_run: bool,
    core_flow_only: bool,
    audio_mod: audio_mp3.AudioMP3,
) -> None:
    """Print startup status for the current phase flow."""
    if dry_run:
        print("Systems ready (simulation). Sensor and audio checks are mocked.")
        return
    print("Systems ready. Sensor calibration complete. Running hardware readiness snapshot:")
    _print_runtime_hardware_snapshot(audio_mod=audio_mod)
    if core_flow_only:
        print("Core-flow mode active: monitoring and logs only, no action audio.")


def _print_runtime_hardware_snapshot(audio_mod: audio_mp3.AudioMP3) -> None:
    """Print quick hardware-ready snapshot for runtime flow."""
    gsm = hardware_check.probe_gsm_readiness()
    gsm_ok = bool(gsm.get("ok_at"))
    gsm_sms_ready = bool(gsm.get("sms_ready"))
    gsm_tag = "OK" if gsm_ok else "ERR"
    print(f"[{gsm_tag:5}] GSM link: {gsm.get('detail')}")
    sms_tag = "OK" if gsm_sms_ready else "ERR"
    print(f"[{sms_tag:5}] GSM SMS readiness: {'ready' if gsm_sms_ready else 'not ready'}")

    gps_mod = gps.GPSModule(dry_run=False)
    gps_ok = False
    gps_hint = "no NMEA sample yet"
    try:
        gps_mod.open()
        if gps_mod._ser is not None or gps_mod._pi is not None:
            deadline = time.monotonic() + 1.8
            while time.monotonic() < deadline:
                line = gps_mod.read_nmea_line()
                if line and line.startswith("$"):
                    gps_ok = True
                    gps_hint = f"NMEA seen: {line[:70]}"
                    break
                time.sleep(0.05)
        else:
            gps_hint = "transport not open (serial/pigpio unavailable)"
    finally:
        gps_mod.close()
    print(f"[{'OK' if gps_ok else 'ERR':5}] GPS stream check: {gps_hint}")

    mp3_transport_ok = (audio_mod._ser is not None) or (audio_mod._pi is not None)
    if not mp3_transport_ok:
        print(f"[{'ERR':5}] MP3 transport unavailable")
        return
    tf_count = audio_mod.query_tf_file_count(timeout_sec=0.6)
    if tf_count is None:
        print(
            f"[{'OK':5}] MP3 transport ready (TX path); no feedback response "
            "(wire DFPlayer TX->Pi RX for file-count diagnostics)"
        )
    elif tf_count <= 0:
        print(f"[{'ERR':5}] MP3 feedback OK but TF file count is {tf_count} (check SD content)")
    else:
        print(f"[{'OK':5}] MP3 feedback OK; TF file count: {tf_count}")


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
        "--action-cooldown-sec",
        type=float,
        default=ACTION_COOLDOWN_SEC,
        help="Debounce true-collision action trigger (default from config)",
    )
    ap.add_argument(
        "--impact-log-cooldown-sec",
        type=float,
        default=IMPACT_LOG_COOLDOWN_SEC,
        help="Debounce impact-window logs (default from config)",
    )
    args = ap.parse_args()
    test_now = args.test_alert or args.trigger
    run(
        dry_run=args.dry_run,
        core_flow_only=args.core_flow_only,
        test_alert_immediately=test_now,
        action_cooldown_sec=args.action_cooldown_sec,
        impact_log_cooldown_sec=args.impact_log_cooldown_sec,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
