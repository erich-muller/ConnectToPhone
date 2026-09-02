"""
Pairing Dialog with QR Code and PIN for ConnectToPhone (Libadwaita / GTK4).
High-contrast ISO-compliant QR Code for instant Android camera scanning.
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
from desktop.core.qr_generator import generate_qr_png_bytes
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
        self.set_default_size(440, 640)
        self.set_resizable(False)

        self._setup_ui()
        self._update_qr_display()

    def _setup_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Header Bar
        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(True)
        toolbar_view.add_top_bar(header_bar)

        # Content Box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        toolbar_view.set_content(main_box)

        # Title / Instruction
        title_label = Gtk.Label(label="Conectar Celular Android")
        title_label.add_css_class("title-1")
        main_box.append(title_label)

        sub_label = Gtk.Label(
            label="Abra o app ConnectToPhone no seu celular e aponte para o QR Code abaixo:"
        )
        sub_label.set_wrap(True)
        sub_label.set_justify(Gtk.Justification.CENTER)
        sub_label.add_css_class("dim-label")
        main_box.append(sub_label)

        # High-Contrast QR Code Card (Always white background for 100% camera readability)
        qr_card = Gtk.Frame()
        qr_card.add_css_class("card")
        qr_card.set_halign(Gtk.Align.CENTER)

        qr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        qr_box.set_margin_top(12)
        qr_box.set_margin_bottom(12)
        qr_box.set_margin_start(12)
        qr_box.set_margin_end(12)
        qr_card.set_child(qr_box)

        self.qr_picture = Gtk.Picture()
        self.qr_picture.set_size_request(240, 240)
        self.qr_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.qr_picture.set_can_shrink(False)
        qr_box.append(self.qr_picture)

        main_box.append(qr_card)

        # Divider or Alternative PIN Section
        or_label = Gtk.Label(label="— OU USE O CÓDIGO PIN —")
        or_label.add_css_class("dim-label")
        or_label.add_css_class("caption")
        or_label.set_margin_top(4)
        main_box.append(or_label)

        # PIN Card
        pin_card = Gtk.Frame()
        pin_card.add_css_class("card")
        pin_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        pin_box.set_margin_top(10)
        pin_box.set_margin_bottom(10)
        pin_box.set_margin_start(16)
        pin_box.set_margin_end(16)
        pin_box.set_halign(Gtk.Align.CENTER)
        pin_card.set_child(pin_box)

        self.pin_label = Gtk.Label(label=self._format_pin(self.pin))
        self.pin_label.add_css_class("title-1")
        self.pin_label.add_css_class("monospace")
        pin_box.append(self.pin_label)

        regen_btn = Gtk.Button()
        regen_btn.set_icon_name("view-refresh-symbolic")
        regen_btn.set_tooltip_text("Gerar novo PIN")
        regen_btn.add_css_class("flat")
        regen_btn.connect("clicked", self._on_regen_clicked)
        pin_box.append(regen_btn)

        main_box.append(pin_card)

        # Status Footer
        self.status_label = Gtk.Label(
            label=f"IP: {self.local_ip}  |  Porta: {self.ws_port}"
        )
        self.status_label.add_css_class("caption")
        self.status_label.add_css_class("dim-label")
        main_box.append(self.status_label)

        # Close / Cancel Button
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        btn_box.set_margin_top(6)
        close_btn = Gtk.Button(label="Fechar")
        close_btn.set_hexpand(True)
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

        png_bytes = generate_qr_png_bytes(payload, box_size=10, border=4)
        bytes_data = GLib.Bytes.new(png_bytes)
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
        self.status_label.set_label(f"Conectado com sucesso a {device_name}!")
        self.status_label.add_css_class("success")
        GLib.timeout_add(700, self.close)
