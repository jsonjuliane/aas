#!/bin/bash
# SmartShell — buzzer silence on boot setup.
#
# Adds a line to /etc/rc.local so the buzzer is silenced immediately
# when the Pi powers on, before the main app starts.
#
# Run once on the Pi:
#   chmod +x deploy/setup-buzzer-silence.sh
#   sudo bash deploy/setup-buzzer-silence.sh

set -e

VENV_PYTHON="/home/smartshell/AccidentAlertSystem/.venv/bin/python"
RC_LOCAL="/etc/rc.local"
MARKER="# SmartShell buzzer silence"
SILENCE_CMD="$VENV_PYTHON -m src.buzzer_silence"
WORKDIR="/home/smartshell/AccidentAlertSystem"

echo "[setup] Checking $RC_LOCAL..."

# Create /etc/rc.local if it does not exist
if [ ! -f "$RC_LOCAL" ]; then
    echo "[setup] Creating $RC_LOCAL..."
    cat > "$RC_LOCAL" <<'EOF'
#!/bin/sh -e
exit 0
EOF
    chmod +x "$RC_LOCAL"
fi

# Make sure it is executable
chmod +x "$RC_LOCAL"

# Check if already installed
if grep -q "$MARKER" "$RC_LOCAL"; then
    echo "[setup] Buzzer silence already in $RC_LOCAL — nothing to do."
    exit 0
fi

# Insert before the final 'exit 0' line
TMPFILE=$(mktemp)
# Write all lines except last 'exit 0', then our block, then 'exit 0'
grep -v '^exit 0' "$RC_LOCAL" > "$TMPFILE" || true

cat >> "$TMPFILE" <<EOF

$MARKER
cd $WORKDIR && $SILENCE_CMD &

exit 0
EOF

cp "$TMPFILE" "$RC_LOCAL"
rm "$TMPFILE"

echo "[setup] Done. Buzzer silence added to $RC_LOCAL."
echo "[setup] Reboot to test: sudo reboot"
echo "[setup] Check result:   sudo grep -A2 'SmartShell' /etc/rc.local"
