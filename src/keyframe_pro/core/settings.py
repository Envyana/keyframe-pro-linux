"""User settings + customizable hotkeys persisted via QSettings."""
from __future__ import annotations

import json
from pathlib import Path
from PySide6.QtCore import QSettings


# Action ID → (default key sequence, human label)
DEFAULT_HOTKEYS: dict[str, tuple[str, str]] = {
    "play_toggle":      ("Space",          "Play / Pause"),
    "step_back_1":      ("Left",           "Previous frame"),
    "step_fwd_1":       ("Right",          "Next frame"),
    "step_back_10":     ("Shift+Left",     "Back 10 frames"),
    "step_fwd_10":      ("Shift+Right",    "Forward 10 frames"),
    "goto_start":       ("Home",           "Go to start"),
    "goto_end":         ("End",            "Go to end"),
    "set_in":           ("I",              "Set In"),
    "set_out":          ("O",              "Set Out"),
    "clear_inout":      ("Shift+X",        "Clear In/Out"),
    "add_bookmark":     ("B",              "Add bookmark"),
    "add_range_bm":     ("Shift+B",        "Add range bookmark"),
    "prev_bookmark":    ("[",              "Previous bookmark"),
    "next_bookmark":    ("]",              "Next bookmark"),
    "annotate_toggle":  ("A",              "Toggle annotate mode"),
    "undo_stroke":      ("Ctrl+Z",         "Undo last stroke"),
    "clear_all_ann":    ("Ctrl+Shift+Delete", "Clear all annotations"),
    "mute_toggle":      ("M",              "Mute"),
    "fullscreen":       ("F",              "Fullscreen"),
    "always_on_top":    ("T",              "Always on top"),
    "compare_a":        ("1",              "View A only"),
    "compare_b":        ("2",              "View B only"),
    "compare_wipe":     ("3",              "Wipe compare"),
    "compare_split_v":  ("4",              "Split vertical"),
    "compare_split_h":  ("5",              "Split horizontal"),
    "compare_grid":     ("6",              "Grid 2×2 compare"),
    "compare_flicker":  ("7",              "Flicker compare"),
    "screenshot":       ("S",              "Save screenshot of current frame"),
    "reset_view":       ("Shift+R",        "Reset pan/zoom"),
    "scrub_audio_toggle": ("Shift+A",      "Toggle audio scrub"),
    "zoom_in":          ("+",              "Zoom in"),
    "zoom_out":         ("-",              "Zoom out"),
    "hud_toggle":       ("H",              "Toggle frame/time HUD"),
    "sync_ann_bm":      ("Ctrl+Shift+B",   "Sync annotation bookmarks"),
    "timeline_view":    ("\\",             "Toggle global/range timeline view"),
}


class Settings:
    """Thin wrapper around QSettings for hotkeys + misc preferences."""

    ORG = "KeyframeProLinux"
    APP = "Keyframe Pro Linux"

    def __init__(self) -> None:
        self._s = QSettings(self.ORG, self.APP)

    def hotkey(self, action_id: str) -> str:
        default = DEFAULT_HOTKEYS.get(action_id, ("", ""))[0]
        return str(self._s.value(f"hotkeys/{action_id}", default))

    def set_hotkey(self, action_id: str, sequence: str) -> None:
        self._s.setValue(f"hotkeys/{action_id}", sequence)

    def reset_hotkeys(self) -> None:
        self._s.remove("hotkeys")

    def all_hotkeys(self) -> dict[str, str]:
        return {a: self.hotkey(a) for a in DEFAULT_HOTKEYS}

    # --- recent files ---

    MAX_RECENT = 12

    def recent_files(self) -> list[str]:
        raw = self._s.value("recent_files", []) or []
        # QSettings can return a string for a 1-element list; normalize.
        if isinstance(raw, str):
            raw = [raw]
        return [str(p) for p in raw if p]

    def add_recent_file(self, path: str) -> None:
        path = str(path)
        items = [p for p in self.recent_files() if p != path]
        items.insert(0, path)
        items = items[: self.MAX_RECENT]
        self._s.setValue("recent_files", items)

    def clear_recent_files(self) -> None:
        self._s.setValue("recent_files", [])

    # --- generic ---

    def value(self, key: str, default=None):
        return self._s.value(key, default)

    def set_value(self, key: str, value) -> None:
        self._s.setValue(key, value)

    # --- preset import/export ---

    PRESET_VERSION = 1

    def export_preset(self, path: str | Path, include_recent: bool = False) -> None:
        data = {
            "version": self.PRESET_VERSION,
            "hotkeys": self.all_hotkeys(),
        }
        if include_recent:
            data["recent_files"] = self.recent_files()
        Path(path).write_text(json.dumps(data, indent=2))

    def import_preset(self, path: str | Path) -> dict:
        """Import a preset file. Returns a summary dict.

        Unknown action IDs in the file are ignored. Missing IDs keep their
        current binding. Recent files are imported only if present in the file.
        """
        raw = json.loads(Path(path).read_text())
        if not isinstance(raw, dict):
            raise ValueError("Preset file is not a JSON object")
        if int(raw.get("version", 0)) != self.PRESET_VERSION:
            raise ValueError(
                f"Unsupported preset version (file={raw.get('version')}, "
                f"expected={self.PRESET_VERSION})"
            )
        applied = 0
        skipped = 0
        for action_id, seq in (raw.get("hotkeys") or {}).items():
            if action_id in DEFAULT_HOTKEYS:
                self.set_hotkey(action_id, str(seq))
                applied += 1
            else:
                skipped += 1
        if "recent_files" in raw and isinstance(raw["recent_files"], list):
            self._s.setValue("recent_files", [str(p) for p in raw["recent_files"]])
        return {"applied": applied, "skipped": skipped}
