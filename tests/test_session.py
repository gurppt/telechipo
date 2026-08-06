import tempfile
import unittest
from pathlib import Path

from salsilink_control.core.session_manager import SleepTimeoutGuard, StateMachine
from salsilink_control.models import AdbDevice, DeviceKind, SessionState


class FakeAdb:
    def __init__(self): self.value = "30000"; self.get_calls = 0
    def get_setting(self, serial, key): self.get_calls += 1; return self.value
    def put_setting(self, serial, key, value): self.value = value
    def device_identity(self, serial): return "phone-1"


class SessionTests(unittest.TestCase):
    def test_transitions(self):
        machine = StateMachine(); machine.transition(SessionState.DISCOVERING); machine.transition(SessionState.USB_READY)
        self.assertEqual(machine.state, SessionState.USB_READY)
        with self.assertRaises(ValueError): machine.transition(SessionState.STOPPING)

    def test_timeout_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = FakeAdb(); guard = SleepTimeoutGuard(adb, Path(directory) / "recovery.json")
            guard.apply("serial"); self.assertEqual(adb.value, "86400000")
            self.assertTrue(guard.restore()); self.assertEqual(adb.value, "30000")
            self.assertFalse(guard.path.exists())

    def test_reapplying_guard_preserves_original_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = FakeAdb(); guard = SleepTimeoutGuard(adb, Path(directory) / "recovery.json")
            guard.apply("serial"); guard.apply("serial")
            self.assertEqual(adb.get_calls, 1)
            self.assertTrue(guard.restore()); self.assertEqual(adb.value, "30000")

    def test_restore_uses_matching_wifi_transport_when_usb_is_gone(self):
        class SwitchingAdb(FakeAdb):
            def put_setting(self, serial, key, value):
                if serial == "usb-serial":
                    raise RuntimeError("device not found")
                self.value = value
            def devices(self):
                return [AdbDevice("192.0.2.8:5555", "device", DeviceKind.TCPIP)]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recovery.json"
            path.write_text('{"serial":"usb-serial","identity":"phone-1","value":"30000"}')
            adb = SwitchingAdb(); guard = SleepTimeoutGuard(adb, path)
            self.assertTrue(guard.restore())
            self.assertEqual(adb.value, "30000")
            self.assertFalse(path.exists())


if __name__ == "__main__": unittest.main()
