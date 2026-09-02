"""
Native GNOME / Libadwaita Main Window for ConnectToPhone.
Compliant with GNOME Human Interface Guidelines (HIG).
"""

import os
import time
from typing import Optional, List, Dict, Any, Tuple

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gtk, Adw, Gdk, GLib, Gio

from desktop.core.config_manager import ConfigManager
from desktop.core.connection_manager import ConnectionManager, ConnectionState
from desktop.core.clipboard_service import ClipboardService, ClipboardItem
from desktop.core.discovery import get_local_ip
from desktop.ui_adw.pair_dialog import PairDialogAdw
from desktop.ui_adw.mirror_window import MirrorWindowAdw

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


class ClipboardRowAdw(Adw.ActionRow):
    def __init__(self, item: ClipboardItem, on_copy_clicked):
        super().__init__()
        self.item = item
        self.on_copy_clicked = on_copy_clicked

        preview_text = item.preview if item.preview else (item.content if item.type == "text" else "[Imagem]")
        self.set_title(preview_text)
        
        time_str = time.strftime("%H:%M", time.localtime(item.timestamp))
        source_str = "PC" if item.source == "local" else "Celular"
        self.set_subtitle(f"{source_str} • {time_str}")

        if item.type == "image":
            img_icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
            self.add_prefix(img_icon)
        else:
            txt_icon = Gtk.Image.new_from_icon_name("edit-copy-symbolic")
            self.add_prefix(txt_icon)

        copy_btn = Gtk.Button(label="Copiar")
        copy_btn.add_css_class("suggested-action")
        copy_btn.set_valign(Gtk.Align.CENTER)
        copy_btn.connect("clicked", lambda b: self.on_copy_clicked(self.item))
        self.add_suffix(copy_btn)


