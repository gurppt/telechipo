import tempfile
import unittest
from pathlib import Path

from salsilink_control.core.session_manager import SleepTimeoutGuard, StateMachine
from salsilink_control.models import SessionState


class FakeAdb:
    def __init__(self): self.value = "30000"; self.get_calls = 0
    def get_setting(self, serial, key): self.get_calls += 1; return self.value
    def put_setting(self, serial, key, value): self.value = value


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


if __name__ == "__main__": unittest.main()
