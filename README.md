# Keyframe Pro Linux

Cross-platform animation reference player inspired by [Keyframe Pro 2](https://zurbrigg.com/keyframe-pro-2). Built with Python, PySide6 (Qt 6), and libmpv. Runs natively on Linux (Ubuntu, Fedora, Arch, openSUSE, Fedora Kinoite/Silverblue via toolbox), and works on macOS / Windows with the same code (libmpv + Qt are cross-platform).

## Status (v0.4.0)

Iterations **1–9 + UX pass + medium pass** complete:

**Playback** — frame-accurate seek, frame stepping, variable speed with audio time-stretch (0.10× → 4×), looping, in/out range, audio offset, volume, mute, RAM-cached playback via libmpv, always-on-top, fullscreen. **Pan & zoom** (mouse wheel zoom around cursor, middle-drag pan, double-click reset, +/− hotkeys). **Audio scrub** mode — brief audible blip while scrubbing the timeline.

**Annotations** — pen, highlighter, arrow, rectangle, ellipse, **text** (with QInputDialog input + drop-shadow rendering), eraser, laser pointer. Foreground / background layers. Per-frame storage (normalized coords). Held frames. Ghosting (prev/next frame preview). Color picker + presets, adjustable width.

**Bookmarks** — frame, range, and **annotation-kind** bookmarks. Cycle next/prev, dock panel with **color dot icons**, **right-click context menu** (Go to / Edit / Delete), **bookmark editor dialog** (name, color picker, kind, in/out, note), **Sync Annotation Bookmarks** button to auto-generate bookmarks for every annotated frame.

**HUD overlay** — toggleable on-viewer display of frame / time / fps. Selectable corner position (top-left, top-right, bottom-left, bottom-right).

**Mouse scrubbing** — Shift + left-drag horizontally on the video to scrub. Ctrl modifier slows it 4× for fine adjustment.

**Multi-source timeline** — add multiple sources, reorder via drag, **per-clip in/out + label + audio override editor dialog**. **Audio override** is wired into mpv (`audio-add … select`) so the chosen audio file replaces the source's own audio when the clip is loaded. Source dock panel, double-click to activate, "Edit…" to edit.

**Files** — drag-and-drop video files into the window (single = load; multiple = add to timeline). **Recent files** menu (last 12, auto-pruned). **Save Screenshot** of current frame to `~/Pictures/keyframe-pro/`.

**A/B/C/D compare** — up to 4 mpv instances. Modes: A-only, B-only, wipe (mouse-drag the seam), split-V, split-H, **grid 2×2** (4 sources), **flicker** (rapid A/B alternation, the classic animator's flip-compare). Adjustable flicker interval (40–2000 ms). Sync toggle.

**Export** — ffmpeg-based export with codec choice (x264, x265, ProRes, VP9, GIF), CRF/preset, FPS, optional resize, with/without audio, live ffmpeg log + progress.

**Python client API** — TCP JSON server on 127.0.0.1:18765. Commands: `ping`, `set_frame`, `get_frame`, `load_file`, `play`, `pause`, `set_fps`, `add_bookmark`, `info`. Includes `KproClient` and example Maya/Blender sync scripts.

**Hotkey customization** — Preferences dialog to remap any shortcut, conflict detection, reset-to-defaults. Persists via QSettings.

**Native Wayland** — experimental `RenderMpvPlayer` using libmpv render API + QOpenGLWidget for native Wayland embedding (default `MpvPlayer` uses wid embedding which works on X11 / XWayland).

**Project** — save/load `.kproj` (JSON) with sources, bookmarks, annotations, fps, speed, loop mode.

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
| Shift+A | Toggle audio scrub |
| Ctrl+Z | Undo last stroke (current frame) |
| M | Mute |
| F | Fullscreen |
| T | Always on top |
| 1–7 | Compare modes (A / B / Wipe / Split V / Split H / Grid 2×2 / Flicker) |
| H | Toggle HUD |
| Ctrl+Shift+B | Sync annotation bookmarks |
| Shift+Left-drag | Variable mouse scrub on video (Ctrl = fine) |
| S | Save screenshot |
| Shift+R | Reset pan/zoom |
| + / − | Zoom in / out |
| Ctrl+S | File → Save Screenshot |
| Ctrl+E | Export Timeline |
| Wheel | Zoom (Ctrl+Wheel = finer) |
| Middle-drag | Pan |
| Double-click | Reset view |

All hotkeys can be remapped via **Edit → Preferences (Hotkeys)**.

## Architecture

```
src/keyframe_pro/
├── __main__.py             # CLI entry
├── app.py                  # QApplication + dark theme
├── main_window.py          # Wires everything
├── player/
│   ├── mpv_player.py       # libmpv embedded via wid (X11/XWayland)
│   └── wayland_player.py   # libmpv render API (native Wayland)
├── widgets/
│   ├── timeline.py             # Scrubber w/ bookmark+annotation ticks
│   ├── transport.py            # Play/step/speed/loop/audio controls
│   ├── annotation.py           # Drawing overlay
│   ├── annotation_toolbar.py   # Tool/color/width pickers
│   ├── bookmark_panel.py       # Bookmark list dock
│   ├── source_panel.py         # Multi-source list dock
│   ├── compare_view.py         # A/B layout (single/wipe/split)
│   ├── compare_toolbar.py      # Compare mode controls
│   ├── export_dialog.py        # ffmpeg export UI + worker
│   └── preferences.py          # Hotkey editor
├── core/
│   ├── bookmarks.py        # BookmarkModel
│   ├── annotations.py      # AnnotationModel (per-frame strokes)
│   ├── timeline.py         # Multi-source Timeline + SourceClip
│   ├── settings.py         # QSettings + hotkey defaults
│   ├── export.py           # ffmpeg command builder
│   └── project.py          # Save/load .kproj
└── api/
    ├── server.py           # TCP JSON command server (port 18765)
    └── client.py           # Stdlib-only client lib for DCCs

scripts/
├── maya_sync.py            # Maya scriptJob → push frame to KPro
└── blender_sync.py         # Blender frame_change_post handler
```

## Maya / Blender sync

Start KPro, then in Maya's script editor:

```python
import sys; sys.path.insert(0, "/path/to/keyframe-pro-linux/scripts")
import maya_sync
maya_sync.start_sync()                         # current frame → KPro
maya_sync.send_playblast("/tmp/blast.mp4")     # load a playblast
maya_sync.bookmark_current_frame("Beat 1")
```

In Blender:

```python
import sys; sys.path.insert(0, "/path/to/keyframe-pro-linux/scripts")
import blender_sync
blender_sync.start_sync()
```

## Known limitations

- Wipe compare uses widget clipping; a true GPU shader compare (with transparency mode) would need both players to render through the libmpv render API and composite — planned.
- "Ping-pong" loop mode currently behaves as loop (mpv has no native reverse-with-audio).
- `wayland_player.py` is experimental — depends on python-mpv exposing `MpvRenderContext`.

## License

MIT (see LICENSE).
