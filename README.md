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


## Selectable thermal regulator

Use the updated Groundstation terminal commands:

```text
thermal off
hysteresis 0.5
bbpower 30
thermal bangbang
thermal on
```

This example selects bang-bang with thresholds at target ±0.5 K and 30% ON
power. Choose ON power for your heater supply; the fresh-setting default is
100%, subject to existing heater limits. PID remains the initial regulator.
Use `thermal pid` to switch back. `pid <Kp> <Ki> <Kd>` only changes gains;
it does not select PID. `thermal on/off` enables/disables the selected regulator.

Bang-bang turns ON at or below target minus hysteresis, OFF at or above target
plus hysteresis, and retains its state inside that band. Hysteresis is a
half-width (>0..10 K); ON power accepts 0..100%. Both regulators use the same
sensor, target, output limits and overtemperature cutoff. The cutoff always
wins, even if the upper hysteresis threshold is above it. There is no automatic
fallback. Missing/invalid/non-finite sensor readings switch heating off.

Switching an enabled regulator clears its history and immediately turns heating
off until the next valid sample. Bang-bang starts OFF inside the band, including
after a reboot or sensor recovery. Changes to its target, hysteresis or power
also restart it OFF. Selecting a regulator while thermal control is OFF does
not enable it or change saved manual outputs.

Regulator selection, hysteresis and ON power survive resets. EEPROM version-2
PID gains, target, enabled state and manual settings are preserved on upgrade.
PID gains remain available when switching back from bang-bang.

The flight computer sends `THERMAL_CONFIG,time_ms,mode,hysteresis_K,on_power_percent`
every health interval (5 s). The GS displays the reported configuration and logs
it in `thermal_config.csv`; the dashboard labels the selected regulator.
Existing THERMAL/PID messages remain unchanged. Update both repositories for
command and display support. New settings may take up to a health interval to
appear, plus any downlink queue delay.

Validation: host-side regression tests exercise the real controller source with
simulated EEPROM, sensor and heater interfaces. Hardware timing, PWM and thermal
response still require a Teensy bench test before use.
