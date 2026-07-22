from __future__ import annotations

import signal

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk

from .config import ConfigStore
from .ui.main_window import MainWindow


class TelechipoApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="io.github.gurppt.Telechipo", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        Gtk.Window.set_default_icon_name("io.github.gurppt.Telechipo")
        self.window: MainWindow | None = None

    def do_activate(self) -> None:
        if not self.window:
            self.window = MainWindow(self, ConfigStore())
        self.window.present()

    def do_shutdown(self) -> None:
        if self.window:
            self.window.shutdown()
        Gtk.Application.do_shutdown(self)


def main() -> int:
    app = TelechipoApplication()
    signal.signal(signal.SIGINT, lambda *_args: app.quit())
    signal.signal(signal.SIGTERM, lambda *_args: app.quit())
    return app.run(None)
