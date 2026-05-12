"""
MP3-TF-16P / DFPlayer Mini — full bench diagnostic.

Run on the Raspberry Pi (venv + pigpiod if using GPIO UART):

    python -m src.mp3_diag
    python -m src.mp3_diag --no-reset --hold-sec 5
    python -m src.mp3_diag --skip-folder-layout

There is no standard serial command to "turn on an LED" on these boards; some
clones blink when UART data arrives. Prefer: speaker output, BUSY pin (config),
and serial queries when RX is wired.
"""

from __future__ import annotations

import argparse
import time

from src import audio_mp3
from src.config import MP3_BAUD


def _describe_transport(mod: audio_mp3.AudioMP3) -> None:
    if mod._ser is not None:
        dev = mod._active_serial_port or "serial"
        baud = int(getattr(mod._ser, "baudrate", MP3_BAUD))
        print(f"[INFO] Transport: kernel serial ({dev} @ {baud})")
    elif mod._pi is not None:
        from src.config import MP3_RX_GPIO, MP3_TX_GPIO

        print(
            f"[INFO] Transport: pigpio soft UART "
            f"(TX=GPIO{MP3_TX_GPIO}, RX=GPIO{MP3_RX_GPIO} @ {MP3_BAUD})"
        )
    else:
        print("[FAIL] No transport (set MP3_SERIAL_PORT or fix pigpio / wiring).")


def run_diag_session(
    *,
    hold_sec: float,
    volume: int | None,
    track: int,
    folder: int,
    file_num: int,
    no_reset: bool,
    try_folder_layout: bool,
) -> int:
    """Shared diagnostic steps for `mp3_diag` CLI and `audio_test --mp3tf16p-diag`."""
    mod = audio_mp3.AudioMP3(dry_run=False)
    mod.open()
    try:
        if mod._ser is None and mod._pi is None:
            print("[FAIL] MP3 transport is not open (pigpiod, wiring, or MP3_SERIAL_PORT).")
            return 1

        print("=== MP3-TF-16P / DFPlayer diagnostic ===")
        _describe_transport(mod)
        print(
            "[NOTE] No standard 'LED on' AT command on DFPlayer. "
            "Watch for UART activity blink on some clones; use speaker + optional BUSY pin."
        )

        if not no_reset:
            print("\n-- Step 1: module reset (0x0C)")
            ok, reason = mod.dfplayer_module_reset()
            print(f"    TX {'OK' if ok else 'FAIL'}: {reason}")
            time.sleep(2.0 if ok else 0.3)
        else:
            print("\n-- Step 1: skip reset (--no-reset)")

        print("\n-- Step 2: wake (0x0B) + select TF card (0x09, param=2)")
        wok, wreason = mod.dfplayer_wake_up()
        print(f"    wake TX {'OK' if wok else 'FAIL'}: {wreason}")
        time.sleep(0.1)
        tok, treason = mod.dfplayer_select_tf_card()
        print(f"    TF select TX {'OK' if tok else 'FAIL'}: {treason}")
        time.sleep(0.2)

        vol = 22 if volume is None else max(0, min(30, int(volume)))
        print(f"\n-- Step 3: set volume ({vol})")
        mod.set_volume(vol)
        time.sleep(0.15)

        print("\n-- Step 4: queries (need DFPlayer TX → Pi RX for answers)")
        vq = mod.query_volume(timeout_sec=0.75)
        sq = mod.query_status(timeout_sec=0.75)
        nq = mod.query_tf_file_count(timeout_sec=0.75)
        print(f"    volume query : {vq if vq is not None else 'no response'}")
        print(f"    status query : {sq if sq is not None else 'no response'}")
        print(f"    TF file count: {nq if nq is not None else 'no response'}")
        if vq is None and sq is None and nq is None:
            print(
                "    [WARN] No RX feedback — Pi cannot confirm the module decoded commands. "
                "Still testing TX (play) below."
            )

        track = max(1, min(2999, int(track)))
        print(f"\n-- Step 5: play track {track} (layout SD:/mp3/{track:04d}.mp3, cmd 0x03)")
        pst = mod.play_track_with_status(track)
        print(
            f"    play TX {'OK' if pst.get('ok') else 'FAIL'}: "
            f"{pst.get('reason')} packet={pst.get('packet_hex')}"
        )
        time.sleep(max(0.3, float(hold_sec)))
        sq_mid = mod.query_status(timeout_sec=0.5)
        busy = mod.read_busy_state()
        print(f"    status after hold: {sq_mid if sq_mid is not None else 'n/a'}, BUSY: {busy}")

        print("\n-- Step 6: stop (0x16)")
        mod.stop()
        time.sleep(0.25)

        if try_folder_layout:
            print(f"\n-- Step 7 (alt layout): folder {folder:02d} file {file_num} (cmd 0x0F)")
            print("    If Step 5 was silent but SD uses 01/001.mp3, this may work instead.")
            mod.play_folder_track(folder, file_num)
            time.sleep(min(3.0, max(0.5, float(hold_sec))))
            mod.stop()
            time.sleep(0.2)

        print("\n[DONE] If still no audio: check SD (mp3/0001.mp3), speaker on SPK±, 5 V, GND, TX/RX.")
        return 0
    finally:
        mod.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="MP3-TF-16P / DFPlayer full diagnostic (reset, TF select, queries, play, stop)",
    )
    ap.add_argument(
        "--hold-sec",
        type=float,
        default=4.0,
        help="Seconds to wait after starting playback (default 4)",
    )
    ap.add_argument("--volume", type=int, default=None, help="Volume 0..30 (default 22)")
    ap.add_argument("--track", type=int, default=1, help="Track index for mp3/000N.mp3 (default 1)")
    ap.add_argument("--folder", type=int, default=1, help="Alt layout folder for step 7 (default 1)")
    ap.add_argument("--file", type=int, default=1, help="Alt layout file for step 7 (default 1)")
    ap.add_argument(
        "--no-reset",
        action="store_true",
        help="Skip module reset (0x0C) at start",
    )
    ap.add_argument(
        "--skip-folder-layout",
        action="store_true",
        help="Do not try 01/001-style folder play at end",
    )
    args = ap.parse_args()
    return run_diag_session(
        hold_sec=max(0.2, float(args.hold_sec)),
        volume=args.volume,
        track=max(1, int(args.track)),
        folder=max(1, int(args.folder)),
        file_num=max(1, int(args.file)),
        no_reset=bool(args.no_reset),
        try_folder_layout=not bool(args.skip_folder_layout),
    )


if __name__ == "__main__":
    raise SystemExit(main())
