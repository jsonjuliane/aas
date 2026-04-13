"""
Isolated DFPlayer audio bench test.

Run on Raspberry Pi:
    python -m src.audio_test --track 1
    python -m src.audio_test --probe-range 5 --track-sec 3
"""

from __future__ import annotations

import argparse
import time

from src import audio_mp3


def _play_once(track: int, hold_sec: float) -> int:
    mod = audio_mp3.AudioMP3(dry_run=False)
    mod.open()
    try:
        if mod._ser is None and mod._pi is None:
            print("[FAIL] MP3 transport is not open (check wiring / pigpio / serial config).")
            return 1
        print(f"[INFO] Playing track {track} for ~{hold_sec:.1f}s...")
        mod.play_track(track)
        time.sleep(max(0.2, hold_sec))
        mod.stop()
        print("[OK] Play command sent.")
        return 0
    finally:
        mod.close()


def _probe_range(max_track: int, hold_sec: float) -> int:
    mod = audio_mp3.AudioMP3(dry_run=False)
    mod.open()
    try:
        if mod._ser is None and mod._pi is None:
            print("[FAIL] MP3 transport is not open (check wiring / pigpio / serial config).")
            return 1
        print(f"[INFO] Probing tracks 1..{max_track} (about {hold_sec:.1f}s each)")
        for track in range(1, max_track + 1):
            print(f"  -> Track {track}")
            mod.play_track(track)
            time.sleep(max(0.2, hold_sec))
            mod.stop()
            time.sleep(0.2)
        print("[DONE] Probe finished. Note which track numbers produced audible playback.")
        return 0
    finally:
        mod.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Isolated DFPlayer audio bench test")
    ap.add_argument(
        "--track",
        type=int,
        default=1,
        help="Single track number to play (default 1)",
    )
    ap.add_argument(
        "--track-sec",
        type=float,
        default=3.0,
        help="How long to wait while a track plays before stop (default 3.0)",
    )
    ap.add_argument(
        "--probe-range",
        type=int,
        default=0,
        help="If >0, play tracks 1..N sequentially to find available files",
    )
    args = ap.parse_args()

    hold_sec = max(0.2, float(args.track_sec))
    if args.probe_range and args.probe_range > 0:
        return _probe_range(max_track=max(1, int(args.probe_range)), hold_sec=hold_sec)
    return _play_once(track=max(1, int(args.track)), hold_sec=hold_sec)


if __name__ == "__main__":
    raise SystemExit(main())
