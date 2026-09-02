"""
Universal Signal / Event Emitter for ConnectToPhone.
Provides a thread-safe unified API (`signal.connect(...)`, `signal.emit(...)`, `signal.disconnect(...)`)
working seamlessly across PyGObject (GTK4/Libadwaita), background worker threads, and headless daemon mode.
"""

import threading
from typing import Callable, List, Any


class EventSignal:
    """Thread-safe event signal dispatcher without external GUI framework dependencies."""
    def __init__(self):
        self._callbacks: List[Callable[..., Any]] = []
        self._lock = threading.Lock()

    def connect(self, callback: Callable[..., Any]):
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def disconnect(self, callback: Callable[..., Any]):
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def emit(self, *args, **kwargs):
        with self._lock:
            callbacks_snapshot = list(self._callbacks)
        for cb in callbacks_snapshot:
            try:
                cb(*args, **kwargs)
            except Exception as e:
                print(f"[Signal] Error in signal callback {cb}: {e}")
