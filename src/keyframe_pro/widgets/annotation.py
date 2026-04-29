from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QMouseEvent, QPixmap, QPainterPath
)
from PySide6.QtWidgets import QWidget

from ..core.annotations import AnnotationModel, Stroke


class AnnotationOverlay(QWidget):
    """Transparent overlay placed on top of the mpv widget.

    Captures pen input when active and renders strokes for the current frame.
    Stores normalized coordinates (0..1) so strokes survive resize.
    """

    laser_moved = Signal(QPointF)

    TOOL_PEN = "pen"
    TOOL_HIGHLIGHTER = "highlighter"
    TOOL_ARROW = "arrow"
    TOOL_RECT = "rect"
    TOOL_ELLIPSE = "ellipse"
    TOOL_ERASER = "eraser"
    TOOL_LASER = "laser"

    def __init__(self, model: AnnotationModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._model = model
        self._frame: int = 0
        self._tool: str = self.TOOL_PEN
        self._color: QColor = QColor("#ff2222")
        self._width: float = 3.0
        self._layer: str = "fg"
        self._active: bool = False
        self._drawing: bool = False
        self._current_points: list[tuple[float, float]] = []
        self._ghost_prev: bool = False
        self._ghost_next: bool = False
        self._laser_pos: Optional[QPointF] = None

        self._model.changed.connect(self._on_model_changed)

    # --- public api ---

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not active)
        self.update()

    def is_active(self) -> bool:
        return self._active

    def set_frame(self, frame: int) -> None:
        if frame == self._frame:
            return
        self._frame = frame
        self.update()

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        self.update()

    def tool(self) -> str:
        return self._tool

    def set_color(self, color: str) -> None:
        self._color = QColor(color)

    def color(self) -> str:
        return self._color.name()

    def set_width(self, width: float) -> None:
        self._width = float(width)

    def width_value(self) -> float:
        return self._width

    def set_layer(self, layer: str) -> None:
        self._layer = layer

    def set_ghost(self, prev: bool, next_: bool) -> None:
        self._ghost_prev = prev
        self._ghost_next = next_
        self.update()

    # --- normalization ---

    def _to_norm(self, pt: QPointF) -> tuple[float, float]:
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        return (pt.x() / w, pt.y() / h)

    def _from_norm(self, p: tuple[float, float]) -> QPointF:
        return QPointF(p[0] * self.width(), p[1] * self.height())

    # --- mouse ---

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if not self._active:
            return
        if self._tool == self.TOOL_LASER:
            self._laser_pos = ev.position()
            self.update()
            return
        if self._tool == self.TOOL_ERASER:
            # Erase last stroke on this frame
            self._model.remove_last(self._frame)
            return
        if ev.button() == Qt.LeftButton:
            self._drawing = True
            self._current_points = [self._to_norm(ev.position())]
            self.update()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if not self._active:
            return
        if self._tool == self.TOOL_LASER:
            self._laser_pos = ev.position()
            self.laser_moved.emit(ev.position())
            self.update()
            return
        if self._drawing:
            self._current_points.append(self._to_norm(ev.position()))
            self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if not self._active:
            return
        if self._drawing and ev.button() == Qt.LeftButton:
            self._drawing = False
            if len(self._current_points) >= 2 or self._tool in (
                self.TOOL_RECT, self.TOOL_ELLIPSE
            ):
                stroke = Stroke(
                    points=self._current_points,
                    color=self._color.name(),
                    width=self._width,
                    layer=self._layer,
                    tool=self._tool,
                )
                self._model.add_stroke(self._frame, stroke)
            self._current_points = []
            self.update()

    def leaveEvent(self, _ev) -> None:
        if self._tool == self.TOOL_LASER:
            self._laser_pos = None
            self.update()

    def _on_model_changed(self, _frame: int) -> None:
        self.update()

    # --- paint ---

    def _draw_stroke(self, p: QPainter, stroke: Stroke, alpha: float = 1.0) -> None:
        if not stroke.points:
            return
        col = QColor(stroke.color)
        if stroke.tool == self.TOOL_HIGHLIGHTER:
            col.setAlphaF(0.35 * alpha)
        else:
            col.setAlphaF(min(1.0, alpha))
        pen = QPen(col, stroke.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        if stroke.tool in (self.TOOL_PEN, self.TOOL_HIGHLIGHTER):
            path = QPainterPath()
            path.moveTo(self._from_norm(stroke.points[0]))
            for pt in stroke.points[1:]:
                path.lineTo(self._from_norm(pt))
            p.drawPath(path)
        elif stroke.tool == self.TOOL_ARROW:
            if len(stroke.points) >= 2:
                a = self._from_norm(stroke.points[0])
                b = self._from_norm(stroke.points[-1])
                p.drawLine(a, b)
                # Arrow head
                from math import atan2, cos, sin, pi
                ang = atan2(b.y() - a.y(), b.x() - a.x())
                size = max(8.0, stroke.width * 3)
                left = QPointF(
                    b.x() - size * cos(ang - pi / 6),
                    b.y() - size * sin(ang - pi / 6),
                )
                right = QPointF(
                    b.x() - size * cos(ang + pi / 6),
                    b.y() - size * sin(ang + pi / 6),
                )
                p.drawLine(b, left)
                p.drawLine(b, right)
        elif stroke.tool == self.TOOL_RECT:
            if len(stroke.points) >= 2:
                a = self._from_norm(stroke.points[0])
                b = self._from_norm(stroke.points[-1])
                p.drawRect(min(a.x(), b.x()), min(a.y(), b.y()),
                           abs(b.x() - a.x()), abs(b.y() - a.y()))
        elif stroke.tool == self.TOOL_ELLIPSE:
            if len(stroke.points) >= 2:
                a = self._from_norm(stroke.points[0])
                b = self._from_norm(stroke.points[-1])
                p.drawEllipse(
                    int(min(a.x(), b.x())),
                    int(min(a.y(), b.y())),
                    int(abs(b.x() - a.x())),
                    int(abs(b.y() - a.y())),
                )

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Ghost previous frame
        if self._ghost_prev and self._frame > 0:
            for s in self._model.strokes_for_frame(self._frame - 1):
                self._draw_stroke(p, s, alpha=0.3)
        if self._ghost_next:
            for s in self._model.strokes_for_frame(self._frame + 1):
                self._draw_stroke(p, s, alpha=0.3)

        # Background-layer strokes for this frame
        for s in self._model.strokes_for_frame(self._frame):
            if s.layer == "bg":
                self._draw_stroke(p, s)

        # In-progress stroke
        if self._drawing and self._current_points:
            tmp = Stroke(
                points=self._current_points,
                color=self._color.name(),
                width=self._width,
                layer=self._layer,
                tool=self._tool,
            )
            self._draw_stroke(p, tmp)

        # Foreground-layer strokes
        for s in self._model.strokes_for_frame(self._frame):
            if s.layer == "fg":
                self._draw_stroke(p, s)

        # Laser
        if self._tool == self.TOOL_LASER and self._laser_pos is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 30, 30, 220)))
            p.drawEllipse(self._laser_pos, 8, 8)
            p.setBrush(QBrush(QColor(255, 120, 120, 90)))
            p.drawEllipse(self._laser_pos, 18, 18)

        p.end()
