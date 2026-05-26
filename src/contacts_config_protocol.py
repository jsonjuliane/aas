"""
JSON command protocol for phone/Bluetooth contact setup.

The Bluetooth layer should pass received JSON payloads to ``handle_request`` and
send the returned JSON object back to the phone.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src import link_security
from src import contacts_config_store as store


def _require_int(value: object, *, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field} must be an integer") from e


def _result(*, ok: bool, request_id: object = None, **fields: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": ok, **fields}
    if request_id is not None:
        out["request_id"] = request_id
    return out


def _parse_payload(payload: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, str):
        parsed = json.loads(payload)
    else:
        parsed = payload
    if not isinstance(parsed, dict):
        raise ValueError("Request must be a JSON object")
    return parsed


def _check_pin(req: dict[str, Any]) -> None:
    if not link_security.verify_pin(req.get("pin")):
        raise PermissionError("invalid or missing config PIN")


def handle_request(
    payload: str | dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """
    Handle one phone/app config request.

    Supported ops:
    - ``ping`` / ``status`` (no PIN required)
    - ``change_pin`` with current ``pin`` and ``new_pin``
    - ``get_config``
    - ``validate``
    - ``set_rider`` with ``rider_name`` and/or ``subject_home_barangay``
    - ``add_contact`` with ``name`` and ``phone``
    - ``update_contact`` with ``index`` plus any contact fields
    - ``delete_contact`` with ``index``
    - ``replace_contacts`` with ``contacts`` list
    """
    request_id: object = None
    try:
        req = _parse_payload(payload)
        request_id = req.get("request_id")
        op = str(req.get("op") or "").strip().lower()
        if op in {"ping", "status"}:
            return _result(
                ok=True,
                request_id=request_id,
                data={
                    "service": "SmartShell Config",
                    "auth_required": link_security.auth_required(),
                },
            )
        _check_pin(req)
        if op == "change_pin":
            new_pin = req.get("new_pin")
            link_security.set_pin(new_pin)
            return _result(
                ok=True,
                request_id=request_id,
                data={"pin_changed": True},
            )
        if op in {"get", "get_config", "read_config"}:
            return _result(
                ok=True,
                request_id=request_id,
                data=store.public_config(path=path),
            )
        if op == "validate":
            store.public_config(path=path)
            return _result(ok=True, request_id=request_id, data={"valid": True})
        if op == "set_rider":
            rider_name = req.get("rider_name", req.get("name"))
            home = req.get("subject_home_barangay", req.get("home_barangay", req.get("home")))
            if rider_name is None and home is None:
                raise ValueError("set_rider requires rider_name and/or subject_home_barangay")
            cfg = store.set_rider(
                rider_name=str(rider_name) if rider_name is not None else None,
                subject_home_barangay=str(home) if home is not None else None,
                path=path,
            )
            return _result(ok=True, request_id=request_id, data=store.public_config(cfg))
        if op == "add_contact":
            cfg = store.add_contact(
                name=str(req.get("name") or ""),
                phone=str(req.get("phone") or ""),
                priority=(
                    _require_int(req["priority"], field="priority")
                    if "priority" in req
                    else None
                ),
                path=path,
            )
            return _result(ok=True, request_id=request_id, data=store.public_config(cfg))
        if op == "update_contact":
            cfg = store.update_contact(
                _require_int(req.get("index"), field="index"),
                name=str(req["name"]) if "name" in req else None,
                phone=str(req["phone"]) if "phone" in req else None,
                priority=(
                    _require_int(req["priority"], field="priority")
                    if "priority" in req
                    else None
                ),
                path=path,
            )
            return _result(ok=True, request_id=request_id, data=store.public_config(cfg))
        if op == "delete_contact":
            cfg = store.delete_contact(
                _require_int(req.get("index"), field="index"),
                path=path,
            )
            return _result(ok=True, request_id=request_id, data=store.public_config(cfg))
        if op == "replace_contacts":
            contacts = req.get("contacts")
            if not isinstance(contacts, list):
                raise ValueError("replace_contacts requires contacts list")
            cfg = store.replace_contacts(contacts, path=path)
            return _result(ok=True, request_id=request_id, data=store.public_config(cfg))
        raise ValueError(f"Unsupported op: {op!r}")
    except PermissionError as e:
        return _result(
            ok=False,
            request_id=request_id,
            auth_required=True,
            error=str(e),
        )
    except Exception as e:
        return _result(ok=False, request_id=request_id, error=str(e))


def main() -> int:
    ap = argparse.ArgumentParser(description="Test phone/Bluetooth config JSON commands")
    ap.add_argument("payload", nargs="?", help="JSON request payload")
    ap.add_argument("--stdin", action="store_true", help="Read JSON request from stdin")
    ap.add_argument("--path", type=Path, help="Alternate contacts.family.json path for testing")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print response JSON")
    args = ap.parse_args()

    if args.stdin:
        payload = sys.stdin.read()
    elif args.payload:
        payload = args.payload
    else:
        ap.error("Provide payload or --stdin")

    response = handle_request(payload, path=args.path)
    print(json.dumps(response, indent=2 if args.pretty else None, ensure_ascii=False))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
