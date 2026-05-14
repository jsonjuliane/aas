"""
Very basic MP3 UART line test (TX / RX / optional loopback).

Run on Raspberry Pi:
    python -m src.mp3_line_test
    python -m src.mp3_line_test --query-only
    python -m src.mp3_line_test --tx-only --track 1 --hold-sec 6

GPIO loopback mode (Pi-side serial sanity):
    1) Disconnect DFPlayer from MP3 TX/RX pins
    2) Add jumper: Pi MP3_TX_GPIO <-> Pi MP3_RX_GPIO
    3) python -m src.mp3_line_test --loopback
"""

from __future__ import annotations

import argparse
import time

from src.audio_mp3 import AudioMP3
from src.config import MP3_BAUD, MP3_RX_GPIO, MP3_TX_GPIO


def _transport_ok(mod: AudioMP3) -> bool:
    return (mod._ser is not None) or (mod._pi is not None)


def _run_tx_only(track: int, hold_sec: float, volume: int) -> bool:
    mod = AudioMP3(dry_run=False)
    mod.open()
    try:
        if not _transport_ok(mod):
            print("[FAIL] MP3 transport not open.")
            return False

        print("[INFO] TX-only test: reset/wake/select/set volume/play/stop")
        ok_reset, rs_reset = mod.dfplayer_module_reset()
        print(f"  reset: {'OK' if ok_reset else 'FAIL'} ({rs_reset})")
        time.sleep(1.2 if ok_reset else 0.2)

        ok_wake, rs_wake = mod.dfplayer_wake_up()
        print(f"  wake : {'OK' if ok_wake else 'FAIL'} ({rs_wake})")
        time.sleep(0.1)

        ok_tf, rs_tf = mod.dfplayer_select_tf_card()
        print(f"  tf   : {'OK' if ok_tf else 'FAIL'} ({rs_tf})")
        time.sleep(0.1)

        mod.set_volume(max(0, min(30, int(volume))))
        play = mod.play_track_with_status(max(1, int(track)))
        print(
            f"  play : {'OK' if play.get('ok') else 'FAIL'} "
            f"({play.get('reason')}, cmd=0x03, track={track})"
        )
        time.sleep(max(0.3, float(hold_sec)))

        busy = mod.read_busy_state()
        print(f"  busy : {busy}")
        mod.stop()
        print("[INFO] TX-only test done.")

        if play.get("ok"):
            print(
                "[NOTE] TX write succeeded. This still does not prove decode/audio; "
                "confirm by hearing sound or wiring BUSY pin."
            )
            return True
        return False
    finally:
        mod.close()


def _run_query_only() -> bool:
    mod = AudioMP3(dry_run=False)
    mod.open()
    try:
        if not _transport_ok(mod):
            print("[FAIL] MP3 transport not open.")
            return False

        print("[INFO] Query test (requires DF TX -> Pi RX):")
        vol = mod.query_volume(timeout_sec=0.9)
        status = mod.query_status(timeout_sec=0.9)
        count = mod.query_tf_file_count(timeout_sec=0.9)

        print(f"  volume query: {vol if vol is not None else 'no response'}")
        print(f"  status query: {status if status is not None else 'no response'}")
        print(f"  file count  : {count if count is not None else 'no response'}")

        ok = any(v is not None for v in (vol, status, count))
        if ok:
            print("[PASS] RX feedback path is alive.")
        else:
            print("[FAIL] No RX feedback. Check DF TX -> Pi RX wiring/level shifting.")
        return ok
    finally:
        mod.close()


def _run_loopback_test(timeout_sec: float) -> bool:
    """
    Pi-side serial sanity test.

    Requires jumper wire: MP3_TX_GPIO <-> MP3_RX_GPIO and DFPlayer disconnected
    from those two pins during this test.
    """
    try:
        import pigpio
    except ImportError:
        print("[FAIL] pigpio module not installed in environment.")
        return False

    pi = pigpio.pi()
    if not getattr(pi, "connected", False):
        print("[FAIL] pigpiod not running.")
        return False

    payload = b"MP3_LOOPBACK_OK\n"
    rx_buf = bytearray()
    try:
        try:
            pi.bb_serial_read_close(MP3_RX_GPIO)
        except Exception:
            pass
        pi.bb_serial_read_open(MP3_RX_GPIO, MP3_BAUD, 8)

        # Clear stale bytes.
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.15:
            try:
                pi.bb_serial_read(MP3_RX_GPIO)
            except Exception:
                break
            time.sleep(0.01)

        pi.wave_clear()
        pi.wave_add_serial(MP3_TX_GPIO, MP3_BAUD, payload)
        wid = pi.wave_create()
        if wid < 0:
            print(f"[FAIL] wave_create failed: {wid}")
            return False
        pi.wave_send_once(wid)
        while pi.wave_tx_busy():
            time.sleep(0.002)
        pi.wave_delete(wid)

        deadline = time.monotonic() + max(0.5, float(timeout_sec))
        while time.monotonic() < deadline:
            try:
                count, data = pi.bb_serial_read(MP3_RX_GPIO)
            except Exception:
                count, data = 0, b""
            if count > 0 and data:
                rx_buf.extend(data)
                if payload in rx_buf:
                    break
            time.sleep(0.01)

        ok = payload in rx_buf
        print(f"[INFO] loopback tx bytes: {payload!r}")
        print(f"[INFO] loopback rx bytes: {bytes(rx_buf)!r}")
        if ok:
            print("[PASS] Pi TX/RX pins + pigpio serial path are working.")
        else:
            print(
                "[FAIL] Loopback failed. Check pigpiod, selected GPIO pins, and "
                "jumper MP3_TX_GPIO <-> MP3_RX_GPIO."
            )
        return ok
    finally:
        try:
            pi.bb_serial_read_close(MP3_RX_GPIO)
        except Exception:
            pass
        try:
            pi.stop()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Basic MP3 UART line test")
    ap.add_argument("--tx-only", action="store_true", help="Run TX-only playback test")
    ap.add_argument("--query-only", action="store_true", help="Run RX feedback query test")
    ap.add_argument(
        "--loopback",
        action="store_true",
        help="Run Pi-side GPIO loopback (needs TX<->RX jumper, DF disconnected)",
    )
    ap.add_argument("--track", type=int, default=1, help="Track index (default 1)")
    ap.add_argument("--hold-sec", type=float, default=5.0, help="Play hold seconds (default 5)")
    ap.add_argument("--volume", type=int, default=25, help="Volume 0..30 (default 25)")
    ap.add_argument(
        "--loopback-timeout-sec",
        type=float,
        default=1.5,
        help="Loopback RX wait timeout (default 1.5)",
    )
    args = ap.parse_args()

    # Default mode: TX then RX query.
    run_tx = bool(args.tx_only)
    run_query = bool(args.query_only)
    if not run_tx and not run_query and not args.loopback:
        run_tx = True
        run_query = True

    any_fail = False
    if run_tx:
        ok_tx = _run_tx_only(track=args.track, hold_sec=args.hold_sec, volume=args.volume)
        any_fail = any_fail or (not ok_tx)
    if run_query:
        ok_query = _run_query_only()
        any_fail = any_fail or (not ok_query)
    if args.loopback:
        ok_loop = _run_loopback_test(timeout_sec=args.loopback_timeout_sec)
        any_fail = any_fail or (not ok_loop)

    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
