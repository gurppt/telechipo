from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ..config import state_dir
from ..models import SessionState
from .adb_client import AdbClient


ALLOWED_TRANSITIONS = {
    SessionState.IDLE: {SessionState.DISCOVERING, SessionState.TCP_CONNECTING, SessionState.ERROR},
    SessionState.DISCOVERING: {SessionState.IDLE, SessionState.USB_READY, SessionState.TCP_READY, SessionState.ERROR},
    SessionState.USB_READY: {SessionState.DISCOVERING, SessionState.TCP_CONNECTING, SessionState.STARTING_SCRCPY, SessionState.ERROR},
    SessionState.TCP_CONNECTING: {SessionState.TCP_READY, SessionState.ERROR},
    SessionState.TCP_READY: {SessionState.DISCOVERING, SessionState.STARTING_SCRCPY, SessionState.IDLE, SessionState.ERROR},
    SessionState.STARTING_SCRCPY: {SessionState.SCRCPY_RUNNING, SessionState.ERROR, SessionState.TCP_READY},
    SessionState.SCRCPY_RUNNING: {SessionState.STOPPING, SessionState.TCP_READY, SessionState.USB_READY, SessionState.IDLE, SessionState.ERROR},
    SessionState.STOPPING: {SessionState.TCP_READY, SessionState.USB_READY, SessionState.IDLE, SessionState.ERROR},
    SessionState.ERROR: {SessionState.IDLE, SessionState.DISCOVERING, SessionState.TCP_CONNECTING},
}


class StateMachine:
    def __init__(self) -> None:
        self.state = SessionState.IDLE

    def transition(self, new_state: SessionState) -> None:
        if new_state != self.state and new_state not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"Transition invalide : {self.state.value} → {new_state.value}")
        self.state = new_state


class SleepTimeoutGuard:
    """Persist and restore Android's exact screen timeout value."""
    def __init__(self, adb: AdbClient, path: Path | None = None, log: Callable[[str], None] | None = None) -> None:
        self.adb = adb
        self.path = path or state_dir() / "screen-timeout-recovery.json"
        self.log = log or (lambda _message: None)

    def apply(self, serial: str, milliseconds: int = 86_400_000) -> None:
        previous = self.adb.get_setting(serial, "screen_off_timeout")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"serial": serial, "value": previous}), encoding="utf-8")
        tmp.replace(self.path)
        self.adb.put_setting(serial, "screen_off_timeout", str(milliseconds))

    def restore(self) -> bool:
        if not self.path.exists():
            return True
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.adb.put_setting(str(data["serial"]), "screen_off_timeout", str(data["value"]))
            self.path.unlink()
            self.log("Délai de veille Android restauré.")
            return True
        except Exception as exc:
            self.log(f"Impossible de restaurer le délai de veille : {exc}")
            return False
