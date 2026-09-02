import unittest
from unittest.mock import MagicMock, patch
import base64

from desktop.core.clipboard_service import ClipboardService, ClipboardItem


class TestClipboardAndMirror(unittest.TestCase):
    def setUp(self):
        self.service = ClipboardService(device_id="test_pc")
        self.service._wl_paste_bin = "/usr/bin/wl-paste"
        self.service._enabled = True
        self.service._sync_images = True

    def test_image_screenshot_detection_prioritized(self):
        # Mock wl-paste --list-types returning image/png
        def mock_subprocess_run(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if "--list-types" in cmd:
                mock_res.returncode = 0
                mock_res.stdout = "image/png\nimage/jpeg\n"
            elif "--type" in cmd and "image/png" in cmd:
                mock_res.returncode = 0
                mock_res.stdout = b"\x89PNGFakeImageBytesForTesting1234567890" * 3
            elif "--type" in cmd and "text/plain" in cmd:
                mock_res.returncode = 1
                mock_res.stdout = b""
            return mock_res

        emitted_images = []
        self.service.add_listener("local_image", lambda b64: emitted_images.append(b64))

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            self.service._check_and_process_system_clipboard()

        self.assertEqual(len(emitted_images), 1)
        decoded = base64.b64decode(emitted_images[0])
        self.assertTrue(decoded.startswith(b"\x89PNGFakeImageBytesForTesting"))
        self.assertEqual(len(self.service.get_history()), 1)
        self.assertEqual(self.service.get_history()[0].type, "image")

    def test_text_copy_detection(self):
        # Mock wl-paste --list-types returning text/plain only
        def mock_subprocess_run(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if "--list-types" in cmd:
                mock_res.returncode = 0
                mock_res.stdout = "text/plain\nUTF8_STRING\n"
            elif "--type" in cmd and "text/plain" in cmd:
                mock_res.returncode = 0
                mock_res.stdout = b"Hello from Linux Ctrl+C"
            return mock_res

        emitted_texts = []
        self.service.add_listener("local_text", lambda txt: emitted_texts.append(txt))

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            self.service._check_and_process_system_clipboard()

        self.assertEqual(len(emitted_texts), 1)
        self.assertEqual(emitted_texts[0], "Hello from Linux Ctrl+C")
        self.assertEqual(len(self.service.get_history()), 1)
        self.assertEqual(self.service.get_history()[0].type, "text")


if __name__ == "__main__":
    unittest.main()

