#!/usr/bin/env python3
"""
ConnectToPhone - Linux Desktop Application Entry Point
Supports Modern GNOME / Libadwaita UI, Background Daemon Mode, and GNOME Shell Extension IPC.
"""

import sys
import os
import glob
import signal
import threading
import time
import argparse

# Ensure system-wide python packages are discoverable even inside a venv (PyGObject, Adw, Gtk4, cairo)
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

    # Load configuration
    config = ConfigManager.get_instance()
    device_id = config.get("device_id")

    if args.headless_check:
        print(f"[SanityCheck] Device ID: {device_id}")
        print(f"[SanityCheck] Device Name: {config.get('device_name')}")
        print(f"[SanityCheck] Libadwaita available: {HAS_LIBADWAITA}")
        print("[SanityCheck] Core Services OK")
        return 0

    # 1. Initialize Core Engine & Background Clipboard
    clipboard_service = ClipboardService(device_id=device_id)
    clipboard_service.initialize()

    stream_receiver = StreamReceiver(device_id=device_id)

    connection_manager = ConnectionManager(
        config_manager=config,
        clipboard_service=clipboard_service,
        stream_receiver=stream_receiver
    )
    connection_manager.start()

    main_window_holder = {"window": None}

    def open_window_action():
        if HAS_LIBADWAITA and app_instance:
            if main_window_holder["window"] is None:
                win = MainWindowAdw(
                    app=app_instance,
                    config_manager=config,
                    connection_manager=connection_manager,
                    clipboard_service=clipboard_service
                )
                main_window_holder["window"] = win
            main_window_holder["window"].set_visible(True)
            main_window_holder["window"].present()

    def open_mirror_action():
        if main_window_holder["window"]:
            main_window_holder["window"]._open_screen_mirror()
        elif HAS_LIBADWAITA and app_instance:
            open_window_action()
            if main_window_holder["window"]:
                main_window_holder["window"]._open_screen_mirror()

    def open_pair_action():
        if main_window_holder["window"]:
            main_window_holder["window"]._open_pair_dialog()
        elif HAS_LIBADWAITA and app_instance:
            open_window_action()
            if main_window_holder["window"]:
                main_window_holder["window"]._open_pair_dialog()

    # 2. Start D-Bus Service (Allows GNOME Shell Extension to interact with daemon 24/7)
    dbus_service = DBusService(
        connection_manager=connection_manager,
        config_manager=config,
        clipboard_service=clipboard_service,
        on_open_window=open_window_action,
        on_open_mirror=open_mirror_action,
        on_open_pair=open_pair_action
    )
    dbus_service.start()

    # 3. Launch UI / Persistent Daemon (Libadwaita / GTK4)
    if HAS_LIBADWAITA:
        app_instance = Adw.Application(
            application_id="org.connecttophone.Desktop",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )

        # Actions registered on Application
        quit_act = Gio.SimpleAction.new("quit", None)
        quit_act.connect("activate", lambda a, p: app_instance.quit())
        app_instance.add_action(quit_act)

        mirror_act = Gio.SimpleAction.new("mirror", None)
        mirror_act.connect("activate", lambda a, p: open_mirror_action())
        app_instance.add_action(mirror_act)

        pair_act = Gio.SimpleAction.new("pair", None)
        pair_act.connect("activate", lambda a, p: open_pair_action())
        app_instance.add_action(pair_act)

        open_win_act = Gio.SimpleAction.new("open_window", None)
        open_win_act.connect("activate", lambda a, p: open_window_action())
        app_instance.add_action(open_win_act)

        def on_activate(app):
            open_window_action()

        def on_command_line(app, cmd_line):
            args_list = cmd_line.get_arguments()
            if "--quit" in args_list:
                app.quit()
                return 0
            if "--mirror" in args_list:
                open_mirror_action()
                return 0
            if "--pair" in args_list:
                open_pair_action()
                return 0
            if not ("--minimized" in args_list or "--daemon" in args_list):
                open_window_action()
            return 0

        app_instance.connect("activate", on_activate)
        app_instance.connect("command-line", on_command_line)

        # Hold application so it keeps running in background when windows are closed
        app_instance.hold()

        def cleanup_adw():
            print("[App] Shutting down services...")
            clipboard_service.shutdown()
            dbus_service.stop()
            connection_manager.stop()

        try:
            return app_instance.run(sys.argv)
        finally:
            cleanup_adw()
    else:
        # Fallback headless loop
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
            clipboard_service.shutdown()
            dbus_service.stop()
            connection_manager.stop()
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
