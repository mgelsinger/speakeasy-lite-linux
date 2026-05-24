import logging
import os
import threading
import time

log = logging.getLogger(__name__)

try:
    from Xlib import X, display
    from Xlib.protocol import event as xevent
    _HAS_XLIB = True
except ImportError:
    _HAS_XLIB = False


class FocusTracker:
    """
    Tracks the most-recently-focused user window via X11's _NET_ACTIVE_WINDOW
    and re-activates it on demand. Works for XWayland windows on KDE Plasma 6;
    purely Wayland-native windows are invisible to X11 and won't be restored.

    Continuous tracking is needed because by the time we receive the tray's
    SNI Activate D-Bus call, the panel click has already happened. We keep
    the last seen non-self window so we can put focus back where it was.
    """

    def __init__(self):
        self._last_window_id = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._read_display = None
        self._write_display = None
        self._active_atom_read = None
        self._active_atom_write = None
        self._pid_atom = None
        self._own_pid = os.getpid()

    def start(self):
        if not _HAS_XLIB:
            log.warning("python-xlib not available; focus tracking disabled")
            return
        try:
            self._read_display = display.Display()
            self._write_display = display.Display()
        except Exception as e:
            log.warning("Could not open X display for focus tracking: %s", e)
            return

        self._active_atom_read = self._read_display.intern_atom("_NET_ACTIVE_WINDOW")
        self._active_atom_write = self._write_display.intern_atom("_NET_ACTIVE_WINDOW")
        self._pid_atom = self._read_display.intern_atom("_NET_WM_PID")

        try:
            root = self._read_display.screen().root
            root.change_attributes(event_mask=X.PropertyChangeMask)
        except Exception:
            log.exception("Could not subscribe to root PropertyNotify")
            return

        # Seed with current active window
        wid = self._read_active_window()
        if wid and not self._is_self(wid):
            with self._lock:
                self._last_window_id = wid
            log.info("Focus tracker: initial active window = 0x%x", wid)

        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="FocusTracker")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _read_active_window(self):
        try:
            root = self._read_display.screen().root
            prop = root.get_full_property(self._active_atom_read, X.AnyPropertyType)
            if prop and prop.value:
                wid = int(prop.value[0])
                return wid if wid else None
        except Exception:
            log.debug("read _NET_ACTIVE_WINDOW failed", exc_info=True)
        return None

    def _is_self(self, wid):
        try:
            win = self._read_display.create_resource_object("window", wid)
            prop = win.get_full_property(self._pid_atom, X.AnyPropertyType)
            if prop and prop.value:
                return int(prop.value[0]) == self._own_pid
        except Exception:
            pass
        return False

    def _loop(self):
        while not self._stop.is_set():
            try:
                if self._read_display.pending_events() == 0:
                    time.sleep(0.05)
                    continue
                ev = self._read_display.next_event()
                if ev.type != X.PropertyNotify:
                    continue
                if ev.atom != self._active_atom_read:
                    continue
                wid = self._read_active_window()
                if not wid or self._is_self(wid):
                    continue
                with self._lock:
                    old = self._last_window_id
                    self._last_window_id = wid
                if old != wid:
                    log.debug("Focus changed: 0x%x -> 0x%x", old or 0, wid)
            except Exception:
                log.exception("Focus tracker loop error")
                time.sleep(0.2)

    def restore(self):
        with self._lock:
            wid = self._last_window_id
        if not wid:
            log.info("Focus: no window to restore")
            return
        if not self._write_display:
            return
        try:
            root = self._write_display.screen().root
            win = self._write_display.create_resource_object("window", wid)
            ev = xevent.ClientMessage(
                window=win,
                client_type=self._active_atom_write,
                data=(32, [2, X.CurrentTime, 0, 0, 0]),  # source=2 (pager)
            )
            mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
            root.send_event(ev, event_mask=mask)
            self._write_display.flush()
            log.info("Focus: requested activation of window 0x%x", wid)
        except Exception:
            log.exception("Focus restore failed")
