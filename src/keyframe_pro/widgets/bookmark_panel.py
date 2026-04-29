from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QPixmap, QIcon, QPainter, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMenu
)

from ..core.bookmarks import BookmarkModel, Bookmark


def _color_icon(color: str, size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


class BookmarkPanel(QWidget):
    bookmark_activated = Signal(Bookmark)
    delete_requested = Signal(int)
    edit_requested = Signal(int)
    sync_annotations_requested = Signal()

    def __init__(self, model: BookmarkModel) -> None:
        super().__init__()
        self._model = model
        self._fps = 24.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QLabel("Bookmarks"))

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._on_activate)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_next = QPushButton("Next ▶")
        self.btn_edit = QPushButton("Edit…")
        self.btn_del = QPushButton("Delete")
        row.addWidget(self.btn_prev)
        row.addWidget(self.btn_next)
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_del)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        self.btn_sync_ann = QPushButton("Sync Annotation Bookmarks")
        self.btn_sync_ann.setToolTip(
            "Add an annotation-kind bookmark for every annotated frame"
        )
        row2.addWidget(self.btn_sync_ann)
        layout.addLayout(row2)

        self.btn_del.clicked.connect(self._on_delete)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_sync_ann.clicked.connect(self.sync_annotations_requested.emit)

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
            label += f"   [{b.kind}]"
            if b.name:
                label += f"  {b.name}"
            it = QListWidgetItem(_color_icon(b.color), label)
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

    def _on_edit(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        self.edit_requested.emit(int(it.data(Qt.UserRole)))

    def _on_context_menu(self, pos: QPoint) -> None:
        it = self.list.itemAt(pos)
        if it is None:
            return
        idx = int(it.data(Qt.UserRole))
        m = QMenu(self)
        a_seek = QAction("Go to frame", self)
        a_edit = QAction("Edit…", self)
        a_del = QAction("Delete", self)
        m.addAction(a_seek)
        m.addAction(a_edit)
        m.addSeparator()
        m.addAction(a_del)

        def _seek():
            items = self._model.all()
            if 0 <= idx < len(items):
                self.bookmark_activated.emit(items[idx])
        a_seek.triggered.connect(_seek)
        a_edit.triggered.connect(lambda: self.edit_requested.emit(idx))
        a_del.triggered.connect(lambda: self.delete_requested.emit(idx))
        m.exec(self.list.mapToGlobal(pos))
