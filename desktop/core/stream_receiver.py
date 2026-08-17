"""
Screen Mirroring Stream Receiver for ConnectToPhone Desktop.
Processes high-speed incoming video frames and manages touch/mouse/keyboard input relays.
"""

import base64
import time
from typing import Optional, Dict, Any, Tuple
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from protocol.protocol_spec import MessageType, create_message

class StreamReceiver(QObject):
    frame_received = pyqtSignal(QImage, dict) # (image, stats: {"fps": float, "resolution": str, "frame_num": int})
    stream_started = pyqtSignal()
    stream_stopped = pyqtSignal(str) # reason

    def __init__(self, device_id: str):
        super().__init__()
        self.device_id = device_id
        self._is_active = False
        self._frame_count = 0
        self._fps = 0.0
        self._last_fps_calc_time = time.time()
        self._frames_since_calc = 0
        self._current_width = 0
        self._current_height = 0

    @property
    def is_active(self) -> bool:
        return self._is_active

    def on_stream_start_response(self, payload: Dict[str, Any]):
        """Called when Android acknowledges screen mirror start."""
        self._is_active = True
        self._frame_count = 0
        self._frames_since_calc = 0
        self._last_fps_calc_time = time.time()
        self.stream_started.emit()
        print("[Stream] Screen stream started from Android")

    def on_stream_stop(self, reason: str = "User stopped"):
        """Called when stream terminates."""
        self._is_active = False
        self.stream_stopped.emit(reason)
        print(f"[Stream] Screen stream stopped: {reason}")

    def handle_frame_data(self, payload: Dict[str, Any]):
        """Decode incoming frame payload into QImage."""
        if not self._is_active:
            self._is_active = True
            self.stream_started.emit()

        data_b64 = payload.get("data")
        if not data_b64:
            return

        try:
            raw_bytes = base64.b64decode(data_b64)
            qimage = QImage.fromData(raw_bytes)
            if qimage.isNull():
                return

            self._frame_count += 1
            self._frames_since_calc += 1
            self._current_width = qimage.width()
            self._current_height = qimage.height()

            now = time.time()
            dt = now - self._last_fps_calc_time
            if dt >= 1.0:
                self._fps = round(self._frames_since_calc / dt, 1)
                self._frames_since_calc = 0
                self._last_fps_calc_time = now

            stats = {
                "fps": self._fps,
                "resolution": f"{self._current_width}x{self._current_height}",
                "frame_num": self._frame_count,
                "timestamp": payload.get("timestamp", 0)
            }

            self.frame_received.emit(qimage, stats)
        except Exception as e:
            print(f"[Stream] Error processing frame: {e}")

    def create_tap_message(self, norm_x: float, norm_y: float, duration_ms: int = 50) -> Dict[str, Any]:
        """Creates a normalized tap event (0.0 to 1.0)."""
        return create_message(
            MessageType.INPUT_TOUCH,
            {
                "action": "TAP",
                "x": max(0.0, min(1.0, norm_x)),
                "y": max(0.0, min(1.0, norm_y)),
                "duration": duration_ms
            },
            source_id=self.device_id
        )

    def create_swipe_message(self, start_x: float, start_y: float, end_x: float, end_y: float, duration_ms: int = 200) -> Dict[str, Any]:
        """Creates a normalized swipe/drag event."""
        return create_message(
            MessageType.INPUT_TOUCH,
            {
                "action": "SWIPE",
                "start_x": max(0.0, min(1.0, start_x)),
                "start_y": max(0.0, min(1.0, start_y)),
                "end_x": max(0.0, min(1.0, end_x)),
                "end_y": max(0.0, min(1.0, end_y)),
                "duration": duration_ms
            },
            source_id=self.device_id
        )

    def create_touch_message(self, action: str, normalized_x: float, normalized_y: float) -> Dict[str, Any]:
        """Creates a generic touch event."""
        return create_message(
            MessageType.INPUT_TOUCH,
            {
                "action": action,
                "x": max(0.0, min(1.0, normalized_x)),
                "y": max(0.0, min(1.0, normalized_y))
            },
            source_id=self.device_id
        )

    def create_key_message(self, key_code: str) -> Dict[str, Any]:
        """
        Creates a key event message (e.g. 'BACK', 'HOME', 'RECENTS', 'ENTER').
        """
        return create_message(
            MessageType.INPUT_KEY,
            {"key": key_code},
            source_id=self.device_id
        )
