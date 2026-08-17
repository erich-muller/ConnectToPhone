"""
Pairing Dialog with QR Code and PIN for ConnectToPhone Desktop.
"""

import io
import qrcode
from PIL import Image
from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPainterPath
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame
)

from protocol.crypto_utils import create_qr_pairing_payload
from desktop.core.discovery import get_local_ip

class PairDialog(QDialog):
    pin_regenerated = pyqtSignal(str)

    def __init__(self, device_id: str, device_name: str, ws_port: int, pin: str, parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self.device_name = device_name
        self.ws_port = ws_port
        self.pin = pin
        self.local_ip = get_local_ip()

        self.setWindowTitle("Conectar Novo Celular")
        self.resize(440, 640)
        self.setMinimumSize(400, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._setup_ui()
        self._generate_qr()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Title & Subtitle
        title_label = QLabel("Vincular Celular ao Linux")
        title_label.setStyleSheet("font-size: 17px; font-weight: bold; color: #F4F4F5;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        sub_label = QLabel("Abra o app ConnectToPhone no seu Android e escaneie o código abaixo:")
        sub_label.setStyleSheet("font-size: 12px; color: #A1A1AA;")
        sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_label.setWordWrap(True)
        layout.addWidget(sub_label)

        # QR Code Label
        self.qr_label = QLabel()
        self.qr_label.setFixedSize(220, 220)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # PIN display section
        pin_container = QFrame()
        pin_container.setProperty("class", "CardFrame")
        pin_container.setStyleSheet("""
            background-color: #27272A;
            border: 1px solid #3F3F46;
            border-radius: 8px;
            padding: 8px 12px;
        """)
        pin_layout = QVBoxLayout(pin_container)
        pin_layout.setContentsMargins(10, 8, 10, 8)
        pin_layout.setSpacing(4)

        pin_desc = QLabel("Ou digite o código PIN no celular:")
        pin_desc.setStyleSheet("font-size: 12px; color: #A1A1AA;")
        pin_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pin_layout.addWidget(pin_desc)

        self.pin_label = QLabel(self._format_pin(self.pin))
        self.pin_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 800;
            color: #3B82F6;
            letter-spacing: 6px;
        """)
        self.pin_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pin_layout.addWidget(self.pin_label)

        info_label = QLabel(f"IP: {self.local_ip}  |  Porta: {self.ws_port}")
        info_label.setStyleSheet("font-size: 11px; color: #71717A;")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pin_layout.addWidget(info_label)

        layout.addWidget(pin_container)

        # Status text
        self.status_label = QLabel("🟡 Aguardando leitura do QR Code...")
        self.status_label.setStyleSheet("color: #F59E0B; font-size: 12px; font-weight: 600;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.regen_btn = QPushButton("Novo PIN / QR")
        self.regen_btn.clicked.connect(self._regenerate)
        btn_layout.addWidget(self.regen_btn)

        self.close_btn = QPushButton("Fechar")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _format_pin(self, pin: str) -> str:
        if len(pin) == 6:
            return f"{pin[:3]} {pin[3:]}"
        return pin

    def _generate_qr(self):
        payload = create_qr_pairing_payload(
            device_id=self.device_id,
            device_name=self.device_name,
            host_ip=self.local_ip,
            port=self.ws_port,
            pin=self.pin
        )

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2
        )
        qr.add_data(payload)
        qr.make(fit=True)

        pil_img = qr.make_image(fill_color="#18181B", back_color="#FFFFFF").convert('RGB')
        
        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        buffer.seek(0)
        
        qimage = QImage.fromData(buffer.getvalue())
        qr_pixmap = QPixmap.fromImage(qimage)

        size = 220
        card_pixmap = QPixmap(size, size)
        card_pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(card_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # White rounded card
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, size, size), 10, 10)
        painter.fillPath(path, QColor("#FFFFFF"))

        margin = 12
        draw_size = size - (margin * 2)
        scaled_qr = qr_pixmap.scaled(
            draw_size, draw_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        draw_x = (size - scaled_qr.width()) // 2
        draw_y = (size - scaled_qr.height()) // 2
        painter.drawPixmap(draw_x, draw_y, scaled_qr)
        painter.end()

        self.qr_label.setPixmap(card_pixmap)

    def update_pin(self, new_pin: str):
        self.pin = new_pin
        self.pin_label.setText(self._format_pin(new_pin))
        self._generate_qr()

    def _regenerate(self):
        self.pin_regenerated.emit(self.pin)

    def on_paired_success(self, device_name: str):
        self.status_label.setText(f"🟢 Conectado com sucesso a {device_name}!")
        self.status_label.setStyleSheet("color: #22C55E; font-size: 13px; font-weight: 700;")
        # Automatically close dialog after 600ms to smoothly return to main window
        QTimer.singleShot(600, self.accept)
