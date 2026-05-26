"""
Bluetooth Serial/RFCOMM config server for phone setup.

Protocol: one JSON command per line, one JSON response per line.
The command payload is handled by ``contacts_config_protocol.handle_request``.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any

from src.contacts_config_protocol import handle_request

SERVICE_NAME = "SmartShell Config"
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"
MAX_LINE_BYTES = 8192


def _response_line(response: dict[str, Any]) -> bytes:
    return (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")


def _handle_line(line: bytes, *, path: Path | None = None) -> bytes:
    text = line.decode("utf-8", errors="replace").strip()
    if not text:
        return b""
    response = handle_request(text, path=path)
    return _response_line(response)


def run_stdio(*, path: Path | None = None) -> int:
    """Run the same line protocol over stdin/stdout for local testing."""
    for raw in sys.stdin.buffer:
        out = _handle_line(raw, path=path)
        if out:
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.flush()
    return 0


def _open_bluetooth_socket(*, channel: int, backlog: int) -> tuple[Any, str, Any | None]:
    """
    Open an RFCOMM server socket.

    Prefer PyBluez because it can advertise an SPP service. Fall back to the
    standard Linux Bluetooth socket if PyBluez is unavailable.
    """
    try:
        import bluetooth

        server = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server.bind(("", channel))
        server.listen(backlog)
        return server, "pybluez", bluetooth
    except ImportError:
        pass

    if not hasattr(socket, "AF_BLUETOOTH"):
        raise RuntimeError("This Python build does not expose Bluetooth sockets")
    server = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    server.bind(("", channel))
    server.listen(backlog)
    return server, "stdlib", None


def _advertise_service(server: Any, bluetooth_mod: Any | None, *, channel: int) -> bool:
    if bluetooth_mod is None:
        print(
            "[BT] PyBluez unavailable; server is listening but may not appear as "
            "a named Serial Port service. Pair first, then connect to RFCOMM channel "
            f"{channel} from a Bluetooth terminal app."
        )
        return False
    try:
        bluetooth_mod.advertise_service(
            server,
            SERVICE_NAME,
            service_id=SPP_UUID,
            service_classes=[SPP_UUID, bluetooth_mod.SERIAL_PORT_CLASS],
            profiles=[bluetooth_mod.SERIAL_PORT_PROFILE],
        )
        print(f"[BT] Advertising service: {SERVICE_NAME}")
        return True
    except Exception as e:
        print(f"[BT] Service advertising failed: {e}")
        return False


def _client_label(addr: object) -> str:
    if isinstance(addr, tuple) and addr:
        return str(addr[0])
    return str(addr)


def handle_client(client: Any, addr: object, *, path: Path | None = None) -> None:
    label = _client_label(addr)
    print(f"[BT] Client connected: {label}")
    buffer = b""
    try:
        client.sendall(
            _response_line(
                {
                    "ok": True,
                    "event": "connected",
                    "service": SERVICE_NAME,
                    "protocol": "newline_json",
                }
            )
        )
        while True:
            chunk = client.recv(1024)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > MAX_LINE_BYTES:
                client.sendall(
                    _response_line(
                        {
                            "ok": False,
                            "error": f"request line too long (max {MAX_LINE_BYTES} bytes)",
                        }
                    )
                )
                buffer = b""
                continue
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                out = _handle_line(line, path=path)
                if out:
                    client.sendall(out)
    finally:
        try:
            client.close()
        except Exception:
            pass
        print(f"[BT] Client disconnected: {label}")


def serve_bluetooth(
    *,
    channel: int,
    backlog: int,
    path: Path | None = None,
    advertise: bool = True,
    once: bool = False,
) -> int:
    server, backend, bluetooth_mod = _open_bluetooth_socket(channel=channel, backlog=backlog)
    try:
        print(f"[BT] SmartShell config server listening on RFCOMM channel {channel} ({backend})")
        if advertise:
            _advertise_service(server, bluetooth_mod, channel=channel)
        while True:
            client, addr = server.accept()
            handle_client(client, addr, path=path)
            if once:
                return 0
    finally:
        try:
            server.close()
        except Exception:
            pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SmartShell phone/Bluetooth config server")
    ap.add_argument("--stdio", action="store_true", help="Use stdin/stdout instead of Bluetooth")
    ap.add_argument("--path", type=Path, help="Alternate contacts.family.json path for testing")
    ap.add_argument("--channel", type=int, default=1, help="RFCOMM channel (default: 1)")
    ap.add_argument("--backlog", type=int, default=1, help="Bluetooth listen backlog")
    ap.add_argument("--once", action="store_true", help="Exit after one Bluetooth client disconnects")
    ap.add_argument(
        "--no-advertise",
        action="store_true",
        help="Do not advertise Serial Port service via PyBluez",
    )
    args = ap.parse_args()

    if args.stdio:
        return run_stdio(path=args.path)

    try:
        return serve_bluetooth(
            channel=max(1, int(args.channel)),
            backlog=max(1, int(args.backlog)),
            path=args.path,
            advertise=not args.no_advertise,
            once=bool(args.once),
        )
    except KeyboardInterrupt:
        print("\n[BT] Stopped.")
        return 0
    except Exception as e:
        print(f"[BT] ERROR: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
