#!/usr/bin/env bash
# Create/update a Raspberry Pi Wi-Fi hotspot for local SmartShell setup/dashboard.
#
# Usage:
#   sudo bash deploy/setup-pi-hotspot.sh
#   sudo bash deploy/setup-pi-hotspot.sh "SmartShell-Setup" "smartshell123"
#
# Defaults:
#   SSID:       SmartShell-Setup
#   password:   smartshell123
#   interface:  wlan0
#   Pi address: 192.168.4.1/24

set -euo pipefail

SSID="${1:-SmartShell-Setup}"
PASSWORD="${2:-smartshell123}"
IFACE="${3:-wlan0}"
IP_CIDR="${4:-192.168.4.1/24}"
CON_NAME="${5:-smartshell-hotspot}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo:"
  echo "  sudo bash deploy/setup-pi-hotspot.sh"
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
  echo "ERROR: nmcli not found. This script expects Raspberry Pi OS with NetworkManager."
  echo "Check with: nmcli --version"
  exit 1
fi

if (( ${#PASSWORD} < 8 )); then
  echo "ERROR: hotspot password must be at least 8 characters for WPA-PSK."
  exit 1
fi

echo "Creating hotspot connection:"
echo "  connection: ${CON_NAME}"
echo "  ssid:       ${SSID}"
echo "  interface:  ${IFACE}"
echo "  address:    ${IP_CIDR}"
echo
echo "WARNING: If you are connected to the Pi over Wi-Fi, this may disconnect SSH."
echo

if nmcli -t -f NAME connection show | grep -Fxq "${CON_NAME}"; then
  nmcli connection down "${CON_NAME}" >/dev/null 2>&1 || true
  nmcli connection delete "${CON_NAME}"
fi

nmcli connection add type wifi ifname "${IFACE}" con-name "${CON_NAME}" ssid "${SSID}"
nmcli connection modify "${CON_NAME}" \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  ipv4.method shared \
  ipv4.addresses "${IP_CIDR}" \
  ipv6.method ignore \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "${PASSWORD}" \
  connection.autoconnect yes \
  connection.autoconnect-priority 10

nmcli connection up "${CON_NAME}"

echo
echo "Hotspot is active."
echo "Phone Wi-Fi:"
echo "  SSID:     ${SSID}"
echo "  Password: ${PASSWORD}"
echo
echo "Open local services at:"
echo "  http://192.168.4.1:<port>"
echo
echo "Useful commands:"
echo "  nmcli connection show --active"
echo "  ip addr show ${IFACE}"
echo "  sudo nmcli connection down ${CON_NAME}"
echo "  sudo nmcli connection delete ${CON_NAME}"
