from __future__ import annotations

from enum import Enum
from typing import Optional
from PySide6.QtCore import Qt, QRect, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent
from PySide6.QtWidgets import QWidget, QStackedLayout

from ..player.mpv_player import MpvPlayer


class CompareMode(str, Enum):
    SINGLE_A = "a"
    SINGLE_B = "b"
    WIPE = "wipe"
    SPLIT_H = "split_h"
    SPLIT_V = "split_v"


class CompareView(QWidget):
    """Hosts two MpvPlayer widgets and arranges them for A/B compare.

    Modes:
      - single A / single B: show one player full-rect
      - wipe: A full, B clipped to a vertical band controlled by `wipe`
      - split H: A on top, B on bottom
      - split V: A on left, B on right

    Sync is up to the controller — this widget only does layout.
    """

    wipe_changed = Signal(float)  # 0..1

    def __init__(self, player_a: MpvPlayer, player_b: MpvPlayer,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._a = player_a
        self._b = player_b
        self._mode: CompareMode = CompareMode.SINGLE_A
        self._wipe: float = 0.5     # 0 = all A, 1 = all B
        self._dragging_wipe: bool = False

        self._a.setParent(self)
        self._b.setParent(self)
        self._a.show()
        self._b.show()

        self._apply_layout()

    # --- public ---

    def player_a(self) -> MpvPlayer:
        return self._a

    def player_b(self) -> MpvPlayer:
        return self._b

    def set_mode(self, mode: CompareMode) -> None:
        self._mode = mode
        self._apply_layout()
        self.update()

    def mode(self) -> CompareMode:
        return self._mode

    def set_wipe(self, value: float) -> None:
        self._wipe = max(0.0, min(1.0, value))
        if self._mode == CompareMode.WIPE:
            self._apply_layout()
        self.update()

    def wipe(self) -> float:
        return self._wipe

    # --- layout ---

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._apply_layout()

    def _apply_layout(self) -> None:
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        if self._mode == CompareMode.SINGLE_A:
            self._a.setGeometry(0, 0, w, h)
            self._b.setGeometry(0, 0, 1, 1)
            self._b.lower()
            self._a.raise_()
            self._b.hide()
            self._a.show()
        elif self._mode == CompareMode.SINGLE_B:
            self._b.setGeometry(0, 0, w, h)
            self._a.setGeometry(0, 0, 1, 1)
            self._a.hide()
            self._b.show()
            self._b.raise_()
        elif self._mode == CompareMode.WIPE:
            # A fills full area, B clipped to right portion (width = w * wipe)
            self._a.setGeometry(0, 0, w, h)
            band_w = max(1, int(round(w * self._wipe)))
            self._b.setGeometry(w - band_w, 0, band_w, h)
            self._a.show()
            self._b.show()
            self._a.lower()
            self._b.raise_()
        elif self._mode == CompareMode.SPLIT_H:
            self._a.setGeometry(0, 0, w, h // 2)
            self._b.setGeometry(0, h // 2, w, h - h // 2)
            self._a.show()
            self._b.show()
        elif self._mode == CompareMode.SPLIT_V:
            self._a.setGeometry(0, 0, w // 2, h)
            self._b.setGeometry(w // 2, 0, w - w // 2, h)
            self._a.show()
            self._b.show()

    # --- wipe interaction ---

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if self._mode != CompareMode.WIPE or ev.button() != Qt.LeftButton:
            return
        # Only grab if click is near the wipe seam (within 10 px)
        seam_x = self.width() * (1 - self._wipe)
        if abs(ev.position().x() - seam_x) <= 10:
            self._dragging_wipe = True
            self._update_wipe_from_mouse(ev.position().x())

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._dragging_wipe:
            self._update_wipe_from_mouse(ev.position().x())

    def mouseReleaseEvent(self, _ev: QMouseEvent) -> None:
        self._dragging_wipe = False

    def _update_wipe_from_mouse(self, x: float) -> None:
        if self.width() <= 0:
            return
        # x measures distance from the LEFT edge; wipe is fraction of the
        # right side covered by B, so wipe = 1 - x/w.
        self._wipe = max(0.0, min(1.0, 1.0 - x / self.width()))
        self._apply_layout()
        self.wipe_changed.emit(self._wipe)
        self.update()

    # --- decoration ---

    def paintEvent(self, _ev) -> None:
        # Mpv widgets paint themselves. We paint a thin seam line for wipe/split.
        if self._mode in (CompareMode.WIPE, CompareMode.SPLIT_V, CompareMode.SPLIT_H):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, False)
            pen = QPen(QColor("#ffcc00"), 1)
            p.setPen(pen)
            if self._mode == CompareMode.WIPE:
                x = int(self.width() * (1 - self._wipe))
                p.drawLine(x, 0, x, self.height())
            elif self._mode == CompareMode.SPLIT_V:
                x = self.width() // 2
                p.drawLine(x, 0, x, self.height())
            elif self._mode == CompareMode.SPLIT_H:
                y = self.height() // 2
                p.drawLine(0, y, self.width(), y)
            p.end()
