from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from collections.abc import Callable

from ..models import AppConfig, ScrcpyCapabilities
from .capability_detection import parse_scrcpy_capabilities


class ScrcpyError(RuntimeError):
    pass


def build_command(binary: str, serial: str, config: AppConfig, caps: ScrcpyCapabilities) -> list[str]:
    command = [binary, "--serial", serial]
    candidates: list[tuple[str, str | None]] = [
        ("--max-size", str(config.max_size)),
        ("--max-fps", str(config.max_fps)),
        ("--video-bit-rate" if caps.supports("--video-bit-rate") else "--bit-rate", config.bit_rate),
        ("--window-title", config.window_title),
    ]
    for option, value in candidates:
        if caps.supports(option) and value:
            command += [option, value]
    geometry = (
        ("--window-x", config.scrcpy_window_x),
        ("--window-y", config.scrcpy_window_y),
        ("--window-width", config.scrcpy_window_width),
        ("--window-height", config.scrcpy_window_height),
    )
    for option, value in geometry:
        if value is not None and caps.supports(option):
            command += [option, str(value)]
    if config.codec and caps.supports("--video-codec"):
        command += ["--video-codec", config.codec]
    if config.turn_screen_off and caps.supports("--turn-screen-off"):
        command.append("--turn-screen-off")
    if config.always_on_top and caps.supports("--always-on-top"):
        command.append("--always-on-top")
    if config.disable_audio and caps.supports("--no-audio"):
        command.append("--no-audio")
    # --stay-awake only works while Android considers itself plugged in.  The
    # explicit timeout also covers wireless sessions on recent scrcpy versions.
    if config.keep_awake and caps.supports("--screen-off-timeout"):
        command += ["--screen-off-timeout", "86400"]
    elif config.keep_awake and caps.supports("--stay-awake"):
        command.append("--stay-awake")
    return command


class ScrcpyClient:
    def __init__(self, line_callback: Callable[[str], None], exit_callback: Callable[[int], None]) -> None:
        self.binary = shutil.which("scrcpy")
        self.line_callback = line_callback
        self.exit_callback = exit_callback
        self.process: subprocess.Popen[str] | None = None

    def detect(self) -> ScrcpyCapabilities:
        if not self.binary:
            raise ScrcpyError("scrcpy est absent du PATH.")
        version = subprocess.run([self.binary, "--version"], capture_output=True, text=True, timeout=8, check=False)
        help_result = subprocess.run([self.binary, "--help"], capture_output=True, text=True, timeout=8, check=False)
        return parse_scrcpy_capabilities(version.stdout + version.stderr, help_result.stdout + help_result.stderr)

    def start(self, serial: str, config: AppConfig, caps: ScrcpyCapabilities) -> list[str]:
        if self.process and self.process.poll() is None:
            raise ScrcpyError("scrcpy est déjà actif.")
        if not self.binary:
            raise ScrcpyError("scrcpy est absent du PATH.")
        command = build_command(self.binary, serial, config, caps)
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
        threading.Thread(target=self._watch, daemon=True).start()
        return command

    def _watch(self) -> None:
        process = self.process
        if not process:
            return
        assert process.stdout is not None
        for line in process.stdout:
            self.line_callback(line.rstrip())
        code = process.wait()
        self.exit_callback(code)

    def stop(self) -> None:
        process = self.process
        if not process or process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
