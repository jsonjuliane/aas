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

# GPS (software serial or hardware UART for testing)
GPS_RX_GPIO = 20  # Pin 38 — Pi RX ← GPS TX
GPS_TX_GPIO = 21  # Pin 40 — Pi TX → GPS RX
GPS_BAUD = 9600
GPS_SERIAL_PORT = "/dev/ttyS0"  # Use mini UART if GPS wired there; else None for dry run

# MP3 Player (software serial, e.g. DFPlayer Mini)
MP3_TX_GPIO = 19  # Pi TX → MP3 RX (when using software serial)
MP3_RX_GPIO = 26  # Pi RX ← MP3 TX (via 1kΩ resistor)
MP3_BAUD = 9600
MP3_SERIAL_PORT = None  # Set to /dev/ttyS0 etc. if MP3 on serial; None = no audio

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
