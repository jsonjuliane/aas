"""
SmartShell — Main entry point.

Runnable in Thonny on Raspberry Pi. Detects impact, runs countdown and SMS,
then resumes monitoring (always-on loop until Ctrl+C).

Usage:
    python -m src.main
    python -m src.main --dry-run        # No hardware; simulate for development
    python -m src.main --core-flow-only # Init + monitor impact detection only
    python -m src.main --test-alert     # Run one full alert cycle immediately (bench test)
    python -m src.main --test-alert --test-lat 14.299 --test-lon 121.060 --disable-sms-send  # Spoof GPS (Langkiwa)
"""

from __future__ import annotations

import argparse
import audioop
import contextlib
import os
import sys
import threading
import time
from dataclasses import dataclass
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
    MP3_DEFAULT_TRACK,
    MP3_DEFAULT_VOLUME,
    VOICE_CANCEL_KEYWORD_ENABLED,
    VOICE_CANCEL_SOUND_ENABLED,
    VOICE_SOUND_CHUNK_SIZE,
    VOICE_SOUND_RMS_SUSTAIN_CHUNKS,
    VOICE_SOUND_RMS_THRESHOLD,
    VOICE_SOUND_SAMPLE_RATE,
)
from src import (
    audio_mp3,
    buzzer_hw,
    cancel,
    contacts,
    gps,
    gsm_alert,
    gsm_sim800l,
    hardware_check,
    logging_store,
    sensor_mpu6050,
    voice_cancel,
)


@contextlib.contextmanager
def _suppress_native_stderr():
    """
    Temporarily suppress native stderr noise (ALSA/JACK via PortAudio).
    """
    try:
        stderr_fd = sys.stderr.fileno()
    except Exception:
        yield
        return

    saved_fd = os.dup(stderr_fd)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, stderr_fd)
        yield
    finally:
        os.dup2(saved_fd, stderr_fd)
        os.close(devnull_fd)
        os.close(saved_fd)


@dataclass
class VoiceCancelContext:
    """Microphone resources for cancel window (sound level and/or keyword)."""

    recognizer: object | None = None
    mic: object | None = None
    speech_ok: bool = False
    keyword_session: voice_cancel.VoiceKeywordSession | None = None
    pa: object | None = None
    stream: object | None = None
    sound_ok: bool = False
    selected_device_index: int | None = None


def _voice_cancel_capabilities_payload(ctx: VoiceCancelContext) -> dict[str, object]:
    """Structured mic paths for JSON logs."""
    return {
        "mic_device_index": ctx.selected_device_index,
        "sound_level_cancel": bool(ctx.sound_ok),
        "keyword_cancel_configured": bool(VOICE_CANCEL_KEYWORD_ENABLED),
        "keyword_cancel_ready": bool(ctx.speech_ok),
        "any_mic_active": bool(
            ctx.sound_ok or (VOICE_CANCEL_KEYWORD_ENABLED and ctx.speech_ok)
        ),
    }


def _close_voice_cancel_context(ctx: VoiceCancelContext) -> None:
    voice_cancel.close_keyword_session(ctx.keyword_session)
    ctx.keyword_session = None
    ctx.recognizer = None
    ctx.mic = None
    if ctx.stream is not None:
        try:
            ctx.stream.stop_stream()
            ctx.stream.close()
        except Exception:
            pass
        ctx.stream = None
    if ctx.pa is not None:
        try:
            ctx.pa.terminate()
        except Exception:
            pass
        ctx.pa = None


def _log_mic_cancel_closed(
    ctx: VoiceCancelContext,
    *,
    dry_run: bool,
    cancelled: bool,
    cancel_reason: str,
) -> None:
    """JSONL + console after countdown window ends (before resources are released)."""
    if dry_run:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    caps = _voice_cancel_capabilities_payload(ctx)
    logging_store.log_event(
        {
            "event": "mic_cancel_closed",
            "timestamp": ts,
            "cancelled": cancelled,
            "cancel_reason": cancel_reason,
            **caps,
        }
    )
    active = bool(caps.get("any_mic_active"))
    print(
        f"[Mic] Closed after countdown (cancelled={cancelled}, reason={cancel_reason!r}, "
        f"had_mic_path={active})."
    )


