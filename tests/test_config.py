import tempfile
import unittest
from pathlib import Path

from salsilink_control.config import ConfigStore
from salsilink_control.models import AppConfig, PhoneProfile


class ConfigTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "config.json")
            config = AppConfig(profiles=[PhoneProfile(phone_name="Pixel", ip_address="10.0.0.8", device_identity="ABC123", port=5566)])
            store.save(config)
            self.assertEqual(store.load().ip_address, "10.0.0.8")
            self.assertEqual(store.load().port, 5566)
            self.assertEqual(store.load().device_identity, "ABC123")

    def test_multiple_phone_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            profiles = [PhoneProfile(phone_name="Pixel", ip_address="10.0.0.8"), PhoneProfile(phone_name="Fairphone", ip_address="10.0.0.9")]
            config = AppConfig(profiles=profiles, active_profile_id=profiles[1].id)
            store = ConfigStore(Path(directory) / "config.json"); store.save(config); loaded = store.load()
            self.assertEqual(len(loaded.profiles), 2)
            self.assertEqual(loaded.phone_name, "Fairphone")

    def test_legacy_single_profile_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"phone_name":"Old phone","ip_address":"10.0.0.7","port":5555}')
            loaded = ConfigStore(path).load()
            self.assertEqual(loaded.phone_name, "Old phone")
            self.assertEqual(len(loaded.profiles), 1)

    def test_scrcpy_geometry_is_saved_per_phone(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            profile = PhoneProfile(scrcpy_window_x=50, scrcpy_window_y=60, scrcpy_window_width=400, scrcpy_window_height=800)
            store = ConfigStore(path); store.save(AppConfig(profiles=[profile])); loaded = store.load()
            self.assertEqual((loaded.scrcpy_window_x, loaded.scrcpy_window_y), (50, 60))
            self.assertEqual((loaded.scrcpy_window_width, loaded.scrcpy_window_height), (400, 800))

    def test_corrupt_config_is_backed_up(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"; path.write_text("not json")
            loaded = ConfigStore(path).load()
            self.assertEqual(loaded.ip_address, AppConfig().ip_address)
            self.assertEqual(len(list(Path(directory).glob("config.corrompu-*.json"))), 1)


if __name__ == "__main__": unittest.main()
