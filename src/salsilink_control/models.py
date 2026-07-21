from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from uuid import uuid4


class DeviceKind(str, Enum):
    USB = "usb"
    TCPIP = "tcpip"


class SessionState(str, Enum):
    IDLE = "idle"
    DISCOVERING = "discovering"
    USB_READY = "usb_ready"
    TCP_CONNECTING = "tcp_connecting"
    TCP_READY = "tcp_ready"
    STARTING_SCRCPY = "starting_scrcpy"
    SCRCPY_RUNNING = "scrcpy_running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(slots=True)
class AdbDevice:
    serial: str
    status: str
    kind: DeviceKind
    model: str = ""
    product: str = ""
    device: str = ""


@dataclass(slots=True)
class ScrcpyCapabilities:
    version: str = "inconnue"
    options: set[str] = field(default_factory=set)

    def supports(self, option: str) -> bool:
        return option in self.options


@dataclass(slots=True)
class PhoneProfile:
    id: str = field(default_factory=lambda: uuid4().hex)
    phone_name: str = "Mon téléphone"
    ip_address: str = ""
    port: int = 5555
    preferred_mode: str = "Automatique"
    quality_profile: str = "Équilibré"
    max_size: int = 1280
    max_fps: int = 30
    bit_rate: str = "4M"
    codec: str = "h264"
    turn_screen_off: bool = False
    keep_awake: bool = True
    always_on_top: bool = False
    disable_audio: bool = True
    window_title: str = "Mon téléphone — Telechipo"
    scrcpy_window_x: int | None = None
    scrcpy_window_y: int | None = None
    scrcpy_window_width: int | None = None
    scrcpy_window_height: int | None = None


@dataclass(slots=True)
class AppConfig:
    profiles: list[PhoneProfile] = field(default_factory=lambda: [PhoneProfile()])
    active_profile_id: str = ""
    show_console: bool = True
    autoscroll: bool = True
    tool_versions: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.profiles:
            self.profiles = [PhoneProfile()]
        if not self.active_profile_id or not any(p.id == self.active_profile_id for p in self.profiles):
            self.active_profile_id = self.profiles[0].id

    @property
    def active_profile(self) -> PhoneProfile:
        return next((p for p in self.profiles if p.id == self.active_profile_id), self.profiles[0])

    def to_dict(self) -> dict:
        return asdict(self)


# Keep the process/configuration APIs pleasantly small while settings live per phone.
for _name in (
    "phone_name", "ip_address", "port", "preferred_mode", "quality_profile",
    "max_size", "max_fps", "bit_rate", "codec", "turn_screen_off", "keep_awake",
    "always_on_top", "disable_audio", "window_title",
    "scrcpy_window_x", "scrcpy_window_y", "scrcpy_window_width", "scrcpy_window_height",
):
    setattr(AppConfig, _name, property(
        lambda self, name=_name: getattr(self.active_profile, name),
        lambda self, value, name=_name: setattr(self.active_profile, name, value),
    ))


QUALITY_PROFILES = {
    "Faible latence": {"max_size": 1024, "max_fps": 30, "bit_rate": "2M", "codec": "h264", "disable_audio": True},
    "Équilibré": {"max_size": 1280, "max_fps": 30, "bit_rate": "4M", "codec": "h264", "disable_audio": True},
    "Haute qualité": {"max_size": 1920, "max_fps": 60, "bit_rate": "8M", "codec": "h264", "disable_audio": True},
}
