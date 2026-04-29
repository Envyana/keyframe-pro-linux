from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QSpinBox, QHBoxLayout,
    QColorDialog, QPlainTextEdit, QDialogButtonBox, QComboBox, QLabel
)

from ..core.bookmarks import Bookmark, KIND_FRAME, KIND_RANGE, KIND_ANNOTATION


class BookmarkEditor(QDialog):
    PRESETS = ["#ffcc00", "#ff5555", "#22cc77", "#22aaff",
               "#ff66cc", "#ffffff", "#888888"]

    def __init__(self, bm: Bookmark, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Bookmark")
        self.resize(420, 360)
        self._bm = bm
        self._color = bm.color or "#ffcc00"

        form = QFormLayout(self)

        self.ed_name = QLineEdit(bm.name)
        form.addRow("Name:", self.ed_name)

        self.cmb_kind = QComboBox()
        self.cmb_kind.addItem("Frame", KIND_FRAME)
        self.cmb_kind.addItem("Range", KIND_RANGE)
        self.cmb_kind.addItem("Annotation", KIND_ANNOTATION)
        idx = max(0, self.cmb_kind.findData(bm.kind))
        self.cmb_kind.setCurrentIndex(idx)
        self.cmb_kind.currentIndexChanged.connect(self._on_kind_changed)
        form.addRow("Kind:", self.cmb_kind)

        self.spn_in = QSpinBox()
        self.spn_in.setRange(0, 10_000_000)
        self.spn_in.setValue(int(bm.frame_in))
        form.addRow("In frame:", self.spn_in)

        self.spn_out = QSpinBox()
        self.spn_out.setRange(-1, 10_000_000)
        self.spn_out.setValue(int(bm.frame_out) if bm.frame_out is not None else -1)
        self.spn_out.setSpecialValueText("(none)")
        form.addRow("Out frame:", self.spn_out)

        # Color row
        color_row = QHBoxLayout()
        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(40, 24)
        self.btn_color.clicked.connect(self._pick_color)
        color_row.addWidget(self.btn_color)
        for c in self.PRESETS:
            b = QPushButton()
            b.setFixedSize(20, 20)
            b.setStyleSheet(f"background-color: {c}; border: 1px solid #444;")
            b.clicked.connect(lambda _=False, col=c: self._set_color(col))
            color_row.addWidget(b)
        color_row.addStretch(1)
        form.addRow("Color:", self._wrap(color_row))

        self.ed_note = QPlainTextEdit(bm.note)
        self.ed_note.setMaximumHeight(80)
        form.addRow("Note:", self.ed_note)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

        self._on_kind_changed()
        self._refresh_color()

    @staticmethod
    def _wrap(layout):
        from PySide6.QtWidgets import QWidget
        w = QWidget()
        w.setLayout(layout)
        return w

    def _on_kind_changed(self) -> None:
        is_range = self.cmb_kind.currentData() == KIND_RANGE
        self.spn_out.setEnabled(is_range)
        if not is_range:
            self.spn_out.setValue(-1)

    def _refresh_color(self) -> None:
        self.btn_color.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #444;"
        )

    def _set_color(self, col: str) -> None:
        self._color = col
        self._refresh_color()

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Pick bookmark color")
        if c.isValid():
            self._set_color(c.name())

    def result(self) -> Bookmark:
        out_val = self.spn_out.value()
        return Bookmark(
            frame_in=int(self.spn_in.value()),
            frame_out=None if out_val < 0 else int(out_val),
            name=self.ed_name.text().strip(),
            color=self._color,
            note=self.ed_note.toPlainText().strip(),
            kind=self.cmb_kind.currentData(),
        )
