"""
One-shot microphone → Google speech recognition test.

Use this to verify flac, internet, and keyword hearing outside the full alert flow.

Run on Raspberry Pi (venv active):

    python -m src.mic_stt_oneshot
    python -m src.mic_stt_oneshot --device-index 0 --keyword cancel
    python -m src.mic_stt_oneshot --list-devices
"""

from __future__ import annotations

import argparse
import shutil
import sys


def _check_flac() -> bool:
    path = shutil.which("flac")
    if path:
        print(f"[OK] flac found: {path}")
        return True
    print(
        "[FAIL] flac not found (SpeechRecognition needs it for recognize_google).\n"
        "       Install: sudo apt update && sudo apt install -y flac"
    )
    return False


def _list_devices() -> int:
    try:
        import speech_recognition as sr
    except ImportError:
        print("[FAIL] SpeechRecognition not installed (pip install SpeechRecognition).")
        return 1

    names = sr.Microphone.list_microphone_names()
    if not names:
        print("[WARN] No microphones reported by SpeechRecognition.")
        return 1
    print(f"[INFO] {len(names)} microphone(s):")
    for i, name in enumerate(names):
        print(f"  [{i}] {name}")
    return 0


def run_oneshot(
    *,
    device_index: int | None,
    keyword: str,
    ambient_sec: float,
    listen_timeout_sec: float,
    phrase_sec: float,
) -> int:
    if not _check_flac():
        return 1

    try:
        import speech_recognition as sr
    except ImportError:
        print("[FAIL] SpeechRecognition not installed (pip install SpeechRecognition).")
        return 1

    kw = (keyword or "cancel").strip().lower()
    ambient = max(0.3, float(ambient_sec))
    timeout = max(1.0, float(listen_timeout_sec))
    phrase = max(0.8, float(phrase_sec))

    idx = device_index
    names = sr.Microphone.list_microphone_names()
    if idx is None and names:
        idx = 0
    dev_label = names[idx] if idx is not None and 0 <= idx < len(names) else "?"

    print(
        f"[INFO] device_index={idx} name={dev_label!r} "
        f"keyword={kw!r} ambient={ambient:.1f}s phrase_limit={phrase:.1f}s"
    )

    r = sr.Recognizer()
    try:
        with sr.Microphone(device_index=idx) as src:
            print(f"[INFO] Calibrating ambient noise ({ambient:.1f}s) — stay quiet…")
            r.adjust_for_ambient_noise(src, duration=ambient)
            print(f"[INFO] energy_threshold={getattr(r, 'energy_threshold', 'n/a')}")
            print(f"[INFO] Say {kw!r} clearly (listening up to {timeout:.0f}s)…")
            audio = r.listen(src, timeout=timeout, phrase_time_limit=phrase)
    except sr.WaitTimeoutError:
        print("[FAIL] Listen timed out — no speech detected.")
        return 1
    except Exception as e:
        print(f"[FAIL] Microphone open/listen failed: {type(e).__name__}: {e}")
        return 1

    try:
        import audioop

        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        rms = int(audioop.rms(raw, 2)) if raw else 0
        print(f"[INFO] Captured audio (RMS={rms}), calling Google recognize_google…")
    except Exception:
        print("[INFO] Captured audio, calling Google recognize_google…")

    try:
        text = r.recognize_google(audio).strip().lower()
    except sr.UnknownValueError:
        print("[FAIL] Google returned no transcript (speech not understood).")
        return 1
    except sr.RequestError as e:
        print(f"[FAIL] Network/API error: {e}")
        print("       Check: ping google.com, curl -sI https://www.google.com")
        return 1
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        if "flac" in str(e).lower():
            print("       Install: sudo apt install -y flac")
        return 1

    print(f"[OK] Heard: {text!r}")
    if kw in text:
        print(f"[OK] Keyword {kw!r} matched — voice cancel path should work.")
        return 0
    print(f"[WARN] Keyword {kw!r} not in transcript (heard something else).")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="One-shot mic → Google STT test (flac + internet required)",
    )
    ap.add_argument("--list-devices", action="store_true", help="List mic indices and exit")
    ap.add_argument("--device-index", type=int, default=None, help="Microphone index (default 0)")
    ap.add_argument("--keyword", type=str, default="cancel", help="Keyword to match (default: cancel)")
    ap.add_argument("--ambient-sec", type=float, default=1.0, help="Ambient calibration seconds")
    ap.add_argument("--timeout", type=float, default=8.0, help="Max wait for speech to start")
    ap.add_argument("--phrase-sec", type=float, default=3.0, help="Max length of utterance")
    args = ap.parse_args()

    if args.list_devices:
        return _list_devices()

    return run_oneshot(
        device_index=args.device_index,
        keyword=args.keyword,
        ambient_sec=args.ambient_sec,
        listen_timeout_sec=args.timeout,
        phrase_sec=args.phrase_sec,
    )


if __name__ == "__main__":
    raise SystemExit(main())
