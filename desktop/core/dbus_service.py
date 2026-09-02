"""
D-Bus Daemon Service for ConnectToPhone.
Exposes `org.connecttophone.Daemon` on the session bus for GNOME Shell Extension integration
and single-instance desktop control.
"""

import json
import time
from typing import Optional, Dict, Any, Callable

try:
    import gi
    gi.require_version('Gio', '2.0')
    gi.require_version('GLib', '2.0')
    from gi.repository import Gio, GLib
    HAS_GIO = True
except Exception:
    HAS_GIO = False

from desktop.core.clipboard_service import ClipboardItem

DBUS_INTROSPECTION_XML = """
<node>
  <interface name="org.connecttophone.Daemon">
    <method name="GetStatus">
      <arg type="s" name="status_json" direction="out"/>
    </method>
    <method name="OpenWindow"/>
    <method name="OpenMirror"/>
    <method name="OpenPairDialog"/>
    <method name="ReconnectDevice"/>
    <method name="TriggerDiscovery"/>
    <method name="TriggerClipboardCheck"/>
    <method name="ToggleClipboardSync">
      <arg type="b" name="enabled" direction="in"/>
    </method>
    <method name="ReportClipboardText">
      <arg type="s" name="text" direction="in"/>
    </method>
    <method name="ReportClipboardImage">
      <arg type="s" name="b64_data" direction="in"/>
    </method>
    <method name="DisconnectDevice"/>
    <method name="Quit"/>
    <signal name="StatusChanged">
      <arg type="s" name="status_json"/>
    </signal>
  </interface>
</node>
"""

