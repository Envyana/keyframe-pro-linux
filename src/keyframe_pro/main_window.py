from __future__ import annotations

from pathlib import Path
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
from .core.bookmarks import BookmarkModel, Bookmark
from .core.annotations import AnnotationModel
from .core.project import Project, ProjectSource

VIDEO_FILTER = (
    "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mpg *.mpeg *.wmv "
    "*.flv *.ogv *.gif);;Image sequences (*.png *.jpg *.jpeg *.exr *.tif *.tiff);;"
    "All files (*)"
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Keyframe Pro Linux")
        self.resize(1280, 800)

        # Models
        self.bookmarks = BookmarkModel()
        self.annotations = AnnotationModel()

        # Player
        self.player = MpvPlayer()

        # Annotation overlay placed on top of player via stacked layout
        self.viewer_container = QWidget()
        viewer_stack = QStackedLayout(self.viewer_container)
        viewer_stack.setStackingMode(QStackedLayout.StackAll)
        viewer_stack.setContentsMargins(0, 0, 0, 0)
        self.overlay = AnnotationOverlay(self.annotations, parent=self.viewer_container)
        viewer_stack.addWidget(self.overlay)
        viewer_stack.addWidget(self.player)
        self.overlay.raise_()

        # Make sure overlay matches player size — install eventFilter
        self.player.installEventFilter(self)

        # Timeline + transport
        self.timeline = TimelineWidget()
        self.timeline.set_bookmarks(self.bookmarks)
        self.transport = TransportBar()

        # Annotation toolbar
        self.ann_toolbar = AnnotationToolbar()

        # Central layout
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.ann_toolbar)
        v.addWidget(self.viewer_container, 1)
        v.addWidget(self.timeline)
        v.addWidget(self.transport)
        self.setCentralWidget(central)

        # Bookmark dock
        self.bookmark_panel = BookmarkPanel(self.bookmarks)
        dock = QDockWidget("Bookmarks", self)
        dock.setWidget(self.bookmark_panel)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # Status bar
        self.setStatusBar(QStatusBar())
        self.lbl_status = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.lbl_status)

        # Menus
        self._build_menu()

        # Wire signals
        self._wire()
        self._wire_shortcuts()

        # Defaults
        self.player.set_volume(80.0)
        self.player.set_loop_mode("loop")

        self._project_path: str | None = None
        self._current_file: str | None = None

    # ------------- menus -------------

    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&File")
        a_open = QAction("&Open Video...", self, shortcut=QKeySequence.Open)
        a_open.triggered.connect(self.open_file)
        a_open_proj = QAction("Open &Project...", self)
        a_open_proj.triggered.connect(self.open_project)
        a_save_proj = QAction("&Save Project", self, shortcut=QKeySequence.Save)
        a_save_proj.triggered.connect(self.save_project)
        a_save_proj_as = QAction("Save Project &As...", self,
                                 shortcut=QKeySequence("Ctrl+Shift+S"))
        a_save_proj_as.triggered.connect(self.save_project_as)
        a_quit = QAction("&Quit", self, shortcut=QKeySequence.Quit)
        a_quit.triggered.connect(self.close)
        m_file.addAction(a_open)
        m_file.addSeparator()
        m_file.addAction(a_open_proj)
        m_file.addAction(a_save_proj)
        m_file.addAction(a_save_proj_as)
        m_file.addSeparator()
        m_file.addAction(a_quit)

        m_view = self.menuBar().addMenu("&View")
        a_top = QAction("Always on &Top", self, checkable=True,
                       shortcut=QKeySequence("T"))
        a_top.toggled.connect(self._toggle_on_top)
        m_view.addAction(a_top)

        a_full = QAction("&Fullscreen", self, shortcut=QKeySequence("F"))
        a_full.triggered.connect(self._toggle_fullscreen)
        m_view.addAction(a_full)

        m_help = self.menuBar().addMenu("&Help")
        a_about = QAction("&About", self)
        a_about.triggered.connect(self._about)
        m_help.addAction(a_about)

    def _about(self) -> None:
        QMessageBox.information(
            self, "About",
            "Keyframe Pro Linux\n\n"
            "Cross-platform animation reference player\n"
            "inspired by Keyframe Pro 2.\n\n"
            "Built with PySide6 + libmpv.",
        )

    # ------------- wiring -------------

    def _wire(self) -> None:
        # player -> ui
        self.player.position_changed.connect(self._on_position)
        self.player.frame_changed.connect(self._on_frame)
        self.player.duration_changed.connect(self._on_duration)
        self.player.fps_changed.connect(self._on_fps)
        self.player.play_state_changed.connect(self.transport.set_play_icon)

        # transport -> player
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

        # timeline -> player
        self.timeline.seeked.connect(self.player.seek_frame)
        self.timeline.range_changed.connect(self._on_inout_changed)

        # bookmarks -> annotations -> timeline
        self.annotations.changed.connect(
            lambda _f: self.timeline.set_annotated_frames(self.annotations.annotated_frames())
        )
        self.bookmark_panel.bookmark_activated.connect(self._goto_bookmark)
        self.bookmark_panel.delete_requested.connect(self.bookmarks.remove)

        # annotation toolbar -> overlay
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

    def _wire_shortcuts(self) -> None:
        def sc(seq: str, fn) -> None:
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(fn)

        sc("Space", self.player.toggle_play)
        sc("Right", lambda: self.player.step_frame(1))
        sc("Left", lambda: self.player.step_frame(-1))
        sc("Shift+Right", lambda: self.player.step_frame(10))
        sc("Shift+Left", lambda: self.player.step_frame(-10))
        sc("Home", lambda: self.player.seek_frame(0))
        sc("End", lambda: self.player.seek_frame(max(0, self.player.total_frames() - 1)))
        sc("I", self._set_in)
        sc("O", self._set_out)
        sc("Shift+X", self._clear_inout)
        sc("B", self._add_bookmark)
        sc("Shift+B", self._add_range_bookmark)
        sc("M", lambda: self.transport.btn_mute.toggle())
        sc("[", lambda: self._goto_prev_bookmark())
        sc("]", lambda: self._goto_next_bookmark())
        sc("A", lambda: self.ann_toolbar.btn_toggle.toggle())
        sc("Ctrl+Z", lambda: self.annotations.remove_last(self.player.current_frame()))
        sc("Ctrl+Shift+Delete", self.annotations.clear_all)

    # ------------- actions -------------

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", VIDEO_FILTER)
        if not path:
            return
        self.load_video(path)

    def load_video(self, path: str) -> None:
        self._current_file = path
        self.setWindowTitle(f"Keyframe Pro Linux — {Path(path).name}")
        self.player.load_file(path)
        self.lbl_status.setText(f"Loaded: {Path(path).name}")

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
        proj = Project(
            sources=[ProjectSource(path=self._current_file)] if self._current_file else [],
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

    # ------------- in/out / bookmarks -------------

    def _set_in(self) -> None:
        f = self.player.current_frame()
        out = self.timeline.out_frame()
        if f >= out:
            out = min(self.player.total_frames() - 1, f + 1)
        self.timeline.set_in_out(f, out)

    def _set_out(self) -> None:
        f = self.player.current_frame()
        in_f = self.timeline.in_frame()
        if f <= in_f:
            in_f = max(0, f - 1)
        self.timeline.set_in_out(in_f, f)

    def _clear_inout(self) -> None:
        self.timeline.set_in_out(0, max(0, self.player.total_frames() - 1))

    def _on_inout_changed(self, in_f: int, out_f: int) -> None:
        self.lbl_status.setText(f"In: {in_f}  Out: {out_f}  ({out_f - in_f + 1} frames)")

    def _add_bookmark(self) -> None:
        f = self.player.current_frame()
        self.bookmarks.add(Bookmark(frame_in=f))
        self.lbl_status.setText(f"Bookmark @ frame {f}")

    def _add_range_bookmark(self) -> None:
        in_f = self.timeline.in_frame()
        out_f = self.timeline.out_frame()
        self.bookmarks.add(Bookmark(frame_in=in_f, frame_out=out_f, color="#22aaff"))
        self.lbl_status.setText(f"Range bookmark {in_f}–{out_f}")

    def _goto_bookmark(self, bm: Bookmark) -> None:
        self.player.seek_frame(bm.frame_in)

    def _goto_next_bookmark(self) -> None:
        bm = self.bookmarks.next_after(self.player.current_frame())
        if bm:
            self.player.seek_frame(bm.frame_in)

    def _goto_prev_bookmark(self) -> None:
        bm = self.bookmarks.prev_before(self.player.current_frame())
        if bm:
            self.player.seek_frame(bm.frame_in)

    def _on_hold_changed(self, n: int) -> None:
        self.annotations.set_held(self.player.current_frame(), int(n))

    # ------------- player -> UI -------------

    def _on_position(self, _seconds: float) -> None:
        pass

    def _on_frame(self, frame: int) -> None:
        self.timeline.set_current_frame(frame)
        self.overlay.set_frame(frame)
        # Loop range enforcement (in/out)
        in_f = self.timeline.in_frame()
        out_f = self.timeline.out_frame()
        total = self.player.total_frames()
        if total > 0 and out_f < total - 1 and frame > out_f:
            if self.player.loop_mode() in ("loop", "pingpong"):
                self.player.seek_frame(in_f)
            else:
                self.player.pause()
        # Status text
        fps = self.player.fps() or 24.0
        self.lbl_status.setText(
            f"Frame {frame:>5} / {max(0, self.player.total_frames()-1):>5}   "
            f"{frame/fps:6.2f}s   FPS {fps:.2f}"
        )

    def _on_duration(self, _sec: float) -> None:
        QTimer.singleShot(150, self._sync_total)

    def _on_fps(self, fps: float) -> None:
        self.bookmark_panel.set_fps(fps)
        self._sync_total()

    def _sync_total(self) -> None:
        total = self.player.total_frames()
        if total > 0:
            self.timeline.set_total_frames(total)
            self.timeline.set_in_out(0, total - 1)

    # ------------- view -------------

    def _toggle_on_top(self, on: bool) -> None:
        flags = self.windowFlags()
        if on:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ------------- overlay sizing -------------

    def eventFilter(self, obj, ev):
        if obj is self.player and ev.type() in (ev.Type.Resize, ev.Type.Show):
            self.overlay.setGeometry(self.player.geometry())
            self.overlay.raise_()
        return super().eventFilter(obj, ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.overlay.setGeometry(self.player.geometry())
        self.overlay.raise_()

    def closeEvent(self, ev):
        self.player.shutdown()
        super().closeEvent(ev)
