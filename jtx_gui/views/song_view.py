"""Song view — top-level song header, voice list, LFO definitions.

Renders the loaded song from :class:`jtx_gui.state.AppState` and writes
edits back, calling ``AppState.mark_dirty()`` to update the save state.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from jtx.model import (
    LFO,
    ChordProgression,
    Key,
    LFOApplication,
    Song,
    VoiceConfig,
    VoiceType,
)
from jtx_gui import theme
from jtx_gui.algorithm_meta import (
    FEEL_KNOBS,
    GLOBAL_FEEL_KNOBS,
    SCHEMAS,
    KnobSpec,
    algorithms_for,
)
from jtx_gui.progressions import FAMILY_CHOICES, degrees_for, lookup, rotation_count
from jtx_gui.state import AppState
from jtx_gui.widgets.collapsible import CollapsibleSection
from jtx_gui.widgets.global_feel_panel import GlobalFeelPanel
from jtx_gui.widgets.knob import KnobWidget

_KNOBS_PER_ROW = 4
_SCALES = (
    "minor",
    "major",
    "minor_pentatonic",
    "major_pentatonic",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "aeolian",
    "locrian",
    "harmonic_minor",
)
_TONICS = ("A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#")


def _seed_from_title(title: str) -> int:
    h = hashlib.sha256(title.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)


# --------------------------------------------------------------------------
#                            voice panel
# --------------------------------------------------------------------------


class VoicePanel(QFrame):
    """One voice in the Song view — collapsed by default; expand to edit.

    The outer ``CollapsibleSection`` shows ``name · type · algorithm``
    so all voices fit on one screen at a glance. Expanding reveals the
    algorithm picker plus the pattern + feel knob sections.
    """

    dirty = Signal()

    def __init__(
        self,
        *,
        voice_name: str,
        voice_type: VoiceType,
        config: VoiceConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._voice_name = voice_name
        self._voice_type = voice_type
        self._config = config

        self._outer_section = CollapsibleSection(
            self._header_title(config.algorithm),
            expanded=False,
        )

        self._algo_combo = QComboBox(self)
        for meta in algorithms_for(voice_type):
            self._algo_combo.addItem(meta.name)
        if self._algo_combo.findText(config.algorithm) < 0:
            self._algo_combo.addItem(config.algorithm)  # tolerate unknown algos
        self._algo_combo.setCurrentText(config.algorithm)
        self._algo_combo.currentTextChanged.connect(self._on_algorithm_changed)

        algo_row = QHBoxLayout()
        algo_label = QLabel("ALGORITHM")
        algo_label.setObjectName("FieldLabel")
        algo_row.addWidget(algo_label)
        algo_row.addWidget(self._algo_combo, 1)
        algo_row_widget = QWidget()
        algo_row_widget.setLayout(algo_row)

        self._pattern_section = CollapsibleSection("Pattern Knobs", expanded=True)
        self._feel_section = CollapsibleSection("Feel Knobs", expanded=False)

        self._outer_section.add_widget(algo_row_widget)
        self._outer_section.add_widget(self._pattern_section)
        self._outer_section.add_widget(self._feel_section)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._outer_section)

        self._rebuild_knob_panels()

    def _header_title(self, algorithm: str) -> str:
        return f"{self._voice_name.upper()}  ·  {self._voice_type}  ·  {algorithm}"

    def _rebuild_knob_panels(self) -> None:
        _clear_layout(self._pattern_section.body_layout())
        _clear_layout(self._feel_section.body_layout())

        # Pattern knobs come from the algorithm's schema, plus any
        # extra keys present in the saved song (so unknown knobs stay
        # editable as raw text rather than getting silently dropped).
        algo = self._algo_combo.currentText()
        algo_schema = SCHEMAS.pattern_by_algo.get(algo, {})
        seen: set[str] = set()
        row_widget, row_layout = _new_knob_row()
        row_count = 0
        for spec in algo_schema.values():
            current = self._config.pattern.get(spec.name, spec.default)
            editor = _editor_for(spec, current, on_change=self._on_pattern_value)
            row_layout.addWidget(editor)
            row_count += 1
            seen.add(spec.name)
            if row_count >= _KNOBS_PER_ROW:
                self._pattern_section.add_widget(row_widget)
                row_widget, row_layout = _new_knob_row()
                row_count = 0
        if row_count > 0:
            row_layout.addStretch(1)
            self._pattern_section.add_widget(row_widget)

        # Extra keys (saved by the engine but not in our schema) — render
        # as JSON-text fallback so they round-trip.
        extras = {k: v for k, v in self._config.pattern.items() if k not in seen}
        if extras:
            extras_box = _RawDictEditor(
                title="Extra Pattern Keys",
                values=extras,
                on_change=self._on_extra_pattern,
                parent=self,
            )
            self._pattern_section.add_widget(extras_box)

        self._pattern_section.set_header_hint(f"{len(algo_schema)} knobs")

        # Feel knobs — universal schema. Only show knobs whose default
        # differs from value (i.e. were edited) plus a few common ones?
        # Simpler: show them all. They're 9 knobs.
        row_widget, row_layout = _new_knob_row()
        row_count = 0
        for spec in FEEL_KNOBS:
            current = self._config.mix.get(spec.name, spec.default)
            editor = _editor_for(spec, current, on_change=self._on_feel_value)
            row_layout.addWidget(editor)
            row_count += 1
            if row_count >= _KNOBS_PER_ROW:
                self._feel_section.add_widget(row_widget)
                row_widget, row_layout = _new_knob_row()
                row_count = 0
        if row_count > 0:
            row_layout.addStretch(1)
            self._feel_section.add_widget(row_widget)

        # Extra feel keys (e.g. sidechain_from / sidechain_floor — these
        # exist in saved songs but aren't part of the universal v1 schema).
        feel_seen = {spec.name for spec in FEEL_KNOBS}
        feel_extras = {k: v for k, v in self._config.mix.items() if k not in feel_seen}
        if feel_extras:
            extras_box = _RawDictEditor(
                title="Extra Feel Keys",
                values=feel_extras,
                on_change=self._on_extra_feel,
                parent=self,
            )
            self._feel_section.add_widget(extras_box)

        self._feel_section.set_header_hint(f"{len(FEEL_KNOBS)} knobs")

    # ----- editing -----------------------------------------------------

    def _on_algorithm_changed(self, new_algo: str) -> None:
        if new_algo == self._config.algorithm:
            return
        self._config.algorithm = new_algo
        # Drop pattern knobs that don't belong to the new algorithm —
        # but only ones we know about, so unknown extras survive a swap.
        new_schema = SCHEMAS.pattern_by_algo.get(new_algo, {})
        if new_schema:
            self._config.pattern = {
                k: v
                for k, v in self._config.pattern.items()
                if k in new_schema or k not in _ALL_KNOWN_PATTERN_KEYS
            }
        self._outer_section.set_title(self._header_title(new_algo))
        self._rebuild_knob_panels()
        self.dirty.emit()

    def _on_pattern_value(self, name: str, value: object) -> None:
        self._config.pattern[name] = value
        self.dirty.emit()

    def _on_feel_value(self, name: str, value: object) -> None:
        self._config.mix[name] = value
        self.dirty.emit()

    def _on_extra_pattern(self, new_dict: dict[str, Any]) -> None:
        # Replace only the extras subset; keep schema knobs intact.
        algo_schema = SCHEMAS.pattern_by_algo.get(self._config.algorithm, {})
        kept = {k: v for k, v in self._config.pattern.items() if k in algo_schema}
        kept.update(new_dict)
        self._config.pattern = kept
        self.dirty.emit()

    def _on_extra_feel(self, new_dict: dict[str, Any]) -> None:
        feel_seen = {spec.name for spec in FEEL_KNOBS}
        kept = {k: v for k, v in self._config.mix.items() if k in feel_seen}
        kept.update(new_dict)
        self._config.mix = kept
        self.dirty.emit()


_ALL_KNOWN_PATTERN_KEYS: set[str] = {
    name for spec_dict in SCHEMAS.pattern_by_algo.values() for name in spec_dict.keys()
}


# --------------------------------------------------------------------------
#                              song view
# --------------------------------------------------------------------------


class SongView(QWidget):
    """Top-level Song editor pane."""

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        self._empty_label = QLabel(
            "Open a .jtx file from the File menu to begin.",
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {theme.INK_DIM.name()}; font-size: 14pt; padding: 80px;"
        )

        # The real editor is built on demand once a song is loaded.
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 24)
        self._content_layout.setSpacing(14)
        self._scroll.setWidget(self._content)
        self._scroll.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._empty_label)
        root.addWidget(self._scroll)

        self._state.song_changed.connect(self._refresh)
        self._refresh()

    # ----- view rebuild ----------------------------------------------------

    def _refresh(self) -> None:
        song = self._state.song
        _clear_layout(self._content_layout)
        if song is None:
            self._scroll.setVisible(False)
            self._empty_label.setVisible(True)
            return
        self._empty_label.setVisible(False)
        self._scroll.setVisible(True)

        self._content_layout.addWidget(_HeaderPanel(song=song, on_dirty=self._state.mark_dirty))

        # Song-wide GLOBAL FEEL knobs (pump / groove / drive / tension / wander).
        self._content_layout.addWidget(
            GlobalFeelPanel(song=song, on_dirty=self._state.mark_dirty)
        )

        # Voices section heading.
        voices_title = QLabel("VOICES")
        voices_title.setObjectName("SectionTitle")
        self._content_layout.addWidget(voices_title)

        # Determine each voice's type. We don't have the Setup loaded
        # in v1 of the Song view (Setup is referenced by id; loading
        # it from disk is a later issue). Fall back to inferring type
        # from the algorithm choice when the setup is unavailable.
        for voice_name, voice_config in song.voices.items():
            voice_type = _infer_voice_type(voice_config.algorithm)
            panel = VoicePanel(
                voice_name=voice_name,
                voice_type=voice_type,
                config=voice_config,
                parent=self._content,
            )
            panel.dirty.connect(self._state.mark_dirty)
            self._content_layout.addWidget(panel)

        # LFO definitions section.
        self._content_layout.addWidget(_LFOPanel(song=song, on_dirty=self._state.mark_dirty))

        self._content_layout.addStretch(1)


def _infer_voice_type(algorithm: str) -> VoiceType:
    """Map an algorithm name back to a voice type.

    Used when the Song view can't read the Setup file (Setup loading
    arrives with the new-song wizard in #20). The picker still lets the
    user swap to any algorithm valid for the inferred type.
    """
    from jtx_gui.algorithm_meta import ALGORITHMS

    meta = ALGORITHMS.get(algorithm)
    if meta is not None and meta.voice_types:
        return meta.voice_types[0]
    return "mono"


# --------------------------------------------------------------------------
#                          header panel (song-level)
# --------------------------------------------------------------------------


class _HeaderPanel(QFrame):
    def __init__(self, *, song: Song, on_dirty) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setObjectName("Panel")
        self._song = song
        self._on_dirty = on_dirty

        title_label = QLabel("SONG")
        title_label.setObjectName("SectionTitle")

        self._title_edit = QLineEdit(song.title)
        self._title_edit.textChanged.connect(self._on_title)

        self._seed_label = QLabel(self._seed_display())
        self._seed_label.setStyleSheet(
            f"font-family: {theme.MONO_FONT_FAMILY}; color: {theme.INK_HOT.name()};"
        )
        reroll_btn = QPushButton("REROLL")
        reroll_btn.setMaximumWidth(96)
        reroll_btn.clicked.connect(self._on_reroll)
        clear_btn = QPushButton("USE TITLE")
        clear_btn.setMaximumWidth(96)
        clear_btn.setToolTip("Clear seed override; derive seed from title")
        clear_btn.clicked.connect(self._on_clear_override)

        self._setup_edit = QLineEdit(song.setup_ref)
        self._setup_edit.setReadOnly(True)
        self._setup_edit.setToolTip("Setup picker lives in issue #20 (new-song wizard).")

        self._tonic = QComboBox()
        self._tonic.addItems(list(_TONICS))
        if song.key.tonic in _TONICS:
            self._tonic.setCurrentText(song.key.tonic)
        else:
            self._tonic.addItem(song.key.tonic)
            self._tonic.setCurrentText(song.key.tonic)
        self._tonic.currentTextChanged.connect(self._on_tonic)

        self._scale = QComboBox()
        self._scale.addItems(list(_SCALES))
        if song.key.scale not in _SCALES:
            self._scale.addItem(song.key.scale)
        self._scale.setCurrentText(song.key.scale)
        self._scale.currentTextChanged.connect(self._on_scale)

        self._meter = QLineEdit(song.meter)
        self._meter.setMaximumWidth(72)
        self._meter.textChanged.connect(self._on_meter)

        self._tempo = QSpinBox()
        self._tempo.setRange(30, 300)
        self._tempo.setValue(song.tempo)
        self._tempo.setSuffix(" BPM")
        self._tempo.valueChanged.connect(self._on_tempo)

        prog = song.chord_progression or ChordProgression(degrees=[], bars_per_chord=4)
        # Detect which named family + rotation produces the current
        # degree list, so the picker opens on a meaningful selection.
        match = lookup(prog.degrees)
        if match is None:
            # Song has a hand-written progression that doesn't match any
            # bundled family — default the combo to the first family so
            # twisting the rotation always feels musical, but only commit
            # the change once the user actually touches the combo.
            self._family = next(iter(FAMILY_CHOICES))
            self._rotation = 0
            initial_family_matches_degrees = False
        else:
            self._family, self._rotation = match
            initial_family_matches_degrees = True

        self._prog_family = QComboBox()
        self._prog_family.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for fname in FAMILY_CHOICES:
            self._prog_family.addItem(fname, fname)
        self._prog_family.setCurrentText(self._family)
        self._prog_family.currentTextChanged.connect(self._on_family_changed)

        self._prog_rotation = KnobWidget(
            label="rotation",
            minimum=0,
            maximum=max(0, rotation_count(self._family) - 1),
            value=float(self._rotation),
            integer=True,
            step=1,
        )
        self._prog_rotation.value_changed.connect(lambda v: self._on_rotation_changed(int(v)))

        self._prog_preview = QLabel(self._format_preview(prog.degrees))
        self._prog_preview.setStyleSheet(
            f"font-family: {theme.MONO_FONT_FAMILY}; color: {theme.INK_HOT.name()};"
        )

        # Suppress the no-op save when the song originally had a custom
        # progression that happens to match no family — keep the list
        # untouched until the user actually edits it.
        self._suppress_initial_resync = not initial_family_matches_degrees

        self._prog_bars = KnobWidget(
            label="bars/chord",
            minimum=1,
            maximum=16,
            value=float(prog.bars_per_chord),
            integer=True,
            step=1,
        )
        self._prog_bars.value_changed.connect(lambda v: self._on_progression_bars(int(v)))

        # ----- layout -----
        seed_row = QHBoxLayout()
        seed_row.addWidget(self._seed_label, 1)
        seed_row.addWidget(reroll_btn)
        seed_row.addWidget(clear_btn)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        _add_labeled(grid, 0, 0, "TITLE", self._title_edit, span=3)
        _add_labeled(grid, 1, 0, "SEED", _wrap_layout(seed_row), span=3)
        _add_labeled(grid, 2, 0, "SETUP", self._setup_edit, span=1)
        _add_labeled(grid, 2, 1, "TONIC", self._tonic, span=1)
        _add_labeled(grid, 2, 2, "SCALE", self._scale, span=1)
        _add_labeled(grid, 3, 0, "METER", self._meter, span=1)
        _add_labeled(grid, 3, 1, "TEMPO", self._tempo, span=1)
        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        prog_row.addWidget(self._prog_family)
        prog_row.addWidget(self._prog_rotation)
        _add_labeled(grid, 4, 0, "PROGRESSION", _wrap_layout(prog_row), span=2)
        _add_labeled(grid, 4, 2, "BARS / CHORD", self._prog_bars, span=1)
        _add_labeled(grid, 5, 0, "DEGREES", self._prog_preview, span=3)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(8)
        root.addWidget(title_label)
        root.addLayout(grid)

    # ----- callbacks -------------------------------------------------------

    def _on_title(self, text: str) -> None:
        self._song.title = text
        self._seed_label.setText(self._seed_display())
        self._on_dirty()

    def _on_reroll(self) -> None:
        self._song.seed_override = secrets.randbits(63)
        self._seed_label.setText(self._seed_display())
        self._on_dirty()

    def _on_clear_override(self) -> None:
        if self._song.seed_override is not None:
            self._song.seed_override = None
            self._seed_label.setText(self._seed_display())
            self._on_dirty()

    def _on_tonic(self, text: str) -> None:
        self._song.key = Key(tonic=text, scale=self._song.key.scale)
        self._on_dirty()

    def _on_scale(self, text: str) -> None:
        self._song.key = Key(tonic=self._song.key.tonic, scale=text)
        self._on_dirty()

    def _on_meter(self, text: str) -> None:
        self._song.meter = text
        self._on_dirty()

    def _on_tempo(self, bpm: int) -> None:
        self._song.tempo = bpm
        self._on_dirty()

    def _on_family_changed(self, family: str) -> None:
        self._family = family
        max_rot = max(0, rotation_count(family) - 1)
        # Update the rotation knob's range; KnobWidget clamps the
        # current value and emits if it changed.
        self._prog_rotation.blockSignals(True)
        self._prog_rotation.set_range(0, max_rot)
        if self._rotation > max_rot:
            self._rotation = 0
            self._prog_rotation.set_value(0.0, emit=False)
        self._prog_rotation.blockSignals(False)
        self._sync_progression_to_song()

    def _on_rotation_changed(self, rotation: int) -> None:
        self._rotation = rotation
        self._sync_progression_to_song()

    def _sync_progression_to_song(self) -> None:
        degrees = degrees_for(self._family, self._rotation)
        bars = int(self._prog_bars.value())
        if self._song.chord_progression is None:
            self._song.chord_progression = ChordProgression(degrees=degrees, bars_per_chord=bars)
        else:
            self._song.chord_progression.degrees = degrees
            self._song.chord_progression.bars_per_chord = bars
        self._prog_preview.setText(self._format_preview(degrees))
        if self._suppress_initial_resync:
            # First user-triggered sync — clear the suppression so subsequent
            # rotations still fire dirty.
            self._suppress_initial_resync = False
        self._on_dirty()

    def _on_progression_bars(self, n: int) -> None:
        if self._song.chord_progression is None:
            self._song.chord_progression = ChordProgression(
                degrees=degrees_for(self._family, self._rotation),
                bars_per_chord=n,
            )
        else:
            self._song.chord_progression.bars_per_chord = n
        self._on_dirty()

    @staticmethod
    def _format_preview(degrees: list[str]) -> str:
        return "  ·  ".join(degrees) if degrees else "(none)"

    # ----- helpers ---------------------------------------------------------

    def _seed_display(self) -> str:
        if self._song.seed_override is not None:
            return f"{self._song.seed_override}  (override)"
        return f"{_seed_from_title(self._song.title)}  (from title)"


# --------------------------------------------------------------------------
#                            LFO list panel
# --------------------------------------------------------------------------


_LFO_SHAPES: tuple[str, ...] = ("sine", "tri", "saw", "ramp", "square", "random", "sh")
_LFO_TARGET_KINDS: tuple[str, ...] = (
    "pattern",
    "mix",
    "global_feel",
    "voice",
    "midi",
    "root",
)
# Common function names for the voice: target. Users can type custom
# names too — the parameter_router will route via slot.parameter_map.
_LFO_VOICE_FUNCTIONS: tuple[str, ...] = (
    "cutoff",
    "resonance",
    "glide",
    "bend",
    "detune",
    "modulator",
)


class _LFOPanel(QFrame):
    """Structured editor for the song's LFO definitions.

    Top: list of LFOs with add / remove.
    Bottom: selected LFO's header fields (name / shape / period / phase /
    depth) plus a per-part applications list with target-kind / voice /
    knob composers (or channel + cc spinners for raw MIDI targets).

    The LFO model fields and target-string format are unchanged
    (e.g. ``"pattern:acid:slide_prob"``); this widget just composes
    them from clickable pickers instead of typed JSON.
    """

    def __init__(self, *, song: Song, on_dirty) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setObjectName("Panel")
        self._song = song
        self._on_dirty = on_dirty
        self._selected_index: int | None = None
        # Holds the current detail-pane widget (rebuilt on selection).
        self._detail_holder = QWidget(self)
        self._detail_layout = QVBoxLayout(self._detail_holder)
        self._detail_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_layout.setSpacing(6)

        title = QLabel("LFOS")
        title.setObjectName("SectionTitle")

        self._list = QListWidget()
        self._list.setMaximumHeight(140)
        self._list.itemSelectionChanged.connect(self._on_select)

        add_btn = QPushButton("ADD")
        add_btn.setMaximumWidth(80)
        add_btn.clicked.connect(self._on_add)
        remove_btn = QPushButton("REMOVE")
        remove_btn.setMaximumWidth(96)
        remove_btn.clicked.connect(self._on_remove)
        button_row = QHBoxLayout()
        button_row.addWidget(add_btn)
        button_row.addWidget(remove_btn)
        button_row.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(8)
        root.addWidget(title)
        root.addWidget(self._list)
        root.addLayout(button_row)
        root.addWidget(self._detail_holder)

        self._refresh_list()

    # ----- list management ------------------------------------------------

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for lfo in self._song.lfos:
            self._list.addItem(
                QListWidgetItem(
                    f"{lfo.name}  ·  {lfo.shape}  ·  period={lfo.period_bars} bars"
                    f"  ·  depth={lfo.depth}  ·  {len(lfo.applications)} bound",
                )
            )
        self._list.blockSignals(False)
        if self._song.lfos:
            self._list.setCurrentRow(0)
            self._selected_index = 0
            self._show_detail(0)
        else:
            self._selected_index = None
            _clear_layout(self._detail_layout)

    def _on_select(self) -> None:
        row = self._list.currentRow()
        self._selected_index = row if row >= 0 else None
        if row >= 0:
            self._show_detail(row)
        else:
            _clear_layout(self._detail_layout)

    def _on_add(self) -> None:
        existing = {lfo.name for lfo in self._song.lfos}
        base = "lfo"
        i = 1
        while f"{base}{i}" in existing:
            i += 1
        new_lfo = LFO(name=f"{base}{i}", shape="sine", period_bars=4.0)
        self._song.lfos.append(new_lfo)
        self._refresh_list()
        self._on_dirty()

    def _on_remove(self) -> None:
        if self._selected_index is None:
            return
        del self._song.lfos[self._selected_index]
        self._refresh_list()
        self._on_dirty()

    # ----- detail pane ---------------------------------------------------

    def _show_detail(self, row: int) -> None:
        _clear_layout(self._detail_layout)
        lfo = self._song.lfos[row]
        self._detail_layout.addWidget(self._build_lfo_header(lfo))
        self._detail_layout.addWidget(self._build_applications_box(lfo))

    def _build_lfo_header(self, lfo: LFO) -> QWidget:
        name_edit = QLineEdit(lfo.name)
        name_edit.editingFinished.connect(lambda: self._on_name_changed(lfo, name_edit.text()))

        shape_combo = QComboBox()
        shape_combo.addItems(_LFO_SHAPES)
        if lfo.shape in _LFO_SHAPES:
            shape_combo.setCurrentText(lfo.shape)
        else:
            shape_combo.addItem(lfo.shape)
            shape_combo.setCurrentText(lfo.shape)
        shape_combo.currentTextChanged.connect(lambda v: self._on_shape_changed(lfo, v))

        period = KnobWidget(
            label="period",
            minimum=0.25,
            maximum=32.0,
            value=float(lfo.period_bars),
            step=0.25,
            decimals=2,
        )
        period.value_changed.connect(lambda v: self._on_period_changed(lfo, float(v)))

        phase = KnobWidget(
            label="phase",
            minimum=0.0,
            maximum=1.0,
            value=float(lfo.phase),
            step=0.01,
            decimals=2,
        )
        phase.value_changed.connect(lambda v: self._on_phase_changed(lfo, float(v)))

        depth = KnobWidget(
            label="depth",
            minimum=0.0,
            maximum=1.0,
            value=float(lfo.depth),
            step=0.01,
            decimals=2,
        )
        depth.value_changed.connect(lambda v: self._on_depth_changed(lfo, float(v)))

        samples = QSpinBox()
        samples.setRange(1, 128)
        samples.setPrefix("samples ")
        samples.setValue(int(lfo.samples_per_bar))
        samples.setToolTip(
            "Sub-bar sampling for event-emitting targets (midi:/voice:). "
            "Higher = smoother sweep, more events per bar. Knob-writing "
            "targets ignore this (they sample once at bar start)."
        )
        samples.valueChanged.connect(lambda v: self._on_samples_changed(lfo, int(v)))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        _add_labeled(grid, 0, 0, "NAME", name_edit, span=2)
        _add_labeled(grid, 0, 2, "SHAPE", shape_combo, span=1)
        _add_labeled(grid, 0, 3, "SAMPLES/BAR", samples, span=1)

        knob_row = QHBoxLayout()
        knob_row.setSpacing(10)
        knob_row.addWidget(period)
        knob_row.addWidget(phase)
        knob_row.addWidget(depth)
        knob_row.addStretch(1)

        container = QFrame()
        container.setObjectName("Panel")
        col = QVBoxLayout(container)
        col.setContentsMargins(10, 8, 10, 8)
        col.setSpacing(6)
        col.addLayout(grid)
        col.addLayout(knob_row)
        return container

    def _build_applications_box(self, lfo: LFO) -> QWidget:
        title = QLabel("BOUND TARGETS")
        title.setObjectName("FieldLabel")

        rows_holder = QWidget()
        rows_layout = QVBoxLayout(rows_holder)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(4)
        for i, app in enumerate(lfo.applications):
            rows_layout.addWidget(self._build_application_row(lfo, i, app))

        add_btn = QPushButton("BIND NEW TARGET")
        add_btn.clicked.connect(lambda: self._on_add_application(lfo))

        wrap = QFrame()
        wrap.setObjectName("Panel")
        col = QVBoxLayout(wrap)
        col.setContentsMargins(10, 8, 10, 8)
        col.setSpacing(6)
        col.addWidget(title)
        col.addWidget(rows_holder)
        col.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignLeft)
        return wrap

    def _build_application_row(self, lfo: LFO, idx: int, app: LFOApplication) -> QWidget:
        return _LFOApplicationRow(
            song=self._song,
            lfo=lfo,
            app=app,
            on_change=self._on_dirty_and_refresh,
            on_remove=lambda: self._on_remove_application(lfo, idx),
        )

    # ----- callbacks ------------------------------------------------------

    def _on_name_changed(self, lfo: LFO, text: str) -> None:
        if lfo.name != text:
            lfo.name = text
            self._on_dirty_and_refresh()

    def _on_shape_changed(self, lfo: LFO, text: str) -> None:
        if lfo.shape != text:
            lfo.shape = text  # type: ignore[assignment]
            self._on_dirty_and_refresh()

    def _on_period_changed(self, lfo: LFO, value: float) -> None:
        lfo.period_bars = value
        self._on_dirty_and_refresh()

    def _on_phase_changed(self, lfo: LFO, value: float) -> None:
        lfo.phase = value
        self._on_dirty()

    def _on_depth_changed(self, lfo: LFO, value: float) -> None:
        lfo.depth = value
        self._on_dirty_and_refresh()

    def _on_samples_changed(self, lfo: LFO, value: int) -> None:
        if lfo.samples_per_bar != value:
            lfo.samples_per_bar = max(1, value)
            self._on_dirty()

    def _on_add_application(self, lfo: LFO) -> None:
        # Default to the first part + first voice's first pattern knob,
        # or root if no voices/knobs exist.
        first_part = next(iter(self._song.parts.keys()), "")
        target = self._default_target_for(self._song)
        lfo.applications.append(LFOApplication(part=first_part, target=target))
        self._on_dirty_and_refresh()
        if self._selected_index is not None:
            self._show_detail(self._selected_index)

    def _on_remove_application(self, lfo: LFO, idx: int) -> None:
        if 0 <= idx < len(lfo.applications):
            del lfo.applications[idx]
            self._on_dirty_and_refresh()
            if self._selected_index is not None:
                self._show_detail(self._selected_index)

    def _on_dirty_and_refresh(self) -> None:
        self._on_dirty()
        # Refresh the list summary line (count of bound targets etc.).
        row = self._selected_index
        self._list.blockSignals(True)
        for i, lfo in enumerate(self._song.lfos):
            item = self._list.item(i)
            if item is not None:
                item.setText(
                    f"{lfo.name}  ·  {lfo.shape}  ·  period={lfo.period_bars} bars"
                    f"  ·  depth={lfo.depth}  ·  {len(lfo.applications)} bound",
                )
        if row is not None:
            self._list.setCurrentRow(row)
        self._list.blockSignals(False)

    @staticmethod
    def _default_target_for(song: Song) -> str:
        for voice_name, voice in song.voices.items():
            schema = SCHEMAS.pattern_by_algo.get(voice.algorithm, {})
            if schema:
                first_knob = next(iter(schema.keys()))
                return f"pattern:{voice_name}:{first_knob}"
        return "root:"


class _LFOApplicationRow(QFrame):
    """One row of the LFO applications list — composes the target string.

    Target syntax (per ``docs/SPEC.md`` §LFOs):
    * ``pattern:<voice>:<knob>``
    * ``mix:<voice>:<knob>``
    * ``global_feel:<knob>``
    * ``voice:<voice>:<function>``
    * ``midi:ch<N>:cc<M>``
    * ``root:<voice>``
    """

    def __init__(
        self,
        *,
        song: Song,
        lfo: LFO,
        app: LFOApplication,
        on_change: Callable[[], None],
        on_remove: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._song = song
        self._lfo = lfo
        self._app = app
        self._on_change = on_change

        kind, voice, knob, midi_channel, midi_cc = _parse_target(app.target)

        self._part_combo = QComboBox()
        self._part_combo.addItems(list(song.parts.keys()))
        if app.part in song.parts:
            self._part_combo.setCurrentText(app.part)
        else:
            if app.part:
                self._part_combo.addItem(app.part)
                self._part_combo.setCurrentText(app.part)
        self._part_combo.currentTextChanged.connect(self._on_part_changed)

        self._kind_combo = QComboBox()
        self._kind_combo.addItems(_LFO_TARGET_KINDS)
        self._kind_combo.setCurrentText(kind)
        self._kind_combo.currentTextChanged.connect(self._on_kind_changed)

        # Composed-target fields (voice / knob / midi channel / cc):
        self._voice_combo = QComboBox()
        self._voice_combo.setMinimumWidth(140)
        self._voice_combo.currentTextChanged.connect(self._on_voice_changed)

        self._knob_combo = QComboBox()
        self._knob_combo.setMinimumWidth(160)
        self._knob_combo.currentTextChanged.connect(self._on_knob_changed)

        self._midi_channel = QSpinBox()
        self._midi_channel.setRange(1, 16)
        self._midi_channel.setPrefix("ch ")
        self._midi_channel.setValue(midi_channel or 1)
        self._midi_channel.valueChanged.connect(self._sync_target)

        self._midi_cc = QSpinBox()
        self._midi_cc.setRange(0, 127)
        self._midi_cc.setPrefix("cc ")
        self._midi_cc.setValue(midi_cc or 74)
        self._midi_cc.valueChanged.connect(self._sync_target)

        remove_btn = QPushButton("×")
        remove_btn.setMaximumWidth(36)
        remove_btn.setToolTip("Remove this binding")
        remove_btn.clicked.connect(on_remove)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self._part_combo)
        row.addWidget(self._kind_combo)
        row.addWidget(self._voice_combo)
        row.addWidget(self._knob_combo)
        row.addWidget(self._midi_channel)
        row.addWidget(self._midi_cc)
        row.addWidget(remove_btn)

        self._populate_voice_combo(initial=voice)
        self._populate_knob_combo(initial=knob)
        self._reveal_fields_for_kind(kind)

    # ----- composing the target string -----------------------------------

    def _sync_target(self) -> None:
        kind = self._kind_combo.currentText()
        if kind in ("pattern", "mix", "voice"):
            voice = self._voice_combo.currentText()
            knob = self._knob_combo.currentText()
            target = f"{kind}:{voice}:{knob}"
        elif kind == "global_feel":
            knob = self._knob_combo.currentText()
            target = f"global_feel:{knob}"
        elif kind == "midi":
            target = f"midi:ch{self._midi_channel.value()}:cc{self._midi_cc.value()}"
        elif kind == "root":
            voice = self._voice_combo.currentText()
            target = f"root:{voice}"
        else:
            target = self._app.target
        if target != self._app.target:
            self._app.target = target
            self._on_change()

    def _on_part_changed(self, name: str) -> None:
        if self._app.part != name:
            self._app.part = name
            self._on_change()

    def _on_kind_changed(self, kind: str) -> None:
        self._reveal_fields_for_kind(kind)
        # Re-populate voice + knob options for the new kind.
        self._populate_voice_combo()
        self._populate_knob_combo()
        self._sync_target()

    def _on_voice_changed(self, _name: str) -> None:
        # Pattern knobs are voice-dependent; refresh.
        if self._kind_combo.currentText() == "pattern":
            self._populate_knob_combo()
        self._sync_target()

    def _on_knob_changed(self, _name: str) -> None:
        self._sync_target()

    def _reveal_fields_for_kind(self, kind: str) -> None:
        self._voice_combo.setVisible(kind in {"pattern", "mix", "voice", "root"})
        self._knob_combo.setVisible(kind in {"pattern", "mix", "global_feel", "voice"})
        self._knob_combo.setEditable(kind == "voice")
        self._midi_channel.setVisible(kind == "midi")
        self._midi_cc.setVisible(kind == "midi")

    def _populate_voice_combo(self, *, initial: str | None = None) -> None:
        current = initial if initial is not None else self._voice_combo.currentText()
        self._voice_combo.blockSignals(True)
        self._voice_combo.clear()
        self._voice_combo.addItems(list(self._song.voices.keys()))
        if current and self._voice_combo.findText(current) < 0:
            self._voice_combo.addItem(current)
        if current:
            self._voice_combo.setCurrentText(current)
        self._voice_combo.blockSignals(False)

    def _populate_knob_combo(self, *, initial: str | None = None) -> None:
        kind = self._kind_combo.currentText()
        voice_name = self._voice_combo.currentText()
        current = initial if initial is not None else self._knob_combo.currentText()
        options: list[str] = []
        if kind == "mix":
            options = [k.name for k in FEEL_KNOBS]  # MIX_KNOBS aliased as FEEL_KNOBS
        elif kind == "global_feel":
            options = [k.name for k in GLOBAL_FEEL_KNOBS]
        elif kind == "voice":
            options = list(_LFO_VOICE_FUNCTIONS)
        elif kind == "pattern" and voice_name in self._song.voices:
            algo = self._song.voices[voice_name].algorithm
            options = list(SCHEMAS.pattern_by_algo.get(algo, {}).keys())
        self._knob_combo.blockSignals(True)
        self._knob_combo.clear()
        self._knob_combo.addItems(options)
        if current and self._knob_combo.findText(current) < 0:
            self._knob_combo.addItem(current)
        if current:
            self._knob_combo.setCurrentText(current)
        self._knob_combo.blockSignals(False)


def _parse_target(target: str) -> tuple[str, str, str, int | None, int | None]:
    """Split a target string into (kind, voice, knob, midi_channel, midi_cc).

    Unknown shapes return ``("pattern", "", "", None, None)`` so the
    GUI opens with sane defaults instead of crashing.
    """
    if not target:
        return ("pattern", "", "", None, None)
    parts = target.split(":")
    if parts[0] in {"pattern", "mix", "voice"} and len(parts) >= 3:
        return (parts[0], parts[1], parts[2], None, None)
    if parts[0] == "global_feel" and len(parts) >= 2:
        return ("global_feel", "", parts[1], None, None)
    if parts[0] == "root" and len(parts) >= 2:
        return ("root", parts[1], "", None, None)
    if parts[0] == "midi" and len(parts) >= 3:
        ch = _trim_int_prefix(parts[1], "ch")
        cc = _trim_int_prefix(parts[2], "cc")
        return ("midi", "", "", ch, cc)
    return ("pattern", "", "", None, None)


def _trim_int_prefix(token: str, prefix: str) -> int | None:
    if token.startswith(prefix):
        try:
            return int(token[len(prefix) :])
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
#                          knob editor factory
# --------------------------------------------------------------------------


def _editor_for(
    spec: KnobSpec,
    current: object,
    on_change: Callable[[str, object], None],
) -> QWidget:
    """Build the right widget for a knob's kind, with a label below it."""
    if spec.kind == "float":
        knob = KnobWidget(
            label=spec.name,
            minimum=float(spec.minimum),
            maximum=float(spec.maximum),
            value=float(current if isinstance(current, (int, float)) else spec.default),  # type: ignore[arg-type]
            step=float(spec.step),
            decimals=spec.decimals,
        )
        knob.value_changed.connect(lambda v, name=spec.name: on_change(name, float(v)))
        if spec.description:
            knob.setToolTip(f"{spec.name}: {spec.description}")
        return knob

    if spec.kind == "int":
        knob = KnobWidget(
            label=spec.name,
            minimum=float(spec.minimum),
            maximum=float(spec.maximum),
            value=float(current if isinstance(current, (int, float)) else spec.default),  # type: ignore[arg-type]
            step=max(1.0, float(spec.step)),
            integer=True,
        )
        knob.value_changed.connect(lambda v, name=spec.name: on_change(name, int(v)))
        if spec.description:
            knob.setToolTip(f"{spec.name}: {spec.description}")
        return knob

    if spec.kind == "choice":
        return _ChoiceField(spec=spec, current=str(current), on_change=on_change)

    if spec.kind in {"list_int", "list_str", "string"}:
        return _TextField(spec=spec, current=current, on_change=on_change)

    raise ValueError(f"unknown knob kind: {spec.kind!r}")


