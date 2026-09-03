#!/usr/bin/env bash

# Configure a dedicated NetworkManager profile for the SHROOM flight computer.

set -euo pipefail

readonly CONNECTION_NAME="SHROOM"
readonly GS_ADDRESS="172.16.18.130/24"
readonly TEENSY_IP="172.16.18.131"
readonly TEENSY_MAC="04:e9:e5:1c:cb:82"
readonly CONFIG_DIRECTORY="/etc/shroom-groundstation"
readonly CONFIG_PATH="$CONFIG_DIRECTORY/network.conf"
readonly DISPATCHER_PATH="/etc/NetworkManager/dispatcher.d/90-shroom-network"

usage() {
    echo "Usage: sudo $0 <ethernet-interface>"
    echo "Example: sudo $0 enp0s31f6"
}

if [[ "$EUID" -ne 0 ]]; then
    echo "Run this setup with sudo." >&2
    exit 1
fi

if [[ "$#" -ne 1 ]]; then
    usage >&2
    exit 1
fi

readonly SHROOM_INTERFACE="$1"

if [[ ! "$SHROOM_INTERFACE" =~ ^[a-zA-Z0-9_.:-]+$ ]]; then
    echo "Invalid interface name: $SHROOM_INTERFACE" >&2
    exit 1
fi

if [[ ! -d "/sys/class/net/$SHROOM_INTERFACE" ]]; then
    echo "Interface does not exist: $SHROOM_INTERFACE" >&2
    echo "Use 'ip -br link' to list available interfaces." >&2
    exit 1
fi

for command in nmcli nft ip install; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Required command is missing: $command" >&2
        exit 1
    fi
done

readonly SCRIPT_DIRECTORY="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
)"
readonly DISPATCHER_SOURCE="$SCRIPT_DIRECTORY/shroom-network-dispatcher"

if [[ ! -f "$DISPATCHER_SOURCE" ]]; then
    echo "Missing dispatcher script: $DISPATCHER_SOURCE" >&2
    exit 1
fi

temporary_config="$(mktemp)"
trap 'rm -f "$temporary_config"' EXIT

printf '%s\n' \
    "SHROOM_INTERFACE=$SHROOM_INTERFACE" \
    "TEENSY_IP=$TEENSY_IP" \
    "TEENSY_MAC=$TEENSY_MAC" \
    >"$temporary_config"

install -d -m 0755 "$CONFIG_DIRECTORY"
install -m 0644 "$temporary_config" "$CONFIG_PATH"
install -m 0755 "$DISPATCHER_SOURCE" "$DISPATCHER_PATH"

if nmcli -g NAME connection show | grep -Fxq "$CONNECTION_NAME"; then
    echo "Updating existing NetworkManager profile '$CONNECTION_NAME'."
else
    nmcli connection add \
        type ethernet \
        ifname "$SHROOM_INTERFACE" \
        con-name "$CONNECTION_NAME"
fi

nmcli connection modify "$CONNECTION_NAME" \
    connection.interface-name "$SHROOM_INTERFACE" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    connection.mdns no \
    connection.llmnr no \
    connection.lldp disable \
    ipv4.method manual \
    ipv4.addresses "$GS_ADDRESS" \
    ipv4.gateway "" \
    ipv4.dns "" \
    ipv4.never-default yes \
    ipv6.method disabled

nmcli connection up "$CONNECTION_NAME"

# Apply immediately as well as on future NetworkManager activations.
"$DISPATCHER_PATH" "$SHROOM_INTERFACE" up

echo
echo "SHROOM network setup completed."
echo "Ground station: 172.16.18.130"
echo "Flight computer: $TEENSY_IP"
echo "Interface:       $SHROOM_INTERFACE"
echo
echo "Verify with:"
echo "  ip address show dev $SHROOM_INTERFACE"
echo "  ip neigh show $TEENSY_IP"
echo "  nft list table inet shroom_filter"
