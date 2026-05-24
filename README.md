# Speakeasy Lite

Local dictation utility for Linux (Wayland). Press a hotkey or click the tray icon, speak, click again — text appears where your cursor is.

No internet required after the model downloads on first run.

---

## Requirements

- Linux on Wayland (tested on CachyOS/Arch + KDE Plasma 6)
- Python 3.11+
- NVIDIA GPU with the proprietary driver (CUDA 12-capable)
- A microphone
- ~1.5 GB disk space for the Whisper model + ~1.4 GB for CUDA runtime wheels

### System packages (Arch/CachyOS)

```bash
sudo pacman -S wl-clipboard libayatana-appindicator libnotify
```

- `wl-clipboard` — `wl-copy`/`wl-paste` used by the clipboard layer
- `libayatana-appindicator` — system tray host library used by KDE Plasma's StatusNotifierItem support
- `libnotify` — `notify-send` for the "ready to dictate" toast

### Input device access

The paste path uses a kernel `uinput` virtual keyboard so keystrokes reach native Wayland apps. Make sure your user can write to `/dev/uinput`:

```bash
sudo usermod -aG input $USER   # then re-login
```

---

## Setup

```bash
bash scripts/setup.sh
```

Creates `.venv` and installs all Python dependencies, including the bundled CUDA runtime wheels. The Whisper model downloads on first transcription.

---

## Run

```bash
bash scripts/run.sh
```

A green tray icon appears in the system tray.

---

## Usage

| Trigger | Action |
|---|---|
| **Ctrl+Alt+D** | Toggle recording on/off |
| **Left-click** tray icon | Toggle recording on/off |
| **Right-click** tray icon | Open menu (Exit) |

**Flow:**
1. Click into the text field you want to dictate into.
2. Trigger recording (hotkey or tray click).
3. Speak.
4. Trigger again to stop.
5. Transcription runs; the text is pasted into whatever window had focus before you triggered.

**Tray icon colors:**
- Green — idle
- Red — recording
- Orange — transcribing

---

## Troubleshooting

**No tray icon appears**
- Check `speakeasy.log` for errors.
- Ensure `libayatana-appindicator` is installed.

**`Library libcublas.so.12 is not found or cannot be loaded`**
- The CUDA runtime wheels (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) aren't installed. Re-run `bash scripts/setup.sh`.

**Recording doesn't start**
- Check that your default recording device is set (`pavucontrol` or `wpctl status`).
- `speakeasy.log` will show the error.

**Text doesn't paste / wrong window receives it**
- Make sure `/dev/uinput` is writable: `ls -l /dev/uinput`. Add yourself to the `input` group and re-login if not.
- Focus restore uses X11's `_NET_ACTIVE_WINDOW`, which works for XWayland apps. Pure-Wayland-only apps can't be focus-tracked — for those, trigger via Ctrl+Alt+D (which doesn't move focus) instead of clicking the tray.

**Paste opens "Paste Special" dialog (LibreOffice)**
- Speakeasy sends `Ctrl+Shift+V` so it works in Linux terminals (kitty, konsole, alacritty, foot, gnome-terminal) which don't bind `Ctrl+V` to paste. LibreOffice interprets `Ctrl+Shift+V` as Paste Special. If LibreOffice is your primary target, edit `app/inserter.py` to send `Ctrl+V` instead (remove the `KEY_LEFTSHIFT` press/release calls).

**Ctrl+Alt+D conflicts with another app**
- Edit the combination in `app/hotkeys.py` (the `HotKey.parse("<ctrl>+<alt>+d")` line).

---

## Log file

`speakeasy.log` in the project root. Appends across launches.
