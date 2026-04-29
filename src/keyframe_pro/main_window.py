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
from .widgets.clip_editor import ClipEditor
from .widgets.bookmark_editor import BookmarkEditor
from .widgets.hud_overlay import HudOverlay
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
        self.setAcceptDrops(True)

        # ---------- models ----------
        self.bookmarks = BookmarkModel()
        self.annotations = AnnotationModel()
        self.timeline_model = Timeline()
        self.settings = Settings()

        # ---------- players (A primary; B/C/D for compare) ----------
        self.player = MpvPlayer()
        self.player_b = MpvPlayer()
        self.player_c = MpvPlayer()
        self.player_d = MpvPlayer()

        # Compare view hosts all 4 players
        self.compare_view = CompareView(
            self.player, self.player_b, self.player_c, self.player_d
        )

        # Annotation + HUD overlays sit on top of compare_view
        self.viewer_container = QWidget()
        viewer_stack = QStackedLayout(self.viewer_container)
        viewer_stack.setStackingMode(QStackedLayout.StackAll)
        viewer_stack.setContentsMargins(0, 0, 0, 0)
        self.hud = HudOverlay(parent=self.viewer_container)
        self.overlay = AnnotationOverlay(self.annotations, parent=self.viewer_container)
        viewer_stack.addWidget(self.hud)
        viewer_stack.addWidget(self.overlay)
        viewer_stack.addWidget(self.compare_view)
        self.overlay.raise_()
        self.hud.raise_()
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
        for p in (self.player_b, self.player_c, self.player_d):
            p.set_volume(0.0)
            p.set_mute(True)
        self._sync_b: bool = True
        self._hud_visible: bool = False

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

        a_open = QAction("&Open Video...", self, shortcut=QKeySequence.Open)
        a_open.triggered.connect(self.open_file)
        m_file.addAction(a_open)

        a_add = QAction("&Add Source to Timeline...", self,
                        shortcut=QKeySequence("Ctrl+Shift+O"))
        a_add.triggered.connect(self.add_source)
        m_file.addAction(a_add)

        # Recent files submenu
        self.menu_recent = m_file.addMenu("Open &Recent")
        self._refresh_recent_menu()

        m_file.addSeparator()
        a_proj_open = QAction("Open &Project...", self)
        a_proj_open.triggered.connect(self.open_project)
        m_file.addAction(a_proj_open)
        a_proj_save = QAction("&Save Project", self, shortcut=QKeySequence.Save)
        a_proj_save.triggered.connect(self.save_project)
        m_file.addAction(a_proj_save)
        a_proj_save_as = QAction("Save Project &As...", self,
                                 shortcut=QKeySequence("Ctrl+Shift+S"))
        a_proj_save_as.triggered.connect(self.save_project_as)
        m_file.addAction(a_proj_save_as)

        m_file.addSeparator()
        a_screenshot = QAction("Save Screenshot...", self,
                               shortcut=QKeySequence("Ctrl+S"))
        a_screenshot.triggered.connect(self.save_screenshot)
        m_file.addAction(a_screenshot)
        a_export = QAction("&Export Timeline…", self,
                           shortcut=QKeySequence("Ctrl+E"))
        a_export.triggered.connect(self.export_timeline)
        m_file.addAction(a_export)

        m_file.addSeparator()
        a_quit = QAction("&Quit", self, shortcut=QKeySequence.Quit)
        a_quit.triggered.connect(self.close)
        m_file.addAction(a_quit)

        m_view = self.menuBar().addMenu("&View")
        a_top = QAction("Always on &Top", self, checkable=True)
        a_top.toggled.connect(self._toggle_on_top)
        m_view.addAction(a_top)
        a_full = QAction("&Fullscreen", self)
        a_full.triggered.connect(self._toggle_fullscreen)
        m_view.addAction(a_full)

        a_hud = QAction("&HUD (frame/time)", self, checkable=True)
        a_hud.toggled.connect(self._toggle_hud)
        m_view.addAction(a_hud)
        self._action_hud = a_hud

        m_hud_pos = m_view.addMenu("HUD position")
        for label, key in [
            ("Top-Left", "top_left"),
            ("Top-Right", "top_right"),
            ("Bottom-Left", "bottom_left"),
            ("Bottom-Right", "bottom_right"),
        ]:
            ap = QAction(label, self)
            ap.triggered.connect(lambda _checked=False, k=key: self.hud.set_position(k))
            m_hud_pos.addAction(ap)

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
        self.transport.scrub_audio_toggled.connect(self.player.set_scrub_audio)
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
        self.bookmark_panel.edit_requested.connect(self._edit_bookmark)
        self.bookmark_panel.sync_annotations_requested.connect(self._sync_annotation_bookmarks)

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
        self.compare_toolbar.load_c_requested.connect(self._load_c)
        self.compare_toolbar.load_d_requested.connect(self._load_d)
        self.compare_toolbar.flicker_interval_changed.connect(
            self.compare_view.set_flicker_interval
        )

        # mouse-scrub from player A → main timeline syncs naturally via frame_changed,
        # but we also want B to follow when sync is on
        self.player.mouse_scrubbed.connect(self._on_mouse_scrub)

        # source panel
        self.source_panel.activate_requested.connect(self._activate_source)
        self.source_panel.add_files_requested.connect(self._add_sources)
        self.source_panel.edit_requested.connect(self._edit_clip)
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
            "compare_grid": lambda: self._set_compare_mode(CompareMode.GRID_2X2),
            "compare_flicker": lambda: self._set_compare_mode(CompareMode.FLICKER),
            "screenshot": self.save_screenshot,
            "reset_view": self.player.reset_view,
            "scrub_audio_toggle": self._toggle_scrub_audio,
            "zoom_in": lambda: self.player.set_zoom(self.player.zoom() + 0.125),
            "zoom_out": lambda: self.player.set_zoom(self.player.zoom() - 0.125),
            "hud_toggle": self._toggle_hud,
            "sync_ann_bm": self._sync_annotation_bookmarks,
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
        self.settings.add_recent_file(path)
        self._refresh_recent_menu()
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
        self.player.load_file(clip.media_path, audio_override=clip.audio_override)
        if self._sync_b:
            self.player_b.load_file(clip.media_path)

    def _on_timeline_changed(self) -> None:
        # Update status with timeline length
        n = self.timeline_model.count()
        self.lbl_status.setText(f"Timeline: {n} source(s)")

    # ---- compare ----

    def _load_b(self, path: str) -> None:
        self.player_b.load_file(path)
        self.lbl_status.setText(f"B = {Path(path).name}")

    def _load_c(self, path: str) -> None:
        self.player_c.load_file(path)
        self.lbl_status.setText(f"C = {Path(path).name}")

    def _load_d(self, path: str) -> None:
        self.player_d.load_file(path)
        self.lbl_status.setText(f"D = {Path(path).name}")

    def _on_mouse_scrub(self, frame: int) -> None:
        if self._sync_b:
            self.player_b.seek_frame(frame)
            self.player_c.seek_frame(frame)
            self.player_d.seek_frame(frame)
        # Also reflect in the timeline widget
        self.timeline_widget.set_current_frame(frame)
        self.overlay.set_frame(frame)

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
        # Use scrub variant — produces an audio blip when scrub-audio is on.
        self.player.scrub_to_frame(frame)
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
        if self._sync_b:
            for p in (self.player_b, self.player_c, self.player_d):
                if abs(p.current_frame() - frame) > 1:
                    p.seek_frame(frame)

        in_f = self.timeline_widget.in_frame()
        out_f = self.timeline_widget.out_frame()
        total = self.player.total_frames()
        if total > 0 and out_f < total - 1 and frame > out_f:
            if self.player.loop_mode() in ("loop", "pingpong"):
                self.player.seek_frame(in_f)
            else:
                self.player.pause()
        fps = self.player.fps() or 24.0
        # HUD update
        self.hud.set_state(frame, self.player.total_frames(), fps,
                           frame / fps if fps > 0 else 0.0)
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

    def _toggle_hud(self, on: bool | None = None) -> None:
        if on is None:
            on = not self._hud_visible
            self._action_hud.setChecked(on)
        self._hud_visible = bool(on)
        self.hud.set_visible(self._hud_visible)
        self.hud.setGeometry(self.compare_view.geometry())
        self.hud.raise_()

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
    # recent files
    # =========================================================
    def _refresh_recent_menu(self) -> None:
        if not hasattr(self, "menu_recent"):
            return
        self.menu_recent.clear()
        items = self.settings.recent_files()
        if not items:
            empty = QAction("(empty)", self)
            empty.setEnabled(False)
            self.menu_recent.addAction(empty)
            return
        for p in items:
            name = Path(p).name
            a = QAction(f"{name}    [{p}]", self)
            a.triggered.connect(lambda _checked=False, path=p: self._open_recent(path))
            self.menu_recent.addAction(a)
        self.menu_recent.addSeparator()
        a_clear = QAction("Clear Recent", self)
        a_clear.triggered.connect(lambda: (self.settings.clear_recent_files(),
                                           self._refresh_recent_menu()))
        self.menu_recent.addAction(a_clear)

    def _open_recent(self, path: str) -> None:
        if not Path(path).exists():
            QMessageBox.warning(self, "File missing",
                                f"File no longer exists:\n{path}")
            return
        self.load_video(path)

    # =========================================================
    # screenshot
    # =========================================================
    def save_screenshot(self) -> None:
        if not self._current_file:
            self.lbl_status.setText("No video loaded")
            return
        from datetime import datetime
        out_dir = Path.home() / "Pictures" / "keyframe-pro"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(self._current_file).stem
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        f = self.player.current_frame()
        path = out_dir / f"{stem}_f{f:06d}_{ts}.png"
        ok = self.player.screenshot(str(path))
        if ok:
            self.lbl_status.setText(f"Saved: {path}")
        else:
            QMessageBox.warning(self, "Screenshot failed",
                                "mpv could not write the screenshot.")

    # =========================================================
    # scrub audio
    # =========================================================
    def _toggle_scrub_audio(self) -> None:
        # Toggle the button so its state stays in sync with the player.
        self.transport.btn_scrub_audio.toggle()
        self.lbl_status.setText(
            f"Scrub audio: {'ON' if self.transport.btn_scrub_audio.isChecked() else 'OFF'}"
        )

    # =========================================================
    # drag and drop
    # =========================================================
    VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v",
                  ".mpg", ".mpeg", ".wmv", ".flv", ".ogv", ".gif"}

    def dragEnterEvent(self, ev) -> None:
        md = ev.mimeData()
        if md.hasUrls() and any(u.isLocalFile() for u in md.urls()):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev) -> None:
        ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        paths = []
        for u in ev.mimeData().urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                if Path(p).suffix.lower() in self.VIDEO_EXTS:
                    paths.append(p)
        if not paths:
            return
        if len(paths) == 1:
            self.load_video(paths[0])
        else:
            self._add_sources(paths)
        ev.acceptProposedAction()

    # =========================================================
    # clip editor
    # =========================================================
    def _edit_bookmark(self, index: int) -> None:
        items = self.bookmarks.all()
        if not (0 <= index < len(items)):
            return
        dlg = BookmarkEditor(items[index], self)
        if dlg.exec():
            self.bookmarks.update_at(index, dlg.result())

    def _sync_annotation_bookmarks(self) -> None:
        added = self.bookmarks.sync_from_annotations(
            self.annotations.annotated_frames()
        )
        self.lbl_status.setText(
            f"Synced annotation bookmarks (+{added})" if added > 0
            else "Annotation bookmarks already in sync"
        )

    def _edit_clip(self, index: int) -> None:
        clip = self.timeline_model.get(index)
        if clip is None:
            return
        dlg = ClipEditor(clip, self)
        if dlg.exec():
            new_clip = dlg.result_clip()
            old_audio = clip.audio_override
            self.timeline_model.replace(index, new_clip)
            # If audio override changed and this clip is currently loaded, reload
            # so the new audio track takes effect.
            if (new_clip.audio_override != old_audio
                    and self._current_file == new_clip.media_path):
                self.player.load_file(new_clip.media_path,
                                      audio_override=new_clip.audio_override)
            self.lbl_status.setText(f"Updated: {new_clip.label}")

    # =========================================================
    # overlay sizing / cleanup
    # =========================================================
    def eventFilter(self, obj, ev):
        if obj is self.compare_view and ev.type() in (ev.Type.Resize, ev.Type.Show):
            self.overlay.setGeometry(self.compare_view.geometry())
            self.hud.setGeometry(self.compare_view.geometry())
            self.overlay.raise_()
            self.hud.raise_()
        return super().eventFilter(obj, ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.overlay.setGeometry(self.compare_view.geometry())
        self.hud.setGeometry(self.compare_view.geometry())
        self.overlay.raise_()
        self.hud.raise_()

    def closeEvent(self, ev):
        try:
            self.api.stop()
        except Exception:
            pass
        try:
            for p in (self.player, self.player_b, self.player_c, self.player_d):
                p.shutdown()
        except Exception:
            pass
        super().closeEvent(ev)