def _prepare_voice_cancel(
    dry_run: bool,
    voice_cancel_keyword: str,
    voice_device_index: int | None,
) -> VoiceCancelContext:
    """
    Open mic paths before countdown audio: optional PyAudio RMS stream and/or SpeechRecognition.
    """
    ctx = VoiceCancelContext()
    if dry_run:
        return ctx

    selected_voice_device_index = voice_device_index
    selected_voice_device_name = "system default"

    if VOICE_CANCEL_SOUND_ENABLED or VOICE_CANCEL_KEYWORD_ENABLED:
        try:
            import speech_recognition as sr

            with _suppress_native_stderr():
                mic_names = sr.Microphone.list_microphone_names()

            if selected_voice_device_index is None and mic_names:
                selected_voice_device_index = 0

            if (
                selected_voice_device_index is not None
                and 0 <= selected_voice_device_index < len(mic_names)
            ):
                selected_voice_device_name = mic_names[selected_voice_device_index]

            ctx.selected_device_index = selected_voice_device_index
        except ImportError:
            if VOICE_CANCEL_KEYWORD_ENABLED:
                print("Voice keyword cancel unavailable: SpeechRecognition not installed.")
        except Exception as e:
            print(f"Voice cancel mic enumeration failed: {e}")

    keyword = voice_cancel_keyword.strip().lower() or "cancel"

    if VOICE_CANCEL_KEYWORD_ENABLED:
        with _suppress_native_stderr():
            session = voice_cancel.open_keyword_session(
                device_index=ctx.selected_device_index,
                keyword=keyword,
            )
        if session is not None:
            ctx.keyword_session = session
            ctx.recognizer = session.recognizer
            ctx.mic = session.microphone
            ctx.speech_ok = True
            selected_voice_device_name = session.device_name or selected_voice_device_name
            ctx.selected_device_index = session.device_index
            print(
                f"Voice keyword cancel enabled (keyword='{keyword}', "
                f"mic_index={ctx.selected_device_index}, mic='{selected_voice_device_name}', "
                f"energy_threshold={session.energy_threshold:.0f})."
            )
        else:
            print("Voice keyword cancel unavailable (mic open or SpeechRecognition failed).")

    if VOICE_CANCEL_SOUND_ENABLED:
        try:
            import pyaudio

            with _suppress_native_stderr():
                pa = pyaudio.PyAudio()
            stream = None
            for rate in (VOICE_SOUND_SAMPLE_RATE, 44100, 48000):
                try:
                    with _suppress_native_stderr():
                        stream = pa.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=rate,
                            input=True,
                            input_device_index=ctx.selected_device_index,
                            frames_per_buffer=VOICE_SOUND_CHUNK_SIZE,
                        )
                    break
                except Exception:
                    stream = None
                    continue
            if stream is not None:
                ctx.pa = pa
                ctx.stream = stream
                ctx.sound_ok = True
                print(
                    "Sound-level cancel enabled "
                    f"(mic_index={ctx.selected_device_index}, RMS≥{VOICE_SOUND_RMS_THRESHOLD}, "
                    f"sustain={VOICE_SOUND_RMS_SUSTAIN_CHUNKS} chunks). "
                    "Speak or tap the mic to abort."
                )
            else:
                pa.terminate()
                print("Sound-level cancel unavailable: PyAudio could not open the microphone.")
        except Exception as e:
            print(f"Sound-level cancel unavailable: {e}")

    if not ctx.speech_ok and not ctx.sound_ok:
        print("No voice/sound cancel path active (button cancel still works if wired).")

    return ctx


def _signal_monitoring_active(*, dry_run: bool, resumed: bool = False) -> None:
    """Triple buzzer beep + log line when impact monitoring is active."""
    label = "Resuming impact monitoring" if resumed else "Impact monitoring active"
    print(f"{label}. Press Ctrl+C to stop.")
    logging_store.log_event(
        {
            "event": "monitoring_resumed" if resumed else "monitoring_started",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "dry_run": dry_run,
        }
    )
    if dry_run:
        print("[dry-run] Would play monitor-ready buzzer (3 quick beeps).")
        return
    if buzzer_hw.monitoring_ready_beeps():
        return
    print("[buzzer] Monitor-ready beep skipped (GPIO unavailable or disabled).")


