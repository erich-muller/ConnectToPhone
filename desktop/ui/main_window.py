"""
Minimalist Dashboard for ConnectToPhone Desktop.
Faithful implementation of user sketch: clean neutral-gray palette,
clickable phone mirror trigger with hover effect, direct clipboard history with solid blue buttons,
and background system-tray persistence.
"""

import time
from typing import Optional, List, Dict, Any
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QImage, QColor, QFont, QCursor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea,
    QCheckBox, QSizePolicy, QApplication
)

from desktop.core.config_manager import ConfigManager
from desktop.core.connection_manager import ConnectionManager, ConnectionState
from desktop.core.clipboard_service import ClipboardService, ClipboardItem
from desktop.core.discovery import get_local_ip
from desktop.ui.pair_dialog import PairDialog
from desktop.ui.mirror_window import MirrorWindow

class ClipboardRowWidget(QFrame):
    def __init__(self, item: ClipboardItem, on_copy_clicked, parent=None):
        super().__init__(parent)
        self.item = item
        self.on_copy_clicked = on_copy_clicked

        self.setStyleSheet("""
            QFrame {
                background-color: #27272A;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                padding: 6px;
            }
            QFrame:hover {
                border-color: #52525B;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        # Icon / Thumbnail
        if item.type == "image" and item.raw_image:
            thumb_label = QLabel()
            pix = QPixmap.fromImage(item.raw_image).scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            thumb_label.setPixmap(pix)
            thumb_label.setFixedSize(36, 36)
            thumb_label.setStyleSheet("border-radius: 4px; background-color: #18181B;")
            layout.addWidget(thumb_label)
        else:
            icon_label = QLabel("📝" if item.type == "text" else "🖼️")
            icon_label.setStyleSheet("font-size: 16px;")
            layout.addWidget(icon_label)

        # Text Content Preview
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        preview_text = item.preview if item.preview else (item.content if item.type == "text" else "[Imagem]")
        content_label = QLabel(preview_text)
        content_label.setStyleSheet("font-weight: 500; color: #F4F4F5; font-size: 12px;")
        content_label.setWordWrap(True)
        text_layout.addWidget(content_label)

        time_str = time.strftime("%H:%M", time.localtime(item.timestamp))
        source_str = "PC" if item.source == "local" else "Celular"
        meta_label = QLabel(f"{source_str} • {time_str}")
        meta_label.setStyleSheet("font-size: 11px; color: #71717A;")
        text_layout.addWidget(meta_label)

        layout.addLayout(text_layout, stretch=1)

        # Solid Blue Copy Button
        copy_btn = QPushButton("Copiar")
        copy_btn.setProperty("class", "CopyButton")
        copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        copy_btn.clicked.connect(lambda: self.on_copy_clicked(self.item))
        layout.addWidget(copy_btn)


class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager, connection_manager: ConnectionManager, clipboard_service: ClipboardService):
        super().__init__()
        self.config = config_manager
        self.conn = connection_manager
        self.clipboard = clipboard_service
        self.mirror_window: Optional[MirrorWindow] = None
        self.pair_dialog: Optional[PairDialog] = None

        self.setWindowTitle("ConnectToPhone")
        self.resize(560, 620)
        self.setMinimumSize(480, 520)

        self._setup_ui()
        self._hook_signals()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(16)

        # ----------------------------------------------------
        # 1. TOP HEADER (Phone Icon, Name/Status, Connect Button)
        # ----------------------------------------------------
        header_frame = QFrame()
        header_frame.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        # Clickable Phone Avatar Button with Hover Effect (Opens Screen Mirror)
        self.phone_btn = QPushButton()
        self.phone_btn.setProperty("class", "PhoneMirrorButton")
        self.phone_btn.setFixedSize(58, 68)
        self.phone_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.phone_btn.setToolTip("📱 Clique para abrir o espelhamento de tela")
        self.phone_btn.clicked.connect(self._open_screen_mirror)

        phone_btn_layout = QVBoxLayout(self.phone_btn)
        phone_btn_layout.setContentsMargins(0, 0, 0, 0)
        phone_btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        phone_icon_label = QLabel("📱")
        phone_icon_label.setStyleSheet("font-size: 30px; background: transparent; border: none;")
        phone_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        phone_btn_layout.addWidget(phone_icon_label)

        header_layout.addWidget(self.phone_btn)

        # Device Info & Live Status
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.device_name_label = QLabel("Nenhum dispositivo")
        self.device_name_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #F4F4F5;")
        info_layout.addWidget(self.device_name_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        self.status_label = QLabel("🟡 Aguardando celular...")
        self.status_label.setStyleSheet("color: #F59E0B; font-weight: 600; font-size: 12px;")
        status_row.addWidget(self.status_label)

        self.battery_label = QLabel("🔋 --%")
        self.battery_label.setStyleSheet("color: #22C55E; font-weight: 600; font-size: 12px;")
        status_row.addWidget(self.battery_label)

        status_row.addStretch()
        info_layout.addLayout(status_row)

        header_layout.addLayout(info_layout, stretch=1)

        # Right: Conectar / QR Code Button
        self.connect_btn = QPushButton("Conectar\n[QR Code]")
        self.connect_btn.setProperty("class", "ConnectHeaderButton")
        self.connect_btn.setFixedSize(96, 68)
        self.connect_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.connect_btn.clicked.connect(self._open_pair_dialog)
        header_layout.addWidget(self.connect_btn)

        main_layout.addWidget(header_frame)

        # ----------------------------------------------------
        # 2. MAIN CARD: Área de Transferências & Histórico
        # ----------------------------------------------------
        card = QFrame()
        card.setProperty("class", "CardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        # Card Title
        card_title = QLabel("📋 Área de transferências")
        card_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F4F4F5;")
        card_layout.addWidget(card_title)

        # Checkbox: Sincronizar Imagens
        self.sync_img_chk = QCheckBox("sincronizar imagens")
        self.sync_img_chk.setChecked(self.config.get("sync_images", True))
        self.sync_img_chk.toggled.connect(self._on_sync_images_toggled)
        card_layout.addWidget(self.sync_img_chk)

        # Divider Line
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #3F3F46; height: 1px; border: none;")
        card_layout.addWidget(divider)

        # Subtitle: Histórico
        hist_header = QHBoxLayout()
        hist_label = QLabel("Histórico")
        hist_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F4F4F5;")
        hist_header.addWidget(hist_label)

        hist_header.addStretch()

        clear_btn = QPushButton("Limpar")
        clear_btn.setStyleSheet("""
            background: transparent;
            border: none;
            color: #71717A;
            font-size: 11px;
            padding: 2px 6px;
        """)
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.clicked.connect(self._clear_history)
        hist_header.addWidget(clear_btn)
        card_layout.addLayout(hist_header)

        # Scroll Area with recent clipboard entries
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.history_list_layout = QVBoxLayout(self.scroll_content)
        self.history_list_layout.setContentsMargins(0, 0, 0, 0)
        self.history_list_layout.setSpacing(8)
        self.history_list_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)

        card_layout.addWidget(self.scroll_area, stretch=1)

        main_layout.addWidget(card, stretch=1)

        # ----------------------------------------------------
        # 3. MINIMAL FOOTER
        # ----------------------------------------------------
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 0, 4, 0)

        self.footer_label = QLabel(f"IP Local: {get_local_ip()}  |  Porta: {self.conn.ws_port}  |  Descoberta LAN: Ativa")
        self.footer_label.setStyleSheet("font-size: 11px; color: #71717A;")
        footer_layout.addWidget(self.footer_label)

        footer_layout.addStretch()
        main_layout.addLayout(footer_layout)

    def _hook_signals(self):
        self.conn.state_changed.connect(self._on_connection_state_changed)
        self.conn.device_status_updated.connect(self._on_device_status_updated)
        self.conn.paired_success.connect(self._on_paired_success)
        self.clipboard.history_changed.connect(self._on_clipboard_history_changed)

    def _on_connection_state_changed(self, state: str, details: str):
        if state == ConnectionState.CONNECTED:
            dev = self.conn.connected_device
            name = dev.get("name", "Celular Android")
            model = dev.get("model", "")
            self.device_name_label.setText(f"{name} ({model})" if model else name)
            self.status_label.setText("🟢 Conectado")
            self.status_label.setStyleSheet("color: #22C55E; font-weight: 600; font-size: 12px;")
            self.phone_btn.setEnabled(True)
        else:
            self.device_name_label.setText("Nenhum dispositivo")
            self.status_label.setText("🟡 Aguardando celular...")
            self.status_label.setStyleSheet("color: #F59E0B; font-weight: 600; font-size: 12px;")
            self.battery_label.setText("🔋 --%")

    def _on_device_status_updated(self, status: Dict[str, Any]):
        battery = status.get("battery_level", 0)
        charging = status.get("is_charging", False)
        symbol = "⚡ " if charging else "🔋 "
        self.battery_label.setText(f"{symbol}{battery}%")

    def _on_paired_success(self, device_id: str, device_name: str):
        self.device_name_label.setText(device_name)
        self.status_label.setText("🟢 Conectado")
        self.status_label.setStyleSheet("color: #22C55E; font-weight: 600; font-size: 12px;")
        if self.pair_dialog and self.pair_dialog.isVisible():
            self.pair_dialog.on_paired_success(device_name)

    def _on_clipboard_history_changed(self, history: List[ClipboardItem]):
        while self.history_list_layout.count() > 1:
            child = self.history_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for item in history:
            row = ClipboardRowWidget(item, on_copy_clicked=self._copy_item_to_clipboard)
            self.history_list_layout.insertWidget(self.history_list_layout.count() - 1, row)

    def _copy_item_to_clipboard(self, item: ClipboardItem):
        app = QApplication.instance()
        if not app:
            return
        cb = app.clipboard()
        if item.type == "text":
            cb.setText(item.content)
        elif item.type == "image" and item.raw_image:
            cb.setImage(item.raw_image)

    def _clear_history(self):
        self.clipboard._history.clear()
        self.clipboard.history_changed.emit([])

    def _on_sync_images_toggled(self, checked: bool):
        self.config.set("sync_images", checked)
        self.clipboard.set_sync_images(checked)

    def _open_pair_dialog(self):
        pin = self.conn.current_pairing_pin
        self.pair_dialog = PairDialog(
            device_id=self.conn.device_id,
            device_name=self.conn.device_name,
            ws_port=self.conn.ws_port,
            pin=pin,
            parent=self
        )
        self.pair_dialog.pin_regenerated.connect(lambda old_pin: self.pair_dialog.update_pin(self.conn.generate_new_pin()))
        self.pair_dialog.exec()

    def _open_screen_mirror(self):
        if self.mirror_window is None or not self.mirror_window.isVisible():
            self.mirror_window = MirrorWindow(self.conn)
            dev = self.conn.connected_device
            if dev:
                self.mirror_window.device_label.setText(f"📱 {dev.get('name', 'Android')}")
            self.mirror_window.show()

        self.conn.request_start_screen_mirror(width=720, height=1280, fps=30)

    def closeEvent(self, event):
        """Minimize to system tray instead of terminating background services."""
        event.ignore()
        self.hide()
