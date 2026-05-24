import logging
import os
import subprocess

from PIL import Image, ImageDraw

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib

log = logging.getLogger(__name__)


_STATE_CFG = {
    "idle":       {"color": (50, 180, 50),  "title": "Speakeasy Lite - Idle"},
    "recording":  {"color": (220, 50, 50),  "title": "Speakeasy Lite - Recording..."},
    "processing": {"color": (220, 140, 50), "title": "Speakeasy Lite - Processing..."},
}

_SNI_PATH = "/StatusNotifierItem"
_SNI_IFACE = "org.kde.StatusNotifierItem"
_WATCHER_NAME = "org.kde.StatusNotifierWatcher"
_WATCHER_PATH = "/StatusNotifierWatcher"
_WATCHER_IFACE = "org.kde.StatusNotifierWatcher"

# Minimal StatusNotifierItem interface: left-click -> Activate, right-click -> ContextMenu.
# Menu property points at a non-existent dbusmenu so KDE falls back to ContextMenu().
_SNI_XML = """<node>
  <interface name="org.kde.StatusNotifierItem">
    <method name="Activate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" name="delta" direction="in"/>
      <arg type="s" name="orientation" direction="in"/>
    </method>
    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewStatus">
      <arg type="s" name="status"/>
    </signal>
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
  </interface>
</node>"""


_DBUSMENU_PATH = "/MenuBar"
_DBUSMENU_IFACE = "com.canonical.dbusmenu"

# KDE Plasma 6 always reads the menu via com.canonical.dbusmenu — if Menu is
# unset (or points at an empty path), right-click does nothing. So we serve a
# tiny dbusmenu with two flat items keyed by id.
_DBUSMENU_XML = """<node>
  <interface name="com.canonical.dbusmenu">
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" name="events" direction="in"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <method name="AboutToShowGroup">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="ai" name="updatesNeeded" direction="out"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
    <signal name="ItemActivationRequested">
      <arg type="i" name="id"/>
      <arg type="u" name="timestamp"/>
    </signal>
    <property name="Version" type="u" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
  </interface>
</node>"""

# (id, label, action) -- action handled in _activate_menu_item
_MENU_ITEMS = [
    (1, "Toggle Floating Button", "floating"),
    (2, "Exit", "exit"),
]


