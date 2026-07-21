from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from .models import AppConfig, PhoneProfile


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "telechipo"


def state_dir() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "telechipo"


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "config.json"
        self.legacy_path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "salsilink-control/config.json" if path is None else None

    def load(self) -> AppConfig:
        source = self.path
        if not source.exists() and self.legacy_path and self.legacy_path.exists():
            source = self.legacy_path
        if not source.exists():
            return AppConfig()
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
            if "profiles" in raw:
                profiles = [PhoneProfile(**profile) for profile in raw.get("profiles", [])]
            else:
                # One-time migration from SalsiLink's single-phone configuration.
                profile_fields = PhoneProfile.__dataclass_fields__
                profiles = [PhoneProfile(**{key: value for key, value in raw.items() if key in profile_fields})]
            config = AppConfig(
                profiles=profiles,
                active_profile_id=raw.get("active_profile_id", profiles[0].id if profiles else ""),
                show_console=raw.get("show_console", True), autoscroll=raw.get("autoscroll", True),
                tool_versions=raw.get("tool_versions", {}),
            )
            if source != self.path:
                self.save(config)
            return config
        except (OSError, ValueError, TypeError):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            try:
                shutil.copy2(source, source.with_name(f"config.corrompu-{stamp}.json"))
            except OSError:
                pass
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
