"""Regression coverage for Teensy internal CPU temperature telemetry."""

import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from data_logger import GroundStationLogger
from telemetry import parse_telemetry


class CpuTemperatureTests(unittest.TestCase):
    def test_parser_accepts_both_boards(self):
        for source in ("PRIMARY", "SECONDARY"):
            parsed = parse_telemetry(f"CPU_TEMP,1234,{source},42.75")
            self.assertEqual(parsed, {
                "type": "CPU_TEMP",
                "time_ms": 1234,
                "source": source,
                "temperature_c": 42.75,
            })

    def test_parser_rejects_corrupt_samples(self):
        samples = (
            "CPU_TEMP,1,OTHER,33.5",
            "CPU_TEMP,1,PRIMARY,nan",
            "CPU_TEMP,1,SECONDARY,inf",
            "CPU_TEMP,1,PRIMARY,151",
            "CPU_TEMP,1,PRIMARY,-56",
            "CPU_TEMP,-1,PRIMARY,30",
            "CPU_TEMP,4294967296,PRIMARY,30",
            "CPU_TEMP,1,PRIMARY,30,EXTRA",
            "CPU_TEMP,1,PRIMARY,",
        )
        for line in samples:
            with self.subTest(line=line):
                self.assertIsNone(parse_telemetry(line))

    def test_cpu_csv_and_jsonl(self):
        with TemporaryDirectory() as root:
            logger = GroundStationLogger(root)
            logger.log_telemetry(parse_telemetry("CPU_TEMP,100,PRIMARY,41.25"), 7)
            logger.log_telemetry(parse_telemetry("CPU_TEMP,110,SECONDARY,39.50"), 8)
            directory = Path(logger.session_directory)
            logger.close()

            with (directory / "cpu_temperature.csv").open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual([r["source"] for r in rows], ["PRIMARY", "SECONDARY"])
            self.assertEqual([r["temperature_C"] for r in rows], ["41.25", "39.5"])
            self.assertEqual([r["sequence"] for r in rows], ["7", "8"])
            self.assertEqual([r["time_ms"] for r in rows], ["100", "110"])
            self.assertEqual(len((directory / "telemetry.jsonl").read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
