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
        for seconds, command in [
                (0, 'PT 0000'), (330, 'PT 0530'),
                (6000, 'PT 10000'), (11999, 'PT 19959')]:
            with self.subTest(seconds=seconds):
                self.device._send_command.reset_mock()
                self.device.put_time(seconds)
                self.device._send_command.assert_called_with(command)

    def test_out_of_range_time_does_not_send(self):
        for seconds in [-1, -0.01, 11999.1, 12000, float('inf'), float('nan')]:
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                self.device.put_time(seconds)
        self.device._send_command.assert_not_called()

    def test_fractional_time_is_truncated_after_validation(self):
        self.device.put_time(60.9)
        self.device._send_command.assert_called_once_with('PT 0100')

    def test_distance_encoding_and_boundaries(self):
        for distance, command in [
                (0, 'PD 0'), (0.19, 'PD 1'), (499.8, 'PD 4998'),
                (499.9, 'PD 4999')]:
            with self.subTest(distance=distance):
                self.device._send_command.reset_mock()
                self.device.put_distance(distance)
                self.device._send_command.assert_called_once_with(command)

    def test_out_of_range_distance_does_not_send(self):
        for distance in [
                -1, -0.01, 499.99, 500, 999.9, float('-inf'), float('nan')]:
            with self.subTest(distance=distance), self.assertRaises(ValueError):
                self.device.put_distance(distance)
        self.device._send_command.assert_not_called()

    def test_watt_encoding_and_boundaries(self):
        for watts, command in [(25, 'PW 25'), (27.9, 'PW 27'), (400, 'PW 400')]:
            with self.subTest(watts=watts):
                self.device._send_command.reset_mock()
                self.device.put_watts(watts)
                self.device._send_command.assert_called_once_with(command)

    def test_out_of_range_watts_do_not_send(self):
        for watts in [
                -1, 0, 24, 24.99, 400.1, 401, 999, float('inf'), float('nan')]:
            with self.subTest(watts=watts), self.assertRaises(ValueError):
                self.device.put_watts(watts)
        self.device._send_command.assert_not_called()

    def test_energy_encoding_and_boundaries(self):
        for energy, command in [(0, 'PE 0'), (1.9, 'PE 1'), (9999, 'PE 9999')]:
            with self.subTest(energy=energy):
                self.device._send_command.reset_mock()
                self.device.put_energy(energy)
                self.device._send_command.assert_called_once_with(command)

    def test_out_of_range_energy_does_not_send(self):
        for energy in [-1, -0.01, 9999.1, 10000, float('-inf'), float('nan')]:
            with self.subTest(energy=energy), self.assertRaises(ValueError):
                self.device.put_energy(energy)
        self.device._send_command.assert_not_called()

    def test_status_parses_more_than_99_minutes(self):
        self.device._send_command.return_value = '0\t52\t95\t1\t100\t43\t199:59\t95'
        status = self.device.get_status()
        self.assertEqual(status.time_elapsed_sec, 11999)

    def test_enter_command_mode_sends_only_cm(self):
        self.device.enter_command_mode()
        self.device._send_command.assert_called_once_with('CM')

    def test_partial_initialization_close(self):
        self.device.close()

    def test_close_is_idempotent(self):
        serial = Mock(is_open=True)
        serial.close.side_effect = lambda: setattr(serial, 'is_open', False)
        self.device.ser = serial
        self.device.close()
        self.device.close()
        serial.close.assert_called_once()


