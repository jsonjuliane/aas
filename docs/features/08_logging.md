# Feature: Event Logging

## Overview

Event data (timestamp, acceleration, location, routing decision) is persisted for debugging and record-keeping.

## Data Stored

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 or Unix |
| `accel` | Trigger values (ax, ay, az in g) |
| `lat`, `lon` | GPS coordinates (or null) |
| `recipients` | List of numbers alerted |
| `cancelled` | True if user cancelled |

## Module Interface

See `docs/phase0_module_boundaries.md` — `logging_store`:

- `log_event(data)` — Append to log file
- `get_log_path()` — Path to current log

## Storage

- Directory: `logs/`
- Format: JSON Lines (one JSON object per line) or CSV
- Retention: Define in Phase 4 (e.g. keep last N days)

## Implementation (Phase 1)

- **File**: `src/logging_store.py`
- **Functions**: `log_event(data)` appends JSON line to `logs/events_YYYY-MM-DD.jsonl`.

## References

- `src/config.py` — `LOGS_DIR`
- `docs/PLAN.md` — System Logging step
