# Feature: MPU-6050 Accident Detection

## Overview

The MPU-6050 is a 6-DOF IMU (accelerometer + gyroscope) used to detect potential accidents by monitoring sudden changes in acceleration and orientation.

## Hardware

| Item | Value |
|------|-------|
| Interface | I2C |
| Address | 0x68 (default) |
| Pi Pins | SDA=Pin 3, SCL=Pin 5, VCC=Pin 1 (3.3V), GND=Pin 14 |
| Bus | I2C-1 (`/dev/i2c-1`) |

## Detection Logic

1. **Threshold**: Acceleration spike ≥ 3g–5g flags potential accident.
2. **Validation**: Both sudden acceleration spike and abnormal tilt/orientation must be present.
3. **Calibration**: Run at startup to establish baseline (device at rest).

## Module Interface

See `docs/phase0_module_boundaries.md` — `sensor_mpu6050`:

- `calibrate()` — Run at startup
- `read_raw()` / `read_g()` — Get current values
- `is_impact_detected()` — Returns True when threshold exceeded

## Implementation (Phase 1)

- **File**: `src/sensor_mpu6050.py`
- **Class**: `SensorMPU6050(dry_run=False)`
- **Usage**: `sensor.calibrate()` at startup; poll `sensor.is_impact_detected()` in main loop.

## Isolated collision/tap debug test

For focused hardware testing without GSM/GPS flow:

```bash
python -m src.mpu_collision_test
```

Useful options:

```bash
python -m src.mpu_collision_test --impact-g 1.5 --tilt-delta-g 0.8 --duration-sec 120
```

Detailed per-sample JSONL logs are written to `logs/mpu_collision_*.jsonl`.

## References

- [MPU-6050 Datasheet](https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/)
- `docs/PLAN.md`, `src/config.py` — `MPU6050_I2C_BUS`, `MPU6050_I2C_ADDR`
