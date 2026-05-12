"""
Isolated DFPlayer audio bench test.

Run on Raspberry Pi:
    python -m src.audio_test --track 1
    python -m src.audio_test --probe-range 5 --track-sec 3
    python -m src.mp3_diag              # full MP3-TF-16P diagnostic (or --mp3tf16p-diag)
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from src import audio_mp3


def _list_sd_files(sd_dir: str) -> int:
    root = Path(sd_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"[FAIL] SD directory not found: {root}")
        return 1

    audio_ext = {".mp3", ".wav", ".wma", ".flac"}
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in audio_ext)
    print(f"[INFO] SD scan root: {root}")
    if not files:
        print("[WARN] No audio files found under this directory.")
        return 0

    print(f"[INFO] Found {len(files)} audio file(s):")
    for p in files[:80]:
        rel = p.relative_to(root)
        print(f"  - {rel}")
    if len(files) > 80:
        print(f"  ... and {len(files) - 80} more")

    mp3_dir = root / "mp3"
    if mp3_dir.exists():
        expected = sorted(x.name for x in mp3_dir.glob("*.mp3"))
        if expected:
            print("[INFO] Files under mp3/ (DFPlayer-friendly naming expected):")
            for name in expected[:40]:
                print(f"  - mp3/{name}")
            if len(expected) > 40:
                print(f"  ... and {len(expected) - 40} more")
    else:
        print("[WARN] No 'mp3/' folder found at SD root.")
    return 0


def _query_device(mod: audio_mp3.AudioMP3) -> None:
    print("[INFO] Querying DFPlayer status (requires RX wiring for responses)...")
    vol = mod.query_volume(timeout_sec=0.7)
    status = mod.query_status(timeout_sec=0.7)
    file_count = mod.query_tf_file_count(timeout_sec=0.7)
    if vol is None and status is None and file_count is None:
        print("[WARN] No query response received.")
        print("       Wire DFPlayer TX -> Pi RX (MP3_RX_GPIO) to enable diagnostics.")
        return
    print(f"[OK] Volume query     : {vol if vol is not None else 'n/a'}")
    print(f"[OK] Playback status  : {status if status is not None else 'n/a'}")
    print(f"[OK] TF file count    : {file_count if file_count is not None else 'n/a'}")


def _play_once(
    track: int,
    hold_sec: float,
    volume: int | None,
    query: bool,
    no_stop: bool,
    folder: int | None,
    file_num: int | None,
) -> int:
    mod = audio_mp3.AudioMP3(dry_run=False)
    mod.open()
    try:
        if mod._ser is None and mod._pi is None:
            print("[FAIL] MP3 transport is not open (check wiring / pigpio / serial config).")
            return 1
        if volume is not None:
            mod.set_volume(volume)
            print(f"[INFO] Volume set to {max(0, min(30, int(volume)))}")
            time.sleep(0.1)
        if query:
            _query_device(mod)
        if folder is not None and file_num is not None:
            print(f"[INFO] Playing folder/file {int(folder):03d}/{int(file_num):03d} for ~{hold_sec:.1f}s...")
            mod.play_folder_track(int(folder), int(file_num))
        else:
            print(f"[INFO] Playing track {track} → expects SD:/mp3/{track:04d}.mp3 (~{hold_sec:.1f}s)...")
            mod.play_track(track)
        time.sleep(max(0.2, hold_sec))
        if not no_stop:
            mod.stop()
        print("[OK] Play command sent.")
        return 0
    finally:
        mod.close()


def _probe_range(max_track: int, hold_sec: float, volume: int | None, query: bool, no_stop: bool) -> int:
    mod = audio_mp3.AudioMP3(dry_run=False)
    mod.open()
    try:
        if mod._ser is None and mod._pi is None:
            print("[FAIL] MP3 transport is not open (check wiring / pigpio / serial config).")
            return 1
        if volume is not None:
            mod.set_volume(volume)
            print(f"[INFO] Volume set to {max(0, min(30, int(volume)))}")
            time.sleep(0.1)
        if query:
            _query_device(mod)
        print(f"[INFO] Probing tracks 1..{max_track} (about {hold_sec:.1f}s each)")
        for track in range(1, max_track + 1):
            print(f"  -> Track {track}")
            mod.play_track(track)
            time.sleep(max(0.2, hold_sec))
            if not no_stop:
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
        help="Track index for SD:/mp3/0001.mp3 layout (default 1 → 0001.mp3)",
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
    ap.add_argument(
        "--volume",
        type=int,
        default=None,
        help="Set DFPlayer volume before playback (0..30)",
    )
    ap.add_argument(
        "--query",
        action="store_true",
        help="Query DFPlayer status/volume/file count (needs RX wiring)",
    )
    ap.add_argument(
        "--no-stop",
        action="store_true",
        help="Do not send stop command after hold time (for long-audible testing)",
    )
    ap.add_argument(
        "--sd-dir",
        type=str,
        default="",
        help="Mounted SD root path to list audio files (e.g. /media/pi/NO_NAME)",
    )
    ap.add_argument(
        "--folder",
        type=int,
        default=0,
        help="Play folder/file target instead of flat track (e.g. --folder 1 --file 1)",
    )
    ap.add_argument(
        "--file",
        type=int,
        default=1,
        help="File number within --folder (default 1)",
    )
    ap.add_argument(
        "--mp3tf16p-diag",
        action="store_true",
        help="Run full MP3-TF-16P diagnostic (same as python -m src.mp3_diag): reset, TF select, queries, play",
    )
    args = ap.parse_args()

    hold_sec = max(0.2, float(args.track_sec))
    volume = None if args.volume is None else max(0, min(30, int(args.volume)))
    folder = int(args.folder) if int(args.folder) > 0 else None
    file_num = max(1, int(args.file))
    if args.sd_dir:
        _list_sd_files(args.sd_dir)
    if args.mp3tf16p_diag:
        from src.mp3_diag import run_diag_session

        diag_folder = int(args.folder) if int(args.folder) > 0 else 1
        return run_diag_session(
            hold_sec=hold_sec,
            volume=volume,
            track=max(1, int(args.track)),
            folder=diag_folder,
            file_num=max(1, int(args.file)),
            no_reset=False,
            try_folder_layout=True,
        )
    if args.probe_range and args.probe_range > 0:
        return _probe_range(
            max_track=max(1, int(args.probe_range)),
            hold_sec=hold_sec,
            volume=volume,
            query=bool(args.query),
            no_stop=bool(args.no_stop),
        )
    return _play_once(
        track=max(1, int(args.track)),
        hold_sec=hold_sec,
        volume=volume,
        query=bool(args.query),
        no_stop=bool(args.no_stop),
        folder=folder,
        file_num=file_num if folder is not None else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
