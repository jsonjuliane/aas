"""
USB / system microphone bench test.

Modes:
  python -m src.mic_test                    # RMS monitor (logs on level changes)
  python -m src.mic_test --baseline        # measure idle noise + suggest threshold
  python -m src.mic_test --keyword-test    # keyword recognition loop (like main)
  python -m src.mic_test --sphinx-oneshot  # one-shot PocketSphinx transcription
  python -m src.mic_test --record out.wav  # save a short WAV sample

Run on Raspberry Pi (venv active).
"""

from __future__ import annotations

import argparse
import audioop
import contextlib
import os
import sys
import time

from src.config import (
    VOICE_KEYWORD_MIN_RMS,
    VOICE_SOUND_CHUNK_SIZE,
    VOICE_SOUND_RMS_THRESHOLD,
    VOICE_SOUND_SAMPLE_RATE,
)
from src import logging_store, voice_cancel


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
    import pyaudio

    with _suppress_native_stderr():
        pa = pyaudio.PyAudio()
    try:
        out: list[tuple[int, str]] = []
        for i in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_index(i)
            except Exception:
                continue
            if int(info.get("maxInputChannels", 0)) < 1:
                continue
            out.append((i, str(info.get("name", "?"))))
        return out
    finally:
        pa.terminate()


def _run_baseline(device_index: int | None, duration_sec: float) -> int:
    print(f"[Mic] Measuring RMS baseline for {duration_sec:.1f}s (stay quiet)...")
    stats = voice_cancel.measure_rms_stats(
        device_index=device_index,
        duration_sec=duration_sec,
    )
    if stats is None:
        print("[FAIL] Could not sample microphone (PyAudio).")
        return 1

    print(
        f"[OK] Baseline: min={stats['min']} avg={stats['avg']} p95={stats['p95']} "
        f"max={stats['max']} @ {stats['sample_rate']}Hz ({stats['samples']} samples)"
    )
    print(
        f"[INFO] Suggested VOICE_SOUND_RMS_THRESHOLD ≈ {stats['suggested_threshold']} "
        f"(current config: {VOICE_SOUND_RMS_THRESHOLD})"
    )
    print(
        f"[INFO] Suggested VOICE_KEYWORD_MIN_RMS ≈ {max(int(stats['p95']) + 400, 1200)} "
        f"(current config: {VOICE_KEYWORD_MIN_RMS})"
    )
    logging_store.log_event(
        {
            "event": "mic_test_baseline",
            "timestamp": _utc_ts(),
            "device_index": device_index,
            **{k: v for k, v in stats.items() if k != "samples"},
        }
    )
    return 0


def _run_keyword_test(
    device_index: int | None,
    keyword: str,
    duration_sec: float,
    *,
    verbose: bool,
) -> int:
    print(f"[Mic] Keyword test for {duration_sec:.0f}s (say '{keyword}' clearly)...")
    with _suppress_native_stderr():
        session = voice_cancel.open_keyword_session(
            device_index=device_index,
            keyword=keyword,
        )
    if session is None:
        print("[FAIL] Could not open keyword session.")
        return 1

    print(
        f"[OK] Mic open: index={session.device_index} name={session.device_name!r} "
        f"energy_threshold={session.energy_threshold:.0f} "
        f"engine={session.engine} ({session.engine_reason})"
    )

    deadline = time.monotonic() + max(1.0, duration_sec)
    attempts = 0
    matches = 0
    try:
        while time.monotonic() < deadline:
            with _suppress_native_stderr():
                result = voice_cancel.listen_once(session, timeout_sec=0.4)
            attempts += 1

            if result.matched:
                matches += 1
                print(f"[OK] Keyword matched! heard={result.heard!r} RMS={result.rms}")
                break

            if result.reason == "ok" or result.reason == "no_keyword":
                print(f"[Mic] Heard: {result.heard!r} (RMS={result.rms}) — keyword not in phrase")
            elif result.reason in ("timeout", "too_quiet"):
                if verbose:
                    print(f"[Mic] … {voice_cancel.reason_message(result.reason)}")
            else:
                print(f"[Mic] {voice_cancel.reason_message(result.reason)} (RMS={result.rms})")

            time.sleep(0.05)
    finally:
        voice_cancel.close_keyword_session(session)

    print(f"[DONE] attempts={attempts} matches={matches}")
    return 0 if matches > 0 else 1


