#!/usr/bin/env bash

# Remove the system configuration installed by setup_linux_network.sh.

set -euo pipefail

readonly CONNECTION_NAME="SHROOM"
readonly CONFIG_PATH="/etc/shroom-groundstation/network.conf"
readonly CONFIG_DIRECTORY="/etc/shroom-groundstation"
readonly DISPATCHER_PATH="/etc/NetworkManager/dispatcher.d/90-shroom-network"

if [[ "$EUID" -ne 0 ]]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

SHROOM_INTERFACE=""
TEENSY_IP="172.16.18.131"

if [[ -r "$CONFIG_PATH" ]]; then
    # shellcheck source=/dev/null
    source "$CONFIG_PATH"
fi

if [[ -n "$SHROOM_INTERFACE" ]]; then
    /usr/bin/ip neigh del "$TEENSY_IP" \
        dev "$SHROOM_INTERFACE" >/dev/null 2>&1 || true
fi

/usr/bin/nft delete table inet shroom_filter >/dev/null 2>&1 || true

if command -v nmcli >/dev/null 2>&1 && \
        nmcli -g NAME connection show | grep -Fxq "$CONNECTION_NAME"; then
    nmcli connection down "$CONNECTION_NAME" >/dev/null 2>&1 || true
    nmcli connection delete "$CONNECTION_NAME"
fi

rm -f "$DISPATCHER_PATH" "$CONFIG_PATH"
rmdir "$CONFIG_DIRECTORY" >/dev/null 2>&1 || true

echo "SHROOM network configuration removed."
