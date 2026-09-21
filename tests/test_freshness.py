import unittest
from unittest.mock import Mock, patch

from bandwidth import BandwidthSettings
from dashboard import DashboardState
from display import storage_notice
from freshness import Freshness
from telemetry import parse_telemetry
from ui import GroundStationApp


class FreshnessTests(unittest.TestCase):
    def test_each_channel_expires_independently(self):
        tracker = Freshness()
        with patch('freshness.time.monotonic', return_value=100):
            tracker.observe(parse_telemetry('MAX31865,1,1,290'))
            tracker.observe(parse_telemetry('PADS,1,291,100000'))
            tracker.observe(parse_telemetry('HIDS,1,292,40'))
            tracker.observe(parse_telemetry('THERMAL,1,1,293,290,10'))
        with patch('freshness.time.monotonic', return_value=110):
            tracker.observe(parse_telemetry('MAX31865,2,2,295'))
            for key in ('MAX31865_1', 'PADS', 'HIDS', 'THERMAL'):
                self.assertEqual(tracker.temperature(key, True)['state'], 'STALE')
            self.assertEqual(tracker.temperature('MAX31865_2', True)['state'], 'OK')
            self.assertEqual(tracker.temperature('MAX31865_3', True)['state'], 'WAITING')
            tracker.observe(parse_telemetry('HEALTH,3,MAX31865,1,OK,0,0'))
            self.assertEqual(tracker.temperature('MAX31865_1', True)['state'], 'STALE')

    def test_fault_nonfinite_and_reconnect(self):
        tracker = Freshness()
        tracker.observe(parse_telemetry('MAX31865,1,1,290'))
        tracker.observe(parse_telemetry('HEALTH,2,MAX31865,1,FAULT,128,1'))
        self.assertIn('INVALID', tracker.label('MAX31865_1', True))
        tracker.observe(parse_telemetry('THERMAL,2,1,293,nan,0'))
        self.assertEqual(tracker.temperature('THERMAL', True)['state'], 'INVALID')
        self.assertIsNone(tracker.temperature('THERMAL', True)['temperature_k'])
        tracker.observe(parse_telemetry('HEALTH,3,MAX31865,1,OK,0,1'))
        tracker.invalidate()
        self.assertEqual(tracker.temperature('MAX31865_1', True)['state'], 'STALE')
        tracker.observe(parse_telemetry('MAX31865,4,1,291'))
        self.assertEqual(tracker.temperature('MAX31865_1', True)['state'], 'OK')
        self.assertEqual(tracker.temperature('MAX31865_1', False)['state'], 'STALE')

    def test_secondary_fault_logs_once_and_recovers(self):
        fault = parse_telemetry('HEALTH,15000,SECONDARY,FAULT,0')
        ok = parse_telemetry('HEALTH,20000,SECONDARY,OK,0')
        self.assertIn('[ERROR] Secondary Teensy link: FAULT', storage_notice(None, fault))
        self.assertIsNone(storage_notice(fault, fault))
        self.assertIn('[INFO]', storage_notice(fault, ok))
        tracker = Freshness()
        with patch('freshness.time.monotonic', return_value=100):
            tracker.observe(ok)
            self.assertEqual(tracker.secondary_state(True), 'OK')
            self.assertIn('STALE', tracker.secondary_state(False))
        with patch('freshness.time.monotonic', return_value=115):
            self.assertIn('STALE', tracker.secondary_state(True))

    def test_terminal_timer_and_dashboard_snapshot(self):
        app = GroundStationApp()
        app.connected = True
        widgets = {}
        app.query_one = lambda key, *args: widgets.setdefault(key, Mock())
        app._write_log = Mock()
        state = DashboardState()
        state.set_connection(True)
        sample = parse_telemetry('MAX31865,1,1,290')
        with patch('freshness.time.monotonic', return_value=100):
            app._handle_telemetry(sample)
            state.add_telemetry(sample)
        with patch('freshness.time.monotonic', return_value=111):
            app._update_live_validity()
            self.assertIn('STALE', widgets['#max31865_temperatures'].update.call_args.args[0])
            snap = state.snapshot(BandwidthSettings())
            self.assertEqual(snap['temperatures']['MAX31865_1']['state'], 'STALE')
            self.assertEqual(snap['latest']['max31865']['1']['temperature_k'], 290)
            # An explicit fault must be both permanent and logged.
            fault = parse_telemetry('HEALTH,15000,SECONDARY,FAULT,0')
            app._handle_telemetry(fault)
            self.assertIn('Secondary Teensy link: FAULT', widgets['#health_status'].update.call_args.args[0])
            app._write_log.assert_called_once()
