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

This example selects bang-bang with thresholds at target ±0.5 °C and 30% ON
power. Choose ON power for your heater supply; the fresh-setting default is
100%, subject to existing heater limits. PID remains the initial regulator.
Use `thermal pid` to switch back. `pid <Kp> <Ki> <Kd>` only changes gains;
it does not select PID. `thermal on/off` enables/disables the selected regulator.

Bang-bang turns ON at or below target minus hysteresis, OFF at or above target
plus hysteresis, and retains its state inside that band. Hysteresis is a
half-width (>0..10 °C); ON power accepts 0..100%. Both regulators use the same
fused temperature, target, output limits and overtemperature cutoff. The cutoff always
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

The flight computer sends
`THERMAL_CONFIG,time_ms,mode,hysteresis_K,on_power_percent,fusion` at startup
and every 60 s, and queues an immediate update after regulator, fusion,
hysteresis or bang-bang-power commands. The GS displays the reported
configuration and logs it in `thermal_config.csv`; the dashboard labels the
selected regulator. Updates still depend on uplink pacing and downlink queue
delay. Existing THERMAL/PID messages remain unchanged.

Validation: host-side regression tests exercise the real controller source with
simulated EEPROM, sensor and heater interfaces. Hardware timing, PWM and thermal
response still require a Teensy bench test before use.

## Thermal sensor fusion

The selected control sensors are TEMP_1, TEMP_2, TEMP_5, TEMP_6, TEMP_7 and
TEMP_9 in Flight Software's `include/config.h`. All six must be valid by default;
a missing selected sensor turns heating off, including manual heating. The
plate sensor TEMP_3 is separate. A per-sensor 40 °C cutoff is checked before
fusion, so MEAN or MEDIAN cannot hide an overheated control sensor.

Use `fusion mean`, `fusion median`, `fusion min` or `fusion max` in the GS.
The selected mode persists on the Teensy and a change clears automatic
controller history. Sensor membership and the minimum valid count remain
firmware configuration settings. The GS sends compact `SET_FUSION` and
`SET_MODE` wire commands so even five-digit command IDs fit the 1 kbit/s
uplink burst budget; the longer legacy names remain accepted.

## Heating-plate temperature limit

The terminal exposes the independent heating-plate safety limiter:

```text
platelimit 50
platelimit on
platelimit off
```

`platelimit <value>` accepts 0..100 °C. The flight computer stores the limit
and enabled state persistently. Fresh EEPROM defaults to a 50 °C limit with
the limiter OFF; `platelimit 50` changes the value, and `platelimit on` arms it. The thermal panel shows whether the limiter is
OFF, ARMED, TRIPPED, or STALE, plus its configured limit, live plate
temperature, configured TEMP sensor, and protected heater channel. A protected
heater value of `ALL HEATERS` corresponds to flight configuration value 0.

The flight computer sends
`PLATE_LIMIT,time_ms,enabled,limit_K,temperature_K,tripped,sensor,heater`.
Reports follow the 1 s thermal-sampling cadence and become STALE after 10 s
or on disconnect. The GS records them in `plate_limit.csv`. Temperature values on the
wire and in CSV remain Kelvin; the terminal converts them to °C.

## Temperature units and storage health

The terminal GS and browser dashboard show temperatures and target values in
**°C**, including PT1000, PADS, HIDS and temperature plots. `target 25` now
means **25 °C** and sends `CMD,SET_TARGET,298.15` to the flight computer.
`hysteresis 0.5` means a ±0.5 °C half-width (numerically identical to 0.5 K).
Raw protocol messages and CSV temperature columns remain in Kelvin.

Storage health lists four independent devices: Primary internal SD, Primary
backup XTSD, Secondary internal SD, and Secondary backup XTSD. Each has its
own error count. FAULT and STALE transitions produce highlighted ERROR entries
in the console/dashboard log, including failures already present at connection.
Identical repeated reports do not spam the console; state/counter changes do.
Health reports are also saved in `health.csv`.

Update both Teensys to receive all four statuses. The Secondary sends storage
status every five seconds over its UART link. The Primary reports WAITING
before the first status and STALE after more than 15 seconds without one;
STALE indicates missing status, not a confirmed card failure. Counters belong
to each board's current boot, and may return to zero after a reset. DISABLED
means that storage was disabled in the firmware configuration. Old aggregate
`SD` messages remain readable for compatibility. If the GS itself is offline,
health values are the last received values; check the connection indicator.


### Secondary link and temperature freshness

The primary reports `HEALTH,time_ms,SECONDARY,state,error_count` at startup
and every 60 seconds. `WAITING` allows 15 seconds after link initialization. Any valid UART
AIRDOS, storage, or overflow-status frame proves the secondary is active;
15 seconds without one gives `FAULT`. The existing periodic secondary status
frames keep this independent of AIRDOS measurement traffic. Recovery is
automatic. The counter reports UART parsing errors, not disconnect count.
The GS logs fault/recovery transitions and shows a permanent secondary state.
A lost primary/GS connection makes this status STALE, not proof that the
secondary itself has failed. Older firmware without this report shows UNKNOWN.

Terminal and browser temperature displays track each PT1000, PADS, HIDS and
thermal-control temperature independently. At 10 seconds without a received
sample they show STALE and the last sample age. Sensor FAULT or non-finite
temperature shows INVALID; never-received channels show WAITING. Disconnection
immediately invalidates received values; reconnect requires new measurements.
Healthy status messages do not refresh the sample timer. Timing is based on
GS reception and does not measure network queue latency. Raw logged values and
historical plots are retained. No thermal-control behavior is changed.

### Primary RTC telemetry

The primary sends `RTC,time_ms,valid,timestamp_utc` at startup and every 60
seconds with health
telemetry, through the existing bandwidth-limited system queue. For example:
`RTC,12345,1,2026-09-21T12:34:56Z`. An unsynchronized clock sends
`RTC,12345,0,`. UTC uses the same TimeLib/hardware RTC source as SD timestamps;
validity confirms synchronization, not accuracy against an external clock.
The terminal and browser dashboard show the last received sample in UTC and
its reception age (not transport latency), with STALE after 75 seconds or
while disconnected. No PC-clock substitution or RTC-setting command is used.
Update both firmware and GS; older firmware leaves the display waiting.

### Binary telemetry

This version accepts both SHB1 binary telemetry and legacy text telemetry. Install
it before flashing the matching binary Flight Software. The UI and decoded logs
keep their existing formats; raw SHB1 traffic is logged losslessly as hex.
See [protocol and replay results](BINARY_TELEMETRY.md).
