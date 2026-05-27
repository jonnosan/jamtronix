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
    Song,
    VoiceConfig,
    VoiceType,
)
from jtx_gui import theme
from jtx_gui.algorithm_meta import (
    FEEL_KNOBS,
    SCHEMAS,
    KnobSpec,
    algorithms_for,
)
from jtx_gui.state import AppState
from jtx_gui.widgets.collapsible import CollapsibleSection
from jtx_gui.widgets.knob import KnobWidget

_KNOBS_PER_ROW = 4
_SCALES = (
    "minor",
    "major",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "aeolian",
    "locrian",
    "harmonic_minor",
    "melodic_minor",
)
_TONICS = ("A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#")


def _seed_from_title(title: str) -> int:
    h = hashlib.sha256(title.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)


# --------------------------------------------------------------------------
#                            voice panel
# --------------------------------------------------------------------------


class VoicePanel(QFrame):
    """One row in the voice list — algorithm picker + collapsible knobs."""

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

        title = QLabel(f"{voice_name.upper()}  ·  {voice_type}")
        title.setObjectName("SectionTitle")

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

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addWidget(title)
        header.addLayout(algo_row)

        self._pattern_section = CollapsibleSection("Pattern Knobs", expanded=True)
        self._feel_section = CollapsibleSection("Feel Knobs", expanded=False)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)
        root.addLayout(header)
        root.addWidget(self._pattern_section)
        root.addWidget(self._feel_section)

        self._rebuild_knob_panels()

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
            current = self._config.feel.get(spec.name, spec.default)
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
        feel_extras = {k: v for k, v in self._config.feel.items() if k not in feel_seen}
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
        self._rebuild_knob_panels()
        self.dirty.emit()

    def _on_pattern_value(self, name: str, value: object) -> None:
        self._config.pattern[name] = value
        self.dirty.emit()

    def _on_feel_value(self, name: str, value: object) -> None:
        self._config.feel[name] = value
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
        kept = {k: v for k, v in self._config.feel.items() if k in feel_seen}
        kept.update(new_dict)
        self._config.feel = kept
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
        self._prog_degrees = QLineEdit(" ".join(prog.degrees))
        self._prog_degrees.setPlaceholderText("e.g. i VI III VII")
        self._prog_degrees.textChanged.connect(self._on_progression)
        self._prog_bars = QSpinBox()
        self._prog_bars.setRange(1, 64)
        self._prog_bars.setValue(prog.bars_per_chord)
        self._prog_bars.setSuffix(" bars/chord")
        self._prog_bars.valueChanged.connect(self._on_progression_bars)

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
        _add_labeled(grid, 4, 0, "PROGRESSION", self._prog_degrees, span=2)
        _add_labeled(grid, 4, 2, "BARS / CHORD", self._prog_bars, span=1)

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

    def _on_progression(self, text: str) -> None:
        degrees = [d for d in text.split() if d]
        if self._song.chord_progression is None:
            self._song.chord_progression = ChordProgression(
                degrees=degrees,
                bars_per_chord=self._prog_bars.value(),
            )
        else:
            self._song.chord_progression.degrees = degrees
        self._on_dirty()

    def _on_progression_bars(self, n: int) -> None:
        if self._song.chord_progression is None:
            self._song.chord_progression = ChordProgression(
                degrees=[d for d in self._prog_degrees.text().split() if d],
                bars_per_chord=n,
            )
        else:
            self._song.chord_progression.bars_per_chord = n
        self._on_dirty()

    # ----- helpers ---------------------------------------------------------

    def _seed_display(self) -> str:
        if self._song.seed_override is not None:
            return f"{self._song.seed_override}  (override)"
        return f"{_seed_from_title(self._song.title)}  (from title)"


# --------------------------------------------------------------------------
#                            LFO list panel
# --------------------------------------------------------------------------


class _LFOPanel(QFrame):
    """Read/edit the song's LFO definitions.

    For #17 this is intentionally lightweight: a list with name + summary,
    plus a JSON-edit fallback for one selected LFO. Full structured
    editing lives with the Parts/Live views in #18 / #19.
    """

    def __init__(self, *, song: Song, on_dirty) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.setObjectName("Panel")
        self._song = song
        self._on_dirty = on_dirty
        self._selected_index: int | None = None

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

        self._detail = QPlainTextEdit()
        self._detail.setMinimumHeight(120)
        self._detail.setPlaceholderText(
            "Select an LFO to view its JSON. Full structured editor in #18/#19."
        )
        self._detail.setReadOnly(True)
        self._detail.setStyleSheet(
            f"font-family: {theme.MONO_FONT_FAMILY}; color: {theme.INK.name()};"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(8)
        root.addWidget(title)
        root.addWidget(self._list)
        root.addLayout(button_row)
        root.addWidget(self._detail)

        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        for lfo in self._song.lfos:
            self._list.addItem(
                QListWidgetItem(
                    f"{lfo.name}  ·  {lfo.shape}  ·  period={lfo.period_bars} bars  "
                    f"·  depth={lfo.depth}",
                )
            )
        if self._song.lfos:
            self._list.setCurrentRow(0)
            self._selected_index = 0
            self._show_detail(0)
        else:
            self._detail.setPlainText("")

    def _on_select(self) -> None:
        row = self._list.currentRow()
        self._selected_index = row if row >= 0 else None
        if row >= 0:
            self._show_detail(row)
        else:
            self._detail.setPlainText("")

    def _show_detail(self, row: int) -> None:
        import json
        from dataclasses import asdict

        lfo = self._song.lfos[row]
        self._detail.setPlainText(json.dumps(asdict(lfo), indent=2))

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
