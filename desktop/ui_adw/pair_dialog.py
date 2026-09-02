"""
Pairing Dialog with QR Code and PIN for ConnectToPhone (Libadwaita / GTK4).
"""

import os
import time
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio

from desktop.core.discovery import get_local_ip
from desktop.core.qr_generator import generate_qr_svg
from protocol.crypto_utils import create_qr_pairing_payload

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


class PairDialogAdw(Adw.Window):
    def __init__(self, device_id: str, device_name: str, ws_port: int, pin: str, parent=None, on_regenerate=None):
        super().__init__()
        self.device_id = device_id
        self.device_name = device_name
        self.ws_port = ws_port
        self.pin = pin
        self.on_regenerate_callback = on_regenerate
        self.local_ip = get_local_ip()

        if parent:
            self.set_transient_for(parent)
            self.set_modal(True)

        self.set_title("Vincular Celular ao Linux")
        self.set_default_size(420, 620)
        self.set_resizable(False)

        self._setup_ui()
        self._update_qr_display()

    def _setup_ui(self):
        # Toolbar View
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header_bar = Adw.HeaderBar()
        toolbar_view.add_top_bar(header_bar)

        # Main scrollable content
        clamp = Adw.Clamp()
        clamp.set_maximum_size(400)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(20)
        clamp.set_margin_start(20)
        clamp.set_margin_end(20)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        clamp.set_child(main_box)
        toolbar_view.set_content(clamp)

        # Title & Guidance
        title_label = Gtk.Label(label="Escanear QR Code")
        title_label.add_css_class("title-1")
        main_box.append(title_label)

        sub_label = Gtk.Label(label="Abra o app ConnectToPhone no seu Android e aponte a câmera para o código:")
        sub_label.set_wrap(True)
        sub_label.set_justify(Gtk.Justification.CENTER)
        sub_label.add_css_class("dim-label")
        main_box.append(sub_label)

        # QR Code Container Frame
        qr_frame = Gtk.Frame()
        qr_frame.set_halign(Gtk.Align.CENTER)
        qr_frame.set_size_request(240, 240)
        qr_frame.add_css_class("card")

        self.qr_picture = Gtk.Picture()
        self.qr_picture.set_size_request(220, 220)
        self.qr_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.qr_picture.set_can_shrink(False)
        self.qr_picture.set_margin_top(10)
        self.qr_picture.set_margin_bottom(10)
        self.qr_picture.set_margin_start(10)
        self.qr_picture.set_margin_end(10)
        qr_frame.set_child(self.qr_picture)
        main_box.append(qr_frame)

        # PIN Group
        pin_group = Adw.PreferencesGroup()
        pin_group.set_title("Ou digite o código PIN no celular:")

        self.pin_row = Adw.ActionRow()
        self.pin_row.set_title("Código de Pareamento")
        self.pin_label = Gtk.Label(label=self._format_pin(self.pin))
        self.pin_label.add_css_class("title-1")
        self.pin_label.add_css_class("accent")
        self.pin_row.add_suffix(self.pin_label)
        pin_group.add(self.pin_row)

        info_row = Adw.ActionRow()
        info_row.set_title("Endereço Local")
        info_row.set_subtitle(f"IP: {self.local_ip}  |  Porta: {self.ws_port}")
        pin_group.add(info_row)

        main_box.append(pin_group)

        # Status text
        self.status_label = Gtk.Label(label="🟡 Aguardando leitura do QR Code...")
        self.status_label.add_css_class("caption")
        main_box.append(self.status_label)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(8)

        regen_btn = Gtk.Button(label="Novo PIN / QR")
        regen_btn.set_icon_name("view-refresh-symbolic")
        regen_btn.connect("clicked", self._on_regen_clicked)
        btn_box.append(regen_btn)

        close_btn = Gtk.Button(label="Fechar")
        close_btn.connect("clicked", lambda b: self.close())
        btn_box.append(close_btn)

        main_box.append(btn_box)

    def _format_pin(self, pin: str) -> str:
        if len(pin) == 6:
            return f"{pin[:3]} {pin[3:]}"
        return pin

    def _update_qr_display(self):
        payload = create_qr_pairing_payload(
            device_id=self.device_id,
            device_name=self.device_name,
            host_ip=self.local_ip,
            port=self.ws_port,
            pin=self.pin
        )

        svg_content = generate_qr_svg(payload, box_size=8, border=2)
        bytes_data = GLib.Bytes.new(svg_content.encode('utf-8'))
        texture = Gdk.Texture.new_from_bytes(bytes_data)
        self.qr_picture.set_paintable(texture)

    def update_pin(self, new_pin: str):
        self.pin = new_pin
        self.pin_label.set_label(self._format_pin(new_pin))
        self._update_qr_display()

    def _on_regen_clicked(self, button):
        if self.on_regenerate_callback:
            new_pin = self.on_regenerate_callback()
            if new_pin:
                self.update_pin(new_pin)

    def on_paired_success(self, device_name: str):
        self.status_label.set_label(f"🟢 Conectado com sucesso a {device_name}!")
        self.status_label.add_css_class("success")
        GLib.timeout_add(700, self.close)

