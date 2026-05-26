# SmartShell App

Flutter app for local SmartShell helmet setup.

## Current Flow

1. Open the app.
2. Enter the helmet PIN.
3. Connect in **Mock** mode for local testing, or **BLE** mode when the Pi GATT server is running.
4. Read rider info and emergency contacts.
5. Add, update, or delete up to 3 emergency contacts.
6. Review the JSON command/response diagnostics at the bottom of the screen.

The app uses the same command shape as the Pi:

```json
{"op":"get_config","pin":"000000"}
{"op":"set_rider","pin":"000000","rider_name":"Juan Dela Cruz","subject_home_barangay":"Zapote"}
{"op":"update_contact","pin":"000000","index":1,"name":"Mom","phone":"09201234567"}
{"op":"change_pin","pin":"000000","new_pin":"123456"}
```

## BLE Contract

The Pi BLE server advertises:

- Local name: `SmartShell`
- Service UUID: `f2d00001-8b6b-4d5d-9d53-5e77295c1c01`
- RX write UUID: `f2d00002-8b6b-4d5d-9d53-5e77295c1c01`
- TX notify UUID: `f2d00003-8b6b-4d5d-9d53-5e77295c1c01`

The BLE mode scans for `SmartShell`, connects to the service, subscribes to TX notifications, writes newline-terminated JSON to RX, and waits for newline-terminated JSON responses.

## Run Locally

```bash
cd mobile/smartshell_app
flutter pub get
flutter run -d macos
```

If you prefer browser testing:

```bash
flutter run -d chrome
```

## Pi Test Pairing

On the Pi:

```bash
python -m src.ble_config_server
```

In the Flutter app:

1. Select **BLE**.
2. Tap **Scan for Helmets**.
3. Select a SmartShell helmet.
4. Enter the same PIN configured on the Pi. First-link default is `000000`.
5. Tap **Connect to Selected Helmet**.
