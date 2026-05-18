"""
Shared microphone + keyword recognition helpers for cancel window and bench tests.
"""

from __future__ import annotations

import audioop
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.config import (
    VOICE_AMBIENT_CALIBRATION_SEC,
    VOICE_KEYWORD_MIN_RMS,
    VOICE_KEYWORD_PHRASE_SEC,
    VOICE_SOUND_CHUNK_SIZE,
    VOICE_SOUND_SAMPLE_RATE,
)


@dataclass
class KeywordListenResult:
    """Outcome of one listen / recognize attempt."""

    matched: bool = False
    heard: str = ""
    rms: int = 0
    reason: str = ""  # ok | timeout | too_quiet | unknown | network | unavailable


@dataclass
class VoiceKeywordSession:
    """Calibrated SpeechRecognition session (one mic open for a cancel window)."""

    recognizer: Any
    microphone: Any
    source: Any
    keyword: str
    device_index: int | None
    device_name: str = ""
    energy_threshold: float = 0.0
    stop_background: Callable[..., Any] | None = None
    _cancel_event: threading.Event = field(default_factory=threading.Event)
    _last_heard: str = ""
    _last_error: str = ""

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def clear_cancel(self) -> None:
        self._cancel_event.clear()

    def consume_cancel(self) -> bool:
        if self._cancel_event.is_set():
            self._cancel_event.clear()
            return True
        return False


def list_microphone_names() -> list[str]:
    import speech_recognition as sr

    return list(sr.Microphone.list_microphone_names())


def open_keyword_session(
    *,
    device_index: int | None,
    keyword: str = "cancel",
    ambient_sec: float | None = None,
) -> VoiceKeywordSession | None:
    """
    Open mic, calibrate ambient noise once, return session for background listening.

    Returns None if SpeechRecognition or mic open fails.
    """
    try:
        import speech_recognition as sr
    except ImportError:
        return None

    ambient = max(0.3, float(VOICE_AMBIENT_CALIBRATION_SEC if ambient_sec is None else ambient_sec))
    kw = (keyword or "cancel").strip().lower()

    names = list_microphone_names()
    idx = device_index
    if idx is None and names:
        idx = 0
    dev_name = names[idx] if idx is not None and 0 <= idx < len(names) else "?"

    try:
        recognizer = sr.Recognizer()
        # Slightly stricter than library default; raised further after ambient calibrate.
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.6
        recognizer.phrase_threshold = 0.25
        mic = sr.Microphone(device_index=idx)
        source = mic.__enter__()
        recognizer.adjust_for_ambient_noise(source, duration=ambient)
        energy = float(getattr(recognizer, "energy_threshold", 0.0))
        return VoiceKeywordSession(
            recognizer=recognizer,
            microphone=mic,
            source=source,
            keyword=kw,
            device_index=idx,
            device_name=dev_name,
            energy_threshold=energy,
        )
    except Exception:
        return None


def close_keyword_session(session: VoiceKeywordSession | None) -> None:
    if session is None:
        return
    stop_background_listening(session)
    try:
        session.microphone.__exit__(None, None, None)
    except Exception:
        pass


def start_background_keyword_listen(session: VoiceKeywordSession) -> bool:
    """Start non-blocking keyword detection; sets session.cancel_requested on match."""

    if session.stop_background is not None:
        return True

    phrase_sec = max(0.8, float(VOICE_KEYWORD_PHRASE_SEC))
    min_rms = max(0, int(VOICE_KEYWORD_MIN_RMS))
    keyword = session.keyword

    def _callback(recognizer: Any, audio: Any) -> None:
        try:
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            rms = int(audioop.rms(raw, 2)) if raw else 0
        except Exception:
            rms = 0

        if rms < min_rms:
            session._last_error = "too_quiet"
            return

        try:
            heard = recognizer.recognize_google(audio).strip().lower()
        except Exception as e:
            session._last_error = classify_recognition_error(e)
            return

        session._last_heard = heard
        session._last_error = ""
        print(f"[Mic] Heard: {heard!r} (RMS={rms})")
        if keyword in heard:
            session._cancel_event.set()

    try:
        session.stop_background = session.recognizer.listen_in_background(
            session.source,
            _callback,
            phrase_time_limit=phrase_sec,
        )
        return True
    except Exception:
        session.stop_background = None
        return False


def stop_background_listening(session: VoiceKeywordSession) -> None:
    if session.stop_background is None:
        return
    try:
        session.stop_background(wait_for_stop=False)
    except Exception:
        pass
    session.stop_background = None


