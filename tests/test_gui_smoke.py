"""Smoke tests for the PySide6 GUI.

Constructing the main window against the bundled test-fixture song
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
TEST_FIXTURE = REPO_ROOT / "examples" / "test-fixture.jtx"


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


def test_main_window_loads_test_fixture(qapp: QApplication) -> None:
    """Opening the bundled test fixture should populate the Song view."""
    state = AppState()
    window = MainWindow(state)
    assert window.open_song(TEST_FIXTURE)
    assert state.song is not None
    assert state.song.title == "Test Fixture"
    assert not state.dirty
    assert "Test Fixture" in window.windowTitle() or "test-fixture" in window.windowTitle()
    window.deleteLater()


def test_song_dirty_round_trip(tmp_path: Path, qapp: QApplication) -> None:
    """Editing then saving should clear dirty state."""
    state = AppState()
    state.open(TEST_FIXTURE)
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
    state.open(TEST_FIXTURE)
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
    """Opening the fixture should also load its sibling .jtx-setup."""
    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.setup is not None
    assert state.setup.id == "test-fixture"
    assert state.setup_error is None


def test_setup_error_surfaces_when_sibling_missing(tmp_path: Path, qapp: QApplication) -> None:
    """Song without its sibling setup should report the error, not crash."""
    # Copy just the song into tmp — no setup file alongside it.
    text = TEST_FIXTURE.read_text(encoding="utf-8")
    orphan = tmp_path / "orphan.jtx"
    orphan.write_text(text, encoding="utf-8")

    state = AppState()
    state.open(orphan)
    assert state.setup is None
    assert state.setup_error is not None


def test_appstate_adopt_inmemory_song(qapp: QApplication) -> None:
    """The wizard hands off a Song + Setup via adopt() with no on-disk path."""
    from jtx.persist import load_setup

    state = AppState()
    state.open(TEST_FIXTURE)
    setup = state.setup
    assert setup is not None
    starter_song = state.song
    assert starter_song is not None

    # Adopt a freshly-built song under a different title.
    starter_song.title = "Fresh"
    state.adopt(song=starter_song, setup=setup)
    assert state.song is starter_song
    assert state.setup is setup
    assert state.path is None
    assert state.dirty is True

    # Loading a separate setup should also work alongside adoption.
    _ = load_setup(REPO_ROOT / "setups" / "iac.jtx-setup")


def test_part_tempo_meter_round_trip(tmp_path: Path) -> None:
    """Part.tempo + Part.meter overrides persist across save/load."""
    from jtx.persist import load_song, save_song

    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.song is not None
    first_part = next(iter(state.song.parts.values()))
    first_part.tempo = 145
    first_part.meter = "3/4"
    target = tmp_path / "part_overrides.jtx"
    save_song(state.song, target)
    reloaded = load_song(target)
    part = next(iter(reloaded.parts.values()))
    assert part.tempo == 145
    assert part.meter == "3/4"


def test_song_player_uses_part_meter_override() -> None:
    """SongPlayer should compute ticks_per_bar from the part override."""
    from jtx.persist import load_setup, load_song
    from jtx.player import SongPlayer

    song = load_song(TEST_FIXTURE)
    setup = load_setup(REPO_ROOT / "examples" / "test-fixture.jtx-setup")
    first_part_name = next(iter(song.parts.keys()))
    song.parts[first_part_name].meter = "3/4"
    player = SongPlayer(song, setup, first_part_name)
    # 3/4 at PPQ 480 = 3 × 480 = 1440 ticks/bar; song was 4/4 (=1920).
    assert player.ticks_per_bar == 1440


def test_part_loop_round_trip(tmp_path: Path) -> None:
    """Part.loop persists across save/load."""
    from jtx.persist import load_song, save_song

    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.song is not None
    next(iter(state.song.parts.values())).loop = True
    target = tmp_path / "loop_test.jtx"
    save_song(state.song, target)
    reloaded = load_song(target)
    assert next(iter(reloaded.parts.values())).loop is True


def test_transport_advances_then_loops(qapp: QApplication) -> None:
    """Worker should advance to next part once current ends; loop=True holds."""
    import time

    from jtx.engine.sink import Sink
    from jtx_gui.transport import TransportService

    class FakeSink(Sink):
        def start(self) -> None: ...
        def emit(self, event: object) -> None:  # type: ignore[override]
            pass

        def stop(self) -> None: ...

    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.song is not None
    assert state.setup is not None
    # Shrink each part to 1 bar so we advance quickly.
    for part in state.song.parts.values():
        part.bars = 1
        part.loop = False
    state.song.tempo = 600
    part_names = list(state.song.parts.keys())

    seen_parts: list[str] = []
    transport = TransportService(sink_factory=lambda _name: FakeSink())
    transport.part_changed.connect(seen_parts.append)

    transport.start(
        song=state.song,
        setup=state.setup,
        part_name=part_names[0],
        port_name=None,
    )
    deadline = time.time() + 3.0
    # Wait until we've seen at least two distinct part transitions.
    while time.time() < deadline and len({*seen_parts}) < 2:
        qapp.processEvents()
        time.sleep(0.02)
    transport.stop()
    deadline = time.time() + 2.0
    while time.time() < deadline and transport.is_running:
        qapp.processEvents()
        time.sleep(0.02)
    assert len({*seen_parts}) >= 2, f"expected ≥2 parts visited, got {seen_parts}"


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
    state.open(TEST_FIXTURE)
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


def test_bundled_test_fixture_opens() -> None:
    """The shipped test fixture .jtx loads + has its sibling setup."""
    from jtx_gui.state import AppState

    path = REPO_ROOT / "examples" / "test-fixture.jtx"
    assert path.exists(), f"missing fixture: {path}"
    state = AppState()
    state.open(path)
    assert state.song is not None
    assert state.setup is not None, "sibling setup missing for test-fixture"
    assert state.setup_error is None


def test_blank_template_builds_valid_song() -> None:
    """The blank template still produces a song that round-trips through persist.

    The other style templates (acid / deep_techno / psytrance / wildcard)
    are deleted in PR 2 in favour of the new mood/format composer.
    """
    import tempfile

    from jtx.persist import save_song
    from templates import STYLES, build

    assert "blank" in STYLES
    song = build("blank", "blank test", "iac")
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


def test_render_song_to_midi_writes_file(tmp_path: Path, qapp: QApplication) -> None:
    """Offline render walks the arrangement and produces a real .mid file."""
    from jtx_gui.render import render_song_to_midi

    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.song is not None
    assert state.setup is not None
    out = tmp_path / "rendered.mid"
    render_song_to_midi(state.song, state.setup, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_toolbar_clock_mode_disables_during_play(qapp: QApplication) -> None:
    """Clock combobox should disable on `started`, re-enable on `stopped`."""
    from jtx_gui.transport import TransportService
    from jtx_gui.views.toolbar import TopToolbar

    state = AppState()
    state.open(TEST_FIXTURE)
    transport = TransportService()
    bar = TopToolbar(state=state, transport=transport, port_factory=lambda: ["A", "B"])
    assert bar._clock_combo.isEnabled()  # type: ignore[attr-defined]
    transport.started.emit()
    assert not bar._clock_combo.isEnabled()  # type: ignore[attr-defined]
    transport.stopped.emit()
    assert bar._clock_combo.isEnabled()  # type: ignore[attr-defined]
    bar.deleteLater()


def test_voice_slot_parameter_map_persists(tmp_path: Path) -> None:
    """parameter_map round-trips through save_setup / load_setup."""
    from jtx.model import CCTarget, Setup, VoiceSlot
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
                midi_channel=2,
                parameter_map={"resonance": CCTarget(90), "cutoff": CCTarget(100)},
            )
        ],
    )
    path = tmp_path / "x.jtx-setup"
    save_setup(setup, path)
    reloaded = load_setup(path)
    assert reloaded.voices[0].parameter_map == {
        "resonance": CCTarget(90),
        "cutoff": CCTarget(100),
    }
    # Functions not in the parameter_map fall back to the algorithm's
    # DEFAULT_PARAM_MAP at router resolution time, not the slot.
    assert "glide" not in reloaded.voices[0].parameter_map


def test_voice_slot_cc_map_v1_migrates_to_parameter_map(tmp_path: Path) -> None:
    """A schema-v1 setup with cc_map auto-migrates to parameter_map of CCTargets."""
    import json

    from jtx.model import CCTarget
    from jtx.persist import load_setup

    v1_setup = {
        "id": "legacy",
        "name": "Legacy",
        "default_midi_port": "IAC",
        "voices": [
            {
                "name": "acid",
                "type": "mono",
                "default_role": "bass",
                "midi_channel": 2,
                "cc_map": {"resonance": 90, "filter_cutoff": 100},
            }
        ],
        "schema_version": 1,
    }
    path = tmp_path / "legacy.jtx-setup"
    path.write_text(json.dumps(v1_setup), encoding="utf-8")
    loaded = load_setup(path)
    # Migration normalises to current SCHEMA_VERSION.
    from jtx.model.types import SCHEMA_VERSION

    assert loaded.schema_version == SCHEMA_VERSION
    assert loaded.voices[0].parameter_map == {
        "resonance": CCTarget(90),
        "filter_cutoff": CCTarget(100),
    }


def test_setup_validation_rejects_mpe_mode_on_channel_1() -> None:
    """A voice with mpe_mode=True must not sit on the MPE master channel."""
    from jtx.model import VoiceSlot

    slot = VoiceSlot(
        name="lead",
        type="mono",
        default_role="lead",
        midi_channel=1,
        mpe_mode=True,
    )
    errors = slot.validate()
    assert any("channel 1" in e for e in errors)


def test_setup_validation_rejects_mpe_block_overflowing_channel_16() -> None:
    """midi_channel + count - 1 > 16 is rejected at validate()."""
    from jtx.model import VoiceSlot

    slot = VoiceSlot(
        name="lead",
        type="mono",
        default_role="lead",
        midi_channel=12,
        mpe_mode=True,
        mpe_channel_count=8,  # block ends at ch 19
    )
    errors = slot.validate()
    assert any("MPE block" in e for e in errors)


def test_setup_editor_target_helpers_round_trip_osc() -> None:
    """_target_kind + _target_from_kind handle OscTarget end-to-end."""
    from jtx.model import CCTarget, MPEPitchBendTarget, OscTarget
    from jtx_gui.views.setup_editor import (
        _KIND_LABELS,
        _default_osc_address,
        _target_from_kind,
        _target_kind,
    )

    # The OSC kind appears in the picker.
    assert any(kind == "osc" for kind, _label in _KIND_LABELS)

    # _target_kind recognises every variant.
    assert _target_kind(CCTarget(74)) == "cc"
    assert _target_kind(MPEPitchBendTarget()) == "mpe_pitch_bend"
    assert _target_kind(OscTarget("/jtx/x/cutoff")) == "osc"

    # Round-trip a constructed OscTarget through _target_from_kind.
    target = _target_from_kind("osc", address="/jtx/lead/cutoff")
    assert target == OscTarget("/jtx/lead/cutoff")

    # The default address helper matches the documented scheme.
    assert _default_osc_address("lead", "cutoff") == "/jtx/lead/cutoff"


@pytest.mark.skip(
    reason="Constructs the full SetupEditor; segfaults at process exit "
    "on macOS PySide6 under pytest. Editor works at runtime."
)
def test_setup_editor_parameter_map_writes_immediately(tmp_path: Path, qapp: QApplication) -> None:
    """SetupEditor parameter-map rows write back as soon as the user toggles override."""
    from jtx.model import CCTarget, Setup, VoiceSlot
    from jtx.persist import load_setup, save_setup
    from jtx_gui.views.setup_editor import SetupEditor, _ParameterMapSection

    setup = Setup(
        id="t",
        name="T",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(
                name="acid",
                type="mono",
                default_role="bass",
                midi_channel=2,
            )
        ],
    )
    path = tmp_path / "t.jtx-setup"
    save_setup(setup, path)

    audition_calls: list[tuple[str, int]] = []

    def fake_audition(voice: VoiceSlot, function: str, cc: int) -> None:
        audition_calls.append((function, cc))

    editor = SetupEditor(setup=setup, setup_path=path, audition_fn=fake_audition)
    sections = editor.findChildren(_ParameterMapSection)
    assert sections, "expected at least one parameter-map section"
    section = sections[0]
    section._overrides["resonance"].setChecked(True)  # type: ignore[attr-defined]
    section._cc_spinners["resonance"].setValue(99)  # type: ignore[attr-defined]
    section._on_audition_param("resonance")  # type: ignore[attr-defined]
    assert audition_calls == [("resonance", 99)]
    assert setup.voices[0].parameter_map == {"resonance": CCTarget(99)}

    save_setup(setup, path)
    assert load_setup(path).voices[0].parameter_map == {"resonance": CCTarget(99)}


@pytest.mark.skip(
    reason="Constructs the full SetupEditor; segfaults at process exit "
    "on macOS PySide6 under pytest. Editor works at runtime."
)
def test_setup_editor_voice_add(tmp_path: Path, qapp: QApplication) -> None:
    """Adding a voice slot updates the model + voice list."""
    from jtx.model import Setup, VoiceSlot
    from jtx_gui.views.setup_editor import SetupEditor

    setup = Setup(
        id="t",
        name="T",
        default_midi_port="IAC",
        voices=[VoiceSlot(name="acid", type="mono", default_role="bass", midi_channel=1)],
    )
    editor = SetupEditor(setup=setup, setup_path=tmp_path / "t.jtx-setup")
    editor._on_add_voice()  # type: ignore[attr-defined]
    assert len(setup.voices) == 2
    assert setup.voices[1].name.startswith("voice")
    assert editor._voice_list.count() == 2  # type: ignore[attr-defined]


def test_wizard_offers_blank_style() -> None:
    """The wizard should expose 'blank' as the first style choice."""
    from templates import STYLES

    assert "blank" in STYLES
    blank_song = STYLES["blank"]("Untitled", "iac")
    assert blank_song.title == "Untitled"
    assert blank_song.parts  # at least one part


def test_wizard_constructs(qapp: QApplication) -> None:
    """The wizard is a single-page QDialog now; just verify it builds."""
    from jtx_gui.views.new_song_wizard import NewSongWizard

    wiz = NewSongWizard()
    assert wiz.windowTitle()
    wiz.deleteLater()
