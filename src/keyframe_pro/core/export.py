from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterator

from .timeline import Timeline


@dataclass
class ExportOptions:
    output_path: str
    fps: float = 24.0
    codec: str = "libx264"           # 'libx264' | 'libx265' | 'prores_ks' | 'gif' | 'libvpx-vp9'
    crf: int = 18                    # quality 0..51 (x264/x265)
    preset: str = "medium"
    pix_fmt: str = "yuv420p"
    width: Optional[int] = None      # None = source size
    height: Optional[int] = None
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    include_audio: bool = True


def find_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def build_concat_file(timeline: Timeline, tmp_dir: Path) -> Path:
    """Generate an ffmpeg concat-demuxer text file describing the timeline.

    Each enabled clip becomes one entry with its in/out trimmed via 'inpoint'
    and 'outpoint' (in seconds).
    """
    lines: list[str] = ["ffconcat version 1.0"]
    for c in timeline.all():
        if not c.enabled:
            continue
        # Quote and escape the path
        p = Path(c.media_path).resolve().as_posix()
        p_escaped = p.replace("'", r"'\''")
        lines.append(f"file '{p_escaped}'")
        if c.src_fps > 0:
            in_s = c.in_frame / c.src_fps
            lines.append(f"inpoint {in_s:.6f}")
            if c.out_frame is not None:
                out_s = (c.out_frame + 1) / c.src_fps
                lines.append(f"outpoint {out_s:.6f}")
    concat_path = tmp_dir / "kpro_concat.txt"
    concat_path.write_text("\n".join(lines))
    return concat_path


def build_ffmpeg_args(concat_file: Path, opts: ExportOptions) -> list[str]:
    args: list[str] = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
    ]

    vf: list[str] = []
    if opts.width and opts.height:
        vf.append(f"scale={opts.width}:{opts.height}:flags=lanczos")
    if opts.fps > 0:
        vf.append(f"fps={opts.fps}")
    if vf:
        args += ["-vf", ",".join(vf)]

    if opts.codec == "gif":
        args += ["-loop", "0", "-an"]
    else:
        args += ["-c:v", opts.codec]
        if opts.codec in ("libx264", "libx265"):
            args += ["-crf", str(opts.crf), "-preset", opts.preset]
        if opts.codec == "prores_ks":
            args += ["-profile:v", "3"]  # HQ
        if opts.pix_fmt:
            args += ["-pix_fmt", opts.pix_fmt]

        if opts.include_audio:
            args += ["-c:a", opts.audio_codec, "-b:a", opts.audio_bitrate]
        else:
            args += ["-an"]

    args += [opts.output_path]
    return args


def run_export(timeline: Timeline, opts: ExportOptions,
               tmp_dir: Optional[Path] = None) -> Iterator[str]:
    """Run ffmpeg, yielding stderr lines for progress reporting.

    Use as: ``for line in run_export(...): show_in_ui(line)``.
    """
    if find_ffmpeg() is None:
        raise FileNotFoundError("ffmpeg not found in PATH")
    if timeline.count() == 0:
        raise ValueError("Timeline is empty")

    tmp_dir = tmp_dir or Path.home() / ".cache" / "keyframe-pro-linux"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    concat = build_concat_file(timeline, tmp_dir)
    args = build_ffmpeg_args(concat, opts)

    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stderr is not None
    try:
        for line in proc.stderr:
            yield line.rstrip()
    finally:
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
