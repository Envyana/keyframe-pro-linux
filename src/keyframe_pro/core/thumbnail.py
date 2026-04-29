"""ffmpeg-based thumbnail generator with on-disk cache.

Generates a small PNG for a given video file at a chosen seek time.
Cache key is sha1(media_path + mtime + width). Returns the cached
path immediately if it exists. Generation is synchronous (subprocess
call, blocks the calling thread); use a QThread or QRunnable for
async usage from the UI.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional


CACHE_DIR = Path.home() / ".cache" / "keyframe-pro" / "thumbs"


def cache_key(media_path: str, width: int) -> str:
    p = Path(media_path)
    try:
        mtime = int(p.stat().st_mtime)
    except OSError:
        mtime = 0
    h = hashlib.sha1(f"{p.resolve().as_posix()}|{mtime}|{width}".encode()).hexdigest()
    return h


def cached_path(media_path: str, width: int = 160) -> Path:
    return CACHE_DIR / f"{cache_key(media_path, width)}.png"


def has_thumbnail(media_path: str, width: int = 160) -> bool:
    return cached_path(media_path, width).exists()


def generate_thumbnail(
    media_path: str,
    seek_seconds: float = 1.0,
    width: int = 160,
    timeout: float = 10.0,
) -> Optional[Path]:
    """Generate a thumbnail PNG. Returns the path on success, None on failure.

    Returns the cached path immediately if it already exists.
    """
    if shutil.which("ffmpeg") is None:
        return None
    out = cached_path(media_path, width)
    if out.exists():
        return out
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        "ffmpeg", "-y",
        "-ss", f"{max(0.0, seek_seconds):.3f}",
        "-i", str(media_path),
        "-frames:v", "1",
        "-vf", f"scale={int(width)}:-1:flags=lanczos",
        "-loglevel", "error",
        str(out),
    ]
    try:
        subprocess.run(args, check=True, timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out if out.exists() else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError, OSError):
        return None


def clear_cache() -> int:
    """Delete all cached thumbnails. Returns count removed."""
    if not CACHE_DIR.exists():
        return 0
    n = 0
    for f in CACHE_DIR.iterdir():
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n
