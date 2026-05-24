import logging
import math

import cairo
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

log = logging.getLogger(__name__)

_STATE_COLORS = {
    "idle":       (50 / 255, 180 / 255, 50 / 255),
    "recording":  (220 / 255, 50 / 255, 50 / 255),
    "processing": (220 / 255, 140 / 255, 50 / 255),
}

_BUTTON_SIZE = 48
_DRAG_THRESHOLD = 5  # pixels of movement before press becomes a drag instead of a click


class FloatingButton:
    """Borderless, always-on-top, RGBA circle that toggles dictation on click and
    can be dragged to reposition.

    The Gdk.Window is created with override-redirect so KWin doesn't manage it
    at all — this is the only reliable way to stop click-to-focus from stealing
    keyboard focus away from the user's text field. Side effect: we lose
    WM-handled dragging (begin_move_drag), so we implement drag manually with
    motion events + Gtk.Window.move()."""

    def __init__(self, on_click):
        self._on_click = on_click
        self._on_moved = None
        self._window = None
        self._drawing_area = None
        self._state = "idle"
        self._pending_pos = None
        # Drag/click tracking
        self._press_root = None     # (x_root, y_root) at button-press
        self._drag_offset = None    # (dx, dy) from pointer to window origin
        self._click_pending = False
        self._dragging = False

    def set_on_moved(self, cb):
        self._on_moved = cb

    def set_initial_position(self, x, y):
        self._pending_pos = (int(x), int(y))

    def show(self):
        if self._window is None:
            self._build()
        self._window.show_all()
        if self._pending_pos is not None:
            x, y = self._pending_pos
            self._window.move(x, y)
            self._pending_pos = None
        # override-redirect windows aren't managed by the WM, so we need to
        # raise ourselves explicitly to ensure visibility.
        gdk_win = self._window.get_window()
        if gdk_win is not None:
            gdk_win.raise_()

    def hide(self):
        if self._window is not None:
            x, y = self._window.get_position()
            self._pending_pos = (x, y)
            self._window.hide()

    def set_state(self, state):
        if state not in _STATE_COLORS:
            return
        self._state = state
        if self._drawing_area is not None:
            GLib.idle_add(self._drawing_area.queue_draw)

    def _build(self):
        win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_title("Speakeasy Lite")
        win.set_decorated(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)
        win.set_type_hint(Gdk.WindowTypeHint.DOCK)
        win.set_resizable(False)
        win.set_default_size(_BUTTON_SIZE, _BUTTON_SIZE)
        win.set_app_paintable(True)
        win.set_accept_focus(False)
        win.set_focus_on_map(False)
        win.set_can_focus(False)

        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            win.set_visual(visual)

        da = Gtk.DrawingArea()
        da.set_size_request(_BUTTON_SIZE, _BUTTON_SIZE)
        da.set_can_focus(False)
        da.connect("draw", self._on_draw)

        evbox = Gtk.EventBox()
        evbox.set_can_focus(False)
        evbox.add(da)
        evbox.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        evbox.connect("button-press-event", self._on_press)
        evbox.connect("button-release-event", self._on_release)
        evbox.connect("motion-notify-event", self._on_motion)
        win.add(evbox)
        win.connect("delete-event", lambda *_: True)

        # Realize so a Gdk.Window exists, then mark it override-redirect.
        # Must happen before show; once set, KWin treats this window as
        # off-the-record — no focus, no taskbar entry, no decoration, no
        # WM-handled drag/move.
        win.realize()
        gdk_win = win.get_window()
        if gdk_win is not None:
            gdk_win.set_override_redirect(True)

        self._window = win
        self._drawing_area = da

    def _on_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()

        cr.save()
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.restore()

        r, g, b = _STATE_COLORS[self._state]
        radius = min(w, h) / 2 - 2
        cr.arc(w / 2, h / 2, radius, 0, 2 * math.pi)
        cr.set_source_rgb(r, g, b)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.set_line_width(2)
        cr.stroke()
        return False

    def _on_press(self, widget, event):
        if event.button != 1:
            return False
        self._press_root = (event.x_root, event.y_root)
        wx, wy = self._window.get_position()
        self._drag_offset = (event.x_root - wx, event.y_root - wy)
        self._click_pending = True
        self._dragging = False
        return False

    def _on_motion(self, widget, event):
        if self._press_root is None:
            return False
        if self._click_pending:
            dx = abs(event.x_root - self._press_root[0])
            dy = abs(event.y_root - self._press_root[1])
            if dx > _DRAG_THRESHOLD or dy > _DRAG_THRESHOLD:
                self._click_pending = False
                self._dragging = True
        if self._dragging and self._drag_offset is not None:
            new_x = int(event.x_root - self._drag_offset[0])
            new_y = int(event.y_root - self._drag_offset[1])
            self._window.move(new_x, new_y)
        return False

    def _on_release(self, widget, event):
        if event.button != 1:
            return False
        if self._click_pending:
            self._click_pending = False
            self._on_click()
        if self._dragging:
            self._dragging = False
            x, y = self._window.get_position()
            if self._on_moved is not None:
                self._on_moved(x, y)
        self._press_root = None
        self._drag_offset = None
        return False