class MainWindowAdw(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, config_manager: ConfigManager, connection_manager: ConnectionManager, clipboard_service: ClipboardService):
        super().__init__(application=app)
        self.app = app
        self.config = config_manager
        self.conn = connection_manager
        self.clipboard = clipboard_service

        self.mirror_window: Optional[MirrorWindowAdw] = None
        self.pair_dialog: Optional[PairDialogAdw] = None
        self._history_rows: List[ClipboardRowAdw] = []

        self._pending_frame: Optional[Tuple[bytes, Dict[str, Any]]] = None
        self._render_scheduled = False

        self.set_title("ConnectToPhone")
        self.set_default_size(540, 680)
        self.set_size_request(440, 520)

        self._setup_ui()
        self._hook_events()
        self._update_device_ui()

        # Hide window on close button instead of killing background daemon
        self.connect("close-request", self._on_close_requested)

    def _setup_ui(self):
        # Toast Overlay for in-app native notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        # Toolbar View
        toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(toolbar_view)

        # HeaderBar
        header_bar = Adw.HeaderBar()
        toolbar_view.add_top_bar(header_bar)

        # Primary Menu Button
        menu = Gio.Menu()
        menu.append("Espelhar Tela", "app.mirror")
        menu.append("Conectar Novo Celular", "app.pair")
        menu.append("Encerrar ConnectToPhone", "app.quit")

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(menu)
        menu_btn.set_tooltip_text("Menu Principal")
        header_bar.pack_end(menu_btn)

        # Main Scrollable Content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        toolbar_view.set_content(scrolled)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        scrolled.set_child(clamp)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(main_box)

        # ----------------------------------------------------
        # 1. HERO CARD: Device Info & Quick Actions
        # ----------------------------------------------------
        hero_card = Gtk.Frame()
        hero_card.add_css_class("card")
        hero_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        hero_box.set_margin_top(16)
        hero_box.set_margin_bottom(16)
        hero_box.set_margin_start(16)
        hero_box.set_margin_end(16)
        hero_card.set_child(hero_box)

        # Device Header Row (Avatar, Name, Status, Battery)
        dev_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        dev_row.set_valign(Gtk.Align.CENTER)

        # Phone Icon / Avatar
        phone_icon_path = os.path.join(ASSETS_DIR, "phone.svg")
        if os.path.exists(phone_icon_path):
            self.phone_avatar = Gtk.Image.new_from_file(phone_icon_path)
            self.phone_avatar.set_pixel_size(54)
        else:
            self.phone_avatar = Gtk.Image.new_from_icon_name("phone-symbolic")
            self.phone_avatar.set_pixel_size(48)
        dev_row.append(self.phone_avatar)

        # Info Labels (Device Name, Status, Battery)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)

        self.device_name_label = Gtk.Label(label="Nenhum dispositivo")
        self.device_name_label.set_halign(Gtk.Align.START)
        self.device_name_label.add_css_class("title-2")
        info_box.append(self.device_name_label)

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        status_row.set_halign(Gtk.Align.START)

        self.status_label = Gtk.Label(label="🟡 Aguardando celular...")
        self.status_label.add_css_class("caption")
        status_row.append(self.status_label)

        self.battery_label = Gtk.Label(label="🔋 --%")
        self.battery_label.add_css_class("caption")
        status_row.append(self.battery_label)

        info_box.append(status_row)
        dev_row.append(info_box)

        hero_box.append(dev_row)

        # Action Buttons Row (Screen Mirror, Connect QR, Reconnect)
        action_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_btn_box.set_margin_top(4)

        self.mirror_btn = Gtk.Button(label="Espelhar Tela")
        self.mirror_btn.set_icon_name("video-display-symbolic")
        self.mirror_btn.set_hexpand(True)
        self.mirror_btn.connect("clicked", self._open_screen_mirror)
        self.mirror_btn.set_sensitive(False)
        action_btn_box.append(self.mirror_btn)

        self.reconnect_btn = Gtk.Button(label="Buscar Celular")
        self.reconnect_btn.set_icon_name("network-wireless-signal-good-symbolic")
        self.reconnect_btn.set_hexpand(True)
        self.reconnect_btn.connect("clicked", lambda b: self._on_reconnect_clicked())
        action_btn_box.append(self.reconnect_btn)

        self.connect_btn = Gtk.Button(label="Vincular Novo [QR]")
        self.connect_btn.set_icon_name("view-refresh-symbolic")
        self.connect_btn.set_hexpand(True)
        self.connect_btn.add_css_class("suggested-action")
        self.connect_btn.connect("clicked", self._open_pair_dialog)
        action_btn_box.append(self.connect_btn)

        hero_box.append(action_btn_box)
        main_box.append(hero_card)

        # ----------------------------------------------------
        # 2. SETTINGS / PREFERENCES GROUP
        # ----------------------------------------------------
        pref_group = Adw.PreferencesGroup()
        pref_group.set_title("Configurações de Sincronização")

        # Sync Clipboard Switch
        self.sync_clip_row = Adw.SwitchRow()
        self.sync_clip_row.set_title("Sincronizar Área de Transferência")
        self.sync_clip_row.set_subtitle("Transfere textos e links copiados em tempo real (em segundo plano)")
        self.sync_clip_row.set_active(self.config.get("sync_clipboard", True))
        self.sync_clip_row.connect("notify::active", self._on_sync_clip_toggled)
        pref_group.add(self.sync_clip_row)

        # Sync Images Switch
        self.sync_img_row = Adw.SwitchRow()
        self.sync_img_row.set_title("Sincronizar Imagens")
        self.sync_img_row.set_subtitle("Transfere capturas de tela e fotos copiadas")
        self.sync_img_row.set_active(self.config.get("sync_images", True))
        self.sync_img_row.connect("notify::active", self._on_sync_img_toggled)
        pref_group.add(self.sync_img_row)

        main_box.append(pref_group)

        # ----------------------------------------------------
        # 3. CLIPBOARD HISTORY GROUP
        # ----------------------------------------------------
        self.history_group = Adw.PreferencesGroup()
        self.history_group.set_title("Histórico da Área de Transferência")

        # Clear History Action Header
        clear_btn = Gtk.Button(label="Limpar")
        clear_btn.add_css_class("flat")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", self._clear_history)
        self.history_group.set_header_suffix(clear_btn)

        # Empty state row
        self.empty_history_row = Adw.ActionRow()
        self.empty_history_row.set_title("Nenhum item recente no histórico")
        self.empty_history_row.set_subtitle("Itens copiados no PC ou celular aparecerão aqui")
        self.history_group.add(self.empty_history_row)

        main_box.append(self.history_group)

        # ----------------------------------------------------
        # 4. FOOTER INFO
        # ----------------------------------------------------
        footer_label = Gtk.Label(
            label=f"IP: {get_local_ip()}  |  Porta: {self.conn.ws_port}  |  Descoberta LAN: Ativa"
        )
        footer_label.add_css_class("dim-label")
        footer_label.add_css_class("caption")
        footer_label.set_margin_top(8)
        main_box.append(footer_label)

    def _hook_events(self):
        try:
            self.conn.state_changed.connect(lambda s, d: GLib.idle_add(self._on_connection_state_changed, s, d))
            self.conn.device_status_updated.connect(lambda st: GLib.idle_add(self._on_device_status_updated, st))
            self.conn.paired_success.connect(lambda did, name: GLib.idle_add(self._on_paired_success, did, name))
            self.conn.notification_requested.connect(lambda t, m: GLib.idle_add(self.show_toast, f"{t}: {m}"))
        except Exception as e:
            print(f"[MainWin] Signal hook error: {e}")

        self.clipboard.add_listener("history_changed", lambda h: GLib.idle_add(self._on_history_changed, h))

    def show_toast(self, message: str):
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    def _on_reconnect_clicked(self):
        self.conn.trigger_discovery()
        self.show_toast("Buscando celular na rede local...")

    def _update_device_ui(self):
        if self.conn.state == ConnectionState.CONNECTED:
            dev = self.conn.connected_device or {}
            name = dev.get("name", "Celular Android")
            model = dev.get("model", "")
            self.device_name_label.set_label(f"{name} ({model})" if model else name)
            self.status_label.set_label("🟢 Conectado")
            self.mirror_btn.set_sensitive(True)
            self.reconnect_btn.set_visible(False)

            connected_icon = os.path.join(ASSETS_DIR, "phone_connected.svg")
            if os.path.exists(connected_icon):
                self.phone_avatar.set_from_file(connected_icon)
        else:
            paired = self.config.get_all_paired_devices()
            if paired:
                first_id = list(paired.keys())[0]
                dev_info = paired[first_id]
                paired_name = dev_info.get("name", "Celular Android")
                last_ip = dev_info.get("last_ip", "")
                ip_str = f" ({last_ip})" if last_ip else ""
                self.device_name_label.set_label(paired_name)
                self.status_label.set_label(f"🟡 Desconectado{ip_str} • Aguardando...")
                self.reconnect_btn.set_visible(True)
            else:
                self.device_name_label.set_label("Nenhum dispositivo")
                self.status_label.set_label("🟡 Aguardando celular...")
                self.reconnect_btn.set_visible(False)

            self.battery_label.set_label("🔋 --%")
            self.mirror_btn.set_sensitive(False)

            default_icon = os.path.join(ASSETS_DIR, "phone.svg")
            if os.path.exists(default_icon):
                self.phone_avatar.set_from_file(default_icon)

    def _on_connection_state_changed(self, state: str, details: str):
        self._update_device_ui()

    def _on_device_status_updated(self, status: Dict[str, Any]):
        battery = status.get("battery_level", 0)
        charging = status.get("is_charging", False)
        symbol = "⚡ " if charging else "🔋 "
        self.battery_label.set_label(f"{symbol}{battery}%")

    def _on_paired_success(self, device_id: str, device_name: str):
        self._update_device_ui()
        self.show_toast(f"Pareamento com {device_name} concluído com sucesso!")
        if self.pair_dialog:
            self.pair_dialog.on_paired_success(device_name)

    def _on_sync_clip_toggled(self, row, gparam):
        val = row.get_active()
        self.config.set("sync_clipboard", val)
        self.clipboard.set_enabled(val)

    def _on_sync_img_toggled(self, row, gparam):
        val = row.get_active()
        self.config.set("sync_images", val)
        self.clipboard.set_sync_images(val)

    def _on_history_changed(self, history: List[ClipboardItem]):
        # Safely remove previous rows
        if hasattr(self, "_history_rows"):
            for row in self._history_rows:
                if row.get_parent() == self.history_group:
                    self.history_group.remove(row)
        self._history_rows = []

        if self.empty_history_row.get_parent() == self.history_group:
            self.history_group.remove(self.empty_history_row)

        if not history:
            if self.empty_history_row.get_parent() is None:
                self.history_group.add(self.empty_history_row)
            return

        for item in history[:12]:
            row = ClipboardRowAdw(item, on_copy_clicked=self._copy_item_to_clipboard)
            self.history_group.add(row)
            self._history_rows.append(row)

    def _copy_item_to_clipboard(self, item: ClipboardItem):
        if item.type == "text":
            display = Gdk.Display.get_default()
            if display:
                cb = display.get_clipboard()
                cb.set(item.content)
            elif self.clipboard._wl_copy_bin:
                import subprocess
                subprocess.run([self.clipboard._wl_copy_bin, item.content], check=False)
            self.show_toast("Texto copiado para a área de transferência!")

    def _clear_history(self, button):
        self.clipboard.clear_history()
        self.show_toast("Histórico limpo!")

    def _open_pair_dialog(self, button=None):
        if self.pair_dialog is None or not self.pair_dialog.get_visible():
            pin = self.conn.current_pairing_pin
            self.pair_dialog = PairDialogAdw(
                device_id=self.conn.device_id,
                device_name=self.conn.device_name,
                ws_port=self.conn.ws_port,
                pin=pin,
                parent=self,
                on_regenerate=self.conn.generate_new_pin
            )
        self.pair_dialog.set_visible(True)
        self.pair_dialog.present()

    def _open_screen_mirror(self, button=None):
        if self.mirror_window is None:
            self.mirror_window = MirrorWindowAdw(self.conn, parent=self)
            self.conn.stream.frame_received.connect(self._queue_frame_for_render)
            self.conn.stream.stream_stopped.connect(
                lambda reason: GLib.idle_add(self._on_stream_stopped, reason)
            )

        dev = self.conn.connected_device or {}
        name = dev.get('name', 'Celular Android')
        self.mirror_window.prepare_for_stream(name)
        self.mirror_window.set_visible(True)
        self.mirror_window.present()
        self.conn.request_start_screen_mirror(width=720, height=1280, fps=30)

    def _queue_frame_for_render(self, frame_bytes: bytes, stats: Dict[str, Any]):
        self._pending_frame = (frame_bytes, stats)
        if not self._render_scheduled:
            self._render_scheduled = True
            GLib.idle_add(self._render_pending_frame)

    def _render_pending_frame(self):
        self._render_scheduled = False
        if not self.mirror_window or not self.mirror_window.get_visible():
            return False
        pending = self._pending_frame
        if pending:
            frame_bytes, stats = pending
            self.mirror_window.update_frame_from_bytes(frame_bytes, stats)
        return False

    def _on_stream_stopped(self, reason: str):
        if self.mirror_window:
            self.mirror_window.on_stream_stopped(reason)

    def _on_close_requested(self, window):
        # Hide the window instead of killing the background daemon
        self.set_visible(False)
        return True
