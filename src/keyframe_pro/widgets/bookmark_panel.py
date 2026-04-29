from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel
)

from ..core.bookmarks import BookmarkModel, Bookmark


class BookmarkPanel(QWidget):
    bookmark_activated = Signal(Bookmark)
    delete_requested = Signal(int)

    def __init__(self, model: BookmarkModel) -> None:
        super().__init__()
        self._model = model
        self._fps = 24.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QLabel("Bookmarks"))

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._on_activate)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_next = QPushButton("Next ▶")
        self.btn_del = QPushButton("Delete")
        row.addWidget(self.btn_prev)
        row.addWidget(self.btn_next)
        row.addWidget(self.btn_del)
        layout.addLayout(row)

        self.btn_del.clicked.connect(self._on_delete)

        self._model.changed.connect(self.refresh)
        self.refresh()

    def set_fps(self, fps: float) -> None:
        self._fps = max(1.0, fps)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for i, b in enumerate(self._model.all()):
            t_in = b.frame_in / self._fps
            label = f"{b.frame_in:>5}  ({t_in:6.2f}s)"
            if b.is_range and b.frame_out is not None:
                label += f"  →  {b.frame_out:>5}"
            if b.name:
                label += f"   {b.name}"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, i)
            it.setForeground(Qt.white)
            self.list.addItem(it)

    def _on_activate(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.UserRole)
        items = self._model.all()
        if 0 <= idx < len(items):
            self.bookmark_activated.emit(items[idx])

    def _on_delete(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        self.delete_requested.emit(int(it.data(Qt.UserRole)))
