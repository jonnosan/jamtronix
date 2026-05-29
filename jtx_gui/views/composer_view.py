"""ComposerView — mood pad + format/title + Generate.

The Composer view is the front door for new songs after the mood +
format composer rework (epic #118). It hosts the
:class:`~jtx_gui.widgets.mood_pad.MoodPadWidget`, an anchor button
row for quick mood snaps, a chaos knob, a format combo, a title
input with a 'Random title' shortcut, a setup picker (bundled
``.jtx-setup`` files), a 'Random song' shortcut, and a 'Generate'
button that calls :func:`jtx.composer.compose` and hands the
resulting :class:`~jtx.model.Song` to :class:`AppState.adopt`.

If a song is already loaded into :class:`AppState`, the view reflects
its mood / format / title / setup_ref so the user can see what the
last generate produced and re-roll from the same starting point.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from jtx.composer import (
    FORMAT_SPECS,
    MOOD_ANCHORS,
    FormatType,
    compose,
    random_title,
)
from jtx.composer.mood import MoodSpec
from jtx.model import Setup, ValidationError
from jtx.persist import load_setup
from jtx_gui import theme
from jtx_gui.bundles import bundled_setups
from jtx_gui.state import AppState
from jtx_gui.widgets.arrangement_timeline import ArrangementTimeline
from jtx_gui.widgets.global_feel_panel import GlobalFeelPanel
from jtx_gui.widgets.knob import KnobWidget
from jtx_gui.widgets.mood_pad import MoodPadWidget
from jtx_gui.widgets.part_editor_panel import PartEditorPanel


class ComposerView(QWidget):
    """Front-door view for generating a new song from a mood + format."""

    def __init__(
        self,
        state: AppState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._state.song_changed.connect(self._sync_from_state)
        self._setup_paths: dict[str, Path] = {}

        # ----- left column: mood pad + anchor row ----------------------------
        self._mood_pad = MoodPadWidget(self)
        self._mood_pad.mood_changed.connect(self._on_mood_changed)

        anchor_row = QHBoxLayout()
        anchor_row.setSpacing(4)
        self._anchor_buttons: list[QPushButton] = []
        for name in MOOD_ANCHORS:
            btn = QPushButton(name.upper(), self)
            btn.setCheckable(False)
            btn.clicked.connect(lambda _ch=False, n=name: self._on_anchor_clicked(n))
            anchor_row.addWidget(btn)
            self._anchor_buttons.append(btn)

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self._mood_pad, 1)
        left.addLayout(anchor_row)

        # ----- right column: parameters + actions ---------------------------
        self._title = QLineEdit(self)
        self._title.setPlaceholderText("e.g. Phuture Lines")
        random_title_btn = QPushButton("RANDOM TITLE", self)
        random_title_btn.clicked.connect(self._on_random_title_clicked)
        title_row = QHBoxLayout()
        title_row.addWidget(self._title, 1)
        title_row.addWidget(random_title_btn)

        self._chaos = KnobWidget(
            label="chaos",
            minimum=0.0,
            maximum=1.0,
            value=0.0,
            step=0.05,
            decimals=2,
            parent=self,
        )

        self._format_combo = QComboBox(self)
        for fmt in FORMAT_SPECS:
            self._format_combo.addItem(fmt.upper(), fmt)
        default_idx = self._format_combo.findData("song")
        if default_idx >= 0:
            self._format_combo.setCurrentIndex(default_idx)

        self._setup_combo = QComboBox(self)
        for path in bundled_setups():
            self._setup_combo.addItem(path.stem, path)
            self._setup_paths[path.stem] = path

        random_song_btn = QPushButton("RANDOM SONG", self)
        random_song_btn.clicked.connect(self._on_random_song_clicked)
        generate_btn = QPushButton("GENERATE", self)
        generate_btn.setDefault(True)
        generate_btn.setMinimumHeight(40)
        generate_btn.clicked.connect(self._on_generate_clicked)

        # Headline.
        heading = QLabel("COMPOSER")
        heading.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-size: 18pt; font-weight: bold; "
            "letter-spacing: 6px; padding-bottom: 8px;"
        )

        form = QFormLayout()
        form.setSpacing(8)
        form.addRow("TITLE", title_row)
        form.addRow("FORMAT", self._format_combo)
        form.addRow("SETUP", self._setup_combo)
        form.addRow("CHAOS", self._chaos)

        actions = QGridLayout()
        actions.addWidget(random_song_btn, 0, 0)
        actions.addWidget(generate_btn, 0, 1)

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(heading)
        right.addLayout(form)
        right.addStretch(1)
        right.addLayout(actions)

        # Top row — mood pad on the left, composer params on the right.
        top_row = QHBoxLayout()
        top_row.setSpacing(16)
        top_row.addLayout(left, 1)
        top_row.addLayout(right, 0)
        top_widget = QWidget(self)
        top_widget.setLayout(top_row)

        # Lower section — global feel + arrangement timeline + part editor.
        # Built lazily on song_changed; the container starts hidden.
        self._global_feel_holder = QVBoxLayout()
        self._global_feel_holder.setContentsMargins(0, 0, 0, 0)
        self._global_feel_panel: GlobalFeelPanel | None = None

        self._timeline = ArrangementTimeline(self)
        self._timeline.part_selected.connect(self._on_part_selected)

        self._part_editor = PartEditorPanel(self)

        song_panels = QWidget(self)
        song_panels_layout = QVBoxLayout(song_panels)
        song_panels_layout.setContentsMargins(0, 0, 0, 0)
        song_panels_layout.setSpacing(10)
        song_panels_layout.addLayout(self._global_feel_holder)
        song_panels_layout.addWidget(self._timeline)
        song_panels_layout.addWidget(self._part_editor)
        song_panels_layout.addStretch(1)

        self._song_panels_scroll = QScrollArea(self)
        self._song_panels_scroll.setWidgetResizable(True)
        self._song_panels_scroll.setWidget(song_panels)
        self._song_panels_scroll.setVisible(False)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(top_widget)
        splitter.addWidget(self._song_panels_scroll)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        body = QVBoxLayout(self)
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(12)
        body.addWidget(splitter, 1)

        # If the state already holds a song (e.g. opened from CLI), sync once.
        self._sync_from_state()

    # ----- public helpers --------------------------------------------------

    def current_mood(self) -> MoodSpec:
        v, e = self._mood_pad.mood()
        return MoodSpec(valence=v, energy=e, chaos=self._chaos.value())

    def current_format(self) -> FormatType:
        return cast("FormatType", self._format_combo.currentData())

    # ----- state sync ------------------------------------------------------

    def _sync_from_state(self) -> None:
        song = self._state.song
        if song is None:
            self._song_panels_scroll.setVisible(False)
            self._clear_global_feel_panel()
            self._timeline.set_song(None)
            self._part_editor.clear()
            return
        # Reflect the loaded song's mood / format / title in the controls.
        self._title.setText(song.title)
        self._mood_pad.set_mood(song.mood.valence, song.mood.energy, emit=False)
        self._chaos.set_value(song.mood.chaos, emit=False)
        idx = self._format_combo.findData(song.format)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)
        setup_idx = self._setup_combo.findText(song.setup_ref)
        if setup_idx >= 0:
            self._setup_combo.setCurrentIndex(setup_idx)

        # Rebuild the song-level panels for the new song.
        self._clear_global_feel_panel()
        self._global_feel_panel = GlobalFeelPanel(
            song=song, on_dirty=self._state.mark_dirty,
        )
        self._global_feel_holder.addWidget(self._global_feel_panel)

        self._timeline.set_song(song)
        first_part = next(iter(song.parts), None)
        if first_part is not None:
            self._timeline.set_selected_part(first_part)
            self._part_editor.set_part(
                song=song,
                part_name=first_part,
                on_dirty=self._state.mark_dirty,
            )
        else:
            self._part_editor.clear()

        self._song_panels_scroll.setVisible(True)

    def _clear_global_feel_panel(self) -> None:
        if self._global_feel_panel is not None:
            self._global_feel_panel.setParent(None)
            self._global_feel_panel.deleteLater()
            self._global_feel_panel = None

    def _on_part_selected(self, part_name: str) -> None:
        song = self._state.song
        if song is None or part_name not in song.parts:
            return
        self._part_editor.set_part(
            song=song,
            part_name=part_name,
            on_dirty=self._state.mark_dirty,
        )

    # ----- callbacks -------------------------------------------------------

    def _on_mood_changed(self, _v: float, _e: float) -> None:
        # The mood is read off the pad at generate time; no immediate
        # state mutation here (mood is a one-shot per epic).
        pass

    def _on_anchor_clicked(self, anchor_name: str) -> None:
        spec = MOOD_ANCHORS[anchor_name]
        self._mood_pad.set_mood(spec.valence, spec.energy)

    def _on_random_title_clicked(self) -> None:
        mood = self.current_mood()
        title = random_title(mood, self.current_format())
        self._title.setText(title)

    def _on_random_song_clicked(self) -> None:
        anchor_name = random.choice(list(MOOD_ANCHORS.keys()))
        anchor = MOOD_ANCHORS[anchor_name]
        self._mood_pad.set_mood(anchor.valence, anchor.energy)

        formats = list(FORMAT_SPECS.keys())
        fmt = random.choice(formats)
        fmt_idx = self._format_combo.findData(fmt)
        if fmt_idx >= 0:
            self._format_combo.setCurrentIndex(fmt_idx)

        chaos = round(random.uniform(0.0, 0.7), 3)
        self._chaos.set_value(chaos, emit=False)

        self._title.setText(random_title(self.current_mood(), fmt))
        self._on_generate_clicked()

    def _on_generate_clicked(self) -> None:
        title = self._title.text().strip()
        if not title:
            title = random_title(self.current_mood(), self.current_format())
            self._title.setText(title)

        setup_path = self._setup_combo.currentData()
        if not isinstance(setup_path, Path) or not setup_path.exists():
            QMessageBox.warning(self, "Generate", "Pick a setup first.")
            return

        try:
            setup: Setup = load_setup(setup_path)
        except (ValidationError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Generate", f"Couldn't load setup:\n{exc}")
            return

        mood = self.current_mood()
        fmt = self.current_format()
        try:
            song = compose(
                title=title,
                setup_ref=setup.id,
                mood=mood,
                fmt=fmt,
                chaos=mood.chaos,
            )
        except Exception as exc:  # noqa: BLE001 — surface verbatim to the user
            QMessageBox.critical(self, "Generate", f"Compose failed:\n{exc}")
            return

        self._state.adopt(song=song, setup=setup)


__all__ = ["ComposerView"]
