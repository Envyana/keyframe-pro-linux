from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
from PySide6.QtCore import QObject, Signal


@dataclass
class SourceClip:
    """One source on the timeline.

    `media_path` points to a video file. `in_frame`/`out_frame` are LOCAL
    frame numbers inside the source (not timeline frames). `audio_override`
    optionally points to a different audio file (used for "audio override").
    """
    media_path: str
    label: str = ""
    in_frame: int = 0
    out_frame: Optional[int] = None      # None = until end of source
    src_fps: float = 24.0
    src_total_frames: int = 0            # populated when probed
    audio_override: Optional[str] = None
    enabled: bool = True

    def length(self) -> int:
        out = self.out_frame if self.out_frame is not None else max(0, self.src_total_frames - 1)
        return max(1, out - self.in_frame + 1)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SourceClip":
        return cls(
            media_path=d["media_path"],
            label=d.get("label", ""),
            in_frame=int(d.get("in_frame", 0)),
            out_frame=None if d.get("out_frame") is None else int(d["out_frame"]),
            src_fps=float(d.get("src_fps", 24.0)),
            src_total_frames=int(d.get("src_total_frames", 0)),
            audio_override=d.get("audio_override"),
            enabled=bool(d.get("enabled", True)),
        )


class Timeline(QObject):
    """Ordered list of source clips. Provides frame -> (clip_index, local_frame)
    mapping so the player can switch sources seamlessly.
    """

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._clips: list[SourceClip] = []
        self._fps: float = 24.0

    # --- list ops ---

    def add(self, clip: SourceClip) -> None:
        self._clips.append(clip)
        self.changed.emit()

    def insert(self, index: int, clip: SourceClip) -> None:
        self._clips.insert(max(0, index), clip)
        self.changed.emit()

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._clips):
            del self._clips[index]
            self.changed.emit()

    def move(self, src: int, dst: int) -> None:
        if src == dst or not (0 <= src < len(self._clips)):
            return
        clip = self._clips.pop(src)
        self._clips.insert(max(0, min(dst, len(self._clips))), clip)
        self.changed.emit()

    def replace(self, index: int, clip: SourceClip) -> None:
        if 0 <= index < len(self._clips):
            self._clips[index] = clip
            self.changed.emit()

    def clear(self) -> None:
        self._clips.clear()
        self.changed.emit()

    def all(self) -> list[SourceClip]:
        return list(self._clips)

    def count(self) -> int:
        return len(self._clips)

    def get(self, index: int) -> Optional[SourceClip]:
        return self._clips[index] if 0 <= index < len(self._clips) else None

    # --- mapping ---

    @property
    def fps(self) -> float:
        return self._fps

    def set_fps(self, fps: float) -> None:
        if fps > 0 and abs(fps - self._fps) > 1e-6:
            self._fps = float(fps)
            self.changed.emit()

    def total_frames(self) -> int:
        return sum(c.length() for c in self._clips if c.enabled) or 1

    def clip_offset(self, index: int) -> int:
        """Timeline frame at which clip[index] starts."""
        offset = 0
        for i, c in enumerate(self._clips):
            if not c.enabled:
                continue
            if i == index:
                return offset
            offset += c.length()
        return offset

    def locate(self, timeline_frame: int) -> Optional[tuple[int, int]]:
        """Map a timeline frame to (clip_index, local_frame_in_source).

        Returns None if there are no clips.
        """
        if not self._clips:
            return None
        f = max(0, timeline_frame)
        offset = 0
        for i, c in enumerate(self._clips):
            if not c.enabled:
                continue
            length = c.length()
            if f < offset + length:
                local = c.in_frame + (f - offset)
                return (i, local)
            offset += length
        # Past end → snap to last frame of last enabled clip
        for i in range(len(self._clips) - 1, -1, -1):
            c = self._clips[i]
            if c.enabled:
                end = c.out_frame if c.out_frame is not None else max(0, c.src_total_frames - 1)
                return (i, end)
        return None

    # --- serialization ---

    def to_list(self) -> list[dict]:
        return [c.to_dict() for c in self._clips]

    def load(self, data: list[dict]) -> None:
        self._clips = [SourceClip.from_dict(d) for d in data]
        self.changed.emit()
