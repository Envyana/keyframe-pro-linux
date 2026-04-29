from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProjectSource:
    path: str
    in_frame: Optional[int] = None
    out_frame: Optional[int] = None
    audio_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "in_frame": self.in_frame,
            "out_frame": self.out_frame,
            "audio_path": self.audio_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectSource":
        return cls(
            path=d["path"],
            in_frame=d.get("in_frame"),
            out_frame=d.get("out_frame"),
            audio_path=d.get("audio_path"),
        )


@dataclass
class Project:
    version: int = 1
    sources: list[ProjectSource] = field(default_factory=list)
    bookmarks: list[dict] = field(default_factory=list)
    annotations: dict = field(default_factory=dict)
    fps: float = 24.0
    speed: float = 1.0
    loop_mode: str = "loop"  # 'none' | 'loop' | 'pingpong'

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "sources": [s.to_dict() for s in self.sources],
            "bookmarks": self.bookmarks,
            "annotations": self.annotations,
            "fps": self.fps,
            "speed": self.speed,
            "loop_mode": self.loop_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(
            version=d.get("version", 1),
            sources=[ProjectSource.from_dict(x) for x in d.get("sources", [])],
            bookmarks=d.get("bookmarks", []),
            annotations=d.get("annotations", {}),
            fps=float(d.get("fps", 24.0)),
            speed=float(d.get("speed", 1.0)),
            loop_mode=d.get("loop_mode", "loop"),
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        p = Path(path)
        return cls.from_dict(json.loads(p.read_text()))
