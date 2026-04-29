"""Frame number / time / fps HUD drawn on top of the viewer."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PySide6.QtWidgets import QWidget


class HudOverlay(QWidget):
    """Read-only overlay that shows frame, time, fps in the corner.

    Made transparent to mouse events so it never blocks the viewer.
    """

    POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._frame: int = 0
        self._total: int = 0
        self._fps: float = 24.0
        self._time: float = 0.0
        self._visible: bool = False
        self._position: str = "top_left"
        self._extra_text: str = ""

    def set_visible(self, on: bool) -> None:
        self._visible = on
        self.setVisible(on)
        self.update()

    def set_position(self, pos: str) -> None:
        if pos in self.POSITIONS:
            self._position = pos
            self.update()

    def set_extra(self, text: str) -> None:
        self._extra_text = text
        self.update()

    def set_state(self, frame: int, total: int, fps: float, time_sec: float) -> None:
        self._frame = int(frame)
        self._total = int(total)
        self._fps = float(fps) if fps > 0 else 24.0
        self._time = float(time_sec)
        self.update()

    def paintEvent(self, _ev) -> None:
        if not self._visible:
            return
        text = (
            f"Frame: {self._frame} / {max(0, self._total - 1)}\n"
            f"Time:  {self._time:7.3f} s\n"
            f"FPS:   {self._fps:6.2f}"
        )
        if self._extra_text:
            text += f"\n{self._extra_text}"

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        font = QFont("Monospace")
        font.setStyleHint(QFont.TypeWriter)
        font.setPointSize(11)
        font.setBold(True)
        p.setFont(font)

        margin = 12
        padding = 8
        metrics = p.fontMetrics()
        line_h = metrics.lineSpacing()
        lines = text.split("\n")
        text_w = max(metrics.horizontalAdvance(l) for l in lines)
        text_h = line_h * len(lines)
        box_w = text_w + 2 * padding
        box_h = text_h + 2 * padding

        if self._position == "top_left":
            x, y = margin, margin
        elif self._position == "top_right":
            x, y = self.width() - box_w - margin, margin
        elif self._position == "bottom_left":
            x, y = margin, self.height() - box_h - margin
        else:  # bottom_right
            x, y = self.width() - box_w - margin, self.height() - box_h - margin

        p.setBrush(QBrush(QColor(0, 0, 0, 160)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(x, y, box_w, box_h), 6, 6)

        p.setPen(QPen(QColor("#ffd400")))
        ty = y + padding + metrics.ascent()
        for i, line in enumerate(lines):
            p.drawText(int(x + padding), int(ty + i * line_h), line)

        p.end()
