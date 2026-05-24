import json
import logging
import os

from config import BASE_DIR

log = logging.getLogger(__name__)

_PREFS_FILE = os.path.join(BASE_DIR, "prefs.json")
_DEFAULTS = {
    "floating_enabled": False,
    "floating_pos": [100, 100],
}


def load():
    try:
        with open(_PREFS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}
    merged = dict(_DEFAULTS)
    merged.update(data)
    return merged


def save(prefs):
    try:
        with open(_PREFS_FILE, "w") as f:
            json.dump(prefs, f, indent=2)
    except OSError as ex:
        log.warning("Failed to save prefs: %s", ex)
