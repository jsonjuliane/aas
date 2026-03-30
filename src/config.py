"""
SmartShell — Central configuration and pin constants.

This module defines hardware pin mappings and application constants
as specified in docs/PLAN.md and README.md. All modules should import
from here to ensure consistency.
"""

from __future__ import annotations

# -----------------------------------------------------------------------------
# Raspberry Pi Zero W — Physical pin mapping (BCM numbering for GPIO)
# -----------------------------------------------------------------------------

# MPU-6050 (I2C)
MPU6050_I2C_BUS = 1
MPU6050_I2C_ADDR = 0x68

# SIM800L (hardware UART)
SIM800L_UART_DEVICE = "/dev/serial0"
SIM800L_BAUD = 9600

# GPS (breadboard: GPIO 20/21 — not the same as /dev/ttyS0 unless you use USB-GPS or an overlay)
GPS_RX_GPIO = 20  # Pin 38 — Pi RX ← GPS TX
GPS_TX_GPIO = 21  # Pin 40 — Pi TX → GPS RX
GPS_BAUD = 9600
# None = do not open a kernel UART for GPS (avoids clashing with GSM on /dev/serial0 → ttyS0).
# Set to e.g. "/dev/ttyUSB0" if the GPS module is on a USB serial adapter.
GPS_SERIAL_PORT: str | None = None

# MP3 / DFPlayer (breadboard: GPIO 19/26 — `audio_mp3` only talks via a kernel serial device)
MP3_TX_GPIO = 19  # Pi TX → MP3 RX (when using software serial)
MP3_RX_GPIO = 26  # Pi RX ← MP3 TX (via 1kΩ resistor)
MP3_BAUD = 9600
# USB-TTL between Pi USB and DFPlayer RX/TX lets `python -m src.main --hardware-check` open this path.
# No adapter: set to None (checks skip). Do not set to /dev/ttyS0 if GSM already uses it.
MP3_SERIAL_PORT: str | None = "/dev/ttyUSB0"

# Buzzer (GPIO → resistor → transistor; typical NPN = HIGH = on, LOW = silent)
BUZZER_GPIO = 18
BUZZER_ACTIVE_HIGH = True  # False if your driver is inverted (swap silence level)

# Optional cancel button (Phase 1 fallback)
CANCEL_BUTTON_GPIO = 17  # Optional; add if you wire a cancel button

# -----------------------------------------------------------------------------
# Application constants
# -----------------------------------------------------------------------------

# Accident detection
ACCEL_THRESHOLD_G = 3.0  # Minimum g-force to flag potential accident
ACCEL_THRESHOLD_G_MAX = 5.0  # Upper bound for validation
COUNTDOWN_SECONDS = 5

# Paths (relative to project root)
CONFIG_DIR = "config"
CONTACTS_FAMILY_FILE = "contacts.family.json"
CONTACTS_BARANGAY_FILE = "contacts.barangay.json"
GEOFENCE_BINAN_FILE = "geofence.binan.json"
ASSETS_AUDIO_DIR = "assets/audio"
LOGS_DIR = "logs"
