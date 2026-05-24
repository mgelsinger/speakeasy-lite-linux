import logging

from pynput import keyboard

log = logging.getLogger(__name__)


class HotkeyListener:
    """Global Ctrl+Alt+D hotkey via pynput's keyboard listener (XWayland passthrough)."""

    def __init__(self, on_toggle):
        self._on_toggle = on_toggle
        self._kb_listener = None
        self._hotkey = None

    def start(self):
        self._hotkey = keyboard.HotKey(
            keyboard.HotKey.parse("<ctrl>+<alt>+d"),
            self._on_toggle,
        )
        self._kb_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._kb_listener.start()
        log.info("Hotkey listener started (Ctrl+Alt+D)")

    def stop(self):
        if self._kb_listener:
            self._kb_listener.stop()

    def _on_press(self, key):
        try:
            self._hotkey.press(self._kb_listener.canonical(key))
        except Exception:
            pass

    def _on_release(self, key):
        try:
            self._hotkey.release(self._kb_listener.canonical(key))
        except Exception:
            pass
