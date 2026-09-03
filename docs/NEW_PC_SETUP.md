# SHROOM Ground Station: setup on a new Linux PC

This guide configures a dedicated Ethernet connection between a Linux ground
station and the SHROOM primary flight computer. The commands are written for
CachyOS and other Arch-based systems using NetworkManager.

## Network parameters

| Item | Value |
|---|---|
| Ground-station IPv4 address | `172.16.18.130/24` |
| Flight-computer IPv4 address | `172.16.18.131/24` |
| Flight-computer MAC address | `04:e9:e5:1c:cb:82` |
| UDP port | `5000` |
| Default uplink limit | `1 kbit/s` |

The Ethernet port is deliberately configured without a gateway or DNS server.
It therefore cannot accidentally become the default route for Internet
traffic.

## 1. Install the required software

```bash
sudo pacman -Syu
sudo pacman -S --needed git uv networkmanager nftables wireshark-qt
```

Enable NetworkManager if it is not already running:

```bash
sudo systemctl enable --now NetworkManager
```

## 2. Obtain the Ground Station

Using HTTPS:

```bash
git clone https://github.com/shroom-bexus/Groundstation.git
cd Groundstation
```

Alternatively, use the SSH URL when an SSH key is registered with GitHub:

```bash
git clone git@github.com:shroom-bexus/Groundstation.git
cd Groundstation
```

Install the requested Python version and project dependencies:

```bash
uv python install 3.14
uv sync --python 3.14
```

## 3. Identify the dedicated Ethernet interface

Connect the Ethernet cable and list the interfaces:

```bash
ip -br link
```

The wired interface is commonly named something such as `enp0s31f6` or
`enp3s0`. Do not select the Wi-Fi interface.

## 4. Configure the SHROOM connection

Replace `enp0s31f6` with the name found in the previous step:

```bash
sudo ./scripts/setup_linux_network.sh enp0s31f6
```

This one-time setup:

- creates an automatically activated NetworkManager profile named `SHROOM`;
- assigns `172.16.18.130/24` to the ground station;
- disables IPv6 on this dedicated link;
- blocks outgoing IPv4 multicast only on the SHROOM interface;
- installs a permanent ARP mapping for the flight computer;
- stores the selected interface for the Ground Station rate display;
- reapplies the firewall and ARP configuration after reboot or reconnect.

## 5. Verify the network

The active connection should be visible:

```bash
nmcli connection show --active
```

Check the local address:

```bash
ip address show dev enp0s31f6
```

Check the static neighbour entry:

```bash
ip neigh show 172.16.18.131
```

The state should be `PERMANENT` and the MAC address should be
`04:e9:e5:1c:cb:82`.

Check the multicast filter:

```bash
sudo nft list table inet shroom_filter
```

Finally, test the flight computer:

```bash
ping -c 3 172.16.18.131
```

Stop diagnostic commands such as `ping` before measuring flight bandwidth.

## 6. Start the Ground Station

From the repository directory:

```bash
uv run python main.py
```

The Ground Station should show the connection as online after receiving UDP
telemetry. Its configured default uplink limit is `1 kbit/s`.

## 7. Optional Wireshark setup

Add the user to the capture group once:

```bash
sudo usermod -aG wireshark "$USER"
```

Log out and back in so the new group becomes active. Confirm it with:

```bash
groups
```

Start Wireshark, select the dedicated Ethernet interface, and capture without
a capture filter. The following display filter shows unwanted IPv4 multicast:

```text
ip.dst == 239.255.255.250 || ip.dst == 224.0.0.251
```

With the SHROOM setup active, this filter should not show newly transmitted
packets on the dedicated interface.

## 8. Updating the Ground Station

```bash
git pull --ff-only
uv sync --python 3.14
```

The system network setup normally does not need to be repeated. Run the setup
script again when the Ethernet interface name changes.

## Removing the configuration

```bash
sudo ./scripts/remove_linux_network.sh
```

This removes only the `SHROOM` NetworkManager profile, the SHROOM nftables
table, the static neighbour entry, and the installed dispatcher/configuration
files. It does not uninstall any packages.
