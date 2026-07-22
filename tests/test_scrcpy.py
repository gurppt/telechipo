import unittest

from salsilink_control.core.capability_detection import parse_scrcpy_capabilities, parse_scrcpy_version
from salsilink_control.core.scrcpy_client import build_command
from salsilink_control.models import AppConfig


class ScrcpyTests(unittest.TestCase):
    def test_version_and_old_bitrate(self):
        caps = parse_scrcpy_capabilities("scrcpy 1.25", "--bit-rate=value\n--max-size=value\n--max-fps=value")
        self.assertEqual(caps.version, "1.25")
        command = build_command("/usr/bin/scrcpy", "abc", AppConfig(), caps)
        self.assertIn("--bit-rate", command)
        self.assertNotIn("--video-bit-rate", command)

    def test_modern_options(self):
        help_text = "--video-bit-rate=value --video-codec=name --no-audio --stay-awake --window-title=text"
        caps = parse_scrcpy_capabilities("scrcpy v3.2", help_text)
        command = build_command("scrcpy", "192.0.2.1:5555", AppConfig(), caps)
        self.assertEqual(parse_scrcpy_version("scrcpy v3.2"), "3.2")
        self.assertIn("--video-bit-rate", command)
        self.assertIn("--no-audio", command)
        self.assertIn("--stay-awake", command)
        self.assertEqual(command[:3], ["scrcpy", "--serial", "192.0.2.1:5555"])

    def test_screen_timeout_fallback(self):
        caps = parse_scrcpy_capabilities("scrcpy 3.0", "--screen-off-timeout=seconds")
        command = build_command("scrcpy", "abc", AppConfig(), caps)
        self.assertEqual(command[-2:], ["--screen-off-timeout", "86400"])

    def test_screen_timeout_is_preferred_over_plugged_in_only_stay_awake(self):
        caps = parse_scrcpy_capabilities("scrcpy 3.0", "--stay-awake --screen-off-timeout=seconds")
        command = build_command("scrcpy", "abc", AppConfig(), caps)
        self.assertIn("--screen-off-timeout", command)
        self.assertNotIn("--stay-awake", command)

    def test_phone_window_geometry(self):
        config = AppConfig()
        config.scrcpy_window_x, config.scrcpy_window_y = 40, 50
        config.scrcpy_window_width, config.scrcpy_window_height = 500, 900
        caps = parse_scrcpy_capabilities("scrcpy 1.25", "--window-x=value --window-y=value --window-width=value --window-height=value")
        command = build_command("scrcpy", "abc", config, caps)
        self.assertIn("--window-x", command); self.assertIn("40", command)
        self.assertIn("--window-height", command); self.assertIn("900", command)


if __name__ == "__main__": unittest.main()