def run(
    dry_run: bool = False,
    core_flow_only: bool = False,
    test_alert_immediately: bool = False,
    disable_sms_send: bool = False,
    voice_cancel_keyword: str = "cancel",
    voice_device_index: int | None = None,
    poll_interval_sec: float = 0.05,
    action_cooldown_sec: float = ACTION_COOLDOWN_SEC,
    impact_log_cooldown_sec: float = IMPACT_LOG_COOLDOWN_SEC,
    test_location: tuple[float, float] | None = None,
) -> None:
    """
    Main loop: monitor sensor; on impact run countdown + SMS, then resume monitoring.

    Args:
        dry_run: If True, no hardware access; simulate.
        core_flow_only: If True, skip countdown/cancel/GPS/SMS side effects.
        test_alert_immediately: If True, run one full alert cycle on first loop (bench test).
        poll_interval_sec: Seconds between sensor polls.
    """
    sensor = sensor_mpu6050.SensorMPU6050(dry_run=dry_run)
    audio_mod = audio_mp3.AudioMP3(dry_run=dry_run)

    try:
        if not dry_run:
            sensor.calibrate()
            cancel.init()
        audio_mod.open()
        if not dry_run:
            buzzer_hw.silence()
        _print_init_status(
            dry_run=dry_run,
            core_flow_only=core_flow_only,
            audio_mod=audio_mod,
        )

        if dry_run:
            print("Simulation mode is running.")
        _signal_monitoring_active(dry_run=dry_run, resumed=False)

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
                        disable_sms_send=disable_sms_send,
                        voice_cancel_keyword=voice_cancel_keyword,
                        voice_device_index=voice_device_index,
                        test_location=test_location,
                    )
                    if not core_flow_only:
                        _signal_monitoring_active(dry_run=dry_run, resumed=True)
                continue

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
                        disable_sms_send=disable_sms_send,
                        voice_cancel_keyword=voice_cancel_keyword,
                        voice_device_index=voice_device_index,
                        test_location=test_location,
                    )
                    _signal_monitoring_active(dry_run=dry_run, resumed=True)
            time.sleep(poll_interval_sec)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sensor.close()
        audio_mod.close()
        if not dry_run:
            buzzer_hw.silence()


