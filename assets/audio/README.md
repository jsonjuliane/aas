# Countdown Audio Assets

Place pre-recorded countdown audio here for the DFPlayer Mini module.

## Format

- **On SD card (DFPlayer)**: `mp3/0001.mp3` (four-digit name in an `mp3` folder at card root). Track index `1` in code maps to `0001.mp3`.
- **Content**: Short countdown voice prompt for the cancel window.
- **Purpose**: Played during the cancellation window so the rider can abort (sound / button / optional keyword).

## DFPlayer Mini SD card

Copy the finished clip to the card as **`mp3/0001.mp3`** (matching `MP3_DEFAULT_TRACK` in `src/config.py`).

## Recording

Record a clear, short countdown. Keep under 10 seconds. Sample rate 8–44.1 kHz, mono or stereo.
