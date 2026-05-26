"""
Safe read/write helpers for ``config/contacts.family.json``.

This module is the local source-of-truth API for future Bluetooth/mobile setup.
It validates edits and writes atomically so the accident alert flow can keep
reading the same JSON file without a database or internet dependency.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from src import contacts
from src.config import CONFIG_DIR, CONTACTS_FAMILY_FILE, PROJECT_ROOT

MAX_FAMILY_CONTACTS = 3


def family_config_path() -> Path:
    return PROJECT_ROOT / CONFIG_DIR / CONTACTS_FAMILY_FILE


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load raw family contact config."""
    cfg_path = path or family_config_path()
    with open(cfg_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Family contacts config must be a JSON object")
    return data


def _clean_text(value: object, *, field: str, max_len: int = 80) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_len:
        raise ValueError(f"{field} is too long (max {max_len} chars)")
    return text


def normalize_contact(entry: dict[str, Any], *, default_priority: int) -> dict[str, Any]:
    """Validate and normalize one contact entry."""
    if not isinstance(entry, dict):
        raise ValueError(f"Invalid contact entry: {entry!r}")
    name = _clean_text(entry.get("name"), field="contact.name", max_len=40)
    phone = contacts.normalize_phone(_clean_text(entry.get("phone"), field="contact.phone"))
    if not (phone.startswith("+63") and len(phone) == 13 and phone[1:].isdigit()):
        raise ValueError(f"Invalid Philippine phone number: {entry.get('phone')!r}")
    try:
        priority = int(entry.get("priority", default_priority))
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid contact priority: {entry.get('priority')!r}") from e
    return {"name": name, "phone": phone, "priority": max(1, priority)}


def normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    """Return a validated, normalized config ready to save."""
    out = deepcopy(data)
    out["version"] = int(out.get("version", 1))
    out["rider_name"] = _clean_text(out.get("rider_name"), field="rider_name", max_len=60)
    out["subject_home_barangay"] = _clean_text(
        out.get("subject_home_barangay"),
        field="subject_home_barangay",
        max_len=60,
    )
    template = str(out.get("message_template") or contacts.FINAL_SMS_ALERT_TEMPLATE)
    if not template.strip():
        raise ValueError("message_template is required")
    # Validate placeholder compatibility with the existing formatter.
    contacts.format_alert_message(
        template=template,
        lat=14.3331,
        lon=121.0854,
        rider_name=out["rider_name"],
        home_barangay=out["subject_home_barangay"],
        area="Inside Binan",
        accident_barangay="Test Accident",
        notified="test",
    )
    out["message_template"] = template

    raw_contacts = out.get("contacts")
    if not isinstance(raw_contacts, list):
        raise ValueError("contacts must be a list")
    if not raw_contacts:
        raise ValueError("At least one family contact is required")
    if len(raw_contacts) > MAX_FAMILY_CONTACTS:
        raise ValueError(f"At most {MAX_FAMILY_CONTACTS} family contacts are allowed")

    normalized = [
        normalize_contact(entry, default_priority=i + 1)
        for i, entry in enumerate(raw_contacts)
    ]
    normalized.sort(key=lambda c: (int(c["priority"]), str(c["name"]).lower()))
    for i, entry in enumerate(normalized, start=1):
        entry["priority"] = i
    out["contacts"] = normalized
    return out


def save_config(data: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """
    Validate and atomically save config.

    A ``.bak`` copy of the previous config is written before replacement.
    """
    cfg_path = path or family_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_config(data)
    if cfg_path.exists():
        shutil.copy2(cfg_path, cfg_path.with_suffix(cfg_path.suffix + ".bak"))
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{cfg_path.name}.",
        suffix=".tmp",
        dir=str(cfg_path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_name, cfg_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return normalized


def public_config(
    data: dict[str, Any] | None = None,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Return normalized config fields intended for app/Bluetooth reads."""
    cfg = normalize_config(data if data is not None else load_config(path))
    return {
        "rider_name": cfg["rider_name"],
        "subject_home_barangay": cfg["subject_home_barangay"],
        "contacts": cfg["contacts"],
        "message_template": cfg["message_template"],
    }


def set_rider(
    *,
    rider_name: str | None = None,
    subject_home_barangay: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_config(path)
    if rider_name is not None:
        cfg["rider_name"] = rider_name
    if subject_home_barangay is not None:
        cfg["subject_home_barangay"] = subject_home_barangay
    return save_config(cfg, path=path)


def add_contact(
    *,
    name: str,
    phone: str,
    priority: int | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_config(path)
    items = list(cfg.get("contacts", []))
    if len(items) >= MAX_FAMILY_CONTACTS:
        raise ValueError(f"Contact limit reached ({MAX_FAMILY_CONTACTS})")
    items.append(
        {
            "name": name,
            "phone": phone,
            "priority": priority if priority is not None else len(items) + 1,
        }
    )
    cfg["contacts"] = items
    return save_config(cfg, path=path)


def update_contact(
    index: int,
    *,
    name: str | None = None,
    phone: str | None = None,
    priority: int | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_config(path)
    items = list(cfg.get("contacts", []))
    i = index - 1
    if i < 0 or i >= len(items):
        raise ValueError(f"Contact index out of range: {index}")
    item = dict(items[i])
    if name is not None:
        item["name"] = name
    if phone is not None:
        item["phone"] = phone
    if priority is not None:
        item["priority"] = priority
    items[i] = item
    cfg["contacts"] = items
    return save_config(cfg, path=path)


def delete_contact(index: int, *, path: Path | None = None) -> dict[str, Any]:
    cfg = load_config(path)
    items = list(cfg.get("contacts", []))
    i = index - 1
    if i < 0 or i >= len(items):
        raise ValueError(f"Contact index out of range: {index}")
    del items[i]
    cfg["contacts"] = items
    return save_config(cfg, path=path)


def replace_contacts(
    new_contacts: list[dict[str, Any]],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_config(path)
    cfg["contacts"] = new_contacts
    return save_config(cfg, path=path)


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(description="Read/write SmartShell family contact config")
    ap.add_argument(
        "--path",
        type=Path,
        help="Alternate contacts.family.json path for testing",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("get", help="Print rider info and contacts as JSON")
    sub.add_parser("validate", help="Validate current config")

    p = sub.add_parser("set-rider", help="Update rider name and/or home barangay")
    p.add_argument("--name", dest="rider_name")
    p.add_argument("--home", dest="subject_home_barangay")

    sub.add_parser("list-contacts", help="Print contacts only")

    p = sub.add_parser("add-contact", help="Add family contact")
    p.add_argument("--name", required=True)
    p.add_argument("--phone", required=True)
    p.add_argument("--priority", type=int)

    p = sub.add_parser("update-contact", help="Update family contact by 1-based index")
    p.add_argument("index", type=int)
    p.add_argument("--name")
    p.add_argument("--phone")
    p.add_argument("--priority", type=int)

    p = sub.add_parser("delete-contact", help="Delete family contact by 1-based index")
    p.add_argument("index", type=int)

    p = sub.add_parser("replace-contacts", help="Replace contacts from JSON file")
    p.add_argument("json_file", help="File containing a JSON list of contacts")

    args = ap.parse_args()
    try:
        if args.cmd == "get":
            _print_json(public_config(path=args.path))
        elif args.cmd == "validate":
            public_config(path=args.path)
            print("OK")
        elif args.cmd == "set-rider":
            if args.rider_name is None and args.subject_home_barangay is None:
                ap.error("set-rider requires --name and/or --home")
            _print_json(public_config(set_rider(
                rider_name=args.rider_name,
                subject_home_barangay=args.subject_home_barangay,
                path=args.path,
            )))
        elif args.cmd == "list-contacts":
            _print_json(public_config(path=args.path)["contacts"])
        elif args.cmd == "add-contact":
            _print_json(public_config(add_contact(
                name=args.name,
                phone=args.phone,
                priority=args.priority,
                path=args.path,
            )))
        elif args.cmd == "update-contact":
            _print_json(public_config(update_contact(
                args.index,
                name=args.name,
                phone=args.phone,
                priority=args.priority,
                path=args.path,
            )))
        elif args.cmd == "delete-contact":
            _print_json(public_config(delete_contact(args.index, path=args.path)))
        elif args.cmd == "replace-contacts":
            with open(args.json_file, encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list):
                raise ValueError("replace-contacts file must contain a JSON list")
            _print_json(public_config(replace_contacts(payload, path=args.path)))
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
