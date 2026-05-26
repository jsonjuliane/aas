"""
Local PIN security for phone/BLE config linking.

The default PIN is intentionally simple for first setup. Once a rider changes it,
only a salted hash is stored on the Pi.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any

from src.config import CONFIG_DIR, CONFIG_LINK_PIN, PROJECT_ROOT

PIN_FILE_ENV = "SMARTSHELL_CONFIG_PIN_FILE"
PIN_OVERRIDE_ENV = "SMARTSHELL_CONFIG_PIN"
PIN_HASH_ITERATIONS = 120_000
PIN_SALT_BYTES = 16
PIN_MIN_LEN = 4
PIN_MAX_LEN = 12


def pin_file_path() -> Path:
    override = os.environ.get(PIN_FILE_ENV)
    if override:
        return Path(override)
    return PROJECT_ROOT / CONFIG_DIR / "link_pin.json"


def _clean_pin(pin: object) -> str:
    text = str(pin or "").strip()
    if not text:
        raise ValueError("PIN is required")
    if not text.isdigit():
        raise ValueError("PIN must contain digits only")
    if len(text) < PIN_MIN_LEN or len(text) > PIN_MAX_LEN:
        raise ValueError(f"PIN must be {PIN_MIN_LEN}-{PIN_MAX_LEN} digits")
    return text


def _hash_pin(pin: str, salt_hex: str, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    )
    return digest.hex()


def _load_pin_record() -> dict[str, Any] | None:
    path = pin_file_path()
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid PIN file: {path}")
    return data


def auth_required() -> bool:
    return True


def verify_pin(pin: object) -> bool:
    try:
        supplied = _clean_pin(pin)
    except ValueError:
        return False
    env_pin = os.environ.get(PIN_OVERRIDE_ENV)
    if env_pin:
        return hmac.compare_digest(supplied, _clean_pin(env_pin))

    record = _load_pin_record()
    if record is None:
        return hmac.compare_digest(supplied, _clean_pin(CONFIG_LINK_PIN))

    salt = str(record.get("salt") or "")
    stored = str(record.get("pin_hash") or "")
    iterations = int(record.get("iterations") or PIN_HASH_ITERATIONS)
    if not salt or not stored:
        raise ValueError("Invalid PIN file contents")
    candidate = _hash_pin(supplied, salt, iterations)
    return hmac.compare_digest(candidate, stored)


def set_pin(new_pin: object) -> Path:
    clean = _clean_pin(new_pin)
    salt = secrets.token_hex(PIN_SALT_BYTES)
    record = {
        "version": 1,
        "algorithm": "pbkdf2_hmac_sha256",
        "iterations": PIN_HASH_ITERATIONS,
        "salt": salt,
        "pin_hash": _hash_pin(clean, salt, PIN_HASH_ITERATIONS),
    }
    path = pin_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path
