"""
Configuration and settings persistence for ConnectToPhone Desktop.
"""

import os
import json
import socket
from pathlib import Path
from typing import Dict, Any, Optional
from protocol.protocol_spec import generate_device_id

CONFIG_DIR = Path.home() / ".config" / "connecttophone"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "device_id": "",
    "device_name": "",
    "ws_port": 42100,
    "discovery_port": 42101,
    "auto_connect": True,
    "sync_clipboard": True,
    "sync_images": True,
    "minimize_to_tray": True,
    "show_notifications": True,
    "stream_quality": "high", # high, medium, low
    "stream_fps": 30,
    "paired_devices": {} # {device_id: {"name": "...", "auth_token": "...", "last_ip": "..."}}
}

class ConfigManager:
    _instance: Optional['ConfigManager'] = None

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or CONFIG_FILE
        self.config_dir = self.config_file.parent
        self.config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._load()

    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = ConfigManager()
        return cls._instance

    def _load(self):
        """Load configuration from disk or create default."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.config.update(saved)
        except Exception as e:
            print(f"[Config] Error loading config: {e}")

        # Ensure unique device ID and sensible device name
        if not self.config.get("device_id"):
            self.config["device_id"] = generate_device_id()
        if not self.config.get("device_name"):
            hostname = socket.gethostname() or "Linux PC"
            self.config["device_name"] = f"{hostname} (Linux)"
        self.save()

    def save(self):
        """Save configuration to disk."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save()

    def add_paired_device(self, device_id: str, name: str, auth_token: str, ip: str = ""):
        paired = self.config.setdefault("paired_devices", {})
        paired[device_id] = {
            "name": name,
            "auth_token": auth_token,
            "last_ip": ip
        }
        self.save()

    def remove_paired_device(self, device_id: str):
        paired = self.config.get("paired_devices", {})
        if device_id in paired:
            del paired[device_id]
            self.save()

    def get_paired_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        return self.config.get("paired_devices", {}).get(device_id)

    def get_all_paired_devices(self) -> Dict[str, Dict[str, Any]]:
        return self.config.get("paired_devices", {})
