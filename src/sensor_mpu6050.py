"""
SmartShell — MPU-6050 accelerometer/gyroscope interface.

Provides accident detection via acceleration and orientation thresholds.
See docs/features/01_sensor_mpu6050.md.
"""

from __future__ import annotations

import math
from typing import Any

from src.config import (
    ACCEL_THRESHOLD_G,
    ACCEL_THRESHOLD_G_MAX,
    MPU6050_I2C_ADDR,
    MPU6050_I2C_BUS,
)

# MPU-6050 register addresses
_PWR_MGMT_1 = 0x6B
_ACCEL_XOUT_H = 0x3B
_GYRO_XOUT_H = 0x43
_ACCEL_SCALE = 16384.0  # LSB/g for ±2g
_GYRO_SCALE = 131.0  # LSB/(°/s) for ±250°/s


def _to_signed(val: int) -> int:
    """Convert 16-bit unsigned to signed."""
    return val - 0x10000 if val >= 0x8000 else val


class MPU6050Error(Exception):
    """Raised when MPU-6050 communication fails."""

    pass


class SensorMPU6050:
    """
    MPU-6050 sensor interface for accident detection.

    Calibrate at startup with device at rest. Then poll is_impact_detected()
    in the main loop.
    """

    def __init__(self, dry_run: bool = False) -> None:
        """
        Initialize the sensor.

        Args:
            dry_run: If True, no hardware access; is_impact_detected() always False.
        """
        self._dry_run = dry_run
        self._bus: Any = None
        self._baseline: tuple[float, float, float] | None = None

    def _ensure_bus(self) -> None:
        """Open I2C bus if not already open."""
        if self._dry_run:
            return
        if self._bus is None:
            try:
                import smbus2

                self._bus = smbus2.SMBus(MPU6050_I2C_BUS)
                self._bus.write_byte_data(MPU6050_I2C_ADDR, _PWR_MGMT_1, 0x00)
            except (ImportError, OSError) as e:
                raise MPU6050Error(f"MPU-6050 init failed: {e}") from e

    def calibrate(self, samples: int = 32) -> None:
        """
        Establish baseline acceleration at rest.

        Call with device stationary. Averages samples to reduce noise.

        Args:
            samples: Number of samples to average.
        """
        if self._dry_run:
            return
        self._ensure_bus()
        ax_sum, ay_sum, az_sum = 0.0, 0.0, 0.0
        for _ in range(samples):
            ax, ay, az = self.read_g()
            ax_sum += ax
            ay_sum += ay
            az_sum += az
        self._baseline = (
            ax_sum / samples,
            ay_sum / samples,
            az_sum / samples,
        )

    def read_raw(self) -> dict[str, float]:
        """
        Read raw accelerometer and gyroscope values.

        Returns:
            Dict with keys: ax, ay, az (accel), gx, gy, gz (gyro).
        """
        if self._dry_run:
            return {"ax": 0.0, "ay": 0.0, "az": 0.0, "gx": 0.0, "gy": 0.0, "gz": 0.0}
        self._ensure_bus()
        accel = self._bus.read_i2c_block_data(MPU6050_I2C_ADDR, _ACCEL_XOUT_H, 6)
        gyro = self._bus.read_i2c_block_data(MPU6050_I2C_ADDR, _GYRO_XOUT_H, 6)
        return {
            "ax": _to_signed(accel[0] << 8 | accel[1]) / _ACCEL_SCALE,
            "ay": _to_signed(accel[2] << 8 | accel[3]) / _ACCEL_SCALE,
            "az": _to_signed(accel[4] << 8 | accel[5]) / _ACCEL_SCALE,
            "gx": _to_signed(gyro[0] << 8 | gyro[1]) / _GYRO_SCALE,
            "gy": _to_signed(gyro[2] << 8 | gyro[3]) / _GYRO_SCALE,
            "gz": _to_signed(gyro[4] << 8 | gyro[5]) / _GYRO_SCALE,
        }

    def read_g(self) -> tuple[float, float, float]:
        """
        Read acceleration in g (ax, ay, az).

        Returns:
            Tuple of (ax_g, ay_g, az_g).
        """
        r = self.read_raw()
        return (r["ax"], r["ay"], r["az"])

    def is_impact_detected(self) -> bool:
        """
        Check if acceleration and orientation indicate a potential accident.

        Uses magnitude threshold (3g–5g) and optional tilt validation.
        Returns True if threshold exceeded.

        Returns:
            True if impact detected, False otherwise.
        """
        if self._dry_run:
            return False
        try:
            ax, ay, az = self.read_g()
        except MPU6050Error:
            return False
        mag = math.sqrt(ax * ax + ay * ay + az * az)
        if mag < ACCEL_THRESHOLD_G:
            return False
        if mag > ACCEL_THRESHOLD_G_MAX:
            return True  # Severe impact
        # In range: validate with optional tilt
        if self._baseline:
            bx, by, bz = self._baseline
            tilt_change = math.sqrt(
                (ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2
            )
            if tilt_change > 1.5:  # Significant orientation change
                return True
        return mag >= ACCEL_THRESHOLD_G

    def close(self) -> None:
        """Release I2C bus."""
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
