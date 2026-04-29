from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QFileDialog, QAbstractItemView
)

from ..core.timeline import Timeline, SourceClip


class SourcePanel(QWidget):
    """Reorderable list of timeline sources."""

    activate_requested = Signal(int)  # clip index → seek to its start
    add_files_requested = Signal(list)  # list[str]

    def __init__(self, timeline: Timeline) -> None:
        super().__init__()
        self._timeline = timeline
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QLabel("Sources"))

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.itemDoubleClicked.connect(self._on_activate)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.btn_add = QPushButton("Add…")
        self.btn_remove = QPushButton("Remove")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_clear = QPushButton("Clear")
        for b in (self.btn_add, self.btn_remove, self.btn_up, self.btn_down, self.btn_clear):
            b.setFixedHeight(26)
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_remove)
        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        row.addWidget(self.btn_clear)
        layout.addLayout(row)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_clear.clicked.connect(self._timeline.clear)

        self._timeline.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for i, c in enumerate(self._timeline.all()):
            label = c.label or Path(c.media_path).name
            extra = f"  [{c.in_frame}–{c.out_frame if c.out_frame is not None else '?'}]"
            it = QListWidgetItem(f"{i+1:>2}.  {label}{extra}")
            it.setData(Qt.UserRole, i)
            if not c.enabled:
                it.setForeground(Qt.gray)
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _on_activate(self, item: QListWidgetItem) -> None:
        idx = int(item.data(Qt.UserRole))
        self.activate_requested.emit(idx)

    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add sources", "",
            "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;All files (*)",
        )
        if paths:
            self.add_files_requested.emit(paths)

    def _on_remove(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        self._timeline.remove(int(it.data(Qt.UserRole)))

    def _move(self, delta: int) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        i = int(it.data(Qt.UserRole))
        self._timeline.move(i, i + delta)

    def _on_rows_moved(self, _parent, src_start, _src_end, _dst_parent, dst_row) -> None:
        # Qt drag/drop reorder fires after the move; sync to model
        # by reconstructing order from current widget order
        new_order_indices: list[int] = []
        for row in range(self.list.count()):
            new_order_indices.append(int(self.list.item(row).data(Qt.UserRole)))
        # Apply reorder atomically: build new list, replace
        old = self._timeline.all()
        reordered = [old[i] for i in new_order_indices if 0 <= i < len(old)]
        self._timeline.clear()
        for c in reordered:
            self._timeline.add(c)
