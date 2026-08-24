#!/usr/bin/env python3
"""
ConnectToPhone - Linux Desktop Main Entry Point.
Pairing and continuous integration with Android companion device over LAN.
"""

import sys
import os
import argparse
import signal

# Add repository root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from desktop.core.config_manager import ConfigManager
from desktop.core.clipboard_service import ClipboardService
from desktop.core.stream_receiver import StreamReceiver
from desktop.core.connection_manager import ConnectionManager
from desktop.ui.styles import MAIN_STYLESHEET
from desktop.ui.main_window import MainWindow
from desktop.ui.tray_icon import TrayIconManager

SOCKET_NAME = "ConnectToPhoneSingleInstance"

def parse_args():
    parser = argparse.ArgumentParser(description="ConnectToPhone Desktop for Linux")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to system tray")
    parser.add_argument("--headless-check", action="store_true", help="Run sanity check and exit")
    parser.add_argument("--force", "-f", action="store_true", help="Force restart and terminate existing instances")
    return parser.parse_args()

def main():
    args = parse_args()

    # Allow clean exit with Ctrl+C in terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Initialize configuration
    config = ConfigManager.get_instance()
    device_id = config.get("device_id")

    if args.headless_check:
        print(f"[SanityCheck] Device ID: {device_id}")
        print(f"[SanityCheck] Device Name: {config.get('device_name')}")
        print("[SanityCheck] ConfigManager OK")
        return 0

    if args.force:
        # Terminate any previously running instances
        import subprocess
        current_pid = os.getpid()
        try:
            subprocess.run(["pkill", "-f", "main.py"], check=False)
            subprocess.run(["pkill", "-f", "main.pyw"], check=False)
        except Exception:
            pass

    # Create Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("ConnectToPhone")
    app.setOrganizationName("ConnectToPhone")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(MAIN_STYLESHEET)

    # Single instance check
    if not args.force:
        local_socket = QLocalSocket()
        local_socket.connectToServer(SOCKET_NAME)
        if local_socket.waitForConnected(500):
            print("[App] 💡 ConnectToPhone já está em execução no sistema.")
            print("[App] 📱 Trazendo a janela existente para o primeiro plano...")
            local_socket.write(b"ACTIVATE_WINDOW")
            local_socket.flush()
            local_socket.waitForBytesWritten(500)
            local_socket.disconnectFromServer()
            return 0

    # Start local server to accept activation signals from future instances
    QLocalServer.removeServer(SOCKET_NAME)
    local_server = QLocalServer()
    local_server.listen(SOCKET_NAME)

    # Set Window and Desktop Icon if available in assets
    assets_dir = os.path.join(ROOT_DIR, "desktop", "assets")
    app_icon_path = os.path.join(assets_dir, "app_icon.png")
    if os.path.exists(app_icon_path):
        app.setWindowIcon(QIcon(app_icon_path))

    # Initialize Core Services
    clipboard_service = ClipboardService(device_id=device_id)
    clipboard_service.initialize()

    stream_receiver = StreamReceiver(device_id=device_id)

    connection_manager = ConnectionManager(
        config_manager=config,
        clipboard_service=clipboard_service,
        stream_receiver=stream_receiver
    )

    # Start network server & discovery
    connection_manager.start()

    # Create Main Window & Tray Icon
    main_window = MainWindow(
        config_manager=config,
        connection_manager=connection_manager,
        clipboard_service=clipboard_service
    )
    tray_manager = TrayIconManager(main_window, connection_manager)

    def handle_instance_message():
        conn = local_server.nextPendingConnection()
        if conn:
            conn.waitForReadyRead(500)
            msg = conn.readAll().data().decode('utf-8', errors='ignore')
            if "ACTIVATE_WINDOW" in msg:
                main_window.show()
                main_window.setWindowState(main_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
                main_window.raise_()
                main_window.activateWindow()
            conn.disconnectFromServer()

    local_server.newConnection.connect(handle_instance_message)

    # Show window unless started minimized
    if not args.minimized:
        main_window.show()

    # Handle application shutdown cleanup
    def cleanup():
        print("[App] Shutting down services...")
        QLocalServer.removeServer(SOCKET_NAME)
        connection_manager.stop()

    app.aboutToQuit.connect(cleanup)

    return app.exec()

if __name__ == "__main__":
    sys.exit(main() or 0)
