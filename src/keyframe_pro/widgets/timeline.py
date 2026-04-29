from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QMouseEvent
from PySide6.QtWidgets import QWidget, QSizePolicy

from ..core.bookmarks import BookmarkModel


class TimelineWidget(QWidget):
    """Custom scrubber that paints bookmarks and annotated frames as marks."""

    seeked = Signal(int)              # frame
    range_changed = Signal(int, int)  # in, out (frames)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

        self._total_frames: int = 1
        self._current_frame: int = 0
        self._in_frame: int = 0
        self._out_frame: int = 0
        self._bookmarks: Optional[BookmarkModel] = None
        self._annotated_frames: list[int] = []
        self._dragging: bool = False
        self._dragging_in: bool = False
        self._dragging_out: bool = False
        # 'global' = show 0..total_frames; 'range' = show in..out only
        self._view_mode: str = "global"

    # --- setters ---

    def set_total_frames(self, n: int) -> None:
        self._total_frames = max(1, int(n))
        if self._out_frame == 0 or self._out_frame > self._total_frames - 1:
            self._out_frame = self._total_frames - 1
        self.update()

    def set_current_frame(self, f: int) -> None:
        self._current_frame = max(0, min(int(f), self._total_frames - 1))
        self.update()

    def set_in_out(self, in_f: int, out_f: int) -> None:
        self._in_frame = max(0, in_f)
        self._out_frame = min(self._total_frames - 1, out_f)
        self.update()

    def in_frame(self) -> int:
        return self._in_frame

    def out_frame(self) -> int:
        return self._out_frame

    def set_bookmarks(self, model: BookmarkModel) -> None:
        if self._bookmarks is not None:
            try:
                self._bookmarks.changed.disconnect(self.update)
            except Exception:
                pass
        self._bookmarks = model
        if model is not None:
            model.changed.connect(self.update)
        self.update()

    def set_annotated_frames(self, frames: list[int]) -> None:
        self._annotated_frames = list(frames)
        self.update()

    def set_view_mode(self, mode: str) -> None:
        if mode in ("global", "range"):
            self._view_mode = mode
            self.update()

    def view_mode(self) -> str:
        return self._view_mode

    # --- helpers ---

    def _domain(self) -> tuple[int, int]:
        """Return the (lo, hi) frame range currently shown by the widget."""
        if self._view_mode == "range":
            lo = max(0, self._in_frame)
            hi = max(lo + 1, self._out_frame)
            return lo, hi
        return 0, max(1, self._total_frames - 1)

    def _frame_to_x(self, frame: int) -> float:
        lo, hi = self._domain()
        span = max(1, hi - lo)
        w = self.width()
        return ((frame - lo) / span) * w

    def _x_to_frame(self, x: float) -> int:
        if self.width() <= 0:
            return 0
        lo, hi = self._domain()
        span = max(1, hi - lo)
        f = int(round((x / self.width()) * span + lo))
        # In range mode, clamp to [lo, hi]; in global mode, [0, total-1]
        if self._view_mode == "range":
            return max(lo, min(f, hi))
        return max(0, min(f, self._total_frames - 1))

    # --- paint ---

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()

        bg = QColor("#1e1e22")
        track = QColor("#2b2b30")
        played = QColor("#4a90e2")
        in_out = QColor("#3a3a44")
        bookmark_default = QColor("#ffcc00")
        ann_color = QColor("#22cc77")
        playhead = QColor("#ff5555")

        p.fillRect(rect, bg)

        # Track bar
        track_rect = QRectF(0, rect.height() / 2 - 4, rect.width(), 8)
        p.fillRect(track_rect, track)

        # In/out region
        x_in = self._frame_to_x(self._in_frame)
        x_out = self._frame_to_x(self._out_frame)
        in_rect = QRectF(x_in, rect.height() / 2 - 4, max(1.0, x_out - x_in), 8)
        p.fillRect(in_rect, in_out)

        # Played portion (in -> current if current is inside in/out)
        if self._in_frame <= self._current_frame <= self._out_frame:
            x_cur = self._frame_to_x(self._current_frame)
            played_rect = QRectF(x_in, rect.height() / 2 - 4, max(0, x_cur - x_in), 8)
            p.fillRect(played_rect, played)

        # Annotated frame ticks (above bar)
        p.setPen(QPen(ann_color, 1.2))
        for f in self._annotated_frames:
            x = self._frame_to_x(f)
            p.drawLine(QPointF(x, rect.height() / 2 - 14), QPointF(x, rect.height() / 2 - 6))

        # Bookmark ticks (below bar)
        if self._bookmarks is not None:
            for b in self._bookmarks.all():
                col = QColor(b.color) if b.color else bookmark_default
                if b.is_range and b.frame_out is not None:
                    x1 = self._frame_to_x(b.frame_in)
                    x2 = self._frame_to_x(b.frame_out)
                    p.fillRect(
                        QRectF(x1, rect.height() / 2 + 6, max(2.0, x2 - x1), 6),
                        QBrush(col),
                    )
                else:
                    x = self._frame_to_x(b.frame_in)
                    p.setPen(QPen(col, 2))
                    p.drawLine(
                        QPointF(x, rect.height() / 2 + 6),
                        QPointF(x, rect.height() / 2 + 16),
                    )

        # In/out handles
        p.setPen(QPen(QColor("#aaaaaa"), 2))
        p.drawLine(QPointF(x_in, 4), QPointF(x_in, rect.height() - 4))
        p.drawLine(QPointF(x_out, 4), QPointF(x_out, rect.height() - 4))

        # Playhead
        x_play = self._frame_to_x(self._current_frame)
        p.setPen(QPen(playhead, 2))
        p.drawLine(QPointF(x_play, 0), QPointF(x_play, rect.height()))

        p.end()

    # --- mouse ---

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() != Qt.LeftButton:
            return
        x = ev.position().x()
        x_in = self._frame_to_x(self._in_frame)
        x_out = self._frame_to_x(self._out_frame)
        # Hit test handles (within 6 px)
        if abs(x - x_in) <= 6:
            self._dragging_in = True
            return
        if abs(x - x_out) <= 6:
            self._dragging_out = True
            return
        self._dragging = True
        self.seeked.emit(self._x_to_frame(x))

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        x = ev.position().x()
        if self._dragging_in:
            f = self._x_to_frame(x)
            self._in_frame = min(f, self._out_frame - 1)
            self.range_changed.emit(self._in_frame, self._out_frame)
            self.update()
        elif self._dragging_out:
            f = self._x_to_frame(x)
            self._out_frame = max(f, self._in_frame + 1)
            self.range_changed.emit(self._in_frame, self._out_frame)
            self.update()
        elif self._dragging:
            self.seeked.emit(self._x_to_frame(x))

    def mouseReleaseEvent(self, _ev: QMouseEvent) -> None:
        self._dragging = False
        self._dragging_in = False
        self._dragging_out = False
