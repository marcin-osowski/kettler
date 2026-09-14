import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class DeviceTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            'tested_kettler', Path(__file__).parents[1] / 'kettler.py')
        module = importlib.util.module_from_spec(spec)
        # No real serial module or device constructor can run in these tests.
        fake_serial = types.SimpleNamespace(Serial=Mock(side_effect=AssertionError('hardware forbidden')))
        with patch.dict(sys.modules, {'serial': fake_serial}):
            spec.loader.exec_module(module)
        self.device = module.KettlerDevice.__new__(module.KettlerDevice)
        self.device._send_command = Mock()

    def test_time_encoding_and_boundary(self):
        for seconds, command in [(0, 'PT 0000'), (330, 'PT 0530'), (5999, 'PT 9959')]:
            with self.subTest(seconds=seconds):
                self.device.put_time(seconds)
                self.device._send_command.assert_called_with(command)

    def test_out_of_range_time_does_not_send(self):
        for seconds in [-1, 6000, 9959]:
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                self.device.put_time(seconds)
        self.device._send_command.assert_not_called()

    def test_partial_initialization_close(self):
        self.device.close()

    def test_close_is_idempotent(self):
        serial = Mock(is_open=True)
        serial.close.side_effect = lambda: setattr(serial, 'is_open', False)
        self.device.ser = serial
        self.device.close()
        self.device.close()
        serial.close.assert_called_once()
