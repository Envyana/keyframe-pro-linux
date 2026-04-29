"""Native-Wayland-friendly mpv player using the libmpv render API.

The default `MpvPlayer` uses libmpv's window-id (wid) embedding which only
works on X11 (or XWayland). On native Wayland, you need to drive mpv via its
render API and feed frames into a QOpenGLWidget yourself. That is what this
module does.

This is experimental but functional. To use it, instantiate `RenderMpvPlayer`
in place of `MpvPlayer`. The public surface is intentionally similar.

Implementation notes:
- mpv's `MpvRenderContext` requires a working OpenGL context. We use
  QOpenGLWidget which gives us one.
- mpv calls `request_update` from a non-Qt thread when a new frame is ready;
  we forward that to a Qt signal so the GUI thread schedules `update()`.
- After Qt has set up the GL context for us in `paintGL()`, we ask mpv to
  render into the framebuffer that Qt is currently bound to.

Caveats:
- python-mpv's `MpvRenderContext` API is needed; older versions may not
  expose it. If import fails, the host code should fall back to MpvPlayer.
- Frame sync, vsync, and HiDPI scaling are simplified — production polish
  beyond this iteration.
"""
from __future__ import annotations

import locale
from typing import Optional

from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtGui import QOpenGLContext, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget

import mpv

try:
    from mpv import MpvRenderContext, MpvGlGetProcAddressFn  # type: ignore
    HAS_RENDER_API = True
except Exception:
    HAS_RENDER_API = False


def _get_proc_addr(_ctx, name) -> int:
    gl = QOpenGLContext.currentContext()
    if gl is None:
        return 0
    return int(gl.getProcAddress(name))


class RenderMpvPlayer(QOpenGLWidget):
    """Drop-in-ish replacement for MpvPlayer using mpv render API.

    Only the public methods/signals also present on MpvPlayer are listed here
    (others can be added as needed). Use this when running natively on
    Wayland or when X11 wid-embedding misbehaves.
    """

    position_changed = Signal(float)
    frame_changed = Signal(int)
    duration_changed = Signal(float)
    fps_changed = Signal(float)
    file_loaded = Signal(str)
    play_state_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        if not HAS_RENDER_API:
            raise RuntimeError(
                "python-mpv does not expose MpvRenderContext on this system. "
                "Use MpvPlayer (X11/XWayland) instead, or upgrade python-mpv."
            )

        locale.setlocale(locale.LC_NUMERIC, "C")

        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setSwapInterval(1)
        self.setFormat(fmt)

        self._mpv = mpv.MPV(
            vo="libmpv",
            keep_open="yes",
            hr_seek="yes",
            audio_pitch_correction="yes",
            input_default_bindings=False,
            osc=False,
        )
        self._render_ctx: Optional[MpvRenderContext] = None

        self._fps: float = 24.0
        self._duration: float = 0.0
        self._position: float = 0.0

        self._mpv.observe_property("time-pos", self._on_time_pos)
        self._mpv.observe_property("duration", self._on_duration)
        self._mpv.observe_property("estimated-vf-fps", self._on_fps)
        self._mpv.observe_property("container-fps", self._on_fps)
        self._mpv.observe_property("pause", self._on_pause)

    # --- GL lifecycle ---

    def initializeGL(self) -> None:
        # Create render context after we have a GL context
        self._render_ctx = MpvRenderContext(
            self._mpv,
            "opengl",
            opengl_init_params={"get_proc_address": _get_proc_addr},
        )
        self._render_ctx.update_cb = self._on_update_request

    def paintGL(self) -> None:
        if self._render_ctx is None:
            return
        # Render into the currently-bound default framebuffer
        ratio = self.devicePixelRatioF()
        w = int(self.width() * ratio)
        h = int(self.height() * ratio)
        try:
            self._render_ctx.render(
                flip_y=True,
                opengl_fbo={"w": w, "h": h, "fbo": self.defaultFramebufferObject()},
            )
        except Exception:
            pass

    def _on_update_request(self) -> None:
        # Called from mpv thread; marshal a paint to the Qt thread.
        QTimer.singleShot(0, self.update)

    # --- file ops & playback (subset) ---

    def load_file(self, path: str) -> None:
        self._mpv.command("loadfile", path, "replace")
        QTimer.singleShot(150, lambda: self.file_loaded.emit(path))

    def play(self) -> None:
        self._mpv.pause = False

    def pause(self) -> None:
        self._mpv.pause = True

    def toggle_play(self) -> None:
        self._mpv.pause = not self._mpv.pause

    def seek_seconds(self, sec: float) -> None:
        try:
            self._mpv.command("seek", f"{sec:.6f}", "absolute+exact")
        except Exception:
            pass

    def seek_frame(self, frame: int) -> None:
        if self._fps > 0:
            self.seek_seconds(frame / self._fps)

    def step_frame(self, n: int = 1) -> None:
        try:
            if n > 0:
                for _ in range(n):
                    self._mpv.command("frame-step")
            elif n < 0:
                for _ in range(-n):
                    self._mpv.command("frame-back-step")
        except Exception:
            pass

    def set_speed(self, s: float) -> None:
        self._mpv.speed = max(0.05, min(s, 8.0))

    def set_volume(self, v: float) -> None:
        self._mpv.volume = max(0.0, min(100.0, v))

    def set_mute(self, m: bool) -> None:
        self._mpv.mute = bool(m)

    def set_audio_offset(self, sec: float) -> None:
        self._mpv.audio_delay = float(sec)

    def set_loop_mode(self, mode: str) -> None:
        self._mpv.loop_file = "inf" if mode == "loop" else "no"

    def shutdown(self) -> None:
        try:
            if self._render_ctx is not None:
                self._render_ctx.free()
                self._render_ctx = None
            self._mpv.terminate()
        except Exception:
            pass

    # --- getters ---

    def position_seconds(self) -> float: return self._position
    def duration_seconds(self) -> float: return self._duration
    def fps(self) -> float: return self._fps
    def current_frame(self) -> int:
        return int(round(self._position * self._fps)) if self._fps else 0
    def total_frames(self) -> int:
        return int(round(self._duration * self._fps)) if self._fps else 0
    def loop_mode(self) -> str:
        return "loop"
    def is_playing(self) -> bool:
        return not bool(self._mpv.pause)

    # --- callbacks ---

    def _on_time_pos(self, _n, v):
        if v is None: return
        self._position = float(v)
        QTimer.singleShot(0, lambda x=self._position: self.position_changed.emit(x))
        if self._fps > 0:
            f = int(round(self._position * self._fps))
            QTimer.singleShot(0, lambda fr=f: self.frame_changed.emit(fr))

    def _on_duration(self, _n, v):
        if v is None: return
        self._duration = float(v)
        QTimer.singleShot(0, lambda x=self._duration: self.duration_changed.emit(x))

    def _on_fps(self, _n, v):
        if v is None or float(v) <= 0: return
        self._fps = float(v)
        QTimer.singleShot(0, lambda x=self._fps: self.fps_changed.emit(x))

    def _on_pause(self, _n, v):
        QTimer.singleShot(0, lambda p=not bool(v): self.play_state_changed.emit(p))
