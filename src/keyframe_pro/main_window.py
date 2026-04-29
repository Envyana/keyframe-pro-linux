from __future__ import annotations

from pathlib import Path
from typing import Callable
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QWidget, QVBoxLayout, QDockWidget,
    QLabel, QStatusBar, QMessageBox, QStackedLayout
)

from .player.mpv_player import MpvPlayer
from .widgets.timeline import TimelineWidget
from .widgets.transport import TransportBar
from .widgets.annotation import AnnotationOverlay
from .widgets.annotation_toolbar import AnnotationToolbar
from .widgets.bookmark_panel import BookmarkPanel
from .widgets.source_panel import SourcePanel
from .widgets.compare_view import CompareView, CompareMode
from .widgets.compare_toolbar import CompareToolbar
from .widgets.export_dialog import ExportDialog
from .widgets.preferences import PreferencesDialog
from .core.bookmarks import BookmarkModel, Bookmark
from .core.annotations import AnnotationModel
from .core.project import Project, ProjectSource
from .core.timeline import Timeline, SourceClip
from .core.settings import Settings, DEFAULT_HOTKEYS
from .api.server import CommandServer

VIDEO_FILTER = (
    "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mpg *.mpeg *.wmv "
    "*.flv *.ogv *.gif);;Image sequences (*.png *.jpg *.jpeg *.exr *.tif *.tiff);;"
    "All files (*)"
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Keyframe Pro Linux")
        self.resize(1320, 820)

        # ---------- models ----------
        self.bookmarks = BookmarkModel()
        self.annotations = AnnotationModel()
        self.timeline_model = Timeline()
        self.settings = Settings()

        # ---------- players (A is primary, B is comparison) ----------
        self.player = MpvPlayer()         # A
        self.player_b = MpvPlayer()       # B (compare)

        # Compare view hosts both players
        self.compare_view = CompareView(self.player, self.player_b)

        # Annotation overlay sits on top of compare_view
        self.viewer_container = QWidget()
        viewer_stack = QStackedLayout(self.viewer_container)
        viewer_stack.setStackingMode(QStackedLayout.StackAll)
        viewer_stack.setContentsMargins(0, 0, 0, 0)
        self.overlay = AnnotationOverlay(self.annotations, parent=self.viewer_container)
        viewer_stack.addWidget(self.overlay)
        viewer_stack.addWidget(self.compare_view)
        self.overlay.raise_()
        self.compare_view.installEventFilter(self)

        # ---------- toolbars / panels ----------
        self.timeline_widget = TimelineWidget()
        self.timeline_widget.set_bookmarks(self.bookmarks)
        self.transport = TransportBar()
        self.ann_toolbar = AnnotationToolbar()
        self.compare_toolbar = CompareToolbar()
        self.bookmark_panel = BookmarkPanel(self.bookmarks)
        self.source_panel = SourcePanel(self.timeline_model)

        # ---------- central layout ----------
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.compare_toolbar)
        v.addWidget(self.ann_toolbar)
        v.addWidget(self.viewer_container, 1)
        v.addWidget(self.timeline_widget)
        v.addWidget(self.transport)
        self.setCentralWidget(central)

        # ---------- docks ----------
        dock_bm = QDockWidget("Bookmarks", self)
        dock_bm.setWidget(self.bookmark_panel)
        dock_bm.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, dock_bm)

        dock_src = QDockWidget("Sources", self)
        dock_src.setWidget(self.source_panel)
        dock_src.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, dock_src)
        self.tabifyDockWidget(dock_bm, dock_src)
        dock_bm.raise_()

        # ---------- status bar ----------
        self.setStatusBar(QStatusBar())
        self.lbl_status = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.lbl_status)
        self.lbl_api = QLabel("")
        self.statusBar().addWidget(self.lbl_api)

        # ---------- menus, wiring, shortcuts ----------
        self._action_callbacks: dict[str, Callable[[], None]] = {}
        self._shortcuts: dict[str, QShortcut] = {}
        self._build_menu()
        self._wire()
        self._wire_actions()
        self._apply_hotkeys()

        # ---------- defaults ----------
        self.player.set_volume(80.0)
        self.player.set_loop_mode("loop")
        self.player_b.set_volume(0.0)            # B muted by default
        self.player_b.set_mute(True)
        self._sync_b: bool = True

        # ---------- API server ----------
        self.api = CommandServer()
        self._register_api_handlers()
        self.api.started.connect(lambda p: self.lbl_api.setText(f"API: 127.0.0.1:{p}"))
        self.api.error.connect(lambda e: self.lbl_api.setText(f"API err: {e}"))
        QTimer.singleShot(300, self.api.start)

        # ---------- state ----------
        self._project_path: str | None = None
        self._current_file: str | None = None

    # =========================================================
    # menu
    # =========================================================
    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&File")
        for label, slot, sc in [
            ("&Open Video...", self.open_file, QKeySequence.Open),
            ("&Add Source to Timeline...", self.add_source, QKeySequence("Ctrl+Shift+O")),
            (None, None, None),
            ("Open &Project...", self.open_project, None),
            ("&Save Project", self.save_project, QKeySequence.Save),
            ("Save Project &As...", self.save_project_as, QKeySequence("Ctrl+Shift+S")),
            (None, None, None),
            ("&Export Timeline…", self.export_timeline, QKeySequence("Ctrl+E")),
            (None, None, None),
            ("&Quit", self.close, QKeySequence.Quit),
        ]:
            if label is None:
                m_file.addSeparator()
                continue
            a = QAction(label, self)
            if sc is not None:
                a.setShortcut(sc)
            a.triggered.connect(slot)
            m_file.addAction(a)

        m_view = self.menuBar().addMenu("&View")
        a_top = QAction("Always on &Top", self, checkable=True)
        a_top.toggled.connect(self._toggle_on_top)
        m_view.addAction(a_top)
        a_full = QAction("&Fullscreen", self)
        a_full.triggered.connect(self._toggle_fullscreen)
        m_view.addAction(a_full)

        m_edit = self.menuBar().addMenu("&Edit")
        a_pref = QAction("&Preferences (Hotkeys)…", self)
        a_pref.triggered.connect(self._open_preferences)
        m_edit.addAction(a_pref)

        m_help = self.menuBar().addMenu("&Help")
        a_about = QAction("&About", self)
        a_about.triggered.connect(self._about)
        m_help.addAction(a_about)

    def _about(self) -> None:
        QMessageBox.information(
            self, "About",
            "Keyframe Pro Linux v0.2\n\n"
            "Cross-platform animation reference player\n"
            "inspired by Keyframe Pro 2.\n\n"
            "Built with PySide6 + libmpv.",
        )

    # =========================================================
    # signal wiring
    # =========================================================
    def _wire(self) -> None:
        # player A → ui
        self.player.position_changed.connect(self._on_position)
        self.player.frame_changed.connect(self._on_frame)
        self.player.duration_changed.connect(self._on_duration)
        self.player.fps_changed.connect(self._on_fps)
        self.player.play_state_changed.connect(self.transport.set_play_icon)

        # transport → player A
        self.transport.play_toggled.connect(self.player.toggle_play)
        self.transport.step_requested.connect(self.player.step_frame)
        self.transport.speed_changed.connect(self.player.set_speed)
        self.transport.loop_mode_changed.connect(self.player.set_loop_mode)
        self.transport.audio_offset_changed.connect(self.player.set_audio_offset)
        self.transport.volume_changed.connect(self.player.set_volume)
        self.transport.mute_toggled.connect(self.player.set_mute)
        self.transport.set_in_requested.connect(self._set_in)
        self.transport.set_out_requested.connect(self._set_out)
        self.transport.clear_inout_requested.connect(self._clear_inout)
        self.transport.add_bookmark_requested.connect(self._add_bookmark)

        # timeline_widget → player
        self.timeline_widget.seeked.connect(self._on_seek_frame)
        self.timeline_widget.range_changed.connect(self._on_inout_changed)

        # bookmark / annotation
        self.annotations.changed.connect(
            lambda _f: self.timeline_widget.set_annotated_frames(self.annotations.annotated_frames())
        )
        self.bookmark_panel.bookmark_activated.connect(self._goto_bookmark)
        self.bookmark_panel.delete_requested.connect(self.bookmarks.remove)

        # annotation toolbar
        self.ann_toolbar.annotate_toggled.connect(self.overlay.set_active)
        self.ann_toolbar.tool_changed.connect(self.overlay.set_tool)
        self.ann_toolbar.color_changed.connect(self.overlay.set_color)
        self.ann_toolbar.width_changed.connect(self.overlay.set_width)
        self.ann_toolbar.layer_changed.connect(self.overlay.set_layer)
        self.ann_toolbar.ghost_changed.connect(self.overlay.set_ghost)
        self.ann_toolbar.held_changed.connect(self._on_hold_changed)
        self.ann_toolbar.clear_frame_requested.connect(
            lambda: self.annotations.clear_frame(self.player.current_frame())
        )
        self.ann_toolbar.undo_requested.connect(
            lambda: self.annotations.remove_last(self.player.current_frame())
        )

        # compare toolbar
        self.compare_toolbar.mode_changed.connect(
            lambda m: self.compare_view.set_mode(CompareMode(m))
        )
        self.compare_toolbar.wipe_changed.connect(self.compare_view.set_wipe)
        self.compare_view.wipe_changed.connect(self.compare_toolbar.set_wipe)
        self.compare_toolbar.sync_toggled.connect(self._set_sync_b)
        self.compare_toolbar.load_b_requested.connect(self._load_b)

        # source panel
        self.source_panel.activate_requested.connect(self._activate_source)
        self.source_panel.add_files_requested.connect(self._add_sources)
        self.timeline_model.changed.connect(self._on_timeline_changed)

    # =========================================================
    # actions (callbacks for hotkeys)
    # =========================================================
    def _wire_actions(self) -> None:
        self._action_callbacks = {
            "play_toggle": self.player.toggle_play,
            "step_back_1": lambda: self.player.step_frame(-1),
            "step_fwd_1":  lambda: self.player.step_frame(1),
            "step_back_10": lambda: self.player.step_frame(-10),
            "step_fwd_10":  lambda: self.player.step_frame(10),
            "goto_start": lambda: self.player.seek_frame(0),
            "goto_end":   lambda: self.player.seek_frame(max(0, self.player.total_frames()-1)),
            "set_in":     self._set_in,
            "set_out":    self._set_out,
            "clear_inout": self._clear_inout,
            "add_bookmark": self._add_bookmark,
            "add_range_bm": self._add_range_bookmark,
            "prev_bookmark": self._goto_prev_bookmark,
            "next_bookmark": self._goto_next_bookmark,
            "annotate_toggle": lambda: self.ann_toolbar.btn_toggle.toggle(),
            "undo_stroke": lambda: self.annotations.remove_last(self.player.current_frame()),
            "clear_all_ann": self.annotations.clear_all,
            "mute_toggle": lambda: self.transport.btn_mute.toggle(),
            "fullscreen": self._toggle_fullscreen,
            "always_on_top": self._toggle_on_top_action,
            "compare_a": lambda: self._set_compare_mode(CompareMode.SINGLE_A),
            "compare_b": lambda: self._set_compare_mode(CompareMode.SINGLE_B),
            "compare_wipe": lambda: self._set_compare_mode(CompareMode.WIPE),
            "compare_split_v": lambda: self._set_compare_mode(CompareMode.SPLIT_V),
            "compare_split_h": lambda: self._set_compare_mode(CompareMode.SPLIT_H),
        }

    def _apply_hotkeys(self) -> None:
        # Clear existing
        for s in self._shortcuts.values():
            s.setEnabled(False)
            s.deleteLater()
        self._shortcuts.clear()

        for action_id, cb in self._action_callbacks.items():
            seq = self.settings.hotkey(action_id)
            if not seq:
                continue
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(cb)
            self._shortcuts[action_id] = sc

    def _open_preferences(self) -> None:
        dlg = PreferencesDialog(self.settings, self)
        if dlg.exec():
            self._apply_hotkeys()
            self.lbl_status.setText("Hotkeys updated")

    # =========================================================
    # file ops
    # =========================================================
    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", VIDEO_FILTER)
        if path:
            self.load_video(path)

    def load_video(self, path: str) -> None:
        self._current_file = path
        self.setWindowTitle(f"Keyframe Pro Linux — {Path(path).name}")
        self.player.load_file(path)
        if self._sync_b and self.player_b is not None:
            self.player_b.load_file(path)
        # Reset timeline to a single-clip representation
        self.timeline_model.clear()
        self.timeline_model.add(SourceClip(media_path=path, label=Path(path).name))
        self.lbl_status.setText(f"Loaded: {Path(path).name}")

    def add_source(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add sources to timeline", "", VIDEO_FILTER
        )
        if paths:
            self._add_sources(paths)

    def _add_sources(self, paths: list[str]) -> None:
        for p in paths:
            self.timeline_model.add(SourceClip(media_path=p, label=Path(p).name))
        # Auto-load first if none loaded yet
        if self._current_file is None and self.timeline_model.count() > 0:
            first = self.timeline_model.get(0)
            if first:
                self.load_video(first.media_path)

    def _activate_source(self, index: int) -> None:
        clip = self.timeline_model.get(index)
        if clip is None:
            return
        # Switch primary source
        self._current_file = clip.media_path
        self.setWindowTitle(f"Keyframe Pro Linux — {Path(clip.media_path).name}")
        self.player.load_file(clip.media_path)
        if self._sync_b:
            self.player_b.load_file(clip.media_path)

    def _on_timeline_changed(self) -> None:
        # Update status with timeline length
        n = self.timeline_model.count()
        self.lbl_status.setText(f"Timeline: {n} source(s)")

    # ---- compare ----

    def _load_b(self, path: str) -> None:
        self.player_b.load_file(path)
        # Disable sync briefly so B can settle
        self.lbl_status.setText(f"B = {Path(path).name}")

    def _set_sync_b(self, on: bool) -> None:
        self._sync_b = on

    def _set_compare_mode(self, mode: CompareMode) -> None:
        self.compare_view.set_mode(mode)
        # Reflect in toolbar
        for m, btn in self.compare_toolbar._buttons.items():
            btn.setChecked(m == mode.value)

    # ---- project ----

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Project (*.kproj *.json);;All files (*)"
        )
        if not path:
            return
        try:
            proj = Project.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")
            return
        self._project_path = path
        self.bookmarks.load(proj.bookmarks)
        self.annotations.load(proj.annotations)
        self.player.set_speed(proj.speed)
        self.player.set_loop_mode(proj.loop_mode)
        self.timeline_model.load([s.to_dict() for s in proj.sources])
        if proj.sources:
            self.load_video(proj.sources[0].path)
        self.lbl_status.setText(f"Project: {Path(path).name}")

    def save_project(self) -> None:
        if not self._project_path:
            self.save_project_as()
            return
        self._do_save(self._project_path)

    def save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "Project (*.kproj);;All files (*)"
        )
        if not path:
            return
        if not path.endswith(".kproj"):
            path += ".kproj"
        self._project_path = path
        self._do_save(path)

    def _do_save(self, path: str) -> None:
        sources = []
        for c in self.timeline_model.all():
            sources.append(ProjectSource(
                path=c.media_path,
                in_frame=c.in_frame,
                out_frame=c.out_frame,
                audio_path=c.audio_override,
            ))
        if not sources and self._current_file:
            sources = [ProjectSource(path=self._current_file)]

        proj = Project(
            sources=sources,
            bookmarks=self.bookmarks.to_list(),
            annotations=self.annotations.to_dict(),
            fps=self.player.fps(),
            speed=self.player.speed(),
            loop_mode=self.player.loop_mode(),
        )
        try:
            proj.save(path)
            self.lbl_status.setText(f"Saved: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed:\n{e}")

    def export_timeline(self) -> None:
        # Make sure clips have src_fps populated (use player A's fps as default)
        fps = self.player.fps() or 24.0
        for c in self.timeline_model.all():
            if c.src_fps <= 0:
                c.src_fps = fps
        dlg = ExportDialog(self.timeline_model, default_fps=fps, parent=self)
        dlg.exec()

    # =========================================================
    # in/out + bookmarks
    # =========================================================
    def _set_in(self) -> None:
        f = self.player.current_frame()
        out = self.timeline_widget.out_frame()
        if f >= out:
            out = min(self.player.total_frames() - 1, f + 1)
        self.timeline_widget.set_in_out(f, out)

    def _set_out(self) -> None:
        f = self.player.current_frame()
        in_f = self.timeline_widget.in_frame()
        if f <= in_f:
            in_f = max(0, f - 1)
        self.timeline_widget.set_in_out(in_f, f)

    def _clear_inout(self) -> None:
        self.timeline_widget.set_in_out(0, max(0, self.player.total_frames() - 1))

    def _on_inout_changed(self, in_f: int, out_f: int) -> None:
        self.lbl_status.setText(f"In: {in_f}  Out: {out_f}  ({out_f - in_f + 1} frames)")

    def _add_bookmark(self) -> None:
        f = self.player.current_frame()
        self.bookmarks.add(Bookmark(frame_in=f))
        self.lbl_status.setText(f"Bookmark @ frame {f}")

    def _add_range_bookmark(self) -> None:
        in_f = self.timeline_widget.in_frame()
        out_f = self.timeline_widget.out_frame()
        self.bookmarks.add(Bookmark(frame_in=in_f, frame_out=out_f, color="#22aaff"))
        self.lbl_status.setText(f"Range bookmark {in_f}–{out_f}")

    def _goto_bookmark(self, bm: Bookmark) -> None:
        self.player.seek_frame(bm.frame_in)
        if self._sync_b:
            self.player_b.seek_frame(bm.frame_in)

    def _goto_next_bookmark(self) -> None:
        bm = self.bookmarks.next_after(self.player.current_frame())
        if bm:
            self._goto_bookmark(bm)

    def _goto_prev_bookmark(self) -> None:
        bm = self.bookmarks.prev_before(self.player.current_frame())
        if bm:
            self._goto_bookmark(bm)

    def _on_hold_changed(self, n: int) -> None:
        self.annotations.set_held(self.player.current_frame(), int(n))

    def _on_seek_frame(self, frame: int) -> None:
        self.player.seek_frame(frame)
        if self._sync_b:
            self.player_b.seek_frame(frame)

    # =========================================================
    # player → UI
    # =========================================================
    def _on_position(self, _seconds: float) -> None:
        pass

    def _on_frame(self, frame: int) -> None:
        self.timeline_widget.set_current_frame(frame)
        self.overlay.set_frame(frame)
        if self._sync_b and abs(self.player_b.current_frame() - frame) > 1:
            self.player_b.seek_frame(frame)

        in_f = self.timeline_widget.in_frame()
        out_f = self.timeline_widget.out_frame()
        total = self.player.total_frames()
        if total > 0 and out_f < total - 1 and frame > out_f:
            if self.player.loop_mode() in ("loop", "pingpong"):
                self.player.seek_frame(in_f)
            else:
                self.player.pause()
        fps = self.player.fps() or 24.0
        self.lbl_status.setText(
            f"Frame {frame:>5} / {max(0, self.player.total_frames()-1):>5}   "
            f"{frame/fps:6.2f}s   FPS {fps:.2f}"
        )

    def _on_duration(self, _sec: float) -> None:
        QTimer.singleShot(150, self._sync_total)

    def _on_fps(self, fps: float) -> None:
        self.bookmark_panel.set_fps(fps)
        self.timeline_model.set_fps(fps)
        # Push fps into source clips that don't have it
        for c in self.timeline_model.all():
            if c.src_fps <= 0:
                c.src_fps = fps
        self._sync_total()

    def _sync_total(self) -> None:
        total = self.player.total_frames()
        if total > 0:
            self.timeline_widget.set_total_frames(total)
            self.timeline_widget.set_in_out(0, total - 1)

    # =========================================================
    # view
    # =========================================================
    def _toggle_on_top(self, on: bool) -> None:
        flags = self.windowFlags()
        if on:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    def _toggle_on_top_action(self) -> None:
        self._toggle_on_top(not bool(self.windowFlags() & Qt.WindowStaysOnTopHint))

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # =========================================================
    # API server handlers
    # =========================================================
    def _register_api_handlers(self) -> None:
        # Use QTimer.singleShot to marshal to GUI thread.
        def ui(fn):
            def wrap(req: dict) -> dict:
                result_box: dict = {"r": None}
                done = [False]
                def runner():
                    try:
                        result_box["r"] = fn(req)
                    except Exception as e:
                        result_box["r"] = {"ok": False, "error": str(e)}
                    done[0] = True
                QTimer.singleShot(0, runner)
                # Spin briefly waiting for the GUI thread
                import time
                t0 = time.monotonic()
                while not done[0] and time.monotonic() - t0 < 2.0:
                    time.sleep(0.005)
                return result_box["r"] or {"ok": False, "error": "ui timeout"}
            return wrap

        @ui
        def h_set_frame(req: dict) -> dict:
            self.player.seek_frame(int(req.get("frame", 0)))
            if self._sync_b:
                self.player_b.seek_frame(int(req.get("frame", 0)))
            return {"ok": True}

        @ui
        def h_get_frame(_req: dict) -> dict:
            return {"ok": True, "frame": self.player.current_frame()}

        @ui
        def h_load_file(req: dict) -> dict:
            p = req.get("path")
            if not p:
                return {"ok": False, "error": "missing path"}
            self.load_video(str(p))
            return {"ok": True}

        @ui
        def h_play(_req: dict) -> dict:
            self.player.play()
            return {"ok": True}

        @ui
        def h_pause(_req: dict) -> dict:
            self.player.pause()
            return {"ok": True}

        @ui
        def h_set_fps(req: dict) -> dict:
            fps = float(req.get("fps", 24.0))
            self.timeline_model.set_fps(fps)
            return {"ok": True, "fps": fps}

        @ui
        def h_add_bookmark(req: dict) -> dict:
            f = int(req.get("frame", self.player.current_frame()))
            self.bookmarks.add(Bookmark(
                frame_in=f,
                name=str(req.get("name", "")),
                color=str(req.get("color", "#ffcc00")),
            ))
            return {"ok": True, "frame": f}

        @ui
        def h_info(_req: dict) -> dict:
            return {
                "ok": True,
                "current_file": self._current_file,
                "frame": self.player.current_frame(),
                "total_frames": self.player.total_frames(),
                "fps": self.player.fps(),
                "playing": self.player.is_playing(),
                "version": "0.2.0",
            }

        for cmd, h in [
            ("set_frame", h_set_frame), ("get_frame", h_get_frame),
            ("load_file", h_load_file), ("play", h_play), ("pause", h_pause),
            ("set_fps", h_set_fps), ("add_bookmark", h_add_bookmark),
            ("info", h_info),
        ]:
            self.api.register(cmd, h)

    # =========================================================
    # overlay sizing / cleanup
    # =========================================================
    def eventFilter(self, obj, ev):
        if obj is self.compare_view and ev.type() in (ev.Type.Resize, ev.Type.Show):
            self.overlay.setGeometry(self.compare_view.geometry())
            self.overlay.raise_()
        return super().eventFilter(obj, ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.overlay.setGeometry(self.compare_view.geometry())
        self.overlay.raise_()

    def closeEvent(self, ev):
        try:
            self.api.stop()
        except Exception:
            pass
        try:
            self.player.shutdown()
            self.player_b.shutdown()
        except Exception:
            pass
        super().closeEvent(ev)
