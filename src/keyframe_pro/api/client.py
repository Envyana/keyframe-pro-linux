"""Lightweight client for the Keyframe Pro Linux command server.

Designed to drop into Maya / Blender / Houdini's bundled Python with no
PySide / extra deps required — only the stdlib.

Usage:
    from keyframe_pro.api.client import KproClient
    c = KproClient()
    c.set_frame(120)
    c.add_bookmark(120)
    c.load_file("/path/to/playblast.mp4")
"""
from __future__ import annotations

import json
import socket
from typing import Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765


class KproClient:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def _send(self, payload: dict) -> dict:
        with socket.create_connection((self.host, self.port), self.timeout) as s:
            s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            buf = b""
            s.settimeout(self.timeout)
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n", 1)[0]
            return json.loads(line.decode("utf-8")) if line else {"ok": False, "error": "no reply"}

    # --- convenience methods ---

    def ping(self) -> bool:
        try:
            return bool(self._send({"cmd": "ping"}).get("pong"))
        except Exception:
            return False

    def info(self) -> dict:
        return self._send({"cmd": "info"})

    def set_frame(self, frame: int) -> dict:
        return self._send({"cmd": "set_frame", "frame": int(frame)})

    def get_frame(self) -> Optional[int]:
        r = self._send({"cmd": "get_frame"})
        return r.get("frame") if r.get("ok") else None

    def load_file(self, path: str) -> dict:
        return self._send({"cmd": "load_file", "path": str(path)})

    def play(self) -> dict:
        return self._send({"cmd": "play"})

    def pause(self) -> dict:
        return self._send({"cmd": "pause"})

    def set_fps(self, fps: float) -> dict:
        return self._send({"cmd": "set_fps", "fps": float(fps)})

    def add_bookmark(self, frame: int, name: str = "", color: str = "#ffcc00") -> dict:
        return self._send({"cmd": "add_bookmark", "frame": int(frame),
                           "name": name, "color": color})
