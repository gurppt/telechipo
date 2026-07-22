import unittest
from unittest.mock import patch

from salsilink_control.core.adb_client import AdbClient, AdbError, parse_devices, scan_tcp_subnet, validate_endpoint
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

    @patch("salsilink_control.core.adb_client.socket.create_connection")
    def test_subnet_scan_uses_previous_ip_network(self, connect):
        def probe(endpoint, timeout):
            if endpoint[0] != "192.0.2.42":
                raise OSError("closed")
            return unittest.mock.MagicMock()
        connect.side_effect = probe
        network, hosts = scan_tcp_subnet("192.0.2.80", 5555)
        self.assertEqual(network, "192.0.2.0/24")
        self.assertEqual(hosts, ["192.0.2.42"])

    @patch("salsilink_control.core.adb_client.socket.create_connection")
    def test_subnet_scan_gives_saved_address_more_time(self, connect):
        connect.return_value = unittest.mock.MagicMock()
        _network, hosts = scan_tcp_subnet("192.0.2.80", 5555, timeout=0.2)
        self.assertIn("192.0.2.80", hosts)
        self.assertEqual(connect.call_args_list[0].args, (("192.0.2.80", 5555),))
        self.assertEqual(connect.call_args_list[0].kwargs, {"timeout": 1.5})


if __name__ == "__main__": unittest.main()
