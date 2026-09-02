#!/usr/bin/env python3
"""
Lightweight Clipboard Event Notifier for ConnectToPhone.
Executed by `wl-paste --watch` whenever the Wayland selection changes.
Sends a 1-byte datagram to the running ConnectToPhone daemon over a local Unix socket.
Runs in < 5ms with zero GUI overhead and zero dock interference.
"""

import socket
import os
import sys

def main():
    try:
        sock_path = f"/tmp/connecttophone_clip_{os.getuid()}.sock"
        if os.path.exists(sock_path):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            s.sendto(b"1", sock_path)
            s.close()
    except Exception:
        pass

if __name__ == "__main__":
    main()

