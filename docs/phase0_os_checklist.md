# Phase 0 — Raspberry Pi OS Configuration Checklist

Use this checklist to prepare Raspberry Pi OS for the SmartShell hardware. Run these steps **before** running the main application.

---

## 1. Enable I2C (MPU-6050)

1. Run `sudo raspi-config`
2. **Interface Options** → **I2C** → **Yes**
3. Reboot: `sudo reboot`
4. Verify device at `0x68`:
   ```bash
   sudo apt-get update
   sudo apt-get install -y i2c-tools
   sudo i2cdetect -y 1
   ```
   Expected: `68` appears in the grid.

---

## 2. Enable Serial (SIM800L hardware UART)

1. Run `sudo raspi-config`
2. **Interface Options** → **Serial Port**
3. **Login shell over serial**: **No**
4. **Serial port hardware**: **Yes**
5. Reboot: `sudo reboot`
6. Verify device:
   ```bash
   ls -la /dev/serial0
   # or /dev/ttyAMA0 on some images
   ```

---

## 3. Audio Output (MP3 countdown)

Choose one:

| Option | Notes |
|--------|-------|
| **USB sound card** | Plug in, set as default in `raspi-config` → System Options → Audio |
| **I2S DAC** | Requires `dtparam=i2s=on` and overlay in `/boot/config.txt` |
| **HDMI** | Not typical for helmet; use only for bench testing |

Verify:
```bash
aplay -l
# Play a test file if available
```

---

## 4. Python Environment

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
# For voice cancel (Phase 3):
sudo apt-get install -y portaudio19-dev
```

Create venv and install deps:
```bash
cd /path/to/AccidentAlertSystem
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 5. GPIO Access

GPIO (buzzer, optional cancel button) requires either:

- Running as `root`, or
- Adding user to `gpio` group: `sudo usermod -aG gpio $USER` (then log out and back in)

---

## 6. Quick Verification

After completing the checklist:

| Check | Command / Action |
|-------|------------------|
| I2C | `sudo i2cdetect -y 1` shows `68` |
| Serial | `ls /dev/serial0` exists |
| Python | `python3 -c "import smbus2, serial"` succeeds |
| GPIO | `python3 -c "import RPi.GPIO; print('OK')"` (on Pi only) |

---

## References

- [Raspberry Pi I2C](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#i2c)
- [Serial configuration](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#uart)
- Project `README.md` for wiring and power notes
