"""Unit conversion and storage health regression tests."""
import csv
import tempfile
import unittest
from unittest.mock import Mock

from display import celsius, target_kelvin, STORAGE_LABELS, storage_notice
from telemetry import parse_telemetry
from data_logger import GroundStationLogger
from dashboard import DashboardState
from bandwidth import BandwidthSettings
from ui import GroundStationApp


class DisplayStorageTests(unittest.TestCase):
    def test_temperature_conversion_and_invalid_targets(self):
        self.assertAlmostEqual(celsius(273.15), 0)
        self.assertAlmostEqual(celsius(253.15), -20)
        self.assertAlmostEqual(target_kelvin("25"), 298.15)
        for value in ("nan", "inf", "-inf", "-300", "bad"):
            with self.assertRaises(ValueError):
                target_kelvin(value)

    def test_all_cards_parse_and_log_independently(self):
        with tempfile.TemporaryDirectory() as root:
            logger = GroundStationLogger(root)
            for index, name in enumerate(STORAGE_LABELS):
                parsed = parse_telemetry(f"HEALTH,1000,{name},FAULT,{index}")
                self.assertEqual(parsed["error_count"], index)
                logger.log_telemetry(parsed, index)
            logger.close()
            with (logger.session_directory / "health.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r["subsystem"] for r in rows], list(STORAGE_LABELS))
        self.assertIsNotNone(parse_telemetry("HEALTH,1,SD,OK,0"))
        self.assertIsNone(parse_telemetry("HEALTH,1,SD_BACKUP,FAULT,bad"))

    def test_faults_stale_recovery_and_deduplication(self):
        ok = parse_telemetry("HEALTH,1,SD_SECONDARY_BACKUP,OK,0")
        fault = parse_telemetry("HEALTH,2,SD_SECONDARY_BACKUP,FAULT,1")
        stale = dict(fault, state="STALE")
        self.assertIsNone(storage_notice(None, ok))
        self.assertIn("[ERROR] Secondary backup XTSD", storage_notice(None, fault))
        self.assertIsNone(storage_notice(fault, fault))
        self.assertIn("STALE", storage_notice(fault, stale))
        self.assertIn("[INFO]", storage_notice(stale, ok))
        self.assertIn("errors: 2", storage_notice(fault, dict(fault, error_count=2)))

    def test_dashboard_keeps_wire_values_and_reports_storage_errors(self):
        state = DashboardState()
        state.add_telemetry(parse_telemetry("THERMAL,1000,1,298.15,273.15,0"))
        fault = parse_telemetry("HEALTH,1000,SD_SECONDARY_BACKUP,FAULT,3")
        state.add_telemetry(fault)
        state.add_telemetry(fault)
        snapshot = state.snapshot(BandwidthSettings())
        self.assertEqual(snapshot["latest"]["thermal"]["temperature_k"], 273.15)
        self.assertEqual(snapshot["series"]["thermal_temperature"][0][1], 273.15)
        self.assertEqual(snapshot["health"]["SD_SECONDARY_BACKUP"]["error_count"], 3)
        self.assertEqual(len(snapshot["logs"]), 1)
        self.assertIn("[ERROR]", snapshot["logs"][0]["message"])

    def test_target_command_converts_to_wire_kelvin(self):
        app = GroundStationApp()
        app._write_log = Mock()
        app.connected = True
        app.on_input_submitted(Mock(value="target 25"))
        self.assertEqual(app.command_queue.get_nowait(), "CMD,SET_TARGET,298.15")
        app.on_input_submitted(Mock(value="target nan"))
        self.assertTrue(app.command_queue.empty())

    def test_ui_temperature_and_storage_messages(self):
        app = GroundStationApp()
        app.connected = True
        widgets = {}
        app.query_one = lambda key, kind: widgets.setdefault(key, Mock())
        app._write_log = Mock()
        app._handle_telemetry(parse_telemetry("THERMAL,1,1,298.15,273.15,0"))
        widgets["#thermal_temperature"].update.assert_called_with("Temperature: 0.000 °C")
        widgets["#thermal_target"].update.assert_called_with("Target: 25.00 °C")
        fault = parse_telemetry("HEALTH,2,SD_BACKUP,FAULT,1")
        app._handle_telemetry(fault)
        app._handle_telemetry(fault)
        app._write_log.assert_called_once()
        self.assertIn("Primary backup XTSD: FAULT", widgets["#health_status"].update.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
