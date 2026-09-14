import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class ReplTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            'tested_repl', Path(__file__).parents[1] / 'repl.py')
        self.repl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.repl)
        self.device = Mock()
        self.device._send_command_multi_line_resp.return_value = 'ACK\r\n'
        self.error = type('CommunicationError', (Exception,), {})
        self.factory = Mock(return_value=self.device)
        self.modules = {
            'config': types.SimpleNamespace(KETTLER_DEVICE_SERIAL='FAKE'),
            'serial': types.SimpleNamespace(SerialException=self.error),
            'kettler': types.SimpleNamespace(
                KettlerDevice=self.factory, SerialPortOpenError=self.error,
                InvalidDeviceResponse=self.error, ErrorDeviceResponse=self.error),
        }

    def run_repl(self, inputs):
        output = io.StringIO()
        with patch.dict(sys.modules, self.modules), contextlib.redirect_stdout(output):
            with patch('builtins.input', side_effect=inputs):
                result = self.repl.main()
        return result, output.getvalue()

    def test_warning_precedes_open_and_arbitrary_commands_survive(self):
        def opened(port):
            self.assertIn('WARNING', sys.stdout.getvalue())
            self.assertEqual(port, 'FAKE')
            return self.device
        self.factory.side_effect = opened
        result, output = self.run_repl(['', 'RF', 'PW 123', EOFError()])
        self.assertEqual(result, 0)
        self.device.reset.assert_called_once()
        self.assertEqual(self.device._send_command_multi_line_resp.call_count, 2)
        self.device._send_command_multi_line_resp.assert_called_with('PW 123', check_noerror=False)
        self.assertIn("'ACK\\r\\n'", output)
        self.device.close.assert_called_once()

    def test_interrupt_closes(self):
        self.assertEqual(self.run_repl([KeyboardInterrupt()])[0], 0)
        self.device.close.assert_called_once()

    def test_transport_error_is_not_retried(self):
        self.device._send_command_multi_line_resp.side_effect = self.error('broken')
        result, output = self.run_repl(['RS'])
        self.assertEqual(result, 1)
        self.assertIn('outcome may be unknown', output)
        self.device._send_command_multi_line_resp.assert_called_once()
        self.device.close.assert_called_once()

    def test_open_failure(self):
        self.factory.side_effect = self.error('busy')
        self.assertEqual(self.run_repl([])[0], 1)
        self.device.reset.assert_not_called()

    def test_reset_failure_closes(self):
        self.device.reset.side_effect = self.error('lost response')
        self.assertEqual(self.run_repl([])[0], 1)
        self.device.close.assert_called_once()
