"""
Screen Mirroring Stream Receiver for ConnectToPhone Desktop.
Processes high-speed incoming video frames and manages touch/mouse/keyboard input relays.
Uses thread-safe EventSignal for zero-latency frame dispatch directly to GTK4 / Libadwaita.
"""

import base64
import time
from typing import Optional, Dict, Any, Tuple

from protocol.protocol_spec import MessageType, create_message
from desktop.core.signals import EventSignal


class StreamReceiver:
    def __init__(self, device_id: str):
        self.frame_received = EventSignal()
        self.stream_started = EventSignal()
        self.stream_stopped = EventSignal()

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
        status = payload.get("status", "accepted")
        if status in ("accepted", "started"):
            self._is_active = True
            self._frame_count = 0
            self._frames_since_calc = 0
            self._last_fps_calc_time = time.time()
            self.stream_started.emit()
            print("[Stream] Screen stream started from Android")
        else:
            self._is_active = False
            self.stream_stopped.emit(f"Recusado pelo celular ({status})")
            print(f"[Stream] Screen stream start rejected: {status}")

    def on_stream_stop(self, reason: str = "User stopped"):
        self._is_active = False
        self.stream_stopped.emit(reason)
        print(f"[Stream] Screen stream stopped: {reason}")

    def handle_frame_data(self, payload: Dict[str, Any]):
        if not self._is_active:
            self._is_active = True
            self.stream_started.emit()

        data_b64 = payload.get("data")
        if not data_b64:
            return

        try:
            raw_bytes = base64.b64decode(data_b64)
            self._frame_count += 1
            self._frames_since_calc += 1

            w = payload.get("width", self._current_width)
            h = payload.get("height", self._current_height)
            self._current_width = w
            self._current_height = h

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

            # Emit raw JPEG bytes directly to UI listener
            self.frame_received.emit(raw_bytes, stats)
        except Exception as e:
            print(f"[Stream] Error processing frame: {e}")

    def create_tap_message(self, norm_x: float, norm_y: float, duration_ms: int = 50) -> Dict[str, Any]:
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
        return create_message(
            MessageType.INPUT_KEY,
            {"key": key_code},
            source_id=self.device_id
        )
