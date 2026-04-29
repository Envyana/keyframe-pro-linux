from __future__ import annotations

from enum import Enum
from typing import Optional, Sequence
from PySide6.QtCore import Qt, QRectF, Signal, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent
from PySide6.QtWidgets import QWidget

from ..player.mpv_player import MpvPlayer


class CompareMode(str, Enum):
    SINGLE_A = "a"
    SINGLE_B = "b"
    WIPE = "wipe"
    SPLIT_H = "split_h"
    SPLIT_V = "split_v"
    GRID_2X2 = "grid"
    FLICKER = "flicker"     # rapidly alternate two players (animation flip-compare)


class CompareView(QWidget):
    """Hosts up to 4 MpvPlayer widgets and arranges them per mode.

    - SINGLE_A / SINGLE_B: one full-rect player.
    - WIPE: A full, B clipped to a vertical band controlled by `wipe`.
    - SPLIT_H / SPLIT_V: A and B stacked / side-by-side.
    - GRID_2X2: A, B, C, D in 4 quadrants. (C/D fall back to A/B if not loaded.)
    - FLICKER: alternates between A and B at `flicker_interval_ms`.
      Implemented by raising/lowering the two players on a QTimer; gives
      animators the classic flip-compare without needing the render API.

    Sync of frame positions across players is the controller's job.
    """

    wipe_changed = Signal(float)  # 0..1

    def __init__(self, player_a: MpvPlayer, player_b: MpvPlayer,
                 player_c: Optional[MpvPlayer] = None,
                 player_d: Optional[MpvPlayer] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._a = player_a
        self._b = player_b
        self._c = player_c
        self._d = player_d
        self._mode: CompareMode = CompareMode.SINGLE_A
        self._wipe: float = 0.5     # 0 = all A, 1 = all B
        self._dragging_wipe: bool = False

        # Flicker
        self._flicker_interval_ms: int = 250
        self._flicker_show_a: bool = True
        self._flicker_timer = QTimer(self)
        self._flicker_timer.timeout.connect(self._flicker_tick)

        for w in self._players():
            w.setParent(self)
            w.show()

        self._apply_layout()

    def _players(self) -> list[MpvPlayer]:
        return [p for p in (self._a, self._b, self._c, self._d) if p is not None]

    # --- public ---

    def player_a(self) -> MpvPlayer: return self._a
    def player_b(self) -> MpvPlayer: return self._b
    def player_c(self) -> Optional[MpvPlayer]: return self._c
    def player_d(self) -> Optional[MpvPlayer]: return self._d

    def set_mode(self, mode: CompareMode) -> None:
        # Stop flicker if leaving FLICKER mode
        if self._mode == CompareMode.FLICKER and mode != CompareMode.FLICKER:
            self._flicker_timer.stop()
            self._flicker_show_a = True
        self._mode = mode
        if mode == CompareMode.FLICKER:
            self._flicker_show_a = True
            self._flicker_timer.start(self._flicker_interval_ms)
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

    def set_flicker_interval(self, ms: int) -> None:
        self._flicker_interval_ms = max(40, min(2000, int(ms)))
        if self._mode == CompareMode.FLICKER:
            self._flicker_timer.start(self._flicker_interval_ms)

    def flicker_interval(self) -> int:
        return self._flicker_interval_ms

    # --- layout ---

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._apply_layout()

    def _apply_layout(self) -> None:
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        def hide_all_except(visible: list[MpvPlayer]) -> None:
            for p in self._players():
                p.setVisible(p in visible)

        def small_offscreen(p: Optional[MpvPlayer]) -> None:
            if p is None:
                return
            p.setGeometry(0, 0, 1, 1)
            p.hide()

        if self._mode == CompareMode.SINGLE_A:
            self._a.setGeometry(0, 0, w, h)
            small_offscreen(self._b); small_offscreen(self._c); small_offscreen(self._d)
            self._a.show()
            self._a.raise_()
        elif self._mode == CompareMode.SINGLE_B:
            self._b.setGeometry(0, 0, w, h)
            small_offscreen(self._a); small_offscreen(self._c); small_offscreen(self._d)
            self._b.show()
            self._b.raise_()
        elif self._mode == CompareMode.WIPE:
            self._a.setGeometry(0, 0, w, h)
            band_w = max(1, int(round(w * self._wipe)))
            self._b.setGeometry(w - band_w, 0, band_w, h)
            small_offscreen(self._c); small_offscreen(self._d)
            self._a.show(); self._b.show()
            self._a.lower(); self._b.raise_()
        elif self._mode == CompareMode.SPLIT_H:
            self._a.setGeometry(0, 0, w, h // 2)
            self._b.setGeometry(0, h // 2, w, h - h // 2)
            small_offscreen(self._c); small_offscreen(self._d)
            self._a.show(); self._b.show()
        elif self._mode == CompareMode.SPLIT_V:
            self._a.setGeometry(0, 0, w // 2, h)
            self._b.setGeometry(w // 2, 0, w - w // 2, h)
            small_offscreen(self._c); small_offscreen(self._d)
            self._a.show(); self._b.show()
        elif self._mode == CompareMode.GRID_2X2:
            cw, ch = w // 2, h // 2
            # Quadrants: A=top-left, B=top-right, C=bottom-left, D=bottom-right.
            # If C/D weren't provided, fall back to A/B for the bottom row so
            # something sensible shows.
            self._a.setGeometry(0, 0, cw, ch)
            self._b.setGeometry(cw, 0, w - cw, ch)
            third = self._c or self._a
            fourth = self._d or self._b
            third.setGeometry(0, ch, cw, h - ch)
            fourth.setGeometry(cw, ch, w - cw, h - ch)
            for p in self._players():
                p.show()
        elif self._mode == CompareMode.FLICKER:
            # Both A and B fill the area; we toggle which one is on top.
            self._a.setGeometry(0, 0, w, h)
            self._b.setGeometry(0, 0, w, h)
            small_offscreen(self._c); small_offscreen(self._d)
            self._a.show(); self._b.show()
            (self._a if self._flicker_show_a else self._b).raise_()
            (self._b if self._flicker_show_a else self._a).lower()

    def _flicker_tick(self) -> None:
        self._flicker_show_a = not self._flicker_show_a
        # Just re-raise; don't relayout (cheaper).
        if self._mode == CompareMode.FLICKER:
            (self._a if self._flicker_show_a else self._b).raise_()
            (self._b if self._flicker_show_a else self._a).lower()

    # --- wipe interaction ---

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if self._mode != CompareMode.WIPE or ev.button() != Qt.LeftButton:
            return
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
        self._wipe = max(0.0, min(1.0, 1.0 - x / self.width()))
        self._apply_layout()
        self.wipe_changed.emit(self._wipe)
        self.update()

    # --- decoration ---

    def paintEvent(self, _ev) -> None:
        if self._mode in (CompareMode.WIPE, CompareMode.SPLIT_V,
                          CompareMode.SPLIT_H, CompareMode.GRID_2X2):
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
            elif self._mode == CompareMode.GRID_2X2:
                cx = self.width() // 2
                cy = self.height() // 2
                p.drawLine(cx, 0, cx, self.height())
                p.drawLine(0, cy, self.width(), cy)
            p.end()
