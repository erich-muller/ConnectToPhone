"""
UDP Local Network Discovery service for ConnectToPhone.
Enables zero-configuration pairing and auto-detection of Android phones and Linux PC on LAN.
"""

import socket
import json
import threading
import time
from typing import Callable, List, Optional, Dict, Any
from protocol.protocol_spec import (
    DEFAULT_DISCOVERY_PORT, DEFAULT_WS_PORT,
    MessageType, create_message, deserialize_message, serialize_message
)

def get_local_ip() -> str:
    """Find primary local LAN IPv4 address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't actually send data, just connects to determine routing interface
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def get_all_local_ips() -> List[str]:
    """Get all non-loopback local IPv4 addresses."""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.') and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    primary = get_local_ip()
    if primary not in ips and not primary.startswith('127.'):
        ips.insert(0, primary)
    return ips if ips else ['127.0.0.1']


class DiscoveryService:
    def __init__(
        self,
        device_id: str,
        device_name: str,
        ws_port: int = DEFAULT_WS_PORT,
        discovery_port: int = DEFAULT_DISCOVERY_PORT,
        on_device_discovered: Optional[Callable[[Dict[str, Any], str], None]] = None
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.ws_port = ws_port
        self.discovery_port = discovery_port
        self.on_device_discovered = on_device_discovered

        self._running = False
        self._listener_thread: Optional[threading.Thread] = None
        self._beacon_thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self):
        """Start UDP listener and periodic announcement beacon."""
        if self._running:
            return
        self._running = True

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._sock.bind(('', self.discovery_port))
            self._sock.settimeout(1.0)
        except Exception as e:
            print(f"[Discovery] Socket bind error on port {self.discovery_port}: {e}")
            self._running = False
            return

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True, name="DiscoveryListener")
        self._listener_thread.start()

        self._beacon_thread = threading.Thread(target=self._beacon_loop, daemon=True, name="DiscoveryBeacon")
        self._beacon_thread.start()
        print(f"[Discovery] Service started on port {self.discovery_port}")

    def stop(self):
        """Stop discovery service."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=1.0)
        if self._beacon_thread and self._beacon_thread.is_alive():
            self._beacon_thread.join(timeout=1.0)
        print("[Discovery] Service stopped")

    def broadcast_beacon(self):
        """Broadcast a single announcement packet to the local subnet."""
        if not self._sock or not self._running:
            return
        msg = create_message(
            MessageType.DISCOVERY_BEACON,
            {
                "device_name": self.device_name,
                "platform": "linux",
                "ws_port": self.ws_port,
                "local_ips": get_all_local_ips()
            },
            source_id=self.device_id
        )
        data = serialize_message(msg).encode('utf-8')
        try:
            self._sock.sendto(data, ('<broadcast>', self.discovery_port))
        except Exception as e:
            # Broadcast might fail if network is not up yet
            pass

    def _listen_loop(self):
        while self._running and self._sock:
            try:
                data, addr = self._sock.recvfrom(4096)
                sender_ip = addr[0]
                text = data.decode('utf-8', errors='ignore')
                msg = deserialize_message(text)
                if not msg:
                    continue

                source_id = msg.get("source_id")
                # Ignore messages from ourselves
                if source_id == self.device_id:
                    continue

                msg_type = msg.get("type")
                if msg_type in (MessageType.DISCOVERY_BEACON, MessageType.DISCOVERY_SEARCH):
                    payload = msg.get("payload", {})
                    payload["sender_ip"] = sender_ip
                    if self.on_device_discovered:
                        self.on_device_discovered(msg, sender_ip)

                    # If it was a search request from a phone, respond immediately with our beacon
                    if msg_type == MessageType.DISCOVERY_SEARCH:
                        self.broadcast_beacon()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    time.sleep(0.5)

    def _beacon_loop(self):
        while self._running:
            self.broadcast_beacon()
            # Broadcast every 3 seconds for fast detection
            for _ in range(30):
                if not self._running:
                    break
                time.sleep(0.1)
