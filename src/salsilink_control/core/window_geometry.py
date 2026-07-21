from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(slots=True)
class WindowGeometry:
    x: int
    y: int
    width: int
    height: int


def parse_xdotool_geometry(output: str) -> WindowGeometry | None:
    values: dict[str, int] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"X", "Y", "WIDTH", "HEIGHT"}:
            try:
                values[key] = int(value)
            except ValueError:
                return None
    if values.keys() >= {"X", "Y", "WIDTH", "HEIGHT"}:
        return WindowGeometry(values["X"], values["Y"], values["WIDTH"], values["HEIGHT"])
    return None


class X11GeometryController:
    """Optional X11 positioning through xdotool; GTK4 itself cannot place windows."""

    def __init__(self) -> None:
        self.binary = shutil.which("xdotool")

    def read(self, xid: int) -> WindowGeometry | None:
        if not self.binary:
            return None
        result = subprocess.run(
            [self.binary, "getwindowgeometry", "--shell", str(xid)],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return parse_xdotool_geometry(result.stdout) if result.returncode == 0 else None

    def read_for_pid(self, pid: int) -> WindowGeometry | None:
        if not self.binary:
            return None
        result = subprocess.run(
            [self.binary, "search", "--onlyvisible", "--pid", str(pid)],
            capture_output=True, text=True, timeout=2, check=False,
        )
        window_ids = [line.strip() for line in result.stdout.splitlines() if line.strip().isdigit()]
        return self.read(int(window_ids[-1])) if window_ids else None

    def apply(self, xid: int, geometry: WindowGeometry) -> bool:
        if not self.binary:
            return False
        commands = (
            [self.binary, "windowsize", str(xid), str(geometry.width), str(geometry.height)],
            [self.binary, "windowmove", str(xid), str(geometry.x), str(geometry.y)],
        )
        return all(subprocess.run(command, timeout=2, check=False).returncode == 0 for command in commands)

    def centered(self, width: int, height: int) -> WindowGeometry:
        if not self.binary:
            return WindowGeometry(80, 80, width, height)
        result = subprocess.run([self.binary, "getdisplaygeometry"], capture_output=True, text=True, timeout=2, check=False)
        try:
            screen_width, screen_height = (int(value) for value in result.stdout.split()[:2])
            return WindowGeometry(max(0, (screen_width - width) // 2), max(0, (screen_height - height) // 2), width, height)
        except (ValueError, IndexError):
            return WindowGeometry(80, 80, width, height)
