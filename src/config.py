"""
SmartShell — Central configuration and pin constants.

This module defines hardware pin mappings and application constants
as specified in docs/PLAN.md and README.md. All modules should import
from here to ensure consistency.
"""

from __future__ import annotations

from pathlib import Path

# Repository root (parent of src/). Use for resolving config/logs paths.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------------
# Raspberry Pi Zero W — Physical pin mapping (BCM numbering for GPIO)
# -----------------------------------------------------------------------------

# MPU-6050 (I2C)
MPU6050_I2C_BUS = 1
MPU6050_I2C_ADDR = 0x68

# SIM800L (hardware UART)
SIM800L_UART_DEVICE = "/dev/serial0"
SIM800L_BAUD = 9600

# GPS (breadboard default: GPIO 20/21 via pigpio software UART)
GPS_RX_GPIO = 20  # Pin 38 — Pi RX ← GPS TX
GPS_TX_GPIO = 21  # Pin 40 — Pi TX → GPS RX
GPS_BAUD = 9600
# None = use GPIO software UART (GPS_RX/TX_GPIO) in gps.py.
# Set to e.g. "/dev/ttyUSB0" only if GPS is physically on a kernel serial adapter.
GPS_SERIAL_PORT: str | None = None

# MP3 / DFPlayer (breadboard default: GPIO 19/26 via pigpio software UART)
MP3_TX_GPIO = 19  # Pi TX → MP3 RX (when using software serial)
MP3_RX_GPIO = 26  # Pi RX ← MP3 TX (via 1kΩ resistor)
# Optional DFPlayer BUSY pin (LOW while playing, HIGH when idle).
# Set to BCM pin number if wired (e.g. 16), else keep None.
MP3_BUSY_GPIO: int | None = None
MP3_BAUD = 9600
# Default to GPIO software UART for DFPlayer in the current wiring.
# Set to e.g. "/dev/ttyUSB0" only when MP3 is on a USB-TTL adapter.
MP3_SERIAL_PORT: str | None = None
# Folder-based playback defaults for DFPlayer layout:
# SD root/001/001.mp3 (countdown), SD root/002/001.mp3, etc.
MP3_DEFAULT_FOLDER = 1
MP3_DEFAULT_FILE = 1
# Scan range used to find first non-empty folder via DFPlayer feedback.
MP3_FOLDER_SCAN_MAX = 20

# Optional cancel button (Phase 1 fallback)
CANCEL_BUTTON_GPIO = 17  # Optional; add if you wire a cancel button

# -----------------------------------------------------------------------------
# Application constants
# -----------------------------------------------------------------------------

# Accident detection
ACCEL_THRESHOLD_G = 3.0  # Minimum g-force to flag potential accident
ACCEL_THRESHOLD_G_MAX = 5.0  # Upper bound for validation
TILT_DELTA_THRESHOLD_G = 1.5  # Baseline delta required to validate true collision
ACTION_COOLDOWN_SEC = 8.0  # Debounce action flow after a true collision
IMPACT_LOG_COOLDOWN_SEC = 0.75  # Debounce impact candidate logs in main loop
# Temporary longer cancel window for field testing (restore to 5 when stable).
COUNTDOWN_SECONDS = 10

# Voice / mic cancel during countdown
# Sound-based cancel: any sustained loud input aborts (PyAudio RMS; tune threshold on device).
VOICE_CANCEL_SOUND_ENABLED = True
VOICE_SOUND_RMS_THRESHOLD = 900  # audioop RMS on 16-bit mono; raise if wind/fan false-triggers
VOICE_SOUND_RMS_SUSTAIN_CHUNKS = 5  # consecutive loud chunks before cancel
VOICE_SOUND_SAMPLE_RATE = 16000
VOICE_SOUND_CHUNK_SIZE = 512
# Google keyword path can block for ~1s per iteration and skip countdown logs; off by default.
VOICE_CANCEL_KEYWORD_ENABLED = False

GPS_COLLISION_FIX_TIMEOUT_SEC = 8.0
GSM_WAIT_REGISTER_SEC = 30.0  # Max wait for network registration before SMS send
GSM_WAIT_POLL_SEC = 2.0  # Poll interval while waiting for GSM readiness
GSM_MIN_CSQ_TO_SEND = 7  # Minimum usable CSQ to attempt SMS send
GSM_SEND_RETRY_COUNT = 2  # Per-recipient SMS send attempts
GSM_SEND_RETRY_BACKOFF_SEC = 4.0  # Delay between SMS retries for same recipient

# Paths (relative to project root)
CONFIG_DIR = "config"
CONTACTS_FAMILY_FILE = "contacts.family.json"
CONTACTS_BARANGAY_FILE = "contacts.barangay.json"
GEOFENCE_BINAN_FILE = "geofence.binan.json"
ASSETS_AUDIO_DIR = "assets/audio"
LOGS_DIR = "logs"
