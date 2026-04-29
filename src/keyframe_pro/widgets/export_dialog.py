from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QFileDialog, QPlainTextEdit,
    QProgressBar, QLabel, QMessageBox
)

from ..core.timeline import Timeline
from ..core.export import ExportOptions, run_export, find_ffmpeg


class ExportWorker(QObject):
    line = Signal(str)
    done = Signal(bool, str)  # success, message

    def __init__(self, timeline: Timeline, opts: ExportOptions) -> None:
        super().__init__()
        self._timeline = timeline
        self._opts = opts

    def run(self) -> None:
        try:
            for line in run_export(self._timeline, self._opts):
                self.line.emit(line)
            self.done.emit(True, f"Exported to {self._opts.output_path}")
        except Exception as e:
            self.done.emit(False, str(e))


class ExportDialog(QDialog):
    def __init__(self, timeline: Timeline, default_fps: float = 24.0,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Timeline")
        self.resize(640, 520)
        self._timeline = timeline
        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None

        layout = QVBoxLayout(self)

        if find_ffmpeg() is None:
            warn = QLabel(
                "<span style='color:#ff5555'><b>ffmpeg not found in PATH.</b> "
                "Install it before exporting.</span>"
            )
            layout.addWidget(warn)

        form = QFormLayout()

        # Output path
        out_row = QHBoxLayout()
        self.ed_out = QLineEdit(str(Path.home() / "keyframe_export.mp4"))
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.clicked.connect(self._browse)
        out_row.addWidget(self.ed_out, 1)
        out_row.addWidget(self.btn_browse)
        form.addRow("Output:", self._wrap(out_row))

        self.cmb_codec = QComboBox()
        for c in ["libx264", "libx265", "prores_ks", "libvpx-vp9", "gif"]:
            self.cmb_codec.addItem(c)
        form.addRow("Video codec:", self.cmb_codec)

        self.spn_crf = QSpinBox()
        self.spn_crf.setRange(0, 51)
        self.spn_crf.setValue(18)
        form.addRow("CRF (lower = better):", self.spn_crf)

        self.cmb_preset = QComboBox()
        for p in ["ultrafast", "veryfast", "faster", "fast", "medium", "slow", "veryslow"]:
            self.cmb_preset.addItem(p)
        self.cmb_preset.setCurrentText("medium")
        form.addRow("Preset:", self.cmb_preset)

        self.spn_fps = QDoubleSpinBox()
        self.spn_fps.setRange(1.0, 240.0)
        self.spn_fps.setDecimals(3)
        self.spn_fps.setValue(default_fps)
        form.addRow("Output FPS:", self.spn_fps)

        size_row = QHBoxLayout()
        self.spn_w = QSpinBox(); self.spn_w.setRange(0, 16384)
        self.spn_h = QSpinBox(); self.spn_h.setRange(0, 16384)
        self.spn_w.setValue(0); self.spn_h.setValue(0)
        self.spn_w.setSpecialValueText("auto")
        self.spn_h.setSpecialValueText("auto")
        size_row.addWidget(self.spn_w)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self.spn_h)
        form.addRow("Size (0 = source):", self._wrap(size_row))

        self.chk_audio = QCheckBox("Include audio")
        self.chk_audio.setChecked(True)
        form.addRow(self.chk_audio)

        layout.addLayout(form)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        layout.addWidget(self.log, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton("Close")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_export = QPushButton("Export")
        self.btn_export.setDefault(True)
        self.btn_export.clicked.connect(self._start)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_export)
        layout.addLayout(btn_row)

    @staticmethod
    def _wrap(layout) -> QLineEdit:
        w = type("Wrap", (object,), {})()
        from PySide6.QtWidgets import QWidget
        ww = QWidget()
        ww.setLayout(layout)
        return ww

    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save export as", self.ed_out.text(),
            "MP4 (*.mp4);;MOV (*.mov);;MKV (*.mkv);;WebM (*.webm);;GIF (*.gif);;All files (*)"
        )
        if path:
            self.ed_out.setText(path)

    def _start(self) -> None:
        if find_ffmpeg() is None:
            QMessageBox.critical(self, "Missing ffmpeg",
                                 "ffmpeg not found in PATH. Install it first.")
            return
        if self._timeline.count() == 0:
            QMessageBox.warning(self, "Empty timeline",
                                "Add at least one source to the timeline first.")
            return

        opts = ExportOptions(
            output_path=self.ed_out.text(),
            fps=float(self.spn_fps.value()),
            codec=self.cmb_codec.currentText(),
            crf=self.spn_crf.value(),
            preset=self.cmb_preset.currentText(),
            width=self.spn_w.value() or None,
            height=self.spn_h.value() or None,
            include_audio=self.chk_audio.isChecked(),
        )

        self.btn_export.setEnabled(False)
        self.progress.setVisible(True)
        self.log.clear()
        self.log.appendPlainText("Starting ffmpeg…")

        self._thread = QThread(self)
        self._worker = ExportWorker(self._timeline, opts)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.line.connect(self.log.appendPlainText)
        self._worker.done.connect(self._on_done)
        self._thread.start()

    def _on_done(self, ok: bool, msg: str) -> None:
        self.progress.setVisible(False)
        self.btn_export.setEnabled(True)
        self.log.appendPlainText(("[OK] " if ok else "[FAIL] ") + msg)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
