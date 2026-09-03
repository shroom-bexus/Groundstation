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

## Data logging

Every Ground Station start creates a new UTC-named directory below `data/`.
The directory contains `traffic.jsonl` with every UDP application payload sent
or received, `telemetry.jsonl` with all parsed telemetry, and CSV files for the
currently supported telemetry types. Commands and their ACK/NACK/WARN responses
are additionally written to `commands.csv`.

The `data/` directory is ignored by Git and can therefore be copied or archived
without affecting the repository.