def _handle_alert(
    sensor: sensor_mpu6050.SensorMPU6050,
    audio_mod: audio_mp3.AudioMP3,
    dry_run: bool,
    disable_sms_send: bool,
    voice_cancel_keyword: str,
    voice_device_index: int | None,
    test_location: tuple[float, float] | None = None,
) -> None:
    """Play countdown audio and log event for this phase."""
    ax, ay, az = sensor.read_g() if not dry_run else (0.0, 0.0, 0.0)
    location = _resolve_collision_location(dry_run=dry_run, test_location=test_location)
    track_num, selection_reason = _select_countdown_audio(audio_mod=audio_mod, dry_run=dry_run)

    voice_ctx = _prepare_voice_cancel(dry_run, voice_cancel_keyword, voice_device_index)
    if not dry_run:
        caps = _voice_cancel_capabilities_payload(voice_ctx)
        ts_mic = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        logging_store.log_event(
            {
                "event": "mic_cancel_ready",
                "timestamp": ts_mic,
                **caps,
            }
        )
        if caps.get("any_mic_active"):
            print(
                f"[Mic] Ready — device_index={voice_ctx.selected_device_index}, "
                f"sound_level={caps.get('sound_level_cancel')}, "
                f"keyword_path={caps.get('keyword_cancel_ready') and VOICE_CANCEL_KEYWORD_ENABLED}."
            )
        else:
            print("[Mic] No microphone cancel path active for this alert (button cancel only).")

    cancelled = False
    cancel_reason = "before_cancel_window"
    play_status: dict = {}
    try:
        # DFPlayer layout: SD:/mp3/0001.mp3 etc.; command 0x03 (see mp3_play_command log).
        if not dry_run:
            audio_mod.set_volume(MP3_DEFAULT_VOLUME)
            print(f"[MP3] Volume set to {max(0, min(30, int(MP3_DEFAULT_VOLUME)))}")
        play_status = audio_mod.play_track_with_status(track_num)
        ts_cmd = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        logging_store.log_event(
            {
                "event": "mp3_play_command",
                "timestamp": ts_cmd,
                "volume": max(0, min(30, int(MP3_DEFAULT_VOLUME))) if not dry_run else None,
                "selection_reason": selection_reason,
                "ok": bool(play_status.get("ok")),
                "reason": play_status.get("reason"),
                "transport": play_status.get("transport"),
                "serial_device": play_status.get("serial_device"),
                "command": play_status.get("command"),
                "param": play_status.get("param"),
                "packet_hex": play_status.get("packet_hex"),
                "path_hint": play_status.get("path_hint"),
            }
        )
        if play_status.get("ok"):
            print(
                f"[MP3] Play command sent (0x{int(play_status.get('command', 0)):02x} "
                f"track={play_status.get('param')}, transport={play_status.get('transport')}, "
                f"serial={play_status.get('serial_device') or 'n/a'}, "
                f"packet={play_status.get('packet_hex')})"
            )
        else:
            print(
                f"[MP3] Play command failed: {play_status.get('reason')} "
                f"(transport={play_status.get('transport')}); "
                "module may not receive UART — check TX wiring and power."
            )
        print(f"Countdown audio selected: mp3/{track_num:04d}.mp3 ({selection_reason})")
        cancelled, cancel_reason = _wait_for_cancel_window(
            timeout_sec=max(0.5, float(COUNTDOWN_SECONDS)),
            dry_run=dry_run,
            audio_mod=audio_mod,
            voice_cancel_keyword=voice_cancel_keyword,
            voice_ctx=voice_ctx,
        )
    finally:
        _log_mic_cancel_closed(
            voice_ctx,
            dry_run=dry_run,
            cancelled=cancelled,
            cancel_reason=cancel_reason,
        )
        _close_voice_cancel_context(voice_ctx)
    audio_mod.stop()
    if cancelled:
        print(f"Countdown cancelled ({cancel_reason}). SMS flow aborted.")
        logging_store.log_event(
            {
                "event": "alert_cancelled",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "reason": cancel_reason,
                "audio_selected": {
                    "path": f"mp3/{track_num:04d}.mp3",
                    "track": track_num,
                    "reason": selection_reason,
                },
                "mp3_command": {
                    "ok": bool(play_status.get("ok")),
                    "reason": play_status.get("reason"),
                    "transport": play_status.get("transport"),
                    "packet_hex": play_status.get("packet_hex"),
                },
            }
        )
        return
    print("Countdown window complete.")
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
                "path": f"mp3/{track_num:04d}.mp3",
                "track": track_num,
                "reason": selection_reason,
            },
            "mp3_command": {
                "ok": bool(play_status.get("ok")),
                "reason": play_status.get("reason"),
                "transport": play_status.get("transport"),
                "packet_hex": play_status.get("packet_hex"),
            },
            "collision_location": location,
        }
    )
    _send_alert_sms(location=location, dry_run=dry_run, disable_sms_send=disable_sms_send)


