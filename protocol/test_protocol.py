import unittest
from protocol.protocol_spec import (
    MessageType, create_message, serialize_message,
    deserialize_message, generate_device_id, generate_pairing_pin,
    generate_auth_token
)
from protocol.crypto_utils import (
    compute_token_hash, verify_token,
    create_qr_pairing_payload, parse_qr_pairing_payload
)

class TestProtocol(unittest.TestCase):
    def test_message_creation_and_serialization(self):
        msg = create_message(
            MessageType.CLIPBOARD_TEXT,
            {"content": "Olá do Linux!"},
            source_id="test-device-123"
        )
        self.assertEqual(msg["type"], MessageType.CLIPBOARD_TEXT)
        self.assertEqual(msg["payload"]["content"], "Olá do Linux!")
        
        serialized = serialize_message(msg)
        self.assertIsInstance(serialized, str)
        
        parsed = deserialize_message(serialized)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["type"], MessageType.CLIPBOARD_TEXT)
        self.assertEqual(parsed["payload"]["content"], "Olá do Linux!")

    def test_qr_pairing_payload(self):
        payload_str = create_qr_pairing_payload("pc-123", "Meu PC", "192.168.1.100", 42100, "123456")
        parsed = parse_qr_pairing_payload(payload_str)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["id"], "pc-123")
        self.assertEqual(parsed["ip"], "192.168.1.100")
        self.assertEqual(parsed["port"], 42100)
        self.assertEqual(parsed["pin"], "123456")

    def test_token_verification(self):
        token = generate_auth_token()
        self.assertTrue(verify_token(token, token))
        self.assertFalse(verify_token(token, "wrong-token"))

if __name__ == "__main__":
    unittest.main()
