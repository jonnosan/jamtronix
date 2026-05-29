"""PartEditorPanel — round-trip edits back into the bound ``Part``."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx.model import Key, Part, Song  # noqa: E402
from jtx_gui.widgets.part_editor_panel import PartEditorPanel  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _song_with_one_part() -> tuple[Song, Part]:
    song = Song(title="t", setup_ref="x", key=Key(tonic="C"))
    part = Part(bars=16, intensity_start=0.4, intensity_end=0.6, loop=False)
    song.parts = {"verse": part}
    return song, part


def test_intensity_knob_changes_round_trip(qapp: QApplication) -> None:
    song, part = _song_with_one_part()
    dirty: list[int] = []
    panel = PartEditorPanel()
    panel.set_part(song=song, part_name="verse", on_dirty=lambda: dirty.append(1))

    panel._intensity_start.set_value(0.75)
    panel._intensity_end.set_value(0.25)
    assert part.intensity_start == pytest.approx(0.75)
    assert part.intensity_end == pytest.approx(0.25)
    assert dirty, "expected on_dirty to fire on intensity edits"
    panel.deleteLater()


def test_loop_checkbox_round_trips(qapp: QApplication) -> None:
    song, part = _song_with_one_part()
    dirty: list[int] = []
    panel = PartEditorPanel()
    panel.set_part(song=song, part_name="verse", on_dirty=lambda: dirty.append(1))

    panel._loop.setChecked(True)
    assert part.loop is True
    assert dirty
    panel._loop.setChecked(False)
    assert part.loop is False
    panel.deleteLater()


def test_bars_spinbox_round_trips(qapp: QApplication) -> None:
    song, part = _song_with_one_part()
    dirty: list[int] = []
    panel = PartEditorPanel()
    panel.set_part(song=song, part_name="verse", on_dirty=lambda: dirty.append(1))

    panel._bars.setValue(64)
    assert part.bars == 64
    assert dirty
    panel.deleteLater()


def test_tempo_override_round_trip(qapp: QApplication) -> None:
    song, part = _song_with_one_part()
    panel = PartEditorPanel()
    panel.set_part(song=song, part_name="verse", on_dirty=lambda: None)

    assert part.tempo is None
    panel._tempo_check.setChecked(True)
    assert part.tempo is not None
    panel._tempo_spin.setValue(145)
    assert part.tempo == 145

    panel._tempo_check.setChecked(False)
    assert part.tempo is None
    panel.deleteLater()


def test_meter_override_round_trip(qapp: QApplication) -> None:
    song, part = _song_with_one_part()
    panel = PartEditorPanel()
    panel.set_part(song=song, part_name="verse", on_dirty=lambda: None)

    assert part.meter is None
    panel._meter_check.setChecked(True)
    # Toggling on writes the song's meter as a starting override.
    assert part.meter == song.meter

    panel._meter_edit.setText("3/4")
    panel._meter_edit.editingFinished.emit()
    assert part.meter == "3/4"

    panel._meter_check.setChecked(False)
    assert part.meter is None
    panel.deleteLater()


def test_set_part_with_unknown_name_clears(qapp: QApplication) -> None:
    song, _part = _song_with_one_part()
    panel = PartEditorPanel()
    panel.set_part(song=song, part_name="ghost", on_dirty=lambda: None)
    assert panel.current_part_name() is None
    panel.deleteLater()


def test_clear_disables_inputs(qapp: QApplication) -> None:
    song, _part = _song_with_one_part()
    panel = PartEditorPanel()
    panel.set_part(song=song, part_name="verse", on_dirty=lambda: None)
    assert panel._bars.isEnabled()
    panel.clear()
    assert not panel._bars.isEnabled()
    assert not panel._loop.isEnabled()
    assert panel.current_part_name() is None
    panel.deleteLater()