def _run_sphinx_oneshot(
    device_index: int | None,
    keyword: str,
    ambient_sec: float,
    timeout_sec: float,
    phrase_sec: float,
) -> int:
    try:
        import speech_recognition as sr
    except ImportError:
        print("[FAIL] SpeechRecognition is not installed.")
        return 1

    try:
        import pocketsphinx  # noqa: F401
    except ImportError:
        print("[FAIL] PocketSphinx is not installed. Try: pip install pocketsphinx")
        return 1

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.6
    recognizer.phrase_threshold = 0.25

    names = voice_cancel.list_microphone_names()
    idx = device_index
    if idx is None and names:
        idx = 0
    dev_name = names[idx] if idx is not None and 0 <= idx < len(names) else "?"

    try:
        # Open with the device's native/default sample rate. Some Pi USB mics
        # reject 16 kHz at open time; SpeechRecognition/PocketSphinx can still
        # convert captured audio to 16 kHz afterward.
        mic = sr.Microphone(device_index=idx)
        print(f"[Mic] Opening device index={idx} name={dev_name!r}")
        with _suppress_native_stderr(), mic as source:
            print(f"[Mic] Adjusting for background noise for {ambient_sec:.1f}s...")
            recognizer.adjust_for_ambient_noise(source, duration=max(0.3, ambient_sec))
            print(
                f"[OK] Mic ready: energy_threshold={recognizer.energy_threshold:.0f}. "
                f"Say '{keyword}' clearly."
            )
            audio = recognizer.listen(
                source,
                timeout=max(0.1, timeout_sec),
                phrase_time_limit=max(0.8, phrase_sec),
            )
    except sr.WaitTimeoutError:
        print("[FAIL] Listening timed out; no speech detected.")
        return 1
    except Exception as e:
        print(f"[FAIL] Could not capture microphone audio: {e}")
        return 1

    try:
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        rms = int(audioop.rms(raw, 2)) if raw else 0
    except Exception:
        rms = 0
    print(f"[Mic] Captured audio RMS={rms}")

    try:
        text = recognizer.recognize_sphinx(audio).strip().lower()
        print(f"[OK] PocketSphinx free-form heard: {text!r}")
    except sr.UnknownValueError:
        text = ""
        print("[Mic] PocketSphinx free-form could not understand the audio.")
    except sr.RequestError as e:
        print(f"[FAIL] PocketSphinx error: {e}")
        return 1

    try:
        kw_text = recognizer.recognize_sphinx(
            audio,
            keyword_entries=[(keyword.strip().lower(), 1.0)],
        ).strip().lower()
        matched = keyword.strip().lower() in kw_text.split()
        print(f"[OK] PocketSphinx keyword heard: {kw_text!r} matched={matched}")
        return 0 if matched else 1
    except sr.UnknownValueError:
        print("[FAIL] PocketSphinx keyword mode did not hear the keyword.")
        return 1
    except sr.RequestError as e:
        print(f"[FAIL] PocketSphinx keyword error: {e}")
        return 1


def _run_record(device_index: int | None, path: str, duration_sec: float) -> int:
    print(f"[Mic] Recording {duration_sec:.1f}s -> {path}")
    ok = voice_cancel.record_wav(path, device_index=device_index, duration_sec=duration_sec)
    if not ok:
        print("[FAIL] Recording failed.")
        return 1
    print(f"[OK] Saved {path}")
    return 0


