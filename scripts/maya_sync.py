"""Maya → Keyframe Pro Linux frame sync.

Drop this into Maya's script editor (Python) or save and source it. Connects
to the Keyframe Pro command server (default 127.0.0.1:18765) and pushes
Maya's current frame whenever the timeline changes.

Usage in Maya:
    import maya_sync
    maya_sync.start_sync()         # begin pushing frame
    maya_sync.stop_sync()          # stop
    maya_sync.send_playblast("/tmp/blast.mp4")  # load a playblast in KPro
"""
from __future__ import annotations

import os
import sys
import json
import socket

# Add the parent of this file to sys.path if running ad-hoc, so the
# stdlib-only client can be imported.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

try:
    from keyframe_pro.api.client import KproClient
except Exception:
    # Fallback: inline a minimal client.
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
        def add_bookmark(self, f, name="", color="#ffcc00"):
            return self._send({"cmd": "add_bookmark", "frame": int(f),
                               "name": name, "color": color})


_client = KproClient()
_job_id = None


def _push_frame(*_args):
    try:
        import maya.cmds as cmds  # type: ignore
        f = int(round(cmds.currentTime(query=True)))
        _client.set_frame(f)
    except Exception as e:
        print(f"[kpro] push_frame error: {e}")


def start_sync():
    """Begin pushing Maya's current frame to KPro on every change."""
    global _job_id
    import maya.cmds as cmds  # type: ignore
    if _job_id is not None:
        return
    if not _client.ping():
        cmds.warning("KPro server not reachable on 127.0.0.1:18765")
        return
    _job_id = cmds.scriptJob(event=["timeChanged", _push_frame])
    print(f"[kpro] sync started (job {_job_id})")


def stop_sync():
    global _job_id
    import maya.cmds as cmds  # type: ignore
    if _job_id is not None:
        cmds.scriptJob(kill=_job_id, force=True)
        _job_id = None
        print("[kpro] sync stopped")


def send_playblast(path: str):
    """Tell KPro to load `path` (e.g. a freshly-rendered playblast)."""
    return _client.load_file(path)


def bookmark_current_frame(name: str = "", color: str = "#ffcc00"):
    import maya.cmds as cmds  # type: ignore
    f = int(round(cmds.currentTime(query=True)))
    return _client.add_bookmark(f, name=name, color=color)
