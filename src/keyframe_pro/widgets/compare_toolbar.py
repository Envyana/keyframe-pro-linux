from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QButtonGroup, QLabel, QSlider,
    QFileDialog, QCheckBox
)

from .compare_view import CompareMode


class CompareToolbar(QWidget):
    mode_changed = Signal(str)         # CompareMode value
    load_b_requested = Signal(str)
    sync_toggled = Signal(bool)
    wipe_changed = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        layout.addWidget(QLabel("View:"))
        group = QButtonGroup(self)
        group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for label, mode in [
            ("A", CompareMode.SINGLE_A.value),
            ("B", CompareMode.SINGLE_B.value),
            ("Wipe", CompareMode.WIPE.value),
            ("Split ⫯", CompareMode.SPLIT_V.value),
            ("Split ⫬", CompareMode.SPLIT_H.value),
        ]:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFixedHeight(26)
            b.setProperty("mode", mode)
            group.addButton(b)
            layout.addWidget(b)
            self._buttons[mode] = b
        self._buttons[CompareMode.SINGLE_A.value].setChecked(True)
        group.buttonClicked.connect(
            lambda btn: self.mode_changed.emit(btn.property("mode"))
        )

        layout.addSpacing(8)
        layout.addWidget(QLabel("Wipe:"))
        self.sld_wipe = QSlider(Qt.Horizontal)
        self.sld_wipe.setRange(0, 1000)
        self.sld_wipe.setValue(500)
        self.sld_wipe.setFixedWidth(140)
        self.sld_wipe.valueChanged.connect(
            lambda v: self.wipe_changed.emit(v / 1000.0)
        )
        layout.addWidget(self.sld_wipe)

        layout.addSpacing(8)
        self.chk_sync = QCheckBox("Sync A↔B")
        self.chk_sync.setChecked(True)
        self.chk_sync.toggled.connect(self.sync_toggled.emit)
        layout.addWidget(self.chk_sync)

        layout.addStretch(1)

        self.btn_load_b = QPushButton("Load B…")
        self.btn_load_b.setFixedHeight(26)
        self.btn_load_b.clicked.connect(self._on_load_b)
        layout.addWidget(self.btn_load_b)

    def _on_load_b(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load comparison source (B)", "",
            "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;All files (*)"
        )
        if path:
            self.load_b_requested.emit(path)

    def set_wipe(self, v: float) -> None:
        self.sld_wipe.blockSignals(True)
        self.sld_wipe.setValue(int(v * 1000))
        self.sld_wipe.blockSignals(False)
