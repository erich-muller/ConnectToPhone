"""
System Tray Icon & Desktop Notifications for ConnectToPhone.
Supports custom PNG icons from desktop/assets/ with automatic fallback to vector rendering.
"""

from pathlib import Path
from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

class TrayIconManager(QObject):
    def __init__(self, main_window, connection_manager, parent=None):
        super().__init__(parent)
        self.window = main_window
        self.conn = connection_manager

        self.tray_icon = QSystemTrayIcon(parent)
        self.tray_icon.setIcon(self._create_default_icon(False))
        self.tray_icon.setToolTip("ConnectToPhone - Vincular ao Celular")

        self._setup_menu()
        self._hook_signals()
        self.tray_icon.show()

    def _create_default_icon(self, connected: bool = False) -> QIcon:
        """Load custom image file from desktop/assets/ or generate clean dynamic icon."""
        # 1. Check for custom asset file
        if connected:
            custom_connected = ASSETS_DIR / "tray_connected.png"
            if custom_connected.exists():
                return QIcon(str(custom_connected))
        else:
            custom_disconnected = ASSETS_DIR / "tray_disconnected.png"
            if custom_disconnected.exists():
                return QIcon(str(custom_disconnected))

        custom_generic = ASSETS_DIR / "tray_icon.png"
        if custom_generic.exists():
            return QIcon(str(custom_generic))

        # 2. Dynamic QPainter fallback
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Phone body
        painter.setBrush(QColor("#2563EB" if connected else "#3F3F46"))
        painter.setPen(QPen(QColor("#F4F4F5"), 2))
        painter.drawRoundedRect(16, 8, 32, 48, 6, 6)

        # Screen area
        painter.setBrush(QColor("#18181B"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(20, 14, 24, 34, 3, 3)

        # Status dot
        dot_color = QColor("#22C55E") if connected else QColor("#F59E0B")
        painter.setBrush(dot_color)
        painter.drawEllipse(44, 44, 14, 14)

        painter.end()
        return QIcon(pixmap)

    def _setup_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #27272A;
                color: #F4F4F5;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2563EB;
                color: #FFFFFF;
            }
        """)

        open_action = menu.addAction("📱 Abrir ConnectToPhone")
        open_action.triggered.connect(self._show_window)

        mirror_action = menu.addAction("🖥️ Espelhar Tela")
        mirror_action.triggered.connect(self.window._open_screen_mirror)

        menu.addSeparator()

        pair_action = menu.addAction("🔗 Conectar Novo Celular")
        pair_action.triggered.connect(self.window._open_pair_dialog)

        menu.addSeparator()

        quit_action = menu.addAction("❌ Sair")
        quit_action.triggered.connect(QApplication.instance().quit)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)

    def _hook_signals(self):
        self.conn.state_changed.connect(self._on_state_changed)
        self.conn.notification_requested.connect(self._show_notification)

    def _on_state_changed(self, state: str, details: str):
        is_conn = (state == "CONNECTED")
        self.tray_icon.setIcon(self._create_default_icon(is_conn))
        tooltip = f"ConnectToPhone - {details}"
        self.tray_icon.setToolTip(tooltip)

    def _show_notification(self, title: str, message: str):
        if self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )

    def _show_window(self):
        self.window.showNormal()
        self.window.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible():
                if self.window.isMinimized():
                    self.window.showNormal()
                else:
                    self.window.activateWindow()
            else:
                self._show_window()