class DBusService:
    BUS_NAME = "org.connecttophone.Daemon"
    OBJECT_PATH = "/org/connecttophone/Daemon"

    def __init__(
        self,
        connection_manager,
        config_manager,
        clipboard_service,
        on_open_window: Optional[Callable[[], None]] = None,
        on_open_mirror: Optional[Callable[[], None]] = None,
        on_open_pair: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None
    ):
        self.conn = connection_manager
        self.config = config_manager
        self.clipboard = clipboard_service
        self.on_open_window = on_open_window
        self.on_open_mirror = on_open_mirror
        self.on_open_pair = on_open_pair
        self.on_quit = on_quit

        self._owner_id = 0
        self._registered_id = 0
        self._dbus_conn: Optional[Gio.DBusConnection] = None
        self._node_info = None

        self._battery_level = 0
        self._is_charging = False

        # Hook signals from connection manager
        self._hook_events()

    def _hook_events(self):
        try:
            self.conn.state_changed.connect(lambda s, d: GLib.idle_add(self._on_state_changed, s, d))
            self.conn.device_status_updated.connect(lambda st: GLib.idle_add(self._on_device_status, st))
        except Exception as e:
            print(f"[DBus] Error hooking connection manager events: {e}")

    def start(self):
        """Acquire D-Bus bus name and register object."""
        if not HAS_GIO:
            print("[DBus] Gio not available, D-Bus service skipped")
            return

        try:
            self._node_info = Gio.DBusNodeInfo.new_for_xml(DBUS_INTROSPECTION_XML)
            self._owner_id = Gio.bus_own_name(
                Gio.BusType.SESSION,
                self.BUS_NAME,
                Gio.BusNameOwnerFlags.NONE,
                self._on_bus_acquired,
                self._on_name_acquired,
                self._on_name_lost
            )
            print(f"[DBus] Registering session bus name: {self.BUS_NAME}")
        except Exception as e:
            print(f"[DBus] Error initializing DBus service: {e}")

    def stop(self):
        if HAS_GIO and self._owner_id != 0:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0

    def _on_bus_acquired(self, conn: Gio.DBusConnection, name: str):
        self._dbus_conn = conn
        try:
            interface_info = self._node_info.interfaces[0]
            self._registered_id = conn.register_object(
                self.OBJECT_PATH,
                interface_info,
                self._handle_method_call,
                None,
                None
            )
            print(f"[DBus] Object registered at path {self.OBJECT_PATH}")
            GLib.timeout_add(100, lambda: (self.emit_status_changed(), False)[1])
        except Exception as e:
            print(f"[DBus] Error registering DBus object: {e}")

    def _on_name_acquired(self, conn: Gio.DBusConnection, name: str):
        print(f"[DBus] Bus name acquired: {name}")
        self.emit_status_changed()

    def _on_name_lost(self, conn: Optional[Gio.DBusConnection], name: str):
        print(f"[DBus] Bus name lost: {name}")

    def get_status_dict(self) -> Dict[str, Any]:
        dev = self.conn.connected_device or {}
        return {
            "state": self.conn.state,
            "connected": (self.conn.state == "CONNECTED"),
            "device_id": dev.get("id", ""),
            "device_name": dev.get("name", "Nenhum dispositivo"),
            "device_model": dev.get("model", ""),
            "battery_level": self._battery_level,
            "is_charging": self._is_charging,
            "sync_clipboard": self.config.get("sync_clipboard", True),
            "sync_images": self.config.get("sync_images", True),
            "ws_port": self.conn.ws_port
        }

    def emit_status_changed(self):
        """Emit D-Bus signal to notify GNOME Shell Extension and UI."""
        if not HAS_GIO or not self._dbus_conn:
            return
        status_json = json.dumps(self.get_status_dict())
        try:
            params = GLib.Variant('(s)', (status_json,))
            self._dbus_conn.emit_signal(
                None,
                self.OBJECT_PATH,
                self.BUS_NAME,
                "StatusChanged",
                params
            )
        except Exception as e:
            print(f"[DBus] Error emitting StatusChanged signal: {e}")

    def _on_state_changed(self, state: str, details: str):
        if state != "CONNECTED":
            self._battery_level = 0
            self._is_charging = False
        self.emit_status_changed()

    def _on_device_status(self, status: Dict[str, Any]):
        print(f"[DBus] 🔋 _on_device_status called with: {status}")
        self._battery_level = status.get("battery_level", self._battery_level)
        self._is_charging = status.get("is_charging", self._is_charging)
        self.emit_status_changed()

    def _handle_method_call(
        self,
        conn: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation
    ):
        try:
            if method_name == "GetStatus":
                status_json = json.dumps(self.get_status_dict())
                invocation.return_value(GLib.Variant('(s)', (status_json,)))

            elif method_name == "OpenWindow":
                if self.on_open_window:
                    GLib.idle_add(self.on_open_window)
                invocation.return_value(None)

            elif method_name == "OpenMirror":
                if self.on_open_mirror:
                    GLib.idle_add(self.on_open_mirror)
                invocation.return_value(None)

            elif method_name == "OpenPairDialog":
                if self.on_open_pair:
                    GLib.idle_add(self.on_open_pair)
                invocation.return_value(None)

            elif method_name in ("ReconnectDevice", "TriggerDiscovery"):
                self.conn.trigger_discovery()
                invocation.return_value(None)

            elif method_name == "TriggerClipboardCheck":
                GLib.idle_add(self.clipboard._check_and_process_system_clipboard)
                invocation.return_value(None)

            elif method_name == "ToggleClipboardSync":
                enabled, = parameters.unpack()
                self.config.set("sync_clipboard", enabled)
                self.clipboard.set_enabled(enabled)
                self.emit_status_changed()
                invocation.return_value(None)

            elif method_name == "ReportClipboardText":
                text, = parameters.unpack()
                if text:
                    text_bytes = text.encode('utf-8')
                    text_hash = self.clipboard._compute_hash(text_bytes)
                    if text_hash != self.clipboard._last_content_hash and time.time() >= self.clipboard._ignore_until:
                        self.clipboard._last_content_hash = text_hash
                        preview = text[:60] + ("..." if len(text) > 60 else "")
                        item = ClipboardItem(
                            item_type="text",
                            content=text,
                            source="local",
                            timestamp=time.time(),
                            preview=preview
                        )
                        self.clipboard._add_to_history(item)
                        self.clipboard._emit_local_text(text)
                        print(f"[Clipboard] (GNOME Extension) Local text captured: {preview!r}")
                invocation.return_value(None)

            elif method_name == "ReportClipboardImage":
                b64_data, = parameters.unpack()
                if b64_data and self.clipboard._sync_images:
                    img_hash = self.clipboard._compute_hash(b64_data.encode('utf-8'))
                    if img_hash != self.clipboard._last_content_hash and time.time() >= self.clipboard._ignore_until:
                        self.clipboard._last_content_hash = img_hash
                        preview = "Imagem capturada"
                        item = ClipboardItem(
                            item_type="image",
                            content=b64_data,
                            source="local",
                            timestamp=time.time(),
                            preview=preview
                        )
                        self.clipboard._add_to_history(item)
                        self.clipboard._emit_local_image(b64_data)
                        print(f"[Clipboard] (GNOME Extension) Local image captured")
                invocation.return_value(None)

            elif method_name == "DisconnectDevice":
                self.conn.disconnect_current_device()
                invocation.return_value(None)

            elif method_name == "Quit":
                if self.on_quit:
                    GLib.idle_add(self.on_quit)
                invocation.return_value(None)

            else:
                invocation.return_error_literal(
                    Gio.DBusError.quark(),
                    Gio.DBusError.UNKNOWN_METHOD,
                    f"Unknown method {method_name}"
                )
        except Exception as e:
            print(f"[DBus] Method {method_name} execution error: {e}")
            invocation.return_error_literal(
                Gio.DBusError.quark(),
                Gio.DBusError.FAILED,
                str(e)
            )