def _wait_for_cancel_window(
    timeout_sec: float,
    dry_run: bool,
    audio_mod: audio_mp3.AudioMP3,
    voice_cancel_keyword: str,
    *,
    voice_ctx: VoiceCancelContext,
) -> tuple[bool, str]:
    """
    Wait through countdown window and check cancellation sources.

    Returns:
        (cancelled, reason)
    """
    timeout_sec = max(0.2, float(timeout_sec))
    keyword = voice_cancel_keyword.strip().lower() or "cancel"
    playback_feedback_known = False
    playback_done = False
    announced_audio_mode = False
    loud_streak = 0
    buzzer_ready = False
    if not dry_run:
        buzzer_ready = bool(buzzer_hw.silence())

    t_start = time.monotonic()
    t_fallback_end = t_start + timeout_sec
    # Safety cap to avoid hanging forever if module status gets stuck as "playing".
    t_hard_end = t_start + max(timeout_sec + 120.0, timeout_sec * 4.0)

    stop_tick = threading.Event()
    playback_known_shared = [False]

    def _fallback_second_ticker() -> None:
        """Wall-clock fallback countdown logs (survives main-thread blocking)."""
        last_rem: int | None = None
        while not stop_tick.is_set():
            if playback_known_shared[0]:
                return
            now = time.monotonic()
            if now >= t_fallback_end:
                if last_rem != 0:
                    print("Cancel window (fallback): 0s remaining...")
                return
            rem = max(0, int(t_fallback_end - now + 0.999))
            if rem != last_rem:
                print(f"Cancel window (fallback): {rem}s remaining...")
                if buzzer_ready and rem > 0:
                    buzzer_hw.countdown_tick_beep(rem)
                last_rem = rem
            time.sleep(0.05)

    tick_thread = threading.Thread(target=_fallback_second_ticker, daemon=True)
    tick_thread.start()

    keyword_bg_started = False
    if (
        not dry_run
        and VOICE_CANCEL_KEYWORD_ENABLED
        and voice_ctx.speech_ok
        and voice_ctx.keyword_session is not None
    ):
        keyword_bg_started = voice_cancel.start_background_keyword_listen(voice_ctx.keyword_session)
        if keyword_bg_started:
            print(
                f"[Mic] Background keyword listener active "
                f"(say '{keyword}' clearly; needs internet for Google STT)."
            )
        else:
            print("[Mic] Background keyword listener failed to start (button cancel still works).")

    if not dry_run:
        caps_listen = _voice_cancel_capabilities_payload(voice_ctx)
        ts_listen = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        logging_store.log_event(
            {
                "event": "mic_cancel_listening",
                "timestamp": ts_listen,
                "cancel_window_timeout_sec": timeout_sec,
                **caps_listen,
            }
        )
        if caps_listen.get("any_mic_active"):
            listen_parts: list[str] = []
            if voice_ctx.sound_ok:
                listen_parts.append("sound-level")
            if VOICE_CANCEL_KEYWORD_ENABLED and voice_ctx.speech_ok:
                listen_parts.append("keyword")
            print(
                f"[Mic] Listening during cancel window "
                f"({' + '.join(listen_parts)}); device_index={voice_ctx.selected_device_index}"
            )
        else:
            print("[Mic] Cancel window active — microphone paths inactive (button cancel only).")

    try:
        while time.monotonic() < t_hard_end:
            # GPIO/button cancel path
            if cancel.wait_for_cancel(timeout_sec=0.05, dry_run=dry_run):
                return True, "button_cancel"

            # Sound-level cancel (short non-blocking reads)
            if voice_ctx.sound_ok and voice_ctx.stream is not None:
                try:
                    raw = voice_ctx.stream.read(VOICE_SOUND_CHUNK_SIZE, exception_on_overflow=False)
                    rms = audioop.rms(raw, 2)
                    if rms >= VOICE_SOUND_RMS_THRESHOLD:
                        loud_streak += 1
                    else:
                        loud_streak = 0
                    if loud_streak >= VOICE_SOUND_RMS_SUSTAIN_CHUNKS:
                        return True, "sound_cancel"
                except Exception:
                    loud_streak = 0

            # Keyword cancel (background listener started above; non-blocking)
            if keyword_bg_started and voice_ctx.keyword_session is not None:
                if voice_ctx.keyword_session.cancel_requested:
                    return True, "voice_cancel"

            # Keep checking whether playback already ended when serial feedback exists.
            waited = audio_mod.wait_for_playback_end(timeout_sec=0.05, poll_interval_sec=0.05)
            if waited is True:
                playback_feedback_known = True
                playback_done = True
            elif waited is False:
                playback_feedback_known = True
                playback_done = False

            now = time.monotonic()
            if playback_feedback_known:
                playback_known_shared[0] = True
                if not announced_audio_mode:
                    print(
                        "Cancel window follows actual MP3 playback duration "
                        "(speak or use button cancel while audio is playing)."
                    )
                    announced_audio_mode = True
            # Fallback countdown lines are printed by _fallback_second_ticker.

            if playback_feedback_known:
                if playback_done:
                    return False, "audio_finished"
            elif now >= t_fallback_end:
                return False, "timeout_fallback"
            time.sleep(0.02)

        return False, "timeout_hard_cap"
    finally:
        stop_tick.set()
        if voice_ctx.keyword_session is not None:
            voice_cancel.stop_background_listening(voice_ctx.keyword_session)
        if buzzer_ready:
            buzzer_hw.silence()


