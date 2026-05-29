"""Tests for the live-reroll path on the Composer view.

Covers the plumbing added in PR 2 of the GUI rework (#153):

* :meth:`TransportService.queue_song` swaps the worker's active song
  at the next bar boundary and preserves ``bar_index`` when the
  current part name persists in the new song.
* :class:`ComposerView` debounces value_committed signals from the
  mood pad, sonics pad, and chaos knob into a single compose() call.
* :meth:`ComposerView._on_format_changed` prompts on dirty state and
  reverts the combo when the user declines.
"""

from __future__ import annotations

import copy
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from jtx.engine.sink import Sink  # noqa: E402
from jtx_gui.state import AppState  # noqa: E402
from jtx_gui.transport import BarTick, TransportService  # noqa: E402
from jtx_gui.views.composer_view import ComposerView  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_FIXTURE = REPO_ROOT / "examples" / "test-fixture.jtx"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class _FakeSink(Sink):
    """Discards events — just lets the worker spin its bar loop."""

    def start(self) -> None: ...

    def emit(self, event: object) -> None:  # type: ignore[override]
        pass

    def stop(self) -> None: ...


def _wait_until(qapp: QApplication, predicate, *, timeout_s: float = 2.5) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline and not predicate():
        qapp.processEvents()
        time.sleep(0.02)


def _shutdown(transport: TransportService, qapp: QApplication) -> None:
    transport.stop()
    _wait_until(qapp, lambda: not transport.is_running, timeout_s=2.0)


# --------------------------------------------------------------------------
#                       TransportService.queue_song
# --------------------------------------------------------------------------


def test_queue_song_swaps_at_bar_boundary_preserving_bar_index(
    qapp: QApplication,
) -> None:
    """queue_song swaps in the new song without resetting bar_index.

    Bar-index continuity matters musically: if the user is mid-jam on
    bar 2 of "intro" when they nudge the sonics pad, the swap should
    land on bar 3 of the new "intro", not restart at bar 0.
    """
    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.song is not None
    assert state.setup is not None
    state.song.tempo = 600  # fast clock keeps the test snappy

    song1 = state.song
    song2 = copy.deepcopy(song1)
    song2.texture = 0.9  # cosmetic diff — same parts, same structure

    part_name = next(iter(song1.parts.keys()))
    transport = TransportService(sink_factory=lambda _name: _FakeSink())
    ticks: list[BarTick] = []
    transport.bar_changed.connect(ticks.append)

    transport.start(
        song=song1, setup=state.setup, part_name=part_name, port_name=None,
    )
    try:
        _wait_until(qapp, lambda: len(ticks) >= 2)
        assert len(ticks) >= 2

        pre_count = len(ticks)
        pre_last_bar = ticks[-1].bar_index
        transport.queue_song(song2)
        _wait_until(qapp, lambda: len(ticks) > pre_count)
        assert len(ticks) > pre_count, "queued song never produced a tick"

        post = ticks[pre_count]
        assert post.part_name == part_name
        # bar_index keeps incrementing (it wraps at the part's bar count).
        expected = (pre_last_bar + 1) % max(1, song2.parts[part_name].bars)
        assert post.bar_index == expected, (
            f"bar_index = {post.bar_index} after swap; "
            f"expected {expected} (continuity)"
        )
    finally:
        _shutdown(transport, qapp)


def test_queue_song_resets_bar_index_when_part_missing(
    qapp: QApplication,
) -> None:
    """If the new song lacks the current part, fall back to its first
    part with bar_index = 0."""
    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.song is not None
    assert state.setup is not None
    state.song.tempo = 600

    song1 = state.song
    song2 = copy.deepcopy(song1)
    # Force song2 to have a completely disjoint part-name set.
    _, only_part = next(iter(song2.parts.items()))
    song2.parts = {"renamed_only_part": only_part}

    part_name = next(iter(song1.parts.keys()))
    transport = TransportService(sink_factory=lambda _name: _FakeSink())
    ticks: list[BarTick] = []
    transport.bar_changed.connect(ticks.append)
    transport.start(
        song=song1, setup=state.setup, part_name=part_name, port_name=None,
    )
    try:
        _wait_until(qapp, lambda: len(ticks) >= 2)
        pre_count = len(ticks)
        transport.queue_song(song2)
        _wait_until(qapp, lambda: len(ticks) > pre_count)
        assert len(ticks) > pre_count

        post = ticks[pre_count]
        assert post.part_name == "renamed_only_part"
        assert post.bar_index == 0
    finally:
        _shutdown(transport, qapp)


