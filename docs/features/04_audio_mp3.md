# Feature: MP3 Countdown Audio

## Overview

A DFPlayer Mini (or compatible) MP3 module plays pre-recorded countdown audio during the 5-second cancellation window.

## Hardware

| Item | Value |
|------|-------|
| Interface | UART (software serial) |
| Pi Pins | TX=GPIO 19, RX=GPIO 26 (via 1kΩ), GND=Pin 30, VCC=5V Buck |
| Baud | 9600 |
| Protocol | 10-byte command format (0x7E ... 0xEF) |

## DFPlayer Mini Commands

| Command | Byte | Purpose |
|---------|------|---------|
| Play | 0x03 | Play track (param = track number) |
| Stop | 0x16 | Stop playback |

## Module Interface

See `docs/phase0_module_boundaries.md` — `audio_mp3`:

- `open()` / `close()` — Serial lifecycle
- `play_track(track_num)` — Play track (1-based)
- `stop()` — Stop playback

## Audio Files

Place pre-recorded countdown files in `assets/audio/` as `001.mp3`, `002.mp3`, etc. (or in `mp3` folder on SD card for DFPlayer).

## Implementation (Phase 1)

- **File**: `src/audio_mp3.py`
- **Class**: `AudioMP3(port=None, dry_run=False)`
- **Usage**: `audio.open()`; `audio.play_track(1)` for countdown.
- **Config**: `MP3_SERIAL_PORT` in `src/config.py`.

## References

- [DFPlayer Mini Datasheet](https://wiki.dfrobot.com/DFPlayer_Mini_SKU_DFR0299)
- `docs/PLAN.md`, `src/config.py` — `MP3_TX_GPIO`, `MP3_RX_GPIO`, `MP3_BAUD`
