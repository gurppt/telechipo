import unittest

from salsilink_control.core.adb_client import AdbError, parse_devices, validate_endpoint
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


if __name__ == "__main__": unittest.main()
