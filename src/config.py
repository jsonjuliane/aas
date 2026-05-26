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
# DFPlayer SD layout: mp3/0001.mp3, mp3/0002.mp3, ... (4-digit names in an "mp3" folder).
# Serial command 0x03 play index N targets 000N.mp3 in that folder (see audio_mp3.play_track).
MP3_DEFAULT_TRACK = 1
MP3_DEFAULT_VOLUME = 12  # DFPlayer range 0..30; applied before countdown play in main

# Optional cancel button (active-low with pull-up)
CANCEL_BUTTON_GPIO = 17  # Wire momentary switch between GPIO17 and GND

# Optional buzzer fallback for countdown cues (GPIO -> transistor/active buzzer)
BUZZER_GPIO = 18
BUZZER_ACTIVE_HIGH = True  # Buzzer silent at LOW, on at HIGH (confirmed by buzzer_diag)
BUZZER_COUNTDOWN_ENABLED = True
BUZZER_BEEP_SEC = 0.08
BUZZER_FINAL_BEEP_SEC = 0.16
BUZZER_MONITOR_READY_ENABLED = True  # Triple beep when monitoring starts / resumes
BUZZER_MONITOR_READY_COUNT = 3
BUZZER_MONITOR_READY_BEEP_SEC = 0.06
BUZZER_MONITOR_READY_GAP_SEC = 0.10

# -----------------------------------------------------------------------------
# Application constants
# -----------------------------------------------------------------------------

# Accident detection (relaxed for easier bench triggering; production: 3.0 / 5.0 / 1.5)
ACCEL_THRESHOLD_G = 1.2  # Minimum g-force to flag potential accident
ACCEL_THRESHOLD_G_MAX = 10.0  # Upper bound for validation (wide so taps >5g still count)
TILT_DELTA_THRESHOLD_G = 0.5  # Baseline delta required to validate true collision
POST_ALERT_COOLDOWN_SEC = 30.0  # No new alert until this long after last alert cycle finished
IMPACT_LOG_COOLDOWN_SEC = 0.75  # Debounce impact candidate logs in main loop
COUNTDOWN_SECONDS = 10
# Countdown cues: buzzer beeps (default). Set True only if DFPlayer MP3 module is wired and working.
COUNTDOWN_USE_MP3 = False

# Accident SMS ``Accident:`` field — reverse geocode lat/lon to street address (Nominatim; needs internet).
REVERSE_GEOCODE_ENABLED = True
REVERSE_GEOCODE_TIMEOUT_SEC = 5.0
REVERSE_GEOCODE_RETRY_COUNT = 2  # Extra Nominatim attempts when the first fails (network flake)
REVERSE_GEOCODE_RETRY_DELAY_SEC = 1.0  # Pause between geocode retries
SMS_ACCIDENT_ADDRESS_MAX_CHARS = 56  # max length for Accident: line (geocode street/area)
SMS_ACCIDENT_COORD_PRECISION = 4  # fallback Accident text and GPS line (must match)

# Voice / mic cancel during countdown
# Primary fallback: GPIO button (CANCEL_BUTTON_GPIO). Keyword cancel prefers offline Vosk when available.
# Set VOICE_CANCEL_SOUND_ENABLED = True to re-enable RMS-based cancel.
VOICE_CANCEL_SOUND_ENABLED = False
VOICE_CANCEL_KEYWORD_ENABLED = True
VOICE_SOUND_RMS_THRESHOLD = 10000  # USB dongle baseline ~p95 6.2k; use mic_test --baseline to retune
VOICE_SOUND_RMS_SUSTAIN_CHUNKS = 5
VOICE_SOUND_SAMPLE_RATE = 16000
VOICE_SOUND_CHUNK_SIZE = 512
# Keyword path (offline first; Google fallback only when engine=auto and offline engines are unavailable)
VOICE_KEYWORD_ENGINE = "auto"  # auto | vosk | pocketsphinx | google
VOICE_VOSK_MODEL_DIR = "models/vosk-model-small-en-us-0.15"
VOICE_AMBIENT_CALIBRATION_SEC = 3.0  # calibrate before the cancel countdown starts
VOICE_KEYWORD_PHRASE_SEC = 3.0  # max seconds per utterance ("cancel")
VOICE_KEYWORD_MIN_RMS = 900  # skip keyword recognition below this; tune with mic_test --sphinx-oneshot
VOICE_KEYWORD_RESULT_GRACE_SEC = 5.0  # allow offline decoder to finish after speech near timeout
GPS_COLLISION_FIX_TIMEOUT_SEC = 8.0
GSM_WAIT_REGISTER_SEC = 30.0  # Max wait for network registration before SMS send
GSM_WAIT_POLL_SEC = 2.0  # Poll interval while waiting for GSM readiness
GSM_MIN_CSQ_TO_SEND = 7  # Minimum usable CSQ to attempt SMS send (0–31; 99=unknown)
GSM_SEND_RETRY_COUNT = 2  # Per-recipient SMS send attempts
GSM_SEND_RETRY_BACKOFF_SEC = 4.0  # Delay between SMS retries after signal is usable again
GSM_SEND_RETRY_SIGNAL_WAIT_SEC = 8.0  # Max wait for CSQ to recover before each attempt/retry
# SMS length: multipart/concat often fails to handsets on prepaid SIMs; prefer one part.
SMS_SINGLE_PART_MAX_CHARS = 160  # GSM 7-bit one-part limit
SMS_ALERT_TARGET_MAX_CHARS = 154  # keep collision alerts under this (margin for handsets)
SMS_SPLIT_PART_MAX_CHARS = 145  # body per part when splitting (room for "(1/2) " prefix)
SMS_INTER_PART_DELAY_SEC = 2.0  # pause between separate CMGS when splitting
GSM_BENCH_TEST_TEXT = "Test text"  # body for: python -m src.gsm_test --send-test-sms PHONE

# Paths (relative to project root)
CONFIG_DIR = "config"
CONTACTS_FAMILY_FILE = "contacts.family.json"
LOGS_DIR = "logs"

# Local phone/app config link PIN used until changed by the linked rider.
CONFIG_LINK_PIN = "000000"

# Phase 2 routing
CONTACTS_BARANGAY_FILE = "contacts.barangay.json"
GEOFENCE_BINAN_FILE = "geofence.binan.json"
BARANGAY_CENTROIDS_BINAN_FILE = "barangay_centroids.binan.json"
BARANGAY_BOUNDARIES_BINAN_FILE = "barangay_boundaries.binan.json"
