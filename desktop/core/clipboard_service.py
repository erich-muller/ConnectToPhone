"""
Clipboard Synchronization Service for ConnectToPhone Linux Desktop.
Monitors system clipboard for Text and Images in the background without needing window focus.
Uses `wl-paste --watch` with Unix Datagram Socket IPC (zero dock flashes)
and native GdkWaylandClipboard as in-process listener.
"""

import os
import sys
import time
import base64
import hashlib
import shutil
import socket
import subprocess
import threading
from typing import Optional, List, Dict, Any, Callable

# Try to import PyGObject / GDK / GLib if available
try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Gdk', '4.0')
    from gi.repository import Gtk, Gdk, GLib, Gio
    HAS_GTK = True
except Exception:
    HAS_GTK = False

# Try to import PyQt6 if available
try:
    from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QBuffer, QIODevice, Qt
    from PyQt6.QtGui import QClipboard, QImage, QPixmap
    from PyQt6.QtWidgets import QApplication
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False
    QObject = object

NOTIFIER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clip_notifier.py")


class ClipboardItem:
    def __init__(self, item_type: str, content: Any, source: str, timestamp: float, preview: str = "", raw_image: Optional[Any] = None):
        self.type = item_type  # 'text' or 'image'
        self.content = content  # str or base64 str
        self.source = source    # 'local' or 'remote'
        self.timestamp = timestamp
        self.preview = preview
        self.raw_image = raw_image

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "preview": self.preview,
            "source": self.source,
            "timestamp": self.timestamp,
            "content": self.content if self.type == "text" else "[Imagem]"
        }


