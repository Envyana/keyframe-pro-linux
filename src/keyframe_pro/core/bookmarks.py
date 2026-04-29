from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
from PySide6.QtCore import QObject, Signal


KIND_FRAME = "frame"
KIND_RANGE = "range"
KIND_ANNOTATION = "annotation"


@dataclass
class Bookmark:
    frame_in: int
    frame_out: Optional[int] = None
    name: str = ""
    color: str = "#ffcc00"
    note: str = ""
    kind: str = KIND_FRAME   # 'frame' | 'range' | 'annotation'

    @property
    def is_range(self) -> bool:
        return self.frame_out is not None and self.frame_out != self.frame_in

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Bookmark":
        return cls(
            frame_in=int(d["frame_in"]),
            frame_out=None if d.get("frame_out") is None else int(d["frame_out"]),
            name=d.get("name", ""),
            color=d.get("color", "#ffcc00"),
            note=d.get("note", ""),
            kind=d.get("kind", KIND_FRAME),
        )


class BookmarkModel(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._items: list[Bookmark] = []

    def add(self, bm: Bookmark) -> None:
        self._items.append(bm)
        self._items.sort(key=lambda b: b.frame_in)
        self.changed.emit()

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            self.changed.emit()

    def clear(self) -> None:
        self._items.clear()
        self.changed.emit()

    def all(self) -> list[Bookmark]:
        return list(self._items)

    def at_frame(self, frame: int) -> Optional[Bookmark]:
        for b in self._items:
            if b.is_range and b.frame_in <= frame <= (b.frame_out or b.frame_in):
                return b
            if not b.is_range and b.frame_in == frame:
                return b
        return None

    def next_after(self, frame: int) -> Optional[Bookmark]:
        for b in self._items:
            if b.frame_in > frame:
                return b
        return self._items[0] if self._items else None

    def prev_before(self, frame: int) -> Optional[Bookmark]:
        prev = None
        for b in self._items:
            if b.frame_in < frame:
                prev = b
            else:
                break
        if prev is None and self._items:
            return self._items[-1]
        return prev

    def update_at(self, index: int, bm: Bookmark) -> None:
        if 0 <= index < len(self._items):
            self._items[index] = bm
            self._items.sort(key=lambda b: b.frame_in)
            self.changed.emit()

    def sync_from_annotations(self, annotated_frames: list[int]) -> int:
        """Add an annotation-kind bookmark for each annotated frame that
        doesn't already have a bookmark of any kind. Returns count added.
        Existing annotation bookmarks for frames no longer annotated are
        removed so the list stays in sync."""
        existing_frames = {b.frame_in for b in self._items}
        added = 0
        for f in annotated_frames:
            if f not in existing_frames:
                self._items.append(Bookmark(
                    frame_in=f,
                    kind=KIND_ANNOTATION,
                    color="#22cc77",
                    name="Annotation",
                ))
                added += 1
        # Drop annotation-kind bookmarks whose frame is no longer annotated
        annotated_set = set(annotated_frames)
        self._items = [
            b for b in self._items
            if b.kind != KIND_ANNOTATION or b.frame_in in annotated_set
        ]
        self._items.sort(key=lambda b: b.frame_in)
        if added or True:
            self.changed.emit()
        return added

    def to_list(self) -> list[dict]:
        return [b.to_dict() for b in self._items]

    def load(self, data: list[dict]) -> None:
        self._items = [Bookmark.from_dict(d) for d in data]
        self._items.sort(key=lambda b: b.frame_in)
        self.changed.emit()
