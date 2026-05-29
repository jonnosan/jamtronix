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

from jtx.model import Setup, Song, ValidationError
from jtx.persist import load_setup, load_song, save_song


class AppState(QObject):
    """Currently-loaded song + edit metadata."""

    song_changed = Signal()
    """Emitted whenever the song's structure or any field has been mutated."""

    dirty_changed = Signal(bool)
    path_changed = Signal(object)  # Path | None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._song: Song | None = None
        self._setup: Setup | None = None
        self._setup_error: str | None = None
        self._path: Path | None = None
        self._dirty = False

    # ----- accessors -------------------------------------------------------

    @property
    def song(self) -> Song | None:
        return self._song

    @property
    def setup(self) -> Setup | None:
        return self._setup

    @property
    def setup_error(self) -> str | None:
        """Reason the sibling .jtx-setup couldn't load, if any."""
        return self._setup_error

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
        self._load_sibling_setup()
        self.song_changed.emit()
        self.path_changed.emit(self._path)
        self.dirty_changed.emit(False)

    def replace_song_in_place(self, song: Song) -> None:
        """Swap the song without marking dirty or changing the path.

        Intended for settings-driven re-rolls (mood/sonics/chaos slider
        moves on the Composer view) where the user hasn't manually
        edited anything — the rolled song replaces the previous roll
        and views just rebuild from the new structure.
        """
        self._song = song
        self.song_changed.emit()

    def adopt(self, *, song: Song, setup: Setup | None) -> None:
        """Take ownership of a fresh in-memory song (e.g. from the wizard).

        Sets the state to ``dirty=True`` and ``path=None`` so File → Save
        falls through to Save As. The caller supplies the setup that was
        chosen at song-creation time; sibling-loading is bypassed since
        there's nothing on disk yet.
        """
        self._song = song
        self._setup = setup
        self._setup_error = None if setup is not None else "No setup attached to new song."
        self._path = None
        self._dirty = True
        self.song_changed.emit()
        self.path_changed.emit(None)
        self.dirty_changed.emit(True)

    def _load_sibling_setup(self) -> None:
        """Look for ``<song_dir>/<setup_ref>.jtx-setup`` next to the song.

        On miss or validation error, ``setup`` stays ``None`` and
        ``setup_error`` describes the problem. The Song view doesn't
        need the setup; the Live view does and surfaces this state.
        """
        self._setup = None
        self._setup_error = None
        if self._song is None or self._path is None:
            return
        candidate = self._path.parent / f"{self._song.setup_ref}.jtx-setup"
        if not candidate.exists():
            self._setup_error = (
                f"Setup file {candidate.name!r} not found next to song. "
                "Live playback needs a sibling .jtx-setup."
            )
            return
        try:
            self._setup = load_setup(candidate)
        except (ValidationError, OSError, ValueError) as exc:
            self._setup_error = f"Failed to load {candidate.name}: {exc}"

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
        """Call from views after a non-structural edit (e.g. a knob change).

        Only flips the dirty flag; does *not* emit ``song_changed`` so
        view widgets don't rebuild themselves (which would collapse
        whichever panel the user is editing). For structural changes
        — add/rename/remove a part, swap a voice — use
        :meth:`notify_structural_change` instead.
        """
        self._set_dirty(True)

    def notify_structural_change(self) -> None:
        """Call after add/rename/remove of parts, voices, etc.

        Marks the song dirty *and* triggers view rebuilds via
        ``song_changed``.
        """
        self._set_dirty(True)
        self.song_changed.emit()

    def _set_dirty(self, value: bool) -> None:
        if value != self._dirty:
            self._dirty = value
            self.dirty_changed.emit(value)
