from __future__ import annotations

import ipaddress
import threading
import time
from datetime import datetime
from typing import Any

from gi.repository import Gdk, GLib, Gtk

from ..config import ConfigStore
from ..core.adb_client import AdbClient, AdbError, local_ipv4_networks, scan_tcp_subnet
from ..core.scrcpy_client import ScrcpyClient
from ..core.session_manager import SleepTimeoutGuard
from ..core.window_geometry import X11GeometryController
from ..models import AdbDevice, AppConfig, DeviceKind, PhoneProfile, QUALITY_PROFILES, ScrcpyCapabilities


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, store: ConfigStore) -> None:
        super().__init__(application=app, title="Telechipo")
        self.store, self.config = store, store.load()
        # Keep the controller intentionally tiny; the native scrcpy window is separate.
        self.set_default_size(470, 440)
        self.devices: list[AdbDevice] = []
        self.selected_serial: str | None = None
        self.caps = ScrcpyCapabilities()
        self._closing = False
        self._scrcpy_geometry_capture_running = False
        self._ignore_scrcpy_geometry = False
        self._switching_profile = False
        self.geometry = X11GeometryController()
        self.adb = AdbClient(lambda text: self.log("INFO", text))
        self.scrcpy = ScrcpyClient(lambda line: GLib.idle_add(self.log, "INFO", line), lambda code: GLib.idle_add(self._scrcpy_exited, code))
        self.guard = SleepTimeoutGuard(self.adb, log=lambda text: self.log("WARNING", text))
        self._build()
        self.connect("close-request", self._on_close)
        self._run_async(self._initialize)

    def _build(self) -> None:
        self._install_css()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        root.set_margin_top(6); root.set_margin_bottom(6); root.set_margin_start(6); root.set_margin_end(6)
        self.set_child(root)

        header = Gtk.Box(spacing=6)
        self.title_label = Gtk.Label(label=self.config.phone_name); self.title_label.add_css_class("heading"); self.title_label.set_hexpand(True); self.title_label.set_xalign(0)
        header.append(self.title_label); root.append(header)

        tabs = Gtk.Notebook(); root.append(tabs)
        connection = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5); connection.set_margin_top(6); connection.set_margin_bottom(4); connection.set_margin_start(6); connection.set_margin_end(6)
        tabs.append_page(connection, Gtk.Label(label="Connexion"))
        grid = Gtk.Grid(column_spacing=6, row_spacing=4); connection.append(grid)
        profile_row = Gtk.Box(spacing=4)
        self.phone_profiles = Gtk.DropDown.new_from_strings([profile.phone_name for profile in self.config.profiles]); profile_row.append(self.phone_profiles)
        self.phone_profiles.set_hexpand(True)
        add_profile = Gtk.Button(label="+"); add_profile.set_tooltip_text("Nouveau téléphone"); add_profile.connect("clicked", self._new_phone_profile)
        remove_profile = Gtk.Button(label="−"); remove_profile.set_tooltip_text("Supprimer ce profil"); remove_profile.connect("clicked", self._delete_phone_profile)
        profile_row.append(add_profile); profile_row.append(remove_profile)
        self.name = self._entry(self.config.phone_name); self.ip = self._entry(self.config.ip_address)
        ip_row = Gtk.Box(spacing=4); ip_row.append(self.ip)
        discover = Gtk.Button(label="Détecter"); discover.set_tooltip_text("Retrouver ce téléphone sur le réseau local"); discover.connect("clicked", self.discover_wifi); ip_row.append(discover)
        self.port = Gtk.SpinButton.new_with_range(1, 65535, 1); self.port.set_value(self.config.port)
        self.mode = Gtk.DropDown.new_from_strings(["Automatique", "Wi-Fi", "USB"]); self._select_text(self.mode, ["Automatique", "Wi-Fi", "USB"], self.config.preferred_mode)
        for row, (label, widget) in enumerate((("Téléphone", profile_row), ("Nom", self.name), ("Adresse IP", ip_row), ("Port", self.port), ("Mode préféré", self.mode))):
            lab = Gtk.Label(label=label, xalign=0); grid.attach(lab, 0, row, 1, 1); grid.attach(widget, 1, row, 1, 1)
        self.device_dropdown = Gtk.DropDown.new_from_strings(["Aucun appareil"]); grid.attach(Gtk.Label(label="Appareil ADB", xalign=0), 0, 5, 1, 1); grid.attach(self.device_dropdown, 1, 5, 1, 1)
        buttons = Gtk.Box(spacing=4, homogeneous=True); connection.append(buttons)
        for label, callback in (("Activer ADB Wi-Fi depuis USB", self.prepare_wifi), ("Connecter", self.connect_wifi), ("Déconnecter", self.disconnect_wifi)):
            short_label = "Activer Wi-Fi via USB" if label.startswith("Activer") else label
            button = Gtk.Button(label=short_label); button.set_tooltip_text(label); button.connect("clicked", callback); buttons.append(button)
            if callback == self.prepare_wifi:
                self.prepare_wifi_button = button
                button.set_sensitive(False)
                button.set_tooltip_text("À utiliser après un redémarrage : branchez le téléphone en USB pour activer ADB sur le Wi-Fi")
        status_row = Gtk.Box(spacing=6); connection.append(status_row)
        self.status = Gtk.Label(label="● Non détecté", xalign=0); self.status.set_hexpand(True); self.status.add_css_class("status-error")
        refresh = Gtk.Button(label="Actualiser"); refresh.connect("clicked", lambda _b: self.refresh())
        status_row.append(self.status); status_row.append(refresh)
        display = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5); display.set_margin_top(6); display.set_margin_bottom(4); display.set_margin_start(6); display.set_margin_end(6)
        tabs.append_page(display, Gtk.Label(label="Affichage"))
        dgrid = Gtk.Grid(column_spacing=6, row_spacing=4); display.append(dgrid)
        profiles = [*QUALITY_PROFILES, "Personnalisé"]
        self.profile = Gtk.DropDown.new_from_strings(profiles); self._select_text(self.profile, profiles, self.config.quality_profile); self.profile.connect("notify::selected", self._profile_changed)
        self.max_size = Gtk.SpinButton.new_with_range(0, 4096, 64); self.max_size.set_value(self.config.max_size)
        self.max_fps = Gtk.SpinButton.new_with_range(1, 240, 1); self.max_fps.set_value(self.config.max_fps)
        self.bit_rate = self._entry(self.config.bit_rate); self.codec = self._entry(self.config.codec)
        self.max_size.set_width_chars(6); self.max_size.set_hexpand(True)
        self.max_fps.set_width_chars(5); self.max_fps.set_hexpand(True)
        self.bit_rate.set_width_chars(4); self.bit_rate.set_max_width_chars(5); self.bit_rate.set_hexpand(False)
        self.codec.set_width_chars(6); self.codec.set_hexpand(False)
        self.window_title = self._entry(self.config.window_title)
        dgrid.attach(Gtk.Label(label="Profil vidéo", xalign=0), 0, 0, 1, 1)
        dgrid.attach(self.profile, 1, 0, 1, 1)

        video_row = Gtk.Grid(column_spacing=5)
        for column, (label, widget) in enumerate((("Taille max.", self.max_size), ("FPS max.", self.max_fps), ("Débit", self.bit_rate))):
            video_row.attach(Gtk.Label(label=label, xalign=0), column * 2, 0, 1, 1)
            video_row.attach(widget, column * 2 + 1, 0, 1, 1)
        dgrid.attach(video_row, 0, 1, 2, 1)

        identity_row = Gtk.Grid(column_spacing=5)
        identity_row.attach(Gtk.Label(label="Codec", xalign=0), 0, 0, 1, 1)
        identity_row.attach(self.codec, 1, 0, 1, 1)
        identity_row.attach(Gtk.Label(label="Titre de fenêtre", xalign=0), 2, 0, 1, 1)
        identity_row.attach(self.window_title, 3, 0, 1, 1)
        self.window_title.set_hexpand(True)
        identity_row.set_hexpand(True)
        dgrid.attach(identity_row, 0, 2, 2, 1)
        checks = Gtk.Grid(column_spacing=8, row_spacing=1); display.append(checks)
        self.screen_off = Gtk.CheckButton(label="Éteindre l’écran"); self.screen_off.set_active(self.config.turn_screen_off)
        self.keep_awake = Gtk.CheckButton(label="Empêcher la veille"); self.keep_awake.set_active(self.config.keep_awake)
        self.top = Gtk.CheckButton(label="Toujours au-dessus"); self.top.set_active(self.config.always_on_top)
        self.no_audio = Gtk.CheckButton(label="Sans audio"); self.no_audio.set_active(self.config.disable_audio)
        for index, widget in enumerate((self.screen_off, self.keep_awake, self.top, self.no_audio)):
            checks.attach(widget, index % 2, index // 2, 1, 1)
        actions = Gtk.Box(spacing=6); display.append(actions)
        self.start_button = Gtk.Button(label="Afficher"); self.start_button.connect("clicked", self.start_scrcpy)
        self.stop_button = Gtk.Button(label="Arrêter"); self.stop_button.set_sensitive(False); self.stop_button.connect("clicked", self.stop_scrcpy)
        reset_window = Gtk.Button(label="Réinitialiser fenêtre téléphone"); reset_window.set_tooltip_text("Oublier la position et la taille mémorisées de scrcpy"); reset_window.connect("clicked", self._reset_scrcpy_window_geometry)
        actions.append(self.start_button); actions.append(self.stop_button); actions.append(reset_window)

        console_header = Gtk.Box(spacing=3)
        console_label = Gtk.Label(label="Terminal", xalign=0); console_label.set_hexpand(True); console_header.append(console_label)
        clear = Gtk.Button(label="×"); clear.set_tooltip_text("Effacer"); clear.add_css_class("flat"); clear.connect("clicked", lambda _b: self.console.get_buffer().set_text(""))
        copy = Gtk.Button(label="⧉"); copy.set_tooltip_text("Copier"); copy.add_css_class("flat"); copy.connect("clicked", self._copy_console); console_header.append(clear); console_header.append(copy); root.append(console_header)
        scroll = Gtk.ScrolledWindow(); scroll.set_min_content_height(150); scroll.set_vexpand(True); scroll.set_propagate_natural_height(True); scroll.add_css_class("terminal-frame")
        self.console = Gtk.TextView(editable=False, cursor_visible=False, monospace=True); self.console.add_css_class("terminal"); self.console.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        buffer = self.console.get_buffer()
        self.log_tags = {
            "INFO": buffer.create_tag("info", foreground="#67e667"),
            "WARNING": buffer.create_tag("warning", foreground="#ffd75f"),
            "ERROR": buffer.create_tag("error", foreground="#ff6b6b", weight=700),
        }
        scroll.set_child(self.console); root.append(scroll)
        active_index = next((i for i, profile in enumerate(self.config.profiles) if profile.id == self.config.active_profile_id), 0)
        self.phone_profiles.set_selected(active_index)
        self.phone_profiles.connect("notify::selected", self._phone_profile_changed)

    @staticmethod
    def _install_css() -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            .terminal-frame { border: 1px solid #303830; border-radius: 3px; }
            textview.terminal, textview.terminal text {
                background-color: #080b08;
                color: #67e667;
                font-family: Terminus, monospace;
                font-size: 8pt;
            }
            textview.terminal { padding: 3px; }
            label.status-ok { color: #2ec27e; font-weight: 700; }
            label.status-pending { color: #f5c211; font-weight: 700; }
            label.status-error { color: #e01b24; font-weight: 700; }
        """)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    @staticmethod
    def _section(title: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7); label = Gtk.Label(label=title, xalign=0); label.add_css_class("heading"); box.append(label); return box

    @staticmethod
    def _entry(value: str) -> Gtk.Entry:
        entry = Gtk.Entry(); entry.set_text(value); entry.set_hexpand(True); return entry

    @staticmethod
    def _select_text(dropdown: Gtk.DropDown, values: list[str], value: str) -> None:
        dropdown.set_selected(values.index(value) if value in values else 0)

    def log(self, level: str, message: str) -> bool:
        if not message: return False
        if not GLib.MainContext.default().is_owner():
            GLib.idle_add(self.log, level, message)
            return False
        buffer = self.console.get_buffer(); end = buffer.get_end_iter()
        tag = self.log_tags.get(level, self.log_tags["INFO"])
        buffer.insert_with_tags(end, f"[{datetime.now():%H:%M:%S}] {level:<5} {message}\n", tag)
        if buffer.get_line_count() > 1000:
            start = buffer.get_start_iter(); cutoff = buffer.get_iter_at_line(100); buffer.delete(start, cutoff)
        mark = buffer.create_mark(None, buffer.get_end_iter(), False); self.console.scroll_mark_onscreen(mark); buffer.delete_mark(mark)
        return False

    def _run_async(self, function: Any, *args: Any) -> None:
        def runner() -> None:
            try: function(*args)
            except Exception as exc: GLib.idle_add(self._error, str(exc))
        threading.Thread(target=runner, daemon=True).start()

    def _initialize(self) -> None:
        self.log("INFO", f"adb trouvé : {self.adb.binary or 'absent'}")
        self.caps = self.scrcpy.detect()
        GLib.idle_add(self._capabilities_ready)
        if self.guard.path.exists():
            self.log("WARNING", "Récupération d’un délai de veille temporaire…")
            self.guard.restore()
        self._refresh_worker()

    def _capabilities_ready(self) -> bool:
        self.log("INFO", f"scrcpy trouvé : {self.scrcpy.binary}, version {self.caps.version}")
        codec_ok = self.caps.supports("--video-codec"); self.codec.set_sensitive(codec_ok); self.codec.set_tooltip_text(None if codec_ok else "Codec configurable non pris en charge par cette version")
        audio_ok = self.caps.supports("--no-audio"); self.no_audio.set_sensitive(audio_ok); self.no_audio.set_tooltip_text(None if audio_ok else "Gestion audio indisponible dans cette version")
        return False

    def _set_status(self, text: str, state: str) -> bool:
        for css_class in ("status-ok", "status-pending", "status-error"):
            self.status.remove_css_class(css_class)
        self.status.add_css_class(f"status-{state}")
        self.status.set_text(f"● {text}")
        return False

    def refresh(self) -> None: self._set_status("Recherche…", "pending"); self._run_async(self._refresh_worker)

    def _refresh_worker(self) -> None:
        devices = self.adb.devices(); GLib.idle_add(self._show_devices, devices)

    def _show_devices(self, devices: list[AdbDevice]) -> bool:
        self.devices = devices
        labels = [f"{d.model or d.serial} — {d.status} ({d.kind.value})" for d in devices] or ["Aucun appareil"]
        self.device_dropdown.set_model(Gtk.StringList.new(labels))
        authorized = [d for d in devices if d.status == "device"]
        unauthorized = [d for d in devices if d.status == "unauthorized"]
        tcp = [d for d in authorized if d.kind == DeviceKind.TCPIP]
        usb = [d for d in authorized if d.kind == DeviceKind.USB]
        preferred_mode = self.mode.get_selected_item().get_string()
        preferred = tcp if preferred_mode in ("Automatique", "Wi-Fi") else usb
        preferred_device = preferred[0] if preferred else (authorized[0] if authorized else None)
        self.device_dropdown.set_selected(devices.index(preferred_device) if preferred_device else 0)
        self.prepare_wifi_button.set_sensitive(bool(usb) and not bool(tcp))
        if tcp:
            self.prepare_wifi_button.set_tooltip_text("ADB Wi-Fi est déjà actif : utilisez Afficher, ou Connecter après une déconnexion")
        elif usb:
            self.prepare_wifi_button.set_tooltip_text("Activer ADB Wi-Fi depuis le téléphone USB sélectionné")
        elif unauthorized:
            self.prepare_wifi_button.set_tooltip_text("Déverrouillez le téléphone et acceptez l’autorisation de débogage USB")
        else:
            self.prepare_wifi_button.set_tooltip_text("À utiliser après un redémarrage : branchez le téléphone en USB pour activer ADB sur le Wi-Fi")
        if tcp: text, state = "Connecté en Wi-Fi", "ok"
        elif usb: text, state = "Connecté en USB", "ok"
        elif unauthorized: text, state = "USB non autorisé", "error"
        else: text, state = "Non détecté", "error"
        self._set_status(text, state); self.start_button.set_sensitive(bool(authorized))
        current_name = self.name.get_text().strip()
        if len(authorized) == 1 and (current_name in ("", "Mon téléphone") or current_name.startswith("Téléphone ")):
            device = authorized[0]
            if device.model:
                self.name.set_text(device.model)
                self.title_label.set_text(device.model)
                self.window_title.set_text(f"{device.model} — Telechipo")
                if device.kind == DeviceKind.TCPIP and ":" in device.serial and not self.ip.get_text().strip():
                    self.ip.set_text(device.serial.rsplit(":", 1)[0])
                self._save()
                self._refresh_profile_dropdown()
        return False

    def _refresh_profile_dropdown(self) -> None:
        self._switching_profile = True
        self.phone_profiles.set_model(Gtk.StringList.new([profile.phone_name for profile in self.config.profiles]))
        index = next((i for i, profile in enumerate(self.config.profiles) if profile.id == self.config.active_profile_id), 0)
        self.phone_profiles.set_selected(index)
        self._switching_profile = False

    def _phone_profile_changed(self, dropdown: Gtk.DropDown, _param: Any) -> None:
        if self._switching_profile:
            return
        index = dropdown.get_selected()
        if index >= len(self.config.profiles):
            return
        self._read_config()
        self.config.active_profile_id = self.config.profiles[index].id
        self._load_active_profile()
        self.store.save(self.config)

    def _new_phone_profile(self, _button: Gtk.Button) -> None:
        self._read_config()
        profile = PhoneProfile(phone_name=f"Téléphone {len(self.config.profiles) + 1}")
        self.config.profiles.append(profile); self.config.active_profile_id = profile.id
        self._load_active_profile(); self._refresh_profile_dropdown(); self.store.save(self.config)

    def _delete_phone_profile(self, _button: Gtk.Button) -> None:
        if len(self.config.profiles) == 1:
            self._error("Il faut conserver au moins un profil téléphone.")
            return
        current = self.config.active_profile
        self.config.profiles.remove(current); self.config.active_profile_id = self.config.profiles[0].id
        self._load_active_profile(); self._refresh_profile_dropdown(); self.store.save(self.config)

    def _load_active_profile(self) -> None:
        profile = self.config.active_profile
        self.name.set_text(profile.phone_name); self.ip.set_text(profile.ip_address); self.port.set_value(profile.port)
        self._select_text(self.mode, ["Automatique", "Wi-Fi", "USB"], profile.preferred_mode)
        profiles = [*QUALITY_PROFILES, "Personnalisé"]; self._select_text(self.profile, profiles, profile.quality_profile)
        self.max_size.set_value(profile.max_size); self.max_fps.set_value(profile.max_fps); self.bit_rate.set_text(profile.bit_rate); self.codec.set_text(profile.codec)
        self.screen_off.set_active(profile.turn_screen_off); self.keep_awake.set_active(profile.keep_awake); self.top.set_active(profile.always_on_top); self.no_audio.set_active(profile.disable_audio)
        self.window_title.set_text(profile.window_title); self.title_label.set_text(profile.phone_name)

    def _chosen(self, kind: DeviceKind | None = None) -> AdbDevice:
        candidates = [d for d in self.devices if d.status == "device" and (kind is None or d.kind == kind)]
        if not candidates: raise AdbError("Aucun appareil autorisé correspondant.")
        if kind is None:
            preferred_mode = self.mode.get_selected_item().get_string()
            preferred_kind = DeviceKind.TCPIP if preferred_mode in ("Automatique", "Wi-Fi") else DeviceKind.USB
            preferred = [device for device in candidates if device.kind == preferred_kind]
            if len(preferred) == 1:
                return preferred[0]
        selected = self.device_dropdown.get_selected()
        if selected < len(self.devices) and self.devices[selected] in candidates: return self.devices[selected]
        if len(candidates) == 1: return candidates[0]
        raise AdbError("Plusieurs appareils sont présents : choisissez explicitement l’appareil dans la liste.")

    def prepare_wifi(self, _button: Gtk.Button) -> None:
        try: device = self._chosen(DeviceKind.USB)
        except Exception:
            self._error("Aucun téléphone autorisé connecté en USB. Branchez-le et acceptez l’autorisation de débogage."); return
        self.prepare_wifi_button.set_sensitive(False)
        self._set_status("Vérification Wi-Fi…", "pending")
        self._run_async(self._prepare_worker, device, int(self.port.get_value()), self.config.active_profile_id)
    def _prepare_worker(self, device: AdbDevice, port: int, profile_id: str) -> None:
        try:
            self.log("INFO", f"Appareil USB détecté : {device.model or device.serial}")
            detected_ip = self._validated_phone_wifi(device.serial)
            self.log("INFO", f"Activation ADB TCP/IP sur le port {port}"); self.adb.enable_tcpip(device.serial, port); time.sleep(2)
            endpoint = self.adb.connect_with_retry(detected_ip, port)
            identity = self.adb.device_identity(endpoint)
            GLib.idle_add(self.ip.set_text, detected_ip)
            GLib.idle_add(self._remember_device_identity, profile_id, identity)
            self.log("INFO", f"Connexion à {endpoint} réussie"); self._refresh_worker(); GLib.idle_add(self._save)
        finally:
            GLib.idle_add(self._prepare_finished)

    def _prepare_finished(self) -> bool:
        usb_ready = any(device.status == "device" and device.kind == DeviceKind.USB for device in self.devices)
        wifi_ready = any(device.status == "device" and device.kind == DeviceKind.TCPIP for device in self.devices)
        self.prepare_wifi_button.set_sensitive(usb_ready and not wifi_ready)
        return False

    def discover_wifi(self, _button: Gtk.Button) -> None:
        config = self._read_config()
        profile = config.active_profile
        usb = [device for device in self.devices if device.status == "device" and device.kind == DeviceKind.USB]
        usb_serial = usb[0].serial if len(usb) == 1 else None
        self._set_status("Détection réseau…", "pending")
        self._run_async(self._discover_worker, profile.id, profile.ip_address, profile.port, profile.device_identity, usb_serial)

    def _validated_phone_wifi(self, serial: str) -> str:
        self.log("INFO", "Vérification système — recherche d’une adresse IPv4 portée par l’interface Wi-Fi du téléphone.")
        detected_ip = self.adb.wifi_ip(serial)
        if not detected_ip:
            raise AdbError("Le téléphone n’est pas connecté au Wi-Fi. Activez le Wi-Fi et connectez-le au même réseau que cet ordinateur.")
        networks = local_ipv4_networks()
        if networks and not any(ipaddress.ip_address(detected_ip) in network for network in networks):
            local_text = ", ".join(str(network) for network in networks)
            raise AdbError(f"Le téléphone ({detected_ip}) n’est pas sur le même réseau local que cet ordinateur ({local_text}).")
        self.log("INFO", f"Vérification système réussie — adresse Wi-Fi locale : {detected_ip}.")
        return detected_ip

    def _discover_worker(self, profile_id: str, previous_ip: str, port: int, expected_identity: str, usb_serial: str | None = None) -> None:
        if usb_serial:
            self.log("INFO", "Téléphone USB présent — contrôle du Wi-Fi avant la découverte réseau.")
            previous_ip = self._validated_phone_wifi(usb_serial)
        self.log("INFO", "Détection Wi-Fi — étape 1/4 : détermination du réseau depuis la dernière adresse connue.")
        network, hosts = scan_tcp_subnet(
            previous_ip,
            port,
            progress=lambda subnet: self.log("INFO", f"Détection Wi-Fi — étape 2/4 : test prioritaire de {previous_ip}, puis recherche du port ADB {port} sur {subnet}."),
        )
        self.log("INFO", f"Détection Wi-Fi — {len(hosts)} adresse(s) candidate(s) trouvée(s).")
        matches: list[tuple[str, str, str]] = []
        self.log("INFO", "Détection Wi-Fi — étape 3/4 : vérification des appareils avec ADB.")
        for host in hosts:
            try:
                endpoint = self.adb.connect(host, port)
                identity = self.adb.device_identity(endpoint)
                model = self.adb.device_model(endpoint)
                self.log("INFO", f"Candidat ADB : {host} — {model or 'modèle inconnu'}")
                if identity and (not expected_identity or identity == expected_identity):
                    matches.append((host, identity, model))
            except AdbError as exc:
                self.log("WARNING", f"Candidat {host} ignoré : {exc}")
        if not matches:
            if expected_identity:
                raise AdbError("Le téléphone enregistré n’a pas été retrouvé sur ce réseau.")
            raise AdbError("Aucun téléphone ADB identifiable n’a été trouvé sur ce réseau.")
        if len(matches) > 1:
            raise AdbError("Plusieurs téléphones ADB ont été trouvés ; connectez d’abord celui voulu manuellement.")
        host, identity, model = matches[0]
        self.log("INFO", f"Détection Wi-Fi — étape 4/4 : téléphone reconnu à l’adresse {host}.")
        GLib.idle_add(self._apply_discovered_device, profile_id, host, identity, model)

    def _remember_device_identity(self, profile_id: str, identity: str) -> bool:
        if identity:
            profile = next((item for item in self.config.profiles if item.id == profile_id), None)
            if profile:
                profile.device_identity = identity
                self.store.save(self.config)
        return False

    def _apply_discovered_device(self, profile_id: str, host: str, identity: str, model: str) -> bool:
        profile = next((item for item in self.config.profiles if item.id == profile_id), None)
        if not profile:
            return False
        profile.ip_address = host; profile.device_identity = identity
        if profile.id == self.config.active_profile_id:
            self.ip.set_text(host)
        self.store.save(self._read_config())
        self.log("INFO", f"Adresse du profil mise à jour : {host} ({model or 'téléphone Android'}).")
        self._refresh_worker()
        return False

    def connect_wifi(self, _button: Gtk.Button) -> None: self._connect_action(False)
    def connect_and_show(self, _button: Gtk.Button) -> None: self._connect_action(True)
    def _connect_action(self, launch: bool) -> None:
        config = self._read_config(); self._run_async(self._connect_worker, launch, config.ip_address, config.port, config)
    def _connect_worker(self, launch: bool, ip: str, port: int, config: AppConfig) -> None:
        GLib.idle_add(self._set_status, "Connexion Wi-Fi en cours", "pending")
        endpoint = self.adb.connect(ip, port); self.log("INFO", f"Connexion à {endpoint} réussie")
        identity = self.adb.device_identity(endpoint)
        GLib.idle_add(self._remember_device_identity, config.active_profile_id, identity)
        devices = self.adb.devices(); GLib.idle_add(self._show_devices, devices)
        if launch:
            tcp = [d for d in devices if d.serial == endpoint and d.status == "device"]
            if not tcp: raise AdbError("La connexion existe mais l’appareil n’est pas encore prêt.")
            self._start_worker(tcp[0].serial, config)

    def disconnect_wifi(self, _button: Gtk.Button) -> None:
        self._run_async(self._disconnect_worker, self.ip.get_text(), int(self.port.get_value()))
    def _disconnect_worker(self, ip: str, port: int) -> None:
        if self.scrcpy.process and self.scrcpy.process.poll() is None: raise AdbError("Arrêtez scrcpy avant de déconnecter le téléphone.")
        self.adb.disconnect(ip, port); self.log("INFO", "Connexion ADB Wi-Fi déconnectée."); self._refresh_worker()

    def start_scrcpy(self, _button: Gtk.Button) -> None:
        try: serial = self._chosen().serial
        except Exception as exc: self._error(str(exc)); return
        self._run_async(self._start_worker, serial, self._read_config())
    def _start_worker(self, device_serial: str, config: AppConfig) -> None:
        self._ignore_scrcpy_geometry = False
        guard_applied = False
        # Old scrcpy versions only provide --stay-awake, which stops working as
        # soon as the USB cable is removed. Use the recoverable Android timeout
        # guard for these Wi-Fi sessions as well.
        if config.keep_awake and not self.caps.supports("--screen-off-timeout"):
            self.guard.apply(device_serial); self.log("INFO", "Délai de veille Android temporairement prolongé.")
            guard_applied = True
        try:
            command = self.scrcpy.start(device_serial, config, self.caps)
        except Exception:
            if guard_applied:
                self.guard.restore()
            raise
        self.log("INFO", "Commande : " + " ".join(command)); GLib.idle_add(self._scrcpy_started)

    def _scrcpy_started(self) -> bool:
        self._set_status("scrcpy actif", "ok"); self.start_button.set_sensitive(False); self.stop_button.set_sensitive(True); self.phone_profiles.set_sensitive(False)
        GLib.timeout_add(750, self._schedule_scrcpy_geometry_capture)
        return False

    def stop_scrcpy(self, _button: Gtk.Button) -> None:
        self._run_async(self._stop_scrcpy_worker)
    def _stop_scrcpy_worker(self) -> None:
        self._capture_scrcpy_geometry_worker()
        self.scrcpy.stop()
    def _scrcpy_exited(self, code: int) -> bool:
        restored = self.guard.restore()
        suffix = "délai de veille restauré" if restored else "restauration du délai de veille en attente d’une reconnexion"
        self.log("INFO" if code == 0 and restored else "WARNING", f"scrcpy fermé (code {code}), {suffix}")
        self.store.save(self._read_config())
        self.stop_button.set_sensitive(False); self.start_button.set_sensitive(True); self.phone_profiles.set_sensitive(True); self.refresh(); return False

    def _schedule_scrcpy_geometry_capture(self) -> bool:
        process = self.scrcpy.process
        if not process or process.poll() is not None:
            return False
        if not self._scrcpy_geometry_capture_running:
            self._scrcpy_geometry_capture_running = True
            self._run_async(self._capture_scrcpy_geometry_worker)
        return True

    def _capture_scrcpy_geometry_worker(self) -> None:
        try:
            process = self.scrcpy.process
            geometry = self.geometry.read_for_pid(process.pid) if process and process.poll() is None and not self._ignore_scrcpy_geometry else None
            if geometry:
                GLib.idle_add(self._store_scrcpy_geometry, geometry.x, geometry.y, geometry.width, geometry.height)
        finally:
            self._scrcpy_geometry_capture_running = False

    def _store_scrcpy_geometry(self, x: int, y: int, width: int, height: int) -> bool:
        profile = self.config.active_profile
        profile.scrcpy_window_x, profile.scrcpy_window_y = x, y
        profile.scrcpy_window_width, profile.scrcpy_window_height = width, height
        self.store.save(self._read_config())
        return False

    def _reset_scrcpy_window_geometry(self, _button: Gtk.Button) -> None:
        profile = self.config.active_profile
        profile.scrcpy_window_x = profile.scrcpy_window_y = None
        profile.scrcpy_window_width = profile.scrcpy_window_height = None
        self._ignore_scrcpy_geometry = True
        self.store.save(self._read_config())
        self.log("INFO", "Position et taille de la fenêtre du téléphone oubliées ; le réglage automatique sera utilisé au prochain affichage.")

    def _profile_changed(self, dropdown: Gtk.DropDown, _param: Any) -> None:
        name = dropdown.get_selected_item().get_string(); profile = QUALITY_PROFILES.get(name)
        if profile: self.max_size.set_value(profile["max_size"]); self.max_fps.set_value(profile["max_fps"]); self.bit_rate.set_text(profile["bit_rate"]); self.codec.set_text(profile["codec"]); self.no_audio.set_active(profile["disable_audio"])

    def _read_config(self) -> AppConfig:
        selected = self.profile.get_selected_item(); mode = self.mode.get_selected_item()
        self.config.phone_name = self.name.get_text().strip() or "Téléphone"; self.config.ip_address = self.ip.get_text().strip(); self.config.port = int(self.port.get_value())
        self.config.preferred_mode = mode.get_string(); self.config.quality_profile = selected.get_string(); self.config.max_size = int(self.max_size.get_value()); self.config.max_fps = int(self.max_fps.get_value())
        self.config.bit_rate = self.bit_rate.get_text().strip(); self.config.codec = self.codec.get_text().strip(); self.config.turn_screen_off = self.screen_off.get_active(); self.config.keep_awake = self.keep_awake.get_active()
        self.config.always_on_top = self.top.get_active(); self.config.disable_audio = self.no_audio.get_active(); self.config.window_title = self.window_title.get_text(); self.config.tool_versions = {"scrcpy": self.caps.version}
        self.title_label.set_text(self.config.phone_name)
        return self.config

    def _save(self) -> bool: self.store.save(self._read_config()); return False
    def _error(self, message: str) -> bool: self._set_status("Erreur", "error"); self.log("ERROR", message); return False
    def _copy_console(self, _button: Gtk.Button) -> None:
        buffer = self.console.get_buffer(); text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False); Gdk.Display.get_default().get_clipboard().set(text)
    def _on_close(self, _window: Gtk.Window) -> bool:
        self.get_application().quit(); return True
    def shutdown(self) -> None:
        if self._closing: return
        self._closing = True
        process = self.scrcpy.process
        if process and process.poll() is None and not self._ignore_scrcpy_geometry:
            geometry = self.geometry.read_for_pid(process.pid)
            if geometry:
                profile = self.config.active_profile
                profile.scrcpy_window_x, profile.scrcpy_window_y = geometry.x, geometry.y
                profile.scrcpy_window_width, profile.scrcpy_window_height = geometry.width, geometry.height
        self._save(); self.scrcpy.stop(); self.guard.restore()
