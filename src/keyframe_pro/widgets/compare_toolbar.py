from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QButtonGroup, QLabel, QSlider,
    QFileDialog, QCheckBox, QSpinBox, QMenu
)
from PySide6.QtGui import QAction

from .compare_view import CompareMode


class CompareToolbar(QWidget):
    mode_changed = Signal(str)         # CompareMode value
    load_b_requested = Signal(str)
    load_c_requested = Signal(str)
    load_d_requested = Signal(str)
    sync_toggled = Signal(bool)
    wipe_changed = Signal(float)
    flicker_interval_changed = Signal(int)

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
            ("Grid 2×2", CompareMode.GRID_2X2.value),
            ("Flicker", CompareMode.FLICKER.value),
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
        self.sld_wipe.setFixedWidth(120)
        self.sld_wipe.valueChanged.connect(
            lambda v: self.wipe_changed.emit(v / 1000.0)
        )
        layout.addWidget(self.sld_wipe)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Flicker:"))
        self.spn_flicker = QSpinBox()
        self.spn_flicker.setRange(40, 2000)
        self.spn_flicker.setSingleStep(10)
        self.spn_flicker.setValue(250)
        self.spn_flicker.setSuffix(" ms")
        self.spn_flicker.valueChanged.connect(self.flicker_interval_changed.emit)
        layout.addWidget(self.spn_flicker)

        layout.addSpacing(8)
        self.chk_sync = QCheckBox("Sync")
        self.chk_sync.setChecked(True)
        self.chk_sync.toggled.connect(self.sync_toggled.emit)
        layout.addWidget(self.chk_sync)

        layout.addStretch(1)

        # "Load…" dropdown for B / C / D
        self.btn_load = QPushButton("Load…")
        self.btn_load.setFixedHeight(26)
        menu = QMenu(self.btn_load)
        a_b = QAction("Load B…", self.btn_load)
        a_c = QAction("Load C…", self.btn_load)
        a_d = QAction("Load D…", self.btn_load)
        a_b.triggered.connect(lambda: self._pick_for(self.load_b_requested))
        a_c.triggered.connect(lambda: self._pick_for(self.load_c_requested))
        a_d.triggered.connect(lambda: self._pick_for(self.load_d_requested))
        menu.addAction(a_b); menu.addAction(a_c); menu.addAction(a_d)
        self.btn_load.setMenu(menu)
        layout.addWidget(self.btn_load)

    def _pick_for(self, signal: Signal) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load comparison source", "",
            "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;All files (*)"
        )
        if path:
            signal.emit(path)

    def set_wipe(self, v: float) -> None:
        self.sld_wipe.blockSignals(True)
        self.sld_wipe.setValue(int(v * 1000))
        self.sld_wipe.blockSignals(False)
