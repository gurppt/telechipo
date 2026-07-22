from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
import time
from collections.abc import Callable

from ..models import AdbDevice, DeviceKind


class AdbError(RuntimeError):
    pass


def parse_devices(output: str) -> list[AdbDevice]:
    devices: list[AdbDevice] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, status = parts[:2]
        attrs = dict(item.split(":", 1) for item in parts[2:] if ":" in item)
        kind = DeviceKind.TCPIP if re.match(r"^.+:\d+$", serial) else DeviceKind.USB
        devices.append(AdbDevice(serial, status, kind, attrs.get("model", "").replace("_", " "), attrs.get("product", ""), attrs.get("device", "")))
    return devices


def validate_endpoint(ip: str, port: int) -> str:
    try:
        address = str(ipaddress.ip_address(ip.strip()))
    except ValueError as exc:
        raise AdbError("Adresse IP invalide.") from exc
    if not 1 <= int(port) <= 65535:
        raise AdbError("Le port doit être compris entre 1 et 65535.")
    return f"{address}:{int(port)}"


class AdbClient:
    def __init__(self, log: Callable[[str], None] | None = None, timeout: float = 12) -> None:
        self.binary = shutil.which("adb")
        self.log = log or (lambda _message: None)
        self.timeout = timeout

    def run(self, args: list[str], serial: str | None = None, timeout: float | None = None) -> str:
        if not self.binary:
            raise AdbError("adb est absent du PATH.")
        command = [self.binary]
        if serial:
            command += ["-s", serial]
        command += args
        self.log("Commande : " + " ".join(command))
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout or self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise AdbError("La commande adb a expiré.") from exc
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if result.returncode:
            raise AdbError(output or f"adb a quitté avec le code {result.returncode}")
        return output

    def devices(self) -> list[AdbDevice]:
        return parse_devices(self.run(["devices", "-l"]))

    def connect(self, ip: str, port: int) -> str:
        endpoint = validate_endpoint(ip, port)
        output = self.run(["connect", endpoint], timeout=18)
        if "connected to" not in output.lower() and "already connected" not in output.lower():
            raise AdbError(output or "Connexion ADB Wi-Fi impossible.")
        return endpoint

    def connect_with_retry(self, ip: str, port: int, attempts: int = 5, delay: float = 1.0) -> str:
        """Connect after ``adb tcpip``, while adbd may still be restarting."""
        last_error: AdbError | None = None
        for attempt in range(max(1, attempts)):
            try:
                return self.connect(ip, port)
            except AdbError as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(delay)
        assert last_error is not None
        raise last_error

    def disconnect(self, ip: str, port: int) -> None:
        self.run(["disconnect", validate_endpoint(ip, port)])

    def enable_tcpip(self, serial: str, port: int) -> None:
        if not 1 <= int(port) <= 65535:
            raise AdbError("Port invalide.")
        self.run(["tcpip", str(port)], serial=serial, timeout=18)

    def wifi_ip(self, serial: str) -> str | None:
        output = self.run(["shell", "ip", "-f", "inet", "addr", "show", "wlan0"], serial=serial)
        match = re.search(r"\binet\s+(\d+(?:\.\d+){3})/", output)
        return match.group(1) if match else None

    def get_setting(self, serial: str, key: str) -> str:
        return self.run(["shell", "settings", "get", "system", key], serial=serial).strip()

    def put_setting(self, serial: str, key: str, value: str) -> None:
        self.run(["shell", "settings", "put", "system", key, value], serial=serial)
