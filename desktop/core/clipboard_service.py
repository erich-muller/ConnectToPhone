"""
Clipboard Synchronization Service for ConnectToPhone Linux Desktop.
Monitors system clipboard for Text and Images and synchronizes bidirectionally with Android.
Uses Qt Signals/Slots to guarantee all clipboard mutations execute safely on the GUI Main Thread.
"""

import base64
import hashlib
import time
from typing import Optional, List, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QBuffer, QIODevice, Qt
from PyQt6.QtGui import QClipboard, QImage, QPixmap
from PyQt6.QtWidgets import QApplication

class ClipboardItem:
    def __init__(self, item_type: str, content: Any, source: str, timestamp: float, preview: str = "", raw_image: Optional[QImage] = None):
        self.type = item_type # 'text' or 'image'
        self.content = content # str or base64 str
        self.source = source # 'local' or 'remote'
        self.timestamp = timestamp
        self.preview = preview
        self.raw_image = raw_image

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "preview": self.preview,
            "source": self.source,
            "timestamp": self.timestamp,
            "content": self.content if self.type == "text" else "[Imagem]"
        }


class ClipboardService(QObject):
    # Signals for UI and networking
    local_text_copied = pyqtSignal(str) # Sent to phone
    local_image_copied = pyqtSignal(str) # Base64 PNG sent to phone
    remote_clip_applied = pyqtSignal(object) # ClipboardItem
    history_changed = pyqtSignal(list)

    # Internal cross-thread invocation signals (guaranteed to execute on Qt Main GUI Thread)
    _apply_remote_text_sig = pyqtSignal(str, str)
    _apply_remote_image_sig = pyqtSignal(str, str)

    def __init__(self, device_id: str, max_history: int = 30):
        super().__init__()
        self.device_id = device_id
        self.max_history = max_history
        self._history: List[ClipboardItem] = []
        self._last_content_hash: str = ""
        self._ignore_until: float = 0.0
        self._enabled = True
        self._sync_images = True

        self._clipboard: Optional[QClipboard] = None

        # Connect internal cross-thread signals to main-thread slots
        self._apply_remote_text_sig.connect(self._do_apply_remote_text, Qt.ConnectionType.QueuedConnection)
        self._apply_remote_image_sig.connect(self._do_apply_remote_image, Qt.ConnectionType.QueuedConnection)

    def initialize(self):
        """Bind to Qt Application clipboard."""
        app = QApplication.instance()
        if app:
            self._clipboard = app.clipboard()
            if self._clipboard:
                self._clipboard.dataChanged.connect(self._on_clipboard_data_changed)
                print("[Clipboard] Service hooked into system clipboard")

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def set_sync_images(self, sync_images: bool):
        self._sync_images = sync_images

    def get_history(self) -> List[ClipboardItem]:
        return list(self._history)

    def _add_to_history(self, item: ClipboardItem):
        self._history.insert(0, item)
        if len(self._history) > self.max_history:
            self._history.pop()
        self.history_changed.emit(self._history)

    def _compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _on_clipboard_data_changed(self):
        if not self._enabled or not self._clipboard:
            return

        # Check if change is an echo of recent remote apply
        if time.time() < self._ignore_until:
            return

        mime = self._clipboard.mimeData()
        if not mime:
            return

        # Check for image first
        if self._sync_images and (mime.hasImage() or not self._clipboard.image().isNull()):
            qimg = self._clipboard.image()
            if not qimg.isNull():
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                qimg.save(buffer, "PNG")
                png_bytes = bytes(buffer.data())
                buffer.close()

                img_hash = self._compute_hash(png_bytes)
                if img_hash == self._last_content_hash:
                    return
                self._last_content_hash = img_hash

                b64_str = base64.b64encode(png_bytes).decode('utf-8')
                preview = f"Imagem ({qimg.width()}x{qimg.height()})"
                item = ClipboardItem(
                    item_type="image",
                    content=b64_str,
                    source="local",
                    timestamp=time.time(),
                    preview=preview,
                    raw_image=qimg
                )
                self._add_to_history(item)
                self.local_image_copied.emit(b64_str)
                print(f"[Clipboard] Local image copied ({qimg.width()}x{qimg.height()}), notifying phone")
                return

        # Check for text
        if mime.hasText():
            text = self._clipboard.text()
            if not text:
                return

            text_bytes = text.encode('utf-8')
            text_hash = self._compute_hash(text_bytes)
            if text_hash == self._last_content_hash:
                return
            self._last_content_hash = text_hash

            preview = text[:60] + ("..." if len(text) > 60 else "")
            item = ClipboardItem(
                item_type="text",
                content=text,
                source="local",
                timestamp=time.time(),
                preview=preview
            )
            self._add_to_history(item)
            self.local_text_copied.emit(text)
            print(f"[Clipboard] Local text copied: {preview!r}, notifying phone")

    def handle_remote_text(self, text: str, source_id: str):
        """Thread-safe entry point: dispatches to GUI main thread."""
        self._apply_remote_text_sig.emit(text, source_id)

    def handle_remote_image(self, b64_data: str, source_id: str):
        """Thread-safe entry point: dispatches to GUI main thread."""
        self._apply_remote_image_sig.emit(b64_data, source_id)

    @pyqtSlot(str, str)
    def _do_apply_remote_text(self, text: str, source_id: str):
        """Executed strictly on Qt Main GUI Thread."""
        if not self._enabled or not self._clipboard or not text:
            return

        text_bytes = text.encode('utf-8')
        text_hash = self._compute_hash(text_bytes)
        if text_hash == self._last_content_hash:
            return

        self._last_content_hash = text_hash
        self._ignore_until = time.time() + 1.0  # Ignore local echo for 1 second

        # Apply to both Standard Clipboard (Ctrl+V) and Selection (Middle Click) on Linux
        self._clipboard.setText(text, QClipboard.Mode.Clipboard)
        try:
            self._clipboard.setText(text, QClipboard.Mode.Selection)
        except Exception:
            pass

        preview = text[:60] + ("..." if len(text) > 60 else "")
        item = ClipboardItem(
            item_type="text",
            content=text,
            source="remote",
            timestamp=time.time(),
            preview=preview
        )
        self._add_to_history(item)
        self.remote_clip_applied.emit(item)
        print(f"[Clipboard] Remote text automatically applied to Linux clipboard: {preview!r}")

    @pyqtSlot(str, str)
    def _do_apply_remote_image(self, b64_data: str, source_id: str):
        """Executed strictly on Qt Main GUI Thread."""
        if not self._enabled or not self._sync_images or not self._clipboard or not b64_data:
            return

        try:
            raw_bytes = base64.b64decode(b64_data)
            img_hash = self._compute_hash(raw_bytes)
            if img_hash == self._last_content_hash:
                return

            self._last_content_hash = img_hash
            qimg = QImage.fromData(raw_bytes)
            if not qimg.isNull():
                self._ignore_until = time.time() + 1.0  # Ignore local echo for 1 second
                
                # Apply image to Linux system clipboard
                self._clipboard.setImage(qimg, QClipboard.Mode.Clipboard)

                preview = f"Imagem ({qimg.width()}x{qimg.height()})"
                item = ClipboardItem(
                    item_type="image",
                    content=b64_data,
                    source="remote",
                    timestamp=time.time(),
                    preview=preview,
                    raw_image=qimg
                )
                self._add_to_history(item)
                self.remote_clip_applied.emit(item)
                print(f"[Clipboard] Remote image automatically applied to Linux clipboard ({qimg.width()}x{qimg.height()})")
        except Exception as e:
            print(f"[Clipboard] Error applying remote image on main thread: {e}")
