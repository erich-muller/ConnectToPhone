import sys
import os
import glob

for site_pkg in glob.glob('/usr/lib*/python3*/site-packages'):
    if site_pkg not in sys.path:
        sys.path.append(site_pkg)

import unittest
import asyncio
import threading
import time
import base64
import json
import struct
import socket
from pathlib import Path
from io import BytesIO

from protocol.protocol_spec import (
    MessageType, create_message, serialize_message,
    deserialize_message, generate_auth_token
)
from desktop.core.config_manager import ConfigManager
from desktop.core.clipboard_service import ClipboardService
from desktop.core.stream_receiver import StreamReceiver
from desktop.core.connection_manager import ConnectionManager, ConnectionState
from desktop.core.qr_generator import QRCode, generate_qr_svg


class SimpleAsyncWebSocketClient:
    """Lightweight test client for RFC 6455."""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.writer.write(req.encode('ascii'))
        await self.writer.drain()

        # Read handshake response
        while True:
            line = await self.reader.readline()
            if line in (b'\r\n', b'\n', b''):
                break

    async def send(self, message: str):
        payload = message.encode('utf-8')
        length = len(payload)
        header = bytearray([0x81])  # FIN + Text

        mask_key = b"\x12\x34\x56\x78"
        if length <= 125:
            header.append(length | 0x80)
        elif length <= 65535:
            header.append(126 | 0x80)
            header.extend(struct.pack('>H', length))
        else:
            header.append(127 | 0x80)
            header.extend(struct.pack('>Q', length))

        header.extend(mask_key)
        masked_payload = bytearray(length)
        for i in range(length):
            masked_payload[i] = payload[i] ^ mask_key[i % 4]

        self.writer.write(header + masked_payload)
        await self.writer.drain()

    async def recv(self, timeout: float = 2.0) -> str:
        async def _recv_internal():
            head = await self.reader.readexactly(2)
            b1, b2 = head[0], head[1]
            payload_len = b2 & 0x7F
            if payload_len == 126:
                ext = await self.reader.readexactly(2)
                payload_len = struct.unpack('>H', ext)[0]
            elif payload_len == 127:
                ext = await self.reader.readexactly(8)
                payload_len = struct.unpack('>Q', ext)[0]

            data = await self.reader.readexactly(payload_len)
            return data.decode('utf-8', errors='replace')

        return await asyncio.wait_for(_recv_internal(), timeout=timeout)

    async def close(self):
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass


class TestConnectToPhoneE2E(unittest.TestCase):
    def setUp(self):
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
        time.sleep(0.4)

    def tearDown(self):
        self.conn_mgr.stop()
        self.clipboard.shutdown()
        if self.test_config_path.exists():
            self.test_config_path.unlink()
        time.sleep(0.2)

    def test_qr_generation(self):
        payload = '{"id":"test-uuid","name":"Fedora PC","ip":"192.168.1.100","port":42100,"pin":"123456"}'
        qr = QRCode(payload)
        self.assertGreater(qr.size, 20)
        svg = generate_qr_svg(payload)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("viewBox", svg)

    def test_full_communication_lifecycle(self):
        received_remote_texts = []
        received_remote_images = []
        received_frames = []
        status_updates = []

        self.clipboard.add_listener("remote_applied", lambda item: (
            received_remote_texts.append(item.content) if item.type == "text" else received_remote_images.append(item.content)
        ))
        self.stream.frame_received.connect(lambda img, stats: received_frames.append((img, stats)))
        self.conn_mgr.device_status_updated.connect(lambda st: status_updates.append(st))

        # Sample 100x100 red PNG in base64
        test_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAAAPklEQVR42u3BAQ0AAADCoPdPbQ43oAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD4Gj4QAAFFT6Z6AAAAAElFTkSuQmCC"

        async def simulated_android_client():
            client = SimpleAsyncWebSocketClient("127.0.0.1", self.conn_mgr.ws_port)
            await client.connect()

            # 1. Pairing handshake with PIN
            pin = self.conn_mgr.current_pairing_pin
            pair_req = create_message(
                MessageType.PAIR_REQUEST,
                {"pin": pin, "device_name": "Galaxy Test Phone", "model": "SM-S911B"},
                source_id="android-test-uuid"
            )
            await client.send(serialize_message(pair_req))

            resp_raw = await client.recv(timeout=2.0)
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
            await client.send(serialize_message(status_msg))
            await asyncio.sleep(0.1)

            # 3. Send Text Clipboard from Phone to Linux
            text_msg = create_message(
                MessageType.CLIPBOARD_TEXT,
                {"content": "Texto copiado no Android!"},
                source_id="android-test-uuid"
            )
            await client.send(serialize_message(text_msg))
            await asyncio.sleep(0.1)

            # 4. Send Image Clipboard from Phone to Linux
            img_msg = create_message(
                MessageType.CLIPBOARD_IMAGE,
                {"format": "png", "data": test_png_b64},
                source_id="android-test-uuid"
            )
            await client.send(serialize_message(img_msg))
            await asyncio.sleep(0.1)

            # 5. Send Screen Mirror Frame from Phone to Linux
            frame_msg = create_message(
                MessageType.STREAM_FRAME,
                {"format": "png", "data": test_png_b64, "width": 100, "height": 100},
                source_id="android-test-uuid"
            )
            await client.send(serialize_message(frame_msg))
            await asyncio.sleep(0.1)

            await client.close()

        asyncio.run(simulated_android_client())

        # Assertions
        self.assertEqual(len(status_updates), 1)
        self.assertEqual(status_updates[0]["battery_level"], 88)
        self.assertEqual(status_updates[0]["is_charging"], True)
        self.assertEqual(status_updates[0]["wifi_ssid"], "MinhaRede-5G")

        self.assertIn("Texto copiado no Android!", received_remote_texts)
        self.assertEqual(len(received_remote_images), 1)
        self.assertEqual(len(received_frames), 1)


if __name__ == "__main__":
    unittest.main()
