from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QKeySequenceEdit, QMessageBox, QLabel
)

from ..core.settings import Settings, DEFAULT_HOTKEYS


class HotkeyEditor(QKeySequenceEdit):
    """A QKeySequenceEdit that limits to one shortcut and allows clearing."""

    def __init__(self, sequence: str = "") -> None:
        super().__init__(QKeySequence(sequence))
        self.setMaximumSequenceLength(1)


class PreferencesDialog(QDialog):
    """Hotkey customization. Edits are applied on Apply / OK."""

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences — Hotkeys")
        self.resize(560, 600)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Click a row's hotkey field, press the desired key combination, "
            "then click Apply or OK."
        ))

        self.table = QTableWidget(len(DEFAULT_HOTKEYS), 2)
        self.table.setHorizontalHeaderLabels(["Action", "Hotkey"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 180)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, 1)

        self._editors: dict[str, HotkeyEditor] = {}
        for row, (action_id, (default, label)) in enumerate(DEFAULT_HOTKEYS.items()):
            it = QTableWidgetItem(label)
            it.setData(Qt.UserRole, action_id)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, it)
            ed = HotkeyEditor(self._settings.hotkey(action_id))
            self._editors[action_id] = ed
            self.table.setCellWidget(row, 1, ed)

        btn_row = QHBoxLayout()
        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self.btn_reset)
        btn_row.addStretch(1)
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self._apply)
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._ok)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

    def _on_reset(self) -> None:
        if QMessageBox.question(self, "Reset hotkeys",
                                "Reset all hotkeys to defaults?") != QMessageBox.Yes:
            return
        for action_id, (default, _) in DEFAULT_HOTKEYS.items():
            self._editors[action_id].setKeySequence(QKeySequence(default))

    def _check_conflicts(self) -> bool:
        seen: dict[str, str] = {}
        for action_id, ed in self._editors.items():
            seq = ed.keySequence().toString()
            if not seq:
                continue
            if seq in seen:
                QMessageBox.warning(self, "Conflict",
                                    f"'{seq}' is bound to both "
                                    f"'{seen[seq]}' and '{action_id}'.")
                return False
            seen[seq] = action_id
        return True

    def _apply(self) -> bool:
        if not self._check_conflicts():
            return False
        for action_id, ed in self._editors.items():
            self._settings.set_hotkey(action_id, ed.keySequence().toString())
        return True

    def _ok(self) -> None:
        if self._apply():
            self.accept()
