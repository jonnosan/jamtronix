"""AppState — the in-memory model the GUI edits.

Wraps the loaded :class:`jtx.model.Song` plus its on-disk path and a
'dirty' flag. Emits Qt signals when fields change so views stay in sync
without owning the song directly. This is intentionally chunky: a single
``song_changed`` covers most structural edits, while ``dirty_changed``
and ``path_changed`` exist for the title bar.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from jtx.model import Song
from jtx.persist import load_song, save_song


class AppState(QObject):
    """Currently-loaded song + edit metadata."""

    song_changed = Signal()
    """Emitted whenever the song's structure or any field has been mutated."""

    dirty_changed = Signal(bool)
    path_changed = Signal(object)  # Path | None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._song: Song | None = None
        self._path: Path | None = None
        self._dirty = False

    # ----- accessors -------------------------------------------------------

    @property
    def song(self) -> Song | None:
        return self._song

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def dirty(self) -> bool:
        return self._dirty

    def display_title(self) -> str:
        if self._song is None:
            return "Jamtronix"
        stem = self._path.name if self._path else f"{self._song.title} (unsaved)"
        marker = " •" if self._dirty else ""
        return f"Jamtronix — {stem}{marker}"

    # ----- file I/O --------------------------------------------------------

    def open(self, path: Path | str) -> None:
        p = Path(path)
        song = load_song(p)
        self._song = song
        self._path = p
        self._dirty = False
        self.song_changed.emit()
        self.path_changed.emit(self._path)
        self.dirty_changed.emit(False)

    def save(self) -> None:
        if self._song is None or self._path is None:
            raise RuntimeError("save() requires both a loaded song and a known path")
        save_song(self._song, self._path)
        self._set_dirty(False)

    def save_as(self, path: Path | str) -> None:
        if self._song is None:
            raise RuntimeError("save_as() requires a loaded song")
        p = Path(path)
        save_song(self._song, p)
        self._path = p
        self.path_changed.emit(self._path)
        self._set_dirty(False)

    # ----- edit signalling -------------------------------------------------

    def mark_dirty(self) -> None:
        """Call from views after a successful edit to the song."""
        self._set_dirty(True)
        self.song_changed.emit()

    def _set_dirty(self, value: bool) -> None:
        if value != self._dirty:
            self._dirty = value
            self.dirty_changed.emit(value)
