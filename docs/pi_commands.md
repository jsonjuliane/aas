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
python -m src.main --silence-buzzer
python -m src.main --hardware-check
python -m src.main
```

- **`--core-flow-only`**: init + sensor monitoring / threshold / validation; skips countdown and SMS path.
- **`--hardware-check`**: one-shot I2C / GPIO / GSM AT / GPS / MP3 port probes (no alert logic).
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

**Conflict:** **GSM** uses **`/dev/serial0`** (usually **`ttyS0`**). **`GPS_SERIAL_PORT`** must **not** be the same device unless only one module is wired there. Breadboard GPS on **GPIO 20/21** is **not** `ttyS0` in software until you add a **USB GPS** (`/dev/ttyUSB*`) or a suitable overlay — default **`GPS_SERIAL_PORT = None`** avoids fighting GSM. **MP3** in `config.py` defaults to **`/dev/ttyUSB0`** for a **USB-TTL** to the DFPlayer; use **`None`** if you have no adapter (see [Troubleshoot GSM and GPS](#troubleshoot-gsm-and-gps)).

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

---

## Troubleshoot GSM and GPS

Run a full report:

```bash
python -m src.main --hardware-check
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
| **`GPS_SERIAL_PORT` is `None`** (default) | Expected when GPS is on **GPIO 20/21** only — Python here does **not** bit-bang; use a **USB GPS** and set **`GPS_SERIAL_PORT = "/dev/ttyUSB0"`** (or whatever `ls /dev/ttyUSB*` shows), or add future GPIO-UART support. |
| Check says port missing | Wrong path — run `ls /dev/ttyUSB*` after plugging USB GPS. |
| Port opens, no NMEA in 2s | **Antenna**, sky view, **cold start** (wait longer), wrong baud (9600 in `config.py`), or GPS TX not reaching Pi RX. |

### MP3 (`MP3_SERIAL_PORT`)

| Symptom | What to check |
|--------|----------------|
| **`FAIL` missing `/dev/ttyUSB0`** | No USB-serial adapter — set **`MP3_SERIAL_PORT = None`** in `src/config.py`, or plug adapter and confirm `ls /dev/ttyUSB0`. |
| DFPlayer only on GPIO 19/26 | This repo expects a **kernel** `/dev/tty*` for `audio_mp3`; USB-TTL is the usual bench setup until GPIO software-UART exists. |

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
