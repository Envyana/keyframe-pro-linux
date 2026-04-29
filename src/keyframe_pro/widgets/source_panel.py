from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QFileDialog, QAbstractItemView
)

from ..core.timeline import Timeline, SourceClip
from ..core import thumbnail


class _ThumbWorker(QThread):
    """Background generator for one thumbnail. Self-deleting."""

    from PySide6.QtCore import Signal as _Sig
    done = _Sig(str, str)  # media_path, thumb_path (empty on failure)

    def __init__(self, media_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._media_path = media_path

    def run(self) -> None:
        out = thumbnail.generate_thumbnail(self._media_path)
        self.done.emit(self._media_path, str(out) if out else "")


class SourcePanel(QWidget):
    """Reorderable list of timeline sources."""

    activate_requested = Signal(int)  # clip index → seek to its start
    add_files_requested = Signal(list)  # list[str]
    edit_requested = Signal(int)       # open ClipEditor for this clip

    def __init__(self, timeline: Timeline) -> None:
        super().__init__()
        self._timeline = timeline
        self._thumb_workers: dict[str, _ThumbWorker] = {}
        self._thumb_cache: dict[str, str] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QLabel("Sources"))

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setIconSize(QSize(80, 45))
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.btn_add = QPushButton("Add…")
        self.btn_edit = QPushButton("Edit…")
        self.btn_remove = QPushButton("Remove")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_clear = QPushButton("Clear")
        for b in (self.btn_add, self.btn_edit, self.btn_remove,
                  self.btn_up, self.btn_down, self.btn_clear):
            b.setFixedHeight(26)
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_remove)
        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        row.addWidget(self.btn_clear)
        layout.addLayout(row)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
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
            it.setData(Qt.UserRole + 1, c.media_path)
            if not c.enabled:
                it.setForeground(Qt.gray)
            # Apply cached thumbnail or kick off generation
            thumb = self._thumb_cache.get(c.media_path)
            if thumb is None and thumbnail.has_thumbnail(c.media_path):
                thumb = str(thumbnail.cached_path(c.media_path))
                self._thumb_cache[c.media_path] = thumb
            if thumb:
                pm = QPixmap(thumb)
                if not pm.isNull():
                    it.setIcon(QIcon(pm))
            else:
                self._request_thumbnail(c.media_path)
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _request_thumbnail(self, media_path: str) -> None:
        if media_path in self._thumb_workers:
            return
        w = _ThumbWorker(media_path, self)
        w.done.connect(self._on_thumb_done)
        self._thumb_workers[media_path] = w
        w.start()

    def _on_thumb_done(self, media_path: str, thumb_path: str) -> None:
        # Worker has finished; let it die.
        w = self._thumb_workers.pop(media_path, None)
        if w is not None:
            w.deleteLater()
        if thumb_path:
            self._thumb_cache[media_path] = thumb_path
            # Repaint matching rows
            pm = QPixmap(thumb_path)
            if pm.isNull():
                return
            ico = QIcon(pm)
            for row in range(self.list.count()):
                it = self.list.item(row)
                if it.data(Qt.UserRole + 1) == media_path:
                    it.setIcon(ico)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        # Double-click activates (loads) the source. Edit is via the button.
        idx = int(item.data(Qt.UserRole))
        self.activate_requested.emit(idx)

    def _on_edit(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        self.edit_requested.emit(int(it.data(Qt.UserRole)))

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
