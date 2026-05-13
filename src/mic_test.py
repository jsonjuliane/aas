"""
USB / system microphone bench test — listen until Ctrl+C.

Logs to console and appends JSON lines to logs/events_YYYY-MM-DD.jsonl (same as main).

Run on Raspberry Pi (venv active):

    python -m src.mic_test
    python -m src.mic_test --device-index 0 --threshold 1200
"""

from __future__ import annotations

import argparse
import audioop
import contextlib
import os
import sys
import time

from src.config import (
    VOICE_SOUND_CHUNK_SIZE,
    VOICE_SOUND_RMS_THRESHOLD,
    VOICE_SOUND_SAMPLE_RATE,
)
from src import logging_store


@contextlib.contextmanager
def _suppress_native_stderr():
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


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


def _list_input_devices() -> list[tuple[int, str]]:
    """(index, name) for PyAudio input-capable devices."""
    import pyaudio

    with _suppress_native_stderr():
        pa = pyaudio.PyAudio()
    try:
        out: list[tuple[int, str]] = []
        n = pa.get_device_count()
        for i in range(n):
            try:
                info = pa.get_device_info_by_index(i)
            except Exception:
                continue
            if int(info.get("maxInputChannels", 0)) < 1:
                continue
            name = str(info.get("name", "?"))
            out.append((i, name))
        return out
    finally:
        pa.terminate()


def _speech_mic_names() -> list[str] | None:
    try:
        import speech_recognition as sr

        with _suppress_native_stderr():
            return list(sr.Microphone.list_microphone_names())
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Listen on microphone until Ctrl+C; log device info and sound (RMS) events",
    )
    ap.add_argument(
        "--device-index",
        type=int,
        default=None,
        help="PyAudio input device index (default: system default input)",
    )
    ap.add_argument(
        "--threshold",
        type=int,
        default=None,
        help=f"audioop RMS threshold for 'sound detected' (default: {VOICE_SOUND_RMS_THRESHOLD})",
    )
    ap.add_argument(
        "--chunk",
        type=int,
        default=VOICE_SOUND_CHUNK_SIZE,
        help=f"Frames per buffer (default {VOICE_SOUND_CHUNK_SIZE})",
    )
    ap.add_argument(
        "--log-interval",
        type=float,
        default=0.35,
        help="Min seconds between mic_sound_detected JSON logs (default 0.35)",
    )
    ap.add_argument(
        "--list-only",
        action="store_true",
        help="Print input devices and exit",
    )
    args = ap.parse_args()

    threshold = int(VOICE_SOUND_RMS_THRESHOLD if args.threshold is None else args.threshold)
    chunk = max(128, int(args.chunk))
    log_interval = max(0.05, float(args.log_interval))

    print("[Mic] Enumerating input devices...")
    devices = _list_input_devices()
    if not devices:
        print("[FAIL] No PyAudio input devices found.")
        logging_store.log_event(
            {
                "event": "mic_test_no_device",
                "timestamp": _utc_ts(),
                "reason": "no_input_devices",
            }
        )
        return 1

    sr_names = _speech_mic_names()
    print(f"[OK] Found {len(devices)} input device(s):")
    for idx, name in devices:
        extra = ""
        if sr_names is not None and 0 <= idx < len(sr_names):
            extra = f" | SpeechRecognition: {sr_names[idx]!r}"
        print(f"     [{idx}] {name}{extra}")

    logging_store.log_event(
        {
            "event": "mic_test_devices",
            "timestamp": _utc_ts(),
            "count": len(devices),
            "devices": [{"index": i, "name": n} for i, n in devices],
        }
    )

    if args.list_only:
        print("[DONE] --list-only: exiting.")
        return 0

    import pyaudio

    with _suppress_native_stderr():
        pa = pyaudio.PyAudio()
    stream = None
    rate_used = VOICE_SOUND_SAMPLE_RATE
    dev_index = args.device_index

    try:
        for rate in (VOICE_SOUND_SAMPLE_RATE, 44100, 48000):
            try:
                with _suppress_native_stderr():
                    stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=rate,
                        input=True,
                        input_device_index=dev_index,
                        frames_per_buffer=chunk,
                    )
                rate_used = rate
                break
            except Exception:
                stream = None
                continue

        if stream is None:
            print("[FAIL] Could not open microphone stream (wrong --device-index or driver issue).")
            logging_store.log_event(
                {
                    "event": "mic_test_open_failed",
                    "timestamp": _utc_ts(),
                    "device_index": dev_index,
                    "threshold": threshold,
                }
            )
            return 1

        if dev_index is None:
            default = pa.get_default_input_device_info()
            resolved_index = int(default["index"])
            dev_name = str(default.get("name", "?"))
        else:
            resolved_index = int(dev_index)
            di = pa.get_device_info_by_index(resolved_index)
            dev_name = str(di.get("name", "?"))

        logging_store.log_event(
            {
                "event": "mic_test_device_ready",
                "timestamp": _utc_ts(),
                "device_index": resolved_index,
                "device_name": dev_name,
                "sample_rate": rate_used,
                "chunk": chunk,
                "rms_threshold": threshold,
            }
        )
        print(
            f"[OK] Microphone open: index={resolved_index} name={dev_name!r} "
            f"rate={rate_used} chunk={chunk} threshold_RMS={threshold}"
        )

        logging_store.log_event(
            {
                "event": "mic_test_listening",
                "timestamp": _utc_ts(),
                "message": "stream_active_until_ctrl_c",
            }
        )
        print("[Mic] Listening… (sound above threshold is logged; Ctrl+C to stop)")

        first_chunk = True
        last_sound_log = 0.0
        total_sound_events = 0

        try:
            while True:
                try:
                    raw = stream.read(chunk, exception_on_overflow=False)
                except Exception as e:
                    print(f"[FAIL] Read error: {e}")
                    logging_store.log_event(
                        {
                            "event": "mic_test_read_error",
                            "timestamp": _utc_ts(),
                            "error": str(e),
                        }
                    )
                    return 1

                if first_chunk:
                    first_chunk = False
                    logging_store.log_event(
                        {
                            "event": "mic_test_working",
                            "timestamp": _utc_ts(),
                            "message": "first_audio_chunk_received",
                        }
                    )
                    print("[OK] First audio chunk received — mic stream is working.")

                rms = audioop.rms(raw, 2)
                now = time.monotonic()
                if rms >= threshold and (now - last_sound_log) >= log_interval:
                    total_sound_events += 1
                    last_sound_log = now
                    logging_store.log_event(
                        {
                            "event": "mic_sound_detected",
                            "timestamp": _utc_ts(),
                            "rms": int(rms),
                            "threshold": threshold,
                            "device_index": resolved_index,
                        }
                    )
                    print(f"[Mic] Sound detected (RMS={rms}, threshold={threshold})")
        except KeyboardInterrupt:
            pass

        logging_store.log_event(
            {
                "event": "mic_test_stopped",
                "timestamp": _utc_ts(),
                "reason": "keyboard_interrupt",
                "sound_events_logged": total_sound_events,
            }
        )
        print(f"\n[Mic] Stopped (Ctrl+C). Logged {total_sound_events} sound event(s).")
        print(f"[Mic] JSONL log: {logging_store.get_log_path()}")
        return 0

    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        try:
            pa.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