def _resolve_collision_location(
    dry_run: bool,
    test_location: tuple[float, float] | None = None,
) -> dict | None:
    """Attempt GPS fix at collision time for logging (or use spoofed test coordinates)."""
    if test_location is not None:
        lat, lon = test_location
        print(f"GPS spoof (test): lat={lat}, lon={lon}")
        return {
            "lat": float(lat),
            "lon": float(lon),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "source": "test_spoof",
        }
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


def _select_countdown_audio(audio_mod: audio_mp3.AudioMP3, dry_run: bool) -> tuple[int, str]:
    """
    Select countdown clip for DFPlayer layout ``mp3/0001.mp3``, ``mp3/0002.mp3``, ...

    Uses command 0x03 via ``play_track`` (1-based index → 4-digit filename).

    Strategy:
      1) Dry-run: configured default track only.
      2) If TF file count is available, clamp ``MP3_DEFAULT_TRACK`` to 1..count.
      3) If feedback unavailable, use ``MP3_DEFAULT_TRACK`` anyway.
    """
    default_t = max(1, min(255, int(MP3_DEFAULT_TRACK)))
    if dry_run:
        return default_t, "dry_run default"
    tf_count = audio_mod.query_tf_file_count(timeout_sec=0.45)
    if tf_count is None:
        return default_t, "feedback unavailable; fallback default"
    if int(tf_count) <= 0:
        return default_t, "TF reports zero files; fallback default"
    n = int(tf_count)
    track = max(1, min(default_t, n))
    if track != default_t:
        return track, f"default track {default_t} clamped to {track} (TF reports {n} file(s))"
    return track, f"TF reports {n} file(s); playing track index {track}"


