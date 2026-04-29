from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QSlider, QComboBox,
    QDoubleSpinBox, QSizePolicy
)


class TransportBar(QWidget):
    """Play/pause, frame step, speed, loop, audio offset, volume."""

    play_toggled = Signal()
    step_requested = Signal(int)             # +/-1, +/-10
    speed_changed = Signal(float)
    loop_mode_changed = Signal(str)          # 'none' | 'loop' | 'pingpong'
    audio_offset_changed = Signal(float)
    volume_changed = Signal(float)
    mute_toggled = Signal(bool)
    set_in_requested = Signal()
    set_out_requested = Signal()
    clear_inout_requested = Signal()
    add_bookmark_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        def btn(text: str, tip: str = "") -> QPushButton:
            b = QPushButton(text)
            b.setFixedHeight(28)
            if tip:
                b.setToolTip(tip)
            return b

        self.btn_back10 = btn("⏪", "Back 10 frames (Shift+Left)")
        self.btn_back1 = btn("◀", "Previous frame (Left)")
        self.btn_play = btn("▶", "Play / Pause (Space)")
        self.btn_fwd1 = btn("▶|", "Next frame (Right)")
        self.btn_fwd10 = btn("⏩", "Forward 10 frames (Shift+Right)")
        self.btn_set_in = btn("[", "Set In (I)")
        self.btn_set_out = btn("]", "Set Out (O)")
        self.btn_clear_inout = btn("⤫", "Clear In/Out (Shift+X)")
        self.btn_bookmark = btn("★", "Add bookmark at current frame (B)")

        layout.addWidget(self.btn_back10)
        layout.addWidget(self.btn_back1)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_fwd1)
        layout.addWidget(self.btn_fwd10)
        layout.addSpacing(8)
        layout.addWidget(self.btn_set_in)
        layout.addWidget(self.btn_set_out)
        layout.addWidget(self.btn_clear_inout)
        layout.addSpacing(8)
        layout.addWidget(self.btn_bookmark)
        layout.addStretch(1)

        # Speed combo
        layout.addWidget(QLabel("Speed:"))
        self.cmb_speed = QComboBox()
        for s in ["0.10", "0.25", "0.50", "0.75", "1.00", "1.25", "1.50", "2.00", "4.00"]:
            self.cmb_speed.addItem(s + "x", float(s))
        self.cmb_speed.setCurrentIndex(4)
        self.cmb_speed.currentIndexChanged.connect(
            lambda _i: self.speed_changed.emit(float(self.cmb_speed.currentData()))
        )
        layout.addWidget(self.cmb_speed)

        # Loop mode
        layout.addWidget(QLabel("Loop:"))
        self.cmb_loop = QComboBox()
        self.cmb_loop.addItem("Off", "none")
        self.cmb_loop.addItem("Loop", "loop")
        self.cmb_loop.addItem("Ping-Pong", "pingpong")
        self.cmb_loop.setCurrentIndex(1)
        self.cmb_loop.currentIndexChanged.connect(
            lambda _i: self.loop_mode_changed.emit(self.cmb_loop.currentData())
        )
        layout.addWidget(self.cmb_loop)

        # Audio offset
        layout.addWidget(QLabel("Audio offset:"))
        self.spn_audio = QDoubleSpinBox()
        self.spn_audio.setRange(-5.0, 5.0)
        self.spn_audio.setSingleStep(0.05)
        self.spn_audio.setSuffix(" s")
        self.spn_audio.valueChanged.connect(self.audio_offset_changed.emit)
        layout.addWidget(self.spn_audio)

        # Volume
        layout.addWidget(QLabel("Vol:"))
        self.sld_vol = QSlider(Qt.Horizontal)
        self.sld_vol.setRange(0, 100)
        self.sld_vol.setValue(80)
        self.sld_vol.setFixedWidth(80)
        self.sld_vol.valueChanged.connect(lambda v: self.volume_changed.emit(float(v)))
        layout.addWidget(self.sld_vol)

        self.btn_mute = btn("🔊", "Mute (M)")
        self.btn_mute.setCheckable(True)
        self.btn_mute.toggled.connect(self._on_mute)
        layout.addWidget(self.btn_mute)

        # Wire button signals
        self.btn_play.clicked.connect(self.play_toggled.emit)
        self.btn_back1.clicked.connect(lambda: self.step_requested.emit(-1))
        self.btn_fwd1.clicked.connect(lambda: self.step_requested.emit(1))
        self.btn_back10.clicked.connect(lambda: self.step_requested.emit(-10))
        self.btn_fwd10.clicked.connect(lambda: self.step_requested.emit(10))
        self.btn_set_in.clicked.connect(self.set_in_requested.emit)
        self.btn_set_out.clicked.connect(self.set_out_requested.emit)
        self.btn_clear_inout.clicked.connect(self.clear_inout_requested.emit)
        self.btn_bookmark.clicked.connect(self.add_bookmark_requested.emit)

    def set_play_icon(self, playing: bool) -> None:
        self.btn_play.setText("⏸" if playing else "▶")

    def _on_mute(self, checked: bool) -> None:
        self.btn_mute.setText("🔇" if checked else "🔊")
        self.mute_toggled.emit(checked)
