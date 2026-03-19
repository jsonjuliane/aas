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
| AT+CSQ | Signal quality |
| AT+CPIN? | SIM status |
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

## Implementation (Phase 1)

- **File**: `src/gsm_sim800l.py`
- **Class**: `GSMSIM800L(device=None, dry_run=False)`
- **Usage**: `gsm.open()`; `ok = gsm.send_sms(phone, text)`.

## References

- [SIM800L AT Command Set](https://simcom.ee/documents/SIM800L/SIM800L_AT_Command_Manual_V1.11.pdf)
- `docs/PLAN.md`, `src/config.py` — `SIM800L_UART_DEVICE`, `SIM800L_BAUD`
