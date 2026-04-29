from __future__ import annotations

import json
import socket
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal, QTimer

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765


class CommandServer(QObject):
    """Tiny line-delimited JSON TCP server for DCC integrations.

    Protocol: each request is one JSON object per line; response is one
    JSON object per line. Commands are dispatched on the Qt main thread
    via QTimer.singleShot, so handlers can safely touch UI.

    Built-in commands (the host application registers handlers; defaults below):
      {"cmd":"ping"}                              → {"ok": true, "pong": true}
      {"cmd":"set_frame", "frame": 42}            → {"ok": true}
      {"cmd":"get_frame"}                         → {"ok": true, "frame": 42}
      {"cmd":"load_file", "path": "/x.mp4"}       → {"ok": true}
      {"cmd":"play"} | {"cmd":"pause"}            → {"ok": true}
      {"cmd":"set_fps", "fps": 24.0}              → {"ok": true}
      {"cmd":"add_bookmark", "frame": 42}         → {"ok": true}
      {"cmd":"info"}                              → {"ok": true, ...}
    """

    started = Signal(int)   # port
    stopped = Signal()
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._handlers: dict[str, Callable[[dict], dict]] = {}
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._port: int = 0

        self.register("ping", lambda _req: {"ok": True, "pong": True})

    def register(self, cmd: str, handler: Callable[[dict], dict]) -> None:
        """Register handler for `cmd`. Handler runs on the *calling* thread.

        For UI-touching handlers, callers should use the marshalling wrapper
        provided in `MainWindow._register_api_handlers`.
        """
        self._handlers[cmd] = handler

    def start(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        if self._thread is not None:
            return
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((host, port))
            srv.listen(8)
            srv.settimeout(0.5)
        except Exception as e:
            self.error.emit(str(e))
            return
        self._sock = srv
        self._port = srv.getsockname()[1]
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._thread.start()
        self.started.emit(self._port)

    def stop(self) -> None:
        self._stop_flag.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._sock = None
        self._thread = None
        self.stopped.emit()

    def port(self) -> int:
        return self._port

    # --- internals ---

    def _serve_loop(self) -> None:
        assert self._sock is not None
        while not self._stop_flag.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            buf = b""
            conn.settimeout(5.0)
            while not self._stop_flag.is_set():
                try:
                    chunk = conn.recv(4096)
                except (socket.timeout, ConnectionError):
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    resp = self._dispatch(line)
                    try:
                        conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                    except Exception:
                        return

    def _dispatch(self, raw: bytes) -> dict:
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": f"bad json: {e}"}
        cmd = req.get("cmd")
        if not cmd:
            return {"ok": False, "error": "missing 'cmd'"}
        h = self._handlers.get(cmd)
        if h is None:
            return {"ok": False, "error": f"unknown cmd: {cmd}"}
        try:
            return h(req)
        except Exception as e:
            return {"ok": False, "error": str(e)}