# --------------------------------------------------------------------------
#                       ComposerView debounced reroll
# --------------------------------------------------------------------------


def test_composer_debounced_reroll_coalesces_signals(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A burst of value_committed signals fires _commit_reroll once."""
    state = AppState()
    view = ComposerView(state)

    calls: list[int] = []
    # Rewire the timer's timeout signal at the Qt level so the new
    # callable is what fires, not the bound method captured at connect time.
    view._reroll_timer.timeout.disconnect()
    view._reroll_timer.timeout.connect(lambda: calls.append(1))

    # Fire a burst within the 200ms debounce window.
    view._mood_pad.value_committed.emit(0.1, 0.2)
    view._mood_pad.value_committed.emit(0.3, 0.4)
    view._sonics_pad.value_committed.emit(0.5, 0.6)
    view._chaos.value_committed.emit(0.7)

    _wait_until(qapp, lambda: len(calls) >= 1, timeout_s=1.5)
    # Drain any extra timer events to confirm we don't get duplicates.
    deadline = time.time() + 0.3
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)

    assert calls == [1], f"expected exactly one compose call, got {len(calls)}"
    view.deleteLater()


def test_composer_reroll_replaces_song_in_place_without_dirty(
    qapp: QApplication,
) -> None:
    """The debounced commit lands a fresh song via replace_song_in_place.

    Verifies the wiring end-to-end: nudging the sonics pad triggers a
    commit that hands AppState a new Song without flipping the dirty
    flag (replace_song_in_place is the no-fanfare path for re-rolls).
    """
    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.song is not None
    original_song = state.song
    assert not state.dirty

    view = ComposerView(state)
    view._commit_reroll()
    # A fresh compose returns a different Song instance.
    assert state.song is not None
    assert state.song is not original_song
    # Still not dirty — re-roll is settings-driven, not a user edit.
    assert not state.dirty
    view.deleteLater()


def test_composer_reroll_queues_song_when_transport_running(
    qapp: QApplication,
) -> None:
    """If playback is running, _commit_reroll also queue_songs the new roll."""
    state = AppState()
    state.open(TEST_FIXTURE)
    assert state.song is not None
    assert state.setup is not None
    state.song.tempo = 600

    transport = TransportService(sink_factory=lambda _name: _FakeSink())
    view = ComposerView(state, transport=transport)

    part_name = next(iter(state.song.parts.keys()))
    transport.start(
        song=state.song, setup=state.setup, part_name=part_name, port_name=None,
    )
    try:
        # Spy on the worker's queue_song to verify it was called.
        queued: list[object] = []
        assert transport._worker is not None
        original = transport._worker.queue_song

        def spy(song):  # type: ignore[no-untyped-def]
            queued.append(song)
            return original(song)

        transport._worker.queue_song = spy  # type: ignore[assignment]
        view._commit_reroll()
        assert len(queued) == 1, "transport.queue_song should have been called once"
    finally:
        _shutdown(transport, qapp)
    view.deleteLater()


# --------------------------------------------------------------------------
#                       Format-change confirmation
# --------------------------------------------------------------------------


def test_format_change_prompts_when_dirty_and_revert_on_decline(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When dirty, changing format prompts; declining reverts the combo."""
    state = AppState()
    state.open(TEST_FIXTURE)
    state.mark_dirty()
    assert state.song is not None
    view = ComposerView(state)
    current_fmt = state.song.format

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *_a, **_kw: QMessageBox.StandardButton.No),
    )

    # Pick a format that's different from the song's current one.
    target_fmt = "song" if current_fmt != "song" else "loop"
    target_idx = view._format_combo.findData(target_fmt)
    assert target_idx >= 0
    view._format_combo.setCurrentIndex(target_idx)

    # The combo should have reverted, and the song's format is unchanged.
    assert view._format_combo.currentData() == current_fmt
    assert state.song.format == current_fmt
    view.deleteLater()


def test_format_change_no_prompt_when_clean(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No popup fires when the state is clean — compose runs directly."""
    state = AppState()
    state.open(TEST_FIXTURE)  # dirty=False
    assert state.song is not None
    view = ComposerView(state)
    current_fmt = state.song.format

    popups: list[int] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(
            lambda *_a, **_kw: (
                popups.append(1) or QMessageBox.StandardButton.Yes
            )
        ),
    )

    target_fmt = "song" if current_fmt != "song" else "loop"
    target_idx = view._format_combo.findData(target_fmt)
    view._format_combo.setCurrentIndex(target_idx)

    assert popups == []
    assert state.song is not None
    assert state.song.format == target_fmt
    view.deleteLater()
