import unittest

from salsilink_control.core.window_geometry import WindowGeometry, parse_xdotool_geometry


class WindowGeometryTests(unittest.TestCase):
    def test_parse_xdotool_output(self):
        output = "WINDOW=42\nX=120\nY=80\nWIDTH=470\nHEIGHT=440\nSCREEN=0\n"
        self.assertEqual(parse_xdotool_geometry(output), WindowGeometry(120, 80, 470, 440))

    def test_invalid_output(self):
        self.assertIsNone(parse_xdotool_geometry("X=nope\n"))


if __name__ == "__main__": unittest.main()
