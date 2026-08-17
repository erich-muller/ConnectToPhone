"""
Floating Screen Mirror Window for ConnectToPhone Desktop.
Provides real-time interactive screen streaming, aspect-ratio locked display,
direct touch / click / scroll / keyboard interaction, and clean immersive UI.
"""

import time
import math
from typing import Optional, Dict, Any, Tuple
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QKeyEvent, QMouseEvent, QWheelEvent, QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy
)

class VideoCanvas(QWidget):
    tap_occurred = pyqtSignal(float, float) # (norm_x, norm_y)
    swipe_occurred = pyqtSignal(float, float, float, float, int) # (start_x, start_y, end_x, end_y, duration_ms)
    key_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._current_image: Optional[QImage] = None
        self._image_rect = QRectF()
        self._press_pos: Optional[QPointF] = None
        self._press_time: float = 0.0
        self.setStyleSheet("background-color: #050811;")

    def update_frame(self, image: QImage):
        self._current_image = image
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            # Clear background
            painter.fillRect(self.rect(), QColor("#050811"))

            if self._current_image is None or self._current_image.isNull():
                painter.setPen(QColor("#64748B"))
                painter.setFont(QFont("Inter", 13, QFont.Weight.Medium))
                painter.drawText(
                    self.rect(),
                    Qt.AlignmentFlag.AlignCenter,
                    "Aguardando transmissão de tela do Android...\n(Autorize a captura no celular se solicitado)"
                )
                return

            img = self._current_image
            widget_w = self.width()
            widget_h = self.height()
            img_w = img.width()
            img_h = img.height()

            if img_w <= 0 or img_h <= 0 or widget_w <= 0 or widget_h <= 0:
                return

            aspect_img = img_w / img_h
            aspect_widget = widget_w / widget_h

            if aspect_widget > aspect_img:
                # Widget is wider than image -> fit height
                render_h = widget_h
                render_w = int(render_h * aspect_img)
                render_x = (widget_w - render_w) // 2
                render_y = 0
            else:
                # Widget is taller than image -> fit width
                render_w = widget_w
                render_h = int(render_w / aspect_img)
                render_x = 0
                render_y = (widget_h - render_h) // 2

            self._image_rect = QRectF(render_x, render_y, render_w, render_h)
            painter.drawImage(self._image_rect, img)
        finally:
            painter.end()

    def _normalize_coords(self, pos: QPointF) -> Optional[Tuple[float, float]]:
        if self._image_rect.isEmpty() or not self._image_rect.contains(pos):
            return None
        norm_x = (pos.x() - self._image_rect.left()) / self._image_rect.width()
        norm_y = (pos.y() - self._image_rect.top()) / self._image_rect.height()
        return (norm_x, norm_y)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position()
            self._press_time = time.time()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            curr_pos = event.position()
            norm_start = self._normalize_coords(self._press_pos)
            norm_end = self._normalize_coords(curr_pos)
            dt_ms = int((time.time() - self._press_time) * 1000)

            if norm_start is not None and norm_end is not None:
                dx = curr_pos.x() - self._press_pos.x()
                dy = curr_pos.y() - self._press_pos.y()
                dist = math.hypot(dx, dy)

                if dist < 12 and dt_ms < 300:
                    # Click / Tap event
                    self.tap_occurred.emit(norm_end[0], norm_end[1])
                else:
                    # Drag / Swipe gesture
                    duration = max(50, min(600, dt_ms))
                    self.swipe_occurred.emit(norm_start[0], norm_start[1], norm_end[0], norm_end[1], duration)

            self._press_pos = None

    def wheelEvent(self, event: QWheelEvent):
        # Mouse wheel scroll support: maps to swipe gesture on phone
        pos = event.position()
        norm = self._normalize_coords(pos)
        if not norm:
            norm = (0.5, 0.5)

        norm_x, norm_y = norm
        delta = event.angleDelta().y()

        if delta != 0:
            scroll_amount = 0.25
            if delta > 0:
                # Scroll up -> swipe downwards
                start_y = max(0.1, norm_y - 0.1)
                end_y = min(0.9, start_y + scroll_amount)
            else:
                # Scroll down -> swipe upwards
                start_y = min(0.9, norm_y + 0.1)
                end_y = max(0.1, start_y - scroll_amount)

            self.swipe_occurred.emit(norm_x, start_y, norm_x, end_y, 150)


