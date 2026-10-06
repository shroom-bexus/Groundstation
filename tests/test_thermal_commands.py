"""Thermal commands must fit the strict 1 kbit/s uplink burst budget."""
import unittest
from unittest.mock import Mock

from bandwidth import estimated_packet_bits
from ethernet_link import _numbered_command
from ui import GroundStationApp


class ThermalCommandTests(unittest.TestCase):
    def test_wire_commands_fit_at_largest_command_id(self):
        app = GroundStationApp()
        app.connected = True
        app._write_log = Mock()
        commands = {
            'fusion mean': 'CMD,SET_FUSION,MEAN',
            'fusion median': 'CMD,SET_FUSION,MEDIAN',
            'fusion min': 'CMD,SET_FUSION,MINIMUM',
            'fusion max': 'CMD,SET_FUSION,MAXIMUM',
            'thermal pid': 'CMD,SET_MODE,PID',
            'thermal bangbang': 'CMD,SET_MODE,BANG_BANG',
            'platelimit 50': 'CMD,SET_PLATE_LIMIT,323.15',
            'platelimit on': 'CMD,PLATE_LIMIT_ON',
            'platelimit off': 'CMD,PLATE_LIMIT_OFF',
        }
        for typed, expected in commands.items():
            with self.subTest(command=typed):
                app.on_input_submitted(Mock(value=typed))
                wire = app.command_queue.get_nowait()
                self.assertEqual(wire, expected)
                payload = (_numbered_command(65535, wire) + '\n').encode()
                self.assertLessEqual(estimated_packet_bits(len(payload)), 800)
