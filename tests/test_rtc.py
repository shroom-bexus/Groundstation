import unittest
from unittest.mock import Mock, patch

from bandwidth import BandwidthSettings
from dashboard import DashboardState
from telemetry import parse_telemetry
from ui import GroundStationApp


class RTCTests(unittest.TestCase):
    def test_wire_validation(self):
        sample = parse_telemetry('RTC,100,1,2026-09-21T12:34:56Z')
        self.assertEqual(sample['timestamp_utc'], '2026-09-21T12:34:56Z')
        self.assertFalse(parse_telemetry('RTC,100,0,')['valid'])
        for line in ('RTC,1,2,', 'RTC,-1,0,', 'RTC,4294967296,0,',
                     'RTC,1,1,2026-02-30T12:00:00Z', 'RTC,1,1,',
                     'RTC,1,1,2026-09-21T12:34:56+02:00', 'RTC,1,0,bad'):
            self.assertIsNone(parse_telemetry(line), line)

    def test_dashboard_reception_age_and_invalid_replacement(self):
        state = DashboardState()
        self.assertIsNone(state.snapshot(BandwidthSettings())['rtc_age_s'])
        with patch('dashboard.time.monotonic', return_value=100):
            state.add_telemetry(parse_telemetry('RTC,1,1,2026-09-21T12:34:56Z'))
        with patch('dashboard.time.monotonic', return_value=120):
            snapshot = state.snapshot(BandwidthSettings())
        self.assertEqual(snapshot['rtc_age_s'], 20)
        self.assertEqual(snapshot['latest']['rtc']['timestamp_utc'], '2026-09-21T12:34:56Z')
        state.add_telemetry(parse_telemetry('RTC,2,0,'))
        self.assertIsNone(state.snapshot(BandwidthSettings())['latest']['rtc']['timestamp_utc'])

    def test_terminal_stale_disconnect_and_recovery(self):
        app = GroundStationApp()
        widget = Mock()
        app.query_one = lambda *args: widget
        app.connected = True
        with patch('ui.time.monotonic', return_value=100):
            app._handle_telemetry(parse_telemetry('RTC,1,1,2026-09-21T12:34:56Z'))
        self.assertIn('2026-09-21T12:34:56Z', widget.update.call_args.args[0])
        with patch('ui.time.monotonic', return_value=116):
            app._update_rtc_panel()
        self.assertIn('STALE', widget.update.call_args.args[0])
        with patch('ui.time.monotonic', return_value=117):
            app._handle_telemetry(parse_telemetry('RTC,2,0,'))
            self.assertIn('INVALID', widget.update.call_args.args[0])
            self.assertNotIn('STALE', widget.update.call_args.args[0])
            app.connected = False
            app._update_rtc_panel()
            self.assertIn('STALE', widget.update.call_args.args[0])
