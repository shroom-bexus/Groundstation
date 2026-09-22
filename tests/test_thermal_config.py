"""Run with python -m unittest discover -s tests from Groundstation."""
import csv
import tempfile
import unittest
from telemetry import parse_telemetry
from data_logger import GroundStationLogger


class ThermalConfigTests(unittest.TestCase):
    def test_modes_and_invalid_settings(self):
        for mode in ("PID", "BANG_BANG"):
            parsed = parse_telemetry(
                f"THERMAL_CONFIG,5000,{mode},0.5,30,MEDIAN"
            )
            self.assertEqual(parsed["mode"], mode)
            self.assertEqual(parsed["hysteresis_k"], 0.5)
            self.assertEqual(parsed["fusion_mode"], "MEDIAN")

        # Legacy firmware without fusion field is still accepted.
        legacy = parse_telemetry("THERMAL_CONFIG,5000,PID,0.5,30")
        self.assertIsNone(legacy["fusion_mode"])

        for fusion in ("MEAN", "MEDIAN", "MINIMUM", "MAXIMUM"):
            parsed = parse_telemetry(
                f"THERMAL_CONFIG,5000,PID,0.5,30,{fusion}"
            )
            self.assertEqual(parsed["fusion_mode"], fusion)

        for suffix in ("PID,0,30", "PID,nan,30", "PID,0.5,inf",
                       "PID,11,30", "BAD,0.5,30", "PID,0.5", "PID,0.5,101",
                       "PID,0.5,30,BAD"):
            self.assertIsNone(parse_telemetry(f"THERMAL_CONFIG,5000,{suffix}"))

    def test_existing_messages(self):
        self.assertEqual(parse_telemetry("THERMAL,1000,1,298.15,297,30")["output_percent"], 30)
        self.assertEqual(parse_telemetry("PID,1000,2,0,0")["kp"], 2)

    def test_configuration_csv(self):
        with tempfile.TemporaryDirectory() as root:
            logger = GroundStationLogger(root)
            logger.log_telemetry(
                parse_telemetry("THERMAL_CONFIG,5000,BANG_BANG,0.5,30,MAXIMUM"),
                7
            )
            logger.close()
            with (logger.session_directory / "thermal_config.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["mode"], "BANG_BANG")
            self.assertEqual(float(rows[0]["bang_bang_power_percent"]), 30)
            self.assertEqual(rows[0]["fusion_mode"], "MAXIMUM")


if __name__ == "__main__":
    unittest.main()
