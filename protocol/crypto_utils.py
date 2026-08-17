"""
Cryptographic and pairing utilities for ConnectToPhone.
"""

import hmac
import hashlib
import json
import base64
from typing import Dict, Any, Optional

def compute_token_hash(token: str) -> str:
    """Compute SHA-256 hash of an auth token."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def verify_token(provided_token: str, expected_token: str) -> bool:
    """Constant-time token verification."""
    return hmac.compare_digest(
        compute_token_hash(provided_token),
        compute_token_hash(expected_token)
    )

def create_qr_pairing_payload(device_id: str, device_name: str, host_ip: str, port: int, pin: str) -> str:
    """
    Generate a compact JSON string to be encoded in a QR Code.
    When the Android app scans this, it has all info needed to connect and initiate pairing.
    """
    data = {
        "id": device_id,
        "name": device_name,
        "ip": host_ip,
        "port": port,
        "pin": pin
    }
    return json.dumps(data)

def parse_qr_pairing_payload(qr_text: str) -> Optional[Dict[str, Any]]:
    """Parse QR code payload."""
    try:
        data = json.loads(qr_text)
        if all(k in data for k in ("id", "ip", "port", "pin")):
            return data
    except Exception:
        pass
    return None
