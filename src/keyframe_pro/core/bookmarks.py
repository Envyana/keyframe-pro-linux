from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
from PySide6.QtCore import QObject, Signal


@dataclass
class Bookmark:
    frame_in: int
    frame_out: Optional[int] = None
    name: str = ""
    color: str = "#ffcc00"
    note: str = ""

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

    def to_list(self) -> list[dict]:
        return [b.to_dict() for b in self._items]

    def load(self, data: list[dict]) -> None:
        self._items = [Bookmark.from_dict(d) for d in data]
        self._items.sort(key=lambda b: b.frame_in)
        self.changed.emit()
