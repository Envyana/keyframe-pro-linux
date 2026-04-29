from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox, QHBoxLayout, QPushButton, QFileDialog, QLabel
)

from ..core.timeline import SourceClip


class ClipEditor(QDialog):
    """Edit one SourceClip: label, in/out frame, fps, audio override, enabled."""

    def __init__(self, clip: SourceClip, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Source — {Path(clip.media_path).name}")
        self.resize(520, 320)
        self._clip = clip

        form = QFormLayout(self)

        form.addRow("Path:", QLabel(clip.media_path))

        self.ed_label = QLineEdit(clip.label or Path(clip.media_path).stem)
        form.addRow("Label:", self.ed_label)

        self.spn_fps = QDoubleSpinBox()
        self.spn_fps.setRange(1.0, 240.0)
        self.spn_fps.setDecimals(3)
        self.spn_fps.setValue(clip.src_fps if clip.src_fps > 0 else 24.0)
        form.addRow("Source FPS:", self.spn_fps)

        self.spn_total = QSpinBox()
        self.spn_total.setRange(0, 10_000_000)
        self.spn_total.setValue(int(clip.src_total_frames))
        self.spn_total.setSuffix("  (0 = unknown)")
        form.addRow("Source total frames:", self.spn_total)

        self.spn_in = QSpinBox()
        self.spn_in.setRange(0, 10_000_000)
        self.spn_in.setValue(int(clip.in_frame))
        form.addRow("In frame:", self.spn_in)

        self.spn_out = QSpinBox()
        self.spn_out.setRange(-1, 10_000_000)
        self.spn_out.setValue(int(clip.out_frame) if clip.out_frame is not None else -1)
        self.spn_out.setSpecialValueText("end of source")
        form.addRow("Out frame:", self.spn_out)

        # Audio override
        ao_row = QHBoxLayout()
        self.ed_audio = QLineEdit(clip.audio_override or "")
        self.ed_audio.setPlaceholderText("(none — use video's own audio)")
        self.btn_browse_audio = QPushButton("Browse…")
        self.btn_clear_audio = QPushButton("Clear")
        ao_row.addWidget(self.ed_audio, 1)
        ao_row.addWidget(self.btn_browse_audio)
        ao_row.addWidget(self.btn_clear_audio)
        form.addRow("Audio override:", self._wrap(ao_row))
        self.btn_browse_audio.clicked.connect(self._browse_audio)
        self.btn_clear_audio.clicked.connect(lambda: self.ed_audio.setText(""))

        self.chk_enabled = QCheckBox("Include in timeline")
        self.chk_enabled.setChecked(clip.enabled)
        form.addRow(self.chk_enabled)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    @staticmethod
    def _wrap(layout):
        from PySide6.QtWidgets import QWidget
        w = QWidget()
        w.setLayout(layout)
        return w

    def _browse_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Audio override", "",
            "Audio (*.wav *.flac *.mp3 *.m4a *.ogg *.aac *.opus);;All files (*)"
        )
        if path:
            self.ed_audio.setText(path)

    def result_clip(self) -> SourceClip:
        out_val = self.spn_out.value()
        return SourceClip(
            media_path=self._clip.media_path,
            label=self.ed_label.text().strip() or Path(self._clip.media_path).stem,
            in_frame=int(self.spn_in.value()),
            out_frame=None if out_val < 0 else int(out_val),
            src_fps=float(self.spn_fps.value()),
            src_total_frames=int(self.spn_total.value()),
            audio_override=self.ed_audio.text().strip() or None,
            enabled=self.chk_enabled.isChecked(),
        )
