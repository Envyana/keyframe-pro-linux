"""Blender → Keyframe Pro Linux frame sync.

Run inside Blender's scripting workspace. Adds a frame_change handler that
pushes the current frame to KPro.

Usage:
    import blender_sync
    blender_sync.start_sync()
    blender_sync.stop_sync()
    blender_sync.send_render("/tmp/render.mp4")
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

try:
    from keyframe_pro.api.client import KproClient
except Exception:
    import json, socket
    class KproClient:  # type: ignore
        def __init__(self, host="127.0.0.1", port=18765, timeout=2.0):
            self.host, self.port, self.timeout = host, port, timeout
        def _send(self, payload):
            with socket.create_connection((self.host, self.port), self.timeout) as s:
                s.sendall((json.dumps(payload) + "\n").encode())
                buf = b""
                while b"\n" not in buf:
                    c = s.recv(4096)
                    if not c: break
                    buf += c
                return json.loads(buf.split(b"\n", 1)[0].decode())
        def ping(self):
            try: return self._send({"cmd": "ping"}).get("pong", False)
            except Exception: return False
        def set_frame(self, f): return self._send({"cmd": "set_frame", "frame": int(f)})
        def load_file(self, p): return self._send({"cmd": "load_file", "path": str(p)})


_client = KproClient()


def _on_frame_change(scene):
    try:
        _client.set_frame(int(scene.frame_current))
    except Exception as e:
        print(f"[kpro] push_frame error: {e}")


def start_sync():
    import bpy  # type: ignore
    if _on_frame_change in bpy.app.handlers.frame_change_post:
        return
    if not _client.ping():
        print("[kpro] server not reachable on 127.0.0.1:18765")
        return
    bpy.app.handlers.frame_change_post.append(_on_frame_change)
    print("[kpro] sync started")


def stop_sync():
    import bpy  # type: ignore
    if _on_frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_on_frame_change)
        print("[kpro] sync stopped")


def send_render(path: str):
    return _client.load_file(path)
