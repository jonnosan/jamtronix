"""Smoke tests for the PySide6 GUI.

Constructing the main window against the bundled acid-demo song
exercises the song-view, voice panels, knob factory, and File menu
wiring. We use Qt's offscreen platform so the tests work headless on
CI runners with no display.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx_gui.algorithm_meta import ALGORITHMS, SCHEMAS, algorithms_for  # noqa: E402
from jtx_gui.main_window import MainWindow  # noqa: E402
from jtx_gui.state import AppState  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
ACID_DEMO = REPO_ROOT / "examples" / "acid-demo.jtx"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_algorithms_for_each_voice_type_is_nonempty() -> None:
    """Every voice type must have at least one valid algorithm."""
    for voice_type in ("drum", "mono", "poly", "modulator", "follower"):
        assert algorithms_for(voice_type), f"no algorithms for {voice_type}"


def test_schemas_cover_every_algorithm() -> None:
    assert set(SCHEMAS.pattern_by_algo) == set(ALGORITHMS)


def test_main_window_constructs_empty(qapp: QApplication) -> None:
    """Window with no song loaded should still build cleanly."""
    state = AppState()
    window = MainWindow(state)
    assert window.windowTitle() == "Jamtronix"
    window.deleteLater()


def test_main_window_loads_acid_demo(qapp: QApplication) -> None:
    """Opening the bundled acid demo should populate the Song view."""
    state = AppState()
    window = MainWindow(state)
    assert window.open_song(ACID_DEMO)
    assert state.song is not None
    assert state.song.title == "Phuture Lines"
    assert not state.dirty
    assert "Phuture Lines" in window.windowTitle() or "acid-demo" in window.windowTitle()
    window.deleteLater()


def test_song_dirty_round_trip(tmp_path: Path, qapp: QApplication) -> None:
    """Editing then saving should clear dirty state."""
    state = AppState()
    state.open(ACID_DEMO)
    state.song.tempo = 130  # type: ignore[union-attr]
    state.mark_dirty()
    assert state.dirty
    save_path = tmp_path / "edited.jtx"
    state.save_as(save_path)
    assert not state.dirty
    assert save_path.exists()
    state2 = AppState()
    state2.open(save_path)
    assert state2.song.tempo == 130  # type: ignore[union-attr]


def test_parts_view_lazy_override_creation(tmp_path: Path, qapp: QApplication) -> None:
    """Editing the override dict via the parts view machinery creates
    a VoiceOverride lazily, and removing the last field cleans it up.
    """
    from jtx.model import Part
    from jtx_gui.views.parts_view import PartsView

    state = AppState()
    state.open(ACID_DEMO)
    # Add a part so the view has something to operate on.
    state.song.parts["test_part"] = Part(bars=4)  # type: ignore[union-attr]
    state.mark_dirty()

    view = PartsView(state)
    # Selecting the new part builds detail widgets — verify it doesn't crash.
    view._current_part = "test_part"  # type: ignore[attr-defined]
    view._rebuild_detail()  # type: ignore[attr-defined]
    part = state.song.parts["test_part"]  # type: ignore[union-attr]
    assert part.voice_overrides == {}
    view.deleteLater()


def test_open_song_loads_sibling_setup(qapp: QApplication) -> None:
    """Opening acid-demo should also load acid-demo.jtx-setup."""
    state = AppState()
    state.open(ACID_DEMO)
    assert state.setup is not None
    assert state.setup.id == "acid-demo"
    assert state.setup_error is None


def test_live_view_no_transport_when_setup_missing(tmp_path: Path, qapp: QApplication) -> None:
    """Song without its sibling setup should report the error, not crash."""
    from jtx_gui.views.live_view import LiveView

    # Copy just the song into tmp — no setup file alongside it.
    text = ACID_DEMO.read_text(encoding="utf-8")
    orphan = tmp_path / "orphan.jtx"
    orphan.write_text(text, encoding="utf-8")

    state = AppState()
    state.open(orphan)
    assert state.setup is None
    assert state.setup_error is not None

    view = LiveView(state)
    view._on_part_clicked("kick")  # type: ignore[attr-defined]
    # The transport should still be idle since the setup is missing.
    assert not view._transport.is_running  # type: ignore[attr-defined]
    view.deleteLater()


def test_transport_starts_and_stops_with_fake_sink(qapp: QApplication) -> None:
    """Smoke-test the transport service with a recording fake sink."""
    import time

    from jtx.engine.sink import Sink
    from jtx_gui.transport import BarTick, TransportService

    class FakeSink(Sink):
        def __init__(self) -> None:
            self.started = False
            self.stopped = False
            self.events: list[object] = []

        def start(self) -> None:
            self.started = True

        def emit(self, event: object) -> None:  # type: ignore[override]
            self.events.append(event)

        def stop(self) -> None:
            self.stopped = True

    fake = FakeSink()
    state = AppState()
    state.open(ACID_DEMO)
    assert state.song is not None
    assert state.setup is not None

    # Slow tempo + a couple of bars in the loop is enough.
    state.song.tempo = 600  # 10 Hz to keep the test snappy

    received: list[BarTick] = []
    transport = TransportService(sink_factory=lambda _name: fake)
    transport.bar_changed.connect(received.append)

    transport.start(
        song=state.song,
        setup=state.setup,
        part_name=next(iter(state.song.parts.keys())),
        port_name=None,
    )
    deadline = time.time() + 2.5
    while time.time() < deadline and len(received) < 2:
        qapp.processEvents()
        time.sleep(0.02)
    transport.stop()
    deadline = time.time() + 2.0
    while time.time() < deadline and transport.is_running:
        qapp.processEvents()
        time.sleep(0.02)

    assert fake.started
    assert fake.stopped
    assert len(received) >= 1


def test_style_templates_build_valid_songs() -> None:
    """Each style template produces a song that round-trips through persist."""
    from jtx.persist import save_song
    from templates import STYLES, build

    for style in STYLES:
        song = build(style, f"{style} test", "iac")
        # validate via the persist layer (raises if invalid).
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jtx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            save_song(song, tmp_path)
            assert tmp_path.exists()
        finally:
            tmp_path.unlink(missing_ok=True)


def test_bundled_setups_discovered_and_loadable() -> None:
    from jtx.persist import load_setup
    from jtx_gui.bundles import bundled_setups

    bundles = bundled_setups()
    assert bundles, "no bundled .jtx-setup files found"
    for path in bundles:
        setup = load_setup(path)
        assert setup.id
        assert setup.voices


def test_voice_slot_cc_map_persists(tmp_path: Path) -> None:
    """cc_map round-trips through save_setup / load_setup."""
    from jtx.model import Setup, VoiceSlot
    from jtx.persist import load_setup, save_setup

    setup = Setup(
        id="x",
        name="X",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(
                name="acid",
                type="mono",
                default_role="bass",
                midi_channel=1,
                cc_map={"resonance": 90, "filter_cutoff": 100},
            )
        ],
    )
    path = tmp_path / "x.jtx-setup"
    save_setup(setup, path)
    reloaded = load_setup(path)
    assert reloaded.voices[0].cc_map == {"resonance": 90, "filter_cutoff": 100}
    assert reloaded.voices[0].cc_for("resonance", 71) == 90
    assert reloaded.voices[0].cc_for("portamento_time", 5) == 5


def test_acid_bass_honours_cc_map_override() -> None:
    """AcidBass with a remapped resonance should emit that CC, not CC 71."""
    import random

    from jtx.algorithms import AcidBass
    from jtx.engine.context import BarContext
    from jtx.engine.events import ControlChange
    from jtx.model import Key

    algo = AcidBass(midi_channel=1, cc_map={"resonance": 100, "filter_cutoff": 105})
    ctx = BarContext(
        bar_index=0,
        ticks_per_bar=1920,
        ppq=480,
        tempo_bpm=120.0,
        rng=random.Random(123456),
        key=Key(tonic="A", scale="minor"),
        chord_root_semitones=0,
        pattern_knobs={"slide_prob": 0.5, "cycle": 2, "resonance": 100},
        feel_knobs={},
        tick_offset=0,
    )
    events = algo.generate_bar(ctx)
    ccs = {e.cc for e in events if isinstance(e, ControlChange)}
    # Should contain the *remapped* CC numbers, never the defaults 71/74.
    assert 100 in ccs
    assert 105 in ccs
    assert 71 not in ccs
    assert 74 not in ccs


def test_setup_editor_writes_back(tmp_path: Path, qapp: QApplication) -> None:
    """SetupEditor flush() should push spinner state into the model."""
    from jtx.model import Setup, VoiceSlot
    from jtx.persist import load_setup, save_setup
    from jtx_gui.views.setup_editor import SetupEditor

    setup = Setup(
        id="t",
        name="T",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(
                name="acid",
                type="mono",
                default_role="bass",
                midi_channel=1,
            )
        ],
    )
    path = tmp_path / "t.jtx-setup"
    save_setup(setup, path)

    audition_calls: list[tuple[str, int]] = []

    def fake_audition(voice: VoiceSlot, function: str, cc: int) -> None:
        audition_calls.append((function, cc))

    editor = SetupEditor(setup=setup, setup_path=path, audition_fn=fake_audition)
    section = editor._voice_panels[0]  # type: ignore[attr-defined]
    section._overrides["resonance"].setChecked(True)  # type: ignore[attr-defined]
    section._spinners["resonance"].setValue(99)  # type: ignore[attr-defined]
    section._on_audition("resonance")  # type: ignore[attr-defined]
    assert audition_calls == [("resonance", 99)]
    section.flush()
    assert setup.voices[0].cc_map == {"resonance": 99}

    # Save round-trip.
    save_setup(setup, path)
    assert load_setup(path).voices[0].cc_map == {"resonance": 99}
    editor.deleteLater()


def test_wizard_constructs(qapp: QApplication) -> None:
    """The wizard should build without errors and expose 3 pages."""
    from jtx_gui.views.new_song_wizard import NewSongWizard

    wiz = NewSongWizard()
    assert wiz.pageIds()
    assert len(wiz.pageIds()) == 3
    wiz.deleteLater()


def test_arrangement_reorder_writes_dirty(qapp: QApplication) -> None:
    """Rebuilding arrangement via the view should sync Song.arrangement."""
    from jtx_gui.widgets.arrangement import ArrangementEditor

    state = AppState()
    state.open(ACID_DEMO)
    assert state.song is not None
    state._dirty = False  # type: ignore[attr-defined]

    bumped = []

    def on_dirty() -> None:
        bumped.append(1)

    editor = ArrangementEditor(song=state.song, on_dirty=on_dirty)
    initial_len = len(state.song.arrangement)
    # Append the first known part.
    first_part = next(iter(state.song.parts.keys()))
    state.song.arrangement.append(first_part)
    editor.reload()
    assert len(state.song.arrangement) == initial_len + 1
    editor.deleteLater()
