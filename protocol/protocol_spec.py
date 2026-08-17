"""
ConnectToPhone Protocol Specification
Defines the communication format, opcodes, and data models for communication
between Linux Desktop and Android Companion App over LAN.
"""

import json
import time
import uuid
import secrets
from typing import Dict, Any, Optional

DEFAULT_WS_PORT = 42100
DEFAULT_DISCOVERY_PORT = 42101
PROTOCOL_VERSION = "1.0"

class MessageType:
    # Discovery & Pairing
    DISCOVERY_BEACON = "DISCOVERY_BEACON"
    DISCOVERY_SEARCH = "DISCOVERY_SEARCH"
    PAIR_REQUEST = "PAIR_REQUEST"
    PAIR_RESPONSE = "PAIR_RESPONSE"
    AUTH_CONNECT = "AUTH_CONNECT"
    AUTH_RESPONSE = "AUTH_RESPONSE"
    
    # Keep-Alive & Status
    PING = "PING"
    PONG = "PONG"
    DEVICE_STATUS = "DEVICE_STATUS"
    
    # Clipboard
    CLIPBOARD_TEXT = "CLIPBOARD_TEXT"
    CLIPBOARD_IMAGE = "CLIPBOARD_IMAGE"
    CLIPBOARD_ACK = "CLIPBOARD_ACK"
    
    # Screen Mirroring
    STREAM_START_REQ = "STREAM_START_REQ"
    STREAM_START_RESP = "STREAM_START_RESP"
    STREAM_STOP = "STREAM_STOP"
    STREAM_FRAME = "STREAM_FRAME"
    
    # Input Relay
    INPUT_TOUCH = "INPUT_TOUCH"
    INPUT_KEY = "INPUT_KEY"


def create_message(msg_type: str, data: Optional[Dict[str, Any]] = None, source_id: str = "") -> Dict[str, Any]:
    """Create a standardized message dictionary."""
    msg = {
        "type": msg_type,
        "version": PROTOCOL_VERSION,
        "timestamp": int(time.time() * 1000),
        "source_id": source_id,
        "payload": data or {}
    }
    return msg


def serialize_message(msg: Dict[str, Any]) -> str:
    """Serialize a message to JSON string."""
    return json.dumps(msg, ensure_ascii=False)


def deserialize_message(raw_data: str) -> Optional[Dict[str, Any]]:
    """Parse JSON string to message dict."""
    try:
        data = json.loads(raw_data)
        if isinstance(data, dict) and "type" in data:
            return data
    except Exception:
        pass
    return None


def generate_device_id() -> str:
    """Generate a persistent unique device ID."""
    return str(uuid.uuid4())


def generate_pairing_pin() -> str:
    """Generate a 6-digit PIN code."""
    return f"{secrets.randbelow(1000000):06d}"


def generate_auth_token() -> str:
    """Generate a high-entropy secret authentication token."""
    return secrets.token_hex(32)
