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

        if test_config_path.exists():
            test_config_path.unlink()


if __name__ == "__main__":
    unittest.main()

