# SHROOM Ground Station

Python ground station for UDP telemetry and command exchange with the SHROOM
primary flight computer.

## Start

```bash
uv sync --python 3.14
uv run python main.py
```

Before using a new Linux PC with the experiment, follow the complete
[new-PC setup guide](docs/NEW_PC_SETUP.md). It includes the static Ethernet
address, automatic ARP configuration, multicast suppression, Wireshark setup,
and verification steps.
