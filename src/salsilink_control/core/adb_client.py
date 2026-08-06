from __future__ import annotations

import ipaddress
import re
import shutil
import socket
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from ..models import AdbDevice, DeviceKind


class AdbError(RuntimeError):
    pass


WIFI_INTERFACE_RE = re.compile(r"^(?:wlan|wifi|swlan)\d*$", re.I)


def parse_wifi_ipv4(output: str) -> list[str]:
    """Extract IPv4 addresses carried by Android Wi-Fi interfaces only."""
    addresses: list[str] = []
    for line in output.splitlines():
        match = re.search(r"^\d+:\s+([^\s:]+)(?:\s+|[^\s]*\s+)inet\s+(\d+(?:\.\d+){3})/", line.strip())
        if not match or not WIFI_INTERFACE_RE.match(match.group(1)):
            continue
        address = ipaddress.ip_address(match.group(2))
        if not address.is_loopback and not address.is_link_local:
            addresses.append(str(address))
    return addresses


def parse_local_ipv4_networks(output: str) -> list[ipaddress.IPv4Network]:
    networks: list[ipaddress.IPv4Network] = []
    for match in re.finditer(r"\binet\s+(\d+(?:\.\d+){3}/\d+)\b", output):
        interface = ipaddress.ip_interface(match.group(1))
        if interface.version == 4 and not interface.ip.is_loopback and not interface.ip.is_link_local:
            networks.append(interface.network)
    return networks


def local_ipv4_networks() -> list[ipaddress.IPv4Network]:
    binary = shutil.which("ip")
    if not binary:
        return []
    result = subprocess.run(
        [binary, "-o", "-4", "addr", "show", "scope", "global"],
        capture_output=True, text=True, timeout=4, check=False,
    )
    return parse_local_ipv4_networks(result.stdout)


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


def scan_tcp_subnet(
    ip: str,
    port: int,
    timeout: float = 0.6,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, list[str]]:
    """Return hosts accepting TCP connections in the saved IPv4 /24 subnet."""
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError as exc:
        raise AdbError("L’ancienne adresse IP du téléphone est nécessaire pour déterminer le réseau local.") from exc
    if address.version != 4 or address.is_loopback or address.is_link_local:
        raise AdbError("La découverte automatique nécessite une ancienne adresse IPv4 locale valide.")
    network = ipaddress.ip_network(f"{address}/24", strict=False)
    if progress:
        progress(str(network))

    def is_open(host: str) -> bool:
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True
        except OSError:
            return False

    # Probe the saved address first with extra time. The initial ARP exchange or
    # a Wi-Fi power-saving state may make the first connection unusually slow.
    saved_host = str(address)
    try:
        with socket.create_connection((saved_host, int(port)), timeout=max(1.5, timeout)):
            found = [saved_host]
    except OSError:
        found = []

    hosts = [str(host) for host in network.hosts() if str(host) != saved_host]
    with ThreadPoolExecutor(max_workers=64) as executor:
        found.extend(host for host, opened in zip(hosts, executor.map(is_open, hosts)) if opened)
    return str(network), found


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
        output = self.run(["shell", "ip", "-o", "-4", "addr", "show"], serial=serial)
        addresses = parse_wifi_ipv4(output)
        return addresses[0] if addresses else None

    def device_identity(self, serial: str) -> str:
        identity = self.run(["shell", "getprop", "ro.serialno"], serial=serial).strip()
        if not identity:
            identity = self.run(["shell", "getprop", "ro.boot.serialno"], serial=serial).strip()
        return identity

    def device_model(self, serial: str) -> str:
        return self.run(["shell", "getprop", "ro.product.model"], serial=serial).strip()

    def get_setting(self, serial: str, key: str) -> str:
        return self.run(["shell", "settings", "get", "system", key], serial=serial).strip()

    def put_setting(self, serial: str, key: str, value: str) -> None:
        self.run(["shell", "settings", "put", "system", key, value], serial=serial)
