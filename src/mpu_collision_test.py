"""
Isolated MPU-6050 collision/tap test.

By default logs collision events + session_end to JSONL; use --log-all-samples for per-sample lines.

Run on Raspberry Pi:
    python -m src.mpu_collision_test
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from src.config import LOGS_DIR
from src.sensor_mpu6050 import MPU6050Error, SensorMPU6050


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f UTC")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_log_path() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = _project_root() / LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"mpu_collision_{ts}.jsonl"


def _write_jsonl(path: Path, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def run_test(
    duration_sec: float,
    sample_hz: float,
    impact_g: float,
    tilt_delta_g: float,
    cooldown_ms: int,
    output_path: Path,
    warmup_sec: float,
    print_every: int,
    log_collisions_only: bool,
) -> int:
    sensor = SensorMPU6050(dry_run=False)
    interval = 1.0 / max(1.0, sample_hz)
    cooldown_sec = max(0.0, cooldown_ms / 1000.0)

    print("MPU-6050 isolated collision test")
    print(f"Log file: {output_path}")
    print(
        f"Settings: duration={duration_sec}s sample_hz={sample_hz} impact_g={impact_g} "
        f"tilt_delta_g={tilt_delta_g} cooldown_ms={cooldown_ms} "
        f"log_collisions_only={log_collisions_only}"
    )

    try:
        sensor.calibrate(samples=64)
    except MPU6050Error as e:
        print(f"[FAIL] Calibration failed: {e}")
        return 1

    # Warmup average after calibration gives a local baseline for this run.
    warmup_deadline = time.monotonic() + max(0.0, warmup_sec)
    warm_ax = warm_ay = warm_az = 0.0
    warm_n = 0
    while time.monotonic() < warmup_deadline:
        try:
            ax, ay, az = sensor.read_g()
        except MPU6050Error as e:
            print(f"[WARN] Warmup read failed: {e}")
            continue
        warm_ax += ax
        warm_ay += ay
        warm_az += az
        warm_n += 1
        time.sleep(interval)

    if warm_n == 0:
        print("[FAIL] No warmup samples read from MPU-6050")
        return 1

    bx, by, bz = warm_ax / warm_n, warm_ay / warm_n, warm_az / warm_n
    baseline_mag = math.sqrt(bx * bx + by * by + bz * bz)

    if not log_collisions_only:
        _write_jsonl(
            output_path,
            {
                "type": "session_start",
                "ts_utc": _utc_now(),
                "duration_sec": duration_sec,
                "sample_hz": sample_hz,
                "impact_g": impact_g,
                "tilt_delta_g": tilt_delta_g,
                "cooldown_ms": cooldown_ms,
                "warmup_sec": warmup_sec,
                "baseline": {"ax": bx, "ay": by, "az": bz, "mag": baseline_mag},
            },
        )

    start = time.monotonic()
    sample_idx = 0
    collisions = 0
    last_collision_at = -1e9

    print("[INFO] Test running. Tap/impact the sensor module to trigger events.")
    try:
        while (time.monotonic() - start) < duration_sec:
            loop_t0 = time.monotonic()
            sample_idx += 1

            try:
                raw = sensor.read_raw()
            except MPU6050Error as e:
                if not log_collisions_only:
                    _write_jsonl(
                        output_path,
                        {
                            "type": "read_error",
                            "ts_utc": _utc_now(),
                            "sample_idx": sample_idx,
                            "error": str(e),
                        },
                    )
                print(f"[WARN] read_error sample={sample_idx}: {e}")
                time.sleep(interval)
                continue

            ax = float(raw["ax"])
            ay = float(raw["ay"])
            az = float(raw["az"])
            gx = float(raw["gx"])
            gy = float(raw["gy"])
            gz = float(raw["gz"])

            mag = math.sqrt(ax * ax + ay * ay + az * az)
            delta = math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)
            impact_hit = mag >= impact_g
            tilt_hit = delta >= tilt_delta_g
            hit = impact_hit or tilt_hit

            now = time.monotonic()
            in_cooldown = (now - last_collision_at) < cooldown_sec
            collision = hit and not in_cooldown
            if collision:
                collisions += 1
                last_collision_at = now

            if not log_collisions_only:
                _write_jsonl(
                    output_path,
                    {
                        "type": "sample",
                        "ts_utc": _utc_now(),
                        "t_rel_sec": round(now - start, 6),
                        "sample_idx": sample_idx,
                        "accel_g": {"ax": ax, "ay": ay, "az": az},
                        "gyro_dps": {"gx": gx, "gy": gy, "gz": gz},
                        "metrics": {
                            "accel_mag_g": mag,
                            "delta_from_baseline_g": delta,
                            "impact_threshold_g": impact_g,
                            "tilt_delta_threshold_g": tilt_delta_g,
                        },
                        "flags": {
                            "impact_hit": impact_hit,
                            "tilt_hit": tilt_hit,
                            "in_cooldown": in_cooldown,
                            "collision_event": collision,
                        },
                    },
                )

            if collision:
                reason = "impact" if impact_hit else "tilt"
                print(
                    f"[COLLISION #{collisions}] sample={sample_idx} "
                    f"mag={mag:.3f}g delta={delta:.3f}g reason={reason}"
                )
                _write_jsonl(
                    output_path,
                    {
                        "type": "collision_event",
                        "ts_utc": _utc_now(),
                        "sample_idx": sample_idx,
                        "collision_index": collisions,
                        "reason": reason,
                        "accel_mag_g": mag,
                        "delta_from_baseline_g": delta,
                        "accel_g": {"ax": ax, "ay": ay, "az": az},
                        "gyro_dps": {"gx": gx, "gy": gy, "gz": gz},
                    },
                )
            elif print_every > 0 and sample_idx % print_every == 0:
                print(
                    f"[sample {sample_idx}] mag={mag:.3f}g delta={delta:.3f}g "
                    f"impact_hit={impact_hit} tilt_hit={tilt_hit}"
                )

            elapsed = time.monotonic() - loop_t0
            sleep_for = interval - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    finally:
        sensor.close()

    total_sec = time.monotonic() - start
    _write_jsonl(
        output_path,
        {
            "type": "session_end",
            "ts_utc": _utc_now(),
            "samples": sample_idx,
            "collisions": collisions,
            "runtime_sec": round(total_sec, 3),
        },
    )

    print(
        f"[DONE] samples={sample_idx} collisions={collisions} runtime={total_sec:.2f}s "
        f"log={output_path}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Isolated MPU-6050 collision/tap test")
    ap.add_argument("--duration-sec", type=float, default=60.0, help="Test duration")
    ap.add_argument("--sample-hz", type=float, default=50.0, help="Sampling frequency")
    ap.add_argument(
        "--impact-g",
        type=float,
        default=1.8,
        help="Collision trigger by acceleration magnitude (good for tap tests)",
    )
    ap.add_argument(
        "--tilt-delta-g",
        type=float,
        default=1.0,
        help="Collision trigger by baseline delta (orientation change)",
    )
    ap.add_argument(
        "--cooldown-ms",
        type=int,
        default=500,
        help="Debounce/cooldown after each collision event",
    )
    ap.add_argument(
        "--warmup-sec",
        type=float,
        default=2.0,
        help="Warmup period before baseline lock",
    )
    ap.add_argument(
        "--print-every",
        type=int,
        default=0,
        help="Print non-collision sample summary every N samples (default 0 = off)",
    )
    ap.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSONL path (default logs/mpu_collision_*.jsonl)",
    )
    ap.add_argument(
        "--log-all-samples",
        action="store_true",
        help="Log every sample + session_start (default: log only collision_event + session_end)",
    )
    args = ap.parse_args()

    out = Path(args.output) if args.output else _default_log_path()
    if not out.is_absolute():
        out = _project_root() / out
    out.parent.mkdir(parents=True, exist_ok=True)

    return run_test(
        duration_sec=args.duration_sec,
        sample_hz=args.sample_hz,
        impact_g=args.impact_g,
        tilt_delta_g=args.tilt_delta_g,
        cooldown_ms=args.cooldown_ms,
        output_path=out,
        warmup_sec=args.warmup_sec,
        print_every=args.print_every,
        log_collisions_only=not args.log_all_samples,
    )


if __name__ == "__main__":
    raise SystemExit(main())
