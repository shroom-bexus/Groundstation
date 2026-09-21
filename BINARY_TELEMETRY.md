# SHB1 binary telemetry

SHB1 replaces regular CSV telemetry on UDP, including AIRDOS and housekeeping.
Commands and immediate ACK/NACK/WARN/session replies remain text. SD logging and
secondary-to-primary UART forwarding are unchanged. Update Groundstation first:
it accepts both legacy text telemetry and SHB1. An old GS cannot decode SHB1.
Deploy matching `feature/binary-telemetry` branches in both repositories.

The codec is lossless for the existing CSV text: no floating-point rounding,
assumed AIRDOS sensor bit widths, or discarded unknown fields. Canonical unsigned
32-bit decimal integers are compacted. Decimals, signed values, leading zeros,
large integers and unknown words are preserved literally. A raw-record fallback
is used whenever token encoding would be larger. This deliberately trades some
possible compression for exact recovery of the original scientific data.

## Wire format

All multi-byte integers are little endian. No native C++ structs are transmitted.
A UDP datagram starts with four ASCII bytes `SHB1`, then a uint32 packet sequence
(shared with the existing telemetry sequence counter). It contains one or more
records, up to 1200 bytes total. Each record has a uint16 body length, including
a one-byte mode followed by its data. Mode 0 means raw UTF-8 CSV without newline.
Mode 1 means comma-separated fields encoded as tokens until the record ends:

| Token | Following data | Decoded field |
|---|---|---|
| 0–239 | none | Decimal integer equal to token |
| 240 | uint32 | Canonical unsigned decimal integer |
| 241 | uint16 byte length, literal bytes | Exact original field, including empty |
| 242 | uint8 dictionary index | Entry from the table below |
| 243–255 | reserved | Reject packet |

Dictionary, in index order (0–11): `AIRDOS`, `$E`, `$START`, `$STOP`, `$ENV`,
`HEALTH`, `PADS`, `THERMAL`, `MAX31865`, `RTC`, `OK`, `FAULT`.
Dictionary changes require a new protocol version. Do not reinterpret SHB1.

The receiver validates the whole datagram before returning any records. Invalid
lengths, versions, tags, dictionary indices, UTF-8, embedded newline/CR/NUL and
expanded lines exceeding 1151 bytes are rejected. Each datagram is independent;
there is no cross-packet compression state. Existing sequence gap reporting
continues to work. Raw traffic logs store binary datagrams as hexadecimal with
`encoding: "hex"`; decoded telemetry retains the existing CSV/JSON formats.

## Queue and pacing

Records are encoded once when queued. The AIRDOS queue uses 4096 descriptors
and a 128 KiB byte ring, about 176 KiB total on a 32-bit target (plus small
bookkeeping); the system queue uses 32 descriptors and a 4 KiB byte ring.
Queue-pressure control now watches both descriptor occupancy and byte occupancy,
so unusually long AIRDOS records cannot silently fill the byte ring before the
automatic 9 -> 6 -> 3 -> 0 downlink reduction reacts.

AIRDOS UART lines may be up to 1023 bytes. The prefixed telemetry line may be up
to 1151 bytes and still fits as one record in the 1200-byte UDP payload. Records
are never silently truncated. A line that exceeds the configured bound is
rejected and counted by the existing overflow/drop diagnostics.

With a configured downlink limit, regular telemetry is paced in 50 ms send slots.
The target packet size is derived from the configured bitrate so a continuously
backlogged queue produces a much smoother stream. Housekeeping records are put
first, then remaining space in the same datagram is filled with AIRDOS records.
A rolling 200 ms guard tracks actual estimated wire bits and prevents regular
telemetry from exceeding the same configured average rate over that window.
Single records larger than one 50 ms target are kept whole; they are sent alone
and the rate/burst schedulers delay subsequent traffic. There is no record
fragmentation.

Immediate command replies remain immediate, but their wire cost is charged to the
same scheduler and recorded in the burst history, so regular telemetry waits
afterwards. A failed UDP send retains queued records and does not advance packet
sequence. Queued records retain their original timestamps.

## Validation (Cirrus recording, 20 May 2026)

Source: uploaded `Cirrus-Radiation-Data-main.zip`, `radiation.jsonl`.
23,769 source records. Roundtrip through the actual C++ encoder and Python decoder
preserves every AIRDOS telemetry line. Text line bytes including LF: 995,945;
length-prefixed binary record bytes: 610,270 (38.72% smaller, excluding packet
headers and network overhead). These counts include SHROOM time and sensor ID.

Replay duplicates each source event across nine sensor IDs at the same recorded
time, runs production queue/pacing code with mocked UDP and a 1 ms service tick,
and adds one PADS message/second at a configured 120 kbit/s. The replay checker
now also verifies at least 50 ms between regular packets and a rolling 200 ms
wire-rate ceiling. Because the pacing algorithm changed after the original
baseline run, the previous packet-count/delay figures are no longer treated as
current validation results. Re-run the script below before flight and record the
new figures together with the hardware replay.

Reproduce with Groundstation's `tools/verify_binary_replay.py`:

```sh
python tools/verify_binary_replay.py ../Flight_Software /path/to/radiation.jsonl
```

Additional host checks cover ring wraparound, 32-bit clock rollover, send failure,
numeric boundaries, raw fallback and malformed packets. Run `test/host/run.sh`
for the existing primary/secondary link tests. A real Teensy build and hardware
replay remain required before flight; the local firmware build dependency download
was blocked by the environment's network approval mechanism.
