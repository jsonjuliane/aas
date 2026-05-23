# Feature: SIM800L GSM / SMS

## Overview

The SIM800L module sends SMS alerts to emergency contacts. Uses hardware UART (primary serial).

## Hardware

| Item | Value |
|------|-------|
| Interface | Hardware UART |
| Pi Pins | TX=Pin 8 (UART TX), RX=Pin 10 (UART RX), GND=Pin 9 |
| Device | `/dev/serial0` or `/dev/ttyAMA0` |
| Baud | 9600 |
| Power | 4V via Buck converter; 100µF capacitor required |

## AT Commands Used

| Command | Purpose |
|---------|---------|
| AT | Basic check |
| ATE0 | Disable command echo (after link up) |
| AT+CMGF=1 | Text mode SMS (before `AT+CMGS`) |
| AT+CSQ | Signal quality |
| AT+CPIN? | SIM status |
| AT+CREG? | Network registration |
| AT+COPS? | Operator (informational) |
| AT+CMGS="\<num\>" | Send SMS |

## Module Interface

See `docs/phase0_module_boundaries.md` — `gsm_sim800l`:

- `open()` / `close()` — UART lifecycle
- `send_sms(phone, text)` — Send SMS; returns True on success

## Power Considerations

SIM800L draws high current bursts during transmit. Ensure:

- Dedicated 4V supply (Buck 2)
- 100µF capacitor at module
- Star ground with Pi

## Implementation

- **Low-level UART**: `src/gsm_sim800l.py` — `GSMSIM800L`, `send_sms_detailed()`
- **Alert policy**: `src/gsm_alert.py` — readiness wait, signal-aware retries (used by `main.py`)

### Collision-alert SMS policy (Phase 2 Step 4)

Configured in `src/config.py`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `GSM_WAIT_REGISTER_SEC` | 30 | Max wait for registration + usable signal before any send |
| `GSM_WAIT_POLL_SEC` | 2 | Poll interval during wait |
| `GSM_MIN_CSQ_TO_SEND` | 7 | Minimum CSQ (0–31) to attempt send; 99 = unknown |
| `GSM_SEND_RETRY_COUNT` | 2 | Attempts per recipient |
| `GSM_SEND_RETRY_BACKOFF_SEC` | 4 | Pause after signal recovers, before retry |
| `GSM_SEND_RETRY_SIGNAL_WAIT_SEC` | 8 | Max wait for CSQ to recover before each attempt/retry |

**Pre-send:** `wait_for_gsm_ready()` then `probe_sms_ready()`. If CSQ stays below threshold after the wait, SMS is **not attempted** (logged as `gsm_not_ready:signal_too_weak:...`).

**Per recipient:** Before each attempt, wait up to `GSM_SEND_RETRY_SIGNAL_WAIT_SEC` for CSQ ≥ minimum. On failure, wait for usable signal again before the second attempt; if signal stays weak, retry is skipped (`weak_signal_retry_aborted`).

## Google Map links in SMS (Philippines / Globe)

**Production collision alerts use plain coordinates** (`GPS: 14.3331, 121.0854`), not an `https://` URL.

Reason: On **Globe** (and similar PH carriers), **person-to-person SMS with clickable links are often blocked at the network** — the SIM800L can still report success (`+CMGS`, `OK`) while the phone never receives the text. See [Globe help: blocking texts with clickable links](https://www.globe.com.ph/help/why-globe-blocks-texts-with-clickable-links).

**Maps URLs (no API key)** — for bench tests only:

| Style | Example |
|-------|---------|
| `legacy` | `https://maps.google.com/?q=14.333122,121.085377` |
| `google_search` | `https://www.google.com/maps/search/?api=1&query=14.333122%2C121.085377` |
| `google_com` | `https://www.google.com/maps?q=14.333122,121.085377` |

There is **no supported public API** to generate `maps.app.goo.gl` short links from a Pi; those are created in the Google Maps app share UI.

**Alternatives if links are required:** WhatsApp/SMS app bypass, Globe **A2P/registered sender** (business SMS, not SIM800L P2P), or keep **GPS coordinates** in SMS.

## Isolated bench test

```bash
python -m src.gsm_test
python -m src.gsm_test --send-sms +639171234567 "Test message"
python -m src.gsm_test --send-map-url-test +639171234567
python -m src.gsm_test --send-map-url-test +639171234567 --map-url-style google_search
python -m src.gsm_alert_test   # Policy unit checks (no hardware)
```

Also covered by `python -m src.hardware_check` (multi-baud AT + quick SIM/signal if AT succeeds).

## References

- [SIM800L AT Command Set](https://simcom.ee/documents/SIM800L/SIM800L_AT_Command_Manual_V1.11.pdf)
- `docs/PLAN.md`, `src/config.py` — `SIM800L_UART_DEVICE`, `SIM800L_BAUD`
