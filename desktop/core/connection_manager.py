"""
Async WebSocket Connection Manager & Network Engine for ConnectToPhone Desktop.
Handles server socket, client connections, authentication, heartbeat keep-alive,
and message routing to clipboard and stream services.
Uses thread-safe EventSignal for zero-latency communication with GTK4/Libadwaita.
"""

import asyncio
import threading
import json
import time
from typing import Optional, Dict, Any, Callable, Set, List

from protocol.protocol_spec import (
    MessageType, DEFAULT_WS_PORT, create_message,
    serialize_message, deserialize_message, generate_auth_token,
    generate_pairing_pin
)
from protocol.crypto_utils import verify_token
from desktop.core.config_manager import ConfigManager
from desktop.core.clipboard_service import ClipboardService
from desktop.core.stream_receiver import StreamReceiver
from desktop.core.discovery import DiscoveryService, get_local_ip
from desktop.core.ws_server import serve_ws, WebSocketClientConnection
from desktop.core.signals import EventSignal


class ConnectionState:
    DISCONNECTED = "DISCONNECTED"
    LISTENING = "LISTENING"
    CONNECTING = "CONNECTING"
    PAIRING = "PAIRING"
    CONNECTED = "CONNECTED"


class ConnectionManager:
    def __init__(self, config_manager: ConfigManager, clipboard_service: ClipboardService, stream_receiver: StreamReceiver):
        self.state_changed = EventSignal()
        self.device_status_updated = EventSignal()
        self.pairing_requested = EventSignal()
        self.paired_success = EventSignal()
        self.notification_requested = EventSignal()

        self.config = config_manager
        self.clipboard = clipboard_service
        self.stream = stream_receiver

        self.device_id = self.config.get("device_id")
        self.device_name = self.config.get("device_name")
        self.ws_port = self.config.get("ws_port", DEFAULT_WS_PORT)

        self._active_ws = None
        self._connected_device_info: Dict[str, Any] = {}
        self._state = ConnectionState.DISCONNECTED

        self._current_pairing_pin: str = ""
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._running = False

        # Hook clipboard listeners
        self.clipboard.add_listener("local_text", self.send_clipboard_text)
        self.clipboard.add_listener("local_image", self.send_clipboard_image)

        # Discovery service
        self.discovery = DiscoveryService(
            device_id=self.device_id,
            device_name=self.device_name,
            ws_port=self.ws_port,
            on_device_discovered=self._on_device_discovered_lan
        )
        self._sync_discovery_targets()

    def _sync_discovery_targets(self):
        """Register all known paired devices' last IPs to receive targeted beacons."""
        paired = self.config.get_all_paired_devices()
        ips = [info.get("last_ip") for info in paired.values() if info.get("last_ip")]
        self.discovery.set_target_ips(ips)

    @property
    def state(self) -> str:
        return self._state

    @property
    def connected_device(self) -> Dict[str, Any]:
        return self._connected_device_info

    @property
    def current_pairing_pin(self) -> str:
        if not self._current_pairing_pin:
            self._current_pairing_pin = generate_pairing_pin()
        return self._current_pairing_pin

    def generate_new_pin(self) -> str:
        self._current_pairing_pin = generate_pairing_pin()
        return self._current_pairing_pin

    def _set_state(self, new_state: str, details: str = ""):
        self._state = new_state
        print(f"[Connection] State: {new_state} ({details})")
        self.state_changed.emit(new_state, details)

    def trigger_discovery(self):
        """Immediately ping local subnet and paired device IPs to wake up the phone."""
        self._sync_discovery_targets()
        self.discovery.trigger_burst(count=3, delay_sec=0.2)
        print("[Connection] Discovery burst triggered for paired phones")

    def disconnect_current_device(self):
        """Gracefully disconnect currently connected device."""
        if self._active_ws and self._loop:
            asyncio.run_coroutine_threadsafe(self._active_ws.close(1000, "Desconectado pelo usuário"), self._loop)

    def start(self):
        if self._running:
            return
        self._running = True
        self._sync_discovery_targets()
        self.discovery.start()

        self._thread = threading.Thread(target=self._run_event_loop, daemon=True, name="ConnectToPhoneNet")
        self._thread.start()

    def stop(self):
        self._running = False
        self.discovery.stop()

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._set_state(ConnectionState.DISCONNECTED, "Stopped")

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_async_loop())
        except Exception as e:
            print(f"[Connection] Net thread loop exception: {e}")

    async def _main_async_loop(self):
        try:
            self._server = await serve_ws(self._handle_client_connection, "0.0.0.0", self.ws_port)
            self._set_state(ConnectionState.LISTENING, f"Porta {self.ws_port}")
            print(f"[Connection] WebSocket server listening on 0.0.0.0:{self.ws_port}")
        except Exception as e:
            print(f"[Connection] ❌ Erro ao iniciar servidor WebSocket na porta {self.ws_port}: {e}")
            self._set_state(ConnectionState.DISCONNECTED, f"Falha ao iniciar: {e}")
            return

        while self._running:
            await asyncio.sleep(2)
            if self._active_ws and self._state == ConnectionState.CONNECTED:
                try:
                    msg = create_message(MessageType.PING, source_id=self.device_id)
                    await self._send_raw_async(serialize_message(msg))
                except Exception:
                    pass

    async def _handle_client_connection(self, websocket):
        client_ip = websocket.remote_address[0] if isinstance(websocket.remote_address, tuple) else str(websocket.remote_address)
        print(f"[Connection] 📱 Nova conexão de cliente recebida de {client_ip}")

        if self._active_ws is not None and self._active_ws != websocket:
            try:
                await self._active_ws.close()
            except Exception:
                pass

        self._active_ws = websocket
        authenticated = False
        device_id = ""
        device_name = "Dispositivo Android"

        try:
            async for raw_message in websocket:
                if isinstance(raw_message, bytes):
                    pass
                else:
                    msg = deserialize_message(raw_message)
                    if not msg:
                        continue

                    msg_type = msg.get("type")
                    source_id = msg.get("source_id", "")
                    payload = msg.get("payload", {})

                    if msg_type == MessageType.AUTH_CONNECT:
                        token = payload.get("auth_token", "")
                        dev_name = payload.get("device_name", "Android")
                        paired_info = self.config.get_paired_device(source_id)
                        print(f"[Connection] 🔐 Pedido de autenticação automática de '{dev_name}' ({client_ip}, id={source_id})")

                        if paired_info and verify_token(token, paired_info.get("auth_token", "")):
                            print(f"[Connection] ✅ Token de autenticação válido! Conexão aceita.")
                            authenticated = True
                            device_id = source_id
                            device_name = dev_name
                            self._connected_device_info = {
                                "id": device_id,
                                "name": device_name,
                                "ip": client_ip,
                                "model": payload.get("model", "Android Device"),
                                "android_version": payload.get("android_version", "")
                            }
                            self.config.add_paired_device(device_id, device_name, token, client_ip)
                            self.discovery.add_target_ip(client_ip)
                            resp = create_message(MessageType.AUTH_RESPONSE, {"status": "accepted", "device_name": self.device_name}, source_id=self.device_id)
                            await websocket.send(serialize_message(resp))
                            self._set_state(ConnectionState.CONNECTED, f"Conectado a {device_name}")
                            self.notification_requested.emit("Celular Conectado", f"{device_name} conectado automaticamente na rede local.")
                        else:
                            print(f"[Connection] ❌ Token de autenticação inválido.")
                            resp = create_message(MessageType.AUTH_RESPONSE, {"status": "rejected", "reason": "invalid_token"}, source_id=self.device_id)
                            await websocket.send(serialize_message(resp))
                            await websocket.close(1008, "Token de autenticação inválido")
                            break

                    elif msg_type == MessageType.PAIR_REQUEST:
                        pin = payload.get("pin", "")
                        dev_name = payload.get("device_name", "Android")
                        device_id = source_id
                        print(f"[Connection] 🔑 Pedido de Pareamento de '{dev_name}' com PIN='{pin}' (PIN esperado='{self._current_pairing_pin}')")

                        if pin == self._current_pairing_pin:
                            print(f"[Connection] ✅ PIN correto! Pareamento aceito com sucesso.")
                            new_token = generate_auth_token()
                            self.config.add_paired_device(device_id, dev_name, new_token, client_ip)
                            self.discovery.add_target_ip(client_ip)
                            authenticated = True
                            device_name = dev_name
                            self._connected_device_info = {
                                "id": device_id,
                                "name": device_name,
                                "ip": client_ip,
                                "model": payload.get("model", "Android Device")
                            }
                            resp = create_message(
                                MessageType.PAIR_RESPONSE,
                                {"status": "accepted", "auth_token": new_token, "device_name": self.device_name},
                                source_id=self.device_id
                            )
                            await websocket.send(serialize_message(resp))
                            self._set_state(ConnectionState.CONNECTED, f"Pareado com {device_name}")
                            self.paired_success.emit(device_id, device_name)
                            self.notification_requested.emit("Pareamento Concluído", f"Dispositivo {device_name} pareado com sucesso!")
                        else:
                            print(f"[Connection] ❌ PIN incorreto! Recebido: '{pin}', Esperado: '{self._current_pairing_pin}'")
                            resp = create_message(
                                MessageType.PAIR_RESPONSE,
                                {"status": "rejected", "reason": "invalid_pin"},
                                source_id=self.device_id
                            )
                            await websocket.send(serialize_message(resp))
                            await websocket.close(1008, "PIN de pareamento incorreto")
                            break

                    elif authenticated:
                        self._handle_authenticated_message(msg_type, payload, source_id)

        except Exception as e:
            print(f"[Connection] Connection disconnected from {client_ip}: {e}")
        finally:
            if self._active_ws == websocket:
                self._active_ws = None
                self._connected_device_info = {}
                self.stream.on_stream_stop("Conexão perdida")
                self._set_state(ConnectionState.LISTENING, "Aguardando celular na rede local")
                self.notification_requested.emit("Celular Desconectado", f"{device_name} foi desconectado.")

    def _handle_authenticated_message(self, msg_type: str, payload: Dict[str, Any], source_id: str):
        if msg_type == MessageType.PING:
            self.send_message(create_message(MessageType.PONG, source_id=self.device_id))
        elif msg_type == MessageType.PONG:
            pass
        elif msg_type == MessageType.DEVICE_STATUS:
            self.device_status_updated.emit(payload)
        elif msg_type == MessageType.CLIPBOARD_TEXT:
            text = payload.get("content", "")
            if text:
                self.clipboard.handle_remote_text(text, source_id)
                self.notification_requested.emit("Texto Copiado do Celular", text[:50] + ("..." if len(text) > 50 else ""))
        elif msg_type == MessageType.CLIPBOARD_IMAGE:
            img_b64 = payload.get("data", "")
            if img_b64:
                self.clipboard.handle_remote_image(img_b64, source_id)
                self.notification_requested.emit("Imagem Copiada do Celular", "Nova imagem inserida na área de transferência.")
        elif msg_type == MessageType.STREAM_START_RESP:
            self.stream.on_stream_start_response(payload)
        elif msg_type == MessageType.STREAM_FRAME:
            self.stream.handle_frame_data(payload)
        elif msg_type == MessageType.STREAM_STOP:
            self.stream.on_stream_stop(payload.get("reason", "Parado pelo celular"))

    def _on_device_discovered_lan(self, msg: Dict[str, Any], sender_ip: str):
        source_id = msg.get("source_id", "")
        payload = msg.get("payload", {})
        dev_name = payload.get("device_name", "Android Phone")

        paired = self.config.get_paired_device(source_id)
        if paired and self._state != ConnectionState.CONNECTED:
            print(f"[Discovery] Paired device {dev_name} ({sender_ip}) detected on LAN")

    def send_message(self, msg: Dict[str, Any]):
        if not self._loop or not self._active_ws or not self._running:
            return
        serialized = serialize_message(msg)
        asyncio.run_coroutine_threadsafe(self._send_raw_async(serialized), self._loop)

    async def _send_raw_async(self, data: str):
        if self._active_ws:
            try:
                await self._active_ws.send(data)
            except Exception as e:
                print(f"[Connection] Send error: {e}")

    def send_clipboard_text(self, text: str):
        if self._state == ConnectionState.CONNECTED:
            msg = create_message(MessageType.CLIPBOARD_TEXT, {"content": text}, source_id=self.device_id)
            self.send_message(msg)

    def send_clipboard_image(self, b64_png: str):
        if self._state == ConnectionState.CONNECTED:
            msg = create_message(MessageType.CLIPBOARD_IMAGE, {"format": "png", "data": b64_png}, source_id=self.device_id)
            self.send_message(msg)

    def request_start_screen_mirror(self, width: int = 720, height: int = 1280, fps: int = 30, bitrate: int = 3000000):
        if self._state == ConnectionState.CONNECTED:
            msg = create_message(
                MessageType.STREAM_START_REQ,
                {
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "bitrate": bitrate
                },
                source_id=self.device_id
            )
            self.send_message(msg)

    def request_stop_screen_mirror(self):
        if self._state == ConnectionState.CONNECTED:
            msg = create_message(MessageType.STREAM_STOP, source_id=self.device_id)
            self.send_message(msg)
            self.stream.on_stream_stop("Parado pelo usuário no Linux")

    def send_tap_event(self, norm_x: float, norm_y: float, duration_ms: int = 50):
        if self._state == ConnectionState.CONNECTED:
            msg = self.stream.create_tap_message(norm_x, norm_y, duration_ms)
            self.send_message(msg)

    def send_swipe_event(self, start_x: float, start_y: float, end_x: float, end_y: float, duration_ms: int = 200):
        if self._state == ConnectionState.CONNECTED:
            msg = self.stream.create_swipe_message(start_x, start_y, end_x, end_y, duration_ms)
            self.send_message(msg)

    def send_touch_event(self, action: str, norm_x: float, norm_y: float):
        if self._state == ConnectionState.CONNECTED:
            msg = self.stream.create_touch_message(action, norm_x, norm_y)
            self.send_message(msg)

    def send_key_event(self, key_code: str):
        if self._state == ConnectionState.CONNECTED:
            msg = self.stream.create_key_message(key_code)
            self.send_message(msg)
