"""Persistent recording of SHROOM Ground Station communication and telemetry."""

import atexit
import csv
import json
import threading
from datetime import datetime, timezone
from pathlib import Path


DATA_DIRECTORY = Path("data")


def _utc_timestamp():
    """Return an ISO-8601 UTC timestamp with millisecond resolution."""

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _unique_session_directory(root):
    """Create a unique UTC-named directory for one Ground Station run."""

    base_name = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
    directory = root / base_name
    suffix = 2

    while directory.exists():
        directory = root / f"{base_name}_{suffix}"
        suffix += 1

    directory.mkdir(parents=True)
    return directory


class GroundStationLogger:
    """Record raw UDP traffic and parsed telemetry for one GS session."""

    def __init__(self, root_directory=DATA_DIRECTORY):
        self._lock = threading.Lock()
        self._closed = False
        self._csv_files = {}
        self._csv_writers = {}

        self.session_directory = _unique_session_directory(
            Path(root_directory)
        )

        self._traffic_file = (
            self.session_directory / "traffic.jsonl"
        ).open("a", encoding="utf-8", buffering=1)

        self._telemetry_file = (
            self.session_directory / "telemetry.jsonl"
        ).open("a", encoding="utf-8", buffering=1)

        atexit.register(self.close)

    def _write_json_line(self, file, record):
        json.dump(record, file, ensure_ascii=False, separators=(",", ":"))
        file.write("\n")
        file.flush()

    def _csv_writer(self, filename, header):
        """Open a CSV file lazily and write its header once."""

        writer = self._csv_writers.get(filename)
        if writer is not None:
            return writer

        file = (self.session_directory / filename).open(
            "a",
            encoding="utf-8",
            newline="",
            buffering=1
        )
        writer = csv.writer(file)

        if file.tell() == 0:
            writer.writerow(header)
            file.flush()

        self._csv_files[filename] = file
        self._csv_writers[filename] = writer
        return writer

    def _write_csv(self, filename, header, row):
        writer = self._csv_writer(filename, header)
        writer.writerow(row)
        self._csv_files[filename].flush()

    def log_traffic(self, direction, payload):
        """Record one complete UDP application payload."""

        if self._closed:
            return

        if isinstance(payload, bytes):
            byte_count = len(payload)
            text = payload.decode("utf-8", errors="replace")
        else:
            text = str(payload)
            byte_count = len(text.encode("utf-8"))

        record = {
            "utc": _utc_timestamp(),
            "direction": direction,
            "bytes": byte_count,
            "data": text,
        }

        with self._lock:
            self._write_json_line(self._traffic_file, record)

    def log_command(
        self,
        event,
        command_id,
        detail,
        attempt="",
        internal=""
    ):
        """Record a command transmission, response, or timeout."""

        if self._closed:
            return

        if isinstance(internal, bool):
            internal = int(internal)

        with self._lock:
            self._write_csv(
                "commands.csv",
                (
                    "utc",
                    "event",
                    "command_id",
                    "attempt",
                    "internal",
                    "detail",
                ),
                (
                    _utc_timestamp(),
                    event,
                    command_id,
                    attempt,
                    internal,
                    detail,
                )
            )

    def log_telemetry(self, telemetry, sequence):
        """Record parsed telemetry in JSONL and type-specific CSV files."""

        if self._closed:
            return

        received_utc = _utc_timestamp()
        telemetry_type = telemetry.get("type")

        json_record = {
            "received_utc": received_utc,
            "sequence": sequence,
            **telemetry,
        }

        with self._lock:
            self._write_json_line(self._telemetry_file, json_record)

            if telemetry_type == "PADS":
                self._write_csv(
                    "wsen_pads.csv",
                    (
                        "received_utc",
                        "sequence",
                        "time_ms",
                        "temperature_K",
                        "pressure_Pa",
                    ),
                    (
                        received_utc,
                        sequence,
                        telemetry["time_ms"],
                        telemetry["temperature_k"],
                        telemetry["pressure_pa"],
                    )
                )

            elif telemetry_type == "HIDS":
                self._write_csv(
                    "wsen_hids.csv",
                    (
                        "received_utc",
                        "sequence",
                        "time_ms",
                        "temperature_K",
                        "humidity_percent",
                    ),
                    (
                        received_utc,
                        sequence,
                        telemetry["time_ms"],
                        telemetry["temperature_k"],
                        telemetry["humidity_percent"],
                    )
                )

            elif telemetry_type == "THERMAL":
                self._write_csv(
                    "thermal.csv",
                    (
                        "received_utc",
                        "sequence",
                        "time_ms",
                        "controller_enabled",
                        "target_K",
                        "temperature_K",
                        "output_percent",
                    ),
                    (
                        received_utc,
                        sequence,
                        telemetry["time_ms"],
                        int(telemetry["controller_enabled"]),
                        telemetry["target_k"],
                        telemetry["temperature_k"],
                        telemetry["output_percent"],
                    )
                )

            elif telemetry_type == "PID":
                self._write_csv(
                    "pid.csv",
                    (
                        "received_utc", "sequence", "time_ms", "kp", "ki", "kd"
                    ),
                    (
                        received_utc,
                        sequence,
                        telemetry["time_ms"],
                        telemetry["kp"],
                        telemetry["ki"],
                        telemetry["kd"],
                    )
                )

            elif telemetry_type == "HEATERS":
                self._write_csv(
                    "heaters.csv",
                    (
                        "received_utc",
                        "sequence",
                        "time_ms",
                        "heater_1_percent",
                        "heater_2_percent",
                        "heater_3_percent",
                        "heater_4_percent",
                    ),
                    (
                        received_utc,
                        sequence,
                        telemetry["time_ms"],
                        telemetry["heater_1"],
                        telemetry["heater_2"],
                        telemetry["heater_3"],
                        telemetry["heater_4"],
                    )
                )

            elif telemetry_type == "HEALTH":
                self._write_csv(
                    "health.csv",
                    (
                        "received_utc",
                        "sequence",
                        "time_ms",
                        "subsystem",
                        "sensor",
                        "state",
                        "fault",
                        "error_count",
                        "last_message_age_ms",
                        "overflow_count",
                    ),
                    (
                        received_utc,
                        sequence,
                        telemetry["time_ms"],
                        telemetry["subsystem"],
                        telemetry.get("sensor", ""),
                        telemetry["state"],
                        telemetry.get("fault", ""),
                        telemetry.get("error_count", ""),
                        telemetry.get("last_message_age_ms", ""),
                        telemetry.get("overflow_count", ""),
                    )
                )

            elif telemetry_type == "LOG":
                self._write_csv(
                    "flight_log.csv",
                    ("received_utc", "sequence", "level", "message"),
                    (
                        received_utc,
                        sequence,
                        telemetry["level"],
                        telemetry["message"],
                    )
                )

    def close(self):
        """Flush and close all session files."""

        with self._lock:
            if self._closed:
                return

            self._closed = True

            self._traffic_file.flush()
            self._traffic_file.close()
            self._telemetry_file.flush()
            self._telemetry_file.close()

            for file in self._csv_files.values():
                file.flush()
                file.close()