def _send_alert_sms(location: dict | None, dry_run: bool, disable_sms_send: bool) -> None:
    """Send SMS alerts and log success/failure with reasons."""
    if disable_sms_send:
        msg = "sms should have been sent, currently disabled for testing voice cancellation"
        print(f"GSM SMS disabled: {msg}")
        logging_store.log_event(
            {
                "event": "sms_alert_disabled",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "reason": msg,
            }
        )
        return
    try:
        phones, template, rider_name, home_barangay = contacts.load_family_contacts()
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

    gsm_probe = gsm_alert.wait_for_gsm_ready(dry_run=dry_run)
    if not dry_run and not gsm_alert.probe_sms_ready(gsm_probe):
        reason = f"gsm_not_ready:{gsm_alert.not_ready_reason(gsm_probe)}"
        print(f"GSM SMS failed: {reason} ({gsm_probe.get('detail')})")
        logging_store.log_event(
            {
                "event": "sms_alert_failed",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "reason": reason,
                "gsm_probe": gsm_probe,
                "csq": gsm_alert.probe_csq(gsm_probe),
            }
        )
        return

    lat = float(location["lat"]) if location and location.get("lat") is not None else None
    lon = float(location["lon"]) if location and location.get("lon") is not None else None

    try:
        from src import routing

        route = routing.get_recipients(
            lat,
            lon,
            family_phones=phones,
            home_barangay=home_barangay,
        )
        phones = list(route.get("phones", phones))
    except Exception as e:
        route = {
            "location_class": "unknown",
            "area_label": "Unknown (routing error)",
            "inside_binan": None,
            "lat": lat,
            "lon": lon,
            "phones": phones,
            "error": str(e),
        }
        print(f"Routing error: {e}")

    area = str(route.get("area_label", "Unknown (no GPS)"))
    home_rescuer = route.get("home_rescuer_phone")
    print(
        f"Routing: {area} (class={route.get('location_class')}, lat={lat}, lon={lon}, "
        f"recipients={len(phones)}, home_rescuer={home_rescuer})"
    )
    logging_store.log_event(
        {
            "event": "routing_decision",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            **route,
        }
    )

    message = contacts.format_alert_message(
        template=template,
        lat=lat,
        lon=lon,
        rider_name=rider_name,
        home_barangay=home_barangay,
        area=area,
        accident_barangay=route.get("accident_barangay")
        if route.get("accident_barangay")
        else None,
        notified=str(route.get("notified", "")),
    )
    sms_parts = contacts.message_parts_for_delivery(message)
    if len(sms_parts) == 1:
        print(f"GSM SMS body: {len(message)} chars, 1 part (GSM 7-bit).")
    else:
        print(
            f"GSM SMS body: {len(message)} chars → {len(sms_parts)} separate SMS "
            f"(run: python -m src.sms_config_check)"
        )

    modem = gsm_sim800l.GSMSIM800L(dry_run=dry_run)
    sent = 0
    failed: list[dict[str, object]] = []
    signal_snapshot = 99
    try:
        modem.open()
        signal_snapshot = modem.check_signal()
        for phone in phones:
            send_out, attempts_used = gsm_alert.send_sms_with_retries(
                modem=modem,
                phone=phone,
                message=message,
                dry_run=dry_run,
            )
            if bool(send_out["ok"]):
                sent += 1
            else:
                failed.append(
                    {
                        "phone": phone,
                        "reason": str(send_out["reason"]),
                        "attempts_used": attempts_used,
                        "signal_strength": int(send_out.get("signal_strength", 99)),
                        "cmgs_response_raw": str(send_out.get("cmgs_response_raw", "")),
                        "final_submit_response_raw": str(send_out.get("final_submit_response_raw", "")),
                        "cms_error_code": send_out.get("cms_error_code"),
                    }
                )
    finally:
        modem.close()

    if sent > 0:
        print(f"GSM SMS success: sent to {sent}/{len(phones)} contact(s), CSQ={signal_snapshot}.")
        if failed:
            print(f"GSM SMS partial failure details: {failed}")
        logging_store.log_event(
            {
                "event": "sms_alert_sent",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "sent_count": sent,
                "total_contacts": len(phones),
                "signal_strength": signal_snapshot,
                "gsm_probe": gsm_probe,
                "failed": failed,
            }
        )
    else:
        reason = str(failed[0]["reason"]) if failed else "unknown_send_failure"
        cms_code = failed[0].get("cms_error_code") if failed else None
        print(
            f"GSM SMS failed: no messages sent (reason: {reason}, "
            f"CSQ={signal_snapshot}, cms_error_code={cms_code})"
        )
        logging_store.log_event(
            {
                "event": "sms_alert_failed",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "reason": reason,
                "signal_strength": signal_snapshot,
                "cms_error_code": cms_code,
                "gsm_probe": gsm_probe,
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
        "--disable-sms-send",
        action="store_true",
        help="Do not send real SMS; log that SMS is intentionally disabled",
    )
    ap.add_argument(
        "--test-lat",
        type=float,
        default=None,
        help="Spoof GPS latitude for --test-alert only (requires --test-lon)",
    )
    ap.add_argument(
        "--test-lon",
        type=float,
        default=None,
        help="Spoof GPS longitude for --test-alert only (requires --test-lat)",
    )
    ap.add_argument(
        "--voice-cancel-keyword",
        type=str,
        default="cancel",
        help="Keyword used by microphone cancellation during countdown (default: cancel)",
    )
    ap.add_argument(
        "--voice-device-index",
        type=int,
        default=None,
        help="Optional microphone device index for SpeechRecognition",
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
    test_location: tuple[float, float] | None = None
    if args.test_lat is not None or args.test_lon is not None:
        if not test_now:
            ap.error("--test-lat/--test-lon are only allowed with --test-alert")
        if args.test_lat is None or args.test_lon is None:
            ap.error("--test-lat and --test-lon must be used together")
        test_location = (float(args.test_lat), float(args.test_lon))
    run(
        dry_run=args.dry_run,
        core_flow_only=args.core_flow_only,
        test_alert_immediately=test_now,
        disable_sms_send=bool(args.disable_sms_send),
        voice_cancel_keyword=str(args.voice_cancel_keyword),
        voice_device_index=args.voice_device_index,
        action_cooldown_sec=args.action_cooldown_sec,
        impact_log_cooldown_sec=args.impact_log_cooldown_sec,
        test_location=test_location,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