class ConstructorTests(unittest.TestCase):
    def load_module(self, serial_factory):
        spec = importlib.util.spec_from_file_location(
            'constructor_tested_kettler', Path(__file__).parents[1] / 'kettler.py')
        module = importlib.util.module_from_spec(spec)
        fake_serial = types.SimpleNamespace(
            Serial=serial_factory, EIGHTBITS=8, PARITY_NONE='N', STOPBITS_ONE=1)
        with patch.dict(sys.modules, {'serial': fake_serial}):
            spec.loader.exec_module(module)
        return module

    def test_incomplete_startup_frames_fail_before_following_command(self):
        cases = [
            ([b'SJ10'], [b'ID\r\n']),
            ([b'', b'SJ10'], [b'ID\r\n', b'ID\r\n']),
            ([b'SJ10X3240\r\n', b'SJ10X UNI'], [b'ID\r\n', b'KI\r\n']),
        ]
        for replies, expected_writes in cases:
            with self.subTest(replies=replies):
                port = Mock(is_open=False, in_waiting=0)
                port.open.side_effect = lambda: setattr(port, 'is_open', True)
                port.close.side_effect = lambda: setattr(port, 'is_open', False)
                port.read_until.side_effect = replies
                module = self.load_module(Mock(return_value=port))
                with patch.object(module.time, 'sleep'):
                    with self.assertRaisesRegex(module.InvalidDeviceResponse, 'Incomplete'):
                        module.KettlerDevice('FAKE')
                self.assertEqual(port.write.call_args_list,
                                 [unittest.mock.call(x) for x in expected_writes])
                port.close.assert_called_once()

    def test_missing_ki_after_duplicate_id_fails_before_sn(self):
        port = Mock(is_open=False, in_waiting=0)
        port.open.side_effect = lambda: setattr(port, 'is_open', True)
        port.close.side_effect = lambda: setattr(port, 'is_open', False)
        port.read_until.side_effect = [b'', b'SJ10X3240\r\n', b'SJ10X3240\r\n', b'']
        module = self.load_module(Mock(return_value=port))
        with patch.object(module.time, 'sleep'):
            with self.assertRaisesRegex(module.InvalidDeviceResponse, 'KI response'):
                module.KettlerDevice('FAKE')
        self.assertEqual(port.write.call_args_list, [
            unittest.mock.call(b'ID\r\n'), unittest.mock.call(b'ID\r\n'),
            unittest.mock.call(b'KI\r\n')])
        port.close.assert_called_once()

    def test_constructor_closes_port_on_interrupt(self):
        serial_port = Mock(is_open=False, in_waiting=0)
        serial_port.open.side_effect = lambda: setattr(serial_port, 'is_open', True)
        serial_port.close.side_effect = lambda: setattr(serial_port, 'is_open', False)
        serial_port.write.side_effect = KeyboardInterrupt()
        module = self.load_module(Mock(return_value=serial_port))

        with self.assertRaises(KeyboardInterrupt):
            module.KettlerDevice('FAKE')

        serial_port.close.assert_called_once()

    def test_constructor_closes_port_when_identity_query_fails(self):
        serial_port = Mock(is_open=False, in_waiting=0)
        serial_port.open.side_effect = lambda: setattr(serial_port, 'is_open', True)
        serial_port.close.side_effect = lambda: setattr(serial_port, 'is_open', False)
        serial_port.write.side_effect = RuntimeError('query failed')
        module = self.load_module(Mock(return_value=serial_port))

        with self.assertRaisesRegex(RuntimeError, 'query failed'):
            module.KettlerDevice('FAKE')

        serial_port.close.assert_called_once()

    def test_constructor_closes_port_when_device_id_is_empty(self):
        serial_port = Mock(is_open=False, in_waiting=0)
        serial_port.open.side_effect = lambda: setattr(serial_port, 'is_open', True)
        serial_port.close.side_effect = lambda: setattr(serial_port, 'is_open', False)
        serial_port.read_until.return_value = b'\r\n'
        module = self.load_module(Mock(return_value=serial_port))

        with patch.object(module.time, 'sleep') as sleep:
            with self.assertRaisesRegex(module.InvalidDeviceResponse, 'Could not get device ID'):
                module.KettlerDevice('FAKE')

        sleep.assert_called_once_with(5.0)
        self.assertEqual(serial_port.write.call_args_list, [
            unittest.mock.call(b'ID\r\n'), unittest.mock.call(b'ID\r\n')])
        serial_port.close.assert_called_once()

    def test_empty_first_id_is_retried_once_after_five_seconds(self):
        serial_port = Mock(is_open=False, in_waiting=0)
        serial_port.open.side_effect = lambda: setattr(serial_port, 'is_open', True)
        serial_port.close.side_effect = lambda: setattr(serial_port, 'is_open', False)
        serial_port.read_until.side_effect = [
            b'', b'SJ10X3240\r\n', b'SJ10X UNIX E\r\n',
            b'SERIAL\r\n', b'3240\r\n']
        module = self.load_module(Mock(return_value=serial_port))

        with patch.object(module.time, 'sleep') as sleep:
            device = module.KettlerDevice('FAKE')

        sleep.assert_called_once_with(5.0)
        self.assertEqual(device.device_id, 'SJ10X3240')
        self.assertEqual(serial_port.write.call_args_list[:3], [
            unittest.mock.call(b'ID\r\n'), unittest.mock.call(b'ID\r\n'),
            unittest.mock.call(b'KI\r\n')])

    def test_late_duplicate_id_cannot_become_device_model(self):
        serial_port = Mock(is_open=False, in_waiting=0)
        serial_port.open.side_effect = lambda: setattr(serial_port, 'is_open', True)
        serial_port.close.side_effect = lambda: setattr(serial_port, 'is_open', False)
        serial_port.read_until.side_effect = [
            b'', b'SJ10X3240\r\n', b'SJ10X3240\r\n',
            b'SJ10X UNIX E\r\n', b'SERIAL\r\n', b'3240\r\n']
        module = self.load_module(Mock(return_value=serial_port))

        with patch.object(module.time, 'sleep'):
            device = module.KettlerDevice('FAKE')

        self.assertEqual(device.device_model, 'SJ10X UNIX E')
        self.assertEqual(serial_port.write.call_args_list, [
            unittest.mock.call(b'ID\r\n'), unittest.mock.call(b'ID\r\n'),
            unittest.mock.call(b'KI\r\n'), unittest.mock.call(b'SN\r\n'),
            unittest.mock.call(b'VE\r\n')])

    def test_complete_delayed_id_is_consumed_without_duplicate_write(self):
        serial_port = Mock(is_open=False, in_waiting=12)
        serial_port.open.side_effect = lambda: setattr(serial_port, 'is_open', True)
        serial_port.close.side_effect = lambda: setattr(serial_port, 'is_open', False)
        serial_port.read_until.side_effect = [
            b'', b'SJ10X3240\r\n', b'SJ10X UNIX E\r\n',
            b'SERIAL\r\n', b'3240\r\n']
        module = self.load_module(Mock(return_value=serial_port))

        with patch.object(module.time, 'sleep') as sleep:
            device = module.KettlerDevice('FAKE')

        sleep.assert_called_once_with(5.0)
        self.assertEqual(device.device_model, 'SJ10X UNIX E')
        self.assertEqual(serial_port.write.call_args_list[:2], [
            unittest.mock.call(b'ID\r\n'), unittest.mock.call(b'KI\r\n')])
        serial_port.reset_input_buffer.assert_not_called()

    def test_partial_delayed_id_fails_without_another_write(self):
        serial_port = Mock(is_open=False, in_waiting=5)
        serial_port.open.side_effect = lambda: setattr(serial_port, 'is_open', True)
        serial_port.close.side_effect = lambda: setattr(serial_port, 'is_open', False)
        serial_port.read_until.side_effect = [b'', b'SJ10']
        module = self.load_module(Mock(return_value=serial_port))

        with patch.object(module.time, 'sleep'):
            with self.assertRaisesRegex(module.InvalidDeviceResponse, 'Incomplete delayed'):
                module.KettlerDevice('FAKE')

        self.assertEqual(serial_port.write.call_args_list, [
            unittest.mock.call(b'ID\r\n')])
        serial_port.close.assert_called_once_with()

    def test_constructor_keeps_startup_error_when_close_also_fails(self):
        serial_port = Mock(is_open=False, in_waiting=0)
        serial_port.open.side_effect = lambda: setattr(serial_port, 'is_open', True)
        serial_port.write.side_effect = RuntimeError('query failed')
        serial_port.close.side_effect = RuntimeError('close failed')
        module = self.load_module(Mock(return_value=serial_port))

        with self.assertRaisesRegex(RuntimeError, 'query failed'):
            module.KettlerDevice('FAKE')

        serial_port.close.assert_called_once()

    def test_constructor_closes_port_when_open_partially_fails(self):
        serial_port = Mock(is_open=False, in_waiting=0)
        def fail_open():
            serial_port.is_open = True
            raise RuntimeError('open failed')
        serial_port.open.side_effect = fail_open
        serial_port.close.side_effect = lambda: setattr(serial_port, 'is_open', False)
        module = self.load_module(Mock(return_value=serial_port))

        with self.assertRaisesRegex(RuntimeError, 'open failed'):
            module.KettlerDevice('FAKE')

        serial_port.close.assert_called_once()

    def test_destructor_suppresses_close_error(self):
        module = self.load_module(Mock(side_effect=AssertionError('unused')))
        device = module.KettlerDevice.__new__(module.KettlerDevice)
        device.close = Mock(side_effect=RuntimeError('close failed'))

        device.__del__()

        device.close.assert_called_once()
