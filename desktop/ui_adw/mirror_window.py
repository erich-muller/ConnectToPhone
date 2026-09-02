"""
Screen Mirror Window for ConnectToPhone (GTK4 / Libadwaita).
Hardware-accelerated rendering with Gtk.Picture, touch/mouse/gesture relay, and keyboard relay.
"""

import time
import math
from typing import Optional, Dict, Any, Tuple

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gtk, Adw, Gdk, GLib


class MirrorWindowAdw(Adw.Window):
    def __init__(self, connection_manager, parent=None):
        super().__init__()
        self.conn = connection_manager
        self._current_texture: Optional[Gdk.Texture] = None
        self._current_aspect = 9.0 / 16.0
        self._has_adjusted_aspect = False

        self._press_x = 0.0
        self._press_y = 0.0
        self._press_time = 0.0

        self.set_title("Espelhamento de Tela - ConnectToPhone")
        self.set_default_size(400, 750)
        self.set_size_request(280, 480)

        if parent:
            self.set_transient_for(parent)

        self._setup_ui()

    def _setup_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Header Bar
        header_bar = Adw.HeaderBar()
        toolbar_view.add_top_bar(header_bar)

        self.title_label = Gtk.Label(label="📱 Celular Android")
        self.title_label.add_css_class("heading")
        header_bar.set_title_widget(self.title_label)

        # Stats Badge
        self.stats_badge = Gtk.Label(label="Aguardando...")
        self.stats_badge.add_css_class("caption")
        self.stats_badge.add_css_class("card")
        self.stats_badge.set_margin_end(6)
        header_bar.pack_end(self.stats_badge)

        # Fullscreen Toggle Button
        fs_btn = Gtk.Button()
        fs_btn.set_icon_name("view-fullscreen-symbolic")
        fs_btn.set_tooltip_text("Alternar Tela Cheia")
        fs_btn.connect("clicked", self._toggle_fullscreen)
        header_bar.pack_end(fs_btn)

        # Main Container (Overlay with Placeholder Label and Video Picture)
        overlay = Gtk.Overlay()
        toolbar_view.set_content(overlay)

        # Placeholder label
        self.placeholder_label = Gtk.Label(label="Aguardando transmissão de tela do celular...\n(Autorize a captura no aparelho se solicitado)")
        self.placeholder_label.set_justify(Gtk.Justification.CENTER)
        self.placeholder_label.add_css_class("dim-label")
        self.placeholder_label.set_valign(Gtk.Align.CENTER)
        self.placeholder_label.set_halign(Gtk.Align.CENTER)
        overlay.set_child(self.placeholder_label)

        # Hardware-accelerated Video Picture
        self.video_picture = Gtk.Picture()
        self.video_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.video_picture.set_can_shrink(True)
        self.video_picture.set_vexpand(True)
        self.video_picture.set_hexpand(True)
        overlay.add_overlay(self.video_picture)

        # Click / Tap / Drag Gestures
        click_gesture = Gtk.GestureClick()
        click_gesture.set_button(1)
        click_gesture.connect("pressed", self._on_press)
        click_gesture.connect("released", self._on_release)
        self.video_picture.add_controller(click_gesture)

        # Scroll / Wheel Controller
        scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE
        )
        scroll_controller.connect("scroll", self._on_scroll)
        self.video_picture.add_controller(scroll_controller)

        # Key Event Controller
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

        self.connect("close-request", self._on_close_requested)

    def update_frame_from_bytes(self, img_bytes: bytes, stats: Dict[str, Any]):
        try:
            glib_bytes = GLib.Bytes.new(img_bytes)
            texture = Gdk.Texture.new_from_bytes(glib_bytes)
            self._current_texture = texture
            self.video_picture.set_paintable(texture)
            self.placeholder_label.set_visible(False)

            w = texture.get_width()
            h = texture.get_height()
            if w > 0 and h > 0:
                new_aspect = w / h
                if not self._has_adjusted_aspect or abs(new_aspect - self._current_aspect) > 0.05:
                    self._has_adjusted_aspect = True
                    self._current_aspect = new_aspect
                    if new_aspect >= 1.0:
                        self.set_default_size(800, int(800 / new_aspect) + 40)
                    else:
                        self.set_default_size(int(700 * new_aspect), 740)

            fps = stats.get("fps", 0)
            res = stats.get("resolution", "")
            self.stats_badge.set_label(f"{fps} FPS • {res}")
        except Exception as e:
            print(f"[Mirror] Error updating frame: {e}")

    def _normalize(self, x: float, y: float) -> Optional[Tuple[float, float]]:
        if not self._current_texture:
            return None

        width = self.video_picture.get_width()
        height = self.video_picture.get_height()
        img_w = self._current_texture.get_width()
        img_h = self._current_texture.get_height()

        if width <= 0 or height <= 0 or img_w <= 0 or img_h <= 0:
            return None

        aspect_img = img_w / img_h
        aspect_pic = width / height

        if aspect_pic > aspect_img:
            render_h = height
            render_w = int(render_h * aspect_img)
            render_x = (width - render_w) / 2.0
            render_y = 0.0
        else:
            render_w = width
            render_h = int(render_w / aspect_img)
            render_x = 0.0
            render_y = (height - render_h) / 2.0

        if not (render_x <= x <= render_x + render_w and render_y <= y <= render_y + render_h):
            return None

        norm_x = (x - render_x) / render_w
        norm_y = (y - render_y) / render_h
        return (max(0.0, min(1.0, norm_x)), max(0.0, min(1.0, norm_y)))

    def _on_press(self, gesture, n_press, x, y):
        self._press_x = x
        self._press_y = y
        self._press_time = time.time()

    def _on_release(self, gesture, n_press, x, y):
        dt_ms = int((time.time() - self._press_time) * 1000)
        norm_start = self._normalize(self._press_x, self._press_y)
        norm_end = self._normalize(x, y)

        if norm_start and norm_end:
            dist = math.hypot(x - self._press_x, y - self._press_y)
            if dist < 12 and dt_ms < 350:
                self.conn.send_tap_event(norm_end[0], norm_end[1])
            else:
                duration = max(50, min(600, dt_ms))
                self.conn.send_swipe_event(norm_start[0], norm_start[1], norm_end[0], norm_end[1], duration)

    def _on_scroll(self, controller, dx, dy):
        if dy != 0:
            if dy > 0:
                self.conn.send_swipe_event(0.5, 0.7, 0.5, 0.3, 150)
            else:
                self.conn.send_swipe_event(0.5, 0.3, 0.5, 0.7, 150)
        return True

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.conn.send_key_event("BACK")
            return True
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.conn.send_key_event("ENTER")
            return True
        elif keyval == Gdk.KEY_BackSpace:
            self.conn.send_key_event("BACKSPACE")
            return True
        elif keyval == Gdk.KEY_Home:
            self.conn.send_key_event("HOME")
            return True
        return False

    def _toggle_fullscreen(self, button):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def _on_close_requested(self, window):
        self.conn.request_stop_screen_mirror()
        return False
