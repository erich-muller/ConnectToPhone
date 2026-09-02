#!/usr/bin/env python3
"""
ConnectToPhone - Linux Desktop Application Entry Point
Supports Modern GNOME / Libadwaita UI, Background Daemon Mode, Single-Instance IPC, and GNOME Shell Extension.
"""

import sys
import os
import glob
import signal
import threading
import time
import argparse

# Ensure system-wide python packages are discoverable inside virtualenvs (PyGObject, Adw, Gtk4, cairo)
for site_pkg in glob.glob('/usr/lib*/python3*/site-packages'):
    if site_pkg not in sys.path:
        sys.path.append(site_pkg)

# Add repo root to python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

HAS_LIBADWAITA = False
try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    gi.require_version('Gio', '2.0')
    gi.require_version('GLib', '2.0')
    from gi.repository import Gtk, Adw, Gio, GLib
    HAS_LIBADWAITA = True
except Exception as e:
    print(f"[Main] Libadwaita not available ({e}), falling back to headless/standard engine")

from desktop.core.config_manager import ConfigManager
from desktop.core.clipboard_service import ClipboardService
from desktop.core.stream_receiver import StreamReceiver
from desktop.core.connection_manager import ConnectionManager
from desktop.core.dbus_service import DBusService

if HAS_LIBADWAITA:
    from desktop.ui_adw.main_window import MainWindowAdw


class ConnectToPhoneApp:
    def __init__(self):
        self.config = ConfigManager.get_instance()
        self.device_id = self.config.get("device_id")

        self.clipboard_service = None
        self.stream_receiver = None
        self.connection_manager = None
        self.dbus_service = None
        self.main_window = None

    def initialize_core_services(self, app_instance=None):
        """Initialize background network, clipboard, and D-Bus services once for primary instance."""
        if self.connection_manager is not None:
            return  # Already initialized

        self.clipboard_service = ClipboardService(device_id=self.device_id)
        self.clipboard_service.initialize()

        self.stream_receiver = StreamReceiver(device_id=self.device_id)

        self.connection_manager = ConnectionManager(
            config_manager=self.config,
            clipboard_service=self.clipboard_service,
            stream_receiver=self.stream_receiver
        )
        self.connection_manager.start()

        def open_window_action():
            if HAS_LIBADWAITA and app_instance:
                if self.main_window is None:
                    self.main_window = MainWindowAdw(
                        app=app_instance,
                        config_manager=self.config,
                        connection_manager=self.connection_manager,
                        clipboard_service=self.clipboard_service
                    )
                self.main_window._update_device_ui()
                self.main_window.set_visible(True)
                self.main_window.present()
                if self.connection_manager and self.connection_manager.state != "CONNECTED":
                    self.connection_manager.trigger_discovery()

        def open_mirror_action():
            if self.main_window:
                self.main_window._open_screen_mirror()
            elif HAS_LIBADWAITA and app_instance:
                open_window_action()
                if self.main_window:
                    self.main_window._open_screen_mirror()

        def open_pair_action():
            if self.main_window:
                self.main_window._open_pair_dialog()
            elif HAS_LIBADWAITA and app_instance:
                open_window_action()
                if self.main_window:
                    self.main_window._open_pair_dialog()

        def quit_daemon_action():
            if HAS_LIBADWAITA and app_instance:
                app_instance.quit()
            else:
                sys.exit(0)

        self.open_window_action = open_window_action
        self.open_mirror_action = open_mirror_action
        self.open_pair_action = open_pair_action
        self.quit_daemon_action = quit_daemon_action

        self.dbus_service = DBusService(
            connection_manager=self.connection_manager,
            config_manager=self.config,
            clipboard_service=self.clipboard_service,
            on_open_window=open_window_action,
            on_open_mirror=open_mirror_action,
            on_open_pair=open_pair_action,
            on_quit=quit_daemon_action
        )
        self.dbus_service.start()

    def cleanup(self):
        print("[App] Shutting down services...")
        if self.clipboard_service:
            self.clipboard_service.shutdown()
        if self.dbus_service:
            self.dbus_service.stop()
        if self.connection_manager:
            self.connection_manager.stop()


def parse_args():
    parser = argparse.ArgumentParser(description="ConnectToPhone Linux Desktop Server")
    parser.add_argument("--minimized", "--daemon", action="store_true", help="Start background daemon without opening main window")
    parser.add_argument("--mirror", action="store_true", help="Open screen mirroring window directly")
    parser.add_argument("--pair", action="store_true", help="Open pairing dialog directly")
    parser.add_argument("--quit", action="store_true", help="Stop running ConnectToPhone daemon")
    parser.add_argument("--headless-check", action="store_true", help="Run sanity check and exit")
    return parser.parse_args()


def main():
    args = parse_args()
    app_helper = ConnectToPhoneApp()

    if args.headless_check:
        print(f"[SanityCheck] Device ID: {app_helper.device_id}")
        print(f"[SanityCheck] Device Name: {app_helper.config.get('device_name')}")
        print(f"[SanityCheck] Libadwaita available: {HAS_LIBADWAITA}")
        print("[SanityCheck] Core Services OK")
        return 0

    if HAS_LIBADWAITA:
        app_instance = Adw.Application(
            application_id="org.connecttophone.Desktop",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )

        def on_startup(app):
            # Only primary instance runs startup
            app_helper.initialize_core_services(app_instance=app)

            # Actions registered on Application
            quit_act = Gio.SimpleAction.new("quit", None)
            quit_act.connect("activate", lambda a, p: app.quit())
            app.add_action(quit_act)

            mirror_act = Gio.SimpleAction.new("mirror", None)
            mirror_act.connect("activate", lambda a, p: app_helper.open_mirror_action())
            app.add_action(mirror_act)

            pair_act = Gio.SimpleAction.new("pair", None)
            pair_act.connect("activate", lambda a, p: app_helper.open_pair_action())
            app.add_action(pair_act)

            open_win_act = Gio.SimpleAction.new("open_window", None)
            open_win_act.connect("activate", lambda a, p: app_helper.open_window_action())
            app.add_action(open_win_act)

            # Hold application so it keeps running in background when windows are closed
            app.hold()

        def on_activate(app):
            app_helper.open_window_action()

        def on_command_line(app, cmd_line):
            args_list = cmd_line.get_arguments()
            if "--quit" in args_list:
                app.quit()
                return 0
            if "--mirror" in args_list:
                app_helper.open_mirror_action()
                return 0
            if "--pair" in args_list:
                app_helper.open_pair_action()
                return 0
            if not ("--minimized" in args_list or "--daemon" in args_list):
                app_helper.open_window_action()
            return 0

        app_instance.connect("startup", on_startup)
        app_instance.connect("activate", on_activate)
        app_instance.connect("command-line", on_command_line)

        try:
            return app_instance.run(sys.argv)
        finally:
            app_helper.cleanup()
    else:
        # Fallback headless loop
        app_helper.initialize_core_services()
        shutdown_event = threading.Event()

        def _sig_handler(sig, frame):
            shutdown_event.set()

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        print("[App] Running in headless background daemon mode...")
        try:
            while not shutdown_event.is_set():
                time.sleep(1.0)
        finally:
            app_helper.cleanup()
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
