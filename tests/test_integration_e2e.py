"""
End-to-End Integration Test for ConnectToPhone.
Simulates a full session between Linux Desktop Server and an Android Companion Client over LAN.
"""

import unittest
import asyncio
import threading
import time
import base64
import json
import websockets
from io import BytesIO
from PIL import Image

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication

from protocol.protocol_spec import (
    MessageType, create_message, serialize_message,
    deserialize_message, generate_auth_token
)
from desktop.core.config_manager import ConfigManager
from desktop.core.clipboard_service import ClipboardService
from desktop.core.stream_receiver import StreamReceiver
from desktop.core.connection_manager import ConnectionManager, ConnectionState

class TestConnectToPhoneE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create Qt Application if not exists
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        import socket
        from pathlib import Path
        def find_free_port():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', 0))
                return s.getsockname()[1]

        self.test_config_path = Path("/tmp/connect_test_config.json")
        if self.test_config_path.exists():
            self.test_config_path.unlink()

        self.config = ConfigManager(config_file=self.test_config_path)
        test_ws_port = find_free_port()
        test_disc_port = find_free_port()
        self.config.set("ws_port", test_ws_port)
        self.config.set("discovery_port", test_disc_port)

        self.clipboard = ClipboardService(device_id=self.config.get("device_id"))
        self.clipboard.initialize()
        self.stream = StreamReceiver(device_id=self.config.get("device_id"))

        self.conn_mgr = ConnectionManager(
            config_manager=self.config,
            clipboard_service=self.clipboard,
            stream_receiver=self.stream
        )
        self.conn_mgr.start()
        time.sleep(0.5)

    def tearDown(self):
        self.conn_mgr.stop()
        if self.test_config_path.exists():
            self.test_config_path.unlink()
        time.sleep(0.3)

    def test_full_communication_lifecycle(self):
        received_remote_texts = []
        received_remote_images = []
        received_frames = []
        status_updates = []

        self.clipboard.remote_clip_applied.connect(lambda item: (
            received_remote_texts.append(item.content) if item.type == "text" else received_remote_images.append(item.content)
        ))
        self.stream.frame_received.connect(lambda img, stats: received_frames.append((img, stats)))
        self.conn_mgr.device_status_updated.connect(lambda st: status_updates.append(st))

        # Create a test PNG image in base64
        pil_img = Image.new('RGB', (100, 100), color=(100, 150, 200))
        buffer = BytesIO()
        pil_img.save(buffer, format='PNG')
        test_png_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        async def simulated_android_client():
            uri = f"ws://127.0.0.1:{self.conn_mgr.ws_port}"
            async with websockets.connect(uri) as ws:
                # 1. Pairing handshake with PIN
                pin = self.conn_mgr.current_pairing_pin
                pair_req = create_message(
                    MessageType.PAIR_REQUEST,
                    {"pin": pin, "device_name": "Galaxy Test Phone", "model": "SM-S911B"},
                    source_id="android-test-uuid"
                )
                await ws.send(serialize_message(pair_req))

                resp_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                resp = deserialize_message(resp_raw)
                self.assertIsNotNone(resp)
                self.assertEqual(resp["type"], MessageType.PAIR_RESPONSE)
                self.assertEqual(resp["payload"]["status"], "accepted")

                auth_token = resp["payload"]["auth_token"]
                self.assertTrue(len(auth_token) > 10)

                # 2. Send Device Status (Battery, Wi-Fi)
                status_msg = create_message(
                    MessageType.DEVICE_STATUS,
                    {"battery_level": 88, "is_charging": True, "wifi_ssid": "MinhaRede-5G"},
                    source_id="android-test-uuid"
                )
                await ws.send(serialize_message(status_msg))
                await asyncio.sleep(0.2)

                # 3. Send Text Clipboard from Phone to Linux
                text_msg = create_message(
                    MessageType.CLIPBOARD_TEXT,
                    {"content": "Texto copiado no Android!"},
                    source_id="android-test-uuid"
                )
                await ws.send(serialize_message(text_msg))
                await asyncio.sleep(0.2)

                # 4. Send Image Clipboard from Phone to Linux
                img_msg = create_message(
                    MessageType.CLIPBOARD_IMAGE,
                    {"format": "png", "data": test_png_b64},
                    source_id="android-test-uuid"
                )
                await ws.send(serialize_message(img_msg))
                await asyncio.sleep(0.2)

                # 5. Send Screen Mirror Frame from Phone to Linux
                frame_msg = create_message(
                    MessageType.STREAM_FRAME,
                    {"format": "png", "data": test_png_b64, "width": 100, "height": 100},
                    source_id="android-test-uuid"
                )
                await ws.send(serialize_message(frame_msg))
                await asyncio.sleep(0.2)

        # Run simulated client
        asyncio.run(simulated_android_client())

        # Process Qt events
        for _ in range(10):
            QCoreApplication.processEvents()
            time.sleep(0.05)

        # Assertions
        self.assertEqual(len(status_updates), 1)
        self.assertEqual(status_updates[0]["battery_level"], 88)
        self.assertEqual(status_updates[0]["is_charging"], True)
        self.assertEqual(status_updates[0]["wifi_ssid"], "MinhaRede-5G")

        self.assertIn("Texto copiado no Android!", received_remote_texts)
        self.assertEqual(len(received_remote_images), 1)
        self.assertEqual(len(received_frames), 1)
        self.assertEqual(received_frames[0][0].width(), 100)
        self.assertEqual(received_frames[0][0].height(), 100)


if __name__ == "__main__":
    unittest.main()
