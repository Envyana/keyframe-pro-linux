from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QSpinBox, QColorDialog,
    QButtonGroup, QCheckBox, QComboBox
)

from .annotation import AnnotationOverlay


class AnnotationToolbar(QWidget):
    tool_changed = Signal(str)
    color_changed = Signal(str)
    width_changed = Signal(int)
    layer_changed = Signal(str)
    ghost_changed = Signal(bool, bool)  # prev, next
    annotate_toggled = Signal(bool)
    held_changed = Signal(int)
    clear_frame_requested = Signal()
    undo_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        self.btn_toggle = QPushButton("Annotate Off")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setFixedHeight(28)
        self.btn_toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self.btn_toggle)

        layout.addSpacing(8)

        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        for label, tool in [
            ("Pen", AnnotationOverlay.TOOL_PEN),
            ("Hi", AnnotationOverlay.TOOL_HIGHLIGHTER),
            ("→", AnnotationOverlay.TOOL_ARROW),
            ("▭", AnnotationOverlay.TOOL_RECT),
            ("◯", AnnotationOverlay.TOOL_ELLIPSE),
            ("Text", AnnotationOverlay.TOOL_TEXT),
            ("Pick", AnnotationOverlay.TOOL_EYEDROPPER),
            ("Erase", AnnotationOverlay.TOOL_ERASER),
            ("Laser", AnnotationOverlay.TOOL_LASER),
        ]:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setProperty("tool", tool)
            self._tool_group.addButton(b)
            layout.addWidget(b)
            if tool == AnnotationOverlay.TOOL_PEN:
                b.setChecked(True)

        self._tool_group.buttonClicked.connect(
            lambda btn: self.tool_changed.emit(btn.property("tool"))
        )

        layout.addSpacing(8)
        layout.addWidget(QLabel("Color:"))
        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(28, 28)
        self._color = "#ff2222"
        self._refresh_color_btn()
        self.btn_color.clicked.connect(self._pick_color)
        layout.addWidget(self.btn_color)

        # Color presets
        for c in ["#ff2222", "#ffcc00", "#22cc77", "#22aaff", "#ffffff", "#000000"]:
            b = QPushButton()
            b.setFixedSize(20, 20)
            b.setStyleSheet(f"background-color: {c}; border: 1px solid #444;")
            b.clicked.connect(lambda _=False, col=c: self._set_color(col))
            layout.addWidget(b)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Width:"))
        self.spn_width = QSpinBox()
        self.spn_width.setRange(1, 30)
        self.spn_width.setValue(3)
        self.spn_width.valueChanged.connect(self.width_changed.emit)
        layout.addWidget(self.spn_width)

        layout.addWidget(QLabel("Layer:"))
        self.cmb_layer = QComboBox()
        self.cmb_layer.addItem("Foreground", "fg")
        self.cmb_layer.addItem("Background", "bg")
        self.cmb_layer.currentIndexChanged.connect(
            lambda _i: self.layer_changed.emit(self.cmb_layer.currentData())
        )
        layout.addWidget(self.cmb_layer)

        self.chk_ghost_prev = QCheckBox("Ghost−1")
        self.chk_ghost_next = QCheckBox("Ghost+1")
        self.chk_ghost_prev.toggled.connect(self._emit_ghost)
        self.chk_ghost_next.toggled.connect(self._emit_ghost)
        layout.addWidget(self.chk_ghost_prev)
        layout.addWidget(self.chk_ghost_next)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Hold:"))
        self.spn_hold = QSpinBox()
        self.spn_hold.setRange(1, 9999)
        self.spn_hold.setValue(1)
        self.spn_hold.valueChanged.connect(self.held_changed.emit)
        self.spn_hold.setToolTip("Hold this frame's annotation across N frames")
        layout.addWidget(self.spn_hold)

        layout.addStretch(1)

        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setFixedHeight(28)
        self.btn_undo.clicked.connect(self.undo_requested.emit)
        layout.addWidget(self.btn_undo)

        self.btn_clear = QPushButton("Clear Frame")
        self.btn_clear.setFixedHeight(28)
        self.btn_clear.clicked.connect(self.clear_frame_requested.emit)
        layout.addWidget(self.btn_clear)

    def _on_toggle(self, on: bool) -> None:
        self.btn_toggle.setText("Annotate ON" if on else "Annotate Off")
        self.annotate_toggled.emit(on)

    def _refresh_color_btn(self) -> None:
        self.btn_color.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #444;"
        )

    def _set_color(self, col: str) -> None:
        self._color = col
        self._refresh_color_btn()
        self.color_changed.emit(col)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Pick color")
        if c.isValid():
            self._set_color(c.name())

    def _emit_ghost(self) -> None:
        self.ghost_changed.emit(self.chk_ghost_prev.isChecked(),
                                self.chk_ghost_next.isChecked())
