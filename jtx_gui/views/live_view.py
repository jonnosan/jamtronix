"""Live view — the jam surface.

Top: big PLAY/STOP transport plus a bar/beat indicator and the
current/queued part labels.

Middle: a horizontal strip of *part buttons*. Click while stopped to
choose the starting part. Click while playing to queue the part — it
takes over at the next bar boundary.

Bottom: a scrollable knob panel for the *active* part's effective
voice configuration. Edits land in the part's :class:`VoiceOverride`,
so jamming with the knobs doesn't perturb the song-level baseline.

The TransportService does the actual playback. Setup loading lives
on :class:`AppState`; if the sibling .jtx-setup is missing we show
the reason and disable transport.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jtx.model import ClockMode, Part, VoiceConfig, VoiceOverride
from jtx_gui import theme
from jtx_gui.algorithm_meta import FEEL_KNOBS, SCHEMAS, KnobSpec
from jtx_gui.state import AppState
from jtx_gui.transport import BarTick, TransportService
from jtx_gui.views.song_view import _clear_layout, _infer_voice_type  # noqa: F401
from jtx_gui.widgets.collapsible import CollapsibleSection
from jtx_gui.widgets.knob import KnobWidget

PlaybackPrefsFn = Callable[[], tuple["ClockMode | None", str | None]]
"""Return ``(clock_mode_or_None, port_override_or_None)``."""

_KNOBS_PER_ROW = 4


class LiveView(QWidget):
    """The jam surface."""

    def __init__(
        self,
        state: AppState,
        transport: TransportService | None = None,
        *,
        playback_prefs: PlaybackPrefsFn | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._transport = transport or TransportService(parent=self)
        self._playback_prefs: PlaybackPrefsFn = playback_prefs or (lambda: (None, None))
        self._current_bar: int = 0
        self._part_bars: int = 1
        self._active_part: str | None = None
        self._queued_part: str | None = None

        self._empty_label = QLabel("Open a .jtx file from the File menu to begin.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {theme.INK_DIM.name()}; font-size: 14pt; padding: 80px;"
        )

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(20, 16, 20, 20)
        content_layout.setSpacing(14)

        # ----- top transport row -----
        self._transport_panel = _TransportPanel(
            transport=self._transport,
            state=state,
        )
        content_layout.addWidget(self._transport_panel)

        # ----- part buttons -----
        self._parts_strip = _PartButtonStrip(
            on_part_clicked=self._on_part_clicked,
        )
        content_layout.addWidget(self._parts_strip)

        # ----- knob panel for active part -----
        knob_title = QLabel("ACTIVE PART KNOBS")
        knob_title.setObjectName("SectionTitle")
        self._knob_scroll = QScrollArea()
        self._knob_scroll.setWidgetResizable(True)
        self._knob_inner = QWidget()
        self._knob_layout = QVBoxLayout(self._knob_inner)
        self._knob_layout.setContentsMargins(8, 8, 8, 12)
        self._knob_layout.setSpacing(10)
        self._knob_scroll.setWidget(self._knob_inner)

        content_layout.addWidget(knob_title)
        content_layout.addWidget(self._knob_scroll, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._empty_label)
        root.addWidget(self._content)
        self._content.setVisible(False)

        # ----- wire state + transport signals -----
        self._state.song_changed.connect(self._refresh)
        self._transport.bar_changed.connect(self._on_bar_changed)
        self._transport.part_changed.connect(self._on_part_changed)
        self._transport.queued_changed.connect(self._on_queued_changed)
        self._transport.stopped.connect(self._on_stopped)

        self._refresh()

    # ----- state-driven refresh -------------------------------------------

    def _refresh(self) -> None:
        song = self._state.song
        if song is None:
            self._content.setVisible(False)
            self._empty_label.setVisible(True)
            return
        self._content.setVisible(True)
        self._empty_label.setVisible(False)
        self._parts_strip.set_parts(list(song.parts.keys()))
        self._transport_panel.refresh()

        # If the active part has gone away (renamed/removed), drop it.
        if self._active_part is not None and self._active_part not in song.parts:
            self._active_part = None
            self._rebuild_knob_panel()
        elif self._active_part is not None:
            self._rebuild_knob_panel()
        else:
            _clear_layout(self._knob_layout)

    # ----- part interactions ----------------------------------------------

    def _on_part_clicked(self, part_name: str) -> None:
        song = self._state.song
        setup = self._state.setup
        if song is None:
            return
        if not self._transport.is_running:
            if setup is None:
                self._transport_panel.show_error(
                    self._state.setup_error or "Setup not loaded — can't play."
                )
                return
            clock_mode, port_override = self._playback_prefs()
            self._transport.start(
                song=song,
                setup=setup,
                part_name=part_name,
                port_name=port_override or setup.default_midi_port,
                clock_mode=clock_mode,
            )
            self._active_part = part_name
            self._parts_strip.set_active(part_name)
            self._rebuild_knob_panel()
        else:
            # Toggle queue: clicking the active part clears any queue.
            if part_name == self._active_part:
                self._transport.queue_part(None)
            else:
                self._transport.queue_part(part_name)

    # ----- transport callbacks --------------------------------------------

    def _on_bar_changed(self, tick: BarTick) -> None:
        self._current_bar = tick.bar_index
        self._part_bars = tick.part_bars
        self._transport_panel.set_bar(tick.part_name, tick.bar_index, tick.part_bars)

    def _on_part_changed(self, name: str) -> None:
        self._active_part = name
        self._parts_strip.set_active(name)
        self._rebuild_knob_panel()
        self._transport_panel.set_active_part(name)

    def _on_queued_changed(self, value: Any) -> None:
        name = value if isinstance(value, str) else None
        self._queued_part = name
        self._parts_strip.set_queued(name)
        self._transport_panel.set_queued_part(name)

    def _on_stopped(self) -> None:
        self._active_part = None
        self._queued_part = None
        self._parts_strip.set_active(None)
        self._parts_strip.set_queued(None)
        self._transport_panel.on_stopped()

    # ----- knob panel rebuild ---------------------------------------------

    def _rebuild_knob_panel(self) -> None:
        _clear_layout(self._knob_layout)
        song = self._state.song
        if song is None or self._active_part is None or self._active_part not in song.parts:
            return
        part = song.parts[self._active_part]
        for voice_name, voice_config in song.voices.items():
            panel = _LiveVoicePanel(
                voice_name=voice_name,
                song_config=voice_config,
                part=part,
                on_dirty=self._state.mark_dirty,
            )
            self._knob_layout.addWidget(panel)
        self._knob_layout.addStretch(1)


# --------------------------------------------------------------------------
#                          transport panel (top)
# --------------------------------------------------------------------------


class _TransportPanel(QFrame):
    """Top strip: big PLAY/STOP, bar/beat indicator, status text."""

    def __init__(
        self,
        *,
        transport: TransportService,
        state: AppState,
    ) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._transport = transport
        self._state = state
        self._current_part: str | None = None
        self._queued_part: str | None = None
        self._bar = 0
        self._part_bars = 0
        # 0..3 beat-within-bar; driven by a 100Hz QTimer in 4/4 land.
        # We don't try to align with the worker's tick stream; this is
        # purely visual feedback.
        self._beat = 0
        self._beat_ms_elapsed = 0

        self._play_btn = QPushButton("PLAY")
        self._play_btn.setMinimumHeight(56)
        self._play_btn.setMinimumWidth(140)
        self._play_btn.setStyleSheet(self._play_button_style(playing=False))
        self._play_btn.clicked.connect(self._toggle)

        self._bar_label = QLabel("BAR —  ·  BEAT —")
        self._bar_label.setStyleSheet(
            f"font-family: {theme.MONO_FONT_FAMILY}; color: {theme.INK_HOT.name()};"
            "font-size: 16pt; letter-spacing: 1px;"
        )

        self._part_label = QLabel("—")
        self._part_label.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-size: 14pt;"
            "font-weight: bold; letter-spacing: 1px;"
        )
        self._queue_label = QLabel("")
        self._queue_label.setStyleSheet(
            f"color: {theme.ACCENT_AMBER.name()}; font-size: 10pt; letter-spacing: 1px;"
        )
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {theme.ACCENT_RED.name()}; font-size: 10pt;")

        info_column = QVBoxLayout()
        info_column.setContentsMargins(0, 0, 0, 0)
        info_column.setSpacing(2)
        info_column.addWidget(self._bar_label)
        info_column.addWidget(self._part_label)
        info_column.addWidget(self._queue_label)
        info_column.addWidget(self._status_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(20)
        layout.addWidget(self._play_btn)
        layout.addLayout(info_column, 1)

        self._beat_timer = QTimer(self)
        self._beat_timer.setInterval(30)
        self._beat_timer.timeout.connect(self._tick_beat_visual)

    # ----- play / stop ----------------------------------------------------

    def _toggle(self) -> None:
        if self._transport.is_running:
            self._transport.stop()

    def refresh(self) -> None:
        """Re-read state for error display (setup missing etc.)."""
        if self._state.song is None:
            self._status_label.setText("")
            return
        if self._state.setup is None and self._state.setup_error:
            self._status_label.setText(self._state.setup_error)
        else:
            self._status_label.setText("")

    def show_error(self, msg: str) -> None:
        self._status_label.setText(msg)

    def set_bar(self, part_name: str, bar_index: int, part_bars: int) -> None:
        self._current_part = part_name
        self._bar = bar_index
        self._part_bars = part_bars
        self._beat = 0
        self._beat_ms_elapsed = 0
        self._update_bar_label()
        self._part_label.setText(
            f"NOW PLAYING  ·  {part_name.upper()}  ·  BAR {bar_index + 1}/{part_bars}"
        )
        if not self._beat_timer.isActive():
            self._play_btn.setText("STOP")
            self._play_btn.setStyleSheet(self._play_button_style(playing=True))
            self._beat_timer.start()

    def set_active_part(self, name: str) -> None:
        self._current_part = name
        self._part_label.setText(f"NOW PLAYING  ·  {name.upper()}")

    def set_queued_part(self, name: str | None) -> None:
        self._queued_part = name
        self._queue_label.setText(f"QUEUED  ·  {name.upper()}" if name else "")

    def on_stopped(self) -> None:
        self._beat_timer.stop()
        self._play_btn.setText("PLAY")
        self._play_btn.setStyleSheet(self._play_button_style(playing=False))
        self._bar_label.setText("BAR —  ·  BEAT —")
        self._part_label.setText("—")
        self._queue_label.setText("")

    # ----- visuals --------------------------------------------------------

    def _tick_beat_visual(self) -> None:
        # Approximate beat advance from the song tempo. Not sample-accurate,
        # just a vibe knob for the user.
        song = self._state.song
        if song is None:
            return
        ms_per_beat = 60000.0 / max(1, song.tempo)
        self._beat_ms_elapsed += self._beat_timer.interval()
        if self._beat_ms_elapsed >= ms_per_beat:
            self._beat_ms_elapsed = 0
            self._beat = (self._beat + 1) % 4
            self._update_bar_label()

    def _update_bar_label(self) -> None:
        bar_text = f"{self._bar + 1}" if self._part_bars else "—"
        self._bar_label.setText(f"BAR {bar_text}  ·  BEAT {self._beat + 1}/4")

    @staticmethod
    def _play_button_style(playing: bool) -> str:
        bg = theme.ACCENT_RED.name() if playing else theme.ACCENT_GREEN.name()
        rules = (
            f"QPushButton {{ background-color: {bg};"
            f" color: {theme.PANEL_BG.name()}; font-size: 16pt; font-weight: bold;"
            " border-radius: 4px; }"
        )
        if not playing:
            rules += f"QPushButton:hover {{ background-color: {theme.INK_HOT.name()}; }}"
        return rules


# --------------------------------------------------------------------------
#                          part buttons strip
# --------------------------------------------------------------------------


class _PartButtonStrip(QFrame):
    """Horizontal row of part buttons. Click → callback(part_name)."""

    def __init__(self, *, on_part_clicked: Callable[[str], None]) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._on_part_clicked = on_part_clicked
        self._buttons: dict[str, QPushButton] = {}
        self._active: str | None = None
        self._queued: str | None = None

        title = QLabel("PARTS  ·  click to queue / play")
        title.setObjectName("SectionTitle")
        self._row = QHBoxLayout()
        self._row.setSpacing(8)
        self._row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addLayout(self._row)

    def set_parts(self, names: list[str]) -> None:
        # Tear down everything and rebuild — cheap; only fires on song
        # changes (add/remove/rename), not on every bar.
        while self._row.count():
            item = self._row.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._buttons.clear()
        for name in names:
            btn = QPushButton(name.upper())
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda _checked=False, n=name: self._on_part_clicked(n))
            self._row.addWidget(btn)
            self._buttons[name] = btn
        self._row.addStretch(1)
        self._restyle_all()

    def set_active(self, name: str | None) -> None:
        self._active = name
        self._restyle_all()

    def set_queued(self, name: str | None) -> None:
        self._queued = name
        self._restyle_all()

    def _restyle_all(self) -> None:
        for name, btn in self._buttons.items():
            btn.setStyleSheet(self._style_for(name))

    def _style_for(self, name: str) -> str:
        if name == self._active:
            return (
                f"QPushButton {{ background-color: {theme.ACCENT_GREEN.name()};"
                f" color: {theme.PANEL_BG.name()}; font-weight: bold;"
                " border-radius: 3px; }"
            )
        if name == self._queued:
            return (
                f"QPushButton {{ background-color: {theme.ACCENT_AMBER.name()};"
                f" color: {theme.PANEL_BG.name()}; font-weight: bold;"
                " border-radius: 3px; }"
            )
        return (
            f"QPushButton {{ background-color: {theme.BRASS_DARK.name()};"
            f" color: {theme.INK.name()}; font-weight: bold;"
            f" border: 1px solid {theme.BRASS_MID.name()}; border-radius: 3px; }}"
            f"QPushButton:hover {{ background-color: {theme.BRASS_MID.name()};"
            f" color: {theme.PANEL_BG.name()}; }}"
        )


# --------------------------------------------------------------------------
#                          live voice / knob panel
# --------------------------------------------------------------------------


class _LiveVoicePanel(QFrame):
    """One voice's effective knobs for the active part.

    Edits land in the part's :class:`VoiceOverride` so jamming the
    Live knobs doesn't perturb the song-level baseline. The first
    edit on an inherited knob auto-creates the override key.
    """

    def __init__(
        self,
        *,
        voice_name: str,
        song_config: VoiceConfig,
        part: Part,
        on_dirty: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._voice_name = voice_name
        self._song_config = song_config
        self._part = part
        self._on_dirty = on_dirty

        title = QLabel(voice_name.upper())
        title.setObjectName("SectionTitle")

        self._pattern_section = CollapsibleSection("Pattern Knobs", expanded=True)
        self._feel_section = CollapsibleSection("Feel Knobs", expanded=False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self._pattern_section)
        layout.addWidget(self._feel_section)

        self._build_knob_rows()

    def _build_knob_rows(self) -> None:
        override = self._part.voice_overrides.get(self._voice_name)
        algo = (
            override.algorithm
            if override is not None and override.algorithm is not None
            else self._song_config.algorithm
        )
        schema = SCHEMAS.pattern_by_algo.get(algo, {})

        row = QHBoxLayout()
        row.setSpacing(10)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        count = 0
        for spec in schema.values():
            knob = self._make_knob(
                spec,
                effective=self._effective_pattern_value(spec),
                on_change=_make_pattern_setter(self, spec.name),
            )
            if knob is None:
                continue
            row.addWidget(knob)
            count += 1
            if count >= _KNOBS_PER_ROW:
                row.addStretch(1)
                container = QWidget()
                container.setLayout(row)
                self._pattern_section.add_widget(container)
                row = QHBoxLayout()
                row.setSpacing(10)
                row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                count = 0
        if count > 0:
            row.addStretch(1)
            container = QWidget()
            container.setLayout(row)
            self._pattern_section.add_widget(container)
        self._pattern_section.set_header_hint(f"{len(schema)} knobs")

        # Feel knobs.
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        count = 0
        for spec in FEEL_KNOBS:
            knob = self._make_knob(
                spec,
                effective=self._effective_feel_value(spec),
                on_change=_make_feel_setter(self, spec.name),
            )
            if knob is None:
                continue
            row.addWidget(knob)
            count += 1
            if count >= _KNOBS_PER_ROW:
                row.addStretch(1)
                container = QWidget()
                container.setLayout(row)
                self._feel_section.add_widget(container)
                row = QHBoxLayout()
                row.setSpacing(10)
                row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                count = 0
        if count > 0:
            row.addStretch(1)
            container = QWidget()
            container.setLayout(row)
            self._feel_section.add_widget(container)
        self._feel_section.set_header_hint(f"{len(FEEL_KNOBS)} knobs")

    def _make_knob(
        self,
        spec: KnobSpec,
        *,
        effective: Any,
        on_change: Callable[[Any], None],
    ) -> QWidget | None:
        # Live view focuses on continuous knobs. Choice / list / string
        # knobs are intentionally surfaced in Song / Parts views instead
        # — they're not "twiddle while jamming" controls.
        if spec.kind not in {"float", "int"}:
            return None
        if not isinstance(effective, int | float):
            return None
        knob = KnobWidget(
            label=spec.name,
            minimum=float(spec.minimum),
            maximum=float(spec.maximum),
            value=float(effective),
            step=max(1.0, float(spec.step)) if spec.kind == "int" else float(spec.step),
            decimals=spec.decimals,
            integer=spec.kind == "int",
        )

        def emit(v: float) -> None:
            on_change(int(v) if spec.kind == "int" else float(v))

        knob.value_changed.connect(emit)
        return knob

    # ----- effective value resolution ------------------------------------

    def _effective_pattern_value(self, spec: KnobSpec) -> Any:
        override = self._part.voice_overrides.get(self._voice_name)
        if override is not None and spec.name in override.pattern:
            return override.pattern[spec.name]
        if spec.name in self._song_config.pattern:
            return self._song_config.pattern[spec.name]
        return spec.default

    def _effective_feel_value(self, spec: KnobSpec) -> Any:
        override = self._part.voice_overrides.get(self._voice_name)
        if override is not None and spec.name in override.feel:
            return override.feel[spec.name]
        if spec.name in self._song_config.feel:
            return self._song_config.feel[spec.name]
        return spec.default

    # ----- write paths (always land in part override) ---------------------

    def _ensure_override(self) -> VoiceOverride:
        override = self._part.voice_overrides.get(self._voice_name)
        if override is None:
            override = VoiceOverride()
            self._part.voice_overrides[self._voice_name] = override
        return override

    def _set_pattern(self, name: str, value: Any) -> None:
        self._ensure_override().pattern[name] = value
        self._on_dirty()

    def _set_feel(self, name: str, value: Any) -> None:
        self._ensure_override().feel[name] = value
        self._on_dirty()


def _make_pattern_setter(panel: _LiveVoicePanel, name: str) -> Callable[[Any], None]:
    return lambda value: panel._set_pattern(name, value)


def _make_feel_setter(panel: _LiveVoicePanel, name: str) -> Callable[[Any], None]:
    return lambda value: panel._set_feel(name, value)