class _ChoiceField(QWidget):
    def __init__(
        self,
        *,
        spec: KnobSpec,
        current: str,
        on_change: Callable[[str, object], None],
    ) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        lbl = QLabel(spec.name.upper())
        lbl.setObjectName("FieldLabel")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._combo = QComboBox()
        self._combo.addItems(list(spec.choices))
        if current not in spec.choices:
            self._combo.addItem(current)
        self._combo.setCurrentText(current)
        self._combo.currentTextChanged.connect(
            lambda v, name=spec.name: on_change(name, v),
        )
        layout.addWidget(self._combo)
        layout.addWidget(lbl)
        self.setMinimumWidth(110)
        if spec.description:
            tip = f"{spec.name}: {spec.description}"
            self.setToolTip(tip)
            self._combo.setToolTip(tip)


class _TextField(QWidget):
    """Free-text editor for list_int / list_str / string knob kinds."""

    def __init__(
        self,
        *,
        spec: KnobSpec,
        current: object,
        on_change: Callable[[str, object], None],
    ) -> None:
        super().__init__()
        self._spec = spec
        self._on_change = on_change

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        lbl = QLabel(spec.name.upper())
        lbl.setObjectName("FieldLabel")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit = QLineEdit()
        self._edit.setText(self._format_value(current))
        self._edit.editingFinished.connect(self._commit)
        if spec.kind == "list_int":
            self._edit.setPlaceholderText("comma-separated ints, e.g. 0,4,8,12")
        layout.addWidget(self._edit)
        layout.addWidget(lbl)
        self.setMinimumWidth(140)
        if spec.description:
            tip = f"{spec.name}: {spec.description}"
            self.setToolTip(tip)
            self._edit.setToolTip(tip)

    def _format_value(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return ", ".join(str(x) for x in value)
        return str(value)

    def _commit(self) -> None:
        raw = self._edit.text().strip()
        parsed: object
        if self._spec.kind == "list_int":
            if not raw:
                parsed = []
            else:
                try:
                    parsed = [int(p.strip()) for p in raw.split(",") if p.strip()]
                except ValueError:
                    # Reject invalid; restore last-good text.
                    return
        elif self._spec.kind == "list_str":
            parsed = [p.strip() for p in raw.split(",") if p.strip()]
        else:
            parsed = raw
        self._on_change(self._spec.name, parsed)


class _RawDictEditor(QFrame):
    """JSON-edit fallback for knob dicts not covered by a known schema."""

    def __init__(
        self,
        *,
        title: str,
        values: dict[str, Any],
        on_change: Callable[[dict[str, Any]], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._on_change = on_change
        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("FieldLabel")
        self._edit = QPlainTextEdit()
        import json

        self._edit.setPlainText(json.dumps(values, indent=2))
        self._edit.setMaximumHeight(120)
        self._edit.setStyleSheet(
            f"font-family: {theme.MONO_FONT_FAMILY}; color: {theme.INK.name()};"
        )
        commit_btn = QPushButton("APPLY")
        commit_btn.setMaximumWidth(96)
        commit_btn.clicked.connect(self._commit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)
        layout.addWidget(title_lbl)
        layout.addWidget(self._edit)
        layout.addWidget(commit_btn, 0, Qt.AlignmentFlag.AlignRight)

    def _commit(self) -> None:
        import json

        try:
            parsed = json.loads(self._edit.toPlainText())
        except json.JSONDecodeError:
            return
        if isinstance(parsed, dict):
            self._on_change(parsed)


# --------------------------------------------------------------------------
#                              utilities
# --------------------------------------------------------------------------


def _clear_layout(layout) -> None:  # type: ignore[no-untyped-def]
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        else:
            sub = item.layout()
            if sub is not None:
                _clear_layout(sub)


def _add_labeled(  # type: ignore[no-untyped-def]
    grid: QGridLayout,
    row: int,
    col: int,
    label_text: str,
    widget,
    *,
    span: int = 1,
) -> None:
    label = QLabel(label_text)
    label.setObjectName("FieldLabel")
    cell = QVBoxLayout()
    cell.setContentsMargins(0, 0, 0, 0)
    cell.setSpacing(2)
    cell.addWidget(label)
    if isinstance(widget, QWidget):
        cell.addWidget(widget)
    else:
        cell.addLayout(widget)
    container = QWidget()
    container.setLayout(cell)
    grid.addWidget(container, row, col, 1, span)


def _wrap_layout(layout) -> QWidget:  # type: ignore[no-untyped-def]
    w = QWidget()
    w.setLayout(layout)
    return w


def _new_knob_row() -> tuple[QWidget, QHBoxLayout]:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    return w, layout