class MirrorWindow(QWidget):
    def __init__(self, connection_manager, parent=None):
        super().__init__(parent)
        self.conn = connection_manager
        self._has_adjusted_aspect = False
        self._current_aspect: float = 9.0 / 16.0

        self.setWindowTitle("Espelhamento de Tela - ConnectToPhone")
        self.resize(420, 800)
        self.setMinimumSize(280, 480)

        self._setup_ui()
        self._hook_events()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Top Control Bar
        self.top_bar = QFrame()
        self.top_bar.setStyleSheet("""
            background-color: #27272A;
            border-bottom: 1px solid #3F3F46;
            padding: 4px 8px;
        """)
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 6, 10, 6)
        top_layout.setSpacing(10)

        self.device_label = QLabel("📱 Celular Android")
        self.device_label.setStyleSheet("font-weight: 700; color: #F4F4F5; font-size: 12px;")
        top_layout.addWidget(self.device_label)

        self.stats_badge = QLabel("0 FPS")
        self.stats_badge.setStyleSheet("""
            background-color: #3F3F46;
            color: #22C55E;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 600;
        """)
        top_layout.addWidget(self.stats_badge)

        top_layout.addStretch()

        self.fs_btn = QPushButton("⛶ Tela Cheia")
        self.fs_btn.setStyleSheet("""
            padding: 4px 10px;
            font-size: 11px;
            background-color: #3F3F46;
            border: 1px solid #52525B;
            border-radius: 6px;
            color: #F4F4F5;
        """)
        self.fs_btn.clicked.connect(self._toggle_fullscreen)
        top_layout.addWidget(self.fs_btn)

        root_layout.addWidget(self.top_bar)

        # Video Canvas (fills entire remaining window area)
        self.canvas = VideoCanvas()
        self.canvas.tap_occurred.connect(self._on_tap)
        self.canvas.swipe_occurred.connect(self._on_swipe)
        root_layout.addWidget(self.canvas, stretch=1)

    def _hook_events(self):
        self.conn.stream.frame_received.connect(self._on_frame_received)
        self.conn.stream.stream_stopped.connect(self._on_stream_stopped)

    def _on_frame_received(self, image: QImage, stats: Dict[str, Any]):
        img_w = image.width()
        img_h = image.height()
        if img_w > 0 and img_h > 0:
            new_aspect = img_w / img_h
            if not self._has_adjusted_aspect or abs(new_aspect - self._current_aspect) > 0.05:
                self._has_adjusted_aspect = True
                self._current_aspect = new_aspect

                # Adapt window geometry dynamically to portrait vs landscape
                if new_aspect >= 1.0:
                    target_width = 860
                    target_height = int(target_width / new_aspect)
                else:
                    target_height = 760
                    target_width = int(target_height * new_aspect)

                top_bar_height = self.top_bar.sizeHint().height() or 40
                self.resize(max(320, target_width), target_height + top_bar_height)

        self.canvas.update_frame(image)
        fps = stats.get("fps", 0)
        res = stats.get("resolution", "")
        self.stats_badge.setText(f"{fps} FPS • {res}")

    def _on_stream_stopped(self, reason: str):
        self.stats_badge.setText("Parado")

    def _on_tap(self, norm_x: float, norm_y: float):
        self.conn.send_tap_event(norm_x, norm_y)

    def _on_swipe(self, start_x: float, start_y: float, end_x: float, end_y: float, duration_ms: int):
        self.conn.send_swipe_event(start_x, start_y, end_x, end_y, duration_ms)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.top_bar.show()
            self.fs_btn.setText("⛶ Tela Cheia")
        else:
            self.showFullScreen()
            self.fs_btn.setText("🗗 Restaurar")

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.conn.send_key_event("BACK")
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            self.conn.send_key_event("ENTER")
        elif key == Qt.Key.Key_Backspace:
            self.conn.send_key_event("BACKSPACE")
        elif event.text():
            self.conn.send_key_event(f"CHAR:{event.text()}")
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.conn.request_stop_screen_mirror()
        super().closeEvent(event)
