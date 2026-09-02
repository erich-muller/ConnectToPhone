"""
Universal Signal / Event Emitter for ConnectToPhone.
Provides a unified API (`signal.connect(...)`, `signal.emit(...)`) whether running under
PyQt6, PyGObject (GTK4/Libadwaita), or headless daemon mode.
"""

from typing import Callable, List, Any

try:
    from PyQt6.QtCore import pyqtSignal, QObject
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False


class EventSignal:
    def __init__(self):
        self._callbacks: List[Callable[..., Any]] = []

    def connect(self, callback: Callable[..., Any]):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def disconnect(self, callback: Callable[..., Any]):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, *args, **kwargs):
        for cb in list(self._callbacks):
            try:
                cb(*args, **kwargs)
            except Exception as e:
                print(f"[Signal] Error in signal callback {cb}: {e}")