def _make_pixmap(color, size=64):
    """Return (ARGB32 bytes, w, h). SNI expects ARGB32 in network byte order."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size // 8
    draw.ellipse([pad, pad, size - pad, size - pad], fill=color)
    rgba = img.tobytes("raw", "RGBA")
    argb = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        argb[i]     = rgba[i + 3]  # A
        argb[i + 1] = rgba[i]      # R
        argb[i + 2] = rgba[i + 1]  # G
        argb[i + 3] = rgba[i + 2]  # B
    return bytes(argb), size, size


class TrayApp:
    def __init__(self, on_toggle, on_exit, on_floating_toggle, is_floating_enabled):
        self._on_toggle = on_toggle
        self._on_exit = on_exit
        self._on_floating_toggle = on_floating_toggle
        self._is_floating_enabled = is_floating_enabled
        self._state = "idle"
        self._bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._connection = None
        self._reg_id = None
        self._menu_reg_id = None
        self._owner_id = None
        self._loop = None
        self._menu_ref = None

    def set_state(self, state):
        if state not in _STATE_CFG:
            return
        self._state = state
        GLib.idle_add(self._emit_changed)

    def _emit_changed(self):
        if not self._connection:
            return False
        try:
            self._connection.emit_signal(
                None, _SNI_PATH, _SNI_IFACE, "NewIcon", None)
            self._connection.emit_signal(
                None, _SNI_PATH, _SNI_IFACE, "NewTitle", None)
        except Exception:
            log.exception("Failed to emit SNI signals")
        return False

    def notify(self, message):
        try:
            subprocess.Popen(
                ["notify-send", "-a", "Speakeasy Lite", "Speakeasy Lite", message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            log.exception("notify failed")

    def _handle_method_call(self, conn, sender, path, iface, method, params, invocation):
        if method == "Activate":
            log.info("SNI Activate (left-click) -> toggle")
            self._on_toggle()
            invocation.return_value(None)
        elif method == "SecondaryActivate":
            log.info("SNI SecondaryActivate (middle-click) -> toggle")
            self._on_toggle()
            invocation.return_value(None)
        elif method == "ContextMenu":
            # KDE renders the menu directly from the dbusmenu at /MenuBar,
            # so it doesn't actually invoke this on right-click. Kept as
            # a no-op for clients that fall through to it.
            invocation.return_value(None)
        elif method == "Scroll":
            invocation.return_value(None)
        else:
            invocation.return_dbus_error(
                "org.kde.StatusNotifierItem.UnknownMethod",
                f"Unknown method: {method}")

    def _handle_get_property(self, conn, sender, path, iface, prop):
        cfg = _STATE_CFG[self._state]
        if prop == "Category":
            return GLib.Variant("s", "ApplicationStatus")
        if prop == "Id":
            return GLib.Variant("s", "speakeasy-lite")
        if prop == "Title":
            return GLib.Variant("s", cfg["title"])
        if prop == "Status":
            return GLib.Variant("s", "Active")
        if prop == "WindowId":
            return GLib.Variant("i", 0)
        if prop == "IconName":
            return GLib.Variant("s", "")
        if prop == "IconPixmap":
            pix, w, h = _make_pixmap(cfg["color"])
            return GLib.Variant("a(iiay)", [(w, h, pix)])
        if prop in ("AttentionIconName", "OverlayIconName"):
            return GLib.Variant("s", "")
        if prop in ("AttentionIconPixmap", "OverlayIconPixmap"):
            return GLib.Variant("a(iiay)", [])
        if prop == "ToolTip":
            return GLib.Variant("(sa(iiay)ss)", ("", [], cfg["title"], ""))
        if prop == "ItemIsMenu":
            return GLib.Variant("b", False)
        if prop == "Menu":
            return GLib.Variant("o", _DBUSMENU_PATH)
        return None

    def _activate_menu_item(self, item_id):
        for i, _, action in _MENU_ITEMS:
            if i != item_id:
                continue
            if action == "floating":
                self._on_floating_toggle()
            elif action == "exit":
                self._handle_exit()
            return

    def _item_props(self, item_id):
        for i, label, _ in _MENU_ITEMS:
            if i == item_id:
                return {"label": GLib.Variant("s", label)}
        return {}

    def _handle_dbusmenu_method(self, conn, sender, path, iface, method, params, invocation):
        if method == "GetLayout":
            parent_id, _depth, _props = params.unpack()
            if parent_id == 0:
                children = [
                    GLib.Variant("(ia{sv}av)", (item_id, self._item_props(item_id), []))
                    for item_id, _, _ in _MENU_ITEMS
                ]
                layout_tuple = (
                    0,
                    {"children-display": GLib.Variant("s", "submenu")},
                    children,
                )
            else:
                layout_tuple = (parent_id, self._item_props(parent_id), [])
            invocation.return_value(
                GLib.Variant("(u(ia{sv}av))", (1, layout_tuple))
            )
            return

        if method == "GetGroupProperties":
            ids, _names = params.unpack()
            wanted = set(ids) if ids else {i for i, _, _ in _MENU_ITEMS}
            entries = [(i, self._item_props(i)) for i, _, _ in _MENU_ITEMS if i in wanted]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (entries,)))
            return

        if method == "GetProperty":
            item_id, name = params.unpack()
            props = self._item_props(item_id)
            value = props.get(name, GLib.Variant("s", ""))
            invocation.return_value(GLib.Variant("(v)", (value,)))
            return

        if method == "Event":
            item_id, event_id, _data, _ts = params.unpack()
            log.info("dbusmenu Event id=%d event=%s", item_id, event_id)
            if event_id == "clicked":
                self._activate_menu_item(item_id)
            invocation.return_value(None)
            return

        if method == "EventGroup":
            (events,) = params.unpack()
            for item_id, event_id, _data, _ts in events:
                if event_id == "clicked":
                    self._activate_menu_item(item_id)
            invocation.return_value(GLib.Variant("(ai)", ([],)))
            return

        if method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
            return

        if method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
            return

        invocation.return_dbus_error(
            "com.canonical.dbusmenu.UnknownMethod", f"Unknown method: {method}"
        )

    def _handle_dbusmenu_get_property(self, conn, sender, path, iface, prop):
        if prop == "Version":
            return GLib.Variant("u", 3)
        if prop == "Status":
            return GLib.Variant("s", "normal")
        if prop == "TextDirection":
            return GLib.Variant("s", "ltr")
        if prop == "IconThemePath":
            return GLib.Variant("as", [])
        return None

    def _handle_exit(self):
        self._on_exit()
        if self._loop:
            self._loop.quit()

    def _on_bus_acquired(self, conn, name):
        self._connection = conn

        sni_node = Gio.DBusNodeInfo.new_for_xml(_SNI_XML)
        sni_iface = sni_node.lookup_interface(_SNI_IFACE)
        self._reg_id = conn.register_object(
            _SNI_PATH,
            sni_iface,
            self._handle_method_call,
            self._handle_get_property,
            None,
        )

        menu_node = Gio.DBusNodeInfo.new_for_xml(_DBUSMENU_XML)
        menu_iface = menu_node.lookup_interface(_DBUSMENU_IFACE)
        self._menu_reg_id = conn.register_object(
            _DBUSMENU_PATH,
            menu_iface,
            self._handle_dbusmenu_method,
            self._handle_dbusmenu_get_property,
            None,
        )

    def _on_name_acquired(self, conn, name):
        try:
            conn.call_sync(
                _WATCHER_NAME, _WATCHER_PATH, _WATCHER_IFACE,
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (name,)),
                None,
                Gio.DBusCallFlags.NONE,
                -1, None)
            log.info("Registered SNI with watcher as %s", name)
        except Exception as e:
            log.error("Failed to register with StatusNotifierWatcher: %s", e)

    def _on_name_lost(self, conn, name):
        log.warning("Lost bus name: %s", name)

    def run(self):
        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            self._bus_name,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            self._on_name_acquired,
            self._on_name_lost,
        )
        self._loop = GLib.MainLoop()
        log.info("Tray (SNI) running on bus %s", self._bus_name)
        try:
            self._loop.run()
        finally:
            if self._connection:
                for rid in (self._reg_id, self._menu_reg_id):
                    if rid:
                        try:
                            self._connection.unregister_object(rid)
                        except Exception:
                            pass
            if self._owner_id:
                Gio.bus_unown_name(self._owner_id)