def listen_once(
    session: VoiceKeywordSession,
    *,
    timeout_sec: float = 0.35,
    phrase_sec: float | None = None,
) -> KeywordListenResult:
    """Blocking single listen (for mic_test bench)."""
    phrase = max(0.8, float(VOICE_KEYWORD_PHRASE_SEC if phrase_sec is None else phrase_sec))
    timeout = max(0.1, float(timeout_sec))
    min_rms = max(0, int(VOICE_KEYWORD_MIN_RMS))

    try:
        import speech_recognition as sr
    except ImportError:
        return KeywordListenResult(reason="unavailable")

    try:
        audio = session.recognizer.listen(
            session.source,
            timeout=timeout,
            phrase_time_limit=phrase,
        )
    except sr.WaitTimeoutError:
        return KeywordListenResult(reason="timeout")
    except Exception as e:
        return KeywordListenResult(reason=classify_recognition_error(e))

    try:
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        rms = int(audioop.rms(raw, 2)) if raw else 0
    except Exception:
        rms = 0

    if rms < min_rms:
        return KeywordListenResult(rms=rms, reason="too_quiet")

    try:
        heard = session.recognizer.recognize_google(audio).strip().lower()
    except Exception as e:
        return KeywordListenResult(rms=rms, reason=classify_recognition_error(e))

    matched = session.keyword in heard
    return KeywordListenResult(
        matched=matched,
        heard=heard,
        rms=rms,
        reason="ok" if matched else "no_keyword",
    )


def classify_recognition_error(exc: BaseException) -> str:
    """Map SpeechRecognition / request errors to short reason codes."""
    try:
        import speech_recognition as sr
    except ImportError:
        return "unavailable"

    if isinstance(exc, sr.WaitTimeoutError):
        return "timeout"
    if isinstance(exc, sr.UnknownValueError):
        return "unknown"
    if isinstance(exc, sr.RequestError):
        return "network"
    return "error"


def reason_message(reason: str) -> str:
    return {
        "timeout": "listening timed out (no speech yet)",
        "too_quiet": "audio below RMS gate (likely ambient noise only)",
        "unknown": "speech detected but not understood",
        "network": "Google recognition unavailable (check internet)",
        "unavailable": "SpeechRecognition not installed",
        "no_keyword": "understood speech but keyword not found",
        "error": "recognition error",
        "ok": "keyword matched",
    }.get(reason, reason)


def measure_rms_stats(
    *,
    device_index: int | None,
    duration_sec: float = 3.0,
    chunk_size: int | None = None,
) -> dict[str, int | float] | None:
    """
    Sample RMS from PyAudio for baseline diagnostics.

    Returns dict with min, max, avg, p95, suggested_threshold or None on failure.
    """
    try:
        import pyaudio
    except ImportError:
        return None

    chunk = max(128, int(chunk_size or VOICE_SOUND_CHUNK_SIZE))
    duration_sec = max(0.5, float(duration_sec))
    samples: list[int] = []

    try:
        pa = pyaudio.PyAudio()
        stream = None
        rate_used = VOICE_SOUND_SAMPLE_RATE
        for rate in (VOICE_SOUND_SAMPLE_RATE, 44100, 48000):
            try:
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
            pa.terminate()
            return None

        deadline = time.monotonic() + duration_sec
        while time.monotonic() < deadline:
            raw = stream.read(chunk, exception_on_overflow=False)
            samples.append(int(audioop.rms(raw, 2)))

        stream.stop_stream()
        stream.close()
        pa.terminate()
    except Exception:
        return None

    if not samples:
        return None

    samples_sorted = sorted(samples)
    n = len(samples_sorted)
    p95_idx = min(n - 1, int(n * 0.95))
    avg = sum(samples_sorted) / n
    p95 = samples_sorted[p95_idx]
    # Threshold above idle noise: ~1.6× p95 or avg+800, whichever is higher.
    suggested = int(max(p95 * 1.6, avg + 800, 1200))

    return {
        "min": samples_sorted[0],
        "max": samples_sorted[-1],
        "avg": int(avg),
        "p95": p95,
        "sample_rate": rate_used,
        "samples": n,
        "suggested_threshold": suggested,
    }


def record_wav(
    path: str,
    *,
    device_index: int | None,
    duration_sec: float = 5.0,
    sample_rate: int | None = None,
) -> bool:
    """Record mono 16-bit WAV via PyAudio."""
    import wave

    try:
        import pyaudio
    except ImportError:
        return False

    duration_sec = max(0.2, float(duration_sec))
    chunk = VOICE_SOUND_CHUNK_SIZE
    rate = int(sample_rate or VOICE_SOUND_SAMPLE_RATE)
    frames: list[bytes] = []

    try:
        pa = pyaudio.PyAudio()
        stream = None
        for try_rate in (rate, 44100, 48000):
            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=try_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=chunk,
                )
                rate = try_rate
                break
            except Exception:
                stream = None
        if stream is None:
            pa.terminate()
            return False

        n_reads = int(duration_sec * rate / chunk) + 1
        for _ in range(n_reads):
            frames.append(stream.read(chunk, exception_on_overflow=False))

        stream.stop_stream()
        stream.close()
        pa.terminate()

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(b"".join(frames))
        return True
    except Exception:
        return False
