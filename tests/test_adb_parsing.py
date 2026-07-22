import unittest
from unittest.mock import patch

from salsilink_control.core.adb_client import AdbClient, AdbError, parse_devices, validate_endpoint
from salsilink_control.models import DeviceKind


class AdbParsingTests(unittest.TestCase):
    def test_all_states_and_transports(self):
        output = """List of devices attached
ABC123 device product:generic model:Example_Phone device:example
192.0.2.10:5555 device product:generic model:Example_Phone
second unauthorized usb:1-2
third offline usb:1-3
"""
        devices = parse_devices(output)
        self.assertEqual(len(devices), 4)
        self.assertEqual(devices[0].kind, DeviceKind.USB)
        self.assertEqual(devices[0].model, "Example Phone")
        self.assertEqual(devices[1].kind, DeviceKind.TCPIP)
        self.assertEqual([d.status for d in devices[2:]], ["unauthorized", "offline"])

    def test_endpoint_validation(self):
        self.assertEqual(validate_endpoint("192.0.2.10", 5555), "192.0.2.10:5555")
        with self.assertRaises(AdbError): validate_endpoint("hello; reboot", 5555)
        with self.assertRaises(AdbError): validate_endpoint("127.0.0.1", 99999)

    @patch("salsilink_control.core.adb_client.time.sleep")
    def test_connect_retries_while_adbd_restarts(self, sleep):
        client = AdbClient()
        outcomes = [AdbError("refused"), "192.0.2.1:5555"]
        def connect(_ip, _port):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        client.connect = connect  # type: ignore[method-assign]
        self.assertEqual(client.connect_with_retry("192.0.2.1", 5555), "192.0.2.1:5555")
        sleep.assert_called_once_with(1.0)


if __name__ == "__main__": unittest.main()
