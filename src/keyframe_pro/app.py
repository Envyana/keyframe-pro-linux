from __future__ import annotations

import sys
import os
import argparse
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


DARK_QSS = """
QMainWindow, QWidget { background-color: #1b1b1f; color: #e6e6e6; }
QMenuBar { background-color: #232328; color: #e6e6e6; }
QMenuBar::item:selected { background-color: #3a3a44; }
QMenu { background-color: #232328; color: #e6e6e6; border: 1px solid #3a3a44; }
QMenu::item:selected { background-color: #4a90e2; }
QPushButton {
    background-color: #2c2c33; color: #e6e6e6;
    border: 1px solid #3a3a44; border-radius: 3px;
    padding: 2px 8px;
}
QPushButton:hover { background-color: #3a3a44; }
QPushButton:checked { background-color: #4a90e2; border-color: #4a90e2; }
QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #2c2c33; color: #e6e6e6;
    border: 1px solid #3a3a44; border-radius: 3px;
    padding: 2px 4px;
}
QListWidget {
    background-color: #232328; color: #e6e6e6;
    border: 1px solid #3a3a44;
}
QListWidget::item:selected { background-color: #4a90e2; }
QLabel { color: #cfcfcf; }
QStatusBar { background-color: #232328; color: #cfcfcf; }
QDockWidget::title { background-color: #232328; padding: 4px; }
QSlider::groove:horizontal {
    height: 6px; background: #2c2c33; border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #4a90e2; width: 12px; margin: -4px 0; border-radius: 6px;
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(prog="keyframe-pro")
    parser.add_argument("file", nargs="?", help="Video file to open")
    parser.add_argument("--project", help="Project file to load (.kproj)")
    args = parser.parse_args()

    # Important on some Linux compositors so libmpv's GPU output works
    # with a Qt-owned native window.
    os.environ.setdefault("QT_X11_NO_MITSHM", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("Keyframe Pro Linux")
    app.setOrganizationName("KeyframeProLinux")
    app.setStyleSheet(DARK_QSS)

    win = MainWindow()
    win.show()

    if args.project:
        try:
            from .core.project import Project
            proj = Project.load(args.project)
            win.bookmarks.load(proj.bookmarks)
            win.annotations.load(proj.annotations)
            if proj.sources:
                win.load_video(proj.sources[0].path)
        except Exception as e:
            print(f"Failed to load project: {e}", file=sys.stderr)
    elif args.file:
        win.load_video(args.file)

    return app.exec()
