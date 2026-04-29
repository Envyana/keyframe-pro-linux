# Keyframe Pro Linux

Cross-platform animation reference player inspired by [Keyframe Pro 2](https://zurbrigg.com/keyframe-pro-2). Built with Python, PySide6 (Qt 6), and libmpv. Runs natively on Linux (Ubuntu, Fedora, Arch, openSUSE, Fedora Kinoite/Silverblue via toolbox), and works on macOS / Windows with the same code (libmpv + Qt are cross-platform).

## Status (v0.1.0)

This is iteration **1 + 2 + 3** of a multi-iteration build. Implemented:

**Playback** — frame-accurate seek, frame stepping (`◀ ▶|`), variable speed with audio time-stretch (0.10× → 4×), looping, in/out range, audio offset, volume, mute, RAM-cached playback via libmpv, always-on-top, fullscreen.

**Annotations** — pen, highlighter, arrow, rectangle, ellipse, eraser (last stroke), laser pointer. Foreground / background layers. Per-frame storage (resolution-independent: normalized coords). Held frames (annotation persists across N frames). Ghosting (preview annotations from prev/next frame). Color picker + presets, adjustable width.

**Bookmarks** — frame bookmarks, range bookmarks (uses current in/out), cycle next/prev, dock panel listing all bookmarks with seek-on-double-click. Annotated frames appear as ticks on the timeline.

**Project** — save/load `.kproj` (JSON) with sources, bookmarks, annotations, fps, speed, loop mode.

Planned for next iterations: timeline (multi-source), A/B compare + split viewers, timeline export via ffmpeg, Python client API (Maya/Blender/Houdini sync), customizable hotkeys.

## Installation

### Ubuntu / Debian / Mint

```bash
./install-deps.sh
```

Or manually:

```bash
sudo apt install python3-venv python3-pip libmpv2 mpv ffmpeg \
    libxkbcommon-x11-0 libxcb-cursor0 libegl1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Fedora (Workstation)

```bash
./install-deps.sh
```

Or manually:

```bash
sudo dnf install python3 python3-pip mpv mpv-libs ffmpeg \
    libxkbcommon-x11 xcb-util-cursor mesa-libEGL
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Fedora Kinoite / Silverblue (immutable)

The base system is immutable, so you have two options:

**Option A — distrobox/toolbox (recommended):**

```bash
toolbox create --image registry.fedoraproject.org/fedora-toolbox:latest kpro
toolbox enter kpro
sudo dnf install python3 python3-pip mpv mpv-libs ffmpeg \
    libxkbcommon-x11 xcb-util-cursor mesa-libEGL
cd /path/to/keyframe-pro-linux
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

**Option B — layer with rpm-ostree (requires reboot):**

```bash
rpm-ostree install mpv mpv-libs ffmpeg python3-pip
systemctl reboot
# then continue with venv install as in Fedora Workstation
```

### Arch / Manjaro

```bash
sudo pacman -S python python-pip mpv ffmpeg libxkbcommon-x11 xcb-util-cursor
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### openSUSE

```bash
sudo zypper install python3 python3-pip mpv libmpv2 ffmpeg \
    libxkbcommon-x11-0 libxcb-cursor0
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### macOS

```bash
brew install mpv ffmpeg python@3.12
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Windows

Install [Python 3.11+](https://python.org), install [mpv](https://mpv.io/) and put `mpv-2.dll` (or `libmpv-2.dll`) on your PATH. Then:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
./run.sh                    # GUI
./run.sh /path/to/file.mp4  # open video on launch
./run.sh --project foo.kproj
```

## Hotkeys

| Key | Action |
|---|---|
| Space | Play / Pause |
| ← / → | Step ±1 frame |
| Shift+← / Shift+→ | Step ±10 frames |
| Home / End | Jump to start / end |
| I / O | Set In / Out |
| Shift+X | Clear In/Out |
| B | Add bookmark at current frame |
| Shift+B | Add range bookmark (uses In/Out) |
| [ / ] | Previous / Next bookmark |
| A | Toggle annotate mode |
| Ctrl+Z | Undo last stroke (current frame) |
| M | Mute |
| F | Fullscreen |
| T | Always on top |

## Architecture

```
src/keyframe_pro/
├── __main__.py           # CLI entry
├── app.py                # QApplication + dark theme
├── main_window.py        # Wires everything
├── player/
│   └── mpv_player.py     # libmpv embedded in QWidget
├── widgets/
│   ├── timeline.py           # Custom scrubber w/ bookmark+annotation marks
│   ├── transport.py          # Play/step/speed/loop/audio controls
│   ├── annotation.py         # Drawing overlay (transparent)
│   ├── annotation_toolbar.py # Tool/color/width pickers
│   └── bookmark_panel.py     # Bookmark list dock
└── core/
    ├── bookmarks.py      # BookmarkModel
    ├── annotations.py    # AnnotationModel (per-frame strokes)
    └── project.py        # Save/load .kproj
```

## Known limitations (current iteration)

- Single source only (multi-source timeline coming next).
- No A/B compare yet.
- No export-to-video (planned via ffmpeg).
- "Ping-pong" loop mode currently behaves as loop (mpv has no native reverse playback for real-time audio).
- Wayland: tested via XWayland. Native Wayland embedding requires `mpv` render API integration — planned.

## License

MIT (see LICENSE).
