"""GlobalFeelPanel — song-wide ``Song.feel`` knob row.

Shared by :class:`~jtx_gui.views.song_view.SongView` (legacy Patcher
song pane) and :class:`~jtx_gui.views.composer_view.ComposerView`.

Each of the 5 global feel knobs (``pump``, ``groove``, ``drive``,
``tension``, ``wander``) is bound to ``song.feel[name]``; editing
fires the parent's ``on_dirty`` callback.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from jtx.model import Song
from jtx_gui.algorithm_meta import GLOBAL_FEEL_KNOBS
from jtx_gui.widgets.collapsible import CollapsibleSection
from jtx_gui.widgets.knob import KnobWidget


class GlobalFeelPanel(QFrame):
    """Renders the 5 song-wide feel knobs and writes back to ``song.feel``."""

    def __init__(
        self,
        *,
        song: Song,
        on_dirty: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._song = song
        self._on_dirty = on_dirty

        self._section = CollapsibleSection("GLOBAL FEEL", expanded=True, parent=self)

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        for spec in GLOBAL_FEEL_KNOBS:
            default = float(spec.default) if isinstance(spec.default, (int, float)) else 0.0
            current = float(song.feel.get(spec.name, default))
            knob = KnobWidget(
                label=spec.name,
                minimum=float(spec.minimum),
                maximum=float(spec.maximum),
                value=current,
                step=float(spec.step),
                decimals=spec.decimals,
            )
            if spec.description:
                knob.setToolTip(f"{spec.name}: {spec.description}")
            knob.value_changed.connect(
                lambda v, name=spec.name: self._on_value(name, v),
            )
            row_layout.addWidget(knob)
        row_layout.addStretch(1)

        self._section.add_widget(row_widget)
        self._section.set_header_hint(f"{len(GLOBAL_FEEL_KNOBS)} knobs")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section)

    def _on_value(self, name: str, value: float) -> None:
        self._song.feel[name] = float(value)
        self._on_dirty()


__all__ = ["GlobalFeelPanel"]