class ClipboardService(QObject if HAS_PYQT else object):
    if HAS_PYQT:
        local_text_copied = pyqtSignal(str)
        local_image_copied = pyqtSignal(str)
        remote_clip_applied = pyqtSignal(object)
        history_changed = pyqtSignal(list)

        _apply_remote_text_sig = pyqtSignal(str, str)
        _apply_remote_image_sig = pyqtSignal(str, str)

    def __init__(self, device_id: str, max_history: int = 30):
        if HAS_PYQT:
            super().__init__()
        self.device_id = device_id
        self.max_history = max_history
        self._history: List[ClipboardItem] = []
        self._last_content_hash: str = ""
        self._ignore_until: float = 0.0
        self._enabled = True
        self._sync_images = True

        # Custom callbacks list
        self._on_local_text_listeners: List[Callable[[str], None]] = []
        self._on_local_image_listeners: List[Callable[[str], None]] = []
        self._on_remote_applied_listeners: List[Callable[[ClipboardItem], None]] = []
        self._on_history_changed_listeners: List[Callable[[List[ClipboardItem]], None]] = []

        # Wayland watcher handles
        self._wl_paste_bin = shutil.which("wl-paste")
        self._wl_copy_bin = shutil.which("wl-copy")
        self._watcher_running = False
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_proc: Optional[subprocess.Popen] = None
        self._sock_path = f"/tmp/connecttophone_clip_{os.getuid()}.sock"
        self._server_sock: Optional[socket.socket] = None

        if HAS_PYQT:
            self._clipboard: Optional[QClipboard] = None
            try:
                self._apply_remote_text_sig.connect(self._do_apply_remote_text, Qt.ConnectionType.QueuedConnection)
                self._apply_remote_image_sig.connect(self._do_apply_remote_image, Qt.ConnectionType.QueuedConnection)
            except Exception:
                pass

    def initialize(self):
        """Hook into Wayland background socket watcher, screenshot folder watcher, and native GDK clipboard."""
        # 1. Background Wayland Watcher
        if self._wl_paste_bin:
            self._start_wayland_watcher()

        # 2. Native GDK in-process listener when GTK display is available
        if HAS_GTK:
            try:
                display = Gdk.Display.get_default()
                if display:
                    cb = display.get_clipboard()
                    cb.connect("changed", self._on_gdk_clipboard_changed)
            except Exception:
                pass

            # Monitor GNOME Screenshot directories directly with inotify (Gio.FileMonitor)
            self._setup_screenshot_folder_watcher()

        # 3. Qt listener if active
        if HAS_PYQT:
            app = QApplication.instance()
            if app:
                self._clipboard = app.clipboard()
                if self._clipboard:
                    self._clipboard.dataChanged.connect(self._on_qt_clipboard_changed)

        print("[Clipboard] Clipboard service initialized (Background Watcher & Screenshot Folder Monitor Active)")

    def _setup_screenshot_folder_watcher(self):
        """Monitor GNOME screenshot directories with inotify (Gio.FileMonitor) for instant sync."""
        if not HAS_GTK:
            return
        screenshot_dirs = [
            os.path.expanduser("~/Imagens/Capturas de tela"),
            os.path.expanduser("~/Pictures/Screenshots"),
            os.path.expanduser("~/Imagens"),
            os.path.expanduser("~/Pictures")
        ]
        self._screenshot_monitors = []
        for s_dir in screenshot_dirs:
            if os.path.isdir(s_dir):
                try:
                    gfile = Gio.File.new_for_path(s_dir)
                    mon = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
                    mon.connect("changed", self._on_screenshot_file_changed)
                    self._screenshot_monitors.append(mon)
                    print(f"[Clipboard] Inotify monitoring screenshot directory: {s_dir}")
                except Exception as e:
                    print(f"[Clipboard] Could not monitor {s_dir}: {e}")

    def _on_screenshot_file_changed(self, monitor, gfile, other_file, event_type):
        if not self._enabled or not self._sync_images:
            return
        if event_type in (Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.CHANGES_DONE_HINT):
            filepath = gfile.get_path()
            if filepath and filepath.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                GLib.timeout_add(150, self._process_screenshot_file, filepath)

    def _process_screenshot_file(self, filepath: str):
        if not os.path.isfile(filepath):
            return False
        try:
            with open(filepath, "rb") as f:
                raw_bytes = f.read()
            if len(raw_bytes) < 64:
                return False
            img_hash = self._compute_hash(raw_bytes)
            if img_hash == self._last_content_hash:
                return False

            self._last_content_hash = img_hash
            b64_str = base64.b64encode(raw_bytes).decode('utf-8')
            preview = f"Captura de tela ({os.path.basename(filepath)}, {len(raw_bytes)//1024} KB)"
            item = ClipboardItem(
                item_type="image",
                content=b64_str,
                source="local",
                timestamp=time.time(),
                preview=preview
            )
            self._add_to_history(item)
            self._emit_local_image(b64_str)
            print(f"[Clipboard] (Screenshot File Detected) Synced {preview}")
        except Exception as e:
            print(f"[Clipboard] Error reading screenshot file: {e}")
        return False

    def _periodic_clipboard_check(self):
        if self._enabled and not self._is_gnome_wayland():
            self._check_and_process_system_clipboard()
        return GLib.SOURCE_REMOVE

    def shutdown(self):
        """Clean shutdown."""
        self._watcher_running = False
        if hasattr(self, "_watcher_procs"):
            for p in self._watcher_procs:
                try:
                    p.terminate()
                    p.kill()
                except Exception:
                    pass
            self._watcher_procs = []
        if self._watcher_proc:
            try:
                self._watcher_proc.terminate()
                self._watcher_proc.kill()
            except Exception:
                pass
            self._watcher_proc = None

        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        if os.path.exists(self._sock_path):
            try:
                os.unlink(self._sock_path)
            except Exception:
                pass

    def add_listener(self, event: str, callback: Callable):
        if event == "local_text":
            self._on_local_text_listeners.append(callback)
        elif event == "local_image":
            self._on_local_image_listeners.append(callback)
        elif event == "remote_applied":
            self._on_remote_applied_listeners.append(callback)
        elif event == "history_changed":
            self._on_history_changed_listeners.append(callback)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def set_sync_images(self, sync_images: bool):
        self._sync_images = sync_images

    def get_history(self) -> List[ClipboardItem]:
        return list(self._history)

    def clear_history(self):
        self._history.clear()
        self._emit_history_changed()

    def _compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _add_to_history(self, item: ClipboardItem):
        self._history.insert(0, item)
        if len(self._history) > self.max_history:
            self._history.pop()
        self._emit_history_changed()

    def _emit_history_changed(self):
        if HAS_PYQT:
            try:
                self.history_changed.emit(self._history)
            except Exception:
                pass
        for cb in list(self._on_history_changed_listeners):
            try:
                cb(self._history)
            except Exception:
                pass

    def _emit_local_text(self, text: str):
        if HAS_PYQT:
            try:
                self.local_text_copied.emit(text)
            except Exception:
                pass
        for cb in list(self._on_local_text_listeners):
            try:
                cb(text)
            except Exception:
                pass

    def _emit_local_image(self, b64_str: str):
        if HAS_PYQT:
            try:
                self.local_image_copied.emit(b64_str)
            except Exception:
                pass
        for cb in list(self._on_local_image_listeners):
            try:
                cb(b64_str)
            except Exception:
                pass

    def _emit_remote_applied(self, item: ClipboardItem):
        if HAS_PYQT:
            try:
                self.remote_clip_applied.emit(item)
            except Exception:
                pass
        for cb in list(self._on_remote_applied_listeners):
            try:
                cb(item)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Wayland Background Watcher (Socket IPC triggered on copy event only)
    # -------------------------------------------------------------------------
    def _is_gnome_wayland(self) -> bool:
        """Return True if running inside a GNOME Wayland session."""
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        session = os.environ.get("DESKTOP_SESSION", "").upper()
        is_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
        return is_wayland and ("GNOME" in desktop or "GNOME" in session)

    def _is_wl_watch_supported(self) -> bool:
        """Check if wl-paste --watch is actually supported by the compositor."""
        if not self._wl_paste_bin:
            return False
        # GNOME Wayland (Mutter) does not implement wlr-data-control.
        # Running wl-paste pops up a tiny window that flashes the dock.
        # GNOME Shell extension handles clipboard synchronization natively.
        if self._is_gnome_wayland():
            return False

        try:
            p = subprocess.Popen(
                [self._wl_paste_bin, "--watch", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(0.1)
            poll = p.poll()
            if poll is not None:
                return False
            p.terminate()
            try:
                p.wait(timeout=0.2)
            except Exception:
                p.kill()
            return True
        except Exception:
            return False

    def _start_wayland_watcher(self):
        if self._watcher_running or not self._wl_paste_bin:
            return
        if not self._is_wl_watch_supported():
            print("[Clipboard] wl-paste --watch not supported on this compositor (GNOME Mutter uses native Shell extension). Watcher skipped.")
            return

        self._watcher_running = True
        self._watcher_procs = []

        if os.path.exists(self._sock_path):
            try:
                os.unlink(self._sock_path)
            except Exception:
                pass

        try:
            self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self._server_sock.bind(self._sock_path)
            self._server_sock.settimeout(0.5)
        except Exception as e:
            print(f"[Clipboard] Socket bind error: {e}")

        self._watcher_thread = threading.Thread(target=self._wayland_socket_listen_loop, daemon=True, name="WlClipboardSocketWatcher")
        self._watcher_thread.start()

    def _wayland_socket_listen_loop(self):
        consecutive_failures = 0
        while self._watcher_running:
            try:
                procs = []
                # Watcher 1: Text selections
                procs.append(subprocess.Popen(
                    [self._wl_paste_bin, "--type", "text/plain", "--watch", sys.executable, NOTIFIER_SCRIPT],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                ))
                # Watcher 2: Image selections & Screenshots (Print)
                procs.append(subprocess.Popen(
                    [self._wl_paste_bin, "--type", "image/png", "--watch", sys.executable, NOTIFIER_SCRIPT],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                ))
                self._watcher_procs = procs

                time.sleep(0.2)
                if any(p.poll() is not None for p in procs):
                    consecutive_failures += 1
                    for p in procs:
                        try:
                            p.terminate()
                        except Exception:
                            pass
                    if consecutive_failures >= 3:
                        print("[Clipboard] wl-paste watcher failed repeatedly; aborting watcher loop to prevent process cycling.")
                        self._watcher_running = False
                        break
                    time.sleep(2.0)
                    continue

                consecutive_failures = 0
                while self._watcher_running and any(p.poll() is None for p in procs):
                    if self._server_sock:
                        try:
                            data, _ = self._server_sock.recvfrom(64)
                            if data:
                                self._check_and_process_system_clipboard()
                        except socket.timeout:
                            continue
                        except Exception:
                            time.sleep(0.2)
                    else:
                        time.sleep(0.5)

                for p in procs:
                    try:
                        p.terminate()
                    except Exception:
                        pass
                time.sleep(1.0)
            except Exception as e:
                time.sleep(1.5)

    def _check_and_process_system_clipboard(self):
        if not self._enabled or time.time() < self._ignore_until or not self._wl_paste_bin:
            return

        offered_types = ""
        try:
            res_types = subprocess.run(
                [self._wl_paste_bin, "--list-types"],
                capture_output=True,
                text=True,
                timeout=0.5
            )
            if res_types.returncode == 0 and res_types.stdout:
                offered_types = res_types.stdout
        except Exception:
            pass

        has_image = ("image/png" in offered_types or "image/jpeg" in offered_types or "image/bmp" in offered_types)
        has_text = ("text/plain" in offered_types or "UTF8_STRING" in offered_types or "STRING" in offered_types or "text/html" in offered_types)

        # 1. Prioritize image if an image format (e.g. screenshot print) is offered!
        if has_image and self._sync_images:
            try:
                res_img = subprocess.run(
                    [self._wl_paste_bin, "--type", "image/png"],
                    capture_output=True,
                    timeout=1.2
                )
                if res_img.returncode == 0 and res_img.stdout and len(res_img.stdout) > 64:
                    img_bytes = res_img.stdout
                    img_hash = self._compute_hash(img_bytes)
                    if img_hash != self._last_content_hash:
                        self._last_content_hash = img_hash
                        b64_str = base64.b64encode(img_bytes).decode('utf-8')
                        preview = f"Captura/Imagem ({len(img_bytes)//1024} KB)"
                        item = ClipboardItem(
                            item_type="image",
                            content=b64_str,
                            source="local",
                            timestamp=time.time(),
                            preview=preview
                        )
                        self._add_to_history(item)
                        self._emit_local_image(b64_str)
                        print(f"[Clipboard] (Background) Screenshot/Image captured ({len(img_bytes)} bytes)")
                        return
            except Exception as e:
                print(f"[Clipboard] Error reading image: {e}")

        # 2. Check text
        if has_text or not has_image:
            try:
                res = subprocess.run(
                    [self._wl_paste_bin, "-n", "--type", "text/plain"],
                    capture_output=True,
                    timeout=0.6
                )
                if res.returncode == 0 and res.stdout:
                    text_bytes = res.stdout
                    text_hash = self._compute_hash(text_bytes)
                    if text_hash != self._last_content_hash:
                        self._last_content_hash = text_hash
                        text = text_bytes.decode('utf-8', errors='replace')
                        if text:
                            preview = text[:60] + ("..." if len(text) > 60 else "")
                            item = ClipboardItem(
                                item_type="text",
                                content=text,
                                source="local",
                                timestamp=time.time(),
                                preview=preview
                            )
                            self._add_to_history(item)
                            self._emit_local_text(text)
                            print(f"[Clipboard] (Background) Local text copied: {preview!r}")
                            return
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Native GDK Clipboard Callbacks
    # -------------------------------------------------------------------------
    def _on_gdk_clipboard_changed(self, clipboard):
        if not self._enabled or time.time() < self._ignore_until:
            return

        clipboard.read_text_async(None, self._on_gdk_text_read_finish)
        if self._sync_images:
            clipboard.read_texture_async(None, self._on_gdk_texture_read_finish)

    def _on_gdk_text_read_finish(self, clipboard, result):
        if not self._enabled or time.time() < self._ignore_until:
            return

        try:
            text = clipboard.read_text_finish(result)
            if not text:
                return

            text_bytes = text.encode('utf-8')
            text_hash = self._compute_hash(text_bytes)
            if text_hash == self._last_content_hash:
                return

            self._last_content_hash = text_hash
            preview = text[:60] + ("..." if len(text) > 60 else "")
            item = ClipboardItem(
                item_type="text",
                content=text,
                source="local",
                timestamp=time.time(),
                preview=preview
            )
            self._add_to_history(item)
            self._emit_local_text(text)
            print(f"[Clipboard] (In-Focus Copied) {preview!r}")
        except Exception:
            pass

    def _on_gdk_texture_read_finish(self, clipboard, result):
        if not self._enabled or not self._sync_images or time.time() < self._ignore_until:
            return

        try:
            texture = clipboard.read_texture_finish(result)
            if not texture:
                return

            png_bytes_glib = texture.save_to_png_bytes()
            if not png_bytes_glib:
                return

            png_bytes = bytes(png_bytes_glib.get_data())
            img_hash = self._compute_hash(png_bytes)
            if img_hash == self._last_content_hash:
                return

            self._last_content_hash = img_hash
            b64_str = base64.b64encode(png_bytes).decode('utf-8')
            preview = f"Imagem ({texture.get_width()}x{texture.get_height()})"
            item = ClipboardItem(
                item_type="image",
                content=b64_str,
                source="local",
                timestamp=time.time(),
                preview=preview
            )
            self._add_to_history(item)
            self._emit_local_image(b64_str)
            print(f"[Clipboard] (In-Focus Image Copied) {preview}")
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Qt Fallback Event Handlers
    # -------------------------------------------------------------------------
    def _on_qt_clipboard_changed(self):
        if not self._enabled or not HAS_PYQT or not self._clipboard or time.time() < self._ignore_until:
            return

        mime = self._clipboard.mimeData()
        if not mime:
            return

        if mime.hasText():
            text = self._clipboard.text()
            if not text:
                return

            text_bytes = text.encode('utf-8')
            text_hash = self._compute_hash(text_bytes)
            if text_hash == self._last_content_hash:
                return
            self._last_content_hash = text_hash

            preview = text[:60] + ("..." if len(text) > 60 else "")
            item = ClipboardItem(
                item_type="text",
                content=text,
                source="local",
                timestamp=time.time(),
                preview=preview
            )
            self._add_to_history(item)
            self._emit_local_text(text)

    # -------------------------------------------------------------------------
    # Incoming Remote Clipboard Mutations (From Android to Linux)
    # -------------------------------------------------------------------------
    def handle_remote_text(self, text: str, source_id: str):
        """Thread-safe entry point for remote text arriving from companion phone."""
        if not self._enabled or not text:
            return

        text_bytes = text.encode('utf-8')
        text_hash = self._compute_hash(text_bytes)
        if text_hash == self._last_content_hash:
            return

        self._last_content_hash = text_hash
        self._ignore_until = time.time() + 1.5  # Suppress local echo

        # 1. Apply to Wayland system clipboard using wl-copy
        if self._wl_copy_bin:
            try:
                subprocess.run([self._wl_copy_bin], input=text_bytes, timeout=0.5, check=False)
            except Exception as e:
                print(f"[Clipboard] wl-copy error: {e}")

        # 2. Apply to GTK4 display clipboard if available
        if HAS_GTK:
            try:
                GLib.idle_add(self._apply_gdk_text, text)
            except Exception:
                pass

        # 3. Apply to Qt clipboard if active
        if HAS_PYQT:
            try:
                self._apply_remote_text_sig.emit(text, source_id)
            except Exception:
                pass

        preview = text[:60] + ("..." if len(text) > 60 else "")
        item = ClipboardItem(
            item_type="text",
            content=text,
            source="remote",
            timestamp=time.time(),
            preview=preview
        )
        self._add_to_history(item)
        self._emit_remote_applied(item)
        print(f"[Clipboard] ✅ Remote text applied to Linux clipboard: {preview!r}")

    def _apply_gdk_text(self, text: str):
        if HAS_GTK:
            try:
                display = Gdk.Display.get_default()
                if display:
                    cb = display.get_clipboard()
                    cb.set(text)
            except Exception:
                pass

    def handle_remote_image(self, b64_data: str, source_id: str):
        """Thread-safe entry point for remote image arriving from companion phone."""
        if not self._enabled or not self._sync_images or not b64_data:
            return

        try:
            raw_bytes = base64.b64decode(b64_data)
            img_hash = self._compute_hash(raw_bytes)
            if img_hash == self._last_content_hash:
                return

            self._last_content_hash = img_hash
            self._ignore_until = time.time() + 1.5

            if self._wl_copy_bin:
                try:
                    subprocess.run([self._wl_copy_bin, "--type", "image/png"], input=raw_bytes, timeout=0.5, check=False)
                except Exception as e:
                    print(f"[Clipboard] wl-copy image error: {e}")

            if HAS_GTK:
                try:
                    GLib.idle_add(self._apply_gdk_image, raw_bytes)
                except Exception:
                    pass

            if HAS_PYQT:
                try:
                    self._apply_remote_image_sig.emit(b64_data, source_id)
                except Exception:
                    pass

            preview = f"Imagem ({len(raw_bytes)//1024} KB)"
            item = ClipboardItem(
                item_type="image",
                content=b64_data,
                source="remote",
                timestamp=time.time(),
                preview=preview
            )
            self._add_to_history(item)
            self._emit_remote_applied(item)
            print(f"[Clipboard] ✅ Remote image applied to Linux clipboard ({len(raw_bytes)} bytes)")
        except Exception as e:
            print(f"[Clipboard] Error applying remote image: {e}")

    def _apply_gdk_image(self, raw_bytes: bytes):
        if HAS_GTK:
            try:
                glib_bytes = GLib.Bytes.new(raw_bytes)
                texture = Gdk.Texture.new_from_bytes(glib_bytes)
                display = Gdk.Display.get_default()
                if display and texture:
                    cb = display.get_clipboard()
                    cb.set(texture)
            except Exception:
                pass

    def _do_apply_remote_text(self, text: str, source_id: str):
        if HAS_PYQT and self._clipboard:
            try:
                self._clipboard.setText(text, QClipboard.Mode.Clipboard)
                self._clipboard.setText(text, QClipboard.Mode.Selection)
            except Exception:
                pass

    def _do_apply_remote_image(self, b64_data: str, source_id: str):
        if HAS_PYQT and self._clipboard:
            try:
                raw_bytes = base64.b64decode(b64_data)
                qimg = QImage.fromData(raw_bytes)
                if not qimg.isNull():
                    self._clipboard.setImage(qimg, QClipboard.Mode.Clipboard)
            except Exception:
                pass
