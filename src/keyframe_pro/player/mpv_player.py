from __future__ import annotations

import locale
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal, QTimer, QPointF
from PySide6.QtGui import QMouseEvent, QWheelEvent
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
    mouse_scrubbed = Signal(int)            # new frame from drag-scrub

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

        # Pan / zoom state (mpv: video-zoom is log2 scale, pan-x/y are 0..1)
        self._zoom_log2: float = 0.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._panning: bool = False
        self._pan_anchor: Optional[QPointF] = None
        self._pan_start: tuple[float, float] = (0.0, 0.0)

        # Variable mouse scrub (Shift + left-drag horizontally)
        self._mouse_scrub_enabled: bool = True
        self._mouse_scrub_active: bool = False
        self._mouse_scrub_anchor_x: float = 0.0
        self._mouse_scrub_start_frame: int = 0
        self._mouse_scrub_pixels_per_frame: float = 4.0
        # Emitted with the new frame index when the user drag-scrubs.
        # Wired by the host so the timeline + B player can update.

        # Audio scrub: when user scrubs while paused, briefly unpause to
        # produce an audible "scratch" sample at the new position.
        self._scrub_audio_enabled: bool = False
        self._scrub_audio_blip_ms: int = 90
        self._scrub_audio_timer = QTimer(self)
        self._scrub_audio_timer.setSingleShot(True)
        self._scrub_audio_timer.timeout.connect(self._end_scrub_blip)
        self._scrub_blipping: bool = False

        # Ping-pong: mpv has no native reverse-with-audio, so we drive
        # backward playback ourselves with a frame-step QTimer. Audio is
        # muted during the reverse phase.
        self._pp_reversing: bool = False
        self._pp_was_muted: bool = False
        self._pp_in_frame: int = 0
        self._pp_out_frame: int = 0
        self._pp_timer = QTimer(self)
        self._pp_timer.timeout.connect(self._pingpong_tick)

        # Property observers — these run on mpv's thread; marshal to Qt thread
        # via QTimer.singleShot(0, ...) when emitting signals that touch UI.
        self._mpv.observe_property("time-pos", self._on_time_pos)
        self._mpv.observe_property("duration", self._on_duration)
        self._mpv.observe_property("estimated-vf-fps", self._on_fps)
        self._mpv.observe_property("container-fps", self._on_fps)
        self._mpv.observe_property("pause", self._on_pause)
        self._mpv.observe_property("eof-reached", self._on_eof)

    # ---------- file ops ----------

    def load_file(self, path: str, audio_override: Optional[str] = None) -> None:
        self._mpv.command("loadfile", path, "replace")
        # Wait briefly then emit signal — the file-loaded event is async,
        # but consumers usually want to know immediately for UI seeding.
        QTimer.singleShot(150, lambda: self.file_loaded.emit(path))
        if audio_override:
            # mpv needs the file loaded first before we can add an external
            # audio track; defer slightly.
            QTimer.singleShot(250, lambda p=audio_override: self._set_audio_override(p))

    def _set_audio_override(self, audio_path: str) -> None:
        try:
            self._mpv.command("audio-add", audio_path, "select")
        except Exception:
            pass

    def set_audio_track_file(self, audio_path: str) -> None:
        """Add an external audio file as a new track and select it."""
        self._set_audio_override(audio_path)

    def load_image_sequence(self, mpv_url: str, fps: float = 24.0) -> None:
        """Load an mf:// URL describing an image sequence."""
        try:
            self._mpv.set_property("mf-fps", float(fps))
        except Exception:
            pass
        self._mpv.command("loadfile", mpv_url, "replace")
        QTimer.singleShot(150, lambda: self.file_loaded.emit(mpv_url))

    def load_playlist(self, paths: list[str]) -> None:
        """Load multiple files as a playlist; mpv plays them back-to-back."""
        if not paths:
            return
        self._mpv.command("loadfile", paths[0], "replace")
        for p in paths[1:]:
            self._mpv.command("loadfile", p, "append")
        QTimer.singleShot(150, lambda p=paths[0]: self.file_loaded.emit(p))

    def playlist_index(self, index: int) -> None:
        try:
            self._mpv.playlist_pos = int(index)
        except Exception:
            pass

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
        """'none' | 'loop' | 'pingpong'

        For 'pingpong' we disable mpv's own loop and instead trigger a
        reverse phase via _start_reverse() when the playhead reaches the
        out-frame (host signals this when in/out range is enforced).
        """
        self._loop_mode = mode
        if mode == "loop":
            self._mpv.loop_file = "inf"
        else:
            self._mpv.loop_file = "no"
        if mode != "pingpong":
            self._stop_reverse()

    def loop_mode(self) -> str:
        return self._loop_mode

    # ---------- ping-pong ----------

    def set_pingpong_range(self, in_frame: int, out_frame: int) -> None:
        self._pp_in_frame = max(0, int(in_frame))
        self._pp_out_frame = max(self._pp_in_frame, int(out_frame))

    def is_reversing(self) -> bool:
        return self._pp_reversing

    def trigger_pingpong_at_end(self) -> None:
        """Call when the host detects the playhead has reached out_frame
        and loop mode is pingpong. Starts the reverse phase."""
        if self._loop_mode != "pingpong":
            return
        if self._pp_reversing:
            return
        self._start_reverse()

    def _start_reverse(self) -> None:
        self._pp_reversing = True
        try:
            self._pp_was_muted = bool(self._mpv.mute)
            self._mpv.mute = True
            self._mpv.pause = True
        except Exception:
            pass
        # Step ~at-the-FPS rate; minimum 30 ms to avoid CPU spikes
        period_ms = max(30, int(1000.0 / max(1.0, self._fps)))
        self._pp_timer.start(period_ms)

    def _stop_reverse(self) -> None:
        if not self._pp_reversing:
            return
        self._pp_reversing = False
        self._pp_timer.stop()
        try:
            self._mpv.mute = self._pp_was_muted
        except Exception:
            pass

    def _pingpong_tick(self) -> None:
        if not self._pp_reversing:
            self._pp_timer.stop()
            return
        cur = self.current_frame()
        if cur <= self._pp_in_frame:
            # Reached the start of the range — flip back to forward play
            self._stop_reverse()
            try:
                self._mpv.pause = False
            except Exception:
                pass
            return
        try:
            self._mpv.command("frame-back-step")
        except Exception:
            pass

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

    def scrub_to_frame(self, frame: int) -> None:
        """Like seek_frame but also produces an audio blip if scrub-audio is on."""
        self.seek_frame(frame)
        self._maybe_audio_blip()

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

    # ---------- pan / zoom ----------

    def set_zoom(self, log2_factor: float) -> None:
        """video-zoom in log2 (0=100%, 1=200%, -1=50%). Clamped to [-3, 3]."""
        z = max(-3.0, min(3.0, float(log2_factor)))
        self._zoom_log2 = z
        try:
            self._mpv.video_zoom = z
        except Exception:
            pass

    def zoom(self) -> float:
        return self._zoom_log2

    def set_pan(self, pan_x: float, pan_y: float) -> None:
        """video-pan-x/y in [-3, 3] (mpv accepts arbitrary; clamp for sanity)."""
        self._pan_x = max(-3.0, min(3.0, float(pan_x)))
        self._pan_y = max(-3.0, min(3.0, float(pan_y)))
        try:
            self._mpv.video_pan_x = self._pan_x
            self._mpv.video_pan_y = self._pan_y
        except Exception:
            pass

    def reset_view(self) -> None:
        self.set_zoom(0.0)
        self.set_pan(0.0, 0.0)

    # ---------- screenshot ----------

    def screenshot(self, path: str, include_overlays: bool = False) -> bool:
        """Save the current frame to `path`. Returns True on success.

        include_overlays=False writes the raw video frame.
        include_overlays=True writes what's currently on screen (with OSD).
        """
        try:
            target = "window" if include_overlays else "video"
            self._mpv.command("screenshot-to-file", str(path), target)
            return Path(path).exists()
        except Exception:
            return False

    # ---------- scrub audio ----------

    def set_scrub_audio(self, enabled: bool) -> None:
        self._scrub_audio_enabled = bool(enabled)
        if not enabled and self._scrub_blipping:
            self._end_scrub_blip()

    def scrub_audio_enabled(self) -> bool:
        return self._scrub_audio_enabled

    def _maybe_audio_blip(self) -> None:
        """Briefly unpause to make audio audible at the new scrub position."""
        if not self._scrub_audio_enabled:
            return
        try:
            if not bool(self._mpv.pause):
                return  # already playing — natural audio handles it
        except Exception:
            return
        try:
            self._mpv.pause = False
            self._scrub_blipping = True
            self._scrub_audio_timer.start(self._scrub_audio_blip_ms)
        except Exception:
            self._scrub_blipping = False

    def _end_scrub_blip(self) -> None:
        if not self._scrub_blipping:
            return
        self._scrub_blipping = False
        try:
            self._mpv.pause = True
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

    # ---------- mouse: pan / zoom ----------

    def wheelEvent(self, ev: QWheelEvent) -> None:
        # Zoom step: 1/8 octave per wheel notch; ctrl = finer
        delta = ev.angleDelta().y()
        if delta == 0:
            return
        step = 1.0 / 8.0
        if ev.modifiers() & Qt.ControlModifier:
            step = 1.0 / 32.0
        self.set_zoom(self._zoom_log2 + (step if delta > 0 else -step))
        ev.accept()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_anchor = ev.position()
            self._pan_start = (self._pan_x, self._pan_y)
            self.setCursor(Qt.ClosedHandCursor)
            ev.accept()
            return
        # Shift+Left-drag: variable scrubbing
        if (ev.button() == Qt.LeftButton
                and self._mouse_scrub_enabled
                and (ev.modifiers() & Qt.ShiftModifier)):
            self._mouse_scrub_active = True
            self._mouse_scrub_anchor_x = ev.position().x()
            self._mouse_scrub_start_frame = self.current_frame()
            self.setCursor(Qt.SizeHorCursor)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._panning and self._pan_anchor is not None:
            w = max(self.width(), 1)
            h = max(self.height(), 1)
            dx = (ev.position().x() - self._pan_anchor.x()) / w
            dy = (ev.position().y() - self._pan_anchor.y()) / h
            self.set_pan(self._pan_start[0] + dx, self._pan_start[1] + dy)
            ev.accept()
            return
        if self._mouse_scrub_active:
            dx = ev.position().x() - self._mouse_scrub_anchor_x
            # Slow-down with Ctrl for fine scrubbing
            ppf = (self._mouse_scrub_pixels_per_frame * 4
                   if (ev.modifiers() & Qt.ControlModifier)
                   else self._mouse_scrub_pixels_per_frame)
            new_frame = int(round(self._mouse_scrub_start_frame + dx / ppf))
            new_frame = max(0, min(new_frame, max(0, self.total_frames() - 1)))
            self.scrub_to_frame(new_frame)
            self.mouse_scrubbed.emit(new_frame)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self._pan_anchor = None
            self.unsetCursor()
            ev.accept()
            return
        if ev.button() == Qt.LeftButton and self._mouse_scrub_active:
            self._mouse_scrub_active = False
            self.unsetCursor()
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.LeftButton:
            self.reset_view()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

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
