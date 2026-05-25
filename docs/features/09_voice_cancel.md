# Feature: Voice Keyword Cancel

## Overview

During the 10-second countdown, saying **"cancel"** into a USB microphone aborts the alert. The system prefers offline keyword recognition: Vosk first when the local model is installed, then PocketSphinx, then Google Speech-to-Text via `SpeechRecognition`.

Voice cancel runs **in parallel** with the GPIO button; whichever fires first wins.

---

## Requirements

| Requirement | Detail |
|-------------|--------|
| USB microphone | Any USB Audio Device recognised by ALSA (e.g. USB dongle mic) |
| Vosk model | Offline model directory, default `models/vosk-model-small-en-us-0.15` |
| PocketSphinx | Offline fallback for `armv6l` Pi where Vosk wheels are unavailable |
| Internet | Only needed when offline engines are unavailable and Google fallback is used |
| `flac` | OS-level dependency for Google fallback; install once: `sudo apt install -y flac` |
| `SpeechRecognition` | Python package; included in `requirements.txt` |
| `pyaudio` | Python package; included in `requirements.txt` |
| `vosk` | Python package; included in `requirements.txt` |
| `pocketsphinx` | Python package; included in `requirements.txt` |

---

## How it works

1. At the start of each alert, `voice_cancel.open_keyword_session()` opens the microphone and calibrates ambient noise for `VOICE_AMBIENT_CALIBRATION_SEC` seconds.
2. `voice_cancel.start_background_keyword_listen()` spawns a background thread that continuously listens for speech above `VOICE_KEYWORD_MIN_RMS`.
3. Each captured utterance is recognized by Vosk offline when available, then PocketSphinx, otherwise Google STT in `auto` mode. If the transcript contains `cancel`, `session.cancel_requested` is set to `True`.
4. `main.py` checks `session.cancel_requested` each second of the countdown window.
5. On keyword match — or on countdown timeout — `voice_cancel.close_keyword_session()` stops the listener and releases the mic.

---

## Config (`src/config.py`)

| Constant | Default | Description |
|----------|---------|-------------|
| `VOICE_CANCEL_KEYWORD_ENABLED` | `True` | Enable voice keyword cancel |
| `VOICE_CANCEL_SOUND_ENABLED` | `False` | Enable RMS-level cancel (loud noise = cancel) |
| `VOICE_KEYWORD_ENGINE` | `auto` | `auto` prefers Vosk, then PocketSphinx, then Google; can force `vosk`, `pocketsphinx`, or `google` |
| `VOICE_VOSK_MODEL_DIR` | `models/vosk-model-small-en-us-0.15` | Local offline Vosk model path |
| `VOICE_KEYWORD_MIN_RMS` | `6500` | Skip recognition for frames quieter than this |
| `VOICE_SOUND_RMS_THRESHOLD` | `10000` | RMS threshold for sound-level cancel |
| `VOICE_KEYWORD_PHRASE_SEC` | `2.0` | Max seconds per STT utterance |
| `VOICE_AMBIENT_CALIBRATION_SEC` | `1.0` | Ambient noise calibration duration |

### Install Vosk model on Pi

```bash
cd ~/AccidentAlertSystem
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p models
wget -O /tmp/vosk-model-small-en-us-0.15.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip /tmp/vosk-model-small-en-us-0.15.zip -d models/
```

If `pip install vosk` says no matching distribution, use `pip install -r requirements.txt` instead. The project requirements reference the official Vosk v0.3.45 wheels for `aarch64` and `armv7l` from the [Vosk release page](https://github.com/alphacep/vosk-api/releases/tag/v0.3.45). A Pi reporting `armv6l` is not covered by those wheels.

For `armv6l`, install/use PocketSphinx instead:

```bash
source .venv/bin/activate
pip install pocketsphinx
python - <<'PY'
import pocketsphinx
print("pocketsphinx OK")
PY
```

### Tuning thresholds

Run a baseline measurement first:

```bash
python -m src.mic_test --baseline
```

This prints `Suggested VOICE_SOUND_RMS_THRESHOLD` and `Suggested VOICE_KEYWORD_MIN_RMS` for your specific mic and environment. Update `config.py` with those values.

---

## Bench tests

```bash
# Ambient noise baseline + threshold suggestions
python -m src.mic_test --baseline

# 15-second live keyword detection test (prints engine=vosk when model is active)
python -m src.mic_test --keyword-test --keyword cancel

# One-shot Google STT check: flac, internet, mic, transcription
python -m src.mic_stt_oneshot

# Full alert cycle (test voice cancel end-to-end)
python -m src.main --test-alert
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `engine=google` when expecting offline | Check Vosk model/install; on `armv6l`, verify `import pocketsphinx` works |
| `recognition error` with Google fallback | Install `flac`: `sudo apt install -y flac` |
| `SpeechRecognition not installed` | `pip install SpeechRecognition` |
| Keyword never matched | Run `--baseline`; ensure speech RMS exceeds `VOICE_KEYWORD_MIN_RMS` |
| Constant `[Mic] Sound detected` without speech | Lower `VOICE_SOUND_RMS_THRESHOLD` or increase mic distance from noise source |
| `AssertionError: already inside context manager` | Fixed in `voice_cancel.py`; ensure mic is opened through `open_keyword_session` only |

---

## References

- `src/voice_cancel.py` — session open/close, background listener
- `src/mic_test.py` — baseline, keyword-test, RMS monitor
- `src/mic_stt_oneshot.py` — one-shot STT verification
- `src/config.py` — `VOICE_*` constants
- `docs/features/06_cancel.md` — full cancel mechanism (button + voice)