def _run_rms_monitor(
    device_index: int | None,
    threshold: int,
    chunk: int,
    log_interval: float,
    run_baseline_first: bool,
) -> int:
    if run_baseline_first:
        stats = voice_cancel.measure_rms_stats(device_index=device_index, duration_sec=2.0)
        if stats is not None:
            threshold = int(stats["suggested_threshold"])
            print(
                f"[INFO] Auto threshold from 2s baseline: {threshold} "
                f"(idle p95={stats['p95']}, avg={stats['avg']})"
            )

    import pyaudio

    with _suppress_native_stderr():
        pa = pyaudio.PyAudio()
    stream = None
    rate_used = VOICE_SOUND_SAMPLE_RATE

    try:
        for rate in (VOICE_SOUND_SAMPLE_RATE, 44100, 48000):
            try:
                with _suppress_native_stderr():
                    stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=chunk,
                    )
                rate_used = rate
                break
            except Exception:
                stream = None

        if stream is None:
            print("[FAIL] Could not open microphone stream.")
            return 1

        print(
            f"[OK] RMS monitor: threshold={threshold} rate={rate_used} chunk={chunk} "
            "(logs when crossing quiet/loud; Ctrl+C to stop)"
        )

        state = "quiet"
        last_log = 0.0
        events = 0

        while True:
            raw = stream.read(chunk, exception_on_overflow=False)
            rms = int(audioop.rms(raw, 2))
            now = time.monotonic()
            loud = rms >= threshold

            new_state = "loud" if loud else "quiet"
            if new_state != state and (now - last_log) >= log_interval:
                state = new_state
                last_log = now
                events += 1
                logging_store.log_event(
                    {
                        "event": "mic_sound_state",
                        "timestamp": _utc_ts(),
                        "state": state,
                        "rms": rms,
                        "threshold": threshold,
                    }
                )
                label = "Sound detected" if loud else "Back to quiet"
                print(f"[Mic] {label} (RMS={rms}, threshold={threshold})")

    except KeyboardInterrupt:
        print(f"\n[Mic] Stopped. {events} state change(s) logged.")
        print(f"[Mic] JSONL: {logging_store.get_log_path()}")
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Microphone bench test (RMS / keyword / record)")
    ap.add_argument("--device-index", type=int, default=None, help="PyAudio input device index")
    ap.add_argument(
        "--threshold",
        type=int,
        default=None,
        help=f"RMS threshold for monitor mode (default {VOICE_SOUND_RMS_THRESHOLD})",
    )
    ap.add_argument("--chunk", type=int, default=VOICE_SOUND_CHUNK_SIZE)
    ap.add_argument("--log-interval", type=float, default=0.35)
    ap.add_argument("--list-only", action="store_true", help="List devices and exit")
    ap.add_argument("--baseline", action="store_true", help="Measure idle RMS + suggest thresholds")
    ap.add_argument("--baseline-sec", type=float, default=3.0)
    ap.add_argument(
        "--keyword-test",
        action="store_true",
        help="Test selected keyword engine (same path as alert cancel window)",
    )
    ap.add_argument("--keyword", type=str, default="cancel")
    ap.add_argument("--keyword-sec", type=float, default=15.0)
    ap.add_argument("--verbose", action="store_true", help="Log quiet/timeouts in keyword-test")
    ap.add_argument(
        "--sphinx-oneshot",
        action="store_true",
        help="One-shot offline PocketSphinx transcription and keyword check",
    )
    ap.add_argument("--sphinx-timeout-sec", type=float, default=5.0)
    ap.add_argument("--sphinx-phrase-sec", type=float, default=3.0)
    ap.add_argument("--record", type=str, default="", metavar="PATH", help="Record WAV and exit")
    ap.add_argument("--record-sec", type=float, default=5.0)
    ap.add_argument(
        "--auto-threshold",
        action="store_true",
        help="In monitor mode, measure 2s baseline first and set threshold automatically",
    )
    args = ap.parse_args()

    print("[Mic] Enumerating input devices...")
    devices = _list_input_devices()
    if not devices:
        print("[FAIL] No PyAudio input devices found.")
        return 1

    sr_names = voice_cancel.list_microphone_names()
    print(f"[OK] Found {len(devices)} input device(s):")
    for idx, name in devices:
        extra = ""
        if sr_names and 0 <= idx < len(sr_names):
            extra = f" | SR: {sr_names[idx]!r}"
        print(f"     [{idx}] {name}{extra}")

    if args.list_only:
        return 0

    dev = args.device_index

    if args.baseline:
        return _run_baseline(dev, args.baseline_sec)

    if args.record:
        return _run_record(dev, args.record, args.record_sec)

    if args.keyword_test:
        return _run_keyword_test(
            dev,
            args.keyword,
            args.keyword_sec,
            verbose=bool(args.verbose),
        )

    if args.sphinx_oneshot:
        return _run_sphinx_oneshot(
            dev,
            args.keyword,
            args.baseline_sec,
            args.sphinx_timeout_sec,
            args.sphinx_phrase_sec,
        )

    threshold = int(VOICE_SOUND_RMS_THRESHOLD if args.threshold is None else args.threshold)
    return _run_rms_monitor(
        dev,
        threshold,
        max(128, int(args.chunk)),
        max(0.05, float(args.log_interval)),
        run_baseline_first=bool(args.auto_threshold),
    )


if __name__ == "__main__":
    raise SystemExit(main())
