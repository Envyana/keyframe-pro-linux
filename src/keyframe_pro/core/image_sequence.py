"""Detect and load image sequences via mpv's mf:// protocol.

A "sequence" here is a set of files in the same directory whose names
share a common prefix and suffix and differ only by a zero-padded
integer (e.g. render_0001.png … render_0240.png).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr",
              ".bmp", ".webp", ".tga"}

# Match  <prefix><digits><suffix>  e.g.  ("frame_", "0001", ".png")
_NUM_RE = re.compile(r"^(.*?)(\d+)([^/\\]*)$")


def is_image_file(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def detect_sequence(path: str) -> Optional[tuple[str, int, int, float]]:
    """Given one image file in a sequence, find the rest.

    Returns (mpv_pattern, frame_count, start_index, default_fps) or None.

    `mpv_pattern` is the mf:// URL ready to pass to mpv loadfile.
    `frame_count` is the number of consecutive files matched.
    `start_index` is the integer of the first frame found.
    """
    p = Path(path)
    if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
        return None

    m = _NUM_RE.match(p.name)
    if m is None:
        return None
    prefix, num_str, suffix = m.group(1), m.group(2), m.group(3)
    width = len(num_str)
    parent = p.parent

    # Collect all files in parent dir matching <prefix><digits-of-same-width><suffix>
    pat = re.compile(rf"^{re.escape(prefix)}(\d{{{width}}}){re.escape(suffix)}$")
    matches: list[tuple[int, Path]] = []
    for f in parent.iterdir():
        mm = pat.match(f.name)
        if mm:
            try:
                matches.append((int(mm.group(1)), f))
            except ValueError:
                continue
    if len(matches) < 2:
        return None
    matches.sort()
    indices = [i for i, _ in matches]

    # Find the longest consecutive run that contains the seed file's index.
    seed_idx = int(num_str)
    start = end = seed_idx
    idx_set = set(indices)
    while start - 1 in idx_set:
        start -= 1
    while end + 1 in idx_set:
        end += 1
    count = end - start + 1
    if count < 2:
        return None

    # Build the mpv pattern. mpv's `mf://` protocol expects a printf-style
    # filename with a glob that the embedded image-format demuxer expands.
    # Using a glob is most reliable across mpv versions.
    glob_path = parent / f"{prefix}*{suffix}"
    mpv_url = f"mf://{glob_path.as_posix()}"
    return mpv_url, count, start, 24.0


def is_sequence_seed(path: str) -> bool:
    return detect_sequence(path) is not None
