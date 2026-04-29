from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from PySide6.QtCore import QObject, Signal, QPointF


@dataclass
class Stroke:
    points: list[tuple[float, float]] = field(default_factory=list)
    color: str = "#ff2222"
    width: float = 3.0
    layer: str = "fg"  # 'fg' or 'bg'
    tool: str = "pen"  # 'pen' | 'highlighter' | 'arrow' | 'rect' | 'ellipse' | 'text'
    text: str = ""     # only used when tool == 'text'
    text_size: int = 18

    def to_dict(self) -> dict:
        return {
            "points": self.points,
            "color": self.color,
            "width": self.width,
            "layer": self.layer,
            "tool": self.tool,
            "text": self.text,
            "text_size": self.text_size,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Stroke":
        return cls(
            points=[tuple(p) for p in d.get("points", [])],
            color=d.get("color", "#ff2222"),
            width=float(d.get("width", 3.0)),
            layer=d.get("layer", "fg"),
            tool=d.get("tool", "pen"),
            text=d.get("text", ""),
            text_size=int(d.get("text_size", 18)),
        )


class AnnotationModel(QObject):
    """Stores strokes per frame. Held frames render across multiple frames."""

    changed = Signal(int)  # frame number that changed (-1 means all)

    def __init__(self) -> None:
        super().__init__()
        self._frames: dict[int, list[Stroke]] = {}
        self._held: dict[int, int] = {}  # frame -> hold count (consecutive frames it persists)

    def strokes_for_frame(self, frame: int) -> list[Stroke]:
        out: list[Stroke] = []
        # held strokes from earlier frames
        for f, hold in self._held.items():
            if f <= frame < f + hold:
                out.extend(self._frames.get(f, []))
        # native strokes for this frame (if not already included via held)
        if frame not in self._held:
            out.extend(self._frames.get(frame, []))
        return out

    def add_stroke(self, frame: int, stroke: Stroke) -> None:
        self._frames.setdefault(frame, []).append(stroke)
        self.changed.emit(frame)

    def remove_last(self, frame: int) -> bool:
        if frame in self._frames and self._frames[frame]:
            self._frames[frame].pop()
            if not self._frames[frame]:
                del self._frames[frame]
            self.changed.emit(frame)
            return True
        return False

    def clear_frame(self, frame: int) -> None:
        if frame in self._frames:
            del self._frames[frame]
        if frame in self._held:
            del self._held[frame]
        self.changed.emit(frame)

    def clear_all(self) -> None:
        self._frames.clear()
        self._held.clear()
        self.changed.emit(-1)

    def set_held(self, frame: int, hold: int) -> None:
        if hold <= 1:
            self._held.pop(frame, None)
        else:
            self._held[frame] = int(hold)
        self.changed.emit(-1)

    def annotated_frames(self) -> list[int]:
        return sorted(self._frames.keys())

    def to_dict(self) -> dict:
        return {
            "frames": {str(k): [s.to_dict() for s in v] for k, v in self._frames.items()},
            "held": {str(k): v for k, v in self._held.items()},
        }

    def load(self, data: dict) -> None:
        self._frames = {
            int(k): [Stroke.from_dict(s) for s in v]
            for k, v in data.get("frames", {}).items()
        }
        self._held = {int(k): int(v) for k, v in data.get("held", {}).items()}
        self.changed.emit(-1)
