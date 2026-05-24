import logging
import threading
import time

import pyperclip
from evdev import UInput, ecodes as e

log = logging.getLogger(__name__)

_uinput = None
_uinput_lock = threading.Lock()


def _get_uinput():
    global _uinput
    with _uinput_lock:
        if _uinput is None:
            _uinput = UInput(
                {e.EV_KEY: [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_V]},
                name="speakeasy-lite-vkbd",
            )
            log.info("Created virtual keyboard via /dev/uinput at %s", _uinput.device.path)
            time.sleep(0.2)  # let compositor enumerate the new device on first use
    return _uinput


def _preview(text, n=120):
    return repr(text[:n] + ("…" if len(text) > n else ""))


def insert_text(text, focus_tracker=None):
    log.info("insert_text called: %d chars, preview=%s", len(text or ""), _preview(text or ""))
    if not text:
        log.info("Skipping insertion: empty text")
        return

    # 1. Write to clipboard via wl-copy (through pyperclip).
    try:
        pyperclip.copy(text)
        log.info("Clipboard: pyperclip.copy() returned (wrote %d chars to wl-copy)", len(text))
    except Exception as ex:
        log.error("Clipboard: pyperclip.copy failed: %s", ex)
        return

    # 2. Give wl-copy a moment to publish the selection on the Wayland clipboard.
    time.sleep(0.05)

    # 3. Read back to verify the clipboard actually holds our text.
    try:
        readback = pyperclip.paste()
    except Exception as ex:
        log.warning("Clipboard: readback failed: %s", ex)
        readback = None

    if readback == text:
        log.info("Clipboard: verified %d chars present", len(text))
    elif readback is None:
        log.warning("Clipboard: could not verify contents")
    else:
        log.warning(
            "Clipboard MISMATCH: wrote %d chars, readback returned %d chars (preview=%s)",
            len(text), len(readback), _preview(readback),
        )

    # 4. Restore focus to whatever window the user had active before the tray
    #    click / hotkey, so the upcoming Ctrl+V lands in the right text field.
    if focus_tracker is not None:
        focus_tracker.restore()
        time.sleep(0.1)  # give the compositor time to actually switch focus

    # 5. Send Ctrl+Shift+V via uinput. Linux terminals (kitty, konsole,
    #    alacritty, foot, gnome-terminal) all use Ctrl+Shift+V for paste;
    #    Ctrl+V is unbound in most of them. Modern GUI apps accept it too:
    #    Firefox/Chrome paste plain text, VSCode pastes normally. LibreOffice
    #    is the outlier — it opens Paste Special instead of pasting.
    try:
        ui = _get_uinput()
        ui.write(e.EV_KEY, e.KEY_LEFTCTRL, 1)
        ui.syn()
        time.sleep(0.01)
        ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
        ui.syn()
        time.sleep(0.01)
        ui.write(e.EV_KEY, e.KEY_V, 1)
        ui.syn()
        time.sleep(0.01)
        ui.write(e.EV_KEY, e.KEY_V, 0)
        ui.syn()
        time.sleep(0.01)
        ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
        ui.syn()
        time.sleep(0.01)
        ui.write(e.EV_KEY, e.KEY_LEFTCTRL, 0)
        ui.syn()
        log.info("Insertion: Ctrl+Shift+V dispatched via uinput")
    except Exception as ex:
        log.error("uinput Ctrl+Shift+V failed: %s", ex)
