# Raspberry Pi — important commands (SmartShell)

Run these from a terminal on the Pi. **Use the same Python you installed dependencies with** (usually the project venv).

---

## Project + venv

```bash
cd ~/AccidentAlertSystem
source .venv/bin/activate
python -m src.main --help
```

If you did not use a venv and installed packages system-wide:

```bash
cd ~/AccidentAlertSystem
python3 -m src.main --help
```

**Why `python -m src.main`?** It runs the package entrypoint correctly; `python src/main.py` can work but `-m` is preferred.

---

## Run modes (same interpreter as above)

```bash
python -m src.main --core-flow-only
python -m src.main --core-flow-only --test-alert
python -m src.main --dry-run
python -m src.buzzer_test --silence-only
python -m src.buzzer_test
python -m src.hardware_check
python -m src.main
```

- **`--core-flow-only`**: init + sensor monitoring / threshold / validation; skips countdown and SMS path.
- **`python -m src.hardware_check`**: one-shot I2C / GPIO / GSM AT / GPS / MP3 port probes (no alert logic). **WARN / SKIP / FAIL / INFO** lines include indented **causes**; the same entries are appended to **`logs/hardware_check.log`** on the Pi (folder is gitignored).
- Startup prints **`GPS serial OK` / `NOT OPEN`** and **`GSM serial OK` / `NOT OPEN`** — see [Serial / GPS vs GSM](#serial--gps-vs-gsm) below.

---

## I2C (MPU-6050)

Enable once: `sudo raspi-config` → Interface Options → **I2C** → Enable → reboot.

```bash
ls /dev/i2c-1
sudo apt-get install -y i2c-tools
sudo i2cdetect -y 1
```

Expect address **`68`** for MPU-6050. If `/dev/i2c-1` is missing, I2C is off or Pi not rebooted.

---

## Serial / GPS vs GSM

Check what the OS exposes:

```bash
ls -l /dev/serial0 /dev/ttyS0 /dev/ttyAMA0 2>/dev/null
```

Typical: **`/dev/serial0` → `ttyS0`** (hardware UART on GPIO 14/15) — good for **SIM800L** when `src/config.py` has `SIM800L_UART_DEVICE = "/dev/serial0"`.

**Conflict:** **GSM** uses **`/dev/serial0`** (usually **`ttyS0`**). Do **not** point `GPS_SERIAL_PORT` to that same UART.  
For breadboard wiring, defaults are now:
- `GPS_SERIAL_PORT = None` → use **pigpio GPIO software UART** on GPS pins (RX GPIO20)
- `MP3_SERIAL_PORT = None` → use **pigpio GPIO software UART TX** on MP3 TX pin (GPIO19)
If you prefer USB adapters, set `GPS_SERIAL_PORT` / `MP3_SERIAL_PORT` to `/dev/ttyUSB*`.

Permissions:

```bash
groups
sudo usermod -aG gpio,dialout $USER
```

Log out and back in (or reboot) after `usermod`.

### If you still get `Permission denied` on `/dev/serial0`

`/dev/serial0` is usually a symlink to `/dev/ttyS0`. Check the **real** device:

```bash
ls -l /dev/serial0
readlink -f /dev/serial0
ls -l $(readlink -f /dev/serial0)
```

**Example — broken state (before fix):** only root can open `ttyS0` (mode **600**). Being in **`dialout`** does not help yet.

```text
lrwxrwxrwx 1 root root 5 ... /dev/serial0 -> ttyS0
/dev/ttyS0
crw------- 1 root root 4, 64 ... /dev/ttyS0
```

`python3 -c "import serial; ... Serial('/dev/serial0'...)"` may then fail with:

```text
PermissionError: [Errno 13] Permission denied: '/dev/serial0'
```

**Fix (persistent):** on the Pi, install a udev rule so `ttyS0` is **`root:dialout`** and mode **660** (run once):

```bash
echo 'SUBSYSTEM=="tty", KERNEL=="ttyS0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-ttyS0-dialout.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo reboot
```

After reboot, confirm (same commands as above):

```bash
ls -l /dev/serial0
readlink -f /dev/serial0
ls -l /dev/ttyS0
```

**Example — fixed state (after rule + reboot):** group **`dialout`**, mode **`crw-rw----`**:

```text
lrwxrwxrwx 1 root root 5 ... /dev/serial0 -> ttyS0
/dev/ttyS0
crw-rw---- 1 root dialout 4, 64 ... /dev/ttyS0
```

Exact major/minor (`4, 64`) and timestamps may differ; the important part is **`rw-rw----`**, **`root`**, **`dialout`**.

### If `/dev/ttyS0` is still `crw------- root root` after reboot

The rule file may not match your kernel/udev, or another rule may run later and reset permissions.

**1. Confirm the rule exists and reload:**

```bash
cat /etc/udev/rules.d/99-ttyS0-dialout.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
ls -l /dev/ttyS0
```

**2. See what udev knows about the device:**

```bash
udevadm info -q all -n /dev/ttyS0
```

**3. Try an alternative rule** (replace the file, reload, trigger, check again — reboot if needed):

```bash
echo 'KERNEL=="ttyS0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-ttyS0-dialout.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
ls -l /dev/ttyS0
```

If still `600`, try adding **`ACTION=="add"`** at the start of the line (some systems need it).

**4. Check for conflicting rules:**

```bash
grep -r ttyS0 /etc/udev/rules.d/ /lib/udev/rules.d/ 2>/dev/null
```

**5. Last-resort (until udev behaves):** after each boot, fix permissions once (not ideal for production):

```bash
sudo chmod 660 /dev/ttyS0
sudo chgrp dialout /dev/ttyS0
ls -l /dev/ttyS0
```

You can automate that with a small **`systemd` oneshot** or **`@reboot` cron** if you must — prefer fixing the udev rule long-term.

**Note:** On some Pi images the UART device is **`ttyAMA0`** instead of **`ttyS0`**. If `readlink -f /dev/serial0` shows **`/dev/ttyAMA0`**, duplicate the rule with `KERNEL=="ttyAMA0"` (or adjust the symlink target in `/boot/firmware/config.txt` / UART overlay docs).

**Non-root AT test** (should open without `PermissionError` once fixed):

```bash
python3 -c "import serial; s=serial.Serial('/dev/serial0',9600,timeout=1); s.write(b'AT\r\n'); print(s.read(200))"
```

**One-shot test as root** (confirms wiring vs permissions if non-root still fails):

```bash
sudo python3 -c "import serial; s=serial.Serial('/dev/serial0',9600,timeout=1); s.write(b'AT\r\n'); print(s.read(200))"
```

---

## Quick GSM (AT) sanity check

Module powered, ground common with Pi, TX/RX crossed correctly, baud **9600** in code:

```bash
python3 -c "import serial; s=serial.Serial('/dev/serial0',9600,timeout=1); s.write(b'AT\r\n'); print(s.read(200))"
```

You want **`OK`** in the response. If `serial0` opens but SmartShell shows **GSM NOT OPEN**, the code requires **`OK`** from `AT` during `open()` — fix power, wiring, or baud.

### pigpio service (required for GPIO software UART)

For GPS/MP3 on GPIO pins (no USB serial adapter), install and start `pigpiod`:

```bash
sudo apt-get update
sudo apt-get install -y pigpio python3-pigpio
sudo systemctl enable --now pigpiod
systemctl status pigpiod --no-pager
```

If `python -m src.hardware_check` says GPS/MP3 open failed in GPIO mode, check this service first.

---

## Troubleshoot GSM and GPS

Run a full report:

```bash
python -m src.hardware_check
```

### GSM (SIM800L on `/dev/serial0`)

| Symptom | What to check |
|--------|----------------|
| `Permission denied` | User in **`dialout`**, **`/dev/ttyS0`** is **`crw-rw---- root dialout`** (udev rule + `udevadm trigger` if needed). |
| Port opens, only see your own `AT\r\n` echo, no **`OK`** | **TX/RX swap**, **GND** common, **power** to module (buck + cap), not a **Pi TX–RX short** (loopback). |
| `Input/output error` on write | Supply sag, bad wiring, or UART/console conflict — **disable serial login** in `raspi-config`, reboot. |
| `OK` sometimes then fails | Typical **brownout** — improve SIM800L supply and wiring. |

### GPS

| Symptom | What to check |
|--------|----------------|
| **`GPS_SERIAL_PORT` is `None`** (default) | This is expected for breadboard mode — code uses **pigpio** software UART on GPS GPIO pins. Ensure `pigpiod` service is running. |
| Check says port missing | Wrong path — run `ls /dev/ttyUSB*` after plugging USB GPS. |
| Port opens, no NMEA in 2s | **Antenna**, sky view, **cold start** (wait longer), wrong baud (9600 in `config.py`), or GPS TX not reaching Pi RX. |

### MP3 (`MP3_SERIAL_PORT`)

| Symptom | What to check |
|--------|----------------|
| `MP3_SERIAL_PORT` is `None` (default) | Breadboard mode — code sends DFPlayer commands via **pigpio** on GPIO19. Ensure `pigpiod` service is running. |
| Want USB adapter instead | Set `MP3_SERIAL_PORT` to `/dev/ttyUSB*` and verify with `ls /dev/ttyUSB*`. |

---

## Buzzer silent at boot (optional hardware bias)

If GPIO 18 floats until software runs, add to `/boot/firmware/config.txt` or `/boot/config.txt`:

```ini
gpio=18=op,dl
```

Reboot. If buzzer stays on, try `gpio=18=op,dh` (inverted driver). Matches `BUZZER_ACTIVE_HIGH` in `src/config.py`.

---

## Boot service (optional)

See `deploy/smartshell.service.example` and **Start on boot (`systemd`)** in `README.md`.

---

## Related docs

- `README.md` — full setup
- `docs/hardware.md` — wiring
- `docs/software_state.md` — what each module expects
