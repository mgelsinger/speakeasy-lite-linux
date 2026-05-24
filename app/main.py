import os

# Force GTK to use XWayland so _NET_WM_STATE_ABOVE (always-on-top for the
# floating button) is honored by KWin. Pure Wayland has no equivalent.
os.environ.setdefault("GDK_BACKEND", "x11")

import logging
import sys
import threading

# Allow `import config` etc. from within the app/ directory
sys.path.insert(0, os.path.dirname(__file__))

from gi.repository import GLib  # noqa: E402

from config import LOG_FILE, TEMP_DIR  # noqa: E402
from recorder import Recorder  # noqa: E402
from transcriber import Transcriber  # noqa: E402
from inserter import insert_text  # noqa: E402
from tray import TrayApp  # noqa: E402
from hotkeys import HotkeyListener  # noqa: E402
from focus import FocusTracker  # noqa: E402
from floating_button import FloatingButton  # noqa: E402
import prefs as _prefs  # noqa: E402


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main():
    os.makedirs(TEMP_DIR, exist_ok=True)
    setup_logging()
    log = logging.getLogger("main")
    log.info("Speakeasy Lite starting")

    prefs = _prefs.load()

    transcriber = Transcriber()
    recorder = Recorder()

    focus_tracker = FocusTracker()
    focus_tracker.start()

    # State: idle | recording | processing
    # Toggle while processing is silently ignored.
    state = {"value": "idle"}
    state_lock = threading.Lock()

    ctx = {"tray": None, "floating": None}

    def set_app_state(s):
        if ctx["tray"]:
            ctx["tray"].set_state(s)
        if ctx["floating"]:
            ctx["floating"].set_state(s)

    def finalize(wav_path):
        if wav_path:
            text = transcriber.transcribe(wav_path)
            if text:
                insert_text(text, focus_tracker=focus_tracker)
        with state_lock:
            state["value"] = "idle"
        set_app_state("idle")

    def on_toggle():
        with state_lock:
            current = state["value"]
            if current == "idle":
                state["value"] = "recording"
            elif current == "recording":
                state["value"] = "processing"
            else:
                return  # still processing — ignore

        if current == "idle":
            try:
                recorder.start()
            except Exception as e:
                log.error("Failed to start recording: %s", e)
                with state_lock:
                    state["value"] = "idle"
                return
            set_app_state("recording")

        elif current == "recording":
            wav_path = recorder.stop()
            set_app_state("processing")
            threading.Thread(target=finalize, args=(wav_path,), daemon=True).start()

    def on_exit():
        log.info("Exit requested")
        recorder.stop()
        hotkeys.stop()

    floating_btn = FloatingButton(on_click=on_toggle)
    floating_btn.set_initial_position(*prefs["floating_pos"])

    def _persist_floating_pos(x, y):
        prefs["floating_pos"] = [x, y]
        _prefs.save(prefs)

    floating_btn.set_on_moved(_persist_floating_pos)
    ctx["floating"] = floating_btn

    def toggle_floating():
        enabled = not prefs.get("floating_enabled", False)
        prefs["floating_enabled"] = enabled
        _prefs.save(prefs)
        log.info("Floating button %s", "enabled" if enabled else "disabled")
        if enabled:
            GLib.idle_add(floating_btn.show)
        else:
            GLib.idle_add(floating_btn.hide)

    hotkeys = HotkeyListener(on_toggle=on_toggle)

    tray = TrayApp(
        on_toggle=on_toggle,
        on_exit=on_exit,
        on_floating_toggle=toggle_floating,
        is_floating_enabled=lambda: prefs.get("floating_enabled", False),
    )
    ctx["tray"] = tray

    hotkeys.start()

    if prefs.get("floating_enabled", False):
        GLib.idle_add(floating_btn.show)

    def _load_model():
        import time as _time
        _time.sleep(0.5)  # let tray icon initialize
        with state_lock:
            state["value"] = "processing"
        set_app_state("processing")
        try:
            transcriber.load()
            with state_lock:
                state["value"] = "idle"
            set_app_state("idle")
            ctx["tray"].notify("Ready to dictate.")
        except Exception as e:
            log.error("Model load failed: %s", e)
            ctx["tray"].notify("Error: model failed to load. See speakeasy.log.")

    threading.Thread(target=_load_model, daemon=True).start()

    tray.run()  # blocks; returns when user clicks Exit
    log.info("Speakeasy Lite stopped")


if __name__ == "__main__":
    main()
