"""
Screen Mirror Window for ConnectToPhone (GTK4 / Libadwaita).
Hardware-accelerated rendering with Gtk.Picture inside Gtk.Stack, solid opaque canvas,
touch/mouse/gesture relay, keyboard relay, dynamic resolution switching, and clean UI without FPS clutter.
"""

import time
import math
from typing import Optional, Dict, Any, Tuple

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gtk, Adw, Gdk, GLib

from desktop.core.connection_manager import QUALITY_PROFILES, normalize_quality_key


class MirrorWindowAdw(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, connection_manager):
        super().__init__(application=app)
        self.conn = connection_manager
        self._current_texture: Optional[Gdk.Texture] = None
        self._current_aspect = 9.0 / 16.0
        self._has_adjusted_aspect = False

        self._press_x = 0.0
        self._press_y = 0.0
        self._press_time = 0.0

        self.set_title("Espelhamento de Tela — ConnectToPhone")
        self.set_default_size(400, 750)
        self.set_size_request(280, 480)
        self.add_css_class("mirror-window")

        self._apply_css()
        self._setup_ui()
        self._hook_events()

    def _apply_css(self):
        css_provider = Gtk.CssProvider()
        css = """
        window.mirror-window {
            background-color: #000000;
        }
        .mirror-black-canvas {
            background-color: #000000;
        }
        .quality-btn {
            padding-left: 10px;
            padding-right: 10px;
        }
        """
        css_provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _setup_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Header Bar with Minimize, Maximize, and Close buttons
        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(True)
        header_bar.set_show_start_title_buttons(True)
        header_bar.set_decoration_layout(":minimize,maximize,close")
        toolbar_view.add_top_bar(header_bar)

        # Title Box with icon and label
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.set_valign(Gtk.Align.CENTER)

        mirror_icon = Gtk.Image.new_from_icon_name("video-display-symbolic")
        mirror_icon.add_css_class("accent")
        title_box.append(mirror_icon)

        self.title_label = Gtk.Label(label="Espelhamento de Tela")
        self.title_label.add_css_class("heading")
        title_box.append(self.title_label)

        header_bar.set_title_widget(title_box)

        # Quality Selector Button in HeaderBar (Replaces FPS display)
        self.quality_btn = Gtk.MenuButton()
        self.quality_btn.set_tooltip_text("Qualidade e Resolução do Espelhamento")
        self.quality_btn.add_css_class("flat")
        self.quality_btn.add_css_class("quality-btn")
        self.quality_btn.set_margin_end(6)

        q_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        q_icon = Gtk.Image.new_from_icon_name("video-single-display-symbolic")
        q_btn_box.append(q_icon)

        self.quality_btn_label = Gtk.Label(label="720p")
        self.quality_btn_label.add_css_class("caption")
        self.quality_btn_label.add_css_class("bold")
        q_btn_box.append(self.quality_btn_label)

        arrow_icon = Gtk.Image.new_from_icon_name("pan-down-symbolic")
        arrow_icon.set_pixel_size(10)
        q_btn_box.append(arrow_icon)

        self.quality_btn.set_child(q_btn_box)
        self._setup_quality_popover()
        header_bar.pack_end(self.quality_btn)

        # Fullscreen Toggle Button
        fs_btn = Gtk.Button()
        fs_btn.set_icon_name("view-fullscreen-symbolic")
        fs_btn.set_tooltip_text("Alternar Tela Cheia")
        fs_btn.connect("clicked", self._toggle_fullscreen)
        header_bar.pack_end(fs_btn)

        # Main Stack Container (solid, artifact-free rendering)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)
        toolbar_view.set_content(self.stack)

        # Page 1: Placeholder page
        placeholder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        placeholder_box.set_valign(Gtk.Align.CENTER)
        placeholder_box.set_halign(Gtk.Align.CENTER)
        placeholder_box.set_margin_start(24)
        placeholder_box.set_margin_end(24)

        phone_icon = Gtk.Image.new_from_icon_name("phone-symbolic")
        phone_icon.set_pixel_size(56)
        phone_icon.add_css_class("dim-label")
        placeholder_box.append(phone_icon)

        self.placeholder_label = Gtk.Label(
            label="Aguardando transmissão de tela do celular...\n(Autorize a captura no aparelho se solicitado)"
        )
        self.placeholder_label.set_justify(Gtk.Justification.CENTER)
        self.placeholder_label.add_css_class("dim-label")
        placeholder_box.append(self.placeholder_label)

        self.stack.add_named(placeholder_box, "placeholder")

        # Page 2: Opaque Video Box (always 100% solid black background to prevent WebRTC/Meet DMA-BUF alpha artifacts)
        video_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        video_box.add_css_class("mirror-black-canvas")
        video_box.set_vexpand(True)
        video_box.set_hexpand(True)

        self.video_picture = Gtk.Picture()
        self.video_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.video_picture.set_can_shrink(True)
        self.video_picture.set_vexpand(True)
        self.video_picture.set_hexpand(True)
        video_box.append(self.video_picture)

        self.stack.add_named(video_box, "video")
        self.stack.set_visible_child_name("placeholder")

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

    def _setup_quality_popover(self):
        popover = Gtk.Popover()
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        popover_box.set_margin_top(10)
        popover_box.set_margin_bottom(10)
        popover_box.set_margin_start(10)
        popover_box.set_margin_end(10)

        header = Gtk.Label(label="Qualidade do Espelhamento")
        header.add_css_class("heading")
        header.set_halign(Gtk.Align.START)
        header.set_margin_bottom(6)
        popover_box.append(header)

        current_quality = normalize_quality_key(self.conn.config.get("stream_quality", "720p"))
        self._update_quality_button_label(current_quality)

        self._quality_check_buttons = {}
        first_radio = None

        for key, profile in QUALITY_PROFILES.items():
            btn = Gtk.CheckButton(label=profile["label"])
            if first_radio is None:
                first_radio = btn
            else:
                btn.set_group(first_radio)

            if key == current_quality:
                btn.set_active(True)

            btn.connect("toggled", self._on_quality_toggled, key, popover)
            popover_box.append(btn)
            self._quality_check_buttons[key] = btn

        popover.set_child(popover_box)
        self.quality_btn.set_popover(popover)

    def _on_quality_toggled(self, check_btn, key: str, popover: Gtk.Popover):
        if check_btn.get_active():
            self._update_quality_button_label(key)
            self.conn.set_stream_quality(key)
            popover.popdown()

    def _update_quality_button_label(self, key: str):
        k = normalize_quality_key(key)
        profile = QUALITY_PROFILES.get(k, QUALITY_PROFILES["720p"])
        self.quality_btn_label.set_label(profile["short_label"])

    def _hook_events(self):
        self.conn.quality_changed.connect(
            lambda k: GLib.idle_add(self._on_quality_changed_externally, k)
        )

    def _on_quality_changed_externally(self, key: str):
        k = normalize_quality_key(key)
        self._update_quality_button_label(k)
        btn = self._quality_check_buttons.get(k)
        if btn and not btn.get_active():
            btn.set_active(True)

    def prepare_for_stream(self, device_name: str = "Celular"):
        self.set_title(f"Espelhamento de Tela — {device_name}")
        self.title_label.set_label(f"Espelhando: {device_name}")
        self.placeholder_label.set_label("Aguardando transmissão de tela do celular...\n(Autorize a captura no aparelho se solicitado)")
        self.stack.set_visible_child_name("placeholder")

    def on_stream_stopped(self, reason: str = "Transmissão encerrada"):
        self._current_texture = None
        self.video_picture.set_paintable(None)
        self.placeholder_label.set_label(f"Transmissão de tela encerrada.\n({reason})")
        self.stack.set_visible_child_name("placeholder")

    def update_frame_from_bytes(self, img_bytes: bytes, stats: Dict[str, Any]):
        try:
            glib_bytes = GLib.Bytes.new(img_bytes)
            texture = Gdk.Texture.new_from_bytes(glib_bytes)
            self._current_texture = texture
            self.video_picture.set_paintable(texture)

            if self.stack.get_visible_child_name() != "video":
                self.stack.set_visible_child_name("video")

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
        self.set_visible(False)
        return True
