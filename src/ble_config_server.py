"""
BLE GATT config server for SmartShell phone setup.

Protocol:
- Phone writes UTF-8 JSON command bytes ending with ``\n`` to RX characteristic.
- Pi sends UTF-8 JSON response bytes ending with ``\n`` over TX notifications.

The JSON command itself is handled by ``contacts_config_protocol.handle_request``.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.contacts_config_protocol import handle_request

BLUEZ_SERVICE_NAME = "org.bluez"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"

ADAPTER_NAME = "hci0"
APP_PATH = "/com/smartshell/config"
SERVICE_UUID = "f2d00001-8b6b-4d5d-9d53-5e77295c1c01"
RX_UUID = "f2d00002-8b6b-4d5d-9d53-5e77295c1c01"
TX_UUID = "f2d00003-8b6b-4d5d-9d53-5e77295c1c01"
STATUS_UUID = "f2d00004-8b6b-4d5d-9d53-5e77295c1c01"
DEFAULT_LOCAL_NAME = "SmartShell"
MAX_REQUEST_BYTES = 8192
DEFAULT_NOTIFY_CHUNK_BYTES = 20


def _json_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def handle_command_line(raw: bytes, *, path: Path | None = None) -> bytes:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return b""
    return _json_line(handle_request(text, path=path))


def run_stdio(*, path: Path | None = None) -> int:
    for raw in sys.stdin.buffer:
        out = handle_command_line(raw, path=path)
        if out:
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.flush()
    return 0


def _run_check(command: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        return proc.returncode == 0, proc.stdout.strip()
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _print_check(label: str, ok: bool, detail: str = "") -> bool:
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {label}")
    if detail:
        for line in detail.splitlines()[:8]:
            print(f"      {line}")
    return ok


def run_diagnostics(adapter: str) -> int:
    print(f"[BLE] Diagnostics for adapter {adapter!r}")
    print(f"[INFO] Python: {sys.version.split()[0]} on {platform.platform()}")

    ok_all = True
    try:
        import dbus  # noqa: F401

        ok_all &= _print_check("python dbus import", True)
    except Exception as e:
        ok_all &= _print_check("python dbus import", False, str(e))

    try:
        from gi.repository import GLib  # noqa: F401

        ok_all &= _print_check("python gi/GLib import", True)
    except Exception as e:
        ok_all &= _print_check("python gi/GLib import", False, str(e))

    ok, out = _run_check(["systemctl", "is-active", "bluetooth"])
    ok_all &= _print_check("bluetooth service active", ok, out)

    ok, out = _run_check(["rfkill", "list", "bluetooth"])
    ok_all &= _print_check("rfkill bluetooth check", ok, out)

    ok, out = _run_check(["bluetoothctl", "show"])
    ok_all &= _print_check("bluetoothctl show", ok, out)

    try:
        import dbus

        bus = dbus.SystemBus()
        adapter_path = f"/org/bluez/{adapter}"
        obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
        props = dbus.Interface(obj, DBUS_PROP_IFACE)
        powered = bool(props.Get("org.bluez.Adapter1", "Powered"))
        ok_all &= _print_check("adapter powered", powered, f"Powered={powered}")
        interfaces = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable").Introspect()
        ok_all &= _print_check(
            "GATT manager available",
            GATT_MANAGER_IFACE in interfaces,
            GATT_MANAGER_IFACE,
        )
        ok_all &= _print_check(
            "LE advertising manager available",
            LE_ADVERTISING_MANAGER_IFACE in interfaces,
            LE_ADVERTISING_MANAGER_IFACE,
        )
    except Exception as e:
        ok_all &= _print_check("BlueZ D-Bus adapter inspection", False, str(e))

    return 0 if ok_all else 1


def _dbus_array(values: list[Any], signature: str) -> Any:
    import dbus

    return dbus.Array(values, signature=signature)


def _dbus_dict(value: dict[str, Any]) -> Any:
    import dbus

    return dbus.Dictionary(value, signature="sv")


def _bytes_to_dbus(value: bytes) -> Any:
    import dbus

    return dbus.Array([dbus.Byte(b) for b in value], signature="y")


def _dbus_to_bytes(value: Any) -> bytes:
    return bytes(int(b) for b in value)


def _load_dbus_modules() -> tuple[Any, Any, Any, Any]:
    try:
        import dbus
        import dbus.mainloop.glib
        import dbus.service
        from gi.repository import GLib
    except Exception as e:
        raise RuntimeError(
            "BLE GATT server needs python3-dbus and python3-gi. "
            "Install on Pi with: sudo apt-get install -y python3-dbus python3-gi"
        ) from e
    return dbus, dbus.service, dbus.mainloop.glib, GLib


def run_ble_server(
    *,
    adapter: str,
    local_name: str,
    path: Path | None,
    notify_chunk_bytes: int,
) -> int:
    dbus, dbus_service, dbus_mainloop, GLib = _load_dbus_modules()
    dbus_mainloop.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    mainloop = GLib.MainLoop()
    adapter_path = f"/org/bluez/{adapter}"

    class Application(dbus_service.Object):
        def __init__(self) -> None:
            self.path = APP_PATH
            self.services: list[Any] = []
            super().__init__(bus, self.path)
            self.add_service(ConfigService(bus, 0))

        def get_path(self) -> str:
            return dbus.ObjectPath(self.path)

        def add_service(self, service: Any) -> None:
            self.services.append(service)

        @dbus_service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
        def GetManagedObjects(self) -> Any:
            response: dict[Any, Any] = {}
            for service in self.services:
                response[service.get_path()] = service.get_properties()
                for chrc in service.characteristics:
                    response[chrc.get_path()] = chrc.get_properties()
            return response

    class Service(dbus_service.Object):
        PATH_BASE = APP_PATH + "/service"

        def __init__(self, index: int, uuid: str, primary: bool) -> None:
            self.path = self.PATH_BASE + str(index)
            self.uuid = uuid
            self.primary = primary
            self.characteristics: list[Any] = []
            super().__init__(bus, self.path)

        def get_properties(self) -> Any:
            return {
                GATT_SERVICE_IFACE: _dbus_dict(
                    {
                        "UUID": dbus.String(self.uuid),
                        "Primary": dbus.Boolean(self.primary),
                    }
                )
            }

        def get_path(self) -> str:
            return dbus.ObjectPath(self.path)

        def add_characteristic(self, chrc: Any) -> None:
            self.characteristics.append(chrc)

        @dbus_service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface: str) -> Any:
            if interface != GATT_SERVICE_IFACE:
                raise dbus.exceptions.DBusException("Invalid interface")
            return self.get_properties()[GATT_SERVICE_IFACE]

    class Characteristic(dbus_service.Object):
        def __init__(self, service: Any, index: int, uuid: str, flags: list[str]) -> None:
            self.path = service.get_path() + f"/char{index}"
            self.service = service
            self.uuid = uuid
            self.flags = flags
            super().__init__(bus, self.path)

        def get_properties(self) -> Any:
            return {
                GATT_CHRC_IFACE: _dbus_dict(
                    {
                        "Service": dbus.ObjectPath(self.service.get_path()),
                        "UUID": dbus.String(self.uuid),
                        "Flags": _dbus_array(self.flags, "s"),
                    }
                )
            }

        def get_path(self) -> str:
            return dbus.ObjectPath(self.path)

        @dbus_service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface: str) -> Any:
            if interface != GATT_CHRC_IFACE:
                raise dbus.exceptions.DBusException("Invalid interface")
            return self.get_properties()[GATT_CHRC_IFACE]

        @dbus_service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options: Any) -> Any:
            return _bytes_to_dbus(b"")

        @dbus_service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
        def WriteValue(self, value: Any, options: Any) -> None:
            raise dbus.exceptions.DBusException("Not writable")

        @dbus_service.method(GATT_CHRC_IFACE)
        def StartNotify(self) -> None:
            raise dbus.exceptions.DBusException("Not notifiable")

        @dbus_service.method(GATT_CHRC_IFACE)
        def StopNotify(self) -> None:
            raise dbus.exceptions.DBusException("Not notifiable")

        @dbus_service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
        def PropertiesChanged(self, interface: str, changed: Any, invalidated: Any) -> None:
            pass

    class TxCharacteristic(Characteristic):
        def __init__(self, service: Any) -> None:
            super().__init__(service, 1, TX_UUID, ["read", "notify"])
            self.notifying = False
            self.last_value = b'{"ok":true,"status":"ready"}\n'

        @dbus_service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options: Any) -> Any:
            return _bytes_to_dbus(self.last_value)

        @dbus_service.method(GATT_CHRC_IFACE)
        def StartNotify(self) -> None:
            self.notifying = True
            print("[BLE] TX notifications enabled")

        @dbus_service.method(GATT_CHRC_IFACE)
        def StopNotify(self) -> None:
            self.notifying = False
            print("[BLE] TX notifications disabled")

        def send(self, payload: bytes) -> None:
            self.last_value = payload
            if not self.notifying:
                print("[BLE] Response ready, but TX notifications are not enabled")
                return
            chunk_size = max(20, int(notify_chunk_bytes))
            for start in range(0, len(payload), chunk_size):
                chunk = payload[start : start + chunk_size]
                self.PropertiesChanged(
                    GATT_CHRC_IFACE,
                    _dbus_dict({"Value": _bytes_to_dbus(chunk)}),
                    _dbus_array([], "s"),
                )

    class RxCharacteristic(Characteristic):
        def __init__(self, service: Any, tx: TxCharacteristic) -> None:
            super().__init__(service, 0, RX_UUID, ["write", "write-without-response"])
            self.buffer = b""
            self.tx = tx

        @dbus_service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
        def WriteValue(self, value: Any, options: Any) -> None:
            chunk = _dbus_to_bytes(value)
            self.buffer += chunk
            if len(self.buffer) > MAX_REQUEST_BYTES:
                self.tx.send(_json_line({"ok": False, "error": "request too large"}))
                self.buffer = b""
                return
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                response = handle_command_line(line, path=path)
                if response:
                    print(f"[BLE] handled request ({len(line)} bytes) -> {len(response)} bytes")
                    self.tx.send(response)

    class StatusCharacteristic(Characteristic):
        def __init__(self, service: Any) -> None:
            super().__init__(service, 2, STATUS_UUID, ["read"])

        @dbus_service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
        def ReadValue(self, options: Any) -> Any:
            return _bytes_to_dbus(
                _json_line(
                    {
                        "ok": True,
                        "service": "SmartShell BLE Config",
                        "rx_uuid": RX_UUID,
                        "tx_uuid": TX_UUID,
                    }
                )
            )

    class ConfigService(Service):
        def __init__(self, bus_obj: Any, index: int) -> None:
            super().__init__(index, SERVICE_UUID, True)
            tx = TxCharacteristic(self)
            self.add_characteristic(RxCharacteristic(self, tx))
            self.add_characteristic(tx)
            self.add_characteristic(StatusCharacteristic(self))

    class Advertisement(dbus_service.Object):
        PATH_BASE = APP_PATH + "/advertisement"

        def __init__(self, index: int) -> None:
            self.path = self.PATH_BASE + str(index)
            super().__init__(bus, self.path)

        def get_path(self) -> str:
            return dbus.ObjectPath(self.path)

        def get_properties(self) -> Any:
            return {
                LE_ADVERTISEMENT_IFACE: _dbus_dict(
                    {
                        "Type": dbus.String("peripheral"),
                        "ServiceUUIDs": _dbus_array([SERVICE_UUID], "s"),
                        "LocalName": dbus.String(local_name),
                        "Includes": _dbus_array(["tx-power"], "s"),
                    }
                )
            }

        @dbus_service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface: str) -> Any:
            if interface != LE_ADVERTISEMENT_IFACE:
                raise dbus.exceptions.DBusException("Invalid interface")
            return self.get_properties()[LE_ADVERTISEMENT_IFACE]

        @dbus_service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
        def Release(self) -> None:
            print("[BLE] Advertisement released")

    def _ok(label: str) -> Any:
        def cb() -> None:
            print(f"[BLE] {label} registered")

        return cb

    def _err(label: str) -> Any:
        def cb(error: Any) -> None:
            print(f"[BLE] Failed to register {label}: {error}")
            mainloop.quit()

        return cb

    app = Application()
    adv = Advertisement(0)
    adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
    gatt_manager = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)
    ad_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)

    gatt_manager.RegisterApplication(
        app.get_path(),
        {},
        reply_handler=_ok("GATT application"),
        error_handler=_err("GATT application"),
    )
    ad_manager.RegisterAdvertisement(
        adv.get_path(),
        {},
        reply_handler=_ok("advertisement"),
        error_handler=_err("advertisement"),
    )

    print(f"[BLE] Advertising {local_name!r}")
    print(f"[BLE] Service UUID: {SERVICE_UUID}")
    print(f"[BLE] RX write UUID: {RX_UUID}")
    print(f"[BLE] TX notify UUID: {TX_UUID}")
    try:
        mainloop.run()
    except KeyboardInterrupt:
        print("\n[BLE] Stopped.")
    finally:
        try:
            ad_manager.UnregisterAdvertisement(adv.get_path())
        except Exception:
            pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SmartShell BLE GATT config server")
    ap.add_argument("--adapter", default=ADAPTER_NAME)
    ap.add_argument("--name", default=DEFAULT_LOCAL_NAME)
    ap.add_argument("--path", type=Path, help="Alternate contacts.family.json path for testing")
    ap.add_argument("--stdio", action="store_true", help="Use stdin/stdout JSON protocol only")
    ap.add_argument("--diagnose", action="store_true", help="Check BLE/BlueZ prerequisites")
    ap.add_argument(
        "--notify-chunk-bytes",
        type=int,
        default=DEFAULT_NOTIFY_CHUNK_BYTES,
        help="Response notification chunk size; 20 is safest before MTU negotiation",
    )
    args = ap.parse_args()

    if args.stdio:
        return run_stdio(path=args.path)
    if args.diagnose:
        return run_diagnostics(str(args.adapter))

    try:
        return run_ble_server(
            adapter=str(args.adapter),
            local_name=str(args.name),
            path=args.path,
            notify_chunk_bytes=max(20, int(args.notify_chunk_bytes)),
        )
    except Exception as e:
        print(f"[BLE] ERROR: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
