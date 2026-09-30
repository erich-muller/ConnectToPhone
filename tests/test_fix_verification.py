import unittest
import threading
import time
import socket
from pathlib import Path

from desktop.core.signals import EventSignal
from desktop.core.stream_receiver import StreamReceiver
from desktop.core.discovery import DiscoveryService, get_subnet_broadcasts
from desktop.core.config_manager import ConfigManager
from desktop.core.clipboard_service import ClipboardService
from desktop.core.connection_manager import ConnectionManager, ConnectionState


class TestFixVerification(unittest.TestCase):
    def test_event_signal_thread_safety(self):
        signal = EventSignal()
        received = []

        def on_event(val1, val2):
            received.append((val1, val2))

        signal.connect(on_event)

        def worker():
            signal.emit("hello", 42)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], ("hello", 42))

    def test_stream_receiver_raw_frames(self):
        receiver = StreamReceiver(device_id="test-pc")
        frames = []

        receiver.frame_received.connect(lambda raw, stats: frames.append((raw, stats)))

        import base64
        sample_bytes = b"\xff\xd8\xff\xe0testjpegdata"
        b64_payload = base64.b64encode(sample_bytes).decode('ascii')

        payload = {
            "data": b64_payload,
            "width": 640,
            "height": 480,
            "timestamp": 12345
        }

        receiver.handle_frame_data(payload)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0][0], sample_bytes)
        self.assertEqual(frames[0][1]["resolution"], "640x480")

    def test_discovery_targets_and_subnets(self):
        subnets = get_subnet_broadcasts()
        self.assertIsInstance(subnets, list)

        disc = DiscoveryService(device_id="test", device_name="test_pc")
        disc.add_target_ip("192.168.1.5")
        self.assertIn("192.168.1.5", disc._target_ips)

        disc.set_target_ips(["10.0.0.2", "192.168.1.50"])
        self.assertEqual(disc._target_ips, {"10.0.0.2", "192.168.1.50"})

    def test_connection_manager_trigger_discovery(self):
        test_config_path = Path("/tmp/connect_test_discovery_config.json")
        if test_config_path.exists():
            test_config_path.unlink()

        cfg = ConfigManager(config_file=test_config_path)
        cfg.add_paired_device("phone-1", "Samsung Test", "token123", "192.168.1.88")

        clip = ClipboardService(device_id=cfg.get("device_id"))
        stream = StreamReceiver(device_id=cfg.get("device_id"))

        conn = ConnectionManager(config_manager=cfg, clipboard_service=clip, stream_receiver=stream)
        self.assertIn("192.168.1.88", conn.discovery._target_ips)

        # Trigger discovery
        conn.trigger_discovery()
        self.assertIn("192.168.1.88", conn.discovery._target_ips)

    def test_quality_profiles_and_normalization(self):
        from desktop.core.connection_manager import QUALITY_PROFILES, normalize_quality_key
        # Check all 5 profiles are present
        self.assertIn("max", QUALITY_PROFILES)
        self.assertIn("1080p", QUALITY_PROFILES)
        self.assertIn("720p", QUALITY_PROFILES)
        self.assertIn("480p", QUALITY_PROFILES)
        self.assertIn("360p", QUALITY_PROFILES)

        # Max resolution allows 2K / 4K without downscaling
        self.assertEqual(QUALITY_PROFILES["max"]["max_dimension"], 0)
        self.assertGreaterEqual(QUALITY_PROFILES["max"]["jpeg_quality"], 85)

        # Test normalization
        self.assertEqual(normalize_quality_key("2k"), "max")
        self.assertEqual(normalize_quality_key("4k"), "max")
        self.assertEqual(normalize_quality_key("native"), "max")
        self.assertEqual(normalize_quality_key("high"), "1080p")
        self.assertEqual(normalize_quality_key("medium"), "720p")
        self.assertEqual(normalize_quality_key("low"), "480p")
        self.assertEqual(normalize_quality_key("360p"), "360p")
        self.assertEqual(normalize_quality_key("invalid_value"), "720p")

    def test_connection_manager_set_quality(self):
        test_config_path = Path("/tmp/connect_test_quality_config.json")
        if test_config_path.exists():
            test_config_path.unlink()

        cfg = ConfigManager(config_file=test_config_path)
        clip = ClipboardService(device_id=cfg.get("device_id"))
        stream = StreamReceiver(device_id=cfg.get("device_id"))
        conn = ConnectionManager(config_manager=cfg, clipboard_service=clip, stream_receiver=stream)

        received_quality = []
        conn.quality_changed.connect(lambda q: received_quality.append(q))

        conn.set_stream_quality("1080p")
        self.assertEqual(cfg.get("stream_quality"), "1080p")
        self.assertEqual(received_quality, ["1080p"])

        conn.set_stream_quality("2k")
        self.assertEqual(cfg.get("stream_quality"), "max")
        self.assertEqual(received_quality, ["1080p", "max"])

        if test_config_path.exists():
            test_config_path.unlink()

    def test_screenshot_and_image_sync_notification(self):
        import base64
        test_config_path = Path("/tmp/connect_test_screen_config.json")
        if test_config_path.exists():
            test_config_path.unlink()

        cfg = ConfigManager(config_file=test_config_path)
        clip = ClipboardService(device_id=cfg.get("device_id"))
        stream = StreamReceiver(device_id=cfg.get("device_id"))
        conn = ConnectionManager(config_manager=cfg, clipboard_service=clip, stream_receiver=stream)

        notifications = []
        conn.notification_requested.connect(lambda title, body: notifications.append((title, body)))

        img_b64 = base64.b64encode(b"samplepngdatabytes12345678").decode("ascii")
        conn._handle_authenticated_message("CLIPBOARD_IMAGE", {"data": img_b64, "is_screenshot": True}, "phone-1")

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0][0], "Captura de Tela Sincronizada")

        if test_config_path.exists():
            test_config_path.unlink()

    def test_scrcpy_launch_helper(self):
        test_config_path = Path("/tmp/connect_test_scrcpy_config.json")
        if test_config_path.exists():
            test_config_path.unlink()

        cfg = ConfigManager(config_file=test_config_path)
        clip = ClipboardService(device_id=cfg.get("device_id"))
        stream = StreamReceiver(device_id=cfg.get("device_id"))
        conn = ConnectionManager(config_manager=cfg, clipboard_service=clip, stream_receiver=stream)

        success, msg = conn.launch_scrcpy()
        self.assertIsInstance(success, bool)
        self.assertIsInstance(msg, str)
        self.assertTrue(len(msg) > 0)

        if test_config_path.exists():
            test_config_path.unlink()

    def test_no_emojis_in_source_tree(self):
        import re
        import glob
        emoji_pattern = re.compile(r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff]")
        files_to_check = (
            glob.glob("desktop/ui_adw/**/*.py", recursive=True) +
            glob.glob("desktop/gnome-extension/**/*.js", recursive=True) +
            glob.glob("desktop/core/**/*.py", recursive=True) +
            glob.glob("android/app/src/main/**/*.kt", recursive=True) +
            glob.glob("android/app/src/main/**/*.xml", recursive=True)
        )
        for filepath in files_to_check:
            with open(filepath, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f, 1):
                    emojis = emoji_pattern.findall(line)
                    self.assertEqual(
                        emojis, [],
                        f"Emoji found in {filepath}:{idx}: {emojis}"
                    )


if __name__ == "__main__":
    unittest.main()


