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

    def test_plate_limit_message(self):
        parsed = parse_telemetry(
            "PLATE_LIMIT,5000,1,323.15,320.25,0,3,0"
        )
        self.assertTrue(parsed["enabled"])
        self.assertEqual(parsed["limit_k"], 323.15)
        self.assertEqual(parsed["temperature_k"], 320.25)
        self.assertFalse(parsed["tripped"])
        self.assertEqual(parsed["sensor"], 3)
        self.assertEqual(parsed["heater"], 0)

        # NaN temperature is meaningful: an enabled flight limiter then trips
        # fail-safe, while infinity or malformed configuration is invalid.
        nan_value = parse_telemetry(
            "PLATE_LIMIT,5000,1,323.15,nan,1,3,2"
        )
        self.assertTrue(nan_value["tripped"])

        invalid = (
            "PLATE_LIMIT,5000,2,323.15,320,0,3,0",
            "PLATE_LIMIT,5000,1,272.15,320,0,3,0",
            "PLATE_LIMIT,5000,1,374.15,320,0,3,0",
            "PLATE_LIMIT,5000,1,323.15,inf,0,3,0",
            "PLATE_LIMIT,5000,1,323.15,320,2,3,0",
            "PLATE_LIMIT,5000,1,323.15,320,0,0,0",
            "PLATE_LIMIT,5000,1,323.15,320,0,10,0",
            "PLATE_LIMIT,5000,1,323.15,320,0,3,5",
            "PLATE_LIMIT,5000,1,323.15,320,0,3",
        )
        for line in invalid:
            self.assertIsNone(parse_telemetry(line))

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

    def test_plate_limit_csv(self):
        with tempfile.TemporaryDirectory() as root:
            logger = GroundStationLogger(root)
            logger.log_telemetry(
                parse_telemetry(
                    "PLATE_LIMIT,5000,1,323.15,321.0,1,3,4"
                ),
                8
            )
            logger.close()
            with (logger.session_directory / "plate_limit.csv").open() as stream:
                rows = list(csv.DictReader(stream))

            self.assertEqual(rows[0]["enabled"], "1")
            self.assertEqual(float(rows[0]["limit_K"]), 323.15)
            self.assertEqual(rows[0]["tripped"], "1")
            self.assertEqual(rows[0]["sensor"], "3")
            self.assertEqual(rows[0]["heater"], "4")


if __name__ == "__main__":
    unittest.main()
