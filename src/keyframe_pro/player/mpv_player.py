from __future__ import annotations

import locale
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget

import mpv


class MpvPlayer(QWidget):
    """libmpv embedded into a Qt widget.

    Emits frame-position and duration changes so other widgets can sync.
    """

    position_changed = Signal(float)        # seconds
    frame_changed = Signal(int)             # current estimated frame
    duration_changed = Signal(float)        # seconds
    fps_changed = Signal(float)
    file_loaded = Signal(str)
    play_state_changed = Signal(bool)       # True = playing
    eof_reached = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # libmpv requires "C" numeric locale.
        locale.setlocale(locale.LC_NUMERIC, "C")

        # Attributes required for stable embedding.
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_NativeWindow)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMouseTracking(True)

        wid = int(self.winId())

        self._mpv = mpv.MPV(
            wid=str(wid),
            vo="gpu",
            hwdec="auto-safe",
            keep_open="yes",
            hr_seek="yes",
            audio_pitch_correction="yes",
            input_default_bindings=False,
            input_vo_keyboard=False,
            osc=False,
            osd_level=0,
        )

        self._duration: float = 0.0
        self._fps: float = 24.0
        self._position: float = 0.0
        self._playing: bool = False
        self._loop_mode: str = "loop"  # 'none' | 'loop' | 'pingpong'
        self._reverse: bool = False
        self._user_speed: float = 1.0

        # Property observers — these run on mpv's thread; marshal to Qt thread
        # via QTimer.singleShot(0, ...) when emitting signals that touch UI.
        self._mpv.observe_property("time-pos", self._on_time_pos)
        self._mpv.observe_property("duration", self._on_duration)
        self._mpv.observe_property("estimated-vf-fps", self._on_fps)
        self._mpv.observe_property("container-fps", self._on_fps)
        self._mpv.observe_property("pause", self._on_pause)
        self._mpv.observe_property("eof-reached", self._on_eof)

    # ---------- file ops ----------

    def load_file(self, path: str) -> None:
        self._mpv.command("loadfile", path, "replace")
        # Wait briefly then emit signal — the file-loaded event is async,
        # but consumers usually want to know immediately for UI seeding.
        QTimer.singleShot(150, lambda: self.file_loaded.emit(path))

    def stop(self) -> None:
        self._mpv.command("stop")

    def shutdown(self) -> None:
        try:
            self._mpv.terminate()
        except Exception:
            pass

    # ---------- playback ----------

    def play(self) -> None:
        self._mpv.pause = False

    def pause(self) -> None:
        self._mpv.pause = True

    def toggle_play(self) -> None:
        self._mpv.pause = not self._mpv.pause

    def is_playing(self) -> bool:
        return not bool(self._mpv.pause)

    def set_speed(self, speed: float) -> None:
        speed = max(0.05, min(speed, 8.0))
        self._user_speed = speed
        self._mpv.speed = speed

    def speed(self) -> float:
        return self._user_speed

    def set_volume(self, vol: float) -> None:
        self._mpv.volume = max(0.0, min(100.0, vol))

    def set_mute(self, mute: bool) -> None:
        self._mpv.mute = bool(mute)

    def set_audio_offset(self, seconds: float) -> None:
        self._mpv.audio_delay = float(seconds)

    def set_loop_mode(self, mode: str) -> None:
        """'none' | 'loop' | 'pingpong'"""
        self._loop_mode = mode
        if mode == "loop":
            self._mpv.loop_file = "inf"
        else:
            self._mpv.loop_file = "no"

    def loop_mode(self) -> str:
        return self._loop_mode

    # ---------- seek ----------

    def seek_seconds(self, seconds: float, exact: bool = True) -> None:
        seconds = max(0.0, min(seconds, max(self._duration, 0.0)))
        flag = "absolute+exact" if exact else "absolute+keyframes"
        try:
            self._mpv.command("seek", f"{seconds:.6f}", flag)
        except Exception:
            pass

    def seek_frame(self, frame: int) -> None:
        if self._fps <= 0:
            return
        self.seek_seconds(frame / self._fps, exact=True)

    def step_frame(self, n: int = 1) -> None:
        """Step n frames (negative = back)."""
        try:
            if n > 0:
                for _ in range(n):
                    self._mpv.command("frame-step")
            elif n < 0:
                for _ in range(-n):
                    self._mpv.command("frame-back-step")
        except Exception:
            pass

    # ---------- getters ----------

    def position_seconds(self) -> float:
        return self._position

    def duration_seconds(self) -> float:
        return self._duration

    def fps(self) -> float:
        return self._fps

    def current_frame(self) -> int:
        if self._fps <= 0:
            return 0
        return int(round(self._position * self._fps))

    def total_frames(self) -> int:
        if self._fps <= 0 or self._duration <= 0:
            return 0
        return int(round(self._duration * self._fps))

    # ---------- property callbacks (mpv thread → Qt thread) ----------

    def _on_time_pos(self, _name, value) -> None:
        if value is None:
            return
        self._position = float(value)
        QTimer.singleShot(0, lambda v=self._position: self.position_changed.emit(v))
        if self._fps > 0:
            f = int(round(self._position * self._fps))
            QTimer.singleShot(0, lambda fr=f: self.frame_changed.emit(fr))

    def _on_duration(self, _name, value) -> None:
        if value is None:
            return
        self._duration = float(value)
        QTimer.singleShot(0, lambda v=self._duration: self.duration_changed.emit(v))

    def _on_fps(self, _name, value) -> None:
        if value is None or float(value) <= 0:
            return
        self._fps = float(value)
        QTimer.singleShot(0, lambda v=self._fps: self.fps_changed.emit(v))

    def _on_pause(self, _name, value) -> None:
        playing = not bool(value)
        self._playing = playing
        QTimer.singleShot(0, lambda p=playing: self.play_state_changed.emit(p))

    def _on_eof(self, _name, value) -> None:
        if value:
            QTimer.singleShot(0, self.eof_reached.emit)
            if self._loop_mode == "pingpong":
                # Reverse direction: mpv has no native pingpong, so we flip
                # speed to negative-ish via 'speed' isn't supported. Workaround:
                # seek back to start and continue playing.
                QTimer.singleShot(50, lambda: self.seek_seconds(0))
                QTimer.singleShot(80, self.play)
